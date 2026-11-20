#!/usr/bin/env python3
"""
campaign_manager.py — Gestionnaire de campagnes Emelia depuis CSV
IMPORTANT: N'envoie AUCUN email. Seulement gestion des listes et campagnes.
Par défaut en mode dry-run. Ajouter --live pour les vraies opérations.

Usage:
  python3 campaign_manager.py --action analyze          # Analyser le CSV
  python3 campaign_manager.py --action create-list      # Créer une liste de contacts (dry-run)
  python3 campaign_manager.py --action create-list --live # Créer la liste pour de vrai
  python3 campaign_manager.py --action status           # Voir l'état des campagnes
"""

import os
import sys
import csv
import json
import requests
import argparse
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

# ── Config ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"
CSV_FILE = BASE_DIR / "context" / "shared" / "prospects.csv"
CAMPAIGN_LOG = BASE_DIR / "memory" / "shared" / "campaigns-log.json"

BATCH_SIZE = 50        # Max contacts par import (limite delivrabilité)
DAILY_LIMIT = 50       # Max emails/jour (règle cold email)
VALID_STATUSES = {"valid"}
VALID_CLASSIFICATIONS = {"B2B (domain)", "B2B (company)", "professional"}


def load_env():
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip()
    return env


def emelia_query(api_key: str, query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(
        "https://api.emelia.io/graphql",
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise ValueError(f"Emelia GraphQL error: {data['errors']}")
    return data.get("data", {})


def load_csv_prospects(max_rows: int = None) -> list[dict]:
    """
    Charge le CSV prospects et filtre les emails B2B valides.
    Format CSV: EMAIL STATUS;EMAIL OCCURRENCE FOUND;EMAIL CLASSIFICATION HELPER;EMAIL
    """
    prospects = []
    try:
        with open(CSV_FILE, encoding="utf-8-sig") as f:
            reader = csv.reader(f, delimiter=";")
            header = next(reader)  # Skip header

            for i, row in enumerate(reader):
                if max_rows and i >= max_rows:
                    break
                if len(row) < 4:
                    continue

                status = row[0].strip().lower()
                occurrence = row[1].strip().lower()
                classification = row[2].strip()
                email = row[3].strip().lower()

                # Filtres qualité
                if status not in VALID_STATUSES:
                    continue
                if occurrence != "unique":
                    continue
                if not email or "@" not in email:
                    continue

                # Extraction du domaine pour le nom d'entreprise approximatif
                domain = email.split("@")[-1].replace(".com", "").replace(".fr", "").replace(".net", "")

                prospects.append({
                    "email": email,
                    "status": status,
                    "classification": classification,
                    "domain": domain,
                    "is_b2b": any(b2b in classification for b2b in ["B2B", "professional"]),
                })

    except FileNotFoundError:
        print(f"⚠ CSV non trouvé: {CSV_FILE}")
        return []

    return prospects


def analyze_csv():
    """Analyse le CSV et affiche les statistiques."""
    print(f"Analyse du CSV: {CSV_FILE}")
    all_prospects = load_csv_prospects()

    total = len(all_prospects)
    b2b = [p for p in all_prospects if p["is_b2b"]]
    classifications = defaultdict(int)
    domains = defaultdict(int)

    for p in all_prospects:
        classifications[p["classification"]] += 1
        domains[p["domain"]] += 1

    # Top domaines (pour identifier les entreprises avec plusieurs contacts)
    multi_contact_domains = {d: c for d, c in domains.items() if c >= 3}

    print(f"\n{'='*60}")
    print(f"ANALYSE CSV PROSPECTS")
    print(f"{'='*60}")
    print(f"Total contacts valides (unique B2B): {total:,}")
    print(f"  → Identifiés B2B: {len(b2b):,} ({len(b2b)/total*100:.1f}%)")
    print(f"\nClassification:")
    for cls, count in sorted(classifications.items(), key=lambda x: -x[1])[:10]:
        print(f"  {cls}: {count:,}")

    print(f"\nDomaines avec 3+ contacts: {len(multi_contact_domains):,}")

    # Plan d'import progressif
    batches = []
    days_needed = total // DAILY_LIMIT
    print(f"\n{'='*60}")
    print(f"PLAN D'IMPORT PROGRESSIF")
    print(f"{'='*60}")
    print(f"Limite: {DAILY_LIMIT} contacts/jour")
    print(f"Total à importer: {total:,}")
    print(f"Durée estimée: {days_needed} jours (~{days_needed//7} semaines)")
    print(f"\nPhases recommandées:")
    print(f"  Phase 1 (J1-J7):   5 contacts/jour — Test delivrabilité")
    print(f"  Phase 2 (J8-J14):  15 contacts/jour — Montée progressive")
    print(f"  Phase 3 (J15-J21): 30 contacts/jour — Accélération")
    print(f"  Phase 4 (J22+):    50 contacts/jour — Régime nominal")

    return all_prospects


def create_contact_list(api_key: str, prospects: list[dict], list_name: str, dry_run: bool = True) -> dict:
    """
    Crée une liste de contacts dans Emelia.
    En dry-run: simule seulement.
    En live: appelle l'API Emelia pour créer la liste.
    """
    print(f"\nCréation liste: '{list_name}' ({len(prospects)} contacts)")

    if dry_run:
        print("  [DRY-RUN] Simulation — aucune donnée envoyée à Emelia")
        print(f"  Contacts qui seraient importés: {len(prospects)}")
        for p in prospects[:5]:
            print(f"    - {p['email']} ({p.get('classification', 'unknown')})")
        if len(prospects) > 5:
            print(f"    ... et {len(prospects)-5} autres")
        return {"dry_run": True, "would_create": list_name, "count": len(prospects)}

    # Mode LIVE — création réelle de la liste
    # Note: Emelia ne semble pas exposer une mutation de création de liste via GraphQL public
    # On log l'intention pour traitement manuel ou via l'API REST si disponible
    print("  [LIVE] Tentative de création via Emelia API...")
    try:
        result = emelia_query(api_key, f"""
        mutation {{
          createContactList(name: "{list_name}") {{
            _id
            name
          }}
        }}
        """)
        list_id = result.get("createContactList", {}).get("_id")
        if list_id:
            print(f"  ✓ Liste créée: {list_id}")
            # Log chaque prospect dans le dashboard leads
            for p in prospects:
                log_lead(
                    email=p["email"],
                    status="ok",
                    source=list_name,
                    campaign_name=list_name,
                )
            print(f"  ✓ {len(prospects)} leads loggés dans le dashboard")
            return {"created": True, "id": list_id, "name": list_name}
        else:
            # Log comme erreur
            for p in prospects:
                log_lead(email=p["email"], status="error", source=list_name,
                         error_msg="no id returned from Emelia")
            print("  ⚠ Réponse inattendue")
            return {"created": False, "error": "no id returned"}
    except Exception as e:
        for p in prospects:
            log_lead(email=p["email"], status="error", source=list_name, error_msg=str(e))
        print(f"  ⚠ Erreur création liste: {e}")
        return {"created": False, "error": str(e)}


def get_campaign_status(api_key: str) -> None:
    """Affiche le statut complet de toutes les campagnes."""
    print("Récupération statut campagnes Emelia...")

    data = emelia_query(api_key, """
    {
      campaigns {
        _id
        name
        status
        createdAt
      }
    }
    """)
    campaigns = data.get("campaigns", [])

    lists_data = emelia_query(api_key, """
    {
      contact_lists {
        _id
        name
      }
    }
    """)
    lists = lists_data.get("contact_lists", [])

    print(f"\n{'='*60}")
    print(f"STATUT CAMPAGNES EMELIA")
    print(f"{'='*60}")

    if not campaigns:
        print("Aucune campagne")
    else:
        for camp in campaigns:
            created_ts = int(camp.get("createdAt", 0)) // 1000
            created_dt = datetime.fromtimestamp(created_ts, tz=timezone.utc).strftime("%d/%m/%Y")
            status_icon = {"RUNNING": "🟢 ACTIVE", "PAUSED": "⏸ PAUSÉE", "DONE": "✅ TERMINÉE", "DRAFT": "📝 BROUILLON"}.get(camp["status"], camp["status"])
            print(f"\n  [{status_icon}] {camp['name']}")
            print(f"     ID: {camp['_id']}")
            print(f"     Créée: {created_dt}")

    print(f"\n{'='*60}")
    print(f"LISTES DE CONTACTS")
    print(f"{'='*60}")
    for cl in lists:
        # Récupérer le count
        try:
            detail = emelia_query(api_key, f"""
            {{
              contact_list(id: "{cl['_id']}") {{
                contacts {{ count }}
              }}
            }}
            """)
            count = detail.get("contact_list", {}).get("contacts", {}).get("count", "?")
        except Exception:
            count = "?"
        print(f"  📋 {cl['name']}: {count} contacts (ID: {cl['_id']})")


LEADS_API = "http://localhost:8081/api/leads/ingest"


def log_lead(email: str, status: str, source: str, gsm: str = "",
             first_name: str = "", last_name: str = "", campaign_name: str = "",
             error_msg: str = ""):
    """Envoie un lead au dashboard leads (http://localhost:8081)."""
    try:
        requests.post(LEADS_API, json={
            "source": source,
            "email": email,
            "gsm": gsm,
            "firstName": first_name,
            "lastName": last_name,
            "status": status,
            "campaign_name": campaign_name,
            "error_msg": error_msg,
        }, timeout=3)
    except Exception:
        pass  # Non-bloquant


def log_campaign_action(action: str, details: dict):
    """Log les actions dans campaigns-log.json."""
    CAMPAIGN_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CAMPAIGN_LOG) as f:
            log = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log = {"entries": []}

    log["entries"].append({
        "date": datetime.now(timezone.utc).isoformat(),
        "action": action,
        **details,
    })

    with open(CAMPAIGN_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Gestionnaire campagnes Emelia")
    parser.add_argument("--action", choices=["analyze", "create-list", "status"], default="status",
                        help="Action à effectuer")
    parser.add_argument("--live", action="store_true",
                        help="Mode live (sans ce flag: dry-run par défaut)")
    parser.add_argument("--batch", type=int, default=50,
                        help="Taille du batch de contacts (défaut: 50)")
    parser.add_argument("--list-name", default="Genesis_LCR_Batch1",
                        help="Nom de la liste à créer")
    args = parser.parse_args()

    dry_run = not args.live

    if dry_run:
        print("⚠ MODE DRY-RUN — aucune donnée ne sera envoyée à Emelia")
        print("  Ajouter --live pour les vraies opérations\n")

    env = load_env()
    api_key = env.get("EMELIA_API_KEY", "")

    if args.action == "analyze":
        prospects = analyze_csv()
        log_campaign_action("analyze_csv", {"total": len(prospects), "dry_run": dry_run})

    elif args.action == "create-list":
        # Charger le premier batch de prospects B2B valides
        all_prospects = load_csv_prospects()
        b2b_only = [p for p in all_prospects if p["is_b2b"]]
        batch = b2b_only[:args.batch]

        print(f"Batch sélectionné: {len(batch)} prospects B2B valides")
        result = create_contact_list(api_key, batch, args.list_name, dry_run=dry_run)
        log_campaign_action("create_contact_list", {
            "list_name": args.list_name,
            "count": len(batch),
            "dry_run": dry_run,
            "result": result,
        })

    elif args.action == "status":
        get_campaign_status(api_key)


if __name__ == "__main__":
    main()
