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
# Sectors-presets : queries optimisées pour Serper Places.
# Pour TOUT secteur libre non listé, fallback automatique : f"{sector} {{city}}".
# Plusieurs ANGLES par secteur : Google Places plafonne à ~20 résultats / requête, et
# renvoie ~le même top-20 quelle que soit la page. Le seul moyen d'élargir la couverture
# est de varier la requête (chaque angle métier a son propre top-20). Combiné au dédoublonnage
# par placeId (cf. _seen_places), on balaie bien plus que 20 commerces/ville sans repasser
# sur les mêmes. NB : plus de variantes = plus de crédits Serper (compromis assumé).
SECTOR_QUERIES = {
    "immobilier":  ["agence immobilière {city}", "agent immobilier {city}",
                    "estimation immobilière {city}", "gestion locative {city}",
                    "syndic de copropriété {city}", "immobilier neuf {city}",
                    "vente appartement {city}", "location maison {city}",
                    "mandataire immobilier {city}", "négociateur immobilier {city}"],
    "restaurant":  ["restaurant {city}", "restaurateur {city}", "brasserie {city}",
                    "bistrot {city}", "pizzeria {city}", "restaurant gastronomique {city}",
                    "traiteur {city}"],
    "garagiste":   ["garagiste {city}", "garage automobile {city}", "carrosserie {city}",
                    "réparation automobile {city}", "centre auto {city}"],
    "coiffeur":    ["coiffeur {city}", "salon de coiffure {city}", "barbier {city}",
                    "coiffeur visagiste {city}"],
    "retail":      ["commerce {city}", "boutique {city}", "magasin {city}",
                    "concept store {city}"],
    "artisan":     ["artisan {city}", "plombier {city}", "électricien {city}",
                    "maçon {city}", "peintre en bâtiment {city}", "carreleur {city}"],
    "fleuriste":   ["fleuriste {city}", "boutique fleurs {city}", "atelier floral {city}"],
    "boulanger":   ["boulangerie {city}", "pâtisserie {city}", "boulangerie artisanale {city}"],
    "plombier":    ["plombier {city}", "plomberie {city}", "plombier chauffagiste {city}",
                    "dépannage plomberie {city}"],
    "electricien": ["electricien {city}", "entreprise électricité {city}",
                    "électricien dépannage {city}", "installation électrique {city}"],
    "menuisier":   ["menuisier {city}", "menuiserie {city}", "ébéniste {city}",
                    "menuiserie bois {city}"],
    "avocat":      ["avocat {city}", "cabinet avocat {city}", "avocat droit des affaires {city}",
                    "avocat immobilier {city}"],
    "comptable":   ["expert comptable {city}", "cabinet comptable {city}",
                    "comptable {city}", "cabinet expertise comptable {city}"],
    "agence-marketing": ["agence marketing {city}", "agence communication {city}",
                         "agence publicité {city}", "agence digitale {city}"],
    "agence-web":  ["agence web {city}", "développement web {city}", "création site internet {city}",
                    "agence seo {city}"],
    "consultant":  ["consultant {city}", "cabinet conseil {city}", "consultant indépendant {city}"],
}


# ── Mémoire des placeId déjà vus (cross-run) ────────────────────────────────────
# Google Places renvoie le même top-20 à chaque run. On persiste les placeId déjà
# examinés par (site, secteur) pour : (a) les SAUTER avant le fetch du site (gain de
# temps + crédits), (b) détecter qu'une requête est ÉPUISÉE (que des placeId connus)
# pour passer à la variante suivante au lieu de tourner en rond.
SEEN_PLACES_DIR = BASE_DIR / "memory" / "scrape"


def _seen_places_path(site_code: str, sector: str) -> Path:
    safe = re.sub(r"[^a-z0-9]+", "-", (sector or "").lower()).strip("-") or "x"
    return SEEN_PLACES_DIR / f"seen-places-{site_code}-{safe}.json"


def load_seen_places(site_code: str, sector: str) -> set:
    p = _seen_places_path(site_code, sector)
    if p.exists():
        try:
            import json as _j
            return set(_j.loads(p.read_text()))
        except Exception:
            return set()
    return set()


def norm_domain(url: str) -> str | None:
    """Domaine normalisé d'une URL (sans scheme/www/port/path), clé de dédup stable.
    Serper Places renvoie `website` quasi toujours ; le placeId, lui, est souvent absent —
    donc le domaine est une bien meilleure clé de « burn » que le placeId."""
    if not url:
        return None
    try:
        u = url.strip().lower()
        if "://" not in u:
            u = "http://" + u
        host = (urlparse(u).netloc or "").split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        return host or None
    except Exception:
        return None


def save_seen_places(site_code: str, sector: str, ids: set) -> None:
    try:
        import json as _j
        SEEN_PLACES_DIR.mkdir(parents=True, exist_ok=True)
        # borne de sécurité : on garde les 200k derniers ids (largement > volume réel)
        _seen_places_path(site_code, sector).write_text(
            _j.dumps(list(ids)[-200000:], ensure_ascii=False))
    except Exception:
        pass


