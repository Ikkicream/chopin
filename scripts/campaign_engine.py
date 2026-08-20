"""
campaign_engine.py — Modèle de campagne unifié multi-canal + scheduler.

Une "campagne unifiée" = un message envoyé sur UN canal (sweego|emelia|maildoso) à une cible
(secteurs, filtrée Mailnjoy valid < 6 mois), étalée dans le temps selon un planning calculé par
`deliverability_agent` (cap dur par canal). Un cron quotidien (`dispatch_due`) exécute le lot du jour.

Table : `campaigns` (PostgreSQL) depuis le 2026-08-19 — voir la note sur le stockage
plus bas. Les journaux d'envoi restent dans data/god_mode.duckdb pour l'instant.
CLI : `python3 scripts/campaign_engine.py dispatch` (appelé par cron).
"""
from __future__ import annotations

import json
import sys
import threading
import uuid as _uuid
from datetime import date as _date, datetime, timezone
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"

VALID_CHANNELS = ("sweego", "emelia", "maildoso")
ACTIVE_STATUSES = ("scheduled", "running")

# FRÉQUENCE MAXIMALE (décision user 2026-08-19) : dès qu'une personne a reçu un email elle
# est inscrite en base repoussoir et ne reçoit PLUS RIEN pendant 120 jours. Doit rester
# aligné sur contacts_pool_backend.SUPPRESSION_DAYS — qui est la source de vérité : on la
# lit plutôt que de la recopier, pour qu'un changement de règle ne laisse pas deux durées
# divergentes entre le moteur de campagne et le pool.
# L'import est gardé : campaign_engine est chargé par l'API au démarrage, et une erreur
# d'import ici la rendrait inaccessible. Le repli conserve la règle (120 jours), il ne
# l'assouplit pas.
try:
    from contacts_pool_backend import SUPPRESSION_DAYS as MIN_DAYS_BETWEEN_EMAILS
except Exception:  # noqa: BLE001
    MIN_DAYS_BETWEEN_EMAILS = 120


# ── Stockage ──────────────────────────────────────────────────────────────────
# Les CAMPAGNES vivent dans PostgreSQL depuis le 2026-08-19. Motif : `god_mode.duckdb`
# n'admet qu'un seul écrivain, et cette table est lue à chaque ouverture du tableau de bord
# comme de la page Campagnes. Tant qu'elle vivait dans ce fichier, un scrape ou un
# nettoyage rendait ces écrans indisponibles — « liste des campagnes indisponible ».
#
# La double écriture existait déjà (`_miroir_campagne` recopiait vers PostgreSQL) : la
# migration a donc consisté à INVERSER le sens, pas à copier des données. La table DuckDB
# reste en place, intacte, comme filet de retour arrière.
#
# Les JOURNAUX d'envoi (`maildoso_sent`, `mass_campaigns`) restent pour l'instant dans
# DuckDB : ils sont écrits par le chemin d'envoi, qui migrera dans un second temps.
#
# L'identifiant public reste l'id court historique (« fd0dc221-b44 »), porté par
# `legacy_id` : il est inscrit dans les identifiants de dispatch (`lcr-fd0dc221-b44-date`),
# dans les URL de l'interface et dans `params.segment_id`. Le changer casserait tout.

def _dsn() -> str:
    for ligne in (BASE_DIR / ".env").read_text().splitlines():
        if ligne.startswith("PG_DSN="):
            return ligne.split("=", 1)[1].strip()
    raise RuntimeError("PG_DSN absent de .env")


_POOL_PG = None


def _conn():
    """Connexion PostgreSQL (campagnes)."""
    global _POOL_PG
    import psycopg2.pool
    if _POOL_PG is None:
        _POOL_PG = psycopg2.pool.ThreadedConnectionPool(1, 6, _dsn())
    return _POOL_PG.getconn()


def _rendre(c):
    if _POOL_PG is not None:
        _POOL_PG.putconn(c)


def _duck():
    """Connexion DuckDB — uniquement pour les journaux d'envoi encore stockés là."""
    import sys as _sys
    _sys.path.insert(0, str(BASE_DIR / "scripts"))
    from duck_ouverture import ouvrir
    return ouvrir(GOD_DB)


def _ecrire(sql: str, params: list) -> None:
    c = _conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(sql, params)
    finally:
        _rendre(c)


def _lire(sql: str, params: list) -> list:
    c = _conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        c.rollback()
        _rendre(c)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_table():
    """Ne crée plus rien : le schéma PostgreSQL est appliqué une fois par `pg_schema.sql`.
    Conservée pour ne pas casser ses nombreux appelants."""
    return None


