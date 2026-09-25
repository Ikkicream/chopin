#!/usr/bin/env python3
"""pool_pg.py — Lectures du pool servies par PostgreSQL (étape 4 de la migration).

Implémente, à l'identique, les fonctions de `contacts_pool_backend` qui décident QUI reçoit
un email. Elles sont portées en premier parce qu'une divergence ici se paie en renvois et en
réputation d'expéditeur ; le reste du module (listes d'écran, compteurs d'ambiance) peut
rester sur DuckDB le temps de la bascule, les deux bases étant tenues alignées par `pg_sync`.

Trois différences de fond avec la version DuckDB, toutes voulues :

1. **La fenêtre de 120 jours est DÉDUITE du journal** (`email_events`), plus lue dans une
   table `email_suppression` tenue à la main. Les trois bugs de renvoi du 19/08/2026
   n'existaient que parce que « a reçu un email » était recopié dans trois endroits.
2. **`sectors` est un vrai tableau** : `'immobilier' = ANY(sectors)` sur index GIN, au lieu
   d'un `LIKE '%immobilier%'` sur du JSON sérialisé qui forçait un parcours complet.
3. **Le cooldown même-site et inter-sites se lisent au même endroit** — le journal — donc
   ils ne peuvent plus diverger l'un de l'autre.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

# Doit rester aligné sur contacts_pool_backend.SUPPRESSION_DAYS.
SUPPRESSION_DAYS = 120
CLEANED_WITHIN_DAYS = 180

_POOL = None
_LOCK = threading.Lock()


def _dsn() -> str:
    for ligne in ENV_FILE.read_text().splitlines():
        if ligne.startswith("PG_DSN="):
            return ligne.split("=", 1)[1].strip()
    raise RuntimeError("PG_DSN absent de .env")


def _conn():
    """Connexion depuis un pool maison.

    PostgreSQL admet les connexions concurrentes, mais chaque `connect()` coûte un aller-retour
    et un fork côté serveur. L'API ouvrait une connexion DuckDB par appel parce qu'elle n'avait
    pas le choix (verrou unique) ; ici on peut faire mieux.
    """
    global _POOL
    import psycopg2.pool
    with _LOCK:
        if _POOL is None:
            _POOL = psycopg2.pool.ThreadedConnectionPool(1, 10, _dsn())
    return _POOL.getconn()


def _rendre(c) -> None:
    if _POOL is not None:
        _POOL.putconn(c)


def _ecrire(sql: str, params=None) -> int:
    """Une écriture, validée, avec retour de la connexion au pool. Rend le nombre de lignes.

    Trois modules en avaient recopié une version identique au caractère près
    (`expediteur`, `refroidissement`, `mozart`). Ce n'est pas seulement du doublon : c'est
    un contrat de transaction — ouvrir, exécuter, VALIDER, RENDRE la connexion. Trois
    copies, c'est trois endroits où l'on peut oublier le `commit` ou le `_rendre`, et une
    connexion non rendue épuise le pool en silence.
    """
    c = _conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, params or {})
            n = cur.rowcount
        c.commit()
        return n
    finally:
        _rendre(c)


def _q(sql: str, params: tuple = ()) -> list[tuple]:
    c = _conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        c.rollback()   # lecture seule : on ne laisse jamais de transaction ouverte
        _rendre(c)


# ── Fragments partagés ────────────────────────────────────────────────────────

# Éligibilité de base, identique pour la pioche, les segments et les compteurs : une seule
# écriture, donc aucun risque qu'un compteur affiche autre chose que ce qui partira.
_ELIGIBLE = f"""
    -- Le verdict stocké d'abord (modèle du 2026-08-20 : PostgreSQL accueille TOUS les
    -- contacts, `etat` dit à qui on a le droit d'écrire). Les conditions qui suivent le
    -- recalculent depuis les faits bruts : elles restent, en second rideau, pour qu'un
    -- état momentanément périmé ne puisse jamais faire partir un email de travers.
    ct.etat = 'ok'
    -- Un contact de TEST n'entre jamais dans une campagne. Le contrôle porte sur
    -- `est_test` et NON sur `etat` : `etat` est réaligné depuis le pool par
    -- `pg_reconcile` à chaque nuit, une protection posée là se serait effacée
    -- toute seule au premier passage.
    AND NOT COALESCE(ct.est_test, false)
    -- L'enrichissement data.gouv reste EXIGÉ pour envoyer (porte d'entrée « option C ») :
    -- il l'était implicitement via `etat`, il l'est désormais explicitement ici, à sa
    -- place. L'état dit si l'adresse est bonne ; c'est cette clause qui dit si on a le
    -- droit d'écrire.
    AND e.contact_id IS NOT NULL
    AND NOT ct.global_blacklisted
    AND NOT COALESCE(e.excluded, false)
    AND ct.mailnjoy_decision = 'valid'
    AND ct.mailnjoy_checked_at >= now() - interval '%(cleaned)s days'
    AND (cs.state IS NULL OR cs.state = ANY(%(etats)s))
    AND NOT EXISTS (
        SELECT 1 FROM email_events ev
        WHERE ev.email = ct.email
          AND ev.event_type = 'sent'
          AND ev.occurred_at > now() - interval '{SUPPRESSION_DAYS} days'
    )
"""

# Priorité absolue aux contacts jamais sollicités par ce site, puis la source, puis le score.
# Sans la première clé, le tri ramenait les déjà-contactés dès leur sortie de cooldown : le
# 15/08/2026, 98 des 100 envois du jour étaient des renvois.
_ORDRE = """
    ORDER BY (derniers.last_sent_at IS NULL) DESC,
             CASE ct.primary_source WHEN 'tally' THEN 0 WHEN 'serper' THEN 1
                                    WHEN 'csv' THEN 2 ELSE 3 END,
             ct.email_score DESC NULLS LAST,
             ct.updated_at DESC
