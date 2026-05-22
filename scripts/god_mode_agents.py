#!/usr/bin/env python3
"""
god_mode_agents.py — Agents de scraping/validation/qualification.

Pipeline:
  1. Scraper (Serper.dev /places + /search)
  2. Extracteur emails/phones (regex sur snippets + websites)
  3. Validateur (regex email obligatoire, phone FR optionnel)
  4. Qualifieur (score selon secteur + ville Top 50 + présence email)
"""

import os
import random
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

import god_mode_backend as gm
from email_validator import validate_and_score

BASE_DIR = Path(__file__).parent.parent
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip("\x27\""))

SERPER_KEY = os.environ.get("SERPER_API_KEY", "")
SERPER_PLACES_URL = "https://google.serper.dev/places"
SERPER_SEARCH_URL = "https://google.serper.dev/search"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_FR_RE = re.compile(r"0[1-9](?:[\s.-]?\d{2}){4}")

# Queries par secteur (en français, ciblées France)
SECTOR_QUERIES = {
    "immobilier": ["agence immobilière {city}", "agent immobilier {city} contact"],
    "restaurant": ["restaurant {city} contact", "restaurateur {city}"],
    "garagiste": ["garagiste {city}", "garage automobile {city} contact"],
    "coiffeur": ["coiffeur {city}", "salon de coiffure {city}"],
    "retail": ["commerce {city}", "boutique {city} contact"],
    "artisan": ["artisan {city}", "plombier electricien {city}"],
}


# ── Serper API ────────────────────────────────────────────────────────────────
def serper_places(query: str, location: str = "France", num: int = 10, site_code: str = None) -> list[dict]:
    if not SERPER_KEY:
        return []
    try:
        r = requests.post(SERPER_PLACES_URL,
                          headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
                          json={"q": query, "gl": "fr", "hl": "fr", "location": location, "num": min(num, 10)},
                          timeout=15)
        r.raise_for_status()
        data = r.json()
        credits = int(data.get("credits") or 1)
        gm.log_serper_call(site_code, "places", query, credits=credits, success=True)
        return data.get("places", [])
    except Exception as e:
        gm.log_serper_call(site_code, "places", query, credits=0, success=False)
        print(f"[serper_places] error: {e}")
        return []


def serper_search(query: str, num: int = 10, site_code: str = None) -> list[dict]:
    if not SERPER_KEY:
        return []
    try:
        r = requests.post(SERPER_SEARCH_URL,
                          headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
                          json={"q": query, "gl": "fr", "hl": "fr", "num": num},
                          timeout=15)
        r.raise_for_status()
        data = r.json()
        credits = int(data.get("credits") or 1)
        gm.log_serper_call(site_code, "search", query, credits=credits, success=True)
        return data.get("organic", [])
    except Exception as e:
        gm.log_serper_call(site_code, "search", query, credits=0, success=False)
        print(f"[serper_search] error: {e}")
        return []


def serper_balance() -> dict:
    """Récupère le balance live (compte global, pas par site)."""
    if not SERPER_KEY:
        return {"balance": None, "rateLimit": None, "ok": False, "error": "SERPER_API_KEY missing"}
    try:
        r = requests.get("https://google.serper.dev/account",
                         headers={"X-API-KEY": SERPER_KEY}, timeout=8)
        r.raise_for_status()
        d = r.json()
        return {"balance": d.get("balance"), "rateLimit": d.get("rateLimit"), "ok": True}
    except Exception as e:
        return {"balance": None, "rateLimit": None, "ok": False, "error": str(e)}


