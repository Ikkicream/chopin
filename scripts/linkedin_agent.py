#!/usr/bin/env python3
"""
linkedin_agent.py — Génère un post LinkedIn J+3 après publication d'un article.
Standards Paperclip LinkedIn Specialist intégrés.

Usage: python3 scripts/linkedin_agent.py
Cron: tous les jours 10h UTC — vérifie s'il y a des articles publiés il y a 3 jours
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent.parent
QUEUE_FILE = BASE_DIR / "memory" / "editorial" / "articles-queue.json"
LINKEDIN_DIR = BASE_DIR / "memory" / "editorial"

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

SITE_LINKEDIN = {
    "lcr": {"page": "LeClientROI", "hashtags": ["#SMSMarketing", "#MarketingLocal", "#TPE"]},
    "mkd": {"page": "MKDgroupe", "hashtags": ["#DataMarketing", "#ProspectionB2B", "#RGPD"]},
}


def call_haiku(prompt):
    from llm_call import call_llm
    return call_llm(prompt, max_tokens=800, module="linkedin", action="post-generation")


def generate_linkedin_post(title, keyword, article_md, site, url):
    """Generate LinkedIn post following Paperclip LinkedIn Specialist standards."""
    cfg = SITE_LINKEDIN[site]
    hashtags = " ".join(cfg["hashtags"])

    prompt = f"""Tu es un LinkedIn Specialist. Écris un post LinkedIn en français pour promouvoir cet article.

ARTICLE : {title}
URL : {url}
KEYWORD : {keyword}
PAGE : {cfg['page']}

EXTRAIT DE L'ARTICLE (pour contexte) :
{article_md[:800]}

RÈGLES STRICTES DU POST :
1. ACCROCHE : 1 phrase qui grabhe l'attention (question forte OU observation audacieuse). Pas de "Saviez-vous que..."
2. DÉVELOPPEMENT : 2-3 courts paragraphes qui développent l'insight clé de l'article
3. URL : l'URL complète de l'article sur une ligne seule
4. QUESTION FINALE : une question ouverte pour générer des commentaires
5. HASHTAGS : exactement 3 hashtags de niche (pas de #marketing générique)

CONTRAINTES :
- Maximum 2-3 emojis par post, JAMAIS en début de ligne
- Ton professionnel et direct, JAMAIS corporate ou générique
- Paragraphes courts (2-3 phrases max)
- Ne PAS résumer l'article — donner envie de cliquer

Écris UNIQUEMENT le post LinkedIn, rien d'autre."""

    try:
        from modules_backend import enrich_prompt
        prompt = enrich_prompt(prompt, site, "linkedin")
    except Exception:
        pass
    return call_haiku(prompt)


def notify_telegram(site, title, post_text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    msg = f"\U0001f4e2 *Post LinkedIn généré ({SITE_LINKEDIN[site]['page']})*\n\n{post_text[:300]}...\n\n_À publier sur LinkedIn_"
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                     json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass


# ── Mode agentique (boucle agent_core) ──────────────────────────────────────
# observe GSC/GA4/Ahrefs + queue éditoriale → recall posts précédents → decide via
# playbook skills/linkedin-specialist.md (format JSON linkedin_post) → act = écrit
# le post dans queue[article].linkedin_post.

def _agentic_writer(item: dict, snapshot: dict, *, site: str, dry_run: bool):
    if item.get("action_type") != "linkedin_post":
        print(f"  [agentic] action_type non géré: {item.get('action_type')!r} — skip")
        return
    target_url = item.get("target")
    tags = item.get("tags") or {}
    hook = tags.get("hook") or ""
    body = tags.get("body") or ""
    cta = tags.get("cta") or ""
    if not target_url:
        raise ValueError("plan sans target (URL article)")
    post_text = "\n\n".join(t for t in (hook, body, cta) if t).strip()
    if not post_text:
        raise ValueError("plan sans hook/body/cta")
    if dry_run:
        print(f"  [agentic] DRY-RUN linkedin_post target={target_url!r} chars={len(post_text)}")
        item["dry_run"] = True
        return
    if not QUEUE_FILE.exists():
        raise FileNotFoundError("queue éditoriale introuvable")
    queue = json.loads(QUEUE_FILE.read_text())
    art = next((a for a in queue if a.get("published_url") == target_url
                or a.get("proposal", {}).get("title", "").lower() in target_url.lower()), None)
    if not art:
        raise ValueError(f"article introuvable pour target {target_url!r}")
    art["linkedin_post"] = {
        "text": post_text, "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "draft", "source": "agentic",
        "scheduled_at": tags.get("scheduled_at"),
        "tags": tags.get("tags_linkedin", []),
    }
    QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False))
    try:
        notify_telegram(art["site"], art["proposal"]["title"], post_text)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ telegram: {e}")
    item["article_id"] = art.get("id")


def run_agentic(site: str, dry_run: bool = True) -> dict:
    from functools import partial
    print(f"[linkedin_agent agentic] Site: {site.upper()} — "
          f"{'DRY-RUN' if dry_run else 'LIVE'}")
    sys.path.insert(0, str(Path(__file__).parent))
    from agent_core import run_cycle
    writer = partial(_agentic_writer, site=site, dry_run=dry_run)
    result = run_cycle(agent="linkedin-specialist", site=site,
                       sources=("gsc", "ga4"), writer_fn=writer)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return result


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", choices=["lcr", "mkd", "both"], default="both")
    ap.add_argument("--agentic", action="store_true")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    if args.agentic:
        sites = ["lcr", "mkd"] if args.site == "both" else [args.site]
        for s in sites:
            run_agentic(s, dry_run=not args.live)
        return

    print(f"[linkedin_agent] {datetime.now(timezone.utc).isoformat()}")

    if not QUEUE_FILE.exists():
        print("  No queue file")
        return

    queue = json.loads(QUEUE_FILE.read_text())
    now = datetime.now(timezone.utc)
    three_days_ago = now - timedelta(days=3)

    # Module toggle check
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from modules_backend import is_enabled
    except Exception:
        is_enabled = lambda *_: True

    for art in queue:
        if art["status"] != "published":
            continue
        if art.get("linkedin_post"):
            continue  # Already generated

        # Skip si module linkedin désactivé pour ce site
        if not is_enabled(art["site"], "linkedin"):
            continue

        published_at = art.get("published_at", "")
        if not published_at:
            continue

        pub_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if pub_date > three_days_ago:
            continue  # Not yet 3 days

        print(f"  Generating LinkedIn for: {art['proposal']['title'][:50]}...")

        try:
            article_md = art.get("article", {}).get("markdown", "")
            url = art.get("published_url", "")
            post = generate_linkedin_post(
                art["proposal"]["title"],
                art["proposal"]["keyword"],
                article_md, art["site"], url
            )
            art["linkedin_post"] = {
                "text": post,
                "generated_at": now.isoformat(),
                "status": "draft",  # draft → posted
            }
            print(f"    Generated ({len(post)} chars)")
            notify_telegram(art["site"], art["proposal"]["title"], post)
        except Exception as e:
            print(f"    ERROR: {e}")

    QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False))
    print("[linkedin_agent] Done!")


if __name__ == "__main__":
    main()