"""

_SELECT = """
    SELECT ct.id, ct.email, ct.prenom, ct.nom, ct.societe, ct.tel, ct.website,
           ct.city, ct.dept_code, ct.region_code, ct.sectors,
           ct.primary_source, ct.email_score, ct.global_blacklisted,
           cs.state, derniers.last_sent_at
"""

_FROM = """
    FROM contacts ct
    LEFT JOIN contact_sites cs ON cs.contact_id = ct.id AND cs.site_code = %(site)s
    LEFT JOIN contact_enrichment e ON e.contact_id = ct.id
    LEFT JOIN LATERAL (
        SELECT max(ev.occurred_at) AS last_sent_at
        FROM email_events ev
        WHERE ev.email = ct.email AND ev.event_type = 'sent' AND ev.site_code = %(site)s
    ) derniers ON true
"""

_COLONNES = ["id", "email", "prenom", "nom", "societe", "tel", "website",
             "city", "dept_code", "region_code", "sectors",
             "primary_source", "email_score", "global_blacklisted",
             "state", "last_contacted_by_site_at"]

# Ouvrir les états prm/lead uniquement pour du RÉ-engagement : viser les cliqueurs, c'est
# reprendre contact avec des gens déjà avancés dans le tunnel. Une campagne froide, non.
_ETATS_FROID = ["cold_email"]
_ETATS_REENGAGEMENT = ["cold_email", "prm", "lead"]

_ENGAGEMENT = {
    "open_30":   "eng.last_open_at >= now() - interval '30 days'",
    "open_180":  "eng.last_open_at >= now() - interval '180 days'",
    "open_any":  "eng.last_open_at IS NOT NULL",
    "click_any": "eng.last_click_at IS NOT NULL",
}
_JOIN_ENG = " LEFT JOIN v_contact_engagement eng ON eng.contact_id = ct.id "


def _ligne(r) -> dict:
    d = dict(zip(_COLONNES, r))
    d["sectors"] = list(d["sectors"] or [])
    if d.get("last_contacted_by_site_at"):
        d["last_contacted_by_site_at"] = str(d["last_contacted_by_site_at"])
    return d


def _geo(regions, depts) -> tuple[str, dict]:
    """Filtre géographique. `COALESCE` obligatoire : en SQL `dept_code IN ('13')` vaut NULL
    — et non FALSE — quand le département est inconnu, ce qui écarterait silencieusement
    tous les contacts non géolocalisés (158 contacts perdus sur le pool LCR en juin)."""
    sql, p = "", {}
    if depts:
        sql += " AND COALESCE(ct.dept_code = ANY(%(depts)s), false)"
        p["depts"] = list(depts)
    elif regions:
        sql += " AND COALESCE(ct.region_code = ANY(%(regions)s), false)"
        p["regions"] = list(regions)
    return sql, p


# ── Les fonctions portées ─────────────────────────────────────────────────────

def pick_for_campaign(site_code: str, sector: str, limit: int = 30,
                      cooldown_global_days: int | None = None,
                      cooldown_same_site_days: int | None = None,
                      cleaned_within_days: int = CLEANED_WITHIN_DAYS,
                      regions: list[str] | None = None,
                      depts: list[str] | None = None,
                      engagement: str | None = None) -> list[dict]:
    """Les N meilleurs contacts pour une campagne. Signature identique à la version DuckDB.

    Les paramètres de cooldown sont acceptés pour compatibilité mais ignorés : la fenêtre est
    désormais celle du journal (`SUPPRESSION_DAYS`), une seule et même règle pour tous les
    sites et tous les canaux. Les accepter sans les appliquer serait trompeur si un appelant
    les changeait — aucun ne le fait aujourd'hui, et le jour où ce sera le cas, la règle
    métier devra être revue, pas contournée.
    """
    eng = _ENGAGEMENT.get(engagement or "")
    params: dict = {"site": site_code, "cleaned": cleaned_within_days,
                    "etats": _ETATS_REENGAGEMENT if eng else _ETATS_FROID,
                    "secteur": sector, "limit": limit}
    geo_sql, geo_p = _geo(regions, depts)
    params.update(geo_p)
    sql = (_SELECT + _FROM + (_JOIN_ENG if eng else "")
           + " WHERE " + _ELIGIBLE
           + " AND %(secteur)s = ANY(ct.sectors)"
           + geo_sql
           + (f" AND {eng}" if eng else "")
           + _ORDRE + " LIMIT %(limit)s")
    return [_ligne(r) for r in _q(sql, params)]


def count_available_for_sector(site_code: str, sector: str,
                               cleaned_within_days: int = CLEANED_WITHIN_DAYS,
                               regions: list[str] | None = None,
                               depts: list[str] | None = None,
                               engagement: str | None = None) -> int:
    eng = _ENGAGEMENT.get(engagement or "")
    params: dict = {"site": site_code, "cleaned": cleaned_within_days,
                    "etats": _ETATS_REENGAGEMENT if eng else _ETATS_FROID,
                    "secteur": sector}
    geo_sql, geo_p = _geo(regions, depts)
    params.update(geo_p)
    sql = ("SELECT count(*)" + _FROM + (_JOIN_ENG if eng else "")
           + " WHERE " + _ELIGIBLE
           + " AND %(secteur)s = ANY(ct.sectors)"
           + geo_sql
           + (f" AND {eng}" if eng else ""))
    r = _q(sql, params)
    return int(r[0][0]) if r else 0


def _segment_sql(rules: dict) -> tuple[str, dict, bool]:
    """Règles d'un segment → fragment SQL PostgreSQL.

    Même sémantique que la version DuckDB : dans une famille les valeurs sont en OU, entre
    familles c'est `match` qui décide — et, côté exclusion, `exclude_match` (« ET » par
    défaut : on décrit la sous-population à retirer).
    """
    r = {"include": rules.get("include") or {}, "exclude": rules.get("exclude") or {},
         "match": str(rules.get("match") or "AND").upper(),
         "exclude_match": str(rules.get("exclude_match") or "AND").upper()}
    params: dict = {}
    n = [0]

    def cote(side: dict, match: str, prefixe: str) -> str:
        parts = []
        if side.get("sectors"):
            n[0] += 1
            cle = f"{prefixe}_sec{n[0]}"
            params[cle] = list(side["sectors"])
            parts.append(f"ct.sectors && %({cle})s")
        if side.get("depts"):
            n[0] += 1
            cle = f"{prefixe}_dep{n[0]}"
            params[cle] = list(side["depts"])
            parts.append(f"COALESCE(ct.dept_code = ANY(%({cle})s), false)")
        if side.get("regions"):
            n[0] += 1
            cle = f"{prefixe}_reg{n[0]}"
            params[cle] = list(side["regions"])
            parts.append(f"COALESCE(ct.region_code = ANY(%({cle})s), false)")
        cond = _ENGAGEMENT.get(side.get("engagement") or "")
        if cond:
            parts.append(f"({cond})")
        if not parts:
            return ""
        colle = " OR " if match == "OR" else " AND "
        return "(" + colle.join(parts) + ")"

    sql = ""
    inc = cote(r["include"], r["match"], "inc")
    if inc:
        sql += f" AND {inc}"
    exc = cote(r["exclude"], r.get("exclude_match", "AND"), "exc")
    if exc:
        # `NOT COALESCE(...)` et non `NOT (...)` : voir la note de `_geo`, même piège NULL.
        sql += f" AND NOT COALESCE({exc}, false)"
    return sql, params, bool(r["include"].get("engagement"))


# ── Pression marketing (décision user 2026-08-20) ─────────────────────────────
# Les 120 jours ne s'appliquent PAS aux segments. Un segment sert une action ciblée, du
# 1 à 1 : « relancer ceux qui ont ouvert » n'a aucun sens si ceux qui ont ouvert sont
# précisément gelés pour avoir reçu. La règle allait à contresens de son propre usage.
#
# À la place, une règle de PRESSION : un contact ne reçoit pas plus de N communications par
# mois glissant, tous canaux et tous sites confondus. C'est le garde-fou qui empêche le
# retour de l'accident d'août 2026 — quatre adresses avaient reçu 11 à 18 emails en trente
# jours ; elles seraient bloquées par cette règle.
#
# Comptée sur `email_events`, seul journal qui garde CHAQUE envoi. Le pool DuckDB ne
# retient qu'une date de dernier envoi par contact : il ne peut pas compter. C'est
# pourquoi les segments passent désormais par PostgreSQL, quel que soit `PG_READS`.
DEFAUT_PRESSION_MAX = 4


def pression_max() -> int:
    """Nombre maximum de communications par mois glissant. 0 = pas de limite."""
    try:
        for ligne in (BASE_DIR / ".env").read_text().splitlines():
            if ligne.startswith("PRESSION_MAX_MOIS="):
                return max(0, int(ligne.split("=", 1)[1].strip() or DEFAUT_PRESSION_MAX))
    except Exception:
        pass
    return DEFAUT_PRESSION_MAX


PRESSION_JOURS = 30

# Fragment réutilisé par la pioche, le comptage et l'explication : une seule écriture.
_PRESSION_SQL = f"""
    (SELECT count(*) FROM email_events ev
      WHERE ev.email = ct.email AND ev.event_type = 'sent'
        AND ev.occurred_at > now() - interval '{PRESSION_JOURS} days') < %(pression)s
