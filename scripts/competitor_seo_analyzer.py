#!/usr/bin/env python3
"""
competitor_seo_analyzer.py — Analyse concurrentielle SEO basée sur une SEED de concurrents connus.

Au lieu de partir des concurrents qu'Ahrefs détecte (= ceux qui rank sur tes maigres keywords),
on part d'une SEED métier (smsmode, octopush, primotexto...) et on regarde leurs top 30 keywords.

Output : `memory/seo/{site}-competitor-analysis.json` avec :
  - tableau de tous les keywords des concurrents
  - score d'opportunité par keyword
  - keyword gaps (eux rank, toi pas)
  - plan d'articles priorité

Score d'opportunité d'un keyword :
  score = volume × (1 - KD/100) × nb_concurrents_ranking × bonus_already_ranked_position

Lourd côté Ahrefs : ~30 keywords × ~10 concurrents = ~10 appels site-explorer/organic-keywords par site
                    ≈ 50 crédits Ahrefs par run (budget 10000/mois OK pour 1 run/sem)

Cron suggéré : 0 5 * * 1 (lundi 5h UTC) — produit la liste avant que seo_strategy_agent tourne
"""

import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, date
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent
SEO_DIR = BASE_DIR / "memory" / "seo"
SEO_DIR.mkdir(parents=True, exist_ok=True)

# Load env
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip("'\""))

AHREFS_TOKEN = os.environ.get("AHREFS_API_KEY", "")
BASE_URL = "https://api.ahrefs.com/v3"
HEADERS = {"Authorization": f"Bearer {AHREFS_TOKEN}", "Accept": "application/json"}
TODAY = date.today().isoformat()
TOP_N = 30  # nombre de keywords à fetch par concurrent

# Seed métier — concurrents à analyser pour chaque site
SEED_COMPETITORS = {
    "lcr": [
        # Routage SMS pro
        "smsmode.com", "octopush.com", "primotexto.com", "allmysms.com",
        "smsfactor.com", "spothit.fr", "spot-hit.fr", "wellpack.fr",
        "esendex.fr", "dexem.com", "smspartner.fr",
        # Location de données B2B/B2C (validés camille 2026-05-21)
        "manageo.com", "manageo.fr", "sosdata.fr", "ecodata-france.com",
        # Groupe data marketing FR (Dekuple)
        "dekuple.com", "agence.dekuple.com",
    ],
    "mkd": [
        "kompass.com", "societe.com", "manageo.com", "easybusiness.com",
        "corporama.com", "infonet.fr", "lusha.com", "explore-france.fr",
    ],
}

SITES = [
    {"code": "lcr", "domain": "leclientroi.com"},
    {"code": "mkd", "domain": "mkdgroupe.com"},
]


def api_get(endpoint: str, params: dict, retries: int = 3) -> dict:
    """GET Ahrefs avec retry exponentiel sur 429."""
    for attempt in range(retries):
        r = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=30)
        if r.status_code == 429:
            wait = 8 * (attempt + 1)  # 8s, 16s, 24s
            print(f"      Rate limit, attente {wait}s…")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return {}


def fetch_top_keywords(domain: str, top_n: int = TOP_N) -> list[dict]:
    """Top N keywords positionnés (par trafic) d'un domaine.

    mode=subdomains nécessaire pour les concurrents (sinon Ahrefs renvoie 0).
    """
    try:
        d = api_get("site-explorer/organic-keywords", {
            "target": domain, "date": TODAY, "country": "fr", "mode": "subdomains",
            "select": "keyword,best_position,volume,sum_traffic,keyword_difficulty,cpc",
            "order_by": "sum_traffic:desc",
            "limit": top_n,
        })
        return d.get("keywords", [])
    except Exception as e:
        print(f"    Erreur keywords {domain}: {e}")
        return []


def fetch_own_keywords(domain: str) -> list[str]:
    """Liste des keywords sur lesquels NOUS rank — pour identifier les gaps."""
    try:
        d = api_get("site-explorer/organic-keywords", {
            "target": domain, "date": TODAY, "country": "fr", "mode": "domain",
            "select": "keyword",
            "order_by": "sum_traffic:desc", "limit": 200,
        })
        return [k.get("keyword", "").lower() for k in d.get("keywords", [])]
    except Exception:
        return []