# ── CRUD ─────────────────────────────────────────────────────────────────────
def create_campaign(site: str, name: str, channel: str, message_id: str, subject: str,
                    sectors: list[str], target_size: int, schedule_start: str,
                    by: str = "ui", regions: list[str] | None = None,
                    depts: list[str] | None = None,
                    engagement: str | None = None,
                    segment_id: str | None = None) -> dict:
    """Crée + planifie une campagne. Valide la faisabilité via deliverability_agent.
    Refuse si le canal est invalide, la cible vide, ou la cadence infaisable."""
    channel = (channel or "").lower()
    if channel not in VALID_CHANNELS:
        return {"ok": False, "error": f"canal invalide: {channel}"}

    # Ciblage par SEGMENT enregistré : ses règles remplacent secteurs/zones/engagement.
    # Résolu AVANT la validation, car une campagne par segment n'a pas de secteurs saisis.
    segment_rules = None
    if segment_id:
        import segments_backend as _sb
        seg = _sb.get_segment(segment_id)
        if not seg or seg.get("site_code") != site:
            return {"ok": False, "error": f"segment introuvable : {segment_id}"}
        segment_rules = seg["rules"]
        # `sectors` reste une colonne du modèle de campagne : on y note l'origine du ciblage.
        sectors = sectors or [f"segment:{seg['name']}"]

    if not name or not message_id or not subject or not sectors or target_size < 1:
        return {"ok": False, "error": "name, message_id, subject, sectors, target_size requis"}

    # Le message doit être résoluble MAINTENANT (évite une campagne qui échouera au dispatch).
    import html_templates_backend as _htb
    if not (_htb.resolve_campaign_message(site, message_id) or {}).get("html"):
        return {"ok": False, "error": f"message introuvable: {message_id}"}

    engagement = (engagement or "").strip() or None
    import contacts_pool_backend as _pool
    if engagement and engagement not in _pool.ENGAGEMENT_FILTERS:
        return {"ok": False, "error": f"filtre engagement invalide: {engagement}"}

    # La cible doit exister : refuse un volume supérieur aux contacts éligibles
    # (sinon la campagne resterait "running" sans jamais atteindre son target).
    if segment_rules is not None:
        available = _pool.count_for_segment(site, segment_rules)
    else:
        available = sum(
            _pool.count_available_for_sector(site, sec, regions=regions or [], depts=depts or [],
                                             engagement=engagement)
            for sec in sectors
        )
    if target_size > available:
        return {"ok": False,
                "error": f"volume trop grand : {target_size} demandés, "
                         f"{available} contacts éligibles",
                "available": available}

    try:
        start = _date.fromisoformat(schedule_start)
    except Exception:
        return {"ok": False, "error": "schedule_start invalide (YYYY-MM-DD)"}

    # Planning + faisabilité (agent délivrabilité)
    import deliverability_agent as da
    plan = da.plan_cadence(site, channel, target_size, start)
    if not plan.get("feasible"):
        return {"ok": False, "error": "cadence infaisable",
                "plan": plan, "explanation": da.explain(plan, channel, target_size)}

    cid = str(_uuid.uuid4())[:12]
    # utm_campaign UNIQUE et STABLE par campagne (attribution GA4 : "quelle campagne a cliqué ?").
    # Format : <slug-du-nom>-<6 hex> — lisible + garanti unique.
    try:
        from utm_tagging import slug_campaign
        utm_campaign = f"{slug_campaign(name)}-{cid[:6]}"
    except Exception:
        utm_campaign = cid
    params = {"utm_campaign": utm_campaign}
    # Ciblage géographique optionnel (codes région / département INSEE)
    if regions:
        params["regions"] = [str(r) for r in regions if r]
    if depts:
        params["depts"] = [str(d) for d in depts if d]
    if engagement:
        params["engagement"] = engagement
    if segment_id:
        # On mémorise l'UUID du segment, pas une copie de ses règles : si le segment est
        # mis à jour (et non verrouillé), les prochains lots suivent la nouvelle définition.
        params["segment_id"] = segment_id
    _ecrire(
        "INSERT INTO campaigns "
        "(id, legacy_id, site_code, name, channel, message_id, subject, sectors, target_size, "
        " schedule_start, cadence, status, sent_count, created_by, created_at, params) "
        "VALUES (gen_random_uuid(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,now(),%s::jsonb)",
        [cid, site, name, channel, message_id, subject, list(sectors or []), int(target_size),
         start, json.dumps(plan.get("schedule", [])), "scheduled", 0,
         by, json.dumps(params)])
    return {"ok": True, "id": cid, "status": "scheduled", "utm_campaign": utm_campaign, "plan": plan}


def _miroir_campagne(cid: str) -> None:
    """Ne fait plus rien : PostgreSQL est devenu la source de vérité des campagnes, il n'y
    a plus de copie à tenir à jour. Conservée le temps que ses appelants disparaissent."""
    return None


