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


def main():
    print(f"[linkedin_agent] {datetime.now(timezone.utc).isoformat()}")

    if not QUEUE_FILE.exists():
        print("  No queue file")
        return

    queue = json.loads(QUEUE_FILE.read_text())
    now = datetime.now(timezone.utc)
    three_days_ago = now - timedelta(days=3)

    for art in queue:
        if art["status"] != "published":
            continue
        if art.get("linkedin_post"):
            continue  # Already generated

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