"""

# Éligibilité d'un SEGMENT : tout ce qui protège la réputation d'expéditeur (adresse
# valide et fraîche, non blacklistée, entreprise non exclue, enrichie) — mais la fenêtre
# de 120 jours est remplacée par la pression mensuelle.
_ELIGIBLE_SEGMENT = f"""
    ct.etat = 'ok'
    -- Un contact de TEST n'entre jamais dans une campagne. Le contrôle porte sur
    -- `est_test` et NON sur `etat` : `etat` est réaligné depuis le pool par
    -- `pg_reconcile` à chaque nuit, une protection posée là se serait effacée
    -- toute seule au premier passage.
    AND NOT COALESCE(ct.est_test, false)
    AND e.contact_id IS NOT NULL
    AND NOT ct.global_blacklisted
    AND NOT COALESCE(e.excluded, false)
    AND ct.mailnjoy_decision = 'valid'
    AND ct.mailnjoy_checked_at >= now() - interval '%(cleaned)s days'
    AND (cs.state IS NULL OR cs.state = ANY(%(etats)s))
    AND {_PRESSION_SQL}
"""


def pick_for_segment(site_code: str, rules: dict, limit: int = 30,
                     cleaned_within_days: int = CLEANED_WITHIN_DAYS) -> list[dict]:
    seg_sql, seg_p, eng = _segment_sql(rules)
    params: dict = {"site": site_code, "cleaned": cleaned_within_days,
                    "etats": _ETATS_REENGAGEMENT if eng else _ETATS_FROID, "limit": limit,
                    "pression": pression_max() or 10 ** 6}
    params.update(seg_p)
    besoin_eng = "eng." in seg_sql
    sql = (_SELECT + _FROM + (_JOIN_ENG if besoin_eng else "")
           + " WHERE " + _ELIGIBLE_SEGMENT + seg_sql + _ORDRE + " LIMIT %(limit)s")
    return [_ligne(r) for r in _q(sql, params)]


def count_for_segment(site_code: str, rules: dict,
                      cleaned_within_days: int = CLEANED_WITHIN_DAYS,
                      patience_s: float = 6.0) -> int:
    seg_sql, seg_p, eng = _segment_sql(rules)
    params: dict = {"site": site_code, "cleaned": cleaned_within_days,
                    "etats": _ETATS_REENGAGEMENT if eng else _ETATS_FROID,
                    "pression": pression_max() or 10 ** 6}
    params.update(seg_p)
    besoin_eng = "eng." in seg_sql
    sql = ("SELECT count(*)" + _FROM + (_JOIN_ENG if besoin_eng else "")
           + " WHERE " + _ELIGIBLE_SEGMENT + seg_sql)
    r = _q(sql, params)
    return int(r[0][0]) if r else 0


# ── La fenêtre de 120 jours ───────────────────────────────────────────────────

def is_suppressed(email: str) -> bool:
    if not email:
        return False
    r = _q(f"""SELECT 1 FROM email_events
               WHERE email = %s AND event_type = 'sent'
                 AND occurred_at > now() - interval '{SUPPRESSION_DAYS} days'
               LIMIT 1""", (email.strip().lower(),))
    return bool(r)


def filter_suppressed(emails: list[str]) -> set[str]:
    """Sous-ensemble bloqué, en une requête pour tout un lot."""
    ems = [(e or "").strip().lower() for e in emails if e]
    if not ems:
        return set()
    r = _q(f"""SELECT DISTINCT email::text FROM email_events
               WHERE email = ANY(%s) AND event_type = 'sent'
                 AND occurred_at > now() - interval '{SUPPRESSION_DAYS} days'""", (ems,))
    return {x[0] for x in r}


def suppression_stats() -> dict:
    r = _q(f"""SELECT count(*),
                      count(*) FILTER (WHERE last_sent_at > now() - interval '{SUPPRESSION_DAYS} days'),
                      min(release_at), max(release_at)
               FROM v_suppression""")
    t, b, mn, mx = r[0] if r else (0, 0, None, None)
    return {"total": int(t or 0), "bloques": int(b or 0),
            "prochaine_liberation": str(mn) if mn else None,
            "derniere_liberation": str(mx) if mx else None,
            "jours": SUPPRESSION_DAYS}


def pool_sectors(min_count: int = 1) -> list[str]:
    """Secteurs réellement présents. `unnest` sur le tableau, là où DuckDB devait
    désérialiser du JSON ligne à ligne côté Python."""
    r = _q("""SELECT s, count(*) FROM contacts ct, unnest(ct.sectors) s
              WHERE NOT ct.global_blacklisted
              GROUP BY s HAVING count(*) >= %s ORDER BY count(*) DESC""", (min_count,))
    return [x[0] for x in r]


# ── Vision : l'état de la base, lu dans PostgreSQL ────────────────────────────
# La page Vision lisait le pool DuckDB — donc le fichier que le scraping verrouille. Elle
# lit désormais PostgreSQL, où tous les contacts vivent depuis le 2026-08-20 avec leur
# `etat`. Même forme de sortie que `contacts_pool_backend.vision_contacts` : les deux
# peuvent être comparées côte à côte, et c'est ce qui a servi à valider la bascule.
#
# La cascade des étapes est écrite dans le MÊME ORDRE que côté DuckDB — blacklisté, écarté,
# en repos, à vérifier, prêt, vérifié. Changer l'ordre changerait les chiffres sans que
# personne ne comprenne pourquoi.
_ETAPE_PG = """
    CASE
        WHEN ct.etat = 'spam' THEN 'blacklisted'
        WHEN ct.etat IN ('ko', 'exclu') THEN 'ecarte'
        WHEN sup.email IS NOT NULL THEN 'repos'
        WHEN ct.etat = 'a_verifier' THEN 'a_verifier'
        WHEN e.siret IS NOT NULL THEN 'pret'
        ELSE 'verifie'
    END