def _row_to_dict(r) -> dict:
    cols = ["id", "site_code", "name", "channel", "message_id", "subject", "sectors",
            "target_size", "schedule_start", "cadence", "status", "sent_count",
            "last_dispatch_at", "last_dispatch_day", "last_error", "created_by",
            "created_at", "params"]
    d = dict(zip(cols, r))
    # PostgreSQL rend `sectors` en liste (text[]) et `cadence`/`params` déjà décodés
    # (jsonb). On accepte encore la forme texte, le temps que d'anciennes lignes
    # disparaissent.
    for k in ("sectors", "cadence", "params"):
        v = d.get(k)
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                v = None
        if v is None:
            v = {} if k == "params" else []
        d[k] = v
    for k in ("schedule_start", "last_dispatch_at", "last_dispatch_day", "created_at"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    d["progress"] = round((d["sent_count"] or 0) / d["target_size"] * 100) if d.get("target_size") else 0
    d["reste"] = max(0, (d.get("target_size") or 0) - (d.get("sent_count") or 0))
    # Prochain lot prévu : la première étape de cadence qui n'est pas encore passée. Sans
    # lui, une liste de campagnes ne répond pas à « qu'est-ce qui part demain ? » — la
    # question qu'on se pose en regardant cette liste.
    d["prochain"] = None
    if d.get("status") in ("scheduled", "running"):
        from zoneinfo import ZoneInfo
        aujourdhui = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
        # Le lot du jour déjà parti ne se présente pas comme « à venir » : sinon la liste
        # annonce 160 emails pour aujourd'hui alors qu'ils sont partis ce matin.
        seuil = aujourdhui
        dernier = str(d.get("last_dispatch_day") or "")[:10]
        for etape in (d.get("cadence") or []):
            jour = str(etape.get("date") or "")[:10]
            if jour > dernier and jour >= seuil:
                d["prochain"] = {"date": jour, "count": etape.get("count") or 0}
                break
    return d


_SELECT = ("SELECT COALESCE(legacy_id, id::text), site_code, name, channel, message_id, "
           "subject, sectors, target_size, schedule_start, cadence, status, sent_count, "
           "last_dispatch_at, last_dispatch_day, last_error, created_by, created_at, params "
           "FROM campaigns")


def list_campaigns(site: str) -> list[dict]:
    return [_row_to_dict(r) for r in
            _lire(_SELECT + " WHERE site_code=%s ORDER BY created_at DESC", [site])]


def journal_envois(site: str, cid: str) -> list[dict]:
    """Ce qui est RÉELLEMENT parti pour cette campagne, jour par jour.

    `sent_count` dit un total ; il ne dit ni quand, ni en combien de fois. Or c'est
    exactement la question qu'on se pose devant une campagne : « elle est partie quand,
    vers combien de personnes ? ». On lit les journaux d'envoi — `maildoso_sent` (une ligne
    par destinataire) et `mass_campaigns` (une ligne par envoi de masse) — et non l'état
    courant du pool, qui écrase la date à chaque nouvel envoi.

    L'identifiant d'un envoi est « {site}-{campagne}-{date} » : un `LIKE` sur le préfixe
    suffit et évite d'avoir à parser la date.
    """
    prefixe = f"{site}-{cid}-%"
    lignes: dict[str, dict] = {}
    c = _duck()          # journaux d'envoi : encore dans DuckDB
    try:
        try:
            for jour, n in c.execute(
                    "SELECT strftime(created_at, '%Y-%m-%d') AS j, count(*) "
                    "FROM maildoso_sent WHERE site_code = ? AND status = 'sent' "
                    "AND campaign_id LIKE ? GROUP BY 1", [site, prefixe]).fetchall():
                lignes.setdefault(jour, {"jour": jour, "volume": 0, "canal": "maildoso"})["volume"] += int(n)
        except Exception:
            pass
        try:
            for jour, n in c.execute(
                    "SELECT strftime(created_at, '%Y-%m-%d') AS j, sum(recipients_count) "
                    "FROM mass_campaigns WHERE site_code = ? AND campaign_id LIKE ? "
                    "GROUP BY 1", [site, prefixe]).fetchall():
                lignes.setdefault(jour, {"jour": jour, "volume": 0, "canal": "sweego"})["volume"] += int(n or 0)
        except Exception:
            pass
    finally:
        c.close()
    return sorted(lignes.values(), key=lambda e: e["jour"], reverse=True)


def get_campaign(cid: str) -> dict | None:
    rows = _lire(_SELECT + " WHERE legacy_id=%s OR id::text=%s", [cid, cid])
    return _row_to_dict(rows[0]) if rows else None


def update_campaign(site: str, cid: str, patch: dict, by: str = "ui") -> dict:
    """Modifie une campagne existante (fiche « Éditer » de l'UI).

    Toujours modifiables : nom, objet, message, ciblage (secteurs / zones / engagement)
    — le dispatch pioche des contacts frais chaque jour, ces changements ne valent donc
    que pour les envois restants.
    Volume et date de lancement : uniquement tant qu'aucun envoi n'a eu lieu, car la
    cadence est recalculée de zéro et les compteurs déjà consommés la rendraient fausse.
    """
    camp = get_campaign(cid)
    if not camp or camp.get("site_code") != site:
        return {"ok": False, "error": "campagne introuvable"}
    if camp.get("status") in ("done", "cancelled"):
        return {"ok": False, "error": f"campagne {camp['status']} — non modifiable"}

    import contacts_pool_backend as _pool
    import html_templates_backend as _htb

    sent = int(camp.get("sent_count") or 0)
    params = dict(camp.get("params") or {})
    sets: list[str] = []
    vals: list = []

    if "name" in patch:
        name = (patch.get("name") or "").strip()
        if not name:
            return {"ok": False, "error": "nom requis"}
        sets.append("name=?"); vals.append(name)
    if "subject" in patch:
        subject = (patch.get("subject") or "").strip()
        if not subject:
            return {"ok": False, "error": "objet requis"}
        sets.append("subject=?"); vals.append(subject)
    if "message_id" in patch:
        mid = (patch.get("message_id") or "").strip()
        if not (_htb.resolve_campaign_message(site, mid) or {}).get("html"):
            return {"ok": False, "error": f"message introuvable: {mid}"}
        sets.append("message_id=?"); vals.append(mid)

    # ── Ciblage ──
    sectors = camp.get("sectors") or []
    if "sectors" in patch:
        sectors = [s for s in (patch.get("sectors") or []) if s]
        if not sectors:
            return {"ok": False, "error": "au moins un secteur requis"}
        sets.append("sectors=?"); vals.append(json.dumps(sectors))
    for key in ("regions", "depts"):
        if key in patch:
            vs = [str(v) for v in (patch.get(key) or []) if v]
            if vs:
                params[key] = vs
            else:
                params.pop(key, None)
    if "engagement" in patch:
        eng = (patch.get("engagement") or "").strip()
        if eng and eng not in _pool.ENGAGEMENT_FILTERS:
            return {"ok": False, "error": f"filtre engagement invalide: {eng}"}
        if eng:
            params["engagement"] = eng
        else:
            params.pop("engagement", None)

    # ── Volume / date de lancement : avant le 1er envoi seulement ──
    target = int(camp.get("target_size") or 0)
    start = str(camp.get("schedule_start") or "")[:10]
    replan = ("target_size" in patch and int(patch["target_size"] or 0) != target) or \
             ("schedule_start" in patch and (patch.get("schedule_start") or "").strip()[:10] != start)
    if replan and sent > 0:
        return {"ok": False,
                "error": f"volume et date non modifiables après le 1er envoi ({sent} déjà envoyés) — "
                         "annule la campagne et recrée-la"}
    if "target_size" in patch:
        target = int(patch.get("target_size") or 0)
        if target < 1:
            return {"ok": False, "error": "volume invalide"}
    if "schedule_start" in patch:
        try:
            start = _date.fromisoformat((patch.get("schedule_start") or "").strip()[:10]).isoformat()
        except Exception:
            return {"ok": False, "error": "date de lancement invalide (YYYY-MM-DD)"}

    # La cible doit rester atteignable dès que le ciblage OU le volume bouge.
    if replan or any(k in patch for k in ("sectors", "regions", "depts", "engagement")):
        available = sum(
            _pool.count_available_for_sector(site, sec,
                                             regions=params.get("regions") or [],
                                             depts=params.get("depts") or [],
                                             engagement=params.get("engagement"))
            for sec in sectors
        )
        if target > available:
            return {"ok": False,
                    "error": f"volume trop grand : {target} demandés, {available} contacts éligibles",
                    "available": available}

    if replan:
        import deliverability_agent as da
        plan = da.plan_cadence(site, camp["channel"], target, _date.fromisoformat(start))
        if not plan.get("feasible"):
            return {"ok": False, "error": "cadence infaisable", "plan": plan,
                    "explanation": da.explain(plan, camp["channel"], target)}
        sets.append("target_size=?"); vals.append(int(target))
        sets.append("schedule_start=?"); vals.append(_date.fromisoformat(start))
        sets.append("cadence=?"); vals.append(json.dumps(plan.get("schedule", [])))

    if params != (camp.get("params") or {}):
        sets.append("params=?"); vals.append(json.dumps(params))
    if not sets:
        return {"ok": True, "id": cid, "unchanged": True, "campaign": camp}

    _ecrire(f"UPDATE campaigns SET {', '.join(sets)} WHERE legacy_id=%s", vals + [cid])
    return {"ok": True, "id": cid, "campaign": get_campaign(cid)}

def set_status(cid: str, status: str, error: str | None = None) -> bool:
    _ecrire("UPDATE campaigns SET status=%s, last_error=%s WHERE legacy_id=%s",
            [status, error, cid])
    return True

def _bump_sent(cid: str, n: int = 1) -> None:
    """Incrémente le compteur d'envois immédiatement, sans attendre la fin du lot.

    Un lot maildoso s'étale sur des heures (pacing 15-60 s/email) : tant que le
    compteur n'était écrit qu'à la fin, un arrêt en cours de route laissait la
    campagne à son ancien `sent_count` alors que les emails étaient bel et bien
    partis. L'UPDATE final de `dispatch_campaign` pose une valeur absolue calculée
    depuis le `sent_count` lu avant le lot : il converge donc vers le même total,
    ces incréments ne le faussent pas."""
    _ecrire("UPDATE campaigns SET sent_count = COALESCE(sent_count, 0) + %s, "
            "last_dispatch_at = now() WHERE legacy_id = %s", [n, cid])


# ── Dispatch (scheduler) ───────────────────────────────────────────────────────
def _todays_allowance(camp: dict, today: _date) -> int:
    """Nb d'emails autorisés aujourd'hui : cumul prévu par la cadence jusqu'à
    aujourd'hui inclus, moins le déjà-envoyé — un jour de dispatch manqué est donc
    rattrapé dès le lendemain, pas seulement après la fin de la cadence. Borné au
    plus gros lot quotidien de la cadence pour respecter le cap du canal."""
    cadence = camp.get("cadence") or []
    sent = camp.get("sent_count", 0) or 0
    target = camp.get("target_size", 0) or 0
    if not cadence:
        return max(0, target - sent)
    expected = sum(int(s.get("count", 0)) for s in cadence
                   if str(s.get("date", "")) <= today.isoformat())
    if today.isoformat() > str(cadence[-1].get("date", "")):
        expected = max(expected, target)  # cadence finie : tout le reliquat
    daily_cap = max(int(s.get("count", 0)) for s in cadence)
    return max(0, min(expected - sent, daily_cap))


def _drop_recently_emailed(contacts: list[dict],
                           days: int = MIN_DAYS_BETWEEN_EMAILS) -> tuple[list[dict], int]:
    """Retire du lot tout contact ayant déjà reçu un email dans les `days` derniers jours.

    Dernière barrière avant l'envoi, croisant DEUX sources indépendantes du tri du pool :

    1. la **base repoussoir** (`email_suppression`) — le registre de référence, alimenté à
       chaque envoi réussi, tous canaux ; il survit à la disparition du contact du pool ;
    2. le **journal d'envois** maildoso (`maildoso_sent`) — la preuve matérielle qu'un
       message est bien parti, utile si l'inscription en base repoussoir a échoué.

    Redondant par construction : en août 2026, quatre adresses ont reçu jusqu'à 17 fois le
    même message parce qu'une seule barrière (le cooldown du pool) pouvait échouer en
    silence. Sweego et Emelia ne journalisant pas par destinataire, la base repoussoir est
    leur seule couverture ici — d'où le fait qu'elle soit écrite dans la transaction du
    marquage de contact.
    """
    emails = [ct.get("email") for ct in contacts if ct.get("email")]
    if not emails:
        return contacts, 0
    blocked: set[str] = set()
    try:
        import contacts_pool_backend as _pool
        blocked |= _pool.filter_suppressed(emails)
    except Exception as e:  # noqa: BLE001
        # Une base repoussoir injoignable ne doit pas faire passer l'envoi en force : on
        # le signale bruyamment, le journal maildoso ci-dessous reste en couverture.
        print(f"[campaign_engine] base repoussoir illisible : {e}")
    c = _duck()          # journal maildoso : encore dans DuckDB
    try:
        c.execute("CREATE TEMP TABLE IF NOT EXISTS _batch(email VARCHAR)")
        c.execute("DELETE FROM _batch")
        c.executemany("INSERT INTO _batch VALUES (?)",
                      [(e.lower(),) for e in emails])
        rows = c.execute(
            f"""SELECT DISTINCT b.email FROM _batch b
                JOIN maildoso_sent m ON lower(m.to_email) = b.email
                WHERE m.status = 'sent'
                  AND m.created_at > CURRENT_TIMESTAMP - INTERVAL '{int(days)}' DAY"""
        ).fetchall()
    finally:
        c.close()
    blocked |= {r[0] for r in rows}
    if not blocked:
        return contacts, 0
    kept = [ct for ct in contacts if (ct.get("email") or "").lower() not in blocked]
    return kept, len(contacts) - len(kept)


def dispatch_campaign(cid: str, today: _date | None = None, dry_run: bool = False) -> dict:
    """Exécute le lot du jour pour une campagne. Idempotent par jour."""
    today = today or _date.today()
    camp = get_campaign(cid)
    if not camp:
        return {"ok": False, "error": "introuvable"}
    if camp["status"] not in ACTIVE_STATUSES:
        return {"ok": False, "error": f"statut {camp['status']} (pas dispatchable)"}
    if camp.get("last_dispatch_day") == today.isoformat():
        return {"ok": False, "error": "déjà dispatché aujourd'hui", "skipped": True}
    if str(camp.get("schedule_start", ""))[:10] > today.isoformat():
        return {"ok": False, "error": "pas encore commencé", "skipped": True}

    allowance = _todays_allowance(camp, today)
    remaining = (camp["target_size"] or 0) - (camp["sent_count"] or 0)
    n = min(allowance, remaining)
    if n <= 0:
        if remaining <= 0:
            set_status(cid, "done")
            return {"ok": True, "done": True, "sent": 0}
        return {"ok": True, "sent": 0, "note": "rien prévu aujourd'hui"}

    # Fenêtre d'envoi : rien le dimanche, rien hors 08:01–17:59 (heure de Paris).
    # Placé AVANT la pioche : inutile de solliciter le pool si l'on ne peut pas envoyer.
    # Couvre le cron quotidien ET le bouton « Envoyer le lot du jour » de l'UI. On sort
    # sans toucher au statut ni à `last_dispatch_day` : ce n'est pas une erreur mais un
    # report — le prochain passage reprendra le lot, et l'allocation cumulée de
    # `_todays_allowance` rattrapera le jour sauté.
    if not dry_run:
        import deliverability_agent as _da
        allowed, why = _da.within_send_window()
        if not allowed:
            return {"ok": True, "sent": 0, "skipped": True, "note": f"envoi différé — {why}"}

    # Pioche les contacts éligibles (Mailnjoy valid < 6 mois) sur tous les secteurs,
    # restreinte aux zones géo de la campagne si définies (params.regions / params.depts)
    import contacts_pool_backend as pool
    site = camp["site_code"]
    geo = camp.get("params") or {}
    contacts: list[dict] = []
    seen = set()
    if geo.get("segment_id"):
        # Segment enregistré : ses règles pilotent la pioche (une seule requête, les
        # secteurs y sont déjà exprimés). Un segment supprimé entre-temps arrête la
        # campagne plutôt que de basculer silencieusement sur un autre ciblage.
        import segments_backend as sb
        seg = sb.get_segment(geo["segment_id"])
        if not seg or seg.get("site_code") != site:
            return {"ok": False, "error": f"segment {geo['segment_id']} introuvable — campagne bloquée"}
        contacts = [ct for ct in pool.pick_for_segment(site, seg["rules"], limit=n)
                    if ct.get("email")]
    else:
        for sec in camp.get("sectors", []):
            for ct in pool.pick_for_campaign(site, sec, limit=n - len(contacts),
                                             regions=geo.get("regions"), depts=geo.get("depts"),
                                             engagement=geo.get("engagement")):
                if ct.get("email") and ct["email"] not in seen:
                    seen.add(ct["email"]); contacts.append(ct)
            if len(contacts) >= n:
                break
    # Garde-fou dur : on écarte les contacts déjà servis dans le mois. Le lot du jour peut
    # en sortir plus petit que prévu — c'est voulu : mieux vaut envoyer moins que renvoyer.
    # En régime normal la pioche les a déjà exclus, donc `dropped` doit rester à 0 ; toute
    # valeur non nulle signale que le cooldown du pool a laissé passer quelque chose.
    contacts, dropped = _drop_recently_emailed(contacts)
    if dropped:
        print(f"[campaign_engine] {cid} : {dropped} contact(s) écarté(s) — déjà "
              f"contactés il y a moins de {MIN_DAYS_BETWEEN_EMAILS} jours")
    contacts = contacts[:n]
    emails = [ct["email"] for ct in contacts if ct.get("email")]
    if not emails:
        return {"ok": True, "sent": 0, "note": "aucun contact éligible aujourd'hui"}

    if dry_run:
        return {"ok": True, "dry_run": True, "would_send": len(emails)}

    # Marqueur du jour posé AVANT l'envoi, et non à la fin : un lot dure des heures, et
    # tant que le marqueur manquait, le cron de 8h30 pouvait démarrer un second dispatch
    # de la même campagne pendant que celui-ci tournait — deux process piochant chacun
    # leurs contacts, donc des doublons. Le verrou `_RUNNING` ne protège pas de ça : il
    # est propre au process. C'est ce marqueur qui rend le dispatch idempotent par jour.
    # Pour reprendre volontairement un lot interrompu le jour même : `reconcile` puis
    # remise à NULL de last_dispatch_day.
    _ecrire("UPDATE campaigns SET last_dispatch_day=%s, last_dispatch_at=now(), "
            "status='running' WHERE legacy_id=%s", [today, cid])

    sent = _send_batch(camp, contacts, emails, today)
    if not sent.get("ok"):
        set_status(cid, "running", error=sent.get("error"))
        if not sent.get("sent"):
            # Rien n'est parti (typiquement : cap journalier des boîtes atteint). On
            # retire le marqueur posé plus haut, sinon la campagne passerait pour
            # dispatchée alors qu'elle n'a rien envoyé — et resterait bloquée jusqu'au
            # lendemain, y compris pour un envoi manuel.
            _ecrire("UPDATE campaigns SET last_dispatch_day=%s WHERE legacy_id=%s",
                    [camp.get("last_dispatch_day"), cid])
        return sent

    # MAJ compteurs + statut
    new_sent = (camp["sent_count"] or 0) + sent.get("sent", 0)
    done = new_sent >= camp["target_size"]
    _ecrire("UPDATE campaigns SET sent_count=%s, status=%s, last_dispatch_at=now(), "
            "last_dispatch_day=%s, last_error=NULL WHERE legacy_id=%s",
            [new_sent, "done" if done else "running", today, cid])
    return {"ok": True, "sent": sent.get("sent", 0), "total_sent": new_sent, "done": done}


# ── Dispatch en tâche de fond ──────────────────────────────────────────────────
# `dispatch_campaign` est bloquant de bout en bout : sur le canal maildoso il tient
# une pause de 15-60 s entre chaque email, soit des heures pour un gros lot. Appelé
# directement depuis un endpoint `async def`, il gelait l'event loop de l'API — plus
# aucune requête n'était servie tant que la campagne n'était pas finie. On l'exécute
# donc dans un thread dédié (et non via le threadpool anyio, qui est partagé avec
# tous les endpoints synchrones et serait monopolisé des heures durant).
_RUNNING: dict[str, dict] = {}
_RUNNING_LOCK = threading.Lock()


def is_dispatching(cid: str) -> dict | None:
    """Infos sur l'envoi en cours pour cette campagne, None si aucun (ce process)."""
    with _RUNNING_LOCK:
        return dict(_RUNNING[cid]) if cid in _RUNNING else None


def dispatch_in_background(cid: str, today: _date | None = None) -> dict:
    """Démarre le lot du jour dans un thread et rend la main immédiatement.

    Le suivi se fait sur `sent_count`, désormais persisté email par email. Le verrou
    est propre au process : il empêche deux clics sur « Envoyer » de lancer deux lots
    concurrents. Après un redémarrage il est vide, mais la garde de reprise de
    `maildoso_backend.send_batch` empêche alors le renvoi aux contacts déjà servis."""
    today = today or _date.today()
    camp = get_campaign(cid)
    if not camp:
        return {"ok": False, "error": "introuvable"}
    with _RUNNING_LOCK:
        if cid in _RUNNING:
            return {"ok": False, "running": True,
                    "error": "un envoi est déjà en cours pour cette campagne",
                    "started_at": _RUNNING[cid]["started_at"].isoformat()}
        _RUNNING[cid] = {"started_at": _now(), "day": today.isoformat()}

    def _run() -> None:
        try:
            # Alerte crédits : réseau, donc à l'intérieur du thread et non dans la requête.
            try:
                import credit_alerts
                credit_alerts.check_and_alert()
            except Exception:
                pass
            res = dispatch_campaign(cid, today)
            print(f"[campaign_engine] dispatch {cid} terminé : {res}")
        except Exception as e:  # noqa: BLE001
            print(f"[campaign_engine] dispatch {cid} a échoué : {e}")
            try:
                set_status(cid, camp["status"], error=str(e))
            except Exception:
                pass
        finally:
            with _RUNNING_LOCK:
                _RUNNING.pop(cid, None)

    threading.Thread(target=_run, name=f"dispatch-{cid}", daemon=True).start()
    return {"ok": True, "started": True, "background": True,
            "note": "envoi lancé en tâche de fond — suivre l'avancement sur sent_count"}


def _send_batch(camp: dict, contacts: list[dict], emails: list[str], today: _date) -> dict:
    """Envoi d'un lot via le canal de la campagne."""
    channel = camp["channel"]
    site = camp["site_code"]
    import html_templates_backend as htb
    msg = htb.resolve_campaign_message(site, camp["message_id"])
    if not msg or not msg.get("html"):
        return {"ok": False, "error": "message introuvable"}
    # utm_campaign unique de la campagne (attribution GA4)
    utm_campaign = (camp.get("params") or {}).get("utm_campaign") or camp["id"]

    if channel == "sweego":
        import sweego_backend as sw
        from contacts_pool_backend import mark_pushed_to_emelia
        campaign_id = f"{site}-{camp['id']}-{today.isoformat()}"
        res = sw.send_campaign(campaign_id, camp["subject"], msg["html"], emails, dry_run=False,
                               utm_campaign=utm_campaign, utm_source="sweego")
        if not res.get("ok"):
            return res
        for ct in contacts:
            try:
                mark_pushed_to_emelia(ct["id"], site, campaign_id, "")
            except Exception:
                pass
        try:
            sw.record_campaign(site, camp["name"], campaign_id, camp["subject"],
                               ",".join(camp.get("sectors", [])), camp["message_id"],
                               len(emails), res.get("transaction_id"), by="scheduler")
        except Exception:
            pass
        return {"ok": True, "sent": res.get("sent", len(emails))}

    if channel == "emelia":
        import emelia_campaign_manager as ecm
        from contacts_pool_backend import mark_pushed_to_emelia
        # Crée la campagne Emelia au 1er dispatch (1 step = le message), réutilise ensuite.
        params = camp.get("params") or {}
        emelia_cid = params.get("emelia_campaign_id")
        if not emelia_cid:
            try:
                created = ecm.create_emelia_campaign(f"{site.upper()}-{camp['name']}"[:60])
                emelia_cid = (created.get("campaign") or {}).get("_id") or created.get("_id")
                if not emelia_cid:
                    return {"ok": False, "error": "création campagne Emelia échouée"}
                # Tag le HTML avec le bon plan (cold email) + utm unique de la campagne
                tagged_html = msg["html"]
                try:
                    from utm_tagging import tag_links
                    tagged_html = tag_links(msg["html"], "coldemail", "email", utm_campaign)
                except Exception:
                    pass
                ecm.configure_steps(emelia_cid, ecm.build_newsletter_steps(tagged_html, camp["subject"]))
                # Fenêtre d'envoi lundi→samedi 08:01–17:59 : indispensable côté Emelia,
                # qui étale les envois lui-même sur les jours suivants — notre garde-fou
                # de dispatch ne contrôle que le moment où on lui remet les contacts.
                # L'échec n'est plus muet : il part dans last_error et remonte dans l'UI.
                _sched = ecm.configure_schedule(emelia_cid)
                if not _sched.get("ok"):
                    params["emelia_schedule_error"] = _sched.get("error")
                    print(f"[campaign_engine] planning Emelia non appliqué : {_sched.get('error')}")
                params["emelia_campaign_id"] = emelia_cid
                _save_params(camp["id"], params)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"setup Emelia: {e}"}

        # 1) Les contacts d'abord : Emelia refuse de démarrer une campagne sans
        #    destinataire (« You must have at least one recipient to start campaign »).
        added = 0
        for ct in contacts:
            contact = {"email": ct["email"], "firstName": ct.get("prenom", ""),
                       "lastName": ct.get("nom", ""), "field1": ct.get("societe", "")}
            try:
                if ecm.add_contact(emelia_cid, contact):
                    added += 1
                    mark_pushed_to_emelia(ct["id"], site, emelia_cid, "")
            except Exception:
                pass

        # 2) Démarrage, une seule fois par campagne. La réponse DOIT être vérifiée :
        #    sur refus Emelia laisse la campagne en DRAFT tout en ayant accepté les
        #    contacts — sans ce contrôle le dispatch comptait des envois fantômes et
        #    posait le cooldown sur des contacts qui n'ont jamais rien reçu.
        if added and not params.get("emelia_started"):
            import requests as _rq
            _st = _rq.post(f"{ecm.EMELIA_URL}/emails/campaigns/{emelia_cid}/start",
                           headers=ecm.HEADERS, timeout=15)
            if _st.status_code >= 400:
                try:
                    _detail = _st.json().get("error") or _st.text[:200]
                except Exception:
                    _detail = _st.text[:200]
                # On NE supprime pas la campagne : son id est déjà enregistré dans les
                # params et les contacts y sont poussés — le prochain dispatch la
                # réutilisera et retentera le démarrage.
                return {"ok": False,
                        "error": f"Emelia refuse de démarrer la campagne "
                                 f"({_st.status_code}) : {_detail}"}
            params["emelia_started"] = True
            _save_params(camp["id"], params)
        return {"ok": True, "sent": added}

    if channel == "maildoso":
        import maildoso_backend as md
        from contacts_pool_backend import mark_pushed_to_emelia
        campaign_id = f"{site}-{camp['id']}-{today.isoformat()}"

        # Progression persistée email par email : le lot dure des heures et doit
        # survivre à un redémarrage. Le marquage du contact pose son cooldown, ce qui
        # l'exclut de la prochaine pioche — c'est ce qui empêche le renvoi.
        def _on_sent(ct: dict) -> None:
            try:
                mark_pushed_to_emelia(ct["id"], site, campaign_id, "")
            except Exception as e:  # noqa: BLE001
                print(f"[campaign_engine] marquage contact {ct.get('email')} échoué : {e}")
            _bump_sent(camp["id"], 1)

        res = md.send_batch(campaign_id, camp["subject"], msg["html"], contacts,
                            site=site, utm_campaign=utm_campaign, on_sent=_on_sent)
        if not res.get("ok"):
            return res
        # Filet : un contact dont le marquage a échoué dans le callback est repris ici.
        ok_emails = set(res.get("sent_emails", []))
        for ct in contacts:
            if ct.get("email") in ok_emails:
                try:
                    mark_pushed_to_emelia(ct["id"], site, campaign_id, "")
                except Exception:
                    pass
        # Ramp-up : ajuste les caps/jour des boîtes après chaque campagne (idempotent/jour)
        try:
            import maildoso_ramp
            maildoso_ramp.adjust_caps(site)
        except Exception:
            pass
        return {"ok": True, "sent": res.get("sent", 0)}

    return {"ok": False, "error": f"canal non supporté: {channel}"}


