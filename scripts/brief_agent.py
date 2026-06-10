#!/usr/bin/env python3
"""
brief_agent.py — Propose des articles basés sur les données Ahrefs + content gaps.
Crée des propositions dans la queue éditoriale.

Cron: lundi + jeudi 8h UTC
Usage: python3 scripts/brief_agent.py [--site lcr|mkd|both]
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent.parent
QUEUE_FILE = BASE_DIR / "memory" / "editorial" / "articles-queue.json"
SEO_DIR = BASE_DIR / "memory" / "seo"

# Load env
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip("'\""))

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

SITE_CONTEXT = {
    "lcr": {
        "label": "LeClientROI",
        "domain": "leclientroi.com",
        "niche": "SMS marketing, RCS, communication locale pour TPE/PME",
        "target_keywords": ["sms marketing", "campagne sms", "sms geolocalise", "rcs messagerie", "sms professionnel"],
    },
    "mkd": {
        "label": "MKDgroupe",
        "domain": "mkdgroupe.com",
        "niche": "Prospection B2B, data marketing, RGPD, RCS entreprise",
        "target_keywords": ["prospection commerciale b2b", "rgpd marketing", "base de donnees b2b", "sms b2b", "rcs entreprise"],
    },
}


def load_queue():
    if QUEUE_FILE.exists():
        return json.loads(QUEUE_FILE.read_text())
    return []


def save_queue(queue):
    QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False))


def load_ahrefs_data(site):
    """Load cached Ahrefs data for a site."""
    f = SEO_DIR / f"{site}-ahrefs-latest.json"
    if f.exists():
        return json.loads(f.read_text())
    return {}


def get_published_titles(queue, site):
    """Get titles already proposed or published for this site."""
    return [a["proposal"]["title"].lower() for a in queue if a["site"] == site and a["status"] != "rejected"]


def generate_proposal(site, ahrefs_data, existing_titles):
    """Use Claude Haiku to generate an article proposal."""
    ctx = SITE_CONTEXT[site]
    keywords = ahrefs_data.get("top_keywords", [])
    competitors = ahrefs_data.get("competitors", [])
    dr = ahrefs_data.get("domain_rating", 0)
    traffic = ahrefs_data.get("org_traffic", 0)

    prompt = f"""Tu es un éditorialiste SEO expert. Propose UN article pour le site {ctx['label']} ({ctx['domain']}).

NICHE : {ctx['niche']}
MOTS-CLÉS CIBLES : {', '.join(ctx['target_keywords'])}
DOMAIN RATING ACTUEL : {dr}
TRAFIC ORGANIQUE : {traffic}/mois
TOP KEYWORDS ACTUELS : {json.dumps(keywords, ensure_ascii=False)}
CONCURRENTS : {json.dumps([c['domain'] for c in competitors[:3]], ensure_ascii=False)}

ARTICLES DÉJÀ PROPOSÉS/PUBLIÉS (NE PAS RÉPÉTER) :
{chr(10).join('- ' + t for t in existing_titles[:10])}

STRATÉGIE : Avec un DR de {dr}, on doit cibler des keywords à KD FAIBLE (<15) avec du volume (>50/mois). Pas de keywords impossibles.

