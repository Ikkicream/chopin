#!/usr/bin/env python3
"""
seo_agent.py — Agent SEO autonome : veille concurrents, annuaires, backlinks.

Tâches :
  1. Scraping RSS concurrents — nouveaux articles → mettre à jour veille
  2. Soumission annuaires automatique (rotation quotidienne)
  3. Mise à jour du brief éditorial quotidien
  4. Rapport Telegram hebdo des progressions

Usage : python3 scripts/seo_agent.py --task all
        python3 scripts/seo_agent.py --task rss
        python3 scripts/seo_agent.py --task directories
        python3 scripts/seo_agent.py --task brief
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"
SEO_DIR  = BASE_DIR / "memory" / "seo"
SEO_DIR.mkdir(parents=True, exist_ok=True)

# ── Sources RSS concurrents ───────────────────────────────────────────────────

# ── RSS Sources (centrale si dispo, sinon fallback) ──────────────────────────
try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.sites_config import load_all_sites as _las
    _all_sites = _las()
    RSS_SOURCES = {
        code: data.get("seo_agent", {}).get("rss_sources", [])
        for code, data in _all_sites.items()
        if data.get("_meta", {}).get("status") == "active"
    }
except Exception as _e:
    RSS_SOURCES = {
        "lcr": [
            {"name": "Spot-Hit Blog",      "url": "https://www.spot-hit.fr/blog/feed/"},
            {"name": "SMS Mode Blog",      "url": "https://www.smsmode.com/blog/feed/"},
            {"name": "SMS Partner Blog",   "url": "https://www.smspartner.fr/blog/feed/"},
            {"name": "Sarbacane Blog",     "url": "https://www.sarbacane.com/blog/feed/"},
            {"name": "Digitaleo Blog",     "url": "https://www.digitaleo.com/blog/feed/"},
            {"name": "Blog du Modérateur", "url": "https://www.blogdumoderateur.com/feed/"},
            {"name": "Journal du Net",     "url": "https://www.journaldunet.com/rss/rss_jdn.xml"},
            {"name": "Codeur Blog",        "url": "https://www.codeur.com/blog/feed/"},
        ],
        "mkd": [
            {"name": "Cartegie Blog",    "url": "https://www.cartegie.com/blog/feed/"},
            {"name": "ECommerce Mag",    "url": "https://www.ecommercemag.fr/rss/"},
            {"name": "Relation Client",  "url": "https://www.relationclient-mag.fr/rss/"},
            {"name": "Blog du Modérateur","url": "https://www.blogdumoderateur.com/feed/"},
        ],
    }

# ── Annuaires à soumettre ─────────────────────────────────────────────────────

DIRECTORIES = [
    # Gratuits FR — soumettre leclientroi.com
    {"name": "Annuaire-Free",    "url": "https://www.annuaire-free.fr",   "submit_url": "https://www.annuaire-free.fr/add.php",    "free": True,  "done": False},
    {"name": "2Annuaire",        "url": "https://www.2annuaire.com",      "submit_url": "https://www.2annuaire.com/ajout/",         "free": True,  "done": False},
    {"name": "Hotfrog FR",       "url": "https://www.hotfrog.fr",         "submit_url": "https://www.hotfrog.fr/ajouter/",         "free": True,  "done": False},
    {"name": "Cylex FR",         "url": "https://www.cylex.fr",           "submit_url": "https://www.cylex.fr/company-register/",  "free": True,  "done": False},
    {"name": "Finderlocal",      "url": "https://www.finderlocal.fr",     "submit_url": "https://www.finderlocal.fr/add/",         "free": True,  "done": False},
    {"name": "Kompass FR",       "url": "https://fr.kompass.com",         "submit_url": "https://fr.kompass.com/inscription/",     "free": True,  "done": False},
    {"name": "Europages FR",     "url": "https://www.europages.fr",       "submit_url": "https://www.europages.fr/entreprise/",    "free": True,  "done": False},
    {"name": "Trustpilot",       "url": "https://fr.trustpilot.com",      "submit_url": "https://www.trustpilot.com/signup",       "free": True,  "done": False},
    {"name": "G2",               "url": "https://www.g2.com",             "submit_url": "https://sell.g2.com/free-listing/",       "free": True,  "done": False},
    {"name": "Capterra FR",      "url": "https://www.capterra.fr",        "submit_url": "https://www.capterra.fr/vendors/signup",  "free": True,  "done": False},
    {"name": "GetApp FR",        "url": "https://www.getapp.fr",          "submit_url": "https://www.getapp.fr/getting-listed/",   "free": True,  "done": False},
    {"name": "Appvizer FR",      "url": "https://www.appvizer.fr",        "submit_url": "https://www.appvizer.fr/inscription/",    "free": True,  "done": False},
    {"name": "Pages Jaunes",     "url": "https://www.pagesjaunes.fr",     "submit_url": "https://www.pagesjaunes.fr/inscrire/",    "free": True,  "done": False},
    {"name": "Made-in-France.fr","url": "https://made-in-france.fr",      "submit_url": "https://made-in-france.fr/inscription/",  "free": True,  "done": False},
    {"name": "Mafranchise.fr",   "url": "https://www.mafranchise.fr",     "submit_url": None,                                      "free": True,  "done": False},
    # Payants DR > 40
    {"name": "Yelp FR",          "url": "https://www.yelp.fr",            "submit_url": "https://biz.yelp.fr/signup_business/",    "free": False, "done": False},
    {"name": "Manageo",          "url": "https://www.manageo.fr",         "submit_url": "https://www.manageo.fr/inscription/",     "free": False, "done": False},
]

DIRS_LOG = SEO_DIR / "directories-log.json"


def load_env() -> dict:
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


# ── RSS Scraping ──────────────────────────────────────────────────────────────

def parse_rss(url: str, timeout: int = 10) -> list[dict]:
    """Parse un flux RSS et retourne les articles récents."""
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Genesis-SEO-Agent/1.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        items = []
        # RSS 2.0
        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            link  = item.findtext("link",  "")
            desc  = item.findtext("description", "")
            pub   = item.findtext("pubDate", "")
            if title and link:
                items.append({"title": title, "url": link, "description": desc[:200], "date": pub})

        # Atom
        if not items:
            for entry in root.findall("atom:entry", ns):
                title = entry.findtext("atom:title", "", ns)
                link_el = entry.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
                items.append({"title": title, "url": link, "description": "", "date": ""})

        return items[:10]
    except Exception as e:
        return [{"error": str(e)}]


def scrape_rss(site: str) -> dict:
    """Scrape tous les flux RSS d'un site et sauve la veille."""
    sources = RSS_SOURCES.get(site, [])
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    all_articles = []

    print(f"  Scraping {len(sources)} sources RSS pour {site.upper()}...")
    for source in sources:
        items = parse_rss(source["url"])
        new_items = [i for i in items if not i.get("error")]
        print(f"    [{source['name']}] {len(new_items)} articles")
        for item in new_items:
            all_articles.append({**item, "source": source["name"]})

    # Sauvegarder la veille
    veille_file = SEO_DIR / f"{site}-veille.json"
    existing = []
    if veille_file.exists():
        try:
            existing = json.loads(veille_file.read_text())
        except Exception:
            pass

    # Dédupliquer par URL
    existing_urls = {a["url"] for a in existing}
    new = [a for a in all_articles if a.get("url") and a["url"] not in existing_urls]
    combined = (new + existing)[:200]  # garder les 200 plus récents
    veille_file.write_text(json.dumps(combined, ensure_ascii=False, indent=2))
    print(f"    {len(new)} nouveaux articles sauvés dans veille ({len(combined)} total)")
    return {"new": len(new), "total": len(combined)}