def _save_params(cid: str, params: dict) -> None:
    _ecrire("UPDATE campaigns SET params=%s::jsonb WHERE legacy_id=%s",
            [json.dumps(params), cid])


def dispatch_due(today: _date | None = None) -> dict:
    """Cron quotidien : dispatch toutes les campagnes actives dues aujourd'hui."""
    today = today or _date.today()
    # Avant d'envoyer : vérifie les crédits d'envoi et alerte l'admin (Telegram) si bas/épuisés.
    try:
        import credit_alerts
        credit_alerts.check_and_alert()
    except Exception:  # noqa: BLE001
        pass
    ids = [r[0] for r in _lire(
        "SELECT COALESCE(legacy_id, id::text) FROM campaigns "
        "WHERE status IN ('scheduled','running') AND schedule_start <= %s", [today])]
    results = []
    for cid in ids:
        try:
            results.append({"id": cid, **dispatch_campaign(cid, today)})
        except Exception as e:  # noqa: BLE001
            results.append({"id": cid, "ok": False, "error": str(e)})
            set_status(cid, "running", error=str(e))
    return {"ok": True, "dispatched": len(ids), "results": results}


def reconcile_from_sent_log(cid: str, apply: bool = False) -> dict:
    """Recale une campagne maildoso sur les envois réellement tracés dans `maildoso_sent`.

    À utiliser après un arrêt brutal en cours de lot : les emails sont partis et tracés,
    mais ni le compteur de la campagne ni le cooldown des contacts n'ont été posés. Sans
    ce rattrapage les contacts déjà servis restent éligibles à la pioche et reçoivent le
    même message au dispatch suivant — la garde de reprise de `send_batch`, elle, ne
    couvre que le jour courant puisque le campaign_id porte la date.

    `apply=False` (défaut) : ne fait qu'un état des lieux."""
    camp = get_campaign(cid)
    if not camp:
        return {"ok": False, "error": "introuvable"}
    if camp["channel"] != "maildoso":
        return {"ok": False, "error": f"canal {camp['channel']} : pas de log d'envoi par contact"}
    site = camp["site_code"]
    c = _duck()          # journal maildoso : encore dans DuckDB
    try:
        emails = [r[0] for r in c.execute(
            "SELECT DISTINCT to_email FROM maildoso_sent "
            "WHERE campaign_id LIKE ? AND status = 'sent'", [f"{site}-{cid}-%"]).fetchall() if r[0]]
        last_day = c.execute(
            "SELECT max(created_at) FROM maildoso_sent WHERE campaign_id LIKE ? AND status = 'sent'",
            [f"{site}-{cid}-%"]).fetchone()[0]
    finally:
        c.close()

    out = {"ok": True, "campaign": cid, "name": camp["name"], "really_sent": len(emails),
           "sent_count_before": camp["sent_count"] or 0, "applied": apply}
    if not apply or not emails:
        out["note"] = "état des lieux — relancer avec --apply pour corriger"
        return out

    import contacts_pool_backend as pool
    from contacts_pool_backend import mark_pushed_to_emelia
    pc = pool._conn(read_only=True)   # lecture seule : contacts.duckdb n'admet qu'un writer
    try:
        rows = pc.execute(
            f"SELECT id, email FROM contacts WHERE email IN ({','.join(['?'] * len(emails))})",
            emails).fetchall()
    finally:
        pc.close()
    by_email = {e: i for i, e in rows}

    marked, missing = 0, []
    day = (last_day.date() if hasattr(last_day, "date") else _date.today()).isoformat()
    for em in emails:
        ct_id = by_email.get(em)
        if not ct_id:
            missing.append(em)
            continue
        try:
            mark_pushed_to_emelia(ct_id, site, f"{site}-{cid}-{day}", "")
            marked += 1
        except Exception as e:  # noqa: BLE001
            print(f"[reconcile] marquage {em} échoué : {e}")

    # Le compteur devient le nombre d'envois réellement tracés, pas un cumul :
    # rejouer la réconciliation deux fois doit donner le même résultat.
    done = len(emails) >= (camp["target_size"] or 0)
    # Le statut n'est touché que si la campagne est encore active : réconcilier une
    # campagne mise en pause (ou annulée) ne doit pas la remettre en route.
    status = ("done" if done else "running") if camp["status"] in ACTIVE_STATUSES else camp["status"]
    _ecrire("UPDATE campaigns SET sent_count = %s, status = %s, "
            "last_dispatch_day = %s, last_dispatch_at = now() WHERE legacy_id = %s",
            [len(emails), status, day, cid])
    out.update({"contacts_marked": marked, "emails_sans_contact": len(missing),
                "sent_count_after": len(emails), "last_dispatch_day": day})
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dispatch"
    if cmd == "dispatch":
        print(json.dumps(dispatch_due(), ensure_ascii=False, default=str))
    elif cmd == "reconcile":
        if len(sys.argv) < 3:
            print(f"usage: {sys.argv[0]} reconcile <campaign_id> [--apply]")
            sys.exit(1)
        print(json.dumps(reconcile_from_sent_log(sys.argv[2], "--apply" in sys.argv),
                         ensure_ascii=False, default=str))
    else:
        print(f"usage: {sys.argv[0]} dispatch | reconcile <campaign_id> [--apply]")
