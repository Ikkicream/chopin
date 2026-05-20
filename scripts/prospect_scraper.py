#!/usr/bin/env python3
"""
prospect_scraper.py — Récolte de prospects B2B FR via Serper + scraping pages contact.

Pipeline (sans dépendance Hunter/Snov/payant) :
  1. Serper SERP `{secteur} {ville} -annuaire -wikipedia -site:google.com` → 20 entreprises
  2. Pour chaque résultat → extraire le DOMAINE (eTLD+1)
  3. Pour chaque domaine → tenter HEAD/GET sur /, /contact, /mentions-legales, /qui-sommes-nous
     → parser regex pour extraire emails (mailto: + @{domaine})
  4. Output : list de {entreprise, domain, source_url, emails[], confidence}
     - confidence = "high" si email trouvé sur leur propre site, sinon "medium"

Usage :
    python3 scripts/prospect_scraper.py --sector "boulangerie" --location "Lyon" --max 20 --site lcr

Sauvegarde dans data/prospects/{site}/{timestamp}.json
Et appende les prospects valides à un CSV de travail data/prospects/{site}/leads.csv
"""

import argparse
import csv
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

import sys
sys.path.insert(0, str(Path(__file__).parent))
from serper_client import search_organic

BASE_DIR = Path(__file__).parent.parent
PROSPECTS_DIR = BASE_DIR / "data" / "prospects"
PROSPECTS_DIR.mkdir(parents=True, exist_ok=True)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36"
REQ_TIMEOUT = 8

# Domaines à ignorer (annuaires généralistes, pas des prospects)
DOMAIN_BLACKLIST = {
    "tripadvisor.fr", "tripadvisor.com", "guide.michelin.com", "lefooding.com",
    "thefork.fr", "yelp.com", "yelp.fr", "facebook.com", "instagram.com",
    "linkedin.com", "twitter.com", "x.com", "pinterest.com", "tiktok.com",
    "youtube.com", "google.com", "google.fr", "maps.google.com",
    "pagesjaunes.fr", "118712.fr", "118000.fr",
    "wikipedia.org", "fr.wikipedia.org", "en.wikipedia.org",
    "societe.com", "infogreffe.fr", "leboncoin.fr",
    "lefigaro.fr", "lemonde.fr", "20minutes.fr",
}

# Emails à ignorer (génériques noreply, marketing massif)
EMAIL_BLACKLIST_PREFIX = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "newsletter", "newsletters", "marketing@noreply",
    "mailer-daemon", "postmaster", "abuse",
}


def etld1(url: str) -> str | None:
    """Renvoie le domaine racine d'une URL (eTLD+1 approximé)."""
    try:
        host = urlparse(url).hostname or ""
        host = host.lower().strip()
        if host.startswith("www."):
            host = host[4:]
        if not host or "." not in host:
            return None
        return host
    except Exception:
        return None


def _fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"}, timeout=REQ_TIMEOUT, allow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return r.text
    except Exception:
        return None
    return None


def extract_emails(html: str, domain_filter: str | None = None) -> list[str]:
    """Extrait emails de HTML. Filtre les blacklist et hors-domaine si demandé."""
    if not html:
        return []
    raw = EMAIL_RE.findall(html)
    out = []
    seen = set()
    for e in raw:
        e = e.lower().strip(".,;:")
        if e in seen:
            continue
        local = e.split("@", 1)[0]
        if any(local.startswith(b) for b in EMAIL_BLACKLIST_PREFIX):
            continue
        # Filtrer ceux qui n'appartiennent pas au domaine cible (signature noisy)
        if domain_filter and not e.endswith("@" + domain_filter) and not e.endswith("." + domain_filter):
            continue
        # Ignore images/extensions techniques (ex: 2x@image.png faux match)
        if e.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
            continue
        seen.add(e)
        out.append(e)
    return out


def enrich_company(domain: str) -> dict:
    """Cherche emails sur le site de l'entreprise (pages contact courantes)."""
    paths_to_try = [
        "/contact", "/contact.html", "/contact-us",
        "/mentions-legales", "/legal", "/legales",
        "/qui-sommes-nous", "/about", "/a-propos",
        "/",  # last resort, footer parfois
    ]
    emails: list[str] = []
    source_url = ""
    for path in paths_to_try:
        url = f"https://{domain}{path}"
        html = _fetch(url)
        if html:
            found = extract_emails(html, domain_filter=domain)
            if found:
                emails = found
                source_url = url
                break
        # En cas d'erreur, on essaye en HTTP comme fallback
    return {"domain": domain, "emails": emails[:5], "contact_page": source_url}


