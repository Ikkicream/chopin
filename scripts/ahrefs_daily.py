#!/usr/bin/env python3
"""
Genesis — Ahrefs Daily Fetch
Fetches SEO data for all configured sites and caches it.
Run via cron: 0 6 * * * cd /home/autoblog/genesis && python3 scripts/ahrefs_daily.py

Uses Ahrefs API v3 via HTTP requests.
Budget: ~250 credits/day for 2 sites.
"""

import json
import os
import sys
from datetime import datetime, timezone, date
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent.parent
SEO_DIR = BASE_DIR / "memory" / "seo"
SEO_DIR.mkdir(parents=True, exist_ok=True)

AHREFS_TOKEN = os.environ.get("AHREFS_API_KEY", "")
if not AHREFS_TOKEN:
    # Try loading from .env
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("AHREFS_API_KEY="):
                AHREFS_TOKEN = line.split("=", 1)[1].strip()
                break

if not AHREFS_TOKEN:
    print("ERROR: AHREFS_API_KEY not found")
    sys.exit(1)

BASE_URL = "https://api.ahrefs.com/v3"
HEADERS = {"Authorization": f"Bearer {AHREFS_TOKEN}", "Accept": "application/json"}

SITES = [
    {"code": "lcr", "domain": "leclientroi.com"},
    {"code": "mkd", "domain": "mkdgroupe.com"},
]

TODAY = date.today().isoformat()


