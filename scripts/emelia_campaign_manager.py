#!/usr/bin/env python3
"""
emelia_campaign_manager.py — Manages Emelia campaigns:
- Segment prospects by sector from CSV
- Create campaigns via Emelia API
- Configure email steps (3 emails, Mon-Fri 8h-18h)
- Add contacts
- Get stats

Usage:
  python3 scripts/emelia_campaign_manager.py --action list-sectors
  python3 scripts/emelia_campaign_manager.py --action create --sector retail --volume 50
  python3 scripts/emelia_campaign_manager.py --action stats
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent.parent
CSV_FILE = BASE_DIR / "context" / "shared" / "prospects.csv"
CAMPAIGNS_FILE = BASE_DIR / "memory" / "editorial" / "emelia-campaigns.json"

env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip("'\""))

EMELIA_KEY = os.environ.get("EMELIA_API_KEY", "")
EMELIA_URL = "https://api.emelia.io"
HEADERS = {"Authorization": EMELIA_KEY, "Content-Type": "application/json"}

# Sector keywords for classification
SECTORS = {
    "retail": ["carrefour", "decathlon", "fnac", "darty", "monoprix", "auchan", "leclerc", "casino", "lidl", "intermarche", "boutique", "magasin", "store", "shop"],
    "hotel": ["accor", "hotel", "louvre-hotels", "club-med", "tourisme", "booking", "resort", "ibis", "novotel", "mercure"],
    "immobilier": ["nexity", "foncia", "vinci-immo", "immo", "immobilier", "foncier", "logement", "agence-immo", "agent-immobilier"],
    "restaurant": ["restaurant", "bistrot", "brasserie", "traiteur", "food", "cuisine", "restaurateur"],
    "sante": ["pharma", "optique", "sante", "medical", "dentiste", "labo", "clinique"],
    "beaute": ["beaute", "beauty", "esthetique", "spa", "wellness", "institut"],
    "coiffeur": ["coiffeur", "coiffure", "salon-coiffure", "barbier", "barbershop", "hair", "hairstyle"],
    "garagiste": ["garage", "garagiste", "mecanicien", "mecanique", "automobile", "carrosserie", "auto-ecole", "auto", "reparation-auto"],
    "artisan": ["artisan", "menuisier", "plombier", "electricien", "macon", "maconnerie", "peintre", "couvreur", "chauffagiste", "serrurier", "carreleur"],
    "agence": ["agence", "agency", "marketing", "communication", "digital", "conseil", "consulting"],
    "tech": ["tech", "software", "saas", "digital", "cloud", "data", "informatique"],
    "autres": [],
}


def load_prospects():
    """Load and parse the CSV file.
    CSV format: status;occurrence;classification;email
    Only email is usable. We extract company from the email domain.
    """
    if not CSV_FILE.exists():
        return []
    prospects = []
    seen = set()
    with open(CSV_FILE, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            if len(row) >= 4 and "@" in row[3]:
                email = row[3].strip().lower()
                if email in seen:
                    continue
                seen.add(email)
                domain = email.split("@")[1] if "@" in email else ""
                # Extract company name from domain (remove TLD)
                company = domain.split(".")[0] if domain else ""
                company = company.replace("-", " ").replace("_", " ").title()
                # Extract first name from email prefix (before @, before dots/numbers)
                prefix = email.split("@")[0]
                parts = prefix.replace(".", " ").replace("-", " ").replace("_", " ").split()
                first_name = parts[0].title() if parts else ""
                last_name = parts[1].title() if len(parts) > 1 else ""
                prospects.append({
                    "email": email,
                    "domain": domain,
                    "firstName": first_name,
                    "lastName": last_name,
                    "company": company,
                })
    return prospects


def classify_sector(domain, company):
    """Classify a prospect into a sector based on domain/company name."""
    text = (domain + " " + company).lower()
    for sector, keywords in SECTORS.items():
        if sector == "autres":
            continue
        for kw in keywords:
            if kw in text:
                return sector
    return "autres"


def get_sector_breakdown():
    """Get prospect count by sector."""
    prospects = load_prospects()
    breakdown = {s: 0 for s in SECTORS}
    for p in prospects:
        sector = classify_sector(p["domain"], p.get("company", ""))
        breakdown[sector] += 1
    return {"total": len(prospects), "by_sector": breakdown}


def get_prospects_by_sector(sector, limit=None):
    """Get prospects for a specific sector."""
    prospects = load_prospects()
    filtered = [p for p in prospects if classify_sector(p["domain"], p.get("company", "")) == sector]
    # Deduplicate by email
    seen = set()
    unique = []
    for p in filtered:
        if p["email"] not in seen:
            seen.add(p["email"])
            unique.append(p)
    if limit:
        unique = unique[:limit]
    return unique


def create_emelia_campaign(name):
    """Create a new Emelia email campaign."""
    r = requests.post(f"{EMELIA_URL}/emails/campaigns", json={"name": name}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def configure_steps(campaign_id, steps_data):
    """Configure email sequence steps."""
    r = requests.patch(f"{EMELIA_URL}/emails/campaigns/{campaign_id}/steps",
                      json={"steps": steps_data}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def configure_settings(campaign_id, sending_days=None, sending_hours=None,
                       timezone_="Europe/Paris"):
    """Configure campaign settings. Défaut : Lun-Ven 8h-18h.
    `sending_days`/`sending_hours` permettent d'élargir la fenêtre (BAT : 7j/7, 24h/24,
    pour que le test parte immédiatement au lieu d'attendre le prochain créneau)."""
    settings = {
        "sendingDays": sending_days or {
            "monday": True, "tuesday": True, "wednesday": True,
            "thursday": True, "friday": True,
            "saturday": False, "sunday": False,
        },
        "sendingHours": sending_hours or {"start": "08:00", "end": "18:00"},
        "timezone": timezone_,
    }
    r = requests.patch(f"{EMELIA_URL}/emails/campaigns/{campaign_id}/settings",
                      json=settings, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


ALL_DAYS = {"monday": True, "tuesday": True, "wednesday": True, "thursday": True,
            "friday": True, "saturday": True, "sunday": True}


def _api_error(resp) -> str:
    """Message d'erreur lisible renvoyé par Emelia (le corps porte le vrai motif,
    que `raise_for_status()` perdrait)."""
    try:
        return resp.json().get("error") or resp.text[:200]
    except Exception:
        return resp.text[:200]


def send_test_email(html: str, subject: str, to_email: str,
                    contact: dict | None = None, label: str = "BAT") -> dict:
    """BAT RÉEL via Emelia. L'API Emelia n'expose aucun envoi de test (ni REST ni
    GraphQL, vérifié 2026-07-29) : on crée donc une campagne jetable d'un seul
    contact et on la démarre. C'est volontairement le MÊME chemin que l'envoi final
    (même expéditeur, même moteur de variables Emelia, même tracking) — un BAT qui
    emprunterait un autre canal ne prouverait rien.

    Seule différence assumée avec la campagne réelle : la fenêtre d'envoi est ouverte
    7j/7 24h/24 pour que le test parte tout de suite.
    """
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "adresse de test invalide"}
    if not (html or "").strip():
        return {"ok": False, "error": "message vide"}
    if not EMELIA_KEY:
        return {"ok": False, "error": "EMELIA_API_KEY absente du .env"}

    # Emelia refuse un nom de campagne déjà pris : on horodate pour que deux BAT
    # successifs sur le même message ne se télescopent pas.
    stamp = datetime.now(timezone.utc).astimezone().strftime("%d/%m %H:%M:%S")
    name = f"[{label}] {(subject or 'test').strip()}"[:46] + f" · {stamp}"
    try:
        r = requests.post(f"{EMELIA_URL}/emails/campaigns", json={"name": name},
                          headers=HEADERS, timeout=30)
        if r.status_code >= 400:
            return {"ok": False, "error": f"Emelia refuse de créer la campagne de test "
                                          f"({r.status_code}) : {_api_error(r)}"}
        created = r.json()
        cid = (created.get("campaign") or {}).get("_id") or created.get("_id")
        if not cid:
            return {"ok": False, "error": "création de la campagne de test échouée"}
        configure_steps(cid, build_newsletter_steps(html, subject))
        try:
            configure_settings(cid, sending_days=ALL_DAYS,
                               sending_hours={"start": "00:00", "end": "23:59"})
        except Exception:
            pass  # fenêtre par défaut : le test partira au prochain créneau ouvré
        # ORDRE IMPOSÉ PAR EMELIA : le destinataire d'abord, le démarrage ensuite
        # (« You must have at least one recipient to start campaign »).
        if not add_contact(cid, contact or {"email": to_email}):
            try:
                requests.delete(f"{EMELIA_URL}/emails/campaigns/{cid}", headers=HEADERS, timeout=15)
            except Exception:
                pass
            return {"ok": False, "error": "ajout du contact de test refusé par Emelia"}
        # La réponse du démarrage DOIT être vérifiée : sur refus (abonnement, quota…)
        # la campagne reste en DRAFT et rien ne part. Ignorer ce code, c'est déclarer
        # un envoi qui n'a pas eu lieu.
        st = requests.post(f"{EMELIA_URL}/emails/campaigns/{cid}/start",
                           headers=HEADERS, timeout=15)
        if st.status_code >= 400:
            # Campagne inutilisable : on la retire pour ne pas polluer le compte Emelia
            # (DELETE n'est pas documenté mais fonctionne — vérifié 2026-07-29).
            try:
                requests.delete(f"{EMELIA_URL}/emails/campaigns/{cid}", headers=HEADERS, timeout=15)
            except Exception:
                pass
            return {"ok": False,
                    "error": f"Emelia refuse de démarrer l'envoi ({st.status_code}) : {_api_error(st)}"}
        return {"ok": True, "emelia_campaign_id": cid,
                "note": f"BAT Emelia envoyé à {to_email} — campagne de test « {name} » "
                        "(à archiver dans Emelia une fois le contrôle fait)"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Emelia: {e}"}


def add_contact(campaign_id, contact):
    """Add a single contact to a campaign."""
    r = requests.post(f"{EMELIA_URL}/emails/campaign/contacts", json={
        "id": campaign_id,
        "contact": contact,
    }, headers=HEADERS, timeout=10)
    return r.status_code in (200, 201)


def get_campaign_stats(campaign_id):
    """Get campaign statistics."""
    r = requests.get(f"{EMELIA_URL}/emails/campaigns/{campaign_id}/statistics",
                    headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def list_campaigns():
    """List all Emelia campaigns."""
    r = requests.get(f"{EMELIA_URL}/emails/campaigns", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


# Default email templates
def _tag_steps_cold(steps, sector):
    """Pose utm_source=coldemail&utm_medium=email&utm_campaign=<secteur> sur les liens
    possédés dans chaque corps d'email (cf. utm_tagging). Best-effort."""
    try:
        from utm_tagging import tag_links
    except Exception:
        return steps
    for st in steps:
        for v in st.get("versions", []):
            if v.get("message"):
                v["message"] = tag_links(v["message"], "coldemail", "email", sector or "")
    return steps


def get_default_steps(sector, company_type="entreprise", site="lcr"):
    """Génère la séquence 3 emails pour un secteur.

    DB-first : utilise d'abord les templates validés dans `email_templates`
    (générés via DeepSeek : icebreaker, lien secteur, signature Juliette).
    Fallback sur les templates génériques ci-dessous si la base est vide/incomplète.
    """
    # --- 1. Templates validés en base (par site) ---
    try:
        import email_templates_backend as etb
        by_kind = {r["kind"]: r for r in etb.get_sector(site, sector)}
        order = ["first", "relance1", "relance2"]
        if all(by_kind.get(k) and (by_kind[k].get("body_html") or "").strip() for k in order):
            delays = [
                {"amount": 0, "unit": "MINUTES"},
                {"amount": 3, "unit": "DAYS"},
                {"amount": 7, "unit": "DAYS"},
            ]
            return _tag_steps_cold([
                {"delay": delays[i], "versions": [{
                    "subject":  by_kind[k].get("subject") or "",
                    "disabled": False,
                    "message":  by_kind[k]["body_html"],
                    "rawHtml":  True,
                    "attachments": [],
                }]}
                for i, k in enumerate(order)
            ], sector)
    except Exception as e:
        print(f"  [steps] DB templates indispo, fallback générique ({e})")

    # --- 2. Fallback : templates génériques codés en dur ---
    templates = {
        "retail": {
            "subject1": "SMS g\u00e9olocalis\u00e9 pour vos points de vente",
            "body1": "<p>Bonjour {{firstName}},</p><p>J'ai vu que {{field1}} poss\u00e8de plusieurs points de vente. Vos clients dans un rayon de 2km pourraient recevoir un SMS au bon moment \u2014 nos partenaires constatent +40% de trafic en magasin.</p><p>Un call de 15 min pour voir le ROI sur 1 magasin test ?</p><p>Camille<br>LeClientROI</p>",
            "subject2": "Re: SMS g\u00e9olocalis\u00e9 {{field1}}",
            "body2": "<p>{{firstName}}, je me permets de relancer \u2014 nous avons lanc\u00e9 une op\u00e9ration drive-to-store pour un acteur similaire \u00e0 {{field1}} avec des r\u00e9sultats mesurables d\u00e8s la premi\u00e8re semaine.</p><p>15 min suffisent pour voir si \u00e7a fait sens pour vous.</p>",
            "subject3": "Derni\u00e8re relance \u2014 {{field1}}",
            "body3": "<p>{{firstName}}, dernier message. Si le SMS g\u00e9olocalis\u00e9 n'est pas une priorit\u00e9 actuellement, je comprends tout \u00e0 fait. N'h\u00e9sitez pas \u00e0 revenir vers moi quand le sujet sera d'actualit\u00e9.</p>",
        },
        "default": {
            "subject1": "Solution SMS marketing pour {{field1}}",
            "body1": "<p>Bonjour {{firstName}},</p><p>Je travaille avec des entreprises comme {{field1}} sur leur strat\u00e9gie de communication SMS. Le taux d'ouverture est de 98% contre 20% pour l'email.</p><p>Seriez-vous disponible pour un \u00e9change de 15 min ?</p><p>Camille<br>LeClientROI</p>",
            "subject2": "Re: SMS marketing {{field1}}",
            "body2": "<p>{{firstName}}, je me permets de relancer. Nous accompagnons des entreprises de votre secteur sur le SMS marketing avec des r\u00e9sultats concrets.</p><p>Un rapide appel cette semaine ?</p>",
            "subject3": "{{firstName}} \u2014 derni\u00e8re relance",
            "body3": "<p>{{firstName}}, dernier message de ma part. Si le sujet vous int\u00e9resse plus tard, n'h\u00e9sitez pas. Bonne continuation !</p>",
        }
    }

    tmpl = templates.get(sector, templates["default"])

    return _tag_steps_cold([
        {"delay": {"amount": 0, "unit": "MINUTES"}, "versions": [{"subject": tmpl["subject1"], "disabled": False, "message": tmpl["body1"], "rawHtml": True, "attachments": []}]},
        {"delay": {"amount": 3, "unit": "DAYS"}, "versions": [{"subject": tmpl["subject2"], "disabled": False, "message": tmpl["body2"], "rawHtml": True, "attachments": []}]},
        {"delay": {"amount": 7, "unit": "DAYS"}, "versions": [{"subject": tmpl["subject3"], "disabled": False, "message": tmpl["body3"], "rawHtml": True, "attachments": []}]},
    ], sector)


def build_newsletter_steps(html, subject):
    """Envoi unique (1 step) d'une newsletter validee : le HTML tel quel, rawHtml=True."""
    return [{
        "delay": {"amount": 0, "unit": "MINUTES"},
        "versions": [{"subject": subject or "", "disabled": False,
                      "message": html or "", "rawHtml": True, "attachments": []}],
    }]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["list-sectors", "stats", "create"], required=True)
    parser.add_argument("--sector", default="retail")
    parser.add_argument("--volume", type=int, default=50)
    args = parser.parse_args()

    if args.action == "list-sectors":
        data = get_sector_breakdown()
        print(f"Total prospects: {data['total']}")
        for s, c in sorted(data["by_sector"].items(), key=lambda x: -x[1]):
            print(f"  {s}: {c}")

    elif args.action == "stats":
        campaigns = list_campaigns()
        for c in campaigns:
            print(f"{c.get('name')} | {c.get('status')} | sent: {c.get('total', 0)}")

    elif args.action == "create":
        print(f"Creating campaign for sector '{args.sector}', volume {args.volume}")
        prospects = get_prospects_by_sector(args.sector, args.volume)
        print(f"  {len(prospects)} prospects found")
