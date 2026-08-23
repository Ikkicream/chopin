#!/usr/bin/env python3
"""
contacts_pool_backend.py — Backend pour le pool mutualisé Genesis.

Source de vérité : data/contacts.duckdb (cf. specs/contacts-model.md).

NB : ce module COEXISTE avec acquisition_backend.py legacy le temps de migrer.
À terme, acquisition_backend.py devient un shim qui appelle ce module.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).parent.parent
POOL_DB = BASE_DIR / "data" / "contacts.duckdb"

# RÈGLE ABSOLUE (décision user 2026-08-19) : dès qu'une personne a reçu UN email, elle est
# inscrite dans la base repoussoir (`email_suppression`) avec son flag à 0 et la date de
# l'envoi, et ne reçoit PLUS RIEN pendant 120 jours — tous sites et tous canaux confondus.
# Les cooldowns du pool sont alignés sur cette durée : ils sont la première barrière, la
# base repoussoir est la seconde (et fait foi, cf. `is_suppressed`).
#
# Historique : le cooldown même-site était à 7 jours. Résultat sur août 2026 : 1 189 envois
# pour 724 destinataires (39 % de redites), jusqu'à 98 renvois sur 100 le 15/08 — les
# contacts touchés début août redevenaient éligibles au bout d'une semaine et le tri les
# repêchait en priorité. Ne jamais redescendre sans décision utilisateur explicite.
SUPPRESSION_DAYS = 120
COOLDOWN_GLOBAL_DAYS = SUPPRESSION_DAYS
COOLDOWN_SAME_SITE_DAYS = SUPPRESSION_DAYS

# State ranking (un état "supérieur" ne peut pas être downgradé sauf blacklisted qui est terminal)
STATE_RANK = {
    "cold_email": 1,
    "prm":        2,
    "lead":       3,
    "crm":        4,
    "blacklisted": 99,  # terminal absolu
}


# Colonnes ajoutées après la création initiale de la table (migration idempotente).
# DuckDB ne garantit pas ADD COLUMN IF NOT EXISTS sur toutes les versions → on vérifie
# PRAGMA table_info avant chaque ALTER.
_EXTRA_COLS: dict[str, str] = {
    "job_title":    "VARCHAR",   # ← jobTitle (intitulé de poste libre)
    "civility":     "VARCHAR",   # ← civility (Monsieur / Madame)
    "job_function": "VARCHAR",   # ← function (rôle normalisé majuscules)
    # Origine du prénom : NULL / "saisi" quand il vient d'un import ou d'une saisie humaine,
    # "email:<forme>" quand il a été DÉDUIT de l'adresse (cf. name_extract). Sans cette
    # trace, impossible de distinguer une donnée vérifiée d'une déduction, ni de revenir
    # en arrière si la règle d'extraction se révèle fausse.
    "prenom_source": "VARCHAR",
}
_MIGRATED = False

# DDL de la table satellite d'enrichissement data.gouv — DOIT rester identique à
# ENRICHMENT_DDL dans scripts/datagouv_enrich.py (CREATE TABLE IF NOT EXISTS, donc
# le 1er des deux à s'exécuter crée le bon schéma).
_ENRICHMENT_DDL = """
CREATE TABLE IF NOT EXISTS contact_enrichment (
    contact_id               VARCHAR PRIMARY KEY,
    siret                    VARCHAR,
    siren                    VARCHAR,
    denomination             VARCHAR,
    nom_commercial           VARCHAR,
    sigle                    VARCHAR,
    code_naf                 VARCHAR,
    section_naf              VARCHAR,
    categorie_entreprise     VARCHAR,
    tranche_effectif_code    VARCHAR,
    tranche_effectif_libelle VARCHAR,
    code_postal              VARCHAR,
    commune                  VARCHAR,
    code_insee               VARCHAR,
    dept_code                VARCHAR,
    region_code              VARCHAR,
    latitude                 DOUBLE,
    longitude                DOUBLE,
    etat_administratif       VARCHAR,
    date_creation            DATE,
    date_fermeture           DATE,
    statut_diffusion         VARCHAR,
    est_rge                  BOOLEAN,
    est_qualiopi             BOOLEAN,
    est_ess                  BOOLEAN,
    est_bio                  BOOLEAN,
    est_societe_mission      BOOLEAN,
    match_quality            VARCHAR,
    excluded                 BOOLEAN,
    exclusion_reason         VARCHAR,
    enriched_at              TIMESTAMP,
    raw                      JSON
);
"""


# Base repoussoir : toute adresse ayant reçu un email y entre avec `contactable = 0` et la
# date de l'envoi. Table à part et non colonne de `contacts` : elle doit survivre à la
# suppression d'un contact du pool (sinon un re-scrape du même site le ferait réapparaître
# vierge le lendemain — c'est exactement ce qui produisait les boucles de renvoi).
SUPPRESSION_DDL = """
CREATE TABLE IF NOT EXISTS email_suppression (
    email        VARCHAR PRIMARY KEY,   -- normalisé (strip + lower)
    contactable  INTEGER NOT NULL,      -- le flag : 0 = ne rien envoyer
    last_sent_at TIMESTAMP,             -- date du dernier email reçu
    release_at   TIMESTAMP,             -- last_sent_at + SUPPRESSION_DAYS
    site_code    VARCHAR,
    campaign_id  VARCHAR,
    reason       VARCHAR,
    created_at   TIMESTAMP,
    updated_at   TIMESTAMP
)
"""


def _ensure_schema() -> None:
    """Ajoute les colonnes manquantes à `contacts`. Idempotent, 1×/process."""
    global _MIGRATED
    if _MIGRATED:
        return
    try:
        c = _connect_with_retry(read_only=False)
        try:
            existing = {r[1] for r in c.execute("PRAGMA table_info(contacts)").fetchall()}
            for col, typ in _EXTRA_COLS.items():
                if col not in existing:
                    c.execute(f"ALTER TABLE contacts ADD COLUMN {col} {typ}")
            # Table satellite d'enrichissement data.gouv (1:1 contacts), alimentée
            # par scripts/datagouv_enrich.py. DDL identique à ENRICHMENT_DDL du
            # script — on la garantit ici pour que le LEFT JOIN de pick_for_campaign
            # ne casse jamais sur une DB fraîche, avant le 1er enrichissement.
            c.execute(_ENRICHMENT_DDL)
            c.execute(SUPPRESSION_DDL)
            c.execute("CREATE INDEX IF NOT EXISTS idx_suppression_release "
                      "ON email_suppression(release_at)")
        finally:
            c.close()
        _MIGRATED = True
    except Exception:
        # Table pas encore créée (1er boot) ou course : on réessaiera au prochain appel.
        pass


def _connect_with_retry(read_only: bool = False, attempts: int = 8, sleep_s: float = 0.35):
    """DuckDB = 1 writer : pendant un autoscrape/cleanup, un connect concurrent lève
    « Could not set lock ». On réessaie brièvement (≈ jusqu'à 2.8 s) au lieu d'échouer
    sec — ce qui évite les « Chargement… » sur Vision/Acquisition pendant un scrape."""
    last = None
    for i in range(attempts):
        try:
            return duckdb.connect(str(POOL_DB), read_only=read_only)
        except Exception as e:  # noqa: BLE001
            last = e
            msg = str(e).lower()
            # Conflit de CONFIGURATION, à ne pas confondre avec le verrou : dans un même
            # process, DuckDB met l'instance en cache et refuse une seconde connexion qui
            # ne demande pas la même chose. Ce n'est pas une question de temps — réessayer
            # à l'identique échouera toujours. On bascule donc sur l'autre configuration :
            # c'est le même fichier, et l'instance déjà ouverte décide.
            if "different configuration" in msg:
                try:
                    return duckdb.connect(str(POOL_DB), read_only=not read_only)
                except Exception as e2:  # noqa: BLE001
                    last = e2
            if ("lock" in msg or "conflicting" in msg) and i < attempts - 1:
                time.sleep(sleep_s)
                continue
            raise
    raise last  # type: ignore


def _conn(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    _ensure_schema()
    return _connect_with_retry(read_only=read_only)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


# ── Bascule des lectures vers PostgreSQL (étape 4 de la migration) ───────────
# Piloté par PG_READS dans .env, pour revenir en arrière en une minute sans redéployer.
# Seules les lectures qui décident QUI reçoit un email sont basculées : une divergence s'y
# paie en renvois et en réputation. Les écritures continuent d'aller dans DuckDB (source de
# vérité) ET dans PostgreSQL (miroir `pg_sync`) jusqu'à l'étape 5.
# Équivalence prouvée sur les données réelles : tests/test_pg_equivalence.py.
_PG_READS: bool | None = None


def _pg_reads() -> bool:
    global _PG_READS
    if _PG_READS is None:
        val = ""
        try:
            for ligne in (BASE_DIR / ".env").read_text().splitlines():
                if ligne.startswith("PG_READS="):
                    val = ligne.split("=", 1)[1].strip()
        except Exception:
            val = ""
        _PG_READS = val == "1"
    return _PG_READS


def _pg():
    import pool_pg
    return pool_pg



def _miroir(fn, *a, **k) -> None:
    """Recopie best-effort vers PostgreSQL (étape 3 de la migration).

    Encapsulé ici pour que les fonctions d'écriture restent lisibles, et pour garantir
    qu'un incident PostgreSQL ne remonte JAMAIS dans le chemin DuckDB : à ce stade
    PostgreSQL est une copie, pas la source de vérité. Les échecs sont comptés et
    journalisés par `pg_sync`, ils ne sont pas avalés.
    """
    try:
        import pg_sync
        getattr(pg_sync, fn)(*a, **k)
    except Exception as e:  # noqa: BLE001
        print(f"[pool] miroir PostgreSQL indisponible ({fn}) : {type(e).__name__}: {e}",
              flush=True)



def _maybe_parse(v):
    if v is None or isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v) if isinstance(v, str) else v
    except Exception:
        return v


# ──────────────────────────────────────────────────────────────────────────────
# Contacts (table master)
# ──────────────────────────────────────────────────────────────────────────────
def find_by_email_global(email: str) -> dict | None:
    """Retourne le contact (sans historique site) ou None."""
    email = _normalize_email(email)
    if not email:
        return None
    c = _conn(read_only=True)
    try:
        cols = [r[1] for r in c.execute("PRAGMA table_info(contacts)").fetchall()]
        row = c.execute("SELECT * FROM contacts WHERE email = ?", [email]).fetchone()
    finally:
        c.close()
    if not row:
        return None
    d = dict(zip(cols, row))
    for k in ("sectors", "email_validation_reasons", "mailnjoy_check"):
        d[k] = _maybe_parse(d.get(k))
    return d


def create_in_pool(data: dict, primary_source: str | None = None,
                   conn: duckdb.DuckDBPyConnection | None = None) -> str | None:
    """Insère ou enrichit un contact dans le pool. Retourne contact_id (ou None si email invalide).

    Dédup par email : si le contact existe, on n'enrichit QUE les champs NULL/vides
    (jamais d'écrasement). `conn` permet de réutiliser une connexion (import en masse).
    """
    email = _normalize_email(data.get("email", ""))
    if not email or "@" not in email:
        return None

    # Prénom / nom déduits de l'adresse quand la source ne les fournit pas — c'est le cas de
    # TOUT le scraping, qui ne collecte que des données d'entreprise. Sept des dix modèles
    # d'email utilisent `{{prenom}}` : sans ça, les envois commencent par « Bonjour, ».
    # Ne remplit que le vide, et trace l'origine pour rester réversible.
    if not (data.get("prenom") or "").strip():
        try:
            import name_extract
            devine = name_extract.extraire(email)
            if devine["prenom"] or devine["nom"]:
                if devine["prenom"]:
                    data = {**data, "prenom": devine["prenom"]}
                if devine["nom"] and not (data.get("nom") or "").strip():
                    data = {**data, "nom": devine["nom"]}
                data = {**data, "prenom_source": f"email:{devine['forme']}"}
        except Exception as e:  # noqa: BLE001
            print(f"[pool] extraction du prénom indisponible : {type(e).__name__}: {e}",
                  flush=True)

    c = conn or _conn()
    own_conn = conn is None
    try:
        existing = c.execute("SELECT id FROM contacts WHERE email = ?", [email]).fetchone()
        if existing:
            cid = existing[0]
            # Update NULL-only : on lit toute la row une fois plutôt qu'un SELECT par colonne.
            scalar_cols = ("prenom", "nom", "societe", "tel", "website", "city",
                           "dept_code", "region_code", "postal_code", "email_score",
                           "primary_source", "job_title", "civility", "job_function")
            json_cols = ("sectors", "email_validation_reasons", "mailnjoy_check")
            all_cols = scalar_cols + json_cols
            cur_row = c.execute(
                f"SELECT {', '.join(all_cols)} FROM contacts WHERE id = ?", [cid]
            ).fetchone()
            cur = dict(zip(all_cols, cur_row)) if cur_row else {}
            updates, params = [], []
            for col in scalar_cols:
                v = data.get(col)
                if v is None or v == "":
                    continue
                if cur.get(col) is None or cur.get(col) == "":
                    updates.append(f"{col} = ?")
                    params.append(v)
            for col in json_cols:
                v = data.get(col)
                if v is None:
                    continue
                if cur.get(col) is None:
                    updates.append(f"{col} = ?")
                    params.append(json.dumps(v) if not isinstance(v, str) else v)
            if updates:
                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(cid)
                c.execute(f"UPDATE contacts SET {', '.join(updates)} WHERE id = ?", params)
            return cid

        # Insert new
        cid = str(uuid.uuid4())
        c.execute("""
            INSERT INTO contacts
            (id, email, prenom, nom, societe, tel, website, city, dept_code, region_code,
             postal_code, sectors, primary_source, email_score, email_validation_reasons,
             mailnjoy_check, job_title, civility, job_function, prenom_source,
             global_blacklisted, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, [
            cid, email, data.get("prenom"), data.get("nom"), data.get("societe"),
            data.get("tel"), data.get("website"), data.get("city"),
            data.get("dept_code"), data.get("region_code"), data.get("postal_code"),
            json.dumps(data.get("sectors")) if data.get("sectors") is not None else None,
            primary_source or data.get("primary_source") or "manual",
            data.get("email_score"),
            json.dumps(data.get("email_validation_reasons")) if data.get("email_validation_reasons") else None,
            json.dumps(data.get("mailnjoy_check")) if data.get("mailnjoy_check") else None,
            data.get("job_title"), data.get("civility"), data.get("job_function"),
            data.get("prenom_source"),
        ])
        # Promotion sous condition : un contact fraîchement scrapé n'est presque jamais
        # éligible (Mailnjoy et l'enrichissement n'ont pas encore tourné). L'appel n'est pas
        # inutile pour autant — un ré-import d'un contact déjà propre doit passer la porte.
        _miroir("promote_contact", cid)
        return cid
    finally:
        if own_conn:
            c.close()


def set_global_blacklist(email: str, reason: str = "") -> bool:
    """Marque un contact comme blacklisté globalement (UNSUBSCRIBE / BOUNCE depuis n'importe quel site)."""
    email = _normalize_email(email)
    if not email:
        return False
    c = _conn()
    try:
        c.execute("""
            UPDATE contacts SET global_blacklisted = TRUE,
                                blacklist_reason = ?,
                                blacklisted_at = CURRENT_TIMESTAMP
            WHERE email = ?
        """, [reason[:200], email])
        # Cascade : tous les contact_site_history → state='blacklisted'
        c.execute("""
            UPDATE contact_site_history
            SET state = 'blacklisted', last_action_at = CURRENT_TIMESTAMP
            WHERE contact_id = (SELECT id FROM contacts WHERE email = ?)
        """, [email])
    finally:
        c.close()
    _miroir("sync_blacklist", email, reason)
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Contact site history
# ──────────────────────────────────────────────────────────────────────────────
def get_history_for_site(contact_id: str, site_code: str) -> dict | None:
    c = _conn(read_only=True)
    try:
        cols = [r[1] for r in c.execute("PRAGMA table_info(contact_site_history)").fetchall()]
        row = c.execute(
            "SELECT * FROM contact_site_history WHERE contact_id = ? AND site_code = ?",
            [contact_id, site_code]
        ).fetchone()
    finally:
        c.close()
    if not row:
        return None
    d = dict(zip(cols, row))
    d["state_history"] = _maybe_parse(d.get("state_history"))
    return d


def upsert_site_history(contact_id: str, site_code: str, state: str = "cold_email",
                        source: str = "manual", account_id: str | None = None,
                        by: str = "system", note: str = "",
                        conn: duckdb.DuckDBPyConnection | None = None) -> str:
    """Crée ou met à jour la row contact_site_history (contact_id, site_code).

    `conn` permet de réutiliser une connexion (import en masse)."""
    c = conn or _conn()
    own_conn = conn is None
    try:
        existing = c.execute(
            "SELECT id, state, state_history FROM contact_site_history WHERE contact_id = ? AND site_code = ?",
            [contact_id, site_code]
        ).fetchone()
        if existing:
            hid, current_state, sh_raw = existing
            # State transition (only upgrade, never downgrade except blacklisted)
            if STATE_RANK.get(state, 0) > STATE_RANK.get(current_state, 0) or state == "blacklisted":
                history = _maybe_parse(sh_raw) or []
                history.append({"state": state, "date": _now().isoformat(), "by": by, "note": note})
                c.execute("""
                    UPDATE contact_site_history
                    SET state = ?, state_history = ?, last_action_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, [state, json.dumps(history), hid])
            return hid

        hid = str(uuid.uuid4())
        history = [{"state": state, "date": _now().isoformat(), "by": by, "note": note}]
        c.execute("""
            INSERT INTO contact_site_history
            (id, contact_id, site_code, account_id, state, source,
             added_to_site_at, state_history, last_action_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, CURRENT_TIMESTAMP)
        """, [hid, contact_id, site_code, account_id, state, source, json.dumps(history)])
        _miroir("promote_contact", contact_id)
    finally:
        if own_conn:
            c.close()
    return hid


def change_state_for_site(contact_id: str, site_code: str, new_state: str,
                          by: str = "system", note: str = "") -> bool:
    """Update state in contact_site_history (avec règle STATE_RANK).
    Si la row n'existe pas, on la crée."""
    if not contact_id or not site_code:
        return False
    existing = get_history_for_site(contact_id, site_code)
    if not existing:
        upsert_site_history(contact_id, site_code, state=new_state, by=by, note=note)
        return True

    current = existing.get("state")
    if current == "blacklisted":
        return False  # terminal
    if STATE_RANK.get(new_state, 0) <= STATE_RANK.get(current, 0) and new_state != "blacklisted":
        return False  # downgrade refused

    c = _conn()
    try:
        history = existing.get("state_history") or []
        history.append({"state": new_state, "date": _now().isoformat(), "by": by, "note": note})
        c.execute("""
            UPDATE contact_site_history
            SET state = ?, state_history = ?, last_action_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, [new_state, json.dumps(history), existing["id"]])
    finally:
        c.close()
    _miroir("promote_contact", contact_id)
    return True


# ── Base repoussoir ────────────────────────────────────────────────────────────
# Clause SQL partagée par toutes les pioches. `NOT EXISTS` et non `NOT IN` : `NOT IN` sur
# une sous-requête contenant un NULL vaut NULL, donc écarte TOUTE la table (même piège que
# le COALESCE des exclusions de segment, cf. `segment_clause`).
SUPPRESSION_CLAUSE_SQL = f"""
            AND NOT EXISTS (
                SELECT 1 FROM email_suppression sup
                WHERE sup.email = lower(c.email)
                  AND sup.contactable = 0
                  AND sup.last_sent_at > CURRENT_TIMESTAMP - INTERVAL '{SUPPRESSION_DAYS}' DAY
            )"""


def suppress(email: str, site_code: str = "", campaign_id: str = "",
             sent_at: datetime | None = None, reason: str = "email envoyé") -> None:
    """Inscrit une adresse dans la base repoussoir : flag à 0 + date de l'envoi.

    Appelé à CHAQUE envoi réussi. Idempotent : un nouvel envoi repousse la date de
    libération de `SUPPRESSION_DAYS` jours à partir du dernier email reçu.
    """
    em = _normalize_email(email)
    if not em:
        return
    at = sent_at or _now()
    release = at + timedelta(days=SUPPRESSION_DAYS)
    c = _conn()
    try:
        _suppress_conn(c, em, site_code, campaign_id, at, release, reason)
    finally:
        c.close()


def _suppress_conn(c, em: str, site_code: str, campaign_id: str,
                   at: datetime, release: datetime, reason: str) -> None:
    """Écriture de la base repoussoir sur une connexion existante (imports en masse)."""
    row = c.execute("SELECT last_sent_at FROM email_suppression WHERE email = ?",
                    [em]).fetchone()
    if row:
        # On ne recule jamais la date de libération : le dernier envoi fait foi.
        c.execute("""UPDATE email_suppression
                     SET contactable = 0,
                         last_sent_at = GREATEST(COALESCE(last_sent_at, ?), ?),
                         release_at = GREATEST(COALESCE(release_at, ?), ?),
                         site_code = COALESCE(NULLIF(?, ''), site_code),
                         campaign_id = COALESCE(NULLIF(?, ''), campaign_id),
                         reason = ?, updated_at = CURRENT_TIMESTAMP
                     WHERE email = ?""",
                  [at, at, release, release, site_code, campaign_id, reason, em])
    else:
        c.execute("""INSERT INTO email_suppression
                     (email, contactable, last_sent_at, release_at, site_code,
                      campaign_id, reason, created_at, updated_at)
                     VALUES (?, 0, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                  [em, at, release, site_code, campaign_id, reason])


def is_suppressed(email: str) -> bool:
    """True si l'adresse a reçu un email il y a moins de SUPPRESSION_DAYS jours."""
    if _pg_reads():
        return _pg().is_suppressed(email)
    em = _normalize_email(email)
    if not em:
        return False
    c = _conn(read_only=True)
    try:
        row = c.execute(
            f"""SELECT 1 FROM email_suppression
                WHERE email = ? AND contactable = 0
                  AND last_sent_at > CURRENT_TIMESTAMP - INTERVAL '{SUPPRESSION_DAYS}' DAY""",
            [em]).fetchone()
    finally:
        c.close()
    return bool(row)


def filter_suppressed(emails: list[str]) -> set[str]:
    """Sous-ensemble des adresses actuellement bloquées (une seule requête pour un lot)."""
    if _pg_reads():
        return _pg().filter_suppressed(emails)
    ems = [_normalize_email(e) for e in emails if e]
    if not ems:
        return set()
    c = _conn(read_only=True)
    try:
        c.execute("CREATE TEMP TABLE IF NOT EXISTS _sup_probe(email VARCHAR)")
        c.execute("DELETE FROM _sup_probe")
        c.executemany("INSERT INTO _sup_probe VALUES (?)", [(e,) for e in ems])
        rows = c.execute(
            f"""SELECT p.email FROM _sup_probe p
                JOIN email_suppression s ON s.email = p.email
                WHERE s.contactable = 0
                  AND s.last_sent_at > CURRENT_TIMESTAMP - INTERVAL '{SUPPRESSION_DAYS}' DAY"""
        ).fetchall()
    finally:
        c.close()
    return {r[0] for r in rows}


def release_expired() -> int:
    """Repasse le flag à 1 pour les adresses sorties des SUPPRESSION_DAYS jours.

    Hygiène/lisibilité seulement : les requêtes de pioche filtrent déjà sur `last_sent_at`,
    la libération est donc automatique même si personne n'appelle cette fonction.
    """
    c = _conn()
    try:
        n = c.execute(
            f"""SELECT COUNT(*) FROM email_suppression
                WHERE contactable = 0
                  AND last_sent_at <= CURRENT_TIMESTAMP - INTERVAL '{SUPPRESSION_DAYS}' DAY"""
        ).fetchone()[0]
        if n:
            c.execute(
                f"""UPDATE email_suppression SET contactable = 1,
                       updated_at = CURRENT_TIMESTAMP
                    WHERE contactable = 0
                      AND last_sent_at <= CURRENT_TIMESTAMP - INTERVAL '{SUPPRESSION_DAYS}' DAY""")
    finally:
        c.close()
    return int(n or 0)


def suppression_stats() -> dict:
    """Compteurs de la base repoussoir pour l'UI/monitoring."""
    if _pg_reads():
        return _pg().suppression_stats()
    c = _conn(read_only=True)
    try:
        row = c.execute(
            f"""SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE contactable = 0
                           AND last_sent_at > CURRENT_TIMESTAMP - INTERVAL '{SUPPRESSION_DAYS}' DAY),
                       MIN(release_at), MAX(release_at)
                FROM email_suppression""").fetchone()
    finally:
        c.close()
    return {"total": int(row[0] or 0), "bloques": int(row[1] or 0),
            "prochaine_liberation": str(row[2]) if row[2] else None,
            "derniere_liberation": str(row[3]) if row[3] else None,
            "jours": SUPPRESSION_DAYS}


def mark_pushed_to_emelia(contact_id: str, site_code: str, campaign_id: str,
                          emelia_contact_id: str = "", email: str | None = None) -> None:
    """Appelé après push réussi : enregistre campaign + last_contacted.

    UPSERT et non simple UPDATE. Un contact sans ligne `contact_site_history` pour ce site
    (14 cas constatés le 19/08/2026 : contacts créés sans rattachement) déclenchait un
    UPDATE à zéro ligne, en silence — aucun cooldown n'était posé, donc la pioche du
    lendemain le reprenait, et ainsi de suite : quatre adresses ont reçu 11 à 17 fois le
    même email en août. On crée la ligne manquante avant de marquer, puis on VÉRIFIE que
    le cooldown est bien posé : un marquage muet est le pire des échecs ici, il se paie en
    réputation d'expéditeur.

    `email` (facultatif) : quand l'appelant connaît déjà l'adresse, le journal PostgreSQL
    est écrit AVANT d'ouvrir DuckDB. Motif, constaté le 2026-08-20 : un scrape tenait
    `contacts.duckdb`, `_conn()` a fini par lever, et l'événement d'envoi n'a jamais été
    journalisé — l'email était parti mais l'adresse restait renvoyable, faute de ligne dans
    `v_suppression`. Depuis la bascule c'est ce journal qui PORTE la fenêtre de 120 jours :
    il ne doit plus dépendre de la disponibilité d'un fichier DuckDB. Le cooldown du pool
    reste posé juste après, mais il n'est plus le seul rempart.
    """
    journalise = False
    if email:
        _miroir("record_send", _normalize_email(email), site_code,
                contact_id=contact_id, campaign_id=campaign_id)
        journalise = True
    c = _conn()
    try:
        exists = c.execute(
            "SELECT 1 FROM contact_site_history WHERE contact_id = ? AND site_code = ?",
            [contact_id, site_code]).fetchone()
        if not exists:
            upsert_site_history(contact_id, site_code, state="cold_email",
                                source="campaign", by="campaign_engine",
                                note=f"ligne créée au marquage d'envoi ({campaign_id})",
                                conn=c)
        c.execute("""
            UPDATE contact_site_history
            SET emelia_campaign_id = ?, emelia_contact_id = ?,
                email_sent_at = CURRENT_TIMESTAMP,
                last_contacted_by_site_at = CURRENT_TIMESTAMP,
                last_action_at = CURRENT_TIMESTAMP
            WHERE contact_id = ? AND site_code = ?
        """, [campaign_id, emelia_contact_id or "pushed", contact_id, site_code])
        ok = c.execute(
            "SELECT COUNT(*) FROM contact_site_history "
            "WHERE contact_id = ? AND site_code = ? AND last_contacted_by_site_at IS NOT NULL",
            [contact_id, site_code]).fetchone()
        if not ok or not ok[0]:
            raise RuntimeError(
                f"cooldown non posé pour {contact_id}/{site_code} — risque de renvoi")
        # Base repoussoir : l'adresse sort du circuit pour SUPPRESSION_DAYS jours. On la
        # pose sur la MÊME connexion que le marquage, donc dans la même transaction : un
        # contact marqué comme contacté sans être repoussé serait renvoyable.
        row = c.execute("SELECT email FROM contacts WHERE id = ?", [contact_id]).fetchone()
        if row and row[0]:
            at = _now()
            _suppress_conn(c, _normalize_email(row[0]), site_code, campaign_id,
                           at, at + timedelta(days=SUPPRESSION_DAYS), "email envoyé")
    finally:
        c.close()
    # Journal PostgreSQL : c'est CET événement qui alimente `v_suppression`, donc la
    # fenêtre de 120 jours après la bascule. Le manquer rouvrirait la porte aux renvois.
    if row and row[0] and not journalise:
        _miroir("record_send", _normalize_email(row[0]), site_code,
                contact_id=contact_id, campaign_id=campaign_id)


def record_emelia_event(contact_id: str, site_code: str, event_type: str,
                        event_date: datetime | None = None) -> None:
    """Appelé par le webhook handler après réception d'un event SENT/OPENED/CLICKED/REPLIED/BOUNCED/UNSUBSCRIBED."""
    col_map = {
        "SENT":         "email_sent_at",
        "OPENED":       "emelia_opened_at",
        "CLICKED":      "emelia_clicked_at",
        "REPLIED":      "emelia_replied_at",
        "BOUNCED":      "emelia_bounced_at",
        "UNSUBSCRIBED": "emelia_unsubscribed_at",
    }
    col = col_map.get(event_type.upper())
    if not col:
        return
    ts = event_date or _now()
    c = _conn()
    try:
        c.execute(f"""
            UPDATE contact_site_history
            SET {col} = ?, last_action_at = CURRENT_TIMESTAMP
            WHERE contact_id = ? AND site_code = ?
        """, [ts, contact_id, site_code])
    finally:
        c.close()


# ──────────────────────────────────────────────────────────────────────────────
# Liste / search / stats
# ──────────────────────────────────────────────────────────────────────────────
# ── Étape d'un contact dans la chaîne de traitement ──────────────────────────
# Les écrans montraient l'état COMMERCIAL (cold_email, lead, PRM, client) en l'appelant
# « état ». Ce n'est pas la question qu'on se pose devant une liste de contacts fraîchement
# collectés : on veut savoir où ils en sont de la CHAÎNE — scrapé, vérifié, enrichi,
# contactable. Deux axes différents, qu'on affiche désormais séparément.
#
# L'étape est calculée ici, à un seul endroit, à partir de ce que les scripts écrivent
# réellement : `mailnjoy_check` (nettoyage des adresses), `contact_enrichment` (SIRET
# data.gouv), `email_suppression` (repos de 120 jours), `global_blacklisted`. La règle est
# une cascade : la première condition bloquante gagne.

ETAPES = {
    "blacklisted": {"label": "Blacklisté",
                    "aide": "Désinscrit, plainte ou rebond dur — ne sera jamais recontacté."},
    "ecarte":      {"label": "Écarté",
                    "aide": "Adresse invalide ou risquée, ou entreprise fermée / administration."},
    "repos":       {"label": "En repos",
                    "aide": "A reçu un email il y a moins de 120 jours — intouchable jusque-là."},
    "a_verifier":  {"label": "À vérifier",
                    "aide": "Collecté, mais l'adresse n'est pas encore passée chez Mailnjoy."},
    "verifie":     {"label": "Vérifié",
                    "aide": "Adresse valide. Société non retrouvée au SIRET : contactable quand même."},
    "pret":        {"label": "Prêt",
                    "aide": "Adresse valide et société retrouvée (SIRET/NAF) : peut entrer en campagne."},
}


# La cascade est écrite UNE FOIS, en SQL. Elle était en Python : impossible de filtrer ou
# de compter par étape sans ramener toute la base, et une seconde écriture en SQL aurait
# fini par diverger de la première. Ici, la même expression sert à afficher l'étape, à
# filtrer dessus et à la compter.
#
# `_ETAPE_SQL` suppose les jointures posées par `_filtre_contacts` : `e` (enrichissement
# data.gouv) et `sup` (repos de 120 jours).
_ETAPE_SQL = """
CASE
    WHEN COALESCE(c.global_blacklisted, FALSE) THEN 'blacklisted'
    WHEN json_extract_string(c.mailnjoy_check, '$.decision') IS NOT NULL
     AND json_extract_string(c.mailnjoy_check, '$.decision') <> 'valid' THEN 'ecarte'
    WHEN COALESCE(e.excluded, FALSE) THEN 'ecarte'
    WHEN sup.email IS NOT NULL THEN 'repos'
    WHEN json_extract_string(c.mailnjoy_check, '$.decision') IS NULL THEN 'a_verifier'
    WHEN e.siret IS NOT NULL THEN 'pret'
    ELSE 'verifie'
END
"""


def _filtre_contacts(site_code: str, state, sectors_in, source, search_email, engagement,
                    etape=None):
    """Le FROM/WHERE commun à la liste et au comptage.

    Écrit une fois : deux clauses séparées finissent par diverger, et la pagination
    annonce alors un nombre de pages qui ne correspond pas à ce qu'on voit.
    """
    q = """
        FROM contacts c
        JOIN contact_site_history csh ON c.id = csh.contact_id
        LEFT JOIN contact_enrichment e ON e.contact_id = c.id
        LEFT JOIN email_suppression sup
               ON sup.email = lower(c.email) AND sup.release_at > CURRENT_TIMESTAMP
        WHERE csh.site_code = ?
    """
    params: list = [site_code]
    if engagement == "openers":
        q += " AND csh.last_opened_at IS NOT NULL"
    elif engagement == "clickers":
        q += " AND csh.last_clicked_at IS NOT NULL"
    if state:
        q += f" AND csh.state IN ({','.join(['?'] * len(state))})"
        params.extend(state)
    if source:
        q += f" AND csh.source IN ({','.join(['?'] * len(source))})"
        params.extend(source)
    if search_email:
        # La recherche portait sur la seule adresse alors que le champ dit « email, nom,
        # prénom, société » : elle ne trouvait rien par société.
        q += " AND (lower(c.email) LIKE ? OR lower(COALESCE(c.societe,'')) LIKE ?"
        q += " OR lower(COALESCE(c.nom,'')) LIKE ? OR lower(COALESCE(c.prenom,'')) LIKE ?"
        q += " OR COALESCE(c.tel,'') LIKE ?)"
        motif = f"%{search_email.lower()}%"
        params.extend([motif, motif, motif, motif, f"%{search_email}%"])
    if sectors_in:
        sub = " OR ".join(["c.sectors::VARCHAR LIKE ?"] * len(sectors_in))
        q += f" AND ({sub})"
        for x in sectors_in:
            params.append(f"%{x}%")
    if etape:
        etapes = [x for x in (etape if isinstance(etape, (list, tuple)) else [etape]) if x]
        if etapes:
            q += f" AND ({_ETAPE_SQL}) IN ({','.join(['?'] * len(etapes))})"
            params.extend(etapes)
    return q, params


def count_contacts_for_site(site_code: str, state: list[str] | None = None,
                            sectors_in: list[str] | None = None,
                            source: list[str] | None = None,
                            search_email: str | None = None,
                            engagement: str | None = None,
                            etape: list[str] | None = None) -> int:
    """Nombre total de contacts correspondant aux filtres — pour la pagination."""
    q, params = _filtre_contacts(site_code, state, sectors_in, source, search_email,
                                 engagement, etape)
    c = _conn(read_only=True)
    try:
        return int(c.execute("SELECT count(*) " + q, params).fetchone()[0] or 0)
    finally:
        c.close()


def compter_par_etape(site_code: str, state=None, sectors_in=None, source=None,
                      search_email=None, engagement=None) -> dict:
    """Combien de contacts à chaque étape, pour les filtres en cours.

    Sert l'onglet de filtrage ET la page Vision : un compteur affiché à côté d'un filtre
    doit venir de la même requête que le filtre, sinon les deux se contredisent.
    """
    q, params = _filtre_contacts(site_code, state, sectors_in, source, search_email,
                                 engagement, None)
    c = _conn(read_only=True)
    try:
        rows = c.execute(f"SELECT ({_ETAPE_SQL}) AS etape, count(*) {q} GROUP BY 1", params).fetchall()
    finally:
        c.close()
    return {cle: 0 for cle in ETAPES} | {r[0]: int(r[1]) for r in rows}


def vision_contacts(site_code: str, secteurs_max: int = 8) -> dict:
    """Tout ce qu'il faut savoir de la base de contacts d'un site, en une requête par angle.

    Quatre questions, et elles ne se répondent pas l'une l'autre :
      - où en sont les contacts dans la chaîne de traitement (étapes) ;
      - combien ont une société retrouvée au SIRET (enrichissement) ;
      - combien ont ouvert, cliqué (engagement) ;
      - comment ils se répartissent par secteur (le donut).
    """
    depuis, params = _filtre_contacts(site_code, None, None, None, None, None, None)
    c = _conn(read_only=True)
    try:
        total = int(c.execute("SELECT count(*) " + depuis, params).fetchone()[0] or 0)
        etapes = {r[0]: int(r[1]) for r in c.execute(
            f"SELECT ({_ETAPE_SQL}) AS etape, count(*) {depuis} GROUP BY 1", params).fetchall()}

        # Enrichissement : trois issues possibles, plus « pas encore passé ».
        enrichi, non_trouve, exclu = c.execute(f"""
            SELECT count(*) FILTER (WHERE e.siret IS NOT NULL),
                   count(*) FILTER (WHERE e.contact_id IS NOT NULL AND e.siret IS NULL
                                      AND NOT COALESCE(e.excluded, FALSE)),
                   count(*) FILTER (WHERE COALESCE(e.excluded, FALSE))
            {depuis}""", params).fetchone()

        # Engagement : des PERSONNES, une seule fois chacune (le pool ne garde que le
        # dernier événement par contact).
        ouvreurs, cliqueurs, contactes = c.execute(f"""
            SELECT count(*) FILTER (WHERE csh.last_opened_at IS NOT NULL),
                   count(*) FILTER (WHERE csh.last_clicked_at IS NOT NULL),
                   count(*) FILTER (WHERE csh.email_sent_at IS NOT NULL
                                       OR csh.last_contacted_by_site_at IS NOT NULL)
            {depuis}""", params).fetchone()

        # Requête à part : DuckDB refuse un UNNEST combiné aux jointures externes de
        # `_filtre_contacts` (« non-inner join on correlated columns »). Les secteurs
        # n'ont besoin ni de l'enrichissement ni du repos, la jointure minimale suffit.
        secteurs = c.execute("""
            SELECT TRIM(sv.value) AS secteur, count(*) AS n
            FROM contacts c
            JOIN contact_site_history csh ON csh.contact_id = c.id,
                 UNNEST(CAST(c.sectors AS VARCHAR[])) AS sv(value)
            WHERE csh.site_code = ? AND c.sectors IS NOT NULL
            GROUP BY 1 HAVING TRIM(sv.value) <> '' ORDER BY n DESC""",
            [site_code]).fetchall()
    finally:
        c.close()

    liste = [{"secteur": r[0], "n": int(r[1])} for r in secteurs]
    tete, reste = liste[:secteurs_max], liste[secteurs_max:]
    if reste:
        tete.append({"secteur": "Autres", "n": sum(x["n"] for x in reste),
                     "detail": len(reste)})

    return {
        "site": site_code,
        "total": total,
        "etapes": {cle: etapes.get(cle, 0) for cle in ETAPES},
        "etapes_libelles": ETAPES,
        "enrichissement": {
            "siret_trouve": int(enrichi or 0),
            "siret_non_trouve": int(non_trouve or 0),
            "exclus": int(exclu or 0),
            "jamais_traite": max(0, total - int(enrichi or 0) - int(non_trouve or 0) - int(exclu or 0)),
        },
        "engagement": {
            "contactes": int(contactes or 0),
            "ouvreurs": int(ouvreurs or 0),
            "cliqueurs": int(cliqueurs or 0),
        },
        "secteurs": tete,
    }


def list_contacts_for_site(site_code: str, state: list[str] | None = None,
                           sectors_in: list[str] | None = None,
                           source: list[str] | None = None,
                           search_email: str | None = None,
                           engagement: str | None = None,
                           etape: list[str] | None = None,
                           limit: int = 500, offset: int = 0) -> list[dict]:
    """Liste les contacts utilisés par un site (JOIN contacts × contact_site_history)."""
    depuis, params = _filtre_contacts(site_code, state, sectors_in, source, search_email,
                                      engagement, etape)
    q = """
        SELECT c.id, c.email, c.prenom, c.nom, c.societe, c.tel, c.website,
               c.city, c.dept_code, c.region_code,
               c.logo_url, c.client_since,
               c.sectors, c.primary_source, c.email_score, c.global_blacklisted,
               csh.state, csh.source, csh.added_to_site_at,
               csh.state_history, csh.last_action_at,
               csh.emelia_campaign_id, csh.emelia_contact_id,
               csh.email_sent_at, csh.emelia_opened_at, csh.emelia_clicked_at,
               csh.emelia_replied_at, csh.emelia_bounced_at, csh.emelia_unsubscribed_at,
               csh.last_contacted_by_site_at, csh.notes,
               csh.last_opened_at, csh.last_clicked_at,
               csh.last_open_channel, csh.last_click_channel,
               c.mailnjoy_check, e.siret, e.match_quality, e.excluded, e.exclusion_reason,
               sup.release_at, """ + _ETAPE_SQL + """ AS etape
    """ + depuis
    q += " ORDER BY csh.last_action_at DESC NULLS LAST LIMIT ? OFFSET ?"
    params = list(params) + [limit, offset]

    c = _conn(read_only=True)
    try:
        rows = c.execute(q, params).fetchall()
    finally:
        c.close()

    cols = [
        "id", "email", "prenom", "nom", "societe", "tel", "website",
        "city", "dept_code", "region_code",
        "logo_url", "client_since",
        "sectors", "primary_source", "email_score", "global_blacklisted",
        "state", "source", "added_to_site_at",
        "state_history", "last_action_at",
        "emelia_campaign_id", "emelia_contact_id",
        "email_sent_at", "emelia_opened_at", "emelia_clicked_at",
        "emelia_replied_at", "emelia_bounced_at", "emelia_unsubscribed_at",
        "last_contacted_by_site_at", "notes",
        "last_opened_at", "last_clicked_at",
        "last_open_channel", "last_click_channel",
        "mailnjoy_check", "siret", "match_quality", "enrichissement_exclu",
        "enrichissement_motif", "en_repos_jusquau", "etape",
    ]
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        d["sectors"] = _maybe_parse(d.get("sectors"))
        d["state_history"] = _maybe_parse(d.get("state_history"))
        d["mailnjoy_check"] = _maybe_parse(d.get("mailnjoy_check"))
        if d.get("en_repos_jusquau"):
            d["en_repos_jusquau"] = str(d["en_repos_jusquau"])
        d["etape_label"] = ETAPES.get(d.get("etape") or "", {}).get("label", "—")
        for ts_col in ("added_to_site_at", "last_action_at", "email_sent_at",
                       "emelia_opened_at", "emelia_clicked_at", "emelia_replied_at",
                       "emelia_bounced_at", "emelia_unsubscribed_at",
                       "last_contacted_by_site_at", "last_opened_at", "last_clicked_at"):
            if d.get(ts_col):
                d[ts_col] = str(d[ts_col])
        out.append(d)
    return out


def engagement_par_canal(site_code: str) -> dict:
    """Ouvreurs et cliqueurs UNIQUES par canal de routage, pour ce site.

    Le suivi Maildoso passait pour inexistant (« pas de tracking en SMTP ») alors que le
    pixel `/api/track/open` et la redirection de clic écrivent bien dans le pool, avec le
    canal. 348 ouvreurs et 58 cliqueurs Maildoso étaient donc comptés nulle part.

    Limite assumée, la même que partout ailleurs sur ces colonnes : le pool ne retient que
    la DERNIÈRE ouverture par contact. On compte donc des PERSONNES ayant ouvert, pas un
    nombre d'ouvertures — c'est ce que `email_events` corrigera après la migration.
    """
    c = _conn(read_only=True)
    try:
        ouvertures = c.execute(
            "SELECT COALESCE(last_open_channel, 'inconnu'), count(*) "
            "FROM contact_site_history "
            "WHERE site_code = ? AND last_opened_at IS NOT NULL GROUP BY 1",
            [site_code]).fetchall()
        clics = c.execute(
            "SELECT COALESCE(last_click_channel, 'inconnu'), count(*) "
            "FROM contact_site_history "
            "WHERE site_code = ? AND last_clicked_at IS NOT NULL GROUP BY 1",
            [site_code]).fetchall()
    finally:
        c.close()
    out: dict[str, dict] = {}
    for canal, n in ouvertures:
        out.setdefault(canal, {"ouvreurs": 0, "cliqueurs": 0})["ouvreurs"] = int(n)
    for canal, n in clics:
        out.setdefault(canal, {"ouvreurs": 0, "cliqueurs": 0})["cliqueurs"] = int(n)
    return out


def filter_values_for_site(site_code: str) -> dict:
    """Valeurs distinctes (secteur, source) AVEC compteurs pour les filtres Acquisition.
    Scopé aux contacts du funnel de ce site (JOIN contact_site_history)."""
    c = _conn(read_only=True)
    try:
        secs = c.execute(
            "SELECT TRIM(sv.value) AS sec, COUNT(*) AS n "
            "FROM contacts c JOIN contact_site_history csh ON c.id = csh.contact_id, "
            "     UNNEST(CAST(c.sectors AS VARCHAR[])) AS sv(value) "
            "WHERE csh.site_code = ? AND c.sectors IS NOT NULL "
            "GROUP BY 1 HAVING TRIM(sv.value) <> '' ORDER BY n DESC",
            [site_code]).fetchall()
        srcs = c.execute(
            "SELECT COALESCE(NULLIF(TRIM(csh.source), ''), '?') AS src, COUNT(*) AS n "
            "FROM contacts c JOIN contact_site_history csh ON c.id = csh.contact_id "
            "WHERE csh.site_code = ? GROUP BY 1 ORDER BY n DESC",
            [site_code]).fetchall()
    finally:
        c.close()
    return {
        "sectors": [{"value": r[0], "count": int(r[1])} for r in secs],
        "sources": [{"value": r[0], "count": int(r[1])} for r in srcs],
    }


def stats_for_site(site_code: str) -> dict:
    """Stats du site. On NE compte QUE les lignes d'historique rattachées à un contact
    réellement existant (JOIN), par EMAIL distinct : sinon les historiques orphelins
    (contacts supprimés par le nettoyage Mailnjoy) gonflent le « Tous » affiché."""
    c = _conn(read_only=True)
    try:
        total = c.execute(
            "SELECT COUNT(DISTINCT c.email) FROM contact_site_history csh "
            "JOIN contacts c ON c.id = csh.contact_id WHERE csh.site_code = ?",
            [site_code]
        ).fetchone()[0]
        by_state = dict(c.execute(
            "SELECT csh.state, COUNT(DISTINCT c.email) FROM contact_site_history csh "
            "JOIN contacts c ON c.id = csh.contact_id WHERE csh.site_code = ? GROUP BY csh.state",
            [site_code]
        ).fetchall())
        by_source = dict(c.execute(
            "SELECT csh.source, COUNT(DISTINCT c.email) FROM contact_site_history csh "
            "JOIN contacts c ON c.id = csh.contact_id WHERE csh.site_code = ? GROUP BY csh.source",
            [site_code]
        ).fetchall())
    finally:
        c.close()
    return {"total": total, "by_state": by_state, "by_source": by_source}


def enrichment_stats() -> dict:
    """Stats globales d'enrichissement data.gouv (table contact_enrichment).

    Univers enrichissable = contacts avec une `societe`. La table contient 1 row
    par contact traité ; `remaining` = contacts pas encore traités (anti-join).
    `excluded`=TRUE => exclusion DURE (filtrée au push) ; les non-matchés
    (siret NULL, excluded=FALSE) restent contactables.
    """
    c = _conn(read_only=True)
    try:
        total_societe = c.execute(
            "SELECT COUNT(*) FROM contacts WHERE societe IS NOT NULL AND societe <> ''"
        ).fetchone()[0]
        r = c.execute("""
            SELECT
              COUNT(*) FILTER (WHERE excluded = FALSE AND siret IS NOT NULL),
              COUNT(*) FILTER (WHERE excluded = FALSE AND siret IS NULL),
              COUNT(*) FILTER (WHERE excluded = TRUE),
              COUNT(*),
              COUNT(*) FILTER (WHERE est_rge),
              COUNT(*) FILTER (WHERE est_qualiopi),
              COUNT(*) FILTER (WHERE est_ess),
              MAX(enriched_at)
            FROM contact_enrichment
        """).fetchone()
        reasons = c.execute(
            "SELECT exclusion_reason, COUNT(*) FROM contact_enrichment "
            "WHERE excluded GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        mj = c.execute(
            "SELECT "
            "COUNT(*) FILTER (WHERE mailnjoy_check IS NULL OR LENGTH(mailnjoy_check)=0), "
            "COUNT(*) FILTER (WHERE json_extract_string(mailnjoy_check,'$.decision')='valid'), "
            "COUNT(*) FILTER (WHERE mailnjoy_check IS NOT NULL AND LENGTH(mailnjoy_check)>0 "
            "  AND COALESCE(json_extract_string(mailnjoy_check,'$.decision'),'')<>'valid') "
            "FROM contacts WHERE global_blacklisted=FALSE"
        ).fetchone()
    finally:
        c.close()
    in_table = r[3] or 0
    return {
        "total_societe": total_societe,
        "in_table": in_table,
        "enriched": r[0] or 0,
        "unmatched": r[1] or 0,
        "hard_excluded": r[2] or 0,
        "remaining": max(0, total_societe - in_table),
        "signals": {"rge": r[4] or 0, "qualiopi": r[5] or 0, "ess": r[6] or 0},
        "hard_exclusion_reasons": {row[0]: row[1] for row in reasons},
        "last_enriched_at": str(r[7]) if r[7] else None,
        "mailnjoy": {"missing": mj[0] or 0, "valid": mj[1] or 0, "other": mj[2] or 0},
    }


# ──────────────────────────────────────────────────────────────────────────────
# Pioche pour campagne (cf. specs/contacts-model.md §3.5)
# ──────────────────────────────────────────────────────────────────────────────
SOURCE_RANK_SQL = """
    CASE c.primary_source
        WHEN 'tally' THEN 0
        WHEN 'serper' THEN 1
        WHEN 'csv' THEN 2
        ELSE 3
    END
"""

# Priorité absolue aux contacts que ce site n'a JAMAIS sollicités. Sans cette clé en tête de
# tri, le classement source/score ramenait les mêmes contacts dès leur sortie de cooldown :
# le 15/08/2026, 98 des 100 envois du jour étaient des renvois alors que 2 126 contacts
# immobilier n'avaient jamais rien reçu. On épuise le pool frais avant de recontacter.
NEVER_CONTACTED_FIRST_SQL = "(csh.last_contacted_by_site_at IS NULL) DESC"


def record_engagement(site_code: str, email: str, kind: str, channel: str,
                      at: str | None = None, only_if_null: bool = False,
                      proxy: bool = False) -> bool:
    """Enregistre une ouverture ('open') ou un clic ('click') pour un contact,
    quel que soit le canal (emelia/sweego/maildoso). Ne garde que la date LA PLUS
    RÉCENTE. Un clic implique aussi une ouverture. `only_if_null` : ne pose la date
    que si aucune n'existe (utilisé quand la vraie date d'événement est inconnue)."""
    if kind not in ("open", "click") or not email or "@" not in email:
        return False
    at = str(at or _now().isoformat())
    cols = [("last_opened_at", "last_open_channel")]
    if kind == "click":
        cols = [("last_clicked_at", "last_click_channel")] + cols
    c = _conn()
    try:
        for col, ch_col in cols:
            guard = f"csh.{col} IS NULL" if only_if_null else f"(csh.{col} IS NULL OR csh.{col} < ?)"
            params = [at, channel, site_code, email] + ([] if only_if_null else [at])
            c.execute(f"""
                UPDATE contact_site_history csh
                SET {col} = ?, {ch_col} = ?
                FROM contacts c2
                WHERE csh.contact_id = c2.id AND csh.site_code = ?
                  AND lower(c2.email) = lower(?) AND {guard}
            """, params)
    finally:
        c.close()
    # Un seul événement dans le journal, du type réellement observé. DuckDB pose aussi
    # l'ouverture quand il reçoit un clic (une seule date par contact, il faut choisir) ;
    # le journal, lui, n'a pas cette contrainte et ne doit pas inventer d'ouverture.
    _miroir("record_event", email, kind, site_code, channel, at=at)

    # Signal positif du client de messagerie : l'adresse expéditrice qui a obtenu ce
    # geste devient définitive pour ce contact. Un clic compte toujours ; une ouverture
    # seulement si elle n'est pas un pré-chargement antispam — 57 % des ouvertures
    # Sweego en sont, et figer une adresse sur un robot n'apprendrait rien.
    if kind == "click" or not proxy:
        try:
            import expediteur
            expediteur.confirmer(email)
        except Exception as e:  # noqa: BLE001
            print(f"[pool] affinité expéditeur non confirmée pour {email} : "
                  f"{type(e).__name__}: {e}", flush=True)
    return True


# Filtres d'engagement pour le ciblage de campagne (wizard étape Cible)
ENGAGEMENT_FILTERS = ("open_30", "open_180", "open_any", "click_any")


# Conditions brutes (sans « AND »), réutilisées par le filtre simple ET par les segments.
_ENGAGEMENT_COND = {
    "open_30":  "csh.last_opened_at >= CURRENT_TIMESTAMP - INTERVAL '30' DAY",
    "open_180": "csh.last_opened_at >= CURRENT_TIMESTAMP - INTERVAL '180' DAY",
    "open_any": "csh.last_opened_at IS NOT NULL",
    "click_any": "csh.last_clicked_at IS NOT NULL",
}


def _engagement_clause(engagement: str | None) -> str:
    """Fragment SQL du filtre d'engagement (aucun paramètre : intervalles littéraux)."""
    cond = _ENGAGEMENT_COND.get(engagement or "")
    return f"AND {cond}" if cond else ""


# ── Segments : règles enregistrées → SQL ─────────────────────────────────────
def _segment_side_sql(side: dict, match: str) -> tuple[str, list]:
    """Traduit UN côté (include ou exclude) en condition SQL.

    Dans une famille, les valeurs sont en OU. Entre familles, c'est `match` qui décide.
    Retourne ("", []) si le côté est vide — l'appelant sait alors qu'il n'y a rien à poser.
    """
    parts: list[str] = []
    params: list = []
    sectors = [s for s in (side.get("sectors") or []) if s]
    if sectors:
        parts.append("(" + " OR ".join(["c.sectors::VARCHAR LIKE ?"] * len(sectors)) + ")")
        params += [f"%{s}%" for s in sectors]
    depts = [d for d in (side.get("depts") or []) if d]
    if depts:
        parts.append(f"c.dept_code IN ({','.join('?' * len(depts))})")
        params += depts
    regions = [r for r in (side.get("regions") or []) if r]
    if regions:
        parts.append(f"c.region_code IN ({','.join('?' * len(regions))})")
        params += regions
    cond = _ENGAGEMENT_COND.get(side.get("engagement") or "")
    if cond:
        parts.append(f"({cond})")
    if not parts:
        return "", []
    glue = " OR " if str(match).upper() == "OR" else " AND "
    return "(" + glue.join(parts) + ")", params


def segment_clause(rules: dict) -> tuple[str, list, bool]:
    """Règles d'un segment → (fragment SQL, params, utilise_engagement).

    L'exclusion est soustraite en bloc ; la façon dont SES critères se combinent entre eux
    suit `exclude_match` (« ET » par défaut depuis le 2026-08-20 : on décrit une
    sous-population à retirer, pas une liste de repoussoirs indépendants).
    """
    import segments_backend as sb
    r = sb.normalize_rules(rules)
    inc_sql, inc_params = _segment_side_sql(r["include"], r["match"])
    exc_sql, exc_params = _segment_side_sql(r["exclude"], r.get("exclude_match", "AND"))

    sql, params = "", []
    if inc_sql:
        sql += f" AND {inc_sql}"
        params += inc_params
    if exc_sql:
        # COALESCE indispensable : en SQL, `dept_code IN ('13')` vaut NULL — et non FALSE —
        # quand le département est inconnu, et `NOT NULL` reste NULL, donc la ligne serait
        # écartée. Sans ça, exclure un département supprimait aussi tous les contacts dont
        # le département n'est pas renseigné (158 contacts perdus sur le pool LCR).
        sql += f" AND NOT COALESCE({exc_sql}, FALSE)"
        params += exc_params
    # Seule une INCLUSION sur l'engagement vaut ré-engagement (et ouvre donc les états
    # prm/lead). Une exclusion « sauf les cliqueurs » reste une campagne froide : elle ne
    # doit pas repêcher des contacts déjà avancés dans le tunnel.
    uses_engagement = bool(r["include"].get("engagement"))
    return sql, params, uses_engagement


def _segment_query(site_code: str, rules: dict, cleaned_within_days: int,
                   select_sql: str, tail_sql: str, extra_params: list | None = None):
    """Construit la requête d'un segment : éligibilité du pool + clauses du segment.

    Les filtres d'éligibilité (Mailnjoy valide et récent, non blacklisté, non exclu par
    l'enrichissement, hors cooldown) sont IDENTIQUES à `pick_for_campaign` : un segment
    restreint la cible, il ne peut jamais l'élargir au-delà du contactable.
    """
    cutoff = (_now() - timedelta(days=cleaned_within_days)).isoformat()
    seg_sql, seg_params, uses_eng = segment_clause(rules)
    # Même règle que le filtre simple : viser l'engagement, c'est du ré-engagement, donc
    # on ouvre aux contacts déjà promus prm/lead (la blacklist reste exclue).
    state_sql = ("(csh.state IS NULL OR csh.state IN ('cold_email','prm','lead'))" if uses_eng
                 else "(csh.state IS NULL OR csh.state = 'cold_email')")
    q = f"""
        {select_sql}
        FROM contacts c
        LEFT JOIN contact_site_history csh
            ON c.id = csh.contact_id AND csh.site_code = ?
        LEFT JOIN contact_enrichment e
            ON e.contact_id = c.id
        WHERE
            c.global_blacklisted = FALSE
            AND COALESCE(e.excluded, FALSE) = FALSE
            AND json_extract_string(c.mailnjoy_check, '$.decision') = 'valid'
            AND json_extract_string(c.mailnjoy_check, '$.checked_at') >= ?
            AND {state_sql}
            {seg_sql}
            AND (
                csh.last_contacted_by_site_at IS NULL
                OR csh.last_contacted_by_site_at < CURRENT_TIMESTAMP - INTERVAL '{COOLDOWN_SAME_SITE_DAYS}' DAY
            )
            AND NOT EXISTS (
                SELECT 1 FROM contact_site_history csh2
                WHERE csh2.contact_id = c.id
                  AND csh2.site_code != ?
                  AND csh2.last_contacted_by_site_at > CURRENT_TIMESTAMP - INTERVAL '{COOLDOWN_GLOBAL_DAYS}' DAY
            )
            {SUPPRESSION_CLAUSE_SQL}
        {tail_sql}
    """
    params = [site_code, cutoff, *seg_params, site_code, *(extra_params or [])]
    return q, params


def count_for_segment(site_code: str, rules: dict, cleaned_within_days: int = 180,
                      patience_s: float = 6.0) -> int:
    """Nombre de contacts contactables correspondant aux règles du segment.

    `patience_s` : le pool est verrouillé dès qu'un scrape ou le nettoyage horaire écrit
    (DuckDB n'admet qu'un écrivain OU des lecteurs). Ces écritures relâchent le verrou par
    intermittence : on patiente plus longtemps que le défaut (2,8 s) pour un compteur
    affiché à l'écran, quitte à répondre en quelques secondes plutôt qu'en erreur.
    """
    # Toujours PostgreSQL depuis le 2026-08-20, sans regarder `PG_READS` : la règle de
    # pression (4 communications par mois glissant) se compte sur `email_events`, et le pool
    # DuckDB ne garde qu'une date de dernier envoi par contact — il ne sait pas compter.
    return _pg().count_for_segment(site_code, rules,
                                   cleaned_within_days=cleaned_within_days)
    q, params = _segment_query(site_code, rules, cleaned_within_days,
                               "SELECT COUNT(*)", "")
    _ensure_schema()
    c = _connect_with_retry(read_only=True,
                            attempts=max(1, int(patience_s / 0.4)), sleep_s=0.4)
    try:
        row = c.execute(q, params).fetchone()
    finally:
        c.close()
    return int(row[0]) if row else 0


def expliquer_segment(site_code: str, rules: dict, cleaned_within_days: int = 180) -> dict:
    """Délégué à PostgreSQL — voir `pool_pg.expliquer_segment`."""
    return _pg().expliquer_segment(site_code, rules, cleaned_within_days=cleaned_within_days)


def _expliquer_segment_duckdb(site_code: str, rules: dict, cleaned_within_days: int = 180) -> dict:
    """Pourquoi un segment ne ramène-t-il personne ?

    Un ciblage « a ouvert » renvoie couramment 0. Ce n'est pas une panne : quelqu'un qui a
    ouvert un email l'a forcément REÇU, il est donc en repos pour 120 jours. Le compteur
    disait « 0 contactable aujourd'hui » sans dire pourquoi, et ce zéro passait pour un bug.

    On rend donc, à côté du contactable, la population qui correspond au CIBLAGE et le
    détail de ce qui la retient — repos, blacklist, adresse non valide, entreprise exclue —
    plus la date de sortie de repos la plus proche.
    """
    seg_sql, seg_params, uses_eng = segment_clause(rules)
    state_sql = ("(csh.state IS NULL OR csh.state IN ('cold_email','prm','lead'))" if uses_eng
                 else "(csh.state IS NULL OR csh.state = 'cold_email')")
    cutoff = (_now() - timedelta(days=cleaned_within_days)).isoformat()

    q = f"""
        SELECT count(*),
               count(*) FILTER (WHERE COALESCE(c.global_blacklisted, FALSE)),
               count(*) FILTER (WHERE COALESCE(e.excluded, FALSE)),
               count(*) FILTER (WHERE COALESCE(json_extract_string(c.mailnjoy_check, '$.decision'), '') <> 'valid'
                                   OR COALESCE(json_extract_string(c.mailnjoy_check, '$.checked_at'), '') < ?),
               count(*) FILTER (WHERE sup.email IS NOT NULL),
               min(sup.release_at) FILTER (WHERE sup.email IS NOT NULL)
        FROM contacts c
        LEFT JOIN contact_site_history csh
            ON c.id = csh.contact_id AND csh.site_code = ?
        LEFT JOIN contact_enrichment e ON e.contact_id = c.id
        LEFT JOIN email_suppression sup
            ON sup.email = lower(c.email) AND sup.contactable = 0
           AND sup.last_sent_at > CURRENT_TIMESTAMP - INTERVAL '{SUPPRESSION_DAYS}' DAY
        WHERE {state_sql} {seg_sql}
    """
    params = [cutoff, site_code] + list(seg_params)

    c = _conn(read_only=True)
    try:
        r = c.execute(q, params).fetchone()
    finally:
        c.close()

    correspondants, blacklist, exclus, email_ko, repos, liberation = r
    return {
        "correspondants": int(correspondants or 0),
        "ecartes": {
            "repos": int(repos or 0),
            "blacklist": int(blacklist or 0),
            "email_non_valide": int(email_ko or 0),
            "entreprise_exclue": int(exclus or 0),
        },
        "prochaine_liberation": str(liberation)[:10] if liberation else None,
    }


def pick_for_segment(site_code: str, rules: dict, limit: int = 30,
                     cleaned_within_days: int = 180) -> list[dict]:
    """Pioche les N meilleurs contacts d'un segment (même tri que pick_for_campaign)."""
    # Voir `count_for_segment` : les segments vivent côté PostgreSQL.
    return _pg().pick_for_segment(site_code, rules, limit=limit,
                                  cleaned_within_days=cleaned_within_days)
    cols = ["id", "email", "prenom", "nom", "societe", "tel", "website",
            "city", "dept_code", "region_code", "sectors",
            "primary_source", "email_score", "global_blacklisted",
            "state", "last_contacted_by_site_at"]
    select_sql = ("SELECT c.id, c.email, c.prenom, c.nom, c.societe, c.tel, c.website, "
                  "c.city, c.dept_code, c.region_code, c.sectors, "
                  "c.primary_source, c.email_score, c.global_blacklisted, "
                  "csh.state, csh.last_contacted_by_site_at")
    tail = f"""ORDER BY
            {NEVER_CONTACTED_FIRST_SQL},
            {SOURCE_RANK_SQL},
            c.email_score DESC NULLS LAST,
            c.updated_at DESC
        LIMIT ?"""
    q, params = _segment_query(site_code, rules, cleaned_within_days, select_sql, tail, [limit])
    c = _conn(read_only=True)
    try:
        rows = c.execute(q, params).fetchall()
    finally:
        c.close()
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        d["sectors"] = _maybe_parse(d.get("sectors"))
        if d.get("last_contacted_by_site_at"):
            d["last_contacted_by_site_at"] = str(d["last_contacted_by_site_at"])
        out.append(d)
    return out


def _geo_clause(regions: list[str] | None, depts: list[str] | None) -> tuple[str, list]:
    """Fragment SQL + params du ciblage géographique optionnel.

    OR entre les zones : un contact matche s'il est dans UN des départements choisis
    OU dans UNE des régions choisies. Sans critère → pas de clause (France entière).
    Les contacts sans dept_code/region_code sont exclus dès qu'un critère géo est posé."""
    regions = [r for r in (regions or []) if r]
    depts = [d for d in (depts or []) if d]
    if not regions and not depts:
        return "", []
    conds, params = [], []
    if depts:
        conds.append(f"c.dept_code IN ({','.join('?' * len(depts))})")
        params += depts
    if regions:
        conds.append(f"c.region_code IN ({','.join('?' * len(regions))})")
        params += regions
    return f"AND ({' OR '.join(conds)})", params


def pick_for_campaign(site_code: str, sector: str, limit: int = 30,
                      cooldown_global_days: int = COOLDOWN_GLOBAL_DAYS,
                      cooldown_same_site_days: int = COOLDOWN_SAME_SITE_DAYS,
                      cleaned_within_days: int = 180,
                      regions: list[str] | None = None,
                      depts: list[str] | None = None,
                      engagement: str | None = None) -> list[dict]:
    """Algorithme de pioche : retourne les N meilleurs contacts pour une campagne.

    Filtres :
      - sector dans contacts.sectors
      - regions/depts (optionnel) : dept_code ou region_code dans les zones ciblées
      - NOT global_blacklisted
      - Mailnjoy décision 'valid' ET vérifié il y a < cleaned_within_days (récence, défaut 6 mois)
      - state IS NULL (jamais utilisé par ce site) OR state = 'cold_email'
      - last_contacted_by_site_at IS NULL OR > NOW - cooldown_same_site_days
      - aucun autre site ne l'a contacté dans les cooldown_global_days

    Tri : source (tally>serper>csv>manual), email_score desc, updated_at desc
    """
    if _pg_reads():
        return _pg().pick_for_campaign(
            site_code, sector, limit=limit, cleaned_within_days=cleaned_within_days,
            regions=regions, depts=depts, engagement=engagement)
    cutoff = (_now() - timedelta(days=cleaned_within_days)).isoformat()
    geo_sql, geo_params = _geo_clause(regions, depts)
    eng_sql = _engagement_clause(engagement)
    # Ciblage engagement = ré-engagement : les cliqueurs sont souvent déjà promus
    # prm/lead, on élargit donc les états éligibles (blacklist reste exclue).
    state_sql = ("(csh.state IS NULL OR csh.state IN ('cold_email','prm','lead'))" if eng_sql
                 else "(csh.state IS NULL OR csh.state = 'cold_email')")
    q = f"""
        SELECT c.id, c.email, c.prenom, c.nom, c.societe, c.tel, c.website,
               c.city, c.dept_code, c.region_code, c.sectors,
               c.primary_source, c.email_score, c.global_blacklisted,
               csh.state, csh.last_contacted_by_site_at
        FROM contacts c
        LEFT JOIN contact_site_history csh
            ON c.id = csh.contact_id AND csh.site_code = ?
        LEFT JOIN contact_enrichment e
            ON e.contact_id = c.id
        WHERE
            c.global_blacklisted = FALSE
            AND c.sectors::VARCHAR LIKE ?
            {geo_sql}
            -- enrichissement data.gouv : on écarte les entités enrichies ET exclues
            -- (fermées, administrations, diffusion partielle). Les non-enrichis (e.* NULL)
            -- passent normalement : on ne bloque pas le flux faute d'enrichissement.
            AND COALESCE(e.excluded, FALSE) = FALSE
            -- N'ENVOYER QU'AUX EMAILS NETTOYÉS : Mailnjoy décision 'valid' uniquement
            -- (exclut error/risky/pending et les jamais-vérifiés NULL).
            AND json_extract_string(c.mailnjoy_check, '$.decision') = 'valid'
            -- RÉCENCE : vérification Mailnjoy < cleaned_within_days (défaut 6 mois)
            AND json_extract_string(c.mailnjoy_check, '$.checked_at') >= ?
            AND {state_sql}
            {eng_sql}
            AND (
                csh.last_contacted_by_site_at IS NULL
                OR csh.last_contacted_by_site_at < CURRENT_TIMESTAMP - INTERVAL '{cooldown_same_site_days}' DAY
            )
            AND NOT EXISTS (
                SELECT 1 FROM contact_site_history csh2
                WHERE csh2.contact_id = c.id
                  AND csh2.site_code != ?
                  AND csh2.last_contacted_by_site_at > CURRENT_TIMESTAMP - INTERVAL '{cooldown_global_days}' DAY
            )
            {SUPPRESSION_CLAUSE_SQL}
        ORDER BY
            {NEVER_CONTACTED_FIRST_SQL},
            {SOURCE_RANK_SQL},
            c.email_score DESC NULLS LAST,
            c.updated_at DESC
        LIMIT ?
    """
    c = _conn(read_only=True)
    try:
        rows = c.execute(q, [site_code, f"%{sector}%", *geo_params, cutoff, site_code, limit]).fetchall()
    finally:
        c.close()
    cols = ["id", "email", "prenom", "nom", "societe", "tel", "website",
            "city", "dept_code", "region_code", "sectors",
            "primary_source", "email_score", "global_blacklisted",
            "state", "last_contacted_by_site_at"]
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        d["sectors"] = _maybe_parse(d.get("sectors"))
        if d.get("last_contacted_by_site_at"):
            d["last_contacted_by_site_at"] = str(d["last_contacted_by_site_at"])
        out.append(d)
    return out


def count_available_for_sector(site_code: str, sector: str, cleaned_within_days: int = 180,
                               regions: list[str] | None = None,
                               depts: list[str] | None = None,
                               engagement: str | None = None) -> int:
    """Count des contacts disponibles pour pioche dans un secteur (filtres identiques à pick_for_campaign)."""
    if _pg_reads():
        return _pg().count_available_for_sector(
            site_code, sector, cleaned_within_days=cleaned_within_days,
            regions=regions, depts=depts, engagement=engagement)
    cutoff = (_now() - timedelta(days=cleaned_within_days)).isoformat()
    geo_sql, geo_params = _geo_clause(regions, depts)
    eng_sql = _engagement_clause(engagement)
    state_sql = ("(csh.state IS NULL OR csh.state IN ('cold_email','prm','lead'))" if eng_sql
                 else "(csh.state IS NULL OR csh.state = 'cold_email')")
    q = f"""
        SELECT COUNT(*)
        FROM contacts c
        LEFT JOIN contact_site_history csh
            ON c.id = csh.contact_id AND csh.site_code = ?
        LEFT JOIN contact_enrichment e
            ON e.contact_id = c.id
        WHERE
            c.global_blacklisted = FALSE
            AND c.sectors::VARCHAR LIKE ?
            {geo_sql}
            AND COALESCE(e.excluded, FALSE) = FALSE
            -- N'ENVOYER QU'AUX EMAILS NETTOYÉS : Mailnjoy décision 'valid' uniquement
            -- (exclut error/risky/pending et les jamais-vérifiés NULL).
            AND json_extract_string(c.mailnjoy_check, '$.decision') = 'valid'
            -- RÉCENCE : vérification Mailnjoy < cleaned_within_days (défaut 6 mois)
            AND json_extract_string(c.mailnjoy_check, '$.checked_at') >= ?
            AND {state_sql}
            {eng_sql}
            AND (
                csh.last_contacted_by_site_at IS NULL
                OR csh.last_contacted_by_site_at < CURRENT_TIMESTAMP - INTERVAL '{COOLDOWN_SAME_SITE_DAYS}' DAY
            )
            AND NOT EXISTS (
                SELECT 1 FROM contact_site_history csh2
                WHERE csh2.contact_id = c.id
                  AND csh2.site_code != ?
                  AND csh2.last_contacted_by_site_at > CURRENT_TIMESTAMP - INTERVAL '{COOLDOWN_GLOBAL_DAYS}' DAY
            )
            {SUPPRESSION_CLAUSE_SQL}
    """
    c = _conn(read_only=True)
    try:
        n = c.execute(q, [site_code, f"%{sector}%", *geo_params, cutoff, site_code]).fetchone()[0]
    finally:
        c.close()
    return int(n or 0)


def pool_sectors(min_count: int = 1) -> list[str]:
    """Secteurs RÉELLEMENT présents dans le pool (non blacklistés), triés par fréquence desc.

    Source de vérité = la donnée, pas la liste scrapable figée SECTORS_GOD_MODE (qui sert au
    scraping Serper et ne reflète pas la taxonomie importée). Utilisé par la Vision pour des
    compteurs par secteur cohérents avec ce qu'on a vraiment en base.
    """
    c = _conn(read_only=True)
    try:
        rows = c.execute(
            "SELECT sectors::VARCHAR AS s, COUNT(*) AS n FROM contacts "
            "WHERE COALESCE(global_blacklisted, FALSE) = FALSE "
            "AND sectors IS NOT NULL AND sectors::VARCHAR NOT IN ('', '[]', 'null') "
            "GROUP BY 1"
        ).fetchall()
    finally:
        c.close()
    # sectors est un tableau JSON ("[\"immobilier\"]") — on agrège les tokens par fréquence.
    freq: dict[str, int] = {}
    for raw, n in rows:
        try:
            vals = json.loads(raw)
        except Exception:
            vals = [raw]
        if not isinstance(vals, list):
            vals = [vals]
        for v in vals:
            tok = str(v).strip().lower()
            if tok:
                freq[tok] = freq.get(tok, 0) + int(n or 0)
    return [s for s, n in sorted(freq.items(), key=lambda kv: kv[1], reverse=True) if n >= min_count]


def check_pool_depletion(site_code: str, sectors: list[str], threshold: int = 10) -> list[dict]:
    """Pour chaque secteur, compte les contacts dispo. Retourne ceux < threshold."""
    out = []
    for s in sectors:
        n = count_available_for_sector(site_code, s)
        if n < threshold:
            out.append({"sector": s, "available": n})
    return out