# ── Annuaires ─────────────────────────────────────────────────────────────────

def get_dirs_log() -> dict:
    """Charge l'état des soumissions d'annuaires."""
    if DIRS_LOG.exists():
        try:
            return json.loads(DIRS_LOG.read_text())
        except Exception:
            pass
    return {"submitted": {}, "pending": [d["name"] for d in DIRECTORIES if d.get("submit_url")]}


def save_dirs_log(log: dict):
    DIRS_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2))


def get_next_directories(n: int = 3) -> list[dict]:
    """Retourne les N prochains annuaires à soumettre."""
    log = get_dirs_log()
    submitted = set(log.get("submitted", {}).keys())
    pending = [d for d in DIRECTORIES if d["name"] not in submitted and d.get("submit_url")]
    return pending[:n]


def mark_directory_submitted(name: str, note: str = ""):
    log = get_dirs_log()
    log.setdefault("submitted", {})[name] = {
        "date": datetime.now(timezone.utc).isoformat(),
        "note": note,
    }
    save_dirs_log(log)


def report_directories() -> str:
    """Rapport Telegram sur l'état des soumissions."""
    log = get_dirs_log()
    submitted = log.get("submitted", {})
    pending = [d for d in DIRECTORIES if d["name"] not in submitted]
    lines = [
        f"*Annuaires LCR*",
        f"  Soumis: {len(submitted)}/{len(DIRECTORIES)}",
        f"  Restants: {len(pending)}",
        "",
        "*Prochains annuaires a soumettre:*",
    ]
    for d in pending[:5]:
        lines.append(f"  - {d['name']}: {d['submit_url']}")
    return "\n".join(lines)


