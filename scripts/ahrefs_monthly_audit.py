#!/usr/bin/env python3
"""
Genesis — Ahrefs Monthly Audit (créé 2026-05-22)

Audit SEO complet, 1 fois par mois (1er du mois à 6h UTC).
Remplace ce que ahrefs_daily.py faisait avant (et que ça n'aurait jamais dû faire).

Endpoints couverts (Tier 1 + Tier 2 du SEO playbook) :
  - site-audit/issues        → corrections techniques à apporter (critique)
  - site-explorer/domain-rating
  - site-explorer/organic-keywords      (limit=20)
  - site-explorer/top-pages              (limit=20)
  - site-explorer/broken-backlinks       (limit=20)
  - site-explorer/organic-competitors    (limit=10)

Budget estimé : ~700 unités / site / run = ~1 400 / mois pour LCR + MKD.

Output : memory/seo/{site}-audit-latest.json + memory/seo/audits/{site}-{YYYY-MM}.json

Cron : 0 6 1 * *
Usage manuel : python3 scripts/ahrefs_monthly_audit.py [--site lcr|mkd|both] [--force]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, date
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent.parent
SEO_DIR  = BASE_DIR / "memory" / "seo"
AUDITS   = SEO_DIR / "audits"
AUDITS.mkdir(parents=True, exist_ok=True)

env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.startswith("AHREFS_API_KEY="):
            os.environ.setdefault("AHREFS_API_KEY", line.split("=", 1)[1].strip().strip('"').strip("'"))
            break

AHREFS_TOKEN = os.environ.get("AHREFS_API_KEY", "")
if not AHREFS_TOKEN:
    print("ERROR: AHREFS_API_KEY not found"); sys.exit(1)

BASE_URL = "https://api.ahrefs.com/v3"
HEADERS  = {"Authorization": f"Bearer {AHREFS_TOKEN}", "Accept": "application/json"}

# Mapping site code → infos Ahrefs (project_id pour site-audit, domain pour site-explorer)
SITES = {
    "lcr": {
        "domain":            "leclientroi.com",
        "site_audit_project": "8344256",   # 'Leclientroi' dans Ahrefs
    },
    "mkd": {
        "domain":            "mkdgroupe.com",
        "site_audit_project": None,         # ⚠️ pas de projet Site Audit. À créer dans l'UI Ahrefs.
    },
}

TODAY    = date.today().isoformat()
THIS_MO  = date.today().strftime("%Y-%m")

sys.path.insert(0, str(BASE_DIR / "scripts"))
from cost_tracker import check_ahrefs_budget, track  # noqa


def api_get(endpoint, params, cost_estimate, critical=True, site_code="", note_label=""):
    """Wrapper : check budget → call → log cost."""
    ok, info = check_ahrefs_budget(cost_estimate=cost_estimate, critical=critical)
    if not ok:
        print(f"  [{site_code}/{note_label}] SKIP — budget : {info['reason']}")
        return None
    try:
        r = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        action = "seo-audit-" + note_label.replace("_", "-")
        track(action, "seo-audit", "ahrefs-api",
              input_tok=cost_estimate, note=f"{site_code} · {note_label} · ~{cost_estimate} units", site=site_code)
        return r.json()
    except Exception as e:
        print(f"  [{site_code}/{note_label}] ERROR : {e}")
        return None


def audit_site(code, cfg):
    domain  = cfg["domain"]
    project = cfg["site_audit_project"]
    print(f"\n=== Audit {code} ({domain}) ===")

    audit = {
        "site":       code,
        "domain":     domain,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "month":      THIS_MO,
    }

    # 1. Site Audit / issues (corrections techniques)
    if project:
        data = api_get("site-audit/issues",
                       {"project_id": project, "limit": 100},
                       cost_estimate=100, critical=True, site_code=code, note_label="issues")
        if data:
            issues = data.get("issues", [])
            audit["issues"] = issues
            errors   = [i for i in issues if i.get("category") == "error"]
            warnings = [i for i in issues if i.get("category") == "warning"]
            notices  = [i for i in issues if i.get("category") == "notice"]
            audit["issues_summary"] = {
                "errors": len(errors), "warnings": len(warnings), "notices": len(notices),
            }
            print(f"  issues: {len(errors)} errors · {len(warnings)} warnings · {len(notices)} notices")
    else:
        audit["issues"] = []
        audit["issues_summary"] = {"note": "No Site Audit project configured for this site. Create one at https://app.ahrefs.com/site-audit"}
        print(f"  issues: SKIP (no project_id — créer un projet Site Audit pour {domain})")

    # 2. Domain Rating
    data = api_get("site-explorer/domain-rating",
                   {"target": domain, "date": TODAY},
                   cost_estimate=50, critical=True, site_code=code, note_label="domain_rating")
    if data:
        dr = data.get("domain_rating", {})
        audit["domain_rating"] = dr.get("domain_rating")
        audit["ahrefs_rank"]   = dr.get("ahrefs_rank")
        print(f"  DR={audit['domain_rating']} ahrefs_rank={audit['ahrefs_rank']}")

    # 3. Organic keywords (top 20)
    data = api_get("site-explorer/organic-keywords",
                   {"target": domain, "date": TODAY, "country": "fr", "mode": "domain",
                    "select": "keyword,best_position,volume,sum_traffic,cpc,keyword_difficulty",
                    "order_by": "sum_traffic:desc", "limit": 20},
                   cost_estimate=200, critical=True, site_code=code, note_label="organic_keywords")
    if data:
        audit["organic_keywords"] = data.get("keywords", [])
        print(f"  organic keywords: {len(audit['organic_keywords'])}")

    # 4. Top pages (top 20)
    data = api_get("site-explorer/pages-by-traffic",
                   {"target": domain, "date": TODAY, "country": "fr", "mode": "domain",
                    "select": "url,sum_traffic,sum_keywords,value",
                    "order_by": "sum_traffic:desc", "limit": 20},
                   cost_estimate=100, critical=True, site_code=code, note_label="top_pages")
    if data:
        audit["top_pages"] = data.get("pages", [])
        print(f"  top pages: {len(audit['top_pages'])}")

    # 5. Broken backlinks (corrections directes — redirect 301)
    data = api_get("site-explorer/broken-backlinks",
                   {"target": domain, "mode": "domain",
                    "select": "url_from,url_to,anchor,domain_rating_source,first_seen",
                    "order_by": "domain_rating_source:desc", "limit": 20},
                   cost_estimate=100, critical=True, site_code=code, note_label="broken_backlinks")
    if data:
        audit["broken_backlinks"] = data.get("backlinks", [])
        print(f"  broken backlinks (à rediriger 301): {len(audit['broken_backlinks'])}")

    # 6. Organic competitors (top 10)
    data = api_get("site-explorer/organic-competitors",
                   {"target": domain, "date": TODAY, "country": "fr", "mode": "domain",
                    "select": "competitor_domain,keywords_common,domain_rating,traffic",
                    "order_by": "keywords_common:desc", "limit": 10},
                   cost_estimate=100, critical=False, site_code=code, note_label="organic_competitors")
    if data:
        audit["organic_competitors"] = data.get("competitors", [])
        print(f"  competitors: {len(audit['organic_competitors'])}")

    # Save
    latest = SEO_DIR / f"{code}-audit-latest.json"
    monthly = AUDITS / f"{code}-{THIS_MO}.json"
    latest.write_text(json.dumps(audit, indent=2, ensure_ascii=False))
    monthly.write_text(json.dumps(audit, indent=2, ensure_ascii=False))
    print(f"  saved : {latest.name} + {monthly.name}")
    return audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="both", choices=["lcr", "mkd", "both"])
    parser.add_argument("--force", action="store_true", help="Override budget gate (à utiliser avec précaution)")
    args = parser.parse_args()

    print(f"=== Ahrefs Monthly Audit — {THIS_MO} ===")
    targets = [args.site] if args.site != "both" else ["lcr", "mkd"]
    for code in targets:
        if code not in SITES:
            print(f"Unknown site: {code}"); continue
        audit_site(code, SITES[code])
    print("\n=== Audit terminé ===")


if __name__ == "__main__":
    main()
