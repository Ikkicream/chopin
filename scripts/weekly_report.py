#!/usr/bin/env python3
"""Weekly report: Monday 8h — pending leads not yet contacted."""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
import requests
import duckdb

BASE_DIR = Path(__file__).parent.parent

for line in open(BASE_DIR / ".env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v.strip("'\""))

BOT_TOKEN = os.environ.get("CHEFFER_TELEGRAM_BOT", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def get_pending_leads(site):
    db_path = BASE_DIR / "data" / "crm" / f"prm_{site}.duckdb"
    if not db_path.exists():
        return []
    conn = duckdb.connect(str(db_path))
    try:
        result = conn.execute(
            "SELECT firstName, lastName, email, company, campaign, created_at FROM prm_contacts WHERE transferred = FALSE ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        conn.close()
        return [{"name": (r[0] or "") + " " + (r[1] or ""), "email": r[2], "company": r[3] or "", "campaign": r[4] or "", "date": str(r[5])[:10]} for r in result]
    except:
        conn.close()
        return []

def get_pending_crm(site):
    db_path = BASE_DIR / "data" / "crm" / f"{site}.duckdb"
    if not db_path.exists():
        return []
    conn = duckdb.connect(str(db_path))
    try:
        result = conn.execute(
            "SELECT prenom, nom, email, tel, societe, statut, created_at FROM contacts WHERE statut = 'nouveau' ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        conn.close()
        return [{"name": (r[0] or "") + " " + (r[1] or ""), "email": r[2], "tel": r[3] or "", "company": r[4] or "", "statut": r[5], "date": str(r[6])[:10]} for r in result]
    except:
        conn.close()
        return []

def main():
    msg = "\U0001f4cb *Rapport hebdomadaire — Leads & CRM*\n"
    msg += f"_{datetime.now().strftime('%d/%m/%Y')}_\n\n"

    for site in ["lcr", "mkd"]:
        leads = get_pending_leads(site)
        crm_new = get_pending_crm(site)

        if leads or crm_new:
            msg += f"*{site.upper()}*\n"

            if leads:
                msg += f"\U0001f3af {len(leads)} leads non trait\u00e9s :\n"
                for l in leads[:5]:
                    msg += f"  \u2022 {l['name'].strip()} | {l['company']} | {l['email']}\n"
                if len(leads) > 5:
                    msg += f"  ... et {len(leads) - 5} autres\n"

            if crm_new:
                msg += f"\U0001f4e5 {len(crm_new)} contacts CRM en attente :\n"
                for c in crm_new[:5]:
                    msg += f"  \u2022 {c['name'].strip()} | {c['company']} | {c['tel']}\n"
                if len(crm_new) > 5:
                    msg += f"  ... et {len(crm_new) - 5} autres\n"

            msg += "\n"

    if "leads non" not in msg and "contacts CRM" not in msg:
        msg += "\u2705 Aucun lead ou contact en attente. Tout est trait\u00e9 !"

    if BOT_TOKEN and CHAT_ID:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        print("Report sent")
    else:
        print("No bot token")
        print(msg)

if __name__ == "__main__":
    main()
