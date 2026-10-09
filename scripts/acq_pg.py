#!/usr/bin/env python3
"""acq_pg.py — la chaîne d'ACQUISITION dans PostgreSQL (lot 1 de la sortie de DuckDB, 06/10).

Pourquoi. `god_mode.duckdb` et `contacts.duckdb` n'admettent qu'un écrivain : le scraper,
le drain Mailnjoy, l'enrichissement et le nettoyage se bloquaient entre eux. Bilan de la
seule nuit du 05 au 06/10 : 42 leads perdus sur verrou, un créneau d'entretien où le
scraping est interdit, et des passes de rattrapage pour recoller les morceaux.

Ce module porte, côté PostgreSQL :
  - la file Mailnjoy `scrappe_pending`, le registre `scrappe`, le tombstone `scrappe_rejected`
    (mêmes colonnes que dans DuckDB) ;
  - l'entrée DIRECTE d'un contact scrappé dans `contacts` / `contact_sites`
    (`entre_par_pg = true` : `pg_reconcile` ne doit jamais le retirer faute de copie DuckDB) ;
  - l'application d'un verdict Mailnjoy « valid » à la fiche PostgreSQL. Avant, ce verdict
    restait dans `scrappe` : la fiche restait « à vérifier » et le nettoyage de nuit
    repayait un crédit Mailnjoy pour la même adresse.

Activé par `ACQUISITION_PG=1` dans .env (lu par `actif()`). DuckDB reçoit encore une copie
best-effort pendant la transition : ses lecteurs (écrans, stats) sont portés au lot 2.

Usage : python3 scripts/acq_pg.py schema | copier | etat
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

MAILNJOY_MAX_ATTEMPTS = 5
CHRONIC_AGE_DAYS = 7
CLEANED_WITHIN_DAYS = 180
SECTEURS_HORS_CIBLE = ["banque", "assurance", "energie", "tech-digital", "sante-pharma"]


def actif() -> bool:
    """La bascule : `ACQUISITION_PG=1` dans .env. Relu à chaque appel (pas de redémarrage)."""
    try:
        for ligne in (BASE_DIR / ".env").read_text().splitlines():
            if ligne.startswith("ACQUISITION_PG="):
                return ligne.split("=", 1)[1].strip() == "1"
    except Exception:  # noqa: BLE001
        pass
    return False


def _q(sql: str, params=None) -> list[tuple]:
    import pool_pg
    return pool_pg._q(sql, params or {})


def _ecrire(sql: str, params=None) -> int:
    import pool_pg
    return pool_pg._ecrire(sql, params or {})


def _ecrire_rendre(sql: str, params=None) -> list[tuple]:
    """Écriture VALIDÉE qui rend des lignes (INSERT … RETURNING). `pool_pg._q` annule
    toujours sa transaction : y passer une écriture la perdrait en silence."""
    import pool_pg
    c = pool_pg._conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, params or {})
            rows = cur.fetchall()
        c.commit()
        return rows
    except Exception:
        c.rollback()
        raise
    finally:
        pool_pg._rendre(c)


def _j(v):
    """JSON → texte pour une colonne jsonb (accepte dict, list, texte JSON ou None)."""
    if v is None:
        return None
    if isinstance(v, str):
        try:
            json.loads(v)
            return v
        except Exception:  # noqa: BLE001
            return json.dumps(v)
    return json.dumps(v, default=str)


# ── Schéma ─────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS scrappe_pending (
    id text PRIMARY KEY, site_code text, company_name text, contact_name text,
    email text, phone text, sector text, city text, postal_code text, website text,
    source text, search_query text, score int DEFAULT 0,
    status text DEFAULT 'pending_mailnjoy', raw_data jsonb, email_score int,
    email_validation_reasons jsonb, region_code text, dept_code text,
    created_at timestamptz DEFAULT now(), mailnjoy_attempts int DEFAULT 0,
    mailnjoy_last_error text);
CREATE INDEX IF NOT EXISTS scrappe_pending_email ON scrappe_pending (lower(email));

CREATE TABLE IF NOT EXISTS scrappe (
    id text PRIMARY KEY, site_code text, company_name text, contact_name text,
    email text, phone text, sector text, city text, postal_code text, website text,
    source text, search_query text, score int DEFAULT 0, status text DEFAULT 'new',
    raw_data jsonb, created_at timestamptz DEFAULT now(), validated_at timestamptz,
    contacted_at timestamptz, rejection_reason text, region_code text, dept_code text,
    population int, qualifier_buyer boolean, qualifier_reason text,
    emelia_segment_id text, emelia_contact_id text, email_score int,
    email_validation_reasons jsonb, mailnjoy_check jsonb);
CREATE INDEX IF NOT EXISTS scrappe_email ON scrappe (lower(email));
CREATE INDEX IF NOT EXISTS scrappe_site_created ON scrappe (site_code, created_at);

CREATE TABLE IF NOT EXISTS scrappe_rejected (
    email text PRIMARY KEY, decision text, reason text, site_code text,
    times_seen int DEFAULT 1, first_seen timestamptz DEFAULT now(),
    last_seen timestamptz DEFAULT now());

ALTER TABLE contacts ADD COLUMN IF NOT EXISTS entre_par_pg boolean NOT NULL DEFAULT false;
"""


