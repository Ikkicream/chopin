#!/usr/bin/env python3
"""dashboard_stats_backend.py — Statistiques hebdomadaires et inventaire des bases.

Deux besoins distincts, volontairement rendus en DEUX tableaux séparés :
  - ce qui SORT   : les emails envoyés et ce qu'ils ont produit (ouvertures, clics, échecs)
  - ce qui ENTRE  : les contacts scrapés et ce qu'il en reste après validation

Les mélanger était précisément ce qui rendait le tableau de bord illisible.

Découpage par JOUR, à l'heure de PARIS, sur 7, 15 ou 31 jours. Les horodatages sont stockés
en UTC ; le scraping tourne de 22 h à 8 h heure de Paris, donc à cheval sur minuit UTC.
Regrouper sur l'UTC ferait basculer une partie d'une nuit dans le jour précédent. Le
regroupement est fait en Python plutôt qu'en SQL : les volumes sont petits, le résultat est
exact aux changements d'heure près, et le code survivra tel quel à la migration PostgreSQL.

Chaque jour porte un `statut` qui pilote le surlignage :
  - `inactif`  : aucune activité alors qu'il aurait dû y en avoir  → surligné en ROUGE
  - `ferme`    : dimanche, aucun envoi n'est prévu (fenêtre lun-sam) → neutre
  - `en_cours` : la journée n'est pas finie                          → neutre
  - `ok`       : activité constatée
Sans cette distinction, chaque dimanche et chaque matin s'afficheraient en rouge, et l'alerte
deviendrait un bruit de fond qu'on cesse de regarder.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"
POOL_DB = BASE_DIR / "data" / "contacts.duckdb"
PARIS = ZoneInfo("Europe/Paris")

_MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
         "juil.", "août", "sept.", "oct.", "nov.", "déc."]


# ── Découpage en semaines ─────────────────────────────────────────────────────

def _to_paris(ts) -> datetime | None:
    """Horodatage de la base → datetime conscient du fuseau de Paris."""
    if ts is None:
        return None
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(PARIS)


_JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def _day_label(d: datetime) -> str:
    """« mar. 19 août »."""
    return f"{_JOURS[d.weekday()]} {d.day} {_MOIS[d.month - 1]}"


def _midnight(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _day_skeleton(days: int) -> tuple[list[datetime], dict]:
    """Les `days` derniers jours, le plus récent d'abord, et leur index vide.

    Construit AVANT d'interroger les bases : un jour sans activité doit apparaître avec des
    zéros et non disparaître — c'est précisément l'information que le user veut voir.
    """
    today = _midnight(datetime.now(PARIS))
    jours = [today - timedelta(days=i) for i in range(days)]
    return jours, {j.date().isoformat(): {} for j in jours}


def _statut(jour: datetime, actif: bool, ferme_le_dimanche: bool) -> str:
    """Statut d'une journée, qui décide du surlignage côté interface."""
    if actif:
        return "ok"
    if _midnight(datetime.now(PARIS)) == jour:
        return "en_cours"          # la journée n'est pas finie : pas d'alarme
    if ferme_le_dimanche and jour.weekday() == 6:
        return "ferme"             # fenêtre d'envoi lun-sam : un dimanche vide est normal
    return "inactif"               # anomalie : rouge


def _bucket(rows, index: dict, key: str, jours: list[datetime], amount_idx: int | None = None):
    """Range des horodatages dans les jours du squelette.

    `rows` = [(timestamp,)] ou [(timestamp, quantité)] si `amount_idx` est fourni.
    """
    first = jours[-1]
    for r in rows:
        p = _to_paris(r[0])
        if p is None or p < first:
            continue
        k = _midnight(p).date().isoformat()
        if k in index:
            index[k][key] = index[k].get(key, 0) + (int(r[amount_idx] or 0)
                                                    if amount_idx is not None else 1)


