#!/usr/bin/env python3
"""
workflow_runner.py — Orchestrateur quotidien du module Workflow.

Pour chaque site (lcr, mkd) où god_mode_state.enabled = TRUE :
  1. Tire 1 département pondéré population
  2. Sélectionne les top_n villes ≥10k hab du département
  3. Pour chaque secteur : scrape Serper places
  4. Qualifie via DeepSeek (buyer true/false)
  5. Pousse les qualifiés vers Emelia (max 50 / site / jour)
  6. Envoie un récap Telegram

Usage :
  python3 scripts/workflow_runner.py                          # tout, prod
  python3 scripts/workflow_runner.py --site lcr               # un seul site
  python3 scripts/workflow_runner.py --site lcr --dept 75     # forcer dept
  python3 scripts/workflow_runner.py --dry-run                # pas de push Emelia

Cron : 30 6 * * 1-5  (lun-ven, 6h30 UTC)
"""

import argparse
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

import god_mode_backend as gm
import god_mode_agents as agents
import workflow_geo as geo
from workflow_qualifier import qualify_prospect
from mailnjoy_check import check_pending_queue
from workflow_emelia_push import push_prospect

import duckdb
import requests

# Load .env
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip("\x27\""))

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"


def telegram(msg: str):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception:
        pass