def directories_task() -> dict:
    """
    Affiche les 3 prochains annuaires à soumettre.
    La soumission est manuelle (formulaires web) — on génère la liste + instructions.
    """
    pending = get_next_directories(5)
    log = get_dirs_log()
    submitted_count = len(log.get("submitted", {}))

    print(f"\n  Annuaires soumis: {submitted_count}/{len(DIRECTORIES)}")
    print(f"  Prochains a soumettre (manuellement ou via navigateur):")
    for d in pending:
        print(f"    - {d['name']}: {d['submit_url']}")

    # Sauvegarder les instructions dans un fichier
    instructions_file = SEO_DIR / "annuaires-todo.md"
    lines = [
        "# Annuaires à soumettre — leclientroi.com",
        f"Mise à jour: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        f"Soumis: {submitted_count}/{len(DIRECTORIES)}",
        "",
        "## A faire maintenant",
        "",
    ]
    for d in pending:
        lines.append(f"### {d['name']} {'(GRATUIT)' if d['free'] else '(PAYANT)'}")
        lines.append(f"- URL: {d['submit_url']}")
        lines.append(f"- Fiche: Nom = LeClientROI, URL = https://leclientroi.com")
        lines.append(f"- Catégorie: Marketing / SMS Marketing / Communication")
        lines.append(f"- Description: Solution SMS marketing et géolocalisation pour PME")
        lines.append("")

    lines += [
        "## Soumis",
        "",
    ]
    for name, info in log.get("submitted", {}).items():
        lines.append(f"- {name} — {info.get('date','')[:10]}")

    instructions_file.write_text("\n".join(lines))
    print(f"  Instructions sauvées: {instructions_file}")
    return {"pending": len(pending), "submitted": submitted_count}


# ── Brief éditorial quotidien ─────────────────────────────────────────────────