def creer_schema() -> None:
    import pool_pg
    for stmt in [s.strip() for s in SCHEMA.split(";") if s.strip()]:
        pool_pg._ecrire(stmt, {})


# ── La règle d'état, côté PostgreSQL ─────────────────────────────────────────
# Traduction fidèle de `pg_gate.ETAT_SQL` (DuckDB). Les deux doivent rester alignées.
ETAT_PG = f"""
    CASE
        WHEN COALESCE(ct.global_blacklisted, false) THEN 'spam'
        WHEN ct.mailnjoy_decision IS NOT NULL AND ct.mailnjoy_decision <> 'valid' THEN 'ko'
        WHEN ct.sectors && ARRAY{SECTEURS_HORS_CIBLE}::text[] THEN 'exclu'
        WHEN EXISTS (SELECT 1 FROM contact_enrichment e
                      WHERE e.contact_id = ct.id AND e.excluded) THEN 'exclu'
        -- Rejetée sans verdict Mailnjoy (validateur, tombstone) : reste « ko » (07/10).
        WHEN ct.mailnjoy_decision IS NULL
         AND EXISTS (SELECT 1 FROM scrappe_rejected r WHERE r.email = lower(ct.email::text))
            THEN 'ko'
        WHEN ct.mailnjoy_decision IS NULL THEN 'a_verifier'
        WHEN ct.mailnjoy_checked_at < now() - interval '{CLEANED_WITHIN_DAYS} days' THEN 'a_verifier'
        ELSE 'ok'
    END"""


# ── File Mailnjoy (scrappe_pending) ──────────────────────────────────────────
_COLS_PENDING = ("id, site_code, company_name, contact_name, email, phone, sector, city, "
                 "postal_code, website, source, search_query, score, status, raw_data, "
                 "email_score, email_validation_reasons, region_code, dept_code")


def add_prospect_pending(site_code: str, data: dict, pid: str | None = None) -> str:
    pid = pid or str(uuid.uuid4())
    _ecrire(f"""INSERT INTO scrappe_pending ({_COLS_PENDING}) VALUES
        (%(id)s, %(site)s, %(cn)s, %(ct)s, %(em)s, %(ph)s, %(sec)s, %(city)s, %(cp)s,
         %(web)s, %(src)s, %(sq)s, %(score)s, %(st)s, %(raw)s::jsonb, %(es)s,
         %(evr)s::jsonb, %(reg)s, %(dep)s)
        ON CONFLICT (id) DO NOTHING""",
        {"id": pid, "site": site_code, "cn": data.get("company_name"),
         "ct": data.get("contact_name"), "em": data.get("email"), "ph": data.get("phone"),
         "sec": data.get("sector"), "city": data.get("city"), "cp": data.get("postal_code"),
         "web": data.get("website"), "src": data.get("source"),
         "sq": data.get("search_query"), "score": data.get("score", 0),
         "st": data.get("status", "pending_mailnjoy"), "raw": _j(data.get("raw_data", {})),
         "es": data.get("email_score"), "evr": _j(data.get("email_validation_reasons")),
         "reg": data.get("region_code"), "dep": data.get("dept_code")})
    return pid