def api_get(endpoint, params):
    """Make Ahrefs API request."""
    r = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_site(site):
    """Fetch all SEO data for a site."""
    domain = site["domain"]
    code = site["code"]
    print(f"[{code}] Fetching {domain}...")

    data = {
        "site": code,
        "domain": domain,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    # 1. Domain Rating
    try:
        dr = api_get("site-explorer/domain-rating", {"target": domain, "date": TODAY})
        data["domain_rating"] = dr["domain_rating"]["domain_rating"]
        data["ahrefs_rank"] = dr["domain_rating"]["ahrefs_rank"]
        print(f"  DR: {data['domain_rating']}")
    except Exception as e:
        print(f"  DR error: {e}")
        data["domain_rating"] = None

    # 2. Metrics
    try:
        m = api_get("site-explorer/metrics", {
            "target": domain, "date": TODAY, "country": "FR", "mode": "subdomains"
        })
        metrics = m["metrics"]
        data["org_traffic"] = metrics.get("org_traffic", 0)
        data["org_keywords"] = metrics.get("org_keywords", 0)
        data["org_keywords_top3"] = metrics.get("org_keywords_1_3", 0)
        data["org_cost_usd_cents"] = metrics.get("org_cost", 0)
        print(f"  Traffic: {data['org_traffic']}, Keywords: {data['org_keywords']}")
    except Exception as e:
        print(f"  Metrics error: {e}")

    # 3. Top 5 keywords
    try:
        kw = api_get("site-explorer/organic-keywords", {
            "target": domain, "date": TODAY, "country": "FR", "mode": "subdomains",
            "select": "keyword,best_position,volume,sum_traffic",
            "order_by": "sum_traffic:desc", "limit": 5
        })
        data["top_keywords"] = [
            {"keyword": k["keyword"], "position": k["best_position"],
             "volume": k.get("volume", 0), "traffic": k.get("sum_traffic", 0)}
            for k in kw.get("keywords", [])
        ]
        print(f"  Keywords: {len(data['top_keywords'])} fetched")
    except Exception as e:
        print(f"  Keywords error: {e}")
        data["top_keywords"] = []

    # 4. Top competitors — fetch 50 puis filtrage strict pour exclure géants généralistes
    #    (avant : ramenait facebook.com, reddit.com, wikipedia.com — ces sites ont des kw communs
    #     avec tout le monde car taille massive, mais ce NE SONT PAS des concurrents)
    BLACKLIST_GEANTS = {
        "facebook.com", "instagram.com", "tiktok.com", "twitter.com", "x.com",
        "linkedin.com", "youtube.com", "pinterest.com", "snapchat.com",
        "reddit.com", "quora.com", "medium.com",
        "wikipedia.org", "fr.wikipedia.org", "en.wikipedia.org",
        "google.com", "google.fr", "amazon.fr", "amazon.com",
        "leboncoin.fr", "ebay.fr", "ebay.com", "aliexpress.com",
        "youtube.com", "vimeo.com", "dailymotion.com",
        "lefigaro.fr", "lemonde.fr", "20minutes.fr", "ouest-france.fr",  # médias généralistes
        "journaldunet.com", "lesechos.fr", "challenges.fr",
    }
    try:
        comp = api_get("site-explorer/organic-competitors", {
            "target": domain, "date": TODAY, "country": "fr", "mode": "domain",
            "select": "competitor_domain,keywords_common,domain_rating,traffic",
            "order_by": "keywords_common:desc", "limit": 50
        })
        raw = comp.get("competitors", [])
        filtered = []
        for c in raw:
            d = (c.get("competitor_domain", "") or "").lower().strip()
            if not d or d in BLACKLIST_GEANTS:
                continue
            dr_v = c.get("domain_rating", 0) or 0
            tr_v = c.get("traffic", 0) or 0
            kw_v = c.get("keywords_common", 0) or 0
            # Exclure géants généralistes (DR > 88 + trafic > 3M = forcément Wikipedia-like)
            if dr_v > 88 and tr_v > 3_000_000:
                continue
            # Garder uniquement avec un signal minimum
            if kw_v < 2:
                continue
            filtered.append({
                "domain": d, "keywords_common": kw_v, "dr": dr_v, "traffic": tr_v,
            })
        # Trier par "score de concurrence" : kw_common * sqrt(traffic + 1) / (DR + 10)
        # Privilégie ceux qui ont vraiment des kw communs sur un volume comparable
        import math
        for c in filtered:
            c["_score"] = (c["keywords_common"] ** 2) * math.sqrt(c["traffic"] + 1) / max(c["dr"] + 10, 1)
        filtered.sort(key=lambda x: x["_score"], reverse=True)
        data["competitors"] = [{k: v for k, v in c.items() if not k.startswith("_")} for c in filtered[:8]]
        print(f"  Competitors: {len(data['competitors'])} (filtré {len(raw)} → {len(filtered)})")
    except Exception as e:
        print(f"  Competitors error: {e}")
        data["competitors"] = []

    # Save to cache
    cache_file = SEO_DIR / f"{code}-ahrefs-latest.json"
    cache_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"  Saved to {cache_file}")

    # Also update the legacy format (used by /api/dashboard/{site})
    legacy_file = SEO_DIR / f"{code}-latest.json"
    if legacy_file.exists():
        try:
            legacy = json.loads(legacy_file.read_text())
            legacy['domain_rating'] = data.get('domain_rating')
            legacy['org_traffic'] = data.get('org_traffic')
            legacy['org_keywords'] = data.get('org_keywords')
            legacy['organic_keywords'] = [
                {'keyword': k['keyword'], 'volume': k['volume'], 'best_position': k['position'], 'keyword_difficulty': 0}
                for k in data.get('top_keywords', [])
            ]
            legacy['organic_competitors'] = [
                {'competitor_domain': c['domain'], 'keywords_common': c['keywords_common'], 'domain_rating': c['dr'], 'traffic': c['traffic']}
                for c in data.get('competitors', [])
            ]
            legacy['date'] = data['fetched_at'][:10]
            legacy_file.write_text(json.dumps(legacy, indent=2, ensure_ascii=False))
            print(f'  Synced to {legacy_file}')
        except Exception as e:
            print(f'  Legacy sync error: {e}')

    # Also save historical
    history_dir = SEO_DIR / "history"
    history_dir.mkdir(exist_ok=True)
    hist_file = history_dir / f"{code}-{TODAY}.json"
    hist_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    return data


def main():
    print(f"=== Ahrefs Daily Fetch — {TODAY} ===")

    # Check credits first + cache pour sidebar (lu par /api/ahrefs/usage)
    try:
        usage = api_get("subscription-info/limits-and-usage", {})
        info = usage.get("limits_and_usage", {})
        used = info.get("units_usage_api_key", 0)
        limit = info.get("units_limit_api_key")
        reset_at = info.get("subscription_information", {}).get("next_billing_date", "")
        print(f"Credits used today: {used}" + (f"/{limit}" if limit else ""))
        # Cache pour la sidebar widget
        try:
            usage_cache = SEO_DIR / "ahrefs-usage.json"
            usage_cache.write_text(json.dumps({
                "used":      used, "total": limit or 10000, "reset_at": reset_at,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False))
        except Exception:
            pass
        if limit and used > limit - 300:
            print("WARNING: Low credits remaining, aborting")
            sys.exit(0)
    except Exception as e:
        print(f"Could not check credits: {e}")

    for site in SITES:
        try:
            fetch_site(site)
        except Exception as e:
            print(f"ERROR fetching {site['code']}: {e}")

    print("=== Done ===")


if __name__ == "__main__":
    main()
