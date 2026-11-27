#!/usr/bin/env python3
"""
tally_to_prm.py — Sync horaire des soumissions Tally → PRM DuckDB.

Filet de sécurité pour les leads : si le webhook Tally a un blip, on récupère via API.
Dédup par submission_id (stocké dans une table de tracking) + par email côté PRM.

Pour chaque site configuré (clé `TALLY_API_KEY_<SITE>` présente dans .env) :
  1. GET /forms → liste tous les formulaires du compte
  2. Pour chaque formulaire → GET /submissions depuis la dernière sync
  3. Pour chaque soumission jamais vue → extract champs → insert PRM (skip si email dup)
  4. Sauvegarde l'ID de la dernière soumission vue dans memory/shared/tally-sync-state.json

Usage :
  python3 scripts/tally_to_prm.py                # tous les sites configurés
  python3 scripts/tally_to_prm.py --site lcr     # un seul site
  python3 scripts/tally_to_prm.py --dry-run      # ne touche pas le PRM

Cron : 0 * * * * (chaque heure)
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from tally_client import list_forms, list_submissions, extract_lead_fields, get_api_key
from acquisition_backend import create as acq_create, find_by_email as acq_find_by_email


def _tally_dual_write_pool(site, email, fields, form_id):
    """DUAL-WRITE pool 2026-05-22."""
    try:
        import contacts_pool_backend as _cpb
        pool_cid = _cpb.create_in_pool({
            "email":   email,
            "prenom":  fields.get("prenom") or fields.get("firstName") or "",
            "nom":     fields.get("nom") or fields.get("lastName") or "",
            "societe": fields.get("societe") or fields.get("company") or "",
            "tel":     fields.get("tel") or fields.get("phone") or "",
        }, primary_source="tally")
        if pool_cid:
            _cpb.upsert_site_history(pool_cid, site, state="lead",
                source="tally", by="tally_sync")
    except Exception as _e:
        print(f"  [tally][pool dual-write] {_e}")

SYNC_STATE = BASE_DIR / "memory" / "shared" / "tally-sync-state.json"
SYNC_STATE.parent.mkdir(parents=True, exist_ok=True)

SITES = ["lcr", "mkd"]


def _load_state() -> dict:
    if SYNC_STATE.exists():
        try:
            return json.loads(SYNC_STATE.read_text())
        except Exception:
            return {}
    return {}


def _save_state(state: dict) -> None:
    SYNC_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _email_in_acquisition(site: str, email: str) -> bool:
    return acq_find_by_email(site, email) is not None


def sync_site(site: str, dry_run: bool = False) -> dict:
    """Sync les soumissions Tally d'un site → PRM. Retourne stats."""
    print(f"[tally→prm] === {site.upper()} ===")
    try:
        get_api_key(site)
    except RuntimeError as e:
        print(f"  Skip : {e}")
        return {"site": site, "skipped": True, "reason": "no_api_key"}

    state = _load_state()
    site_state = state.setdefault(site, {"forms": {}})

    try:
        forms = list_forms(site)
    except Exception as e:
        print(f"  Erreur list_forms: {e}")
        return {"site": site, "error": str(e)}

    total_new, total_dup_email, total_already_seen = 0, 0, 0
    for form in forms:
        form_id = form.get("id") or form.get("formId") or ""
        if not form_id:
            continue
        form_name = form.get("name", "")
        last_seen_id = site_state["forms"].get(form_id, {}).get("last_submission_id", "")
        print(f"  Form '{form_name}' ({form_id}) — last_seen={last_seen_id[:8] or '(none)'}")

        try:
            submissions = list_submissions(site, form_id, page=1, limit=100)
        except Exception as e:
            print(f"    Erreur submissions: {e}")
            continue

        if not submissions:
            print("    (aucune soumission)")
            continue

        new_count = 0
        latest_id = last_seen_id

        # On parcourt du plus récent au plus ancien — stop dès qu'on retrouve last_seen
        for sub in submissions:
            sub_id = sub.get("id") or sub.get("submissionId", "")
            if sub_id == last_seen_id:
                total_already_seen += 1
                break

            lead = extract_lead_fields(sub)
            if not lead["email"]:
                continue  # pas de mail = pas un lead exploitable

            if not latest_id:
                latest_id = sub_id

            if _email_in_acquisition(site, lead["email"]):
                total_dup_email += 1
                continue

            if dry_run:
                print(f"    DRY: {lead['email']} ({lead['firstName']} {lead['lastName']})")
            else:
                _tally_dual_write_pool(site, email, fields, form_id) if "email" in dir() and "fields" in dir() and "form_id" in dir() else None; acq_create(site, {
                    "email":   lead["email"],
                    "prenom":  lead["firstName"],
                    "nom":     lead["lastName"],
                    "societe": lead["company"],
                    "tel":     lead.get("phone", ""),
                    "notes":   f"tally:{form_name} submission_id={lead.get('submission_id','')}",
                    "state":   "lead",
                    "source":  f"tally:{form_name}",
                }, by="tally_sync")
                print(f"    +acq[lead]: {lead['email']} ({lead['firstName']} {lead['lastName']}) — {form_name}")
            new_count += 1

        total_new += new_count

        if latest_id and latest_id != last_seen_id:
            site_state["forms"][form_id] = {
                "form_name": form_name,
                "last_submission_id": latest_id,
                "last_sync_at": datetime.now(timezone.utc).isoformat(),
            }

    if not dry_run:
        state[site] = site_state
        _save_state(state)

    print(f"  → {total_new} new · {total_dup_email} dédoublonnés · {total_already_seen} déjà vus")
    return {"site": site, "new": total_new, "dup_email": total_dup_email, "already_seen": total_already_seen}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=SITES, help="un seul site (par défaut: tous)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    targets = [args.site] if args.site else SITES
    print(f"[tally→prm] {datetime.now(timezone.utc).isoformat()} sites={targets}")

    for s in targets:
        try:
            sync_site(s, dry_run=args.dry_run)
        except Exception as e:
            print(f"  Erreur globale {s}: {e}")


if __name__ == "__main__":
    main()