def _connect(path, attempts: int = 8, sleep_s: float = 0.3):
    """Ouvre une base DuckDB en tolérant les DEUX échecs propres à un process partagé.

    1. Le verrou d'écriture : un scrape ou un nettoyage tient la base.
    2. Le **conflit de configuration** : dans un même process, DuckDB met l'instance de base
       en cache. Une connexion en lecture seule et une connexion en lecture-écriture sur le
       même fichier ne peuvent donc pas coexister — la seconde lève
       « Can't open a connection to same database file with a different configuration ».

    Le point 2 s'est payé cash le 19/08/2026 : ces statistiques ouvraient god_mode.duckdb en
    lecture seule pendant que `campaign_engine.list_campaigns` l'ouvrait en lecture-écriture
    pour la même page. L'API renvoyait une erreur, l'interface l'avalait, et la page
    Campagnes affichait « 0 campagne » alors que la base en contenait huit.

    On tente la **lecture-écriture d'abord**, contre-intuitif pour un module qui n'écrit
    jamais : c'est la configuration qu'utilisent tous les autres modules de l'API
    (`god_mode_backend`, `campaign_engine`). Ouvrir en lecture seule mettrait en cache une
    instance que ces modules ne peuvent plus rejoindre — eux n'ont aucun repli, et c'est la
    page Campagnes qui tombe. La lecture seule reste en second, pour les usages hors API
    (CLI, inventaire) où rien d'autre n'est ouvert.
    """
    last = None
    for i in range(attempts):
        for read_only in (False, True):
            try:
                return duckdb.connect(str(path), read_only=read_only)
            except Exception as e:  # noqa: BLE001
                last = e
        if i < attempts - 1:
            time.sleep(sleep_s)
    raise last  # type: ignore[misc]


def _god():
    return _connect(GOD_DB)


# ── Canaux de routage ─────────────────────────────────────────────────────────
# Un envoi est estampillé « {site}-{campagne}-{date} » : c'est l'identifiant du DISPATCH,
# pas celui de la campagne. On en extrait la campagne pour rattacher chaque email à son
# canal — sans quoi le tableau de bord annonce un volume quotidien sans dire par où il est
# parti, alors que Maildoso, Sweego et Emelia n'ont ni la même réputation, ni le même coût,
# ni les mêmes limites.

_RE_DISPATCH = re.compile(r"^[a-z]{2,5}-(.+)-\d{4}-\d{2}-\d{2}$")

CANAUX = ("maildoso", "sweego", "emelia")


def _campagne_du_dispatch(dispatch_id: str | None) -> str | None:
    m = _RE_DISPATCH.match(dispatch_id or "")
    return m.group(1) if m else None


# ── Tableau 1 : ce qui sort ───────────────────────────────────────────────────