def find_prospects(sector: str, location: str, max_results: int = 20) -> list[dict]:
    """Étape 1 : Serper SERP avec plusieurs angles. Étape 2 : enrich en parallèle.

    Stratégie de queries (en ordre, on cumule les résultats jusqu'à max_results) :
      1. `"{sector} {location}"` — direct, le plus fréquent
      2. `{sector} {location} site:.fr` — privilégie domaines FR
      3. `{sector} {location} contact email` — pages contact directes
    On enlève les domaines blacklistés en post-process plutôt qu'avec `-` (trop restrictif).
    """
    queries = [
        f"{sector} {location}",
        f"{sector} {location} site:.fr",
        f"{sector} {location} contact email",
    ]
    seen_links: set[str] = set()
    all_results: list[dict] = []
    for q in queries:
        if len(all_results) >= max_results * 2:
            break
        print(f"[serper] {q!r} num={max_results}")
        try:
            res = search_organic(q, gl="fr", hl="fr", num=max_results)
        except Exception as e:
            print(f"  err: {e}")
            continue
        for r in res:
            link = r.get("link", "")
            if link and link not in seen_links:
                seen_links.add(link)
                all_results.append(r)
    serp = all_results[:max_results * 2]
    print(f"[serper] total {len(serp)} résultats cumulés (3 queries)")

    seen_domains: set[str] = set()
    candidates: list[dict] = []
    for r in serp:
        link = r.get("link", "")
        domain = etld1(link)
        if not domain or domain in DOMAIN_BLACKLIST or domain in seen_domains:
            continue
        seen_domains.add(domain)
        candidates.append({
            "company":     r.get("title", "")[:120],
            "domain":      domain,
            "serp_url":    link,
            "snippet":     r.get("snippet", "")[:200],
            "position":    r.get("position", 0),
        })

    print(f"[serper] {len(candidates)} candidats uniques après dédup et filtre")

    # Étape 2 : enrich en parallèle (8 workers, timeout 8s chacun)
    enriched: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(enrich_company, c["domain"]): c for c in candidates}
        for fut in as_completed(futures):
            base = futures[fut]
            try:
                e = fut.result()
            except Exception:
                e = {"emails": [], "contact_page": ""}
            enriched.append({
                **base,
                "emails":       e.get("emails", []),
                "contact_page": e.get("contact_page", ""),
                "confidence":   "high" if e.get("emails") else "low",
            })
    enriched.sort(key=lambda x: (-len(x["emails"]), x["position"]))
    return enriched


def save_run(site: str, sector: str, location: str, prospects: list[dict]) -> Path:
    site_dir = PROSPECTS_DIR / site
    site_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_file = site_dir / f"run_{ts}_{sector.replace(' ', '_')}.json"
    run_file.write_text(json.dumps({
        "site": site, "sector": sector, "location": location,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "count":  len(prospects),
        "prospects": prospects,
    }, ensure_ascii=False, indent=2))

    # Append au CSV cumulatif (pour Emelia import)
    csv_file = site_dir / "leads.csv"
    is_new = not csv_file.exists()
    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["sector", "location", "company", "domain", "email", "contact_page", "confidence", "added_at"])
        for p in prospects:
            now = datetime.now(timezone.utc).isoformat()
            if p["emails"]:
                for em in p["emails"]:
                    w.writerow([sector, location, p["company"], p["domain"], em, p["contact_page"], p["confidence"], now])
            else:
                w.writerow([sector, location, p["company"], p["domain"], "", "", p["confidence"], now])
    return run_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True, choices=["lcr", "mkd"])
    parser.add_argument("--sector", required=True, help="ex: boulangerie, restaurant, coiffeur, garage, agence_marketing")
    parser.add_argument("--location", required=True, help="ex: Lyon, Paris, France")
    parser.add_argument("--max", type=int, default=20, help="nombre max de résultats SERP (10-100)")
    args = parser.parse_args()

    t0 = time.time()
    prospects = find_prospects(args.sector, args.location, args.max)
    out = save_run(args.site, args.sector, args.location, prospects)
    n_email = sum(1 for p in prospects if p["emails"])
    print(f"\n[done] {len(prospects)} prospects ({n_email} avec email) en {time.time()-t0:.1f}s")
    print(f"       → {out}")


if __name__ == "__main__":
    main()