def analyze_site(site_code: str, site_domain: str) -> dict:
    """Analyse concurrentielle complète d'un site."""
    print(f"\n=== {site_code.upper()} ({site_domain}) ===")
    competitors = SEED_COMPETITORS.get(site_code, [])
    if not competitors:
        return {"error": "no seed for site"}

    print(f"  Fetch nos propres keywords...")
    own = set(fetch_own_keywords(site_domain))
    print(f"    {len(own)} keywords positionnés actuellement")

    # Collecte tous les keywords des concurrents
    all_keywords: dict[str, dict] = {}  # keyword → {volume, kd, cpc, competitors: [{domain, position, traffic}]}
    for comp in competitors:
        print(f"  Fetch top {TOP_N} kw de {comp}...")
        kw_list = fetch_top_keywords(comp, TOP_N)
        print(f"    {len(kw_list)} kw retournés")
        time.sleep(2)  # Pause anti-rate-limit Ahrefs
        for kw in kw_list:
            keyword = (kw.get("keyword", "") or "").lower().strip()
            if not keyword:
                continue
            entry = all_keywords.setdefault(keyword, {
                "keyword":              keyword,
                "volume":               kw.get("volume", 0) or 0,
                "keyword_difficulty":   kw.get("keyword_difficulty", 0) or 0,
                "cpc":                  kw.get("cpc", 0) or 0,
                "competitors":          [],
                "already_own_ranking":  keyword in own,
            })
            entry["competitors"].append({
                "domain":   comp,
                "position": kw.get("best_position", 0) or 0,
                "traffic":  kw.get("sum_traffic", 0) or 0,
            })
            # Take max volume / KD si plusieurs concurrents ont la même donnée
            entry["volume"] = max(entry["volume"], kw.get("volume", 0) or 0)
            entry["keyword_difficulty"] = max(entry["keyword_difficulty"], kw.get("keyword_difficulty", 0) or 0)

    # Calcul du score d'opportunité
    # score = volume × (1 - KD/100) × nb_concurrents_qui_rank × bonus_si_pas_encore_chez_nous
    keywords_list = []
    for kw in all_keywords.values():
        nb_c = len(kw["competitors"])
        vol = kw["volume"]
        kd = kw["keyword_difficulty"]
        gap_bonus = 1.5 if not kw["already_own_ranking"] else 0.5  # gap = +50%, déjà chez nous = -50%
        score = vol * (1 - kd / 100) * nb_c * gap_bonus
        kw["opportunity_score"] = round(score, 1)
        keywords_list.append(kw)

    # Tri par score décroissant
    keywords_list.sort(key=lambda x: -x["opportunity_score"])

    # Gaps : keywords où ≥2 concurrents rank mais pas nous
    gaps = [k for k in keywords_list if not k["already_own_ranking"] and len(k["competitors"]) >= 2]

    # Plan d'articles : top 20 keywords gap avec KD < 30 (gagnable)
    plan = [k for k in gaps if k["keyword_difficulty"] < 30][:20]

    # Stats agrégées
    total_kw_seen = len(all_keywords)
    total_kw_gaps = len(gaps)
    total_kw_own = sum(1 for k in keywords_list if k["already_own_ranking"])
    total_competitor_traffic = sum(
        c["traffic"]
        for kw in keywords_list
        for c in kw["competitors"]
    )

    result = {
        "site":                site_code,
        "domain":              site_domain,
        "analyzed_at":         datetime.now(timezone.utc).isoformat(),
        "competitors_seed":    competitors,
        "stats": {
            "competitors_analyzed":      len(competitors),
            "total_keywords_seen":       total_kw_seen,
            "keywords_we_already_rank":  total_kw_own,
            "keyword_gaps":              total_kw_gaps,
            "competitor_traffic_total":  total_competitor_traffic,
            "own_keywords_count":        len(own),
        },
        "top_opportunities":   keywords_list[:50],
        "gaps":                gaps[:50],
        "article_plan":        plan,
    }
    print(f"\n  Stats : {result['stats']}")
    print(f"  Top 5 opportunités :")
    for k in keywords_list[:5]:
        rank = "✓" if k["already_own_ranking"] else "○"
        print(f"    {rank} {k['keyword'][:50]:50s} vol={k['volume']:5d} KD={k['keyword_difficulty']:3d} score={k['opportunity_score']:.0f}")

    # Sauvegarde JSON
    out = SEO_DIR / f"{site_code}-competitor-analysis.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"  Sauvegardé : {out}")

    # RAG : archive un résumé markdown pour usage futur
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from rag_writer import save_chunk
        rag_content_lines = [
            f"Analyse concurrentielle SEO du {result['analyzed_at'][:10]} pour {site_code.upper()} ({site_domain}).",
            "",
            f"## Stats",
            f"- Concurrents analysés : {result['stats']['competitors_analyzed']}",
            f"- Keywords vus chez les concurrents : {result['stats']['total_keywords_seen']}",
            f"- Gaps (keywords où nous ne rank pas mais ≥2 concurrents oui) : {result['stats']['keyword_gaps']}",
            f"- Trafic concurrentiel total : {result['stats']['competitor_traffic_total']} visites/mois",
            "",
            f"## Top opportunités",
        ]
        for k in keywords_list[:30]:
            n_c = len(k["competitors"])
            rag_content_lines.append(
                f"- **{k['keyword']}** — vol {k['volume']}/mois, KD {k['keyword_difficulty']}, "
                f"{n_c} concurrent(s) y rank, score {k['opportunity_score']:.0f}, "
                f"{'déjà chez nous' if k['already_own_ranking'] else 'GAP'}"
            )
        save_chunk(
            site=site_code,
            source="ahrefs",
            agent="competitor_seo_analyzer",
            content="\n".join(rag_content_lines),
            metadata={
                "prompt_summary": f"Analyse concurrentielle {site_code} {result['analyzed_at'][:10]}",
                "competitors_count":  result["stats"]["competitors_analyzed"],
                "keywords_seen":      result["stats"]["total_keywords_seen"],
                "tags":               ["seo", "competitor", site_code, "ahrefs"],
            },
        )
    except Exception as e:
        print(f"  [rag] erreur archivage : {e}")

    return result


def main():
    if not AHREFS_TOKEN:
        print("ERROR: AHREFS_API_KEY non défini")
        sys.exit(1)

    print(f"=== Competitor SEO Analyzer — {TODAY} ===")
    # Check credits
    try:
        usage = api_get("subscription-info/limits-and-usage", {})
        info = usage.get("limits_and_usage", {})
        used = info.get("units_usage_api_key", 0)
        limit = info.get("units_limit_api_key", 10000)
        remaining = (limit or 10000) - used
        print(f"Ahrefs credits : {used}/{limit} (reste {remaining})")
        if remaining < 100:
            print("WARN: Moins de 100 crédits restants — abort")
            return
    except Exception as e:
        print(f"Warning credits check: {e}")

    for s in SITES:
        try:
            analyze_site(s["code"], s["domain"])
        except Exception as e:
            print(f"ERROR {s['code']}: {e}")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