# ── Serper API ────────────────────────────────────────────────────────────────
# Signalé à True (= code HTTP) quand Serper REFUSE explicitement l'appel : rate-limit
# (429) ou quota/paiement épuisé (402/403). L'autoscrape lit ce flag pour distinguer
# « Serper nous a stoppés » (→ pause + retry quotidien) d'une simple ville sans résultat.
SERPER_BLOCKED_STATUS = None


def serper_places(query: str, location: str = "France", num: int = 10, site_code: str = None,
                  page: int = 1) -> list[dict]:
    global SERPER_BLOCKED_STATUS
    if not SERPER_KEY:
        return []
    try:
        payload = {"q": query, "gl": "fr", "hl": "fr", "location": location, "num": min(num, 10)}
        if page and page > 1:
            payload["page"] = page
        r = requests.post(SERPER_PLACES_URL,
                          headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
                          json=payload,
                          timeout=15)
    except Exception as e:
        gm.log_serper_call(site_code, "places", query, credits=0, success=False)
        print(f"[serper_places] error: {e}")
        return []
    # Refus EXPLICITE de Serper → on lève le flag (au lieu de l'avaler en []), pour que
    # l'autoscrape sache qu'il est bloqué et ré-essaie chaque jour jusqu'à passage.
    if r.status_code in (429, 402, 403):
        SERPER_BLOCKED_STATUS = r.status_code
        gm.log_serper_call(site_code, "places", query, credits=0, success=False)
        print(f"[serper_places] BLOCKED HTTP {r.status_code} — Serper refuse l'appel")
        return []
    try:
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
PRIO_SECTORS = {
    "immobilier": 30, "retail": 30, "restaurant": 25, "coiffeur": 20, "garagiste": 20, "artisan": 15,
    "fleuriste": 10, "boulanger": 10, "plombier": 10, "electricien": 10, "menuisier": 10,
    "avocat": 15, "comptable": 15, "agence-marketing": 15, "agence-web": 15, "consultant": 10,
}


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
def scrape_sector(site_code: str, sector: str, cities: list[str] = None,
                  max_per_city: int = 10, global_cap: int = 1500, max_pages: int = 4,
                  username: str = "system", heartbeat_cb=None) -> dict:
    """Scrape Serper Places pour un secteur sur une LISTE de villes.

    Sémantique corrigée 2026-05-31 (le `max_results` global était un piège) :
      - `max_per_city` = nb de contacts GARDÉS (validés + insérés) visé PAR VILLE.
        On pagine Serper (jusqu'à `max_pages` pages/requête) pour tenter de l'atteindre.
      - `global_cap` = plafond GLOBAL de contacts gardés sur TOUT le scrape (garde-fou crédits).
      - On boucle sur TOUTES les villes fournies (plus d'arrêt global prématuré).
    Retourne {scraped(=commerces examinés), valid, rejected, errors, kept_total, cities_done}.
    """
    if not sector or not sector.strip():
        gm.log_action(site_code, username, "system", "scrape",
                      resource="sector", resource_id=sector or "",
                      payload={"sector": sector, "error": "empty sector"},
                      success=False, error_message="empty sector")
        return {"error": "sector required"}
    if not SERPER_KEY:
        gm.log_action(site_code, username, "system", "scrape",
                      resource="sector", resource_id=sector,
                      payload={"sector": sector, "error": "SERPER_API_KEY missing"},
                      success=False, error_message="SERPER_API_KEY missing")
        return {"error": "SERPER_API_KEY manquante"}

    cities = cities or random.sample(gm.TOP_50_INSEE, min(10, len(gm.TOP_50_INSEE)))
    queries = SECTOR_QUERIES.get(sector, [f"{sector} {{city}}"])
    max_per_city = max(1, int(max_per_city))
    global_cap = max(1, int(global_cap))
    max_pages = max(1, int(max_pages))

    examined = 0       # commerces Google examinés (≈ crédits Serper / 10)
    valid = 0          # gardés (email valide + inséré)
    rejected = 0
    errors = 0
    duplicates = 0     # déjà connus (email déjà en pool/file/validé) → ignorés, JAMAIS dupliqués
    kept_total = 0     # = valid, mais explicite pour le plafond global
    cities_done = 0
    seen_emails = set()
    seen_places = load_seen_places(site_code, sector)   # placeId déjà vus (runs précédents)
    skipped_seen = 0   # commerces sautés car placeId déjà connu (avant tout fetch)

    for city in cities:
        if kept_total >= global_cap:
            break
        cities_done += 1
        kept_city = 0
        for q_template in queries:
            if kept_city >= max_per_city or kept_total >= global_cap:
                break
            q = q_template.format(city=city)
            for page in range(1, max_pages + 1):
                if kept_city >= max_per_city or kept_total >= global_cap:
                    break
                places = serper_places(q, location=f"{city}, France", num=10,
                                       site_code=site_code, page=page)
                time.sleep(0.5)
                # Heartbeat intra-ville (à chaque page Serper) : maj statut live + évite le faux "figé"
                if heartbeat_cb:
                    try:
                        heartbeat_cb(city, sector, examined, valid)
                    except Exception:
                        pass
                if not places:
                    break  # plus de résultats pour cette requête → ville suivante/requête suivante
                page_new = 0   # nb de placeId NEUFS sur cette page (0 → variante épuisée)
                for place in places:
                    if kept_city >= max_per_city or kept_total >= global_cap:
                        break
                    # « Burn » des lieux déjà scrappés : clé = DOMAINE du site web (stable et
                    # quasi toujours présent ; le placeId Serper est souvent null). Si déjà vu
                    # (run précédent ou cette session), on saute AVANT le fetch du site (gain
                    # temps + crédits). Sinon Google resservant le même top-20, on retomberait
                    # sans cesse sur les mêmes commerces. Fallback placeId si pas de website.
                    website = place.get("website", "")
                    burn_key = norm_domain(website) or place.get("placeId") or place.get("place_id")
                    if burn_key and burn_key in seen_places:
                        skipped_seen += 1
                        continue
                    if burn_key:
                        seen_places.add(burn_key)
                        page_new += 1
                    examined += 1
                    title = place.get("title", "")
                    address = place.get("address", "")
                    phone_raw = place.get("phoneNumber", "")
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
                        duplicates += 1
                        continue
                    seen_emails.add(email)

                    # Dedup + validation + insert : TOLÉRANT AUX ERREURS DB. Un conflit
                    # DuckDB transitoire (verrou cross-process avec l'API) saute CE commerce
                    # au lieu de crasher toute la ville (cf. autoscrape). Avec un petit retry.
                    try:
                        try:
                            _dup = gm.email_recently_validated(email, days=30) or gm.email_in_pending(email)
                        except Exception:
                            time.sleep(0.5)
                            _dup = gm.email_recently_validated(email, days=30) or gm.email_in_pending(email)
                        if _dup:
                            duplicates += 1
                            continue

                        # === Validator email (6 étages spec EMAIL_VALIDATION_SCORING.md) ===
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
                        email_status = "mailnjoy_pending"

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
                        gm.add_prospect_pending(site_code, prospect)
                        valid += 1
                        kept_city += 1
                        kept_total += 1

                        # DUAL-WRITE pool 2026-05-22 : insert aussi dans contacts.duckdb
                        try:
                            import contacts_pool_backend as _cpb
                            try:
                                from workflow_geo import resolve_city_geo
                                _geo = resolve_city_geo(city)
                            except Exception:
                                _geo = {"dept": None, "region": None}
                            _pool_cid = _cpb.create_in_pool({
                                "email":      vres["email"],
                                "societe":    title,
                                "tel":        phone,
                                "website":    website,
                                "city":       city,
                                "dept_code":   _geo.get("dept"),
                                "region_code": _geo.get("region"),
                                "sectors":    [sector] if sector else None,
                                "email_score":              vres["score"],
                                "email_validation_reasons": vres["reasons"],
                            }, primary_source="serper")
                            if _pool_cid:
                                _cpb.upsert_site_history(_pool_cid, site_code,
                                    state="cold_email",
                                    source="serper",
                                    by="scrape_sector")
                        except Exception as _pool_err:
                            print(f"  [scrape][pool dual-write] {_pool_err}")
                    except Exception as e:
                        errors += 1
                        print(f"[scrape] place error (skip): {e}")
                        continue

                # Variante épuisée : la page n'a ramené QUE des placeId déjà connus →
                # inutile de paginer plus loin sur cette requête, on passe à la variante suivante.
                if page_new == 0:
                    break

    save_seen_places(site_code, sector, seen_places)
    gm.log_action(site_code, username, "system", "scrape",
                  resource="sector", resource_id=sector,
                  payload={"sector": sector, "cities_done": cities_done, "cities_total": len(cities),
                           "cities": cities[:5], "scraped": examined, "valid": valid,
                           "rejected": rejected, "duplicates": duplicates, "errors": errors,
                           "skipped_seen": skipped_seen,
                           "max_per_city": max_per_city, "global_cap": global_cap})
    return {"sector": sector, "scraped": examined, "valid": valid, "rejected": rejected,
            "duplicates": duplicates, "errors": errors, "kept_total": kept_total,
            "skipped_seen": skipped_seen, "cities_done": cities_done, "cities_total": len(cities)}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: god_mode_agents.py <site_code> <sector> [max_results]")
        sys.exit(1)
    site = sys.argv[1]
    sector = sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    print(scrape_sector(site, sector, max_results=n))