def daily_email_stats(site: str, days: int = 7) -> dict:
    """Emails envoyés par JOUR, et ce qu'ils ont produit.

    Sources, et pourquoi celles-là :

    - `envoyes` / `destinataires` : journal `maildoso_sent` (une ligne par destinataire) plus
      les campagnes de masse Sweego, qui ne fournissent qu'un compteur global.
    - `redites` = envoyés − destinataires uniques du jour. C'est LE chiffre à surveiller : en
      août 2026, 1 189 envois n'ont touché que 724 personnes, et quatre adresses ont reçu
      jusqu'à 18 fois le même message. Une valeur non nulle doit alerter.
    - `ouvreurs` / `cliqueurs` : `contact_site_history` et NON `sweego_events`. Les emails
      maildoso sont tracés par le pixel `/api/track/open`, qui écrit dans le pool ;
      `sweego_events` ne couvre que le canal Sweego et contient en outre le trafic des boîtes
      de test et les ouvertures par proxy anti-spam — s'en servir donnait des taux à 15 000 %.

    Limite assumée : le pool ne retient que la DERNIÈRE ouverture par contact. Ces colonnes
    comptent donc des *personnes ayant ouvert ce jour-là*, pas un nombre d'ouvertures. C'est
    exactement ce que la table `email_events` de la migration PostgreSQL corrigera.
    """
    jours, idx = _day_skeleton(days)
    depuis = jours[-1].astimezone(timezone.utc).replace(tzinfo=None)

    c = _god()
    try:
        envois = c.execute(
            "SELECT created_at, lower(to_email), campaign_id FROM maildoso_sent "
            "WHERE site_code = ? AND status = 'sent' AND created_at >= ?",
            [site, depuis]).fetchall()
        _bucket([(t,) for t, _, _ in envois], idx, "envoyes", jours)

        # Destinataires DISTINCTS par jour : il faut dédupliquer à l'intérieur de chaque
        # journée, ce qu'un simple comptage ne saurait pas faire.
        vus: dict[str, set] = {}
        for t, em, _cid in envois:
            p = _to_paris(t)
            if p is None or p < jours[-1]:
                continue
            k = _midnight(p).date().isoformat()
            if k in idx:
                vus.setdefault(k, set()).add(em)

        masse = c.execute(
            "SELECT created_at, recipients_count, campaign_id FROM mass_campaigns "
            "WHERE site_code = ? AND created_at >= ?", [site, depuis]).fetchall()
        _bucket([(t, n) for t, n, _ in masse], idx, "envoyes", jours, amount_idx=1)

        # Le nom et le canal de chaque campagne : `campaigns_unified` fait foi. Deviner le
        # canal d'après la table d'origine marcherait aujourd'hui et se tromperait au
        # premier canal ajouté.
        campagnes = {r[0]: {"nom": r[1], "canal": r[2]} for r in c.execute(
            "SELECT id, name, channel FROM campaigns_unified WHERE site_code = ?",
            [site]).fetchall()}

        # Échecs : on ne retient que les rebonds d'adresses RÉELLEMENT prospectées. Sans ce
        # filtre, les boîtes de test et de warmup gonflent la colonne.
        rebonds = c.execute(
            "SELECT received_at, lower(email) FROM sweego_events "
            "WHERE site_code = ? AND event_type IN ('hard_bounce', 'complaint') "
            "AND received_at >= ?", [site, depuis]).fetchall()
    finally:
        c.close()

    # ── Répartition par canal et par campagne ─────────────────────────────────
    # Une entrée par jour : {canal: volume} et le détail campagne par campagne. Les deux
    # sources sont des JOURNAUX (une ligne écrite une fois), pas des états courants : le
    # pool, lui, écrase `email_sent_at` à chaque nouvel envoi et perdrait l'historique.
    canaux = {k: {c: 0 for c in CANAUX} for k in idx}
    detail: dict[str, dict[str, dict]] = {k: {} for k in idx}

    def _porter(jour_cle: str, cid: str | None, canal: str, volume: int):
        if jour_cle not in canaux:
            return
        canaux[jour_cle][canal] = canaux[jour_cle].get(canal, 0) + volume
        cle = cid or "(hors campagne)"
        e = detail[jour_cle].setdefault(cle, {
            "id": cid, "nom": campagnes.get(cle, {}).get("nom") or "Envoi hors campagne",
            "canal": canal, "volume": 0})
        e["volume"] += volume

    for t, _em, disp in envois:
        pj = _to_paris(t)
        if pj is None or pj < jours[-1]:
            continue
        k = _midnight(pj).date().isoformat()
        cid = _campagne_du_dispatch(disp)
        _porter(k, cid, campagnes.get(cid or "", {}).get("canal") or "maildoso", 1)

    for t, n, disp in masse:
        pj = _to_paris(t)
        if pj is None or pj < jours[-1]:
            continue
        k = _midnight(pj).date().isoformat()
        cid = _campagne_du_dispatch(disp)
        _porter(k, cid, campagnes.get(cid or "", {}).get("canal") or "sweego", int(n or 0))

    ouvreurs, cliqueurs, prospects = [], [], set()
    emelia_rows: list = []
    try:
        pool = _connect(POOL_DB)
        try:
            ouvreurs = pool.execute(
                "SELECT last_opened_at FROM contact_site_history "
                "WHERE site_code = ? AND last_opened_at >= ?", [site, depuis]).fetchall()
            cliqueurs = pool.execute(
                "SELECT last_clicked_at FROM contact_site_history "
                "WHERE site_code = ? AND last_clicked_at >= ?", [site, depuis]).fetchall()
            prospects = {r[0] for r in pool.execute(
                "SELECT lower(c.email) FROM contacts c "
                "JOIN contact_site_history h ON h.contact_id = c.id "
                "WHERE h.site_code = ? AND c.email IS NOT NULL", [site]).fetchall()}
            # Emelia n'a pas de journal d'envoi local : c'est lui qui étale les envois de
            # son côté, on ne connaît que le moment où on lui a remis les contacts. Le pool
            # ne garde que le DERNIER envoi par contact : un contact recontacté plus tard
            # disparaît du jour d'origine. Chiffre minorant, donc, et jamais majorant —
            # signalé comme tel dans la note.
            emelia_rows = pool.execute(
                "SELECT email_sent_at, emelia_campaign_id FROM contact_site_history "
                "WHERE site_code = ? AND email_sent_at >= ?", [site, depuis]).fetchall()
        finally:
            pool.close()
    except Exception:
        pass  # pool verrouillé : on rend les envois plutôt qu'une erreur

    for t, disp in emelia_rows:
        cid = _campagne_du_dispatch(disp)
        if not cid or campagnes.get(cid, {}).get("canal") != "emelia":
            continue          # maildoso et sweego ont déjà été comptés sur leur journal
        pj = _to_paris(t)
        if pj is None or pj < jours[-1]:
            continue
        k = _midnight(pj).date().isoformat()
        _porter(k, cid, "emelia", 1)
        idx[k]["envoyes"] = idx[k].get("envoyes", 0) + 1

    _bucket(ouvreurs, idx, "ouvreurs", jours)
    _bucket(cliqueurs, idx, "cliqueurs", jours)
    _bucket([(t,) for t, em in rebonds if em in prospects], idx, "echecs", jours)

    lignes = []
    for j in jours:
        k = j.date().isoformat()
        d = idx[k]
        envoyes = d.get("envoyes", 0)
        destinataires = len(vus.get(k, ()))
        ouv = d.get("ouvreurs", 0)
        lignes.append({
            "jour": k,
            "libelle": _day_label(j),
            "envoyes": envoyes,
            "destinataires": destinataires,
            "redites": max(0, envoyes - destinataires) if destinataires else 0,
            "ouvreurs": ouv,
            "cliqueurs": d.get("cliqueurs", 0),
            "echecs": d.get("echecs", 0),
            # Par où c'est parti, et pour quelle campagne. Sans ça, « 100 envoyés » ne dit
            # ni sur quel routeur ni pour quelle cible.
            "canaux": canaux.get(k, {c: 0 for c in CANAUX}),
            "campagnes": sorted(detail.get(k, {}).values(),
                                key=lambda e: -e["volume"]),
            # Rapporté aux destinataires uniques et non aux envois : deux comptages de
            # personnes, donc comparables. Rapporté aux envois, un renvoi ferait
            # mécaniquement chuter le taux sans que personne n'ait moins ouvert.
            "taux_ouverture": round(100 * ouv / destinataires, 1) if destinataires else 0.0,
            # Fenêtre d'envoi lundi→samedi : un dimanche à zéro n'est pas une anomalie.
            "statut": _statut(j, envoyes > 0, ferme_le_dimanche=True),
        })
    return {
        "site": site,
        "jours": lignes,
        "note": ("« Ouvreurs » compte des personnes, pas des ouvertures : le pool ne garde "
                 "que la dernière ouverture par contact. « Redites » = emails envoyés à "
                 "quelqu'un qui en avait déjà reçu un le même jour — doit rester à 0. "
                 "Le volume Emelia est un minorant : Emelia n'expose pas de journal d'envoi "
                 "par jour, il est reconstitué depuis le dernier envoi connu de chaque contact."),
    }


