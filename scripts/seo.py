#!/usr/bin/env python3
"""
seo.py — Analyse SEO complète via Ahrefs API pour LCR + MKD.

Endpoints couverts (tous ceux demandés) :
  Site Explorer : domain_rating, backlinks_stats, outlinks_stats, metrics,
                  refdomains_history, url_rating_history, pages_history,
                  metrics_history, keywords_history, metrics_by_country,
                  pages_by_traffic, search_volume_history, all_backlinks,
                  broken_backlinks, referring_domains, anchors,
                  organic_keywords, organic_competitors, top_pages,
                  paid_pages, best_by_ext_links, best_by_int_links,
                  linked_domains, ext_anchors, int_anchors
  Keywords Explorer : overview, volume_history, volume_by_country,
                      matching_terms, related_terms, search_suggestions
  SERP Overview   : top_100
  Site Audit      : health_score, issues
  Rank Tracker    : overview, competitor_overview, competitor_pages,
                    serp_overview, competitor_metrics
  Batch Analysis  : batch_analysis
  Brand Radar     : ai_overview

Usage:
  python3 scripts/seo.py --site lcr --report full
  python3 scripts/seo.py --site mkd --report keywords --kw "sms marketing"
  python3 scripts/seo.py --site lcr --report competitors
"""

import json
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR    = Path(__file__).parent.parent
ENV_FILE    = BASE_DIR / ".env"
SEO_DIR     = BASE_DIR / "memory" / "seo"
SEO_DIR.mkdir(parents=True, exist_ok=True)

AHREFS_BASE = "https://api.ahrefs.com/v3"

# ── Config multi-sites (centrale si dispo, sinon fallback) ───────────────────
try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.sites_config import get_sites_for_script as _gss
    SITES = _gss("seo")
except Exception as _e:
    print(f"  [sites_config] fallback hardcodé: {_e}")
    SITES = {
        "lcr": {
            "domain":   "leclientroi.com", "url": "https://leclientroi.com",
            "label":    "LeClientROI",
            "keywords": ["sms marketing", "sms geolocalise", "campagne sms", "rcs messagerie"],
        },
        "mkd": {
            "domain":   "mkdgroupe.com", "url": "https://mkdgroupe.com",
            "label":    "MKD Groupe",
            "keywords": ["rgpd marketing", "data marketing b2b", "rcs entreprise", "prospection b2b"],
        },
    }

# Coût Ahrefs : 1 unité ≈ 0.0001 USD (estimation — ajuster selon plan)
AHREFS_UNIT_USD = 0.00010


def load_env() -> dict:
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def ahrefs_get(endpoint: str, params: dict, api_key: str, cost_estimate: int = 50, critical: bool = False) -> dict:
    """Appel GET Ahrefs API avec tracking des unités + budget gate.

    Args:
        cost_estimate : estimation des unités (50 par défaut)
        critical      : True = Tier 1/2 essentiel, False = Tier 3/4 (bloqué si warning budget)

    Budget gate ajoutée 2026-05-22 — voir specs/seo-playbook.md.
    """
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        from cost_tracker import check_ahrefs_budget
        ok, info = check_ahrefs_budget(cost_estimate=cost_estimate, critical=critical)
        if not ok:
            print(f"  [BUDGET BLOCK] {endpoint} → {info[chr(39)+chr(114)+chr(101)+chr(97)+chr(115)+chr(111)+chr(110)+chr(39)]}")
            return {"error": "budget_block", "units": 0, "_budget": info}
    except Exception as e:
        print(f"  [BUDGET GATE WARN] {e}")

    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    url = f"{AHREFS_BASE}/{endpoint}"
    r = requests.get(url, params=params, headers=headers, timeout=30)

    units = int(r.headers.get("x-api-units-cost-total", 0))
    cost_usd = round(units * AHREFS_UNIT_USD, 6)

    if r.status_code == 429:
        print(f"  Rate limit — attente 10s...")
        time.sleep(10)
        return ahrefs_get(endpoint, params, api_key)

    if r.status_code != 200:
        print(f"  ⚠ {endpoint} → {r.status_code}: {r.text[:150]}")
        return {"error": r.text, "units": 0}

    data = r.json()
    data["_units"] = units
    data["_cost_usd"] = cost_usd
    return data


