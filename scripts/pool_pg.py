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
    NOT ct.global_blacklisted
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
    familles c'est `match` qui décide, et l'exclusion est toujours en OU.
    """
    r = {"include": rules.get("include") or {}, "exclude": rules.get("exclude") or {},
         "match": str(rules.get("match") or "AND").upper()}
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
    exc = cote(r["exclude"], "OR", "exc")
    if exc:
        # `NOT COALESCE(...)` et non `NOT (...)` : voir la note de `_geo`, même piège NULL.
        sql += f" AND NOT COALESCE({exc}, false)"
    return sql, params, bool(r["include"].get("engagement"))


def pick_for_segment(site_code: str, rules: dict, limit: int = 30,
                     cleaned_within_days: int = CLEANED_WITHIN_DAYS) -> list[dict]:
    seg_sql, seg_p, eng = _segment_sql(rules)
    params: dict = {"site": site_code, "cleaned": cleaned_within_days,
                    "etats": _ETATS_REENGAGEMENT if eng else _ETATS_FROID, "limit": limit}
    params.update(seg_p)
    besoin_eng = "eng." in seg_sql
    sql = (_SELECT + _FROM + (_JOIN_ENG if besoin_eng else "")
           + " WHERE " + _ELIGIBLE + seg_sql + _ORDRE + " LIMIT %(limit)s")
    return [_ligne(r) for r in _q(sql, params)]


def count_for_segment(site_code: str, rules: dict,
                      cleaned_within_days: int = CLEANED_WITHIN_DAYS,
                      patience_s: float = 6.0) -> int:
    seg_sql, seg_p, eng = _segment_sql(rules)
    params: dict = {"site": site_code, "cleaned": cleaned_within_days,
                    "etats": _ETATS_REENGAGEMENT if eng else _ETATS_FROID}
    params.update(seg_p)
    besoin_eng = "eng." in seg_sql
    sql = ("SELECT count(*)" + _FROM + (_JOIN_ENG if besoin_eng else "")
           + " WHERE " + _ELIGIBLE + seg_sql)
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
