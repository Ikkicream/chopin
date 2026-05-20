#!/usr/bin/env python3
"""
emelia_to_twenty.py — Sync Emelia activities → Twenty CRM.

Chaque soir 19h UTC :
  1. GET Emelia campaigns activities (clicks, replies, opens)
  2. Pour chaque cliqueur/répondeur : créer/update contact dans Twenty CRM
  3. Tagger : lead_hot (reply), lead_warm (click), contacted (open)
  4. Notifier Telegram pour les replies

Cron : 0 19 * * * cd /home/autoblog/genesis && set -a && source .env && set +a && python3 scripts/emelia_to_twenty.py

Usage : python3 scripts/emelia_to_twenty.py [--dry-run]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent

# Load env
def load_env():
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip("'\"")
                os.environ.setdefault(k, v)

load_env()

EMELIA_API_KEY = os.environ.get("EMELIA_API_KEY", "")
TWENTY_API_KEY = os.environ.get("TWENTY_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

EMELIA_URL = "https://api.emelia.io/graphql"
TWENTY_URL = "http://localhost:3000/api"

SYNC_LOG = BASE_DIR / "memory" / "shared" / "crm-sync-log.json"


def emelia_query(query, variables=None):
    """Execute Emelia GraphQL query."""
    headers = {"Authorization": f"Bearer {EMELIA_API_KEY}", "Content-Type": "application/json"}
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    r = requests.post(EMELIA_URL, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("data", {})


def get_campaign_activities():
    """Get all campaign activities from last 24h."""
    query = """
    query {
      campaigns {
        _id
        name
        status
      }
    }
    """
    data = emelia_query(query)
    campaigns = data.get("campaigns", [])

    # For each campaign, get contacts with activity
    all_activities = []
    for camp in campaigns:
        contacts_query = """
        query($campaignId: ID!) {
          contactsList(campaignId: $campaignId, filter: {hasReplied: true}) {
            contacts {
              email
              firstName
              lastName
              company
              hasReplied
              hasClicked
              hasOpened
              lastActivityDate
            }
          }
        }
        """
        try:
            contacts_data = emelia_query(contacts_query, {"campaignId": camp["_id"]})
            contacts = contacts_data.get("contactsList", {}).get("contacts", [])
            for c in contacts:
                c["campaign"] = camp["name"]
                all_activities.append(c)
        except Exception as e:
            print(f"  Warning: campaign {camp['name']}: {e}")

    return all_activities


def create_twenty_contact(contact, tag):
    """Create or update contact in Twenty CRM."""
    headers = {"Authorization": f"Bearer {TWENTY_API_KEY}", "Content-Type": "application/json"}

    # Search if contact exists
    search_url = f"{TWENTY_URL}/objects/people?filter[email][eq]={contact['email']}"
    r = requests.get(search_url, headers=headers, timeout=10)

    person_data = {
        "name": {"firstName": contact.get("firstName", ""), "lastName": contact.get("lastName", "")},
        "emails": {"primaryEmail": contact["email"]},
        "company": contact.get("company", ""),
        "jobTitle": tag,
    }

    if r.status_code == 200 and r.json().get("data", {}).get("people", []):
        # Update existing
        person_id = r.json()["data"]["people"][0]["id"]
        requests.patch(f"{TWENTY_URL}/objects/people/{person_id}",
                      json=person_data, headers=headers, timeout=10)
        return "updated", person_id
    else:
        # Create new
        r2 = requests.post(f"{TWENTY_URL}/objects/people",
                          json=person_data, headers=headers, timeout=10)
        if r2.status_code in (200, 201):
            return "created", r2.json().get("data", {}).get("id", "")
        return "error", str(r2.status_code)


def notify_telegram(message):
    """Send notification to Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"[emelia→twenty] {datetime.now(timezone.utc).isoformat()}")

    if not EMELIA_API_KEY:
        print("  ERROR: EMELIA_API_KEY not set")
        sys.exit(1)
    if not TWENTY_API_KEY:
        print("  ERROR: TWENTY_API_KEY not set")
        sys.exit(1)

    # Get activities
    activities = get_campaign_activities()
    print(f"  {len(activities)} contacts with activity")

    if not activities:
        print("  No new activities")
        return

    synced = []
    for contact in activities:
        # Determine tag based on activity
        if contact.get("hasReplied"):
            tag = "lead_hot"
        elif contact.get("hasClicked"):
            tag = "lead_warm"
        elif contact.get("hasOpened"):
            tag = "contacted"
        else:
            continue

        if args.dry_run:
            print(f"  DRY-RUN: {contact['email']} → {tag}")
            continue

        action, pid = create_twenty_contact(contact, tag)
        synced.append({
            "email": contact["email"],
            "tag": tag,
            "action": action,
            "campaign": contact.get("campaign", ""),
            "date": datetime.now(timezone.utc).isoformat()
        })
        print(f"  {action}: {contact['email']} → {tag}")

        # Telegram alert for hot leads
        if tag == "lead_hot":
            name = f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip()
            company = contact.get("company", "")
            notify_telegram(
                f"🔥 *Nouveau lead hot!*\n"
                f"• {name} ({company})\n"
                f"• {contact['email']}\n"
                f"• Campagne: {contact.get('campaign', '?')}\n"
                f"• A répondu à l'email"
            )

    # Save sync log
    if synced and not args.dry_run:
        log = []
        if SYNC_LOG.exists():
            try:
                log = json.loads(SYNC_LOG.read_text())
            except:
                log = []
        log.extend(synced)
        # Keep last 500 entries
        log = log[-500:]
        SYNC_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False))

    print(f"  Synced: {len(synced)} contacts")


if __name__ == "__main__":
    main()