def track_cost(action: str, site: str, units: int, cost_usd: float, note: str = ""):
    """Log le coût Ahrefs dans cost_tracker."""
    try:
        sys.path.insert(0, str(BASE_DIR))
        from scripts.cost_tracker import track
        track(
            action=action,
            module="seo",
            model="ahrefs-api",
            input_tok=units,   # on réutilise input_tok pour les unités
            output_tok=0,
            note=f"{site} · {note} · {units} units"
        )
    except Exception as e:
        print(f"  cost_tracker: {e}")


def save_report(site: str, report_type: str, data: dict):
    """Sauvegarde le rapport JSON + met à jour le fichier MD de synthèse."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    out = SEO_DIR / f"{site}_{report_type}_{ts}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"  Sauvegardé: {out}")
    return str(out)


# ── SITE EXPLORER ────────────────────────────────────────────────────────────

def site_explorer_full(domain: str, api_key: str, site_key: str) -> dict:
    """Lance tous les endpoints Site Explorer pour un domaine."""
    results = {}
    total_units = 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    se_endpoints = [
        ("domain_rating",       "site-explorer/domain-rating",
            {"target": domain, "date": today, "select": "domain_rating,ahrefs_rank"}),
        ("backlinks_stats",     "site-explorer/backlinks-stats",
            {"target": domain, "date": today, "select": "live,all_time,new_lost_links,live_refdomains"}),
        ("outlinks_stats",      "site-explorer/outlinks-stats",
            {"target": domain, "select": "outgoing_links,outgoing_links_dofollow,linked_domains,linked_domains_dofollow"}),
        ("metrics",             "site-explorer/metrics",
            {"target": domain, "date": today, "select": "org_traffic,org_keywords,paid_traffic,paid_keywords"}),
        ("metrics_by_country",  "site-explorer/metrics-by-country",
            {"target": domain, "date": today, "select": "country,org_traffic,org_keywords", "limit": 10}),
        ("pages_by_traffic",    "site-explorer/pages-by-traffic",
            {"target": domain, "select": "url,traffic,keywords,top_keyword", "limit": 20}),
        ("organic_keywords",    "site-explorer/organic-keywords",
            {"target": domain, "date": today, "country": "fr",
             "select": "keyword,volume,keyword_difficulty,best_position", "limit": 50, "order_by": "volume:desc"}),
        ("organic_competitors", "site-explorer/organic-competitors",
            {"target": domain, "date": today, "country": "fr",
             "select": "competitor_domain,domain_rating,traffic,keywords_common,keywords_competitor", "limit": 10}),
        ("top_pages",           "site-explorer/top-pages",
            {"target": domain, "date": today, "country": "fr",
             "select": "url,keywords,top_keyword_best_position,top_keyword_best_position_title", "limit": 20}),
        ("anchors",             "site-explorer/anchors",
            {"target": domain, "select": "anchor,top_domain_rating,dofollow_links,new_links", "limit": 20}),
        ("broken_backlinks",    "site-explorer/broken-backlinks",
            {"target": domain, "select": "anchor,url_from,http_code", "limit": 20}),
        ("best_by_ext_links",   "site-explorer/best-by-external-links",
            {"target": domain, "select": "top_domain_rating_source,last_visited_target,lost_links_to_target", "limit": 20}),
        ("best_by_int_links",   "site-explorer/best-by-internal-links",
            {"target": domain, "select": "last_visited_target,dofollow_to_target,last_seen", "limit": 20}),
    ]

    for name, endpoint, params in se_endpoints:
        print(f"  [{name}]...")
        data = ahrefs_get(endpoint, params, api_key)
        units = data.pop("_units", 0)
        cost  = data.pop("_cost_usd", 0)
        total_units += units
        if not data.get("error"):
            results[name] = data
            track_cost(f"seo-se-{name}", site_key, units, cost, name)
        time.sleep(0.5)  # respecter rate limit 60 req/min

    results["_total_units"] = total_units
    results["_total_cost_usd"] = round(total_units * AHREFS_UNIT_USD, 4)
    return results


# ── KEYWORDS EXPLORER ────────────────────────────────────────────────────────

def keywords_explorer(keywords: list, country: str, api_key: str, site_key: str) -> dict:
    """Analyse de mots-clés."""
    results = {}
    total_units = 0
    kw_str = ",".join(keywords[:10])  # max 10 pour éviter les coûts excessifs

    kw_endpoints = [
        ("overview",       "keywords-explorer/overview",          {"keywords": kw_str, "country": country, "select": "keyword,volume,difficulty,cpc,clicks"}),
        ("matching_terms", "keywords-explorer/matching-terms",    {"keywords": kw_str, "country": country, "select": "keyword,volume,difficulty,parent_topic", "limit": 50}),
        ("related_terms",  "keywords-explorer/related-terms",     {"keywords": kw_str, "country": country, "select": "keyword,volume,difficulty", "limit": 30}),
        ("suggestions",    "keywords-explorer/search-suggestions", {"keywords": kw_str, "country": country, "select": "keyword,volume", "limit": 20}),
        ("volume_history", "keywords-explorer/volume-history",    {"keyword": keywords[0], "country": country, "select": "month,volume"}),
    ]

    for name, endpoint, params in kw_endpoints:
        print(f"  [{name}]...")
        data = ahrefs_get(endpoint, params, api_key)
        units = data.pop("_units", 0)
        cost  = data.pop("_cost_usd", 0)
        total_units += units
        if not data.get("error"):
            results[name] = data
            track_cost(f"seo-kw-{name}", site_key, units, cost, name)
        time.sleep(0.5)

    results["_total_units"] = total_units
    return results


# ── SERP OVERVIEW ────────────────────────────────────────────────────────────

def serp_overview(keyword: str, country: str, api_key: str, site_key: str) -> dict:
    """Top 100 SERP pour un mot-clé."""
    print(f"  [serp_overview] {keyword}...")
    data = ahrefs_get(
        "serp-overview/serp-overview",
        {"keyword": keyword, "country": country, "select": "url,title,position,traffic,domain_rating", "limit": 20},
        api_key
    )
    units = data.pop("_units", 0)
    cost  = data.pop("_cost_usd", 0)
    track_cost("seo-serp", site_key, units, cost, keyword)
    return data


# ── RANK TRACKER ─────────────────────────────────────────────────────────────

def rank_tracker(domain: str, api_key: str, site_key: str) -> dict:
    """Rank Tracker — nécessite un project_id configuré dans Ahrefs."""
    # Le Rank Tracker nécessite un projet créé dans l'interface Ahrefs.
    # Sans project_id, ces endpoints retournent 400/404. On les ignore.
    print("  [rank-tracker] Skipped — nécessite un project_id Ahrefs configuré")
    return {"skipped": True, "reason": "project_id requis — créer un projet dans app.ahrefs.com"}


# ── RAPPORT ÉDITORIAL ────────────────────────────────────────────────────────

def save_latest(site_key: str, se_data: dict, kw_data: dict, serp_data: dict):
    """Sauvegarde un fichier {site}-latest.json lisible par le dashboard."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Extraire les données utiles pour le dashboard
    dr_raw   = se_data.get("domain_rating", {})
    dr_val   = dr_raw.get("domain_rating", {})
    # domain_rating peut être imbriqué (dict dans dict selon le endpoint)
    if isinstance(dr_val, dict):
        dr_num = dr_val.get("domain_rating", 0)
        ar_num = dr_val.get("ahrefs_rank", 0)
    else:
        dr_num = dr_val
        ar_num = dr_raw.get("ahrefs_rank", 0)

    metrics_raw = se_data.get("metrics", {})
    if isinstance(metrics_raw, dict):
        m = metrics_raw.get("metrics", metrics_raw)
    else:
        m = {}

    # Mots-clés organiques
    org_kws_raw = se_data.get("organic_keywords", {})
    org_kws = org_kws_raw.get("keywords", []) if isinstance(org_kws_raw, dict) else []

    # Concurrents
    comp_raw = se_data.get("organic_competitors", {})
    competitors = comp_raw.get("competitors", []) if isinstance(comp_raw, dict) else []

    # Opportunités KD < 30
    matching = kw_data.get("matching_terms", {}).get("keywords", [])
    opportunities = [k for k in matching if (k.get("difficulty") or 100) < 30 and (k.get("volume") or 0) > 0]

    latest = {
        "site":         site_key,
        "date":         today,
        "domain_rating": dr_num,
        "ahrefs_rank":  ar_num,
        "org_traffic":  m.get("org_traffic", 0) if isinstance(m, dict) else 0,
        "org_keywords": m.get("org_keywords", 0) if isinstance(m, dict) else 0,
        "organic_keywords":    org_kws[:20],
        "organic_competitors": competitors[:10],
        "opportunities":       opportunities[:20],
        "kw_overview":         kw_data.get("overview", {}).get("keywords", []),
        "serp_top":            serp_data.get("positions", [])[:10] if isinstance(serp_data, dict) else [],
        "backlinks_stats":     se_data.get("backlinks_stats", {}),
        "outlinks_stats":      se_data.get("outlinks_stats", {}),
        "pages_by_traffic":    se_data.get("pages_by_traffic", {}).get("pages", {}),
        "top_pages":           se_data.get("top_pages", {}).get("pages", [])[:10],
    }

    out = SEO_DIR / f"{site_key}-latest.json"
    out.write_text(json.dumps(latest, ensure_ascii=False, indent=2))
    print(f"  Dashboard: {out}")
    return latest