# ── Tableau 2 : ce qui entre ──────────────────────────────────────────────────

def daily_scraping_stats(site: str, days: int = 7) -> dict:
    """Contacts scrapés par JOUR, et ce qu'il en reste après validation Mailnjoy.

    Le scraping tourne la nuit (22 h → 8 h heure de Paris) : la récolte d'une nuit est
    donc horodatée en grande partie sur la SOIRÉE, c'est-à-dire la veille au sens calendaire.
    Un zéro sur la journée en cours avant 22 h est normal — d'où le statut `en_cours`.
    """
    jours, idx = _day_skeleton(days)
    depuis = jours[-1].astimezone(timezone.utc).replace(tzinfo=None)

    c = _god()
    try:
        _bucket(c.execute(
            "SELECT created_at FROM scrappe WHERE site_code = ? AND created_at >= ?",
            [site, depuis]).fetchall(), idx, "valides", jours)
        _bucket(c.execute(
            "SELECT last_seen FROM scrappe_rejected WHERE site_code = ? AND last_seen >= ?",
            [site, depuis]).fetchall(), idx, "rejetes", jours)
        _bucket(c.execute(
            "SELECT created_at FROM scrappe_pending WHERE site_code = ? AND created_at >= ?",
            [site, depuis]).fetchall(), idx, "en_attente", jours)
    finally:
        c.close()

    # Entrées réelles dans le pool : c'est le seul chiffre qui compte vraiment, car un email
    # déjà connu est validé sans rien ajouter. L'écart avec `valides` est le taux de doublon.
    try:
        pool = _connect(POOL_DB)
        try:
            _bucket(pool.execute(
                "SELECT added_to_site_at FROM contact_site_history "
                "WHERE site_code = ? AND added_to_site_at >= ?",
                [site, depuis]).fetchall(), idx, "nouveaux_pool", jours)
        finally:
            pool.close()
    except Exception:
        pass  # pool verrouillé par un scrape : on rend le reste plutôt qu'une erreur

    lignes = []
    for j in jours:
        d = idx[j.date().isoformat()]
        valides = d.get("valides", 0)
        rejetes = d.get("rejetes", 0)
        traites = valides + rejetes
        lignes.append({
            "jour": j.date().isoformat(),
            "libelle": _day_label(j),
            "traites": traites,
            "valides": valides,
            "rejetes": rejetes,
            "en_attente": d.get("en_attente", 0),
            "nouveaux_pool": d.get("nouveaux_pool", 0),
            "taux_validation": round(100 * valides / traites, 1) if traites else 0.0,
            # Le scraping tourne toutes les nuits, dimanche compris : pas d'exception.
            "statut": _statut(j, traites > 0, ferme_le_dimanche=False),
        })
    return {
        "site": site,
        "jours": lignes,
        "note": ("« Traités » = validés + rejetés. « Nouveaux au pool » exclut les emails "
                 "déjà connus : l'écart avec « validés » est le taux de doublon du scraping."),
    }


