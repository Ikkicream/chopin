#!/usr/bin/env python3
"""
crm_sync.py — Synchronisation Emelia → Twenty CRM
Détecte les réponses positives dans Emelia et crée/met à jour les contacts dans Twenty.
Par défaut en dry-run. Ajouter --live pour les vraies opérations.

Usage:
  python3 crm_sync.py --dry-run   # Voir ce qui serait synchro
  python3 crm_sync.py --live      # Synchronisation réelle vers Twenty CRM
"""

import sys
import json
import requests
import argparse
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"
SYNC_LOG = BASE_DIR / "memory" / "shared" / "crm-sync-log.json"
TWENTY_URL = "http://localhost:3000/graphql"

# Mots-clés indiquant une réponse positive dans un email de reply
POSITIVE_KEYWORDS = [
    "intéressé", "interesse", "intéressant", "interessant",
    "appel", "call", "meeting", "rdv", "rendez-vous",
    "disponible", "dispo", "ok", "accord",
    "oui", "yes", "absolument", "parfait",
    "15 min", "15min", "visio", "zoom",
    "quand", "lundi", "mardi", "mercredi", "jeudi", "vendredi",
]


def load_env():
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip()
    return env


def emelia_query(api_key: str, query: str) -> dict:
    resp = requests.post(
        "https://api.emelia.io/graphql",
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        json={"query": query},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise ValueError(f"Emelia error: {data['errors']}")
    return data.get("data", {})


def twenty_query(api_key: str, query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(
        TWENTY_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise ValueError(f"Twenty CRM error: {data['errors']}")
    return data.get("data", {})


def get_replied_contacts(api_key: str) -> list[dict]:
    """
    Récupère les contacts ayant répondu dans Emelia.
    Note: l'API Emelia ne retourne pas le corps des réponses via GraphQL.
    On compte sur le statut REPLIED des contacts.
    """
    data = emelia_query(api_key, """
    {
      contacts(query: "status:REPLIED") {
        _id
        email
        status
        firstName
        lastName
      }
    }
    """)
    replied = data.get("contacts", [])
    return replied


def check_existing_person(api_key: str, email: str) -> str | None:
    """Vérifie si un contact existe déjà dans Twenty CRM par email."""
    data = twenty_query(api_key, f"""
    {{
      people(filter: {{ emails: {{ primaryEmail: {{ eq: "{email}" }} }} }}) {{
        edges {{
          node {{
            id
            name {{ firstName lastName }}
          }}
        }}
      }}
    }}
    """)
    edges = data.get("people", {}).get("edges", [])
    if edges:
        return edges[0]["node"]["id"]
    return None


def create_crm_contact(api_key: str, contact: dict, source: str = "emelia-replied") -> dict:
    """Crée un contact dans Twenty CRM."""
    email = contact.get("email", "")
    first = contact.get("firstName") or email.split("@")[0].capitalize()
    last = contact.get("lastName") or ""
    domain = email.split("@")[-1] if "@" in email else ""

    data = twenty_query(api_key, """
    mutation CreatePerson($data: PersonCreateInput!) {
      createPerson(data: $data) {
        id
        name { firstName lastName }
        emails { primaryEmail }
      }
    }
    """, variables={
        "data": {
            "name": {"firstName": first, "lastName": last},
            "emails": {"primaryEmail": email},
            "jobTitle": f"Réponse Emelia ({source})",
        }
    })
    return data.get("createPerson", {})


def update_crm_contact_note(api_key: str, person_id: str, note: str) -> bool:
    """Ajoute une note sur un contact existant dans Twenty CRM."""
    # Twenty CRM: création d'une note via l'objet Note
    data = twenty_query(api_key, """
    mutation CreateNote($data: NoteCreateInput!) {
      createNote(data: $data) {
        id
      }
    }
    """, variables={
        "data": {
            "title": "Réponse Emelia",
            "body": note,
        }
    })
    return bool(data.get("createNote", {}).get("id"))


def load_sync_log() -> dict:
    try:
        with open(SYNC_LOG) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"synced_ids": [], "entries": []}


def save_sync_log(log: dict):
    SYNC_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SYNC_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Sync Emelia → Twenty CRM")
    parser.add_argument("--live", action="store_true", help="Mode live (défaut: dry-run)")
    args = parser.parse_args()

    dry_run = not args.live

    if dry_run:
        print("⚠ MODE DRY-RUN — aucune donnée ne sera envoyée à Twenty CRM")
        print("  Ajouter --live pour la synchronisation réelle\n")

    env = load_env()
    emelia_key = env.get("EMELIA_API_KEY", "")
    twenty_key = env.get("TWENTY_API_KEY", "")

    # 1. Récupérer les contacts qui ont répondu dans Emelia
    print("[crm_sync] Récupération des réponses Emelia...")
    try:
        replied_contacts = get_replied_contacts(emelia_key)
        print(f"  → {len(replied_contacts)} contact(s) avec statut REPLIED")
    except Exception as e:
        print(f"  ⚠ Erreur Emelia: {e}")
        replied_contacts = []

    if not replied_contacts:
        print("[crm_sync] Aucun nouveau contact à synchroniser")
        # Quand même afficher les stats Twenty
        try:
            data = twenty_query(twenty_key, "{ people { edges { node { id } } } }")
            count = len(data.get("people", {}).get("edges", []))
            print(f"[crm_sync] Twenty CRM: {count} contacts existants")
        except Exception as e:
            print(f"  ⚠ Impossible d'accéder à Twenty CRM: {e}")
        return

    # 2. Charger le log de sync (éviter les doublons)
    sync_log = load_sync_log()
    already_synced = set(sync_log.get("synced_ids", []))

    new_contacts = [c for c in replied_contacts if c["_id"] not in already_synced]
    print(f"[crm_sync] Nouveaux à synchroniser: {len(new_contacts)} (ignorés déjà synchro: {len(replied_contacts) - len(new_contacts)})")

    if not new_contacts:
        print("[crm_sync] Tous les contacts sont déjà synchronisés")
        return

    # 3. Synchroniser vers Twenty CRM
    synced = 0
    updated = 0
    errors = 0

    for contact in new_contacts:
        email = contact.get("email", "")
        print(f"\n  → Traitement: {email}")

        if dry_run:
            print(f"    [DRY-RUN] Serait créé/mis à jour dans Twenty CRM")
            print(f"    Données: firstName={contact.get('firstName')}, lastName={contact.get('lastName')}")
            continue

        try:
            # Vérifier si le contact existe déjà
            existing_id = check_existing_person(twenty_key, email)

            if existing_id:
                print(f"    Contact existant (id: {existing_id}) — ajout note")
                note = f"Réponse détectée via Emelia le {datetime.now(timezone.utc).strftime('%d/%m/%Y')}"
                update_crm_contact_note(twenty_key, existing_id, note)
                updated += 1
            else:
                print(f"    Nouveau contact — création dans Twenty CRM")
                created = create_crm_contact(twenty_key, contact)
                if created.get("id"):
                    print(f"    ✓ Créé: {created['id']}")
                    synced += 1
                else:
                    print(f"    ⚠ Création échouée")
                    errors += 1

            # Marquer comme synchronisé
            sync_log["synced_ids"].append(contact["_id"])
            sync_log["entries"].append({
                "date": datetime.now(timezone.utc).isoformat(),
                "emelia_id": contact["_id"],
                "email": email,
                "action": "updated" if existing_id else "created",
            })

        except Exception as e:
            print(f"    ⚠ Erreur: {e}")
            errors += 1

    if not dry_run:
        save_sync_log(sync_log)
        print(f"\n[crm_sync] Résumé: {synced} créés, {updated} mis à jour, {errors} erreurs")
    else:
        print(f"\n[crm_sync] DRY-RUN terminé — {len(new_contacts)} contact(s) seraient synchronisés")


if __name__ == "__main__":
    main()
