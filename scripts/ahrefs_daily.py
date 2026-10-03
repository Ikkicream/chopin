#!/usr/bin/env python3
"""
Genesis — Ahrefs Daily Fetch (version MINIMALISTE 2026-05-22)

Ne fait QU'UNE chose : récupérer 'site-explorer/metrics' pour chaque site.
C'est le seul endpoint qui justifie une fréquence quotidienne (KPI de trajectoire).

Tout le reste (domain-rating, organic-keywords, organic-competitors, etc.) est
déplacé dans ahrefs_monthly_audit.py — voir specs/seo-playbook.md.

Cron : 0 6 * * *
Budget : ~100 unités / jour (50 × 2 sites) = ~3 000 / mois

Ancienne version backupée : ahrefs_daily.py.bak-2026-05-22
"""

import json
import os
import sys
from datetime import datetime, timezone, date
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent.parent
SEO_DIR  = BASE_DIR / "memory" / "seo"
SEO_DIR.mkdir(parents=True, exist_ok=True)

# .env
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

SITES = [
    {"code": "lcr", "domain": "leclientroi.com"},
    {"code": "mkd", "domain": "mkdgroupe.com"},
]
TODAY = date.today().isoformat()

# Budget gate
sys.path.insert(0, str(BASE_DIR / "scripts"))
from cost_tracker import check_ahrefs_budget, track  # noqa


def api_get(endpoint, params):
    r = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_metrics(site):
    """Récupère uniquement les KPI principaux (1 appel = 50 unités).
    NOTE 2026-05-22 : bypass volontaire de la gate budget. site-explorer/metrics
    est l'unique KPI quotidien essentiel et n'est JAMAIS bloqué, même en
    dépassement de quota. Décision user.
    """
    domain, code = site["domain"], site["code"]

    try:
        m = api_get("site-explorer/metrics", {
            "target": domain, "date": TODAY, "country": "fr", "mode": "domain"
        })
        metrics = m.get("metrics", {})
        data = {
            "site":                code,
            "domain":              domain,
            "fetched_at":          datetime.now(timezone.utc).isoformat(),
            "org_traffic":         metrics.get("org_traffic", 0),
            "org_keywords":        metrics.get("org_keywords", 0),
            "org_keywords_top3":   metrics.get("org_keywords_1_3", 0),
            "org_cost_usd_cents": metrics.get("org_cost", 0),
        }
        track("seo-se-metrics", "seo", "ahrefs-api", input_tok=50, note=f"{code} · metrics · 50 units", site=code)
        print(f"[{code}] traffic={data['org_traffic']} kw={data['org_keywords']} top3={data['org_keywords_top3']}")
        return data
    except Exception as e:
        print(f"[{code}] ERROR metrics : {e}")
        return None


def save_history(site_code, data):
    """Sauve dans cache + historique journalier."""
    # Cache courant (utilisé par /api/seo et /api/dashboard)
    cache = SEO_DIR / f"{site_code}-metrics-latest.json"
    cache.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # Historique journalier
    hist_dir = SEO_DIR / "history"
    hist_dir.mkdir(exist_ok=True)
    (hist_dir / f"{site_code}-metrics-{TODAY}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False)
    )

    # Synchro format legacy {code}-latest.json (consommé par /api/dashboard/{site})
    legacy = SEO_DIR / f"{site_code}-latest.json"
    if legacy.exists():
        try:
            blob = json.loads(legacy.read_text())
            blob["org_traffic"]  = data.get("org_traffic")
            blob["org_keywords"] = data.get("org_keywords")
            blob["date"]         = TODAY
            legacy.write_text(json.dumps(blob, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"  legacy sync error: {e}")


def update_usage_cache():
    """Rafraichit le cache de conso (subscription-info ne coûte rien)."""
    try:
        r = requests.get(f"{BASE_URL}/subscription-info/limits-and-usage",
                         headers=HEADERS, timeout=10)
        if r.status_code == 200:
            info = r.json().get("limits_and_usage", {})
            cache = {
                "used":       info.get("units_usage_api_key", 0),
                "total":      info.get("units_limit_api_key") or 10000,
                "reset_at":   info.get("usage_reset_date", ""),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            (SEO_DIR / "ahrefs-usage.json").write_text(
                json.dumps(cache, ensure_ascii=False, indent=2)
            )
            print(f"Credits used: {cache['used']} / {cache['total']} "
                  f"({round(100*cache['used']/cache['total'],1)}%) — reset {cache['reset_at'][:10]}")
    except Exception as e:
        print(f"Usage check failed: {e}")


def main():
    print(f"=== Ahrefs Daily (minimal) — {TODAY} ===")
    update_usage_cache()
    for site in SITES:
        data = fetch_metrics(site)
        if data:
            save_history(site["code"], data)
    print("=== Done ===")


if __name__ == "__main__":
    main()
