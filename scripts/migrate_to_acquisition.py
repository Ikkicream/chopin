#!/usr/bin/env python3
"""
migrate_to_acquisition.py — Migration douce vers acquisition_contacts (one-shot).

Ce script lit les 3 storages historiques et les fusionne dans la nouvelle table :
  1. data/crm/prm_{site}.duckdb table `prm_contacts` (= PRM/leads)
  2. data/crm/{site}.duckdb table `contacts` (= CRM)
  3. data/prospects/{site}/leads.csv (= cold emails du scraping Serper)

Dédup par email — état le plus avancé garde la main (crm > lead > prm > cold_email).

Avant écriture : dump JSON safety dans backups/migration-acquisition-{ts}/{site}-{source}.json
Idempotent : on peut le rejouer sans pb (les emails déjà migrés sont skip via find_by_email).

Usage:
  python3 scripts/migrate_to_acquisition.py [--site lcr|mkd|both] [--dry-run]
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

import duckdb
from acquisition_backend import find_by_email, create, change_state, STATE_RANK

BACKUP_BASE = BASE_DIR / "backups" / f"migration-acquisition-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _dump(path: Path, label: str, rows: list):
    path.mkdir(parents=True, exist_ok=True)
    target = path / f"{label}.json"
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    print(f"    dump → {target}  ({len(rows)} entrées)")


def _infer_state_from_old_contact(row: dict) -> str:
    """Heuristique pour deviner l'état d'un contact CRM legacy."""
    statut = (row.get("statut") or "").lower()
    if statut in ("client", "client_actif", "client_signe", "client_signé"):
        return "crm"
    if statut in ("lead_hot", "hot", "rdv_pris", "rdv"):
        return "lead"
    if statut in ("lead_warm", "warm", "contacted"):
        return "prm"
    if statut in ("blacklist", "blacklisted", "unsubscribed", "bounced"):
        return "blacklisted"
    # Par défaut on suppose qu'un contact du CRM legacy est au moins un lead
    return "lead"


def _infer_state_from_prm(row: dict) -> str:
    """Heuristique pour deviner l'état d'un prm_contact legacy."""
    campaign = (row.get("campaign") or "").lower()
    action = (row.get("action") or "").lower()
    if "tally" in campaign or "form" in campaign or "form" in action:
        return "lead"
    if "emelia" in campaign or "click" in action:
        return "prm"
    # PRM legacy par défaut = lead (parce que la source originale était les formulaires Tally)
    return "lead"


def _migrate_one(site: str, payload: dict, source: str, target_state: str, dry: bool) -> str:
    """Insert ou promote selon hiérarchie d'état. Retourne 'created'|'promoted'|'kept'."""
    email = (payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return "invalid"
    existing = find_by_email(site, email)
    if existing:
        current_rank = STATE_RANK.get(existing["state"], 0)
        target_rank  = STATE_RANK.get(target_state, 0)
        if existing["state"] == "blacklisted" or target_rank <= current_rank:
            return "kept"
        if dry:
            return "promoted_DRY"
        change_state(site, existing["id"], target_state, by="migration", note=f"from {source}")
        return "promoted"
    if dry:
        return "created_DRY"
    create(site, {**payload, "email": email, "state": target_state, "source": source}, by="migration")
    return "created"


def migrate_prm(site: str, dry: bool):
    p = BASE_DIR / "data" / "crm" / f"prm_{site}.duckdb"
    if not p.exists():
        print(f"  [prm:{site}] base absente, skip")
        return
    print(f"  [prm:{site}] reading {p}")
    conn = duckdb.connect(str(p), read_only=True)
    try:
        cols = [c[0] for c in conn.execute("DESCRIBE prm_contacts").fetchall()]
        select = ", ".join(cols)
        rows = conn.execute(f"SELECT {select} FROM prm_contacts").fetchall()
    finally:
        conn.close()
    rows_d = [dict(zip(cols, r)) for r in rows]
    _dump(BACKUP_BASE, f"{site}-prm", rows_d)

    counts = {"created": 0, "promoted": 0, "kept": 0, "invalid": 0, "created_DRY": 0, "promoted_DRY": 0}
    for row in rows_d:
        target_state = _infer_state_from_prm(row)
        source = row.get("campaign") or "tally_legacy"
        result = _migrate_one(site, {
            "email":   row.get("email", ""),
            "nom":     row.get("lastName") or row.get("nom", ""),
            "prenom":  row.get("firstName") or row.get("prenom", ""),
            "societe": row.get("company") or row.get("societe", ""),
            "tel":     row.get("phone") or row.get("tel", ""),
            "notes":   f"campaign={row.get('campaign','')} action={row.get('action','')}",
        }, source=source if source.startswith("tally") else "tally_legacy", target_state=target_state, dry=dry)
        counts[result] = counts.get(result, 0) + 1
    print(f"  [prm:{site}] {counts}")


def migrate_crm(site: str, dry: bool):
    p = BASE_DIR / "data" / "crm" / f"{site}.duckdb"
    if not p.exists():
        print(f"  [crm:{site}] base absente, skip")
        return
    print(f"  [crm:{site}] reading {p} table 'contacts'")
    conn = duckdb.connect(str(p), read_only=True)
    try:
        tables = [r[0] for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()]
        if "contacts" not in tables:
            print(f"  [crm:{site}] table contacts absente, skip")
            return
        cols = [c[0] for c in conn.execute("DESCRIBE contacts").fetchall()]
        select = ", ".join(cols)
        rows = conn.execute(f"SELECT {select} FROM contacts").fetchall()
    finally:
        conn.close()
    rows_d = [dict(zip(cols, r)) for r in rows]
    _dump(BACKUP_BASE, f"{site}-crm", rows_d)

    counts = {}
    for row in rows_d:
        target_state = _infer_state_from_old_contact(row)
        source = row.get("source") or "crm_legacy"
        result = _migrate_one(site, {
            "email":   row.get("email", ""),
            "nom":     row.get("nom", ""),
            "prenom":  row.get("prenom", ""),
            "societe": row.get("societe", ""),
            "tel":     row.get("tel", ""),
            "notes":   row.get("notes", ""),
        }, source=source, target_state=target_state, dry=dry)
        counts[result] = counts.get(result, 0) + 1
    print(f"  [crm:{site}] {counts}")


def migrate_leads_csv(site: str, dry: bool):
    p = BASE_DIR / "data" / "prospects" / site / "leads.csv"
    if not p.exists():
        print(f"  [csv:{site}] {p} absent, skip")
        return
    print(f"  [csv:{site}] reading {p}")
    rows = []
    with open(p, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    _dump(BACKUP_BASE, f"{site}-coldemail-csv", rows)

    counts = {}
    for row in rows:
        if not row.get("email"):
            continue
        result = _migrate_one(site, {
            "email":   row.get("email", ""),
            "prenom":  "",
            "nom":     "",
            "societe": row.get("company", ""),
            "tel":     "",
            "notes":   f"scraping {row.get('sector','')} {row.get('location','')} — {row.get('contact_page','')}",
        }, source="scraping_serper", target_state="cold_email", dry=dry)
        counts[result] = counts.get(result, 0) + 1
    print(f"  [csv:{site}] {counts}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["lcr", "mkd", "both"], default="both")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sites = ["lcr", "mkd"] if args.site == "both" else [args.site]
    mode = "DRY-RUN" if args.dry_run else "WRITE"
    print(f"=== Migration acquisition_contacts ({mode}) — sites={sites} ===")
    print(f"  Backup dir: {BACKUP_BASE}")
    if not args.dry_run:
        BACKUP_BASE.mkdir(parents=True, exist_ok=True)

    for site in sites:
        print(f"\n--- {site.upper()} ---")
        migrate_prm(site, args.dry_run)
        migrate_crm(site, args.dry_run)
        migrate_leads_csv(site, args.dry_run)

    # Stats finales
    print("\n=== Stats finales ===")
    from acquisition_backend import stats
    for site in sites:
        s = stats(site)
        print(f"  [{site}] total={s['total']}  by_state={s['by_state']}")


if __name__ == "__main__":
    main()
