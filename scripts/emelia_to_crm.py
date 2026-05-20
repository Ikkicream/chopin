#!/usr/bin/env python3
"""
emelia_to_crm.py — Sync Emelia activities → CRM interne DuckDB.

Remplace l'ancien emelia_to_twenty.py (Twenty CRM tué le 2026-05-20).

Chaque soir 19h UTC :
  1. GET Emelia campaigns + contacts ayant une activité
  2. Pour chaque cliqueur/répondeur :
     - Détermine le site (LCR si campagne préfixée "LCR-…" ou mailbox @leclientroi, sinon MKD)
     - Upsert le contact dans data/crm/{site}.duckdb (table contacts)
     - Ajoute une interaction (type=email_open/click/reply)
     - Statut : "lead_hot" si reply, "lead_warm" si click, "contacted" si open uniquement
  3. Alerte Telegram pour les replies

Usage : python3 scripts/emelia_to_crm.py [--dry-run]
Cron  : 0 19 * * * (déjà actif)
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from acquisition_backend import create as acq_create, find_by_email as acq_find, change_state as acq_change_state, STATE_RANK


def load_env():
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v.strip("'\""))

load_env()

EMELIA_API_KEY = os.environ.get("EMELIA_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

EMELIA_URL = "https://api.emelia.io/graphql"
SYNC_LOG = BASE_DIR / "memory" / "shared" / "crm-sync-log.json"


def emelia_query(query, variables=None):
    headers = {"Authorization": f"Bearer {EMELIA_API_KEY}", "Content-Type": "application/json"}
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    r = requests.post(EMELIA_URL, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("data", {})


def detect_site(campaign_name: str, email: str = "") -> str:
    """Devine le site à partir du nom de campagne ou de la mailbox d'envoi."""
    n = (campaign_name or "").upper()
    if n.startswith("LCR") or "LCR-" in n or "LECLIENTROI" in n.replace(" ", ""):
        return "lcr"
    if n.startswith("MKD") or "MKD-" in n or "MKDGROUPE" in n.replace(" ", ""):
        return "mkd"
    # Fallback : domaine de l'email
    if email.endswith("@leclientroi.com"):
        return "lcr"
    if email.endswith("@mkdgroupe.com"):
        return "mkd"
    return "lcr"  # default


def get_campaign_activities():
    """Récupère toutes les campagnes + contacts ayant une activité."""
    data = emelia_query("query { campaigns { _id name status } }")
    campaigns = data.get("campaigns", [])

    all_activities = []
    for camp in campaigns:
        try:
            contacts_data = emelia_query(
                """query($campaignId: ID!) {
                  contactsList(campaignId: $campaignId, filter: {hasReplied: true}) {
                    contacts { email firstName lastName company hasReplied hasClicked hasOpened lastActivityDate }
                  }
                }""",
                {"campaignId": camp["_id"]},
            )
            contacts = contacts_data.get("contactsList", {}).get("contacts", []) or []
            for c in contacts:
                c["campaign"] = camp["name"]
                all_activities.append(c)
        except Exception as e:
            print(f"  Warning campagne {camp.get('name')}: {e}")
    return all_activities


def upsert_contact_with_interaction(site: str, contact: dict, target_state: str, interaction_type: str, campaign: str) -> dict:
    """Crée ou promote le contact dans acquisition_contacts.

    Transitions :
      - email_open  → cold_email reste cold_email (juste interaction loggée via notes)
      - email_click → cold_email/lead/prm → prm (si current_rank < prm)
      - email_reply → cold_email/prm → lead (si current_rank < lead)

    Retourne {action: created|promoted|kept, ...}.
    """
    email = contact.get("email", "").strip().lower()
    if not email:
        return {"action": "skipped", "reason": "no_email"}

    existing = acq_find(site, email)
    if existing:
        current_rank = STATE_RANK.get(existing["state"], 0)
        target_rank = STATE_RANK.get(target_state, 0)
        if existing["state"] == "blacklisted":
            return {"action": "kept_blacklisted", "id": existing["id"]}
        if target_rank > current_rank:
            acq_change_state(site, existing["id"], target_state, by="emelia_sync",
                             note=f"campaign={campaign} interaction={interaction_type}")
            return {"action": "promoted", "id": existing["id"], "state": target_state, "site": site}
        return {"action": "kept", "id": existing["id"], "state": existing["state"], "site": site}

    # Création nouveau contact avec l'état déduit (souvent prm via click, lead via reply)
    res = acq_create(site, {
        "email":   email,
        "prenom":  contact.get("firstName", ""),
        "nom":     contact.get("lastName", ""),
        "societe": contact.get("company", ""),
        "notes":   f"emelia campaign={campaign} interaction={interaction_type}",
        "state":   target_state,
        "source":  f"emelia:{campaign}"[:60],
    }, by="emelia_sync")
    return {"action": "created", "id": res.get("id", ""), "state": target_state, "site": site}


def notify_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"[emelia→crm] {datetime.now(timezone.utc).isoformat()}")

    if not EMELIA_API_KEY:
        print("  ERROR: EMELIA_API_KEY not set")
        sys.exit(1)

    activities = get_campaign_activities()
    print(f"  {len(activities)} contacts avec activité")
    if not activities:
        return

    synced = []
    for contact in activities:
        # Mapping events Emelia → états acquisition_contacts
        if contact.get("hasReplied"):
            target_state, itype = "lead", "email_reply"
        elif contact.get("hasClicked"):
            target_state, itype = "prm", "email_click"
        elif contact.get("hasOpened"):
            # Open seul = signal trop faible, on ne promote pas
            continue
        else:
            continue

        site = detect_site(contact.get("campaign", ""), contact.get("email", ""))
        if args.dry_run:
            print(f"  DRY-RUN: [{site}] {contact.get('email')} → {target_state}")
            continue

        try:
            r = upsert_contact_with_interaction(site, contact, target_state, itype, contact.get("campaign", ""))
            r["email"]   = contact.get("email", "")
            r["target_state"] = target_state
            r["campaign"] = contact.get("campaign", "")
            r["date"]    = datetime.now(timezone.utc).isoformat()
            synced.append(r)
            print(f"  {r['action']}: [{site}] {contact.get('email')} → {target_state}")
        except Exception as e:
            print(f"  ERROR {contact.get('email')}: {e}")

        if target_state == "lead":
            name = f"{contact.get('firstName','')} {contact.get('lastName','')}".strip()
            company = contact.get("company", "")
            notify_telegram(
                f"🔥 *Lead HOT* — {site.upper()}\n"
                f"• {name} ({company})\n"
                f"• {contact.get('email','')}\n"
                f"• Campagne: {contact.get('campaign','?')}\n"
                f"• A répondu — voir le CRM"
            )

    # Save sync log (dernier 500 entries)
    if synced and not args.dry_run:
        log = []
        if SYNC_LOG.exists():
            try:
                log = json.loads(SYNC_LOG.read_text())
            except Exception:
                log = []
        log.extend(synced)
        log = log[-500:]
        SYNC_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2))

    print(f"  Synced: {len(synced)} contacts")


if __name__ == "__main__":
    main()