def run_site(site: str, forced_dept: str | None = None,
             scrape_quota: int = 30, daily_emelia_limit: int = 50,
             dry_run: bool = False) -> dict:
    print(f"\n=== Workflow runner — site {site.upper()} ===")
    state = gm.get_state(site)
    if not (state and state.get("enabled")):
        print(f"  Site {site} désactivé (state.enabled=False) → skip")
        return {"site": site, "skipped": "disabled"}

    if forced_dept:
        dept_code = forced_dept
        dept = next((d for d in geo.list_departments() if d["code"] == dept_code), None)
        if not dept:
            return {"site": site, "error": f"dept {dept_code} introuvable"}
    else:
        dept = geo.next_dept_by_priority()  # 2026-05-22 — priorité 92/75/59/69 puis pop desc
        dept_code = dept["code"]

    cities = geo.resolve_dept_to_cities(dept_code, top_n=5)
    if not cities:
        return {"site": site, "error": f"aucune ville ≥10k hab dans dept {dept_code}"}

    print(f"  Département : {dept['name']} ({dept_code})")
    print(f"  Villes      : {', '.join(c['name'] for c in cities)}")

    city_names = [c["name"] for c in cities]
    per_sector = max(1, scrape_quota // len(gm.SECTORS_GOD_MODE))
    summary_per_sector: dict[str, dict] = {}
    pushed_count = 0

    for sector in gm.SECTORS_GOD_MODE:
        if not dry_run and pushed_count >= daily_emelia_limit:
            print(f"  Quota Emelia {daily_emelia_limit} atteint → arrêt scrape")
            break
        print(f"\n  -- Secteur {sector} --")
        # Scrape
        res = agents.scrape_sector(site, sector, cities=city_names, max_results=per_sector,
                                   username="workflow_runner")
        scraped = res.get("scraped", 0)
        valid = res.get("valid", 0)
        print(f"    scrape: {scraped} bruts, {valid} validés (email OK)")

        # === Mailnjoy drain — vérifie chaque pending row puis insert scrappe OU delete ===
        mn = check_pending_queue(site_code=site)
        if mn.get("error"):
            print(f"    mailnjoy ERROR: {mn['error']}")
        else:
            print(f"    mailnjoy: valid={mn.get('valid',0)} risky={mn.get('risky',0)} invalid={mn.get('invalid',0)} errored={mn.get('errored',0)} credit_left={mn.get('credit_left')}")

        # Récupère les prospects fraîchement insérés (created_at > 5 min)
        c = duckdb.connect(str(GOD_DB))
        try:
            rows = c.execute("""
                SELECT id, company_name, sector, city, email, phone, website, raw_data
                FROM scrappe
                WHERE site_code=? AND sector=? AND created_at > now() - INTERVAL 10 MINUTE
                  AND status='mailnjoy_valid'
                  AND qualifier_buyer IS NULL
                  AND emelia_contact_id IS NULL
                ORDER BY created_at DESC
                LIMIT ?
            """, [site, sector, per_sector * 2]).fetchall()
        finally:
            c.close()

        sec_qualified = 0
        sec_pushed = 0
        sec_rejected = 0
        import json as _json
        for row in rows:
            pid, company, sec, city, email, phone, website, raw = row
            # raw peut être str (JSON sérialisé en DuckDB) ou dict
            if isinstance(raw, str):
                try:
                    raw = _json.loads(raw)
                except Exception:
                    raw = {}
            raw = raw or {}
            # Enrich avec dept_code (depuis ville)
            city_obj = next((cc for cc in cities if cc["name"].lower() == (city or "").lower()), None)
            dept_for_prospect = city_obj["dept"] if city_obj else dept_code
            region_for_prospect = city_obj["region"] if city_obj else dept["region_code"]

            prospect_dict = {
                "company_name": company, "sector": sec, "city": city,
                "dept_code": dept_for_prospect, "email": email,
                "phone": phone, "website": website, "raw_data": raw,
            }
            verdict = qualify_prospect(prospect_dict, site=site)

            # Update DB avec verdict + geo
            c = duckdb.connect(str(GOD_DB))
            try:
                c.execute("""
                    UPDATE scrappe SET qualifier_buyer=?, qualifier_reason=?,
                                       dept_code=?, region_code=?
                    WHERE id=?
                """, [verdict["buyer"], verdict["reason"], dept_for_prospect, region_for_prospect, pid])
            finally:
                c.close()

            if verdict["buyer"]:
                sec_qualified += 1
                if dry_run:
                    print(f"      [dry] {company} ({city}, {dept_for_prospect}) → {verdict['reason']}")
                    continue
                if pushed_count >= daily_emelia_limit:
                    break
                pres = push_prospect(site, pid, daily_limit=daily_emelia_limit)
                if pres.get("pushed"):
                    sec_pushed += 1
                    pushed_count += 1
                    print(f"      ✓ pushed {company} → campaign {pres.get('campaign_name')}")
                else:
                    print(f"      ✗ push skipped {company}: {pres.get('reason')}")
            else:
                sec_rejected += 1

            time.sleep(0.3)  # politesse DeepSeek + Emelia

        summary_per_sector[sector] = {
            "scraped": scraped, "valid": valid,
            "qualified": sec_qualified, "rejected_by_ai": sec_rejected, "pushed": sec_pushed,
        }

    # Récap Telegram
    total_scraped = sum(s["scraped"] for s in summary_per_sector.values())
    total_pushed = sum(s["pushed"] for s in summary_per_sector.values())
    msg_lines = [
        f"🔁 *Workflow — {site.upper()}*",
        f"Département : *{dept['name']}* ({dept_code})",
        f"Scrapés : {total_scraped}  •  Poussés Emelia : {total_pushed}",
        "",
        *[f"  • {k:11} → {v['pushed']} (sur {v['valid']} valid., {v['qualified']} qualifiés)"
          for k, v in summary_per_sector.items()],
    ]
    telegram("\n".join(msg_lines))

    return {
        "site": site, "dept": dept_code, "cities": city_names,
        "total_pushed": total_pushed, "total_scraped": total_scraped,
        "per_sector": summary_per_sector,
        "dry_run": dry_run,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["lcr", "mkd", "both"], default="both")
    parser.add_argument("--dept", default=None, help="code département à forcer (ex 75)")
    parser.add_argument("--scrape-quota", type=int, default=30,
                        help="prospects scrapés max par site/jour (divisé par 6 secteurs)")
    parser.add_argument("--daily-limit", type=int, default=50,
                        help="contacts max poussés vers Emelia par site/jour")
    parser.add_argument("--dry-run", action="store_true",
                        help="ne pousse rien vers Emelia, qualifie seulement")
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc).isoformat()
    print(f"[workflow_runner] start {started_at} args={vars(args)}")

    sites = ["lcr", "mkd"] if args.site == "both" else [args.site]
    results = []
    for s in sites:
        try:
            r = run_site(s, forced_dept=args.dept,
                         scrape_quota=args.scrape_quota,
                         daily_emelia_limit=args.daily_limit,
                         dry_run=args.dry_run)
            results.append(r)
        except Exception as e:
            print(f"  ERR {s}: {e}")
            results.append({"site": s, "error": str(e)})

    print(f"\n[workflow_runner] done")
    for r in results:
        print(f"  {r}")


if __name__ == "__main__":
    main()