def list_pending(site_code: str | None = None, limit: int = 500) -> list[dict]:
    cols = (_COLS_PENDING + ", created_at, mailnjoy_attempts, mailnjoy_last_error").split(", ")
    lignes = _q(f"""SELECT {', '.join(cols)} FROM scrappe_pending
                    WHERE mailnjoy_attempts < {MAILNJOY_MAX_ATTEMPTS}
                      AND (%(site)s::text IS NULL OR site_code = %(site)s)
                    ORDER BY mailnjoy_attempts ASC, created_at DESC LIMIT %(n)s""",
                {"site": site_code, "n": int(limit)})
    out = []
    for r in lignes:
        d = dict(zip(cols, r))
        d["created_at"] = str(d["created_at"]) if d.get("created_at") else None
        out.append(d)
    return out


def move_pending_to_scrappe(pending_id: str, mn_check: dict) -> str | None:
    import pool_pg
    new_id = str(uuid.uuid4())
    n = pool_pg._ecrire("""
        WITH p AS (DELETE FROM scrappe_pending WHERE id = %(pid)s RETURNING *)
        INSERT INTO scrappe (id, site_code, company_name, contact_name, email, phone, sector,
                             city, postal_code, website, source, search_query, score, status,
                             raw_data, email_score, email_validation_reasons, region_code,
                             dept_code, mailnjoy_check, validated_at)
        SELECT %(nid)s, site_code, company_name, contact_name, email, phone, sector, city,
               postal_code, website, source, search_query, score, 'mailnjoy_valid', raw_data,
               email_score, email_validation_reasons, region_code, dept_code,
               %(mn)s::jsonb, now()
          FROM p""", {"pid": pending_id, "nid": new_id, "mn": _j(mn_check)})
    return new_id if n else None


def delete_pending(pending_id: str) -> None:
    _ecrire("DELETE FROM scrappe_pending WHERE id = %(id)s", {"id": pending_id})


def bump_pending_error(pending_id: str, err: str) -> None:
    _ecrire("""UPDATE scrappe_pending SET mailnjoy_attempts = mailnjoy_attempts + 1,
                      mailnjoy_last_error = %(e)s WHERE id = %(id)s""",
            {"e": (err or "")[:500], "id": pending_id})


def count_chronic_pending(site_code: str | None = None) -> int:
    r = _q(f"""SELECT count(*) FROM scrappe_pending
               WHERE mailnjoy_attempts >= {MAILNJOY_MAX_ATTEMPTS}
                 AND (%(site)s::text IS NULL OR site_code = %(site)s)""", {"site": site_code})
    return int(r[0][0] or 0)


def retire_chronic_pending(site_code: str | None = None, age_days: int = CHRONIC_AGE_DAYS) -> dict:
    lignes = _q(f"""SELECT id, lower(email), site_code, mailnjoy_last_error FROM scrappe_pending
                    WHERE mailnjoy_attempts >= {MAILNJOY_MAX_ATTEMPTS}
                      AND created_at < now() - make_interval(days => %(d)s)
                      AND (%(site)s::text IS NULL OR site_code = %(site)s)""",
                {"d": int(age_days), "site": site_code})
    for pid, em, site, err in lignes:
        if em:
            _tombstone(em, "unverifiable",
                       f"unverifiable_mailnjoy_500 ({(err or 'http_500')[:60]})", site or "")
        delete_pending(pid)
    return {"retired": len(lignes), "emails": [e for _, e, _, _ in lignes if e]}


# ── Garde-fous de doublon ─────────────────────────────────────────────────────
def email_recently_validated(email: str, days: int = 30) -> bool:
    if not email:
        return False
    return bool(_q("""SELECT 1 FROM scrappe WHERE lower(email) = lower(%(e)s)
                        AND (mailnjoy_check->>'checked_at') >
                            to_char((now() - make_interval(days => %(d)s)) AT TIME ZONE 'UTC',
                                    'YYYY-MM-DD"T"HH24:MI:SS')
                      LIMIT 1""", {"e": email, "d": int(days)}))


def email_deja_en_base(email: str) -> bool:
    em = (email or "").strip().lower()
    return bool(em) and bool(_q("SELECT 1 FROM contacts WHERE email = %(e)s LIMIT 1", {"e": em}))


def email_in_pending(email: str) -> bool:
    return bool(email) and bool(_q(
        "SELECT 1 FROM scrappe_pending WHERE lower(email) = lower(%(e)s) LIMIT 1", {"e": email}))


def email_rejected(email: str) -> bool:
    return bool(email) and bool(_q(
        "SELECT 1 FROM scrappe_rejected WHERE email = %(e)s LIMIT 1",
        {"e": email.strip().lower()}))