# ── Inventaire des bases ──────────────────────────────────────────────────────

_BASES = [
    ("god_mode.duckdb",      "data/god_mode.duckdb",      "duckdb",
     "Scraping, campagnes, envois, journaux"),
    ("contacts.duckdb",      "data/contacts.duckdb",      "duckdb",
     "Pool de contacts mutualisé"),
    ("auth.duckdb",          "data/auth.duckdb",          "duckdb",
     "Utilisateurs, sessions, connexions"),
    ("crm/lcr.duckdb",       "data/crm/lcr.duckdb",       "duckdb",
     "CRM legacy LCR (en cours de migration vers le pool)"),
    ("crm/mkd.duckdb",       "data/crm/mkd.duckdb",       "duckdb",
     "CRM legacy MKD (en cours de migration vers le pool)"),
    ("datagouv_cache.sqlite", "data/datagouv_cache.sqlite", "sqlite",
     "Cache des appels data.gouv (enrichissement)"),
]

# PostgreSQL n'est pas un fichier : il est inventorié à part, via le catalogue.
PG_ROLE = "Référentiel Cheffer — cible de la migration (contacts, campagnes, événements)"


def _inventaire_postgres() -> dict | None:
    """Tables, lignes et champs de la base PostgreSQL, plus la santé de la double écriture.

    Les comptages viennent d'un `count(*)` réel et non des statistiques du planificateur :
    `reltuples` est une estimation, et sur une migration on veut le chiffre exact.
    """
    dsn = ""
    try:
        for ligne in (BASE_DIR / ".env").read_text().splitlines():
            if ligne.startswith("PG_DSN="):
                dsn = ligne.split("=", 1)[1].strip()
    except Exception:
        return None
    if not dsn:
        return None

    entree = {"nom": "postgresql://cheffer", "moteur": "postgres", "role": PG_ROLE,
              "octets": 0, "tables": [], "erreur": None}
    try:
        import psycopg2
        c = psycopg2.connect(dsn)
        try:
            with c.cursor() as cur:
                cur.execute("SELECT pg_database_size(current_database())")
                entree["octets"] = int(cur.fetchone()[0] or 0)
                cur.execute("""SELECT c.relname,
                                      (SELECT count(*) FROM information_schema.columns col
                                       WHERE col.table_name = c.relname
                                         AND col.table_schema = 'public')
                               FROM pg_class c
                               JOIN pg_namespace n ON n.oid = c.relnamespace
                               WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v')
                               ORDER BY c.relname""")
                for nom, champs in cur.fetchall():
                    cur2 = c.cursor()
                    try:
                        cur2.execute(f'SELECT count(*) FROM "{nom}"')
                        n = int(cur2.fetchone()[0] or 0)
                    finally:
                        cur2.close()
                    entree["tables"].append({"nom": nom, "lignes": n, "champs": int(champs)})
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        entree["erreur"] = str(e)[:200]

    try:
        import pg_sync
        entree["sync"] = {k: v for k, v in pg_sync.sync_health().items()
                          if k != "derniers_echecs"}
    except Exception:
        pass

    entree["tables"].sort(key=lambda x: -x["lignes"])
    entree["nb_tables"] = len(entree["tables"])
    entree["nb_champs"] = sum(t["champs"] for t in entree["tables"])
    entree["nb_lignes"] = sum(t["lignes"] for t in entree["tables"])
    return entree


