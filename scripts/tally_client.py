#!/usr/bin/env python3
"""
tally_client.py — Wrapper API REST Tally.so par site.

Chaque site a sa propre clé Tally (ajoutable lors de l'onboarding) :
  - TALLY_API_KEY_LCR
  - TALLY_API_KEY_MKD
  - TALLY_API_KEY_<CODE> pour les futurs sites

Doc Tally : https://developers.tally.so/api-reference/
Auth      : header `Authorization: Bearer <key>`

Endpoints utilisés :
  GET /forms                              → liste des formulaires du compte
  GET /forms/{formId}/submissions         → soumissions paginées
"""

import os
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"
TALLY_BASE_URL = "https://api.tally.so"


def _load_env() -> dict:
    """Lecture paresseuse du .env (ne pollue pas os.environ)."""
    out = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip("'\"")
    return out


def get_api_key(site: str) -> str:
    """Retourne la clé Tally d'un site (ex: 'lcr', 'mkd'). Lève si manquante."""
    env = _load_env()
    env.update(os.environ)
    var = f"TALLY_API_KEY_{site.upper()}"
    key = env.get(var, "")
    if not key:
        raise RuntimeError(f"{var} introuvable dans .env — l'ajouter pour activer la sync Tally du site {site}")
    return key


def list_forms(site: str) -> list[dict]:
    """Liste les formulaires Tally du compte associé au site."""
    key = get_api_key(site)
    r = requests.get(
        f"{TALLY_BASE_URL}/forms",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    # Tally renvoie {"items": [...]} ou directement [...] selon version
    if isinstance(data, dict):
        return data.get("items", data.get("forms", []))
    return data if isinstance(data, list) else []


def list_submissions(site: str, form_id: str, page: int = 1, limit: int = 50, since_iso: str | None = None) -> list[dict]:
    """Récupère les soumissions d'un formulaire (paginé)."""
    key = get_api_key(site)
    params: dict = {"page": page, "limit": limit}
    if since_iso:
        params["createdAt[gte]"] = since_iso
    r = requests.get(
        f"{TALLY_BASE_URL}/forms/{form_id}/submissions",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        params=params, timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        return data.get("items", data.get("submissions", []))
    return data if isinstance(data, list) else []


def extract_lead_fields(submission: dict) -> dict:
    """Mappe une soumission Tally vers le format PRM (email, firstName, lastName, company, phone, raw).

    Détecte automatiquement les champs email/prénom/nom/société par patterns courants FR.
    Stocke tout le reste sérialisé dans `raw_fields`.
    """
    fields = submission.get("fields", []) or submission.get("answers", [])
    out: dict = {
        "email": "", "firstName": "", "lastName": "", "company": "", "phone": "",
        "raw_fields": {}, "submission_id": submission.get("id") or submission.get("submissionId", ""),
        "submitted_at": submission.get("submittedAt") or submission.get("createdAt", ""),
    }
    for f in fields:
        key  = (f.get("key") or f.get("label") or "").lower().strip()
        val  = f.get("value")
        if val is None or val == "":
            continue
        # Email
        if not out["email"] and ("email" in key or "mail" in key or (isinstance(val, str) and "@" in val and "." in val.split("@")[-1])):
            out["email"] = str(val).strip().lower()
            continue
        # Prénom / Firstname
        if not out["firstName"] and any(t in key for t in ("prenom", "prénom", "firstname", "first_name", "first name")):
            out["firstName"] = str(val).strip()
            continue
        # Nom / Lastname (mais pas "nom_complet" ou "nom de société")
        if not out["lastName"] and key in ("nom", "lastname", "last_name", "last name", "nom_famille", "nom de famille"):
            out["lastName"] = str(val).strip()
            continue
        # Société / Entreprise
        if not out["company"] and any(t in key for t in ("societe", "société", "company", "entreprise", "organisation", "enseigne")):
            out["company"] = str(val).strip()
            continue
        # Téléphone
        if not out["phone"] and any(t in key for t in ("phone", "tel", "telephone", "téléphone", "mobile", "portable")):
            out["phone"] = str(val).strip()
            continue
        # Tout le reste
        out["raw_fields"][key] = val

    # Si on a un nom complet sur 1 ligne et pas split, tentative
    if not out["firstName"] and not out["lastName"]:
        for k, v in list(out["raw_fields"].items()):
            if "nom" in k and "complet" in k and isinstance(v, str):
                parts = v.strip().split(" ", 1)
                out["firstName"] = parts[0]
                if len(parts) > 1: out["lastName"] = parts[1]
                out["raw_fields"].pop(k, None)
                break

    return out


if __name__ == "__main__":
    import json, sys
    site = sys.argv[1] if len(sys.argv) > 1 else "lcr"
    try:
        forms = list_forms(site)
        print(f"[tally:{site}] {len(forms)} formulaires :")
        for f in forms[:10]:
            print(f"  - {f.get('name', '?')} (id={f.get('id', '?')})")
    except RuntimeError as e:
        print(f"ERREUR: {e}")
        sys.exit(1)