"""
# « Prêt » exige un SIRET retrouvé, « Vérifié » se contente d'une adresse valide : c'est
# exactement l'ordre de la cascade DuckDB, et c'est ce que dit la légende à l'écran —
# « société non retrouvée au SIRET : contactable quand même ».

_VISION_FROM = """
    FROM contacts ct
    JOIN contact_sites cs ON cs.contact_id = ct.id AND cs.site_code = %(site)s
    LEFT JOIN contact_enrichment e ON e.contact_id = ct.id
    LEFT JOIN v_suppression sup ON sup.email = ct.email AND sup.release_at > now()
"""


def vision_contacts(site_code: str, secteurs_max: int = 5) -> dict:
    """Étapes, enrichissement, engagement et secteurs — depuis PostgreSQL."""
    p = {"site": site_code}
    total = _q("SELECT count(*) " + _VISION_FROM, p)[0][0]
    etapes = {r[0]: int(r[1]) for r in
              _q(f"SELECT ({_ETAPE_PG}) AS etape, count(*) {_VISION_FROM} GROUP BY 1", p)}

    enrichi, non_trouve, exclu = _q(f"""
        SELECT count(*) FILTER (WHERE e.siret IS NOT NULL),
               count(*) FILTER (WHERE e.contact_id IS NOT NULL AND e.siret IS NULL
                                  AND NOT COALESCE(e.excluded, false)),
               count(*) FILTER (WHERE COALESCE(e.excluded, false))
        {_VISION_FROM}""", p)[0]

    # Engagement : compté sur le JOURNAL d'événements, pas sur un dernier état. Le pool
    # n'garde que le dernier signal par contact et sous-compte donc les ouvreurs.
    contactes, ouvreurs, cliqueurs = _q("""
        SELECT count(DISTINCT email) FILTER (WHERE event_type = 'sent'),
               count(DISTINCT email) FILTER (WHERE event_type = 'open'),
               count(DISTINCT email) FILTER (WHERE event_type = 'click')
        FROM email_events WHERE site_code = %(site)s""", p)[0]

    secteurs = _q("""
        SELECT s AS secteur, count(*) AS n
        FROM contacts ct
        JOIN contact_sites cs ON cs.contact_id = ct.id AND cs.site_code = %(site)s,
             unnest(ct.sectors) AS s
        WHERE s <> '' GROUP BY 1 ORDER BY n DESC""", p)

    liste = [{"secteur": r[0], "n": int(r[1])} for r in secteurs]
    tete, reste = liste[:secteurs_max], liste[secteurs_max:]
    if reste:
        tete.append({"secteur": "Autres", "n": sum(x["n"] for x in reste),
                     "detail": len(reste)})

    import contacts_pool_backend as _cpb           # vocabulaire des étapes, défini une fois
    return {
        "site": site_code,
        "total": int(total),
        "etapes": {cle: etapes.get(cle, 0) for cle in _cpb.ETAPES},
        "etapes_libelles": _cpb.ETAPES,
        "enrichissement": {
            "siret_trouve": int(enrichi or 0),
            "siret_non_trouve": int(non_trouve or 0),
            "exclus": int(exclu or 0),
            "jamais_traite": max(0, int(total) - int(enrichi or 0) - int(non_trouve or 0) - int(exclu or 0)),
        },
        "engagement": {
            "contactes": int(contactes or 0),
            "ouvreurs": int(ouvreurs or 0),
            "cliqueurs": int(cliqueurs or 0),
        },
        "secteurs": tete,
        "source": "postgresql",
    }


def enrichment_stats() -> dict:
    """Statistiques data.gouv, depuis PostgreSQL — même forme que la version DuckDB.

    Le miroir PostgreSQL ne portait que (contact_id, excluded, raw) : le SIRET dormait dans
    le JSON, les motifs d'exclusion et les signaux n'existaient pas. Les colonnes ont été
    ajoutées et synchronisées le 2026-08-20 (`pg_sync_enrichment.py`), ce qui rend cette
    lecture possible.
    """
    total_societe, in_table, enriched, unmatched, exclus = _q("""
        SELECT (SELECT count(*) FROM contacts WHERE societe IS NOT NULL AND societe <> ''),
               (SELECT count(*) FROM contact_enrichment),
               (SELECT count(*) FROM contact_enrichment WHERE siret IS NOT NULL),
               (SELECT count(*) FROM contact_enrichment
                 WHERE siret IS NULL AND NOT COALESCE(excluded, false)),
               (SELECT count(*) FROM contact_enrichment WHERE COALESCE(excluded, false))
    """)[0]

    signaux = _q("""SELECT count(*) FILTER (WHERE est_rge),
                           count(*) FILTER (WHERE est_qualiopi),
                           count(*) FILTER (WHERE est_ess) FROM contact_enrichment""")[0]
    motifs = {r[0]: int(r[1]) for r in _q("""
        SELECT exclusion_reason, count(*) FROM contact_enrichment
        WHERE COALESCE(excluded, false) AND exclusion_reason IS NOT NULL GROUP BY 1""")}
    dernier = _q("SELECT max(enriched_at) FROM contact_enrichment")[0][0]

    # « Reste à traiter » : les contacts qui ont un nom de société mais aucune ligne
    # d'enrichissement. C'est le seul chiffre qui dit si le cron a du travail devant lui.
    # Les blacklistés sont exclus : on ne dépense pas d'appel data.gouv pour quelqu'un
    # qu'on ne recontactera jamais.
    reste = _q("""
        SELECT count(*) FROM contacts ct
        LEFT JOIN contact_enrichment e ON e.contact_id = ct.id
        WHERE ct.societe IS NOT NULL AND ct.societe <> '' AND e.contact_id IS NULL
          AND NOT COALESCE(ct.global_blacklisted, false)""")[0][0]

    # Idem pour le nettoyage : compter les 1 482 blacklistés comme « à vérifier » ferait
    # croire à un retard de vérification qui n'existe pas — on ne vérifie pas une adresse
    # qu'on s'interdit d'écrire.
    mn = _q("""SELECT count(*) FILTER (WHERE mailnjoy_decision IS NULL),
                      count(*) FILTER (WHERE mailnjoy_decision = 'valid'),
                      count(*) FILTER (WHERE mailnjoy_decision IS NOT NULL
                                         AND mailnjoy_decision <> 'valid')
               FROM contacts WHERE NOT COALESCE(global_blacklisted, false)""")[0]

    return {
        "total_societe": int(total_societe), "in_table": int(in_table),
        "enriched": int(enriched), "unmatched": int(unmatched),
        "hard_excluded": int(exclus), "remaining": int(reste),
        "signals": {"rge": int(signaux[0]), "qualiopi": int(signaux[1]), "ess": int(signaux[2])},
        "hard_exclusion_reasons": motifs,
        "last_enriched_at": str(dernier) if dernier else None,
        "mailnjoy": {"missing": int(mn[0]), "valid": int(mn[1]), "other": int(mn[2])},
        "source": "postgresql",
    }


def expliquer_segment(site_code: str, rules: dict,
                      cleaned_within_days: int = CLEANED_WITHIN_DAYS) -> dict:
    """Pourquoi un segment ne ramène-t-il pas plus de monde ?

    Rend la population qui correspond au CIBLAGE, puis ce qui la retient : pression
    mensuelle atteinte, adresse non valide, entreprise exclue, blacklist. Sans ça, un
    compteur à zéro passe pour une panne.
    """
    seg_sql, seg_p, eng = _segment_sql(rules)
    params: dict = {"site": site_code, "cleaned": cleaned_within_days,
                    "etats": _ETATS_REENGAGEMENT if eng else _ETATS_FROID,
                    "pression": pression_max() or 10 ** 6}
    params.update(seg_p)
    besoin_eng = "eng." in seg_sql
    # Population de l'INCLUSION seule : c'est elle qu'il faut comparer au résultat final
    # pour savoir combien de contacts les exclusions retirent.
    seg_inc, seg_inc_p, _ = _segment_sql({"match": rules.get("match", "AND"),
                                          "include": (rules.get("include") or {}),
                                          "exclude": {}})
    p_inc = dict(params); p_inc.update(seg_inc_p)
    inclus = _q("SELECT count(*)" + _FROM + (_JOIN_ENG if "eng." in seg_inc else "")
                + " WHERE " + _ELIGIBLE_SEGMENT + seg_inc, p_inc)
    inclus = int(inclus[0][0]) if inclus else 0

    sql = (f"""
        SELECT count(*),
               count(*) FILTER (WHERE ct.global_blacklisted),
               count(*) FILTER (WHERE COALESCE(e.excluded, false)),
               count(*) FILTER (WHERE ct.mailnjoy_decision IS DISTINCT FROM 'valid'
                                   OR ct.mailnjoy_checked_at < now() - interval '%(cleaned)s days'),
               count(*) FILTER (WHERE NOT ({_PRESSION_SQL}))
        """ + _FROM + (_JOIN_ENG if besoin_eng else "")
        + " WHERE (cs.state IS NULL OR cs.state = ANY(%(etats)s))" + seg_sql)
    r = _q(sql, params)
    correspondants, blacklist, exclus, email_ko, pression = r[0] if r else (0, 0, 0, 0, 0)
    import segments_backend as _sb
    contactables = count_for_segment(site_code, rules, cleaned_within_days=cleaned_within_days)
    return {
        "correspondants": int(correspondants or 0),
        "inclus": inclus,
        # Ce que les exclusions retirent. Quand ce nombre égale la population incluse, le
        # segment s'annule lui-même — c'est le symptôme d'un critère répété des deux côtés.
        "retires_par_exclusion": max(0, inclus - contactables),
        "conflits": _sb.conflits_rules(rules),
        "ecartes": {
            "pression": int(pression or 0),
            "blacklist": int(blacklist or 0),
            "email_non_valide": int(email_ko or 0),
            "entreprise_exclue": int(exclus or 0),
        },
        "pression_max": pression_max(),
        "pression_jours": PRESSION_JOURS,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Acquisition : liste, compteurs, filtres (étape 5 de la migration)
# ──────────────────────────────────────────────────────────────────────────────
# Portées ici parce que ce sont les dernières lectures d'écran encore servies par le
# fichier que le scraping verrouille : tant qu'elles y restaient, ouvrir Acquisition
# pendant une passe de collecte affichait « Chargement… » sans fin.
#
# Trois substitutions, toutes voulues et toutes dans le même sens — remplacer un champ
# recopié par le fait qui le produit :
#
# 1. **L'engagement vient du journal** (`email_events`), plus des colonnes
#    `last_opened_at` / `last_clicked_at` de l'historique de site, qui ne retenaient que
#    le DERNIER signal par contact. Le canal (`last_open_channel`) est celui de
#    l'événement le plus récent, et non plus celui écrasé au passage suivant.
# 2. **Le repos vient de `v_suppression`**, donc du même journal — les 120 jours ne sont
#    plus lus dans une table tenue à la main en parallèle.
# 3. **Le secteur se teste sur un vrai tableau** (`= ANY(ct.sectors)`, index GIN) au lieu
#    d'un `LIKE '%…%'` sur du JSON sérialisé, qui matchait aussi `immobilier-neuf` quand
#    on demandait `immobilier`.
#
# Le reste est une transposition littérale : même cascade d'étapes, mêmes filtres, même
# ordre de tri. Équivalence vérifiée chiffre par chiffre — voir tests/test_pg_acquisition.py.

ETAPES_CLES = ("blacklisted", "ecarte", "repos", "a_verifier", "verifie", "pret")

# Même cascade que `contacts_pool_backend._ETAPE_SQL`, écrite avec les colonnes
# PostgreSQL : `mailnjoy_decision` remplace l'extraction JSON (colonne dédiée, indexée,
# et prouvée strictement égale à `mailnjoy_check->>'decision'` sur les 10 027 contacts).
_ETAPE_SQL = """
CASE
    WHEN COALESCE(ct.global_blacklisted, FALSE) THEN 'blacklisted'
    -- Un contact REJETÉ à la collecte est écarté, pas « à vérifier ». Sans cette ligne il
    -- retombait plus bas sur `mailnjoy_decision IS NULL` — vrai, puisqu'on ne l'a jamais
    -- vérifié et qu'on ne le fera pas : il s'affichait alors comme une vérification en
    -- attente qui n'arriverait jamais. 64 fiches dans ce cas le 2026-08-25.
    WHEN ct.etat = 'ko' THEN 'ecarte'
    WHEN ct.mailnjoy_decision IS NOT NULL AND ct.mailnjoy_decision <> 'valid' THEN 'ecarte'
    WHEN COALESCE(e.excluded, FALSE) THEN 'ecarte'
    WHEN sup.release_at IS NOT NULL THEN 'repos'
    WHEN ct.mailnjoy_decision IS NULL THEN 'a_verifier'
    WHEN e.siret IS NOT NULL THEN 'pret'
    ELSE 'verifie'