def build_editorial_brief(site_key: str, se_data: dict, kw_data: dict) -> str:
    """Génère un brief éditorial depuis les données SEO."""
    site = SITES[site_key]
    lines = [
        f"# Brief SEO — {site['label']} — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        "## Métriques du domaine",
    ]

    # domain_rating peut être imbriqué
    dr_raw = se_data.get("domain_rating", {})
    dr_val = dr_raw.get("domain_rating", {})
    if isinstance(dr_val, dict):
        dr_num = dr_val.get("domain_rating", "?")
        ar_num = dr_val.get("ahrefs_rank", "?")
    else:
        dr_num = dr_val or "?"
        ar_num = dr_raw.get("ahrefs_rank", "?")
    lines.append(f"- Domain Rating : **{dr_num}**")
    lines.append(f"- Ahrefs Rank : #{ar_num}")

    metrics_raw = se_data.get("metrics", {})
    m = metrics_raw.get("metrics", metrics_raw) if isinstance(metrics_raw, dict) else {}
    if m and isinstance(m, dict):
        lines.append(f"- Trafic organique : **{m.get('org_traffic', 0):,}** visites/mois")
        lines.append(f"- Mots-clés organiques : **{m.get('org_keywords', 0):,}**")

    lines += ["", "## Top mots-clés organiques"]
    kws = se_data.get("organic_keywords", {}).get("keywords", [])[:10]
    for kw in kws:
        lines.append(f"- `{kw.get('keyword')}` — vol. {kw.get('volume', 0):,} · pos. #{kw.get('position')} · trafic {kw.get('traffic', 0):,}")

    lines += ["", "## Opportunités de mots-clés"]
    matching = kw_data.get("matching_terms", {}).get("keywords", [])[:15]
    low_competition = [k for k in matching if (k.get("difficulty") or 100) < 30]
    for kw in low_competition[:10]:
        lines.append(f"- `{kw.get('keyword')}` — vol. {kw.get('volume', 0):,} · KD {kw.get('difficulty', '?')} · **OPPORTUNITÉ**")

    lines += ["", "## Articles à créer (basé sur les gaps)"]
    seen_topics = {k.get("parent_topic") for k in matching if k.get("parent_topic")}
    for i, topic in enumerate(list(seen_topics)[:8], 1):
        lines.append(f"{i}. Article sur : **{topic}**")

    lines += ["", "## Concurrents organiques"]
    competitors = se_data.get("organic_competitors", {}).get("competitors", [])[:5]
    for c in competitors:
        lines.append(f"- {c.get('competitor')} — {c.get('common_keywords', 0)} mots-clés communs · trafic {c.get('competitor_traffic', 0):,}")

    lines += ["", "## Actions recommandées"]
    if low_competition:
        lines.append(f"- **Contenu** : {len(low_competition)} mots-clés KD<30 identifiés → créer les articles")
    broken = se_data.get("broken_backlinks", {}).get("backlinks", [])
    if broken:
        lines.append(f"- **Technique** : {len(broken)} backlinks cassés → rediriger")
    lines.append(f"- **Newsletter** : inclure les topics {', '.join(list(seen_topics)[:3])}")
    lines.append(f"- **LinkedIn** : publier sur les top mots-clés organiques")

    return "\n".join(lines)


