#!/usr/bin/env python3
"""
migrate_contacts_to_pool.py — One-shot migration vers le pool mutualisé Genesis.

Crée data/contacts.duckdb avec 2 tables :
  - contacts (master, PK email)
  - contact_site_history (relation N-N, état par site)

Lit depuis :
  - data/crm/lcr.duckdb.acquisition_contacts
  - data/crm/mkd.duckdb.acquisition_contacts
  - data/god_mode.duckdb.scrappe (status IN mailnjoy_valid, pushed_emelia, manual_review)

Dédup par email. Old DBs intactes (RO).

Voir specs/contacts-model.md
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

BASE = Path("/home/autoblog/genesis")
OUT = BASE / "data" / "contacts.duckdb"
LOG_F = BASE / "logs" / "migration_contacts_pool.log"
LOG_F.parent.mkdir(exist_ok=True)


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line)
    with open(LOG_F, "a") as f:
        f.write(line + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# 1. Création des tables
# ──────────────────────────────────────────────────────────────────────────────
def create_schema(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id                          VARCHAR PRIMARY KEY,
            email                       VARCHAR UNIQUE,
            prenom                      VARCHAR,
            nom                         VARCHAR,
            societe                     VARCHAR,
            tel                         VARCHAR,
            website                     VARCHAR,
            city                        VARCHAR,
            dept_code                   VARCHAR,
            region_code                 VARCHAR,
            postal_code                 VARCHAR,
            sectors                     JSON,
            primary_source              VARCHAR,
            email_score                 INTEGER,
            email_validation_reasons    JSON,
            mailnjoy_check              JSON,
            global_blacklisted          BOOLEAN DEFAULT FALSE,
            blacklist_reason            VARCHAR,
            blacklisted_at              TIMESTAMP,
            created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_contacts_blacklist ON contacts(global_blacklisted)")

    c.execute("""
        CREATE TABLE IF NOT EXISTS contact_site_history (
            id                          VARCHAR PRIMARY KEY,
            contact_id                  VARCHAR,
            site_code                   VARCHAR,
            account_id                  VARCHAR,
            state                       VARCHAR,
            source                      VARCHAR,
            added_to_site_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            state_history               JSON,
            last_action_at              TIMESTAMP,
            emelia_campaign_id          VARCHAR,
            emelia_contact_id           VARCHAR,
            email_sent_at               TIMESTAMP,
            emelia_opened_at            TIMESTAMP,
            emelia_clicked_at           TIMESTAMP,
            emelia_replied_at           TIMESTAMP,
            emelia_bounced_at           TIMESTAMP,
            emelia_unsubscribed_at      TIMESTAMP,
            last_contacted_by_site_at   TIMESTAMP,
            notes                       VARCHAR,
            UNIQUE (contact_id, site_code)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_csh_contact ON contact_site_history(contact_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_csh_site ON contact_site_history(site_code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_csh_state ON contact_site_history(state)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_csh_last_contact ON contact_site_history(last_contacted_by_site_at)")


# ──────────────────────────────────────────────────────────────────────────────
# 2. Helper : upsert dans contacts (dédup par email)
# ──────────────────────────────────────────────────────────────────────────────
def upsert_contact(c, **kwargs) -> str:
    """INSERT or UPDATE-NULL-only. Retourne contact_id."""
    email = (kwargs.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return None

    existing = c.execute("SELECT id FROM contacts WHERE email = ?", [email]).fetchone()
    if existing:
        cid = existing[0]
        # Update les champs NULL uniquement (jamais override)
        for col in ("prenom", "nom", "societe", "tel", "website", "city",
                    "dept_code", "region_code", "postal_code", "email_score",
                    "primary_source"):
            v = kwargs.get(col)
            if v is None:
                continue
            row = c.execute(f"SELECT {col} FROM contacts WHERE id = ?", [cid]).fetchone()
            if row and (row[0] is None or row[0] == ""):
                c.execute(f"UPDATE contacts SET {col} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", [v, cid])
        # JSON fields : if NULL, set
        for col in ("sectors", "email_validation_reasons", "mailnjoy_check"):
            v = kwargs.get(col)
            if v is None:
                continue
            row = c.execute(f"SELECT {col} FROM contacts WHERE id = ?", [cid]).fetchone()
            if row and row[0] is None:
                c.execute(f"UPDATE contacts SET {col} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                          [json.dumps(v) if not isinstance(v, str) else v, cid])
        return cid

    # Insert new
    cid = str(uuid.uuid4())
    c.execute("""
        INSERT INTO contacts
        (id, email, prenom, nom, societe, tel, website, city, dept_code, region_code,
         postal_code, sectors, primary_source, email_score, email_validation_reasons,
         mailnjoy_check, global_blacklisted, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, [
        cid, email,
        kwargs.get("prenom"), kwargs.get("nom"), kwargs.get("societe"), kwargs.get("tel"),
        kwargs.get("website"), kwargs.get("city"), kwargs.get("dept_code"), kwargs.get("region_code"),
        kwargs.get("postal_code"),
        json.dumps(kwargs.get("sectors")) if kwargs.get("sectors") is not None else None,
        kwargs.get("primary_source"),
        kwargs.get("email_score"),
        json.dumps(kwargs.get("email_validation_reasons")) if kwargs.get("email_validation_reasons") else None,
        json.dumps(kwargs.get("mailnjoy_check")) if kwargs.get("mailnjoy_check") else None,
    ])
    return cid


def upsert_history(c, contact_id, site_code, **kwargs):
    """Insert ou update history row pour (contact_id, site_code)."""
    if not contact_id or not site_code:
        return
    existing = c.execute(
        "SELECT id FROM contact_site_history WHERE contact_id = ? AND site_code = ?",
        [contact_id, site_code]
    ).fetchone()
    if existing:
        # Update les champs si fournis (sauf state qu'on garde plus avancé)
        return  # on garde l'historique existant
    hid = str(uuid.uuid4())
    c.execute("""
        INSERT INTO contact_site_history
        (id, contact_id, site_code, account_id, state, source, added_to_site_at,
         state_history, last_action_at, emelia_campaign_id, emelia_contact_id,
         email_sent_at, emelia_opened_at, emelia_clicked_at, emelia_replied_at,
         emelia_bounced_at, emelia_unsubscribed_at, last_contacted_by_site_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        hid, contact_id, site_code, kwargs.get("account_id"),
        kwargs.get("state", "cold_email"),
        kwargs.get("source", "migration"),
        kwargs.get("added_to_site_at") or datetime.now(timezone.utc),
        json.dumps(kwargs.get("state_history")) if kwargs.get("state_history") else None,
        kwargs.get("last_action_at"),
        kwargs.get("emelia_campaign_id"), kwargs.get("emelia_contact_id"),
        kwargs.get("email_sent_at"), kwargs.get("emelia_opened_at"),
        kwargs.get("emelia_clicked_at"), kwargs.get("emelia_replied_at"),
        kwargs.get("emelia_bounced_at"), kwargs.get("emelia_unsubscribed_at"),
        kwargs.get("last_contacted_by_site_at"),
        kwargs.get("notes"),
    ])


# ──────────────────────────────────────────────────────────────────────────────
# 3. Migration depuis acquisition_contacts (crm/lcr + crm/mkd)
# ──────────────────────────────────────────────────────────────────────────────
def migrate_acquisition(out_conn, site_code: str):
    src_path = BASE / "data" / "crm" / f"{site_code}.duckdb"
    if not src_path.exists():
        log(f"  [{site_code}] {src_path.name} introuvable, skip")
        return 0, 0

    src = duckdb.connect(str(src_path), read_only=True)
    try:
        rows = src.execute("""
            SELECT id, state, source, email, nom, prenom, societe, tel, notes,
                   state_history, created_at, updated_at, last_action_at,
                   email_sent_at, emelia_campaign_id, emelia_contact_id,
                   emelia_opened_at, emelia_clicked_at, emelia_replied_at,
                   emelia_bounced_at, emelia_unsubscribed_at,
                   sector, dept_code, region_code
            FROM acquisition_contacts
        """).fetchall()
    finally:
        src.close()

    inserted_contacts = 0
    inserted_history = 0
    for r in rows:
        (_old_id, state, source, email, nom, prenom, societe, tel, notes,
         state_history, created_at, updated_at, last_action_at,
         email_sent_at, emelia_campaign_id, emelia_contact_id,
         emelia_opened_at, emelia_clicked_at, emelia_replied_at,
         emelia_bounced_at, emelia_unsubscribed_at,
         sector, dept_code, region_code) = r

        sectors = [sector] if sector else []

        # Détermine primary_source (1ère insertion seulement)
        primary_source_map = {
            "scraping_serper": "serper",
            "workflow:restaurant": "serper", "workflow:immobilier": "serper",
            "workflow:coiffeur": "serper", "workflow:garagiste": "serper",
            "workflow:retail": "serper", "workflow:artisan": "serper",
            "import_csv": "csv", "manual": "manual", "tally_legacy": "tally",
            "emelia_click": "serper",  # historique avant tracking
        }
        primary_source = "manual"
        if source:
            for prefix, mapped in primary_source_map.items():
                if source.startswith(prefix):
                    primary_source = mapped
                    break
            else:
                if "tally" in (source or "").lower():
                    primary_source = "tally"

        cid = upsert_contact(
            out_conn,
            email=email, prenom=prenom, nom=nom, societe=societe, tel=tel,
            dept_code=dept_code, region_code=region_code,
            sectors=sectors if sectors else None,
            primary_source=primary_source,
        )
        if cid is None:
            continue
        inserted_contacts += 1

        # Détermine état + blacklist
        if state == "blacklisted":
            out_conn.execute("""
                UPDATE contacts SET global_blacklisted = TRUE,
                                    blacklist_reason = ?, blacklisted_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, [f"migrated from {site_code} ({source})", cid])

        # last_contacted = max(email_sent_at, dernière interaction)
        timestamps = [t for t in (email_sent_at, emelia_opened_at, emelia_clicked_at,
                                  emelia_replied_at, emelia_bounced_at, emelia_unsubscribed_at)
                      if t is not None]
        last_contact = max(timestamps) if timestamps else email_sent_at

        try:
            sh = json.loads(state_history) if isinstance(state_history, str) and state_history else state_history
        except Exception:
            sh = None

        upsert_history(
            out_conn, cid, site_code,
            state=state,
            source=source or "migration",
            state_history=sh,
            last_action_at=last_action_at,
            email_sent_at=email_sent_at,
            emelia_campaign_id=emelia_campaign_id,
            emelia_contact_id=emelia_contact_id,
            emelia_opened_at=emelia_opened_at,
            emelia_clicked_at=emelia_clicked_at,
            emelia_replied_at=emelia_replied_at,
            emelia_bounced_at=emelia_bounced_at,
            emelia_unsubscribed_at=emelia_unsubscribed_at,
            last_contacted_by_site_at=last_contact,
            notes=notes,
        )
        inserted_history += 1

    log(f"  [{site_code}] migrated {inserted_contacts} contacts, {inserted_history} history rows")
    return inserted_contacts, inserted_history


# ──────────────────────────────────────────────────────────────────────────────
# 4. Migration depuis scrappe (god_mode.duckdb)
# ──────────────────────────────────────────────────────────────────────────────
def migrate_scrappe(out_conn):
    src_path = BASE / "data" / "god_mode.duckdb"
    if not src_path.exists():
        log("  [scrappe] god_mode.duckdb introuvable, skip")
        return 0, 0

    src = duckdb.connect(str(src_path), read_only=True)
    try:
        rows = src.execute("""
            SELECT id, site_code, company_name, contact_name, email, phone,
                   sector, city, postal_code, website, source, score, status,
                   created_at, contacted_at, rejection_reason,
                   region_code, dept_code,
                   qualifier_buyer, qualifier_reason,
                   emelia_segment_id, emelia_contact_id,
                   email_score, email_validation_reasons, mailnjoy_check
            FROM scrappe
            WHERE status IN ('mailnjoy_valid', 'pushed_emelia', 'manual_review')
              AND email IS NOT NULL AND email != ''
        """).fetchall()
    finally:
        src.close()

    inserted = 0
    history = 0
    state_map = {
        "mailnjoy_valid": ("cold_email", "Migrated from scrappe (mailnjoy_valid)"),
        "pushed_emelia":  ("cold_email", "Migrated from scrappe (already pushed Emelia)"),
        "manual_review":  ("cold_email", "Migrated from scrappe (manual_review)"),
    }

    for r in rows:
        (_old_id, site_code, company, contact_name, email, phone, sector, city,
         postal_code, website, source, _score, status,
         created_at, contacted_at, _rej_reason, region_code, dept_code,
         _qualifier_buyer, _qualifier_reason,
         emelia_segment_id, emelia_contact_id,
         email_score, email_validation_reasons, mailnjoy_check) = r

        first_name, last_name = "", ""
        if contact_name:
            parts = contact_name.strip().split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

        sectors = [sector] if sector else []

        # Parse JSON cols
        evr = None
        if email_validation_reasons:
            try:
                evr = json.loads(email_validation_reasons) if isinstance(email_validation_reasons, str) else email_validation_reasons
            except Exception:
                pass
        mnc = None
        if mailnjoy_check:
            try:
                mnc = json.loads(mailnjoy_check) if isinstance(mailnjoy_check, str) else mailnjoy_check
            except Exception:
                pass

        cid = upsert_contact(
            out_conn,
            email=email, prenom=first_name, nom=last_name, societe=company, tel=phone,
            website=website, city=city, postal_code=postal_code,
            dept_code=dept_code, region_code=region_code,
            sectors=sectors if sectors else None,
            primary_source="serper" if (source or "").startswith("serper") else "manual",
            email_score=email_score,
            email_validation_reasons=evr,
            mailnjoy_check=mnc,
        )
        if cid is None:
            continue
        inserted += 1

        new_state, note = state_map.get(status, ("cold_email", f"migrated status={status}"))
        upsert_history(
            out_conn, cid, site_code,
            state=new_state,
            source=source or "serper",
            emelia_campaign_id=emelia_segment_id,
            emelia_contact_id=emelia_contact_id,
            email_sent_at=contacted_at if status == "pushed_emelia" else None,
            last_contacted_by_site_at=contacted_at if status == "pushed_emelia" else None,
            notes=note,
        )
        history += 1

    log(f"  [scrappe] migrated {inserted} contacts, {history} history rows")
    return inserted, history


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────
def main():
    log("=== Migration contacts vers pool mutualisé ===")
    log(f"Out: {OUT}")

    if OUT.exists():
        # Backup
        bak = OUT.with_suffix(".duckdb.bak-" + datetime.now().strftime("%Y%m%d_%H%M"))
        OUT.rename(bak)
        log(f"  Backup existant -> {bak.name}")

    out = duckdb.connect(str(OUT))
    try:
        create_schema(out)
        log("Schema OK (contacts + contact_site_history)")

        total_c = 0
        total_h = 0
        for site in ("lcr", "mkd"):
            c, h = migrate_acquisition(out, site)
            total_c += c
            total_h += h

        c, h = migrate_scrappe(out)
        total_c += c
        total_h += h

        # Stats finales
        n_contacts = out.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        n_history = out.execute("SELECT COUNT(*) FROM contact_site_history").fetchone()[0]
        n_bl = out.execute("SELECT COUNT(*) FROM contacts WHERE global_blacklisted").fetchone()[0]
        by_site = out.execute("SELECT site_code, COUNT(*) FROM contact_site_history GROUP BY site_code").fetchall()
        by_state = out.execute("SELECT state, COUNT(*) FROM contact_site_history GROUP BY state").fetchall()

        log("=== Stats finales ===")
        log(f"  contacts (uniques): {n_contacts}")
        log(f"  history rows total: {n_history}")
        log(f"  global blacklisted: {n_bl}")
        log(f"  par site: {dict(by_site)}")
        log(f"  par state: {dict(by_state)}")
        log("=== Migration terminée ===")
    finally:
        out.close()


if __name__ == "__main__":
    main()