def _tombstone(email: str, decision: str, reason: str, site_code: str) -> None:
    _ecrire("""INSERT INTO scrappe_rejected (email, decision, reason, site_code)
               VALUES (%(e)s, %(d)s, %(r)s, %(s)s)
               ON CONFLICT (email) DO UPDATE SET times_seen = scrappe_rejected.times_seen + 1,
                    last_seen = now(), decision = EXCLUDED.decision, reason = EXCLUDED.reason""",
            {"e": email.strip().lower(), "d": decision, "r": (reason or "")[:300],
             "s": site_code or ""})


def mark_email_rejected(email: str, decision: str, reason: str = "", site_code: str = "") -> None:
    if email:
        _tombstone(email, decision, reason, site_code)


# ── La fiche contact, directement dans PostgreSQL ─────────────────────────────
def creer_contact(p: dict, site_code: str, source: str) -> str | None:
    """Entre un contact scrappé dans `contacts` + `contact_sites`. Rend son id.

    Contact déjà connu : on ne complète QUE les champs vides et on ajoute le secteur —
    même règle que `contacts_pool_backend.create_in_pool`. L'état part « a_verifier »
    (Mailnjoy n'est pas encore passé) ; un contact existant garde le sien.
    """
    em = (p.get("email") or "").strip().lower()
    if not em:
        return None
    sectors = [s for s in (p.get("sectors") or []) if s]
    r = _ecrire_rendre("""
        INSERT INTO contacts (id, email, societe, tel, website, city, dept_code, region_code,
                              postal_code, sectors, primary_source, email_score,
                              email_validation_reasons, entre_par_pg, prenom, nom)
        VALUES (gen_random_uuid(), %(em)s, %(soc)s, %(tel)s, %(web)s, %(city)s, %(dep)s,
                %(reg)s, %(cp)s, %(sec)s::text[], %(src)s, %(es)s, %(evr)s::jsonb, true,
                %(prenom)s, %(nom)s)
        ON CONFLICT (email) DO UPDATE SET
            societe = COALESCE(contacts.societe, EXCLUDED.societe),
            tel = COALESCE(contacts.tel, EXCLUDED.tel),
            website = COALESCE(contacts.website, EXCLUDED.website),
            city = COALESCE(contacts.city, EXCLUDED.city),
            dept_code = COALESCE(contacts.dept_code, EXCLUDED.dept_code),
            region_code = COALESCE(contacts.region_code, EXCLUDED.region_code),
            postal_code = COALESCE(contacts.postal_code, EXCLUDED.postal_code),
            prenom = COALESCE(contacts.prenom, EXCLUDED.prenom),
            nom = COALESCE(contacts.nom, EXCLUDED.nom),
            sectors = (SELECT ARRAY(SELECT DISTINCT unnest(contacts.sectors || EXCLUDED.sectors)))
        RETURNING id::text""",
        {"em": em, "soc": p.get("societe"), "tel": p.get("tel"), "web": p.get("website"),
         "city": p.get("city"), "dep": p.get("dept_code"), "reg": p.get("region_code"),
         "cp": p.get("postal_code"), "sec": sectors, "src": source,
         "es": p.get("email_score"), "evr": _j(p.get("email_validation_reasons")),
         "prenom": p.get("prenom"), "nom": p.get("nom")})
    cid = r[0][0] if r else None
    if cid:
        _ecrire("""INSERT INTO contact_sites (id, contact_id, site_code, state, source,
                                              added_at, last_action_at, state_history)
                   VALUES (gen_random_uuid(), %(c)s::uuid, %(s)s, 'cold_email', %(src)s,
                           now(), now(), '[]'::jsonb)
                   ON CONFLICT (contact_id, site_code) DO NOTHING""",
                {"c": cid, "s": site_code, "src": source})
        recalculer_etat(em)
    return cid


def recalculer_etat(email: str) -> None:
    """Réapplique la règle d'état à une fiche (sans toucher `updated_at`, clé de pioche)."""
    _ecrire(f"""UPDATE contacts ct SET etat = {ETAT_PG}, etat_at = now()
                WHERE ct.email = %(e)s AND NOT ct.est_test
                  AND ct.etat IS DISTINCT FROM {ETAT_PG}""",
            {"e": (email or "").strip().lower()})