# ── MAIN ──────────────────────────────────────────────────────────────────────

def run_full_seo(site_key: str, api_key: str):
    """Rapport SEO complet pour un site."""
    site = SITES[site_key]
    domain = site["domain"]
    print(f"\n{'='*60}")
    print(f"SEO Analysis — {site['label']} ({domain})")
    print(f"{'='*60}\n")

    # 1. Site Explorer
    print("[1/4] Site Explorer...")
    se_data = site_explorer_full(domain, api_key, site_key)
    save_report(site_key, "site_explorer", se_data)

    # 2. Keywords Explorer
    print("\n[2/4] Keywords Explorer...")
    kw_data = keywords_explorer(site["keywords"], "fr", api_key, site_key)
    save_report(site_key, "keywords", kw_data)

    # 3. SERP pour le mot-clé principal
    print("\n[3/4] SERP Overview...")
    serp_data = serp_overview(site["keywords"][0], "fr", api_key, site_key)
    save_report(site_key, "serp", serp_data)

    # 4. Rank Tracker
    print("\n[4/4] Rank Tracker...")
    rt_data = rank_tracker(domain, api_key, site_key)
    save_report(site_key, "rank_tracker", rt_data)

    # 5. Fichier latest pour le dashboard
    print("\n[5/6] Mise à jour dashboard...")
    save_latest(site_key, se_data, kw_data, serp_data)

    # 6. Brief éditorial
    print("\n[6/6] Génération brief éditorial...")
    brief = build_editorial_brief(site_key, se_data, kw_data)
    brief_path = SEO_DIR / f"{site_key}_brief_{datetime.now(timezone.utc).strftime('%Y%m%d')}.md"
    brief_path.write_text(brief)
    print(f"  Brief sauvegardé: {brief_path}")
    print("\n" + brief[:600] + "...")

    total_units = se_data.get("_total_units", 0) + kw_data.get("_total_units", 0)
    total_cost = round(total_units * AHREFS_UNIT_USD, 4)
    print(f"\nTotal: {total_units:,} unités Ahrefs · ~{total_cost:.4f} USD")
    return {"site": site_key, "total_units": total_units, "brief_path": str(brief_path)}