def database_inventory() -> dict:
    """Toutes les bases, leurs tables, le nombre de lignes et de champs.

    Une base verrouillée par un écrivain est rendue avec son erreur plutôt que de faire
    échouer l'inventaire entier : sur DuckDB, c'est une situation normale pendant un scrape,
    et l'écran doit rester lisible.
    """
    bases, t_tables, t_champs, t_lignes, t_octets = [], 0, 0, 0, 0

    for nom, rel, moteur, role in _BASES:
        chemin = BASE_DIR / rel
        entree = {"nom": nom, "moteur": moteur, "role": role,
                  "octets": 0, "tables": [], "erreur": None}
        if not chemin.exists():
            entree["erreur"] = "fichier absent"
            bases.append(entree)
            continue
        entree["octets"] = os.path.getsize(chemin)
        t_octets += entree["octets"]

        try:
            if moteur == "duckdb":
                c = _connect(chemin, attempts=3)
                try:
                    champs = dict(c.execute(
                        "SELECT table_name, count(*) FROM information_schema.columns "
                        "GROUP BY 1").fetchall())
                    noms = sorted(c.execute(
                        "SELECT table_name FROM information_schema.tables").fetchall())
                    for (t,) in noms:
                        n = c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                        entree["tables"].append(
                            {"nom": t, "lignes": int(n), "champs": int(champs.get(t, 0))})
                finally:
                    c.close()
            else:
                con = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
                try:
                    noms = [r[0] for r in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%' ORDER BY 1")]
                    for t in noms:
                        n = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                        ch = len(con.execute(f'PRAGMA table_info("{t}")').fetchall())
                        entree["tables"].append(
                            {"nom": t, "lignes": int(n), "champs": ch})
                finally:
                    con.close()
        except Exception as e:  # noqa: BLE001
            entree["erreur"] = str(e)[:200]

        entree["tables"].sort(key=lambda x: -x["lignes"])
        entree["nb_tables"] = len(entree["tables"])
        entree["nb_champs"] = sum(t["champs"] for t in entree["tables"])
        entree["nb_lignes"] = sum(t["lignes"] for t in entree["tables"])
        t_tables += entree["nb_tables"]
        t_champs += entree["nb_champs"]
        t_lignes += entree["nb_lignes"]
        bases.append(entree)

    # PostgreSQL : même page, même lecture. Pendant la double écriture, voir les deux
    # bases côte à côte est le seul moyen simple de repérer une divergence.
    pg = _inventaire_postgres()
    if pg:
        bases.append(pg)
        if not pg.get("erreur"):
            t_tables += pg["nb_tables"]
            t_champs += pg["nb_champs"]
            t_lignes += pg["nb_lignes"]
            t_octets += pg["octets"]

    return {"bases": bases,
            "total": {"bases": len(bases), "tables": t_tables,
                      "champs": t_champs, "lignes": t_lignes, "octets": t_octets},
            "genere_le": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    import json
    import sys
    quoi = sys.argv[1] if len(sys.argv) > 1 else "inventaire"
    site = sys.argv[2] if len(sys.argv) > 2 else "lcr"
    if quoi == "emails":
        print(json.dumps(daily_email_stats(site, int(sys.argv[3]) if len(sys.argv) > 3 else 7), indent=2, ensure_ascii=False))
    elif quoi == "scraping":
        print(json.dumps(daily_scraping_stats(site, int(sys.argv[3]) if len(sys.argv) > 3 else 7), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(database_inventory(), indent=2, ensure_ascii=False))