END
"""

# Agrégat du journal par adresse, restreint au site : une passe sur `email_events` puis
# une jointure de hachage. La variante en LATERAL relisait le journal une fois par contact.
# La jointure porte sur l'ADRESSE et non sur `contact_id` : 1 529 des 3 835 événements
# n'ont pas de contact_id (rattachés après coup par l'adresse seule), et les ignorer
# perdait 5 ouvreurs sur 441.
_ENG_SITE = """
    LEFT JOIN (
        SELECT ev.email,
               max(ev.occurred_at) FILTER (WHERE ev.event_type = 'sent')  AS last_sent_at,
               max(ev.occurred_at) FILTER (WHERE ev.event_type = 'open')  AS last_open_at,
               max(ev.occurred_at) FILTER (WHERE ev.event_type = 'click') AS last_click_at,
               (array_agg(ev.channel ORDER BY ev.occurred_at DESC)
                    FILTER (WHERE ev.event_type = 'open'))[1]  AS open_channel,
               (array_agg(ev.channel ORDER BY ev.occurred_at DESC)
                    FILTER (WHERE ev.event_type = 'click'))[1] AS click_channel,
               max(ev.occurred_at) FILTER (WHERE ev.event_type = 'reply')  AS last_reply_at,
               max(ev.occurred_at) FILTER (WHERE ev.event_type = 'bounce') AS last_bounce_at,
               max(ev.occurred_at) FILTER (WHERE ev.event_type = 'unsub')  AS last_unsub_at
        FROM email_events ev
        WHERE ev.site_code = %(site)s
        GROUP BY ev.email
    ) eng ON eng.email = ct.email