def appliquer_verdict(email: str, mn_check: dict) -> None:
    """Le verdict Mailnjoy atterrit sur la fiche PostgreSQL, et l'état suit."""
    em = (email or "").strip().lower()
    if not em or not mn_check:
        return
    _ecrire("""UPDATE contacts SET mailnjoy_decision = %(d)s,
                      mailnjoy_checked_at = %(at)s::timestamptz, mailnjoy_check = %(mn)s::jsonb
               WHERE email = %(e)s""",
            {"d": mn_check.get("decision"), "at": mn_check.get("checked_at"),
             "mn": _j(mn_check), "e": em})
    recalculer_etat(em)


# ── Adaptateur pour les lecteurs historiques ──────────────────────────────────
class ConnexionPG:
    """Se présente comme une connexion DuckDB (`execute(sql, [params])` puis `fetchone` /
    `fetchall`, `description`, `close`) et exécute dans PostgreSQL. Les lecteurs des tables
    scrappe* (écrans, stats) basculent ainsi en changeant UNE ligne. Les `?` deviennent `%s` ;
    le SQL utilisé par ces lecteurs (COUNT, FILTER, CAST AS DATE) est commun aux deux.
    Chaque `execute` valide sa transaction : un UPDATE passé par ici n'est jamais perdu."""

    def __init__(self):
        import pool_pg
        self._c = pool_pg._conn()
        self._cur = None
        self.description = None

    def execute(self, sql: str, params=None):
        self._cur = self._c.cursor()
        self._cur.execute(sql.replace("%", "%%").replace("?", "%s"), list(params or []))
        self.description = self._cur.description
        self._c.commit()
        return self

    @staticmethod
    def _texte(row):
        # DuckDB rendait les identifiants en texte ; psycopg2 rend des UUID, que les
        # appelants repasseraient ensuite en paramètre sans savoir les adapter.
        import uuid as _u
        return tuple(str(v) if isinstance(v, _u.UUID) else v for v in row) if row else row

    def fetchone(self):
        return self._texte(self._cur.fetchone()) if self._cur and self._cur.description else None

    def fetchall(self):
        return ([self._texte(r) for r in self._cur.fetchall()]
                if self._cur and self._cur.description else [])

    def close(self):
        import pool_pg
        try:
            self._c.rollback()
        finally:
            pool_pg._rendre(self._c)


def connexion():
    return ConnexionPG()


# ── Reprise de l'existant DuckDB (à la bascule) ───────────────────────────────
def copier_depuis_duckdb() -> dict:
    """Recopie les 3 tables de god_mode.duckdb dans PostgreSQL. Idempotent (ON CONFLICT)."""
    import psycopg2
    import psycopg2.extras
    import god_mode_backend as gm
    from duck_ouverture import ouvrir
    duck = ouvrir(gm.GOD_DB)
    bilan = {}
    try:
        dsn = [l.split("=", 1)[1].strip() for l in (BASE_DIR / ".env").read_text().splitlines()
               if l.startswith("PG_DSN=")][0]
        pg = psycopg2.connect(dsn)
        cur = pg.cursor()
        for table, cle, jsons in (("scrappe_pending", "id", ("raw_data", "email_validation_reasons")),
                                  ("scrappe", "id", ("raw_data", "email_validation_reasons",
                                                     "mailnjoy_check")),
                                  ("scrappe_rejected", "email", ())):
            rows = duck.execute(f"SELECT * FROM {table}").fetchall()
            cols = [d[0] for d in duck.description]
            data = []
            for r in rows:
                d = dict(zip(cols, r))
                for k in jsons:
                    d[k] = _j(d.get(k))
                data.append(tuple(d[c] for c in cols))
            psycopg2.extras.execute_values(
                cur, f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s "
                     f"ON CONFLICT ({cle}) DO NOTHING", data, page_size=1000)
            bilan[table] = len(data)
        pg.commit()
        pg.close()
    finally:
        duck.close()
    return bilan


def etat() -> dict:
    return {t: int(_q(f"SELECT count(*) FROM {t}")[0][0])
            for t in ("scrappe_pending", "scrappe", "scrappe_rejected")} | {
        "entres_par_pg": int(_q("SELECT count(*) FROM contacts WHERE entre_par_pg")[0][0]),
        "actif": actif()}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "etat"
    if cmd == "schema":
        creer_schema(); print(json.dumps(etat()))
    elif cmd == "copier":
        print(json.dumps(copier_depuis_duckdb()))
    else:
        print(json.dumps(etat()))