# ── Extraction emails depuis website ──────────────────────────────────────────
def fetch_email_from_site(url: str, timeout: int = 6) -> str | None:
    """Fetch homepage + /contact, extract first valid email."""
    if not url:
        return None
    try:
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        base = f"{parsed.scheme or 'https'}://{parsed.netloc or parsed.path}"
        candidates = [base, f"{base}/contact", f"{base}/contact/", f"{base}/mentions-legales"]
        seen = set()
        for u in candidates:
            try:
                r = requests.get(u, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 GodModeBot/1.0"})
                if r.status_code == 200:
                    matches = EMAIL_RE.findall(r.text)
                    for m in matches:
                        m_low = m.lower()
                        # Filtre extensions images / fake
                        if m_low.endswith((".png", ".jpg", ".gif", ".svg", ".webp")):
                            continue
                        if m_low.startswith(("noreply@", "no-reply@", "wordpress@", "example@")):
                            continue
                        if m_low in seen:
                            continue
                        seen.add(m_low)
                        if gm.validate_email(m_low):
                            return m_low
            except Exception:
                continue
        return None
    except Exception:
        return None


def extract_phone(text: str) -> str | None:
    if not text:
        return None
    m = PHONE_FR_RE.search(text)
    return m.group(0).replace(" ", "").replace(".", "").replace("-", "") if m else None


# ── Qualifieur ────────────────────────────────────────────────────────────────
PRIO_SECTORS = {"immobilier": 30, "retail": 30, "restaurant": 25, "coiffeur": 20, "garagiste": 20, "artisan": 15}


def score_prospect(prospect: dict) -> int:
    score = 0
    if prospect.get("email"):
        score += 50  # email obligatoire pour l'envoi
    if prospect.get("phone"):
        score += 10
    sector = prospect.get("sector")
    score += PRIO_SECTORS.get(sector, 0)
    city = prospect.get("city", "")
    if any(c.lower() in city.lower() for c in gm.TOP_50_INSEE[:10]):
        score += 20  # top 10 villes
    elif any(c.lower() in city.lower() for c in gm.TOP_50_INSEE):
        score += 10
    return min(score, 100)


# ── Pipeline scrape ───────────────────────────────────────────────────────────
def scrape_sector(site_code: str, sector: str, cities: list[str] = None, max_results: int = 100,
                  username: str = "system") -> dict:
    """Scrape Serper places pour un secteur, valide emails, insert dans `scrappe`.
    Retourne {scraped, valid, rejected, errors}.
    """
    if sector not in gm.SECTORS_GOD_MODE:
        return {"error": f"Secteur invalide: {sector}"}
    if not SERPER_KEY:
        return {"error": "SERPER_API_KEY manquante"}

    cities = cities or random.sample(gm.TOP_50_INSEE, min(10, len(gm.TOP_50_INSEE)))
    queries = SECTOR_QUERIES.get(sector, [f"{sector} {{city}}"])

    scraped = 0
    valid = 0
    rejected = 0
    errors = 0
    seen_emails = set()

    for city in cities:
        if scraped >= max_results:
            break
        for q_template in queries:
            if scraped >= max_results:
                break
            q = q_template.format(city=city)
            places = serper_places(q, location=f"{city}, France", num=10, site_code=site_code)
            time.sleep(0.5)
            for place in places:
                if scraped >= max_results:
                    break
                scraped += 1
                title = place.get("title", "")
                address = place.get("address", "")
                phone_raw = place.get("phoneNumber", "")
                website = place.get("website", "")
                rating = place.get("rating")

                phone = extract_phone(phone_raw) if phone_raw else None
                # Email obligatoire — on tente fetch website
                email = None
                if website:
                    email = fetch_email_from_site(website)
                    time.sleep(0.3)

                if not email:
                    rejected += 1
                    continue
                if email in seen_emails:
                    continue
                seen_emails.add(email)

                # Idempotence : skip si déjà checké Mailnjoy < 30j ou déjà en pending
                if gm.email_recently_validated(email, days=30):
                    rejected += 1
                    continue
                if gm.email_in_pending(email):
                    rejected += 1
                    continue

                # === Validator email (6 étages spec EMAIL_VALIDATION_SCORING.md) ===
                # Drop AVANT insertion DB si l'email échoue les hard rejects.
                prospect_for_validation = {
                    "company_name": title,
                    "phone":         phone,
                    "sector":        sector,
                    "city":          city,
                    "website":       website,
                    "source":        "serper_places",
                }
                vres = validate_and_score(email, prospect_for_validation)
                if vres["decision"] == "drop":
                    rejected += 1
                    continue
                # queue → status manual_review (revue humaine), push → mailnjoy_pending (sera mis à mailnjoy_valid par le drain)
                email_status = "manual_review" if vres["decision"] == "queue" else "mailnjoy_pending"

                prospect = {
                    "company_name":              title,
                    "contact_name":              "",
                    "email":                     vres["email"],
                    "phone":                     phone,
                    "sector":                    sector,
                    "city":                      city,
                    "postal_code":               None,
                    "website":                   website,
                    "source":                    "serper_places",
                    "search_query":              q,
                    "status":                    email_status,
                    "raw_data":                  {"address": address, "rating": rating, "place_id": place.get("placeId")},
                    "email_score":               vres["score"],
                    "email_validation_reasons":  vres["reasons"],
                }
                prospect["score"] = score_prospect(prospect)
                try:
                    gm.add_prospect_pending(site_code, prospect)
                    valid += 1
                except Exception as e:
                    errors += 1
                    print(f"[scrape] insert error: {e}")

    gm.log_action(site_code, username, "system", "scrape",
                  resource="sector", resource_id=sector,
                  payload={"sector": sector, "cities": cities[:5], "scraped": scraped,
                           "valid": valid, "rejected": rejected, "errors": errors})
    return {"sector": sector, "scraped": scraped, "valid": valid, "rejected": rejected, "errors": errors}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: god_mode_agents.py <site_code> <sector> [max_results]")
        sys.exit(1)
    site = sys.argv[1]
    sector = sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    print(scrape_sector(site, sector, max_results=n))