"""

_ACQ_FROM = """
    FROM contacts ct
    JOIN contact_sites cs ON cs.contact_id = ct.id
    LEFT JOIN contact_enrichment e ON e.contact_id = ct.id
    LEFT JOIN v_suppression sup ON sup.email = ct.email AND sup.release_at > now()
""" + _ENG_SITE + """
    WHERE cs.site_code = %(site)s
"""


def _acq_filtre(site_code: str, state=None, sectors_in=None, source=None,
                search_email=None, engagement=None, etape=None) -> tuple[str, dict]:
    """Le FROM/WHERE commun à la liste, au comptage et aux compteurs d'étape.

    Écrit une fois, exactement comme côté DuckDB : deux clauses séparées finissent par
    diverger, et la pagination annonce alors un nombre de pages qui ne correspond à rien.
    """
    q = _ACQ_FROM
    p: dict = {"site": site_code}

    if engagement == "openers":
        q += " AND eng.last_open_at IS NOT NULL"
    elif engagement == "clickers":
        q += " AND eng.last_click_at IS NOT NULL"
    if state:
        q += " AND cs.state = ANY(%(state)s)"
        p["state"] = list(state)
    if source:
        q += " AND cs.source = ANY(%(source)s)"
        p["source"] = list(source)
    if search_email:
        # Le champ annonce « email, nom, prénom, société, téléphone » : la recherche doit
        # porter sur les cinq. `citext` rend la comparaison d'adresse insensible à la
        # casse toute seule ; les autres colonnes passent par lower().
        q += (" AND (ct.email ILIKE %(rech)s"
              " OR lower(COALESCE(ct.societe, '')) LIKE %(rechl)s"
              " OR lower(COALESCE(ct.nom, '')) LIKE %(rechl)s"
              " OR lower(COALESCE(ct.prenom, '')) LIKE %(rechl)s"
              " OR COALESCE(ct.tel, '') LIKE %(rechb)s)")
        p["rech"] = f"%{search_email}%"
        p["rechl"] = f"%{search_email.lower()}%"
        p["rechb"] = f"%{search_email}%"
    if sectors_in:
        q += " AND ct.sectors && %(secteurs)s"
        p["secteurs"] = list(sectors_in)
    if etape:
        etapes = [x for x in (etape if isinstance(etape, (list, tuple)) else [etape]) if x]
        if etapes:
            q += f" AND ({_ETAPE_SQL}) = ANY(%(etapes)s)"
            p["etapes"] = etapes
    return q, p


def count_contacts_for_site(site_code: str, state=None, sectors_in=None, source=None,
                            search_email=None, engagement=None, etape=None) -> int:
    """Nombre total de contacts correspondant aux filtres — pour la pagination."""
    q, p = _acq_filtre(site_code, state, sectors_in, source, search_email, engagement, etape)
    r = _q("SELECT count(*) " + q, p)
    return int(r[0][0] or 0) if r else 0


def compter_par_etape(site_code: str, state=None, sectors_in=None, source=None,
                      search_email=None, engagement=None) -> dict:
    """Combien de contacts à chaque étape, pour les filtres en cours.

    L'étape elle-même est volontairement absente des filtres : un onglet doit annoncer ce
    qu'il contient si on clique dessus, pas ce qu'il contient une fois déjà cliqué.
    """
    q, p = _acq_filtre(site_code, state, sectors_in, source, search_email, engagement, None)
    rows = _q(f"SELECT ({_ETAPE_SQL}) AS etape, count(*) {q} GROUP BY 1", p)
    return {cle: 0 for cle in ETAPES_CLES} | {r[0]: int(r[1]) for r in rows}


_ACQ_SELECT = """
    SELECT ct.id::text, ct.email::text, ct.prenom, ct.nom, ct.societe, ct.tel, ct.website,
           ct.city, ct.dept_code, ct.region_code,
           ct.logo_url, ct.client_since,
           ct.sectors, ct.primary_source, ct.email_score, ct.global_blacklisted,
           cs.state, cs.source, cs.added_at,
           cs.state_history, cs.last_action_at, cs.notes,
           eng.last_sent_at, eng.last_reply_at, eng.last_bounce_at, eng.last_unsub_at,
           eng.last_open_at, eng.last_click_at, eng.open_channel, eng.click_channel,
           ct.mailnjoy_check, e.siret, e.match_quality, e.excluded, e.exclusion_reason,
           sup.release_at, """ + _ETAPE_SQL + """ AS etape,
           COALESCE(ct.est_test, false)
