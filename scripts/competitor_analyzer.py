#!/usr/bin/env python3
"""
competitor_analyzer.py — Analyse un concurrent via Ahrefs API.
Scrape ses top keywords, pages, et stratégie → génère des recommandations.

Usage: python3 scripts/competitor_analyzer.py --domain greenbureau.com --site lcr
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, date
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent.parent
SEO_DIR = BASE_DIR / "memory" / "seo"
RECO_FILE = SEO_DIR / "recommendations.json"

# Load env
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip("'\""))

AHREFS_KEY = os.environ.get("AHREFS_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AHREFS_URL = "https://api.ahrefs.com/v3"
AHREFS_HEADERS = {"Authorization": f"Bearer {AHREFS_KEY}", "Accept": "application/json"}

TODAY = date.today().isoformat()


def ahrefs_get(endpoint, params):
    r = requests.get(f"{AHREFS_URL}/{endpoint}", headers=AHREFS_HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def analyze_competitor(domain, site):
    """Fetch competitor data from Ahrefs and generate strategy insights."""
    print(f"[competitor] Analyzing {domain} for {site}...")

    # 1. Domain Rating
    try:
        dr_data = ahrefs_get("site-explorer/domain-rating", {"target": domain, "date": TODAY})
        dr = dr_data["domain_rating"]["domain_rating"]
        print(f"  DR: {dr}")
    except Exception as e:
        dr = 0
        print(f"  DR error: {e}")

    # 2. Metrics
    try:
        m = ahrefs_get("site-explorer/metrics", {"target": domain, "date": TODAY, "country": "FR", "mode": "subdomains"})
        metrics = m["metrics"]
        traffic = metrics.get("org_traffic", 0)
        kw_count = metrics.get("org_keywords", 0)
        print(f"  Traffic: {traffic}, Keywords: {kw_count}")
    except Exception as e:
        traffic, kw_count = 0, 0
        print(f"  Metrics error: {e}")

    # 3. Top keywords (their best performing)
    try:
        kw = ahrefs_get("site-explorer/organic-keywords", {
            "target": domain, "date": TODAY, "country": "FR", "mode": "subdomains",
            "select": "keyword,best_position,volume,sum_traffic",
            "order_by": "sum_traffic:desc", "limit": 10
        })
        top_kw = kw.get("keywords", [])
        print(f"  Top keywords: {len(top_kw)}")
    except Exception as e:
        top_kw = []
        print(f"  Keywords error: {e}")

    # 4. Top pages
    try:
        pages = ahrefs_get("site-explorer/top-pages", {
            "target": domain, "date": TODAY, "country": "FR", "mode": "subdomains",
            "select": "url,sum_traffic,keywords",
            "order_by": "sum_traffic:desc", "limit": 5
        })
        top_pages = pages.get("pages", [])
        print(f"  Top pages: {len(top_pages)}")
    except Exception as e:
        top_pages = []
        print(f"  Pages error: {e}")

    # Save raw data
    comp_file = SEO_DIR / f"competitor-{domain.replace('.', '_')}.json"
    comp_data = {
        "domain": domain,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "dr": dr,
        "traffic": traffic,
        "keywords_count": kw_count,
        "top_keywords": top_kw,
        "top_pages": top_pages,
    }
    comp_file.write_text(json.dumps(comp_data, indent=2, ensure_ascii=False))
    print(f"  Saved to {comp_file}")

    # 5. Generate strategic recommendations using Claude
    print("  Generating strategy...")
    prompt = f"""Analyse ce concurrent et propose des recommandations pour le surpasser.

NOTRE SITE : {site.upper()}
CONCURRENT : {domain}
- Domain Rating : {dr}
- Trafic organique : {traffic}/mois
- Keywords positionnés : {kw_count}

LEURS TOP KEYWORDS (ce sur quoi ils rankent) :
{json.dumps(top_kw[:7], ensure_ascii=False, indent=2)}

LEURS TOP PAGES (leurs contenus les plus performants) :
{json.dumps(top_pages[:5], ensure_ascii=False, indent=2)}