def update_daily_brief(site: str) -> str:
    """Met à jour le brief éditorial avec la veille du jour."""
    veille_file = SEO_DIR / f"{site}-veille.json"
    latest_file = SEO_DIR / f"{site}-latest.json"

    veille = []
    if veille_file.exists():
        veille = json.loads(veille_file.read_text())[:20]

    seo_data = {}
    if latest_file.exists():
        seo_data = json.loads(latest_file.read_text())

    # Identifier les sujets couverts par les concurrents
    topics_competitors = []
    for art in veille[:10]:
        title = art.get("title", "")
        if any(kw in title.lower() for kw in ["sms", "marketing", "campagne", "rcs", "rgpd", "b2b", "data"]):
            topics_competitors.append(f"- [{art['source']}] {title}")

    opps = seo_data.get("opportunities", [])
    kws  = seo_data.get("organic_keywords", [])

    brief = [
        f"# Brief éditorial — {site.upper()} — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        "## Métriques SEO actuelles",
        f"- DR: {seo_data.get('domain_rating', '?')} | Trafic: {seo_data.get('org_traffic', '?')}/mois | Keywords: {seo_data.get('org_keywords', '?')}",
        "",
        "## Opportunités prioritaires (KD < 30)",
    ]
    for opp in opps[:5]:
        brief.append(f"- `{opp.get('keyword')}` — vol. {opp.get('volume',0)} · KD {opp.get('difficulty','?')}")

    brief += ["", "## Top keywords actuels"]
    for kw in kws[:5]:
        brief.append(f"- `{kw.get('keyword')}` — pos. #{kw.get('best_position','?')} · vol. {kw.get('volume',0)}")

    brief += ["", "## Concurrents actifs (veille RSS)"]
    brief += topics_competitors[:8] if topics_competitors else ["- Aucun contenu récent détecté"]

    brief += [
        "",
        "## Sujets d'articles recommandés (aujourd'hui)",
        "Choisir 1 de ces sujets :",
    ]
    # Combiner opportunités + lacunes vs concurrents
    all_topics = [opp.get("keyword", "") for opp in opps[:3]]
    for art in veille[:5]:
        kw = art.get("title", "").lower()
        if kw and kw not in all_topics:
            all_topics.append(kw[:60])
    for t in all_topics[:5]:
        brief.append(f"1. {t}")

    brief_text = "\n".join(brief)
    brief_path = SEO_DIR / f"{site}-brief-daily.md"
    brief_path.write_text(brief_text)
    print(f"  Brief mis à jour: {brief_path}")
    return brief_text


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=["all", "rss", "directories", "brief"], default="all")
    parser.add_argument("--site", choices=["lcr", "mkd", "both"], default="both")
    args = parser.parse_args()

    env = load_env()
    now = datetime.now(timezone.utc)
    print(f"[seo_agent] Démarrage {now.isoformat()} — task: {args.task}")

    sites = ["lcr", "mkd"] if args.site == "both" else [args.site]
    results = {}

    for site in sites:
        print(f"\n--- {site.upper()} ---")
        site_results = {}

        if args.task in ("all", "rss"):
            print("[1] Scraping RSS concurrents...")
            site_results["rss"] = scrape_rss(site)

        if args.task in ("all", "brief"):
            print("[2] Mise à jour brief éditorial...")
            update_daily_brief(site)
            site_results["brief"] = "updated"

        if args.task in ("all", "directories") and site == "lcr":
            print("[3] Rapport annuaires...")
            site_results["directories"] = directories_task()

        results[site] = site_results

    # Telegram notification hebdo (le lundi uniquement)
    if now.weekday() == 0 and args.task in ("all",):
        try:
            tg_token  = env.get("TELEGRAM_BOT_TOKEN", "")
            tg_chat   = env.get("TELEGRAM_CHAT_ID", "")
            lcr_data  = json.loads((SEO_DIR / "lcr-latest.json").read_text()) if (SEO_DIR / "lcr-latest.json").exists() else {}
            mkd_data  = json.loads((SEO_DIR / "mkd-latest.json").read_text()) if (SEO_DIR / "mkd-latest.json").exists() else {}
            msg = (
                f"*SEO Hebdo — Genesis*\n\n"
                f"*LCR* — DR {lcr_data.get('domain_rating','?')} | "
                f"{lcr_data.get('org_traffic','?')} visites | {lcr_data.get('org_keywords','?')} keywords\n"
                f"*MKD* — DR {mkd_data.get('domain_rating','?')} | "
                f"{mkd_data.get('org_traffic','?')} visites | {mkd_data.get('org_keywords','?')} keywords\n\n"
                f"{report_directories()}"
            )
            if tg_token and tg_chat:
                requests.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat, "text": msg, "parse_mode": "Markdown"},
                    timeout=5,
                )
                print("  Telegram hebdo envoyé")
        except Exception as e:
            print(f"  ⚠ Telegram: {e}")

    print(f"\n[seo_agent] Terminé {datetime.now(timezone.utc).isoformat()}")
    return results


if __name__ == "__main__":
    main()