"""

_ACQ_COLS = [
    "id", "email", "prenom", "nom", "societe", "tel", "website",
    "city", "dept_code", "region_code",
    "logo_url", "client_since",
    "sectors", "primary_source", "email_score", "global_blacklisted",
    "state", "source", "added_to_site_at",
    "state_history", "last_action_at", "notes",
    "email_sent_at", "emelia_replied_at", "emelia_bounced_at", "emelia_unsubscribed_at",
    "last_opened_at", "last_clicked_at", "last_open_channel", "last_click_channel",
    "mailnjoy_check", "siret", "match_quality", "enrichissement_exclu",
    "enrichissement_motif", "en_repos_jusquau", "etape",
    # La fiche de test se signale à l'écran : épinglée en tête, grisée, étiquetée.
    "est_test",
]

# Champs que l'écran attend encore et que PostgreSQL ne porte pas : les identifiants
# Emelia vivaient dans l'historique de site DuckDB, le journal ne les a jamais repris.
# Rendus à `None` plutôt qu'omis, pour que l'interface reçoive toujours la même forme.
_ACQ_ABSENTS = ("emelia_campaign_id", "emelia_contact_id",
                "emelia_opened_at", "emelia_clicked_at")


def list_contacts_for_site(site_code: str, state=None, sectors_in=None, source=None,
                           search_email=None, engagement=None, etape=None,
                           limit: int = 500, offset: int = 0) -> list[dict]:
    """Liste les contacts utilisés par un site, dans la forme attendue par Acquisition."""
    q, p = _acq_filtre(site_code, state, sectors_in, source, search_email, engagement, etape)
    p["lim"] = int(limit)
    p["off"] = int(offset)
    rows = _q(_ACQ_SELECT + q +
              " ORDER BY COALESCE(ct.est_test, false) DESC,"
              " cs.last_action_at DESC NULLS LAST LIMIT %(lim)s OFFSET %(off)s", p)

    import contacts_pool_backend as _cpb   # pour ETAPES, le vocabulaire d'affichage
    out = []
    for r in rows:
        d = dict(zip(_ACQ_COLS, r))
        for absent in _ACQ_ABSENTS:
            d[absent] = None
        # `last_contacted_by_site_at` et `email_sent_at` disaient la même chose dans le
        # pool (l'un recopiait l'autre) ; le journal n'en connaît qu'un. L'écran lit
        # `last_contacted_by_site_at || email_sent_at`, les deux restent donc alimentés.
        d["last_contacted_by_site_at"] = d.get("email_sent_at")
        d["sectors"] = list(d.get("sectors") or [])
        if d.get("en_repos_jusquau"):
            d["en_repos_jusquau"] = str(d["en_repos_jusquau"])
        d["etape_label"] = _cpb.ETAPES.get(d.get("etape") or "", {}).get("label", "—")
        for ts in ("added_to_site_at", "last_action_at", "email_sent_at", "client_since",
                   "emelia_replied_at", "emelia_bounced_at", "emelia_unsubscribed_at",
                   "last_contacted_by_site_at", "last_opened_at", "last_clicked_at"):
            if d.get(ts):
                d[ts] = str(d[ts])
        out.append(d)
    return out


def filter_values_for_site(site_code: str) -> dict:
    """Valeurs distinctes (secteur, source) AVEC compteurs, pour les filtres Acquisition."""
    secs = _q("""
        SELECT s AS secteur, count(*) AS n
        FROM contacts ct
        JOIN contact_sites cs ON cs.contact_id = ct.id,
             LATERAL unnest(ct.sectors) AS s
        WHERE cs.site_code = %(site)s AND btrim(s) <> ''
        GROUP BY 1 ORDER BY n DESC""", {"site": site_code})
    srcs = _q("""
        SELECT COALESCE(NULLIF(btrim(cs.source), ''), '?') AS src, count(*) AS n
        FROM contacts ct
        JOIN contact_sites cs ON cs.contact_id = ct.id
        WHERE cs.site_code = %(site)s
        GROUP BY 1 ORDER BY n DESC""", {"site": site_code})
    return {
        "sectors": [{"value": r[0], "count": int(r[1])} for r in secs],
        "sources": [{"value": r[0], "count": int(r[1])} for r in srcs],
    }


def stats_for_site(site_code: str) -> dict:
    """Totaux du site par état et par source, comptés par ADRESSE distincte.

    La contrainte d'unicité `(contact_id, site_code)` rend le DISTINCT superflu ici — il
    est gardé parce que l'appelant (`followup_backend`) compare ces nombres à ceux du
    pool, où les historiques orphelins imposaient de compter par email.
    """
    total = _q("""
        SELECT count(DISTINCT ct.email) FROM contact_sites cs
        JOIN contacts ct ON ct.id = cs.contact_id WHERE cs.site_code = %(site)s""",
        {"site": site_code})
    by_state = _q("""
        SELECT cs.state, count(DISTINCT ct.email) FROM contact_sites cs
        JOIN contacts ct ON ct.id = cs.contact_id WHERE cs.site_code = %(site)s
        GROUP BY 1""", {"site": site_code})
    by_source = _q("""
        SELECT cs.source, count(DISTINCT ct.email) FROM contact_sites cs
        JOIN contacts ct ON ct.id = cs.contact_id WHERE cs.site_code = %(site)s
        GROUP BY 1""", {"site": site_code})
    return {
        "total": int(total[0][0] or 0) if total else 0,
        "by_state": {r[0]: int(r[1]) for r in by_state},
        "by_source": {r[0]: int(r[1]) for r in by_source},
    }


def engagement_par_canal(site_code: str) -> dict:
    """Ouvreurs et cliqueurs UNIQUES par canal de routage, pour ce site.

    Le pool comptait des personnes en ne gardant que leur dernier signal, ce qui rangeait
    un contact ouvert via Maildoso puis via Sweego dans le seul second canal. Ici chaque
    (personne, canal) est compté une fois : un même contact peut donc apparaître dans deux
    canaux, ce qui est la réalité de ce qui s'est passé.
    """
    rows = _q("""
        SELECT ev.channel,
               count(DISTINCT ev.email) FILTER (WHERE ev.event_type = 'open')  AS ouvreurs,
               count(DISTINCT ev.email) FILTER (WHERE ev.event_type = 'click') AS cliqueurs
        FROM email_events ev
        WHERE ev.site_code = %(site)s AND ev.event_type IN ('open', 'click')
        GROUP BY 1""", {"site": site_code})
    return {(r[0] or "inconnu"): {"ouvreurs": int(r[1] or 0), "cliqueurs": int(r[2] or 0)}
            for r in rows}


def check_pool_depletion(site_code: str, sectors: list[str], threshold: int = 10) -> list[dict]:
    """Secteurs dont la réserve contactable passe sous le seuil."""
    out = []
    for s in sectors:
        n = count_available_for_sector(site_code, s)
        if n < threshold:
            out.append({"sector": s, "available": n})
    return out