Génère 3 recommandations CONCRÈTES pour voler leur trafic. Pour chaque :
- Explique leur stratégie (ce qu'ils font bien)
- Propose comment faire MIEUX
- Identifie les keywords qu'on peut leur prendre

Réponds en JSON valide :
[
  {{
    "type": "competitor",
    "title": "Action courte",
    "why": "Explication : {domain} fait X, ils rankent #Y sur 'keyword' avec Z visites/mois. On peut les battre parce que...",
    "how": "Étapes concrètes pour surpasser ce concurrent sur ce point",
    "priority": "haute|moyenne",
    "impact": "Estimation chiffrée",
    "keyword": "mot-clé principal ciblé"
  }}
]"""

    try:
        from llm_call import call_llm_json
        recos = call_llm_json(prompt, max_tokens=3000, module="competitor-analysis", action=f"analyze-{domain}", site=site)
    except Exception as e:
        print(f"  Strategy generation error: {e}")
        recos = []

    # Save recommendations
    if recos:
        all_recos = json.loads(RECO_FILE.read_text()) if RECO_FILE.exists() else {"lcr": [], "mkd": []}
        now = datetime.now(timezone.utc).isoformat()
        for i, r in enumerate(recos):
            r["id"] = f"reco_{site}_comp_{domain.replace('.','_')}_{i+1:02d}"
            r["site"] = site
            r["status"] = "pending"
            r["created_at"] = now
            r["source_competitor"] = domain
        all_recos[site] = all_recos.get(site, []) + recos
        RECO_FILE.write_text(json.dumps(all_recos, indent=2, ensure_ascii=False))
        print(f"  Added {len(recos)} competitor recommendations")

    print("[competitor] Done!")


# ── Mode agentique (boucle agent_core) ──────────────────────────────────────
# observe GSC/GA4/Ahrefs → recall signaux passés → decide via playbook
# skills/competitive-intel.md (format JSON intel_signal) → act = persiste le signal
# dans memory/seo/recommendations.json (compat) + agent_actions.

def _agentic_writer(item: dict, snapshot: dict, *, site: str, dry_run: bool):
    if item.get("action_type") != "intel_signal":
        print(f"  [agentic] action_type non géré: {item.get('action_type')!r} — skip")
        return
    target = item.get("target")
    tags = item.get("tags") or {}
    if not target:
        raise ValueError("plan sans target (concurrent/URL)")
    if dry_run:
        print(f"  [agentic] DRY-RUN signal {tags.get('signal_type')!r} "
              f"competitor={tags.get('competitor')!r} urgency={tags.get('urgency')!r}")
        item["dry_run"] = True
        return
    import sys as _sys
    from pathlib import Path as _Path
    reco_file = _Path(__file__).resolve().parent.parent / "memory" / "seo" / "recommendations.json"
    all_recos = json.loads(reco_file.read_text()) if reco_file.exists() else {"lcr": [], "mkd": []}
    now = datetime.now(timezone.utc).isoformat()
    signal = {
        "id": f"intel_{site}_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "site": site, "target": target,
        "priority": "high" if tags.get("urgency") == "immediate" else "medium",
        "type": "competitor", "title": f"Veille : {tags.get('competitor', target)}",
        "action": tags.get("suggested_action", item.get("why", "")),
        "competitor": tags.get("competitor"), "signal_type": tags.get("signal_type"),
        "topic": tags.get("topic"), "urgency": tags.get("urgency"),
        "why": item.get("why", ""),
        "status": "pending", "created_at": now, "source": "agentic",
    }
    all_recos.setdefault(site, []).insert(0, signal)
    reco_file.write_text(json.dumps(all_recos, indent=2, ensure_ascii=False))
    item["signal_id"] = signal["id"]


def run_agentic(site: str, dry_run: bool = True) -> dict:
    from functools import partial
    print(f"[competitor_analyzer agentic] Site: {site.upper()} — "
          f"{'DRY-RUN' if dry_run else 'LIVE'}")
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from agent_core import run_cycle
    writer = partial(_agentic_writer, site=site, dry_run=dry_run)
    result = run_cycle(agent="competitive-intel", site=site,
                       sources=("gsc", "ga4", "ahrefs"), writer_fn=writer)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain")
    parser.add_argument("--site", choices=["lcr", "mkd", "both"], default="lcr")
    parser.add_argument("--agentic", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    if args.agentic:
        sites = ["lcr", "mkd"] if args.site == "both" else [args.site]
        for s in sites:
            run_agentic(s, dry_run=not args.live)
        return

    if not args.domain:
        parser.error("--domain requis en mode classique (sinon --agentic)")
    analyze_competitor(args.domain, args.site)


if __name__ == "__main__":
    main()