Réponds UNIQUEMENT en JSON valide (pas de markdown, pas de commentaires) :
{{
  "title": "Titre H1 optimisé SEO (max 60 chars)",
  "summary": "Résumé en 2 phrases de ce que l'article couvre et pourquoi le lecteur devrait le lire",
  "keyword": "mot-clé principal ciblé",
  "volume": estimation du volume mensuel,
  "kd": estimation de la difficulté (0-100),
  "rationale": "Pourquoi cet article maintenant — justification SEO en 1 phrase"
}}"""

    from llm_call import call_llm_json
    try:
        from modules_backend import enrich_prompt
        prompt = enrich_prompt(prompt, site, "articles")
    except Exception:
        pass
    return call_llm_json(prompt, max_tokens=500, temperature=0.7, module="briefing", action="article-proposal", site=site)


def notify_telegram(site, proposal):
    """Send proposal notification to Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    label = SITE_CONTEXT[site]["label"]
    msg = (
        f"\U0001f4dd *Nouvel article proposé ({label})*\n\n"
        f"*Titre :* {proposal['title']}\n"
        f"*Keyword :* {proposal['keyword']} (vol: {proposal.get('volume', '?')}, KD: {proposal.get('kd', '?')})\n"
        f"*Résumé :* {proposal['summary']}\n\n"
        f"_Valider sur le dashboard #articles_"
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        print(f"  Telegram error: {e}")


def process_site(site):
    """Generate and save a proposal for a site."""
    print(f"[brief] {site.upper()} — generating proposal...")

    ahrefs = load_ahrefs_data(site)
    if not ahrefs:
        print(f"  No Ahrefs data for {site}, skipping")
        return

    queue = load_queue()
    existing = get_published_titles(queue, site)

    try:
        proposal = generate_proposal(site, ahrefs, existing)
    except Exception as e:
        print(f"  ERROR generating proposal: {e}")
        return

    print(f"  Title: {proposal['title']}")
    print(f"  Keyword: {proposal['keyword']} (vol: {proposal.get('volume')}, KD: {proposal.get('kd')})")

    # Create queue entry
    now = datetime.now(timezone.utc)
    count = len([a for a in queue if a["site"] == site]) + 1
    article_id = f"art_{now.strftime('%Y%m%d')}_{site}_{count:03d}"

    entry = {
        "id": article_id,
        "site": site,
        "status": "proposed",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "proposal": {
            "title": proposal["title"],
            "summary": proposal["summary"],
            "keyword": proposal["keyword"],
            "volume": proposal.get("volume", 0),
            "kd": proposal.get("kd", 0),
            "rationale": proposal.get("rationale", ""),
        },
        "seo_check": None,
        "article": None,
        "qc_report": None,
        "human_notes": None,
    }

    queue.append(entry)
    save_queue(queue)
    print(f"  Saved: {article_id}")

    # Telegram notification
    notify_telegram(site, proposal)
    print(f"  Telegram notified")


# ── Mode agentique (boucle agent_core) ──────────────────────────────────────
# Au lieu de `process_site()` qui propose via un appel DeepSeek brut, on délègue
# à agent_core : observe GSC/GA4/Ahrefs → recall actions passées → decide via
# playbook skills/content-writer.md (format JSON write_article+target=mot-clé)
# → act = crée une entry status=proposed dans la queue + notif Telegram.

def _agentic_writer(item: dict, snapshot: dict, *, site: str, dry_run: bool):
    if item.get("action_type") not in ("write_article", "propose_article"):
        print(f"  [agentic] action_type non géré: {item.get('action_type')!r} — skip")
        return
    tags = item.get("tags") or {}
    keyword = tags.get("keyword") or item.get("target")
    title = tags.get("draft_title") or item.get("target") or keyword
    summary = item.get("why") or ""
    if not keyword or not title:
        raise ValueError("plan sans keyword/title")
    if dry_run:
        print(f"  [agentic] DRY-RUN proposal title={title!r} keyword={keyword!r}")
        item["dry_run"] = True
        return
    queue = load_queue()
    now = datetime.now(timezone.utc)
    count = len([a for a in queue if a["site"] == site]) + 1
    article_id = f"art_{now.strftime('%Y%m%d')}_{site}_{count:03d}"
    entry = {
        "id": article_id, "site": site, "status": "proposed",
        "created_at": now.isoformat(), "updated_at": now.isoformat(),
        "proposal": {
            "title": title, "summary": summary, "keyword": keyword,
            "volume": tags.get("volume", 0), "kd": tags.get("kd", 0),
            "rationale": item.get("why", ""),
            "secondary_keywords": tags.get("secondary_keywords", []),
            "intent": tags.get("intent", ""),
            "source": "agentic",
        },
        "seo_check": None, "article": None, "qc_report": None, "human_notes": None,
    }
    queue.append(entry)
    save_queue(queue)
    try:
        notify_telegram(site, entry["proposal"])
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ telegram: {e}")
    item["article_id"] = article_id


def run_agentic(site: str, dry_run: bool = True) -> dict:
    from functools import partial
    print(f"[brief_agent agentic] Site: {site.upper()} — "
          f"{'DRY-RUN' if dry_run else 'LIVE'}")
    sys.path.insert(0, str(Path(__file__).parent))
    from agent_core import run_cycle
    writer = partial(_agentic_writer, site=site, dry_run=dry_run)
    result = run_cycle(agent="content-writer", site=site,
                       sources=("gsc", "ga4", "ahrefs"), writer_fn=writer)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["lcr", "mkd", "both"], default="both")
    parser.add_argument("--agentic", action="store_true",
                        help="Passe par la boucle agent_core (observe/recall/decide/act)")
    parser.add_argument("--live", action="store_true",
                        help="En mode agentique : exécute pour de vrai (sinon dry-run)")
    args = parser.parse_args()

    print(f"[brief_agent] {datetime.now(timezone.utc).isoformat()}")

    if args.agentic:
        sites = ["lcr", "mkd"] if args.site == "both" else [args.site]
        for s in sites:
            run_agentic(s, dry_run=not args.live)
        return

    # Respect modules toggle : skip si articles désactivé pour ce site
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from modules_backend import is_enabled
    except Exception:
        is_enabled = lambda *_: True  # fallback

    sites = ["lcr", "mkd"] if args.site == "both" else [args.site]
    for site in sites:
        if not is_enabled(site, "articles"):
            print(f"[brief_agent] {site}: module 'articles' désactivé → skip")
            continue
        process_site(site)

    print("[brief_agent] Done!")


if __name__ == "__main__":
    main()