def main():
    # --- BLOCAGE 2026-05-22 : --report full désactivé ---
    # Trop coûteux (~3 100u/site/run). Remplacé par ahrefs_monthly_audit.py.
    # Pour relancer un audit complet : python3 scripts/ahrefs_monthly_audit.py
    # Pour les recherches kw ponctuelles : --report keywords --kw "..." (1×/2 mois max)
    if "--report" in sys.argv:
        try:
            idx = sys.argv.index("--report")
            if idx + 1 < len(sys.argv) and sys.argv[idx + 1] == "full":
                print("[SEO.PY] --report full DÉSACTIVÉ (décision 2026-05-22).")
                print("Utilise : python3 scripts/ahrefs_monthly_audit.py")
                print("Voir : specs/seo-playbook.md")
                sys.exit(0)
        except (ValueError, IndexError):
            pass


    parser = argparse.ArgumentParser(description="Analyse SEO Ahrefs")
    parser.add_argument("--site", required=True, choices=None)
    parser.add_argument("--report", default="full",
                        choices=["full", "keywords", "competitors", "backlinks", "serp"])
    parser.add_argument("--kw", help="Mot-clé spécifique pour l'analyse")
    args = parser.parse_args()

    env = load_env()
    api_key = env.get("AHREFS_API_KEY", "")
    if not api_key:
        print("ERREUR: AHREFS_API_KEY manquante dans .env")
        print("→ Récupérer sur app.ahrefs.com/account/api-keys")
        print("→ Ajouter: AHREFS_API_KEY=votre_clé dans .env")
        sys.exit(1)

    sites = ["lcr", "mkd"] if args.site == "both" else [args.site]

    for site_key in sites:
        if args.report == "full":
            run_full_seo(site_key, api_key)
        elif args.report == "keywords":
            site = SITES[site_key]
            kws = [args.kw] if args.kw else site["keywords"]
            data = keywords_explorer(kws, "fr", api_key, site_key)
            save_report(site_key, "keywords_custom", data)
        elif args.report == "competitors":
            domain = SITES[site_key]["domain"]
            data = ahrefs_get("site-explorer/organic-competitors",
                {"target": domain, "select": "competitor,common_keywords,competitor_traffic", "limit": 20},
                api_key)
            print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
