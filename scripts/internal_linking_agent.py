#!/usr/bin/env python3
"""
internal_linking_agent.py — Ajoute des liens internes dans les articles.
Standards Paperclip Internal Linking Agent intégrés.

Fonctionne en 2 modes :
1. PRE-PUBLISH : ajoute des liens dans l'article avant publication
2. RETROACTIVE : met à jour les anciens articles pour linker vers le nouveau

Usage: python3 scripts/internal_linking_agent.py --id art_xxx [--mode pre|retro]
"""

import json
import os
import re
import sys
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent.parent
QUEUE_FILE = BASE_DIR / "memory" / "editorial" / "articles-queue.json"

env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip("'\""))

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
EMDASH_URL = os.environ.get("EMDASH_API_URL", "http://localhost:4321/_emdash/api")
EMDASH_TOKEN = os.environ.get("EMDASH_API_TOKEN", "")
WP_URL = os.environ.get("WP_SITE_URL", "")
WP_USER = os.environ.get("WP_USERNAME", "")
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")


def call_haiku(prompt):
    from llm_call import call_llm
    return call_llm(prompt, max_tokens=1500, module="internal-linking", action="link-suggestions")


def get_existing_articles(site):
    """Fetch list of existing published articles."""
    articles = []
    if site == "lcr":
        try:
            r = requests.get(f"{EMDASH_URL}/content/posts?limit=50",
                           headers={"Authorization": f"Bearer {EMDASH_TOKEN}"}, timeout=10)
            if r.status_code == 200:
                for p in r.json().get("data", {}).get("items", []):
                    if p.get("status") == "published":
                        articles.append({
                            "title": p.get("data", {}).get("title", ""),
                            "slug": p.get("slug", ""),
                            "url": f"https://blog.leclientroi.com/posts/{p['slug']}"
                        })
        except:
            pass
    elif site == "mkd":
        try:
            r = requests.get(f"{WP_URL}/wp-json/wp/v2/posts?per_page=50&status=publish",
                           auth=(WP_USER, WP_PASS), timeout=10)
            if r.status_code == 200:
                for p in r.json():
                    articles.append({
                        "title": p.get("title", {}).get("rendered", ""),
                        "slug": p.get("slug", ""),
                        "url": p.get("link", "")
                    })
        except:
            pass
    return articles


def suggest_internal_links(article_md, keyword, existing_articles):
    """Use Haiku to suggest natural internal link placements."""
    if not existing_articles:
        return []

    articles_list = "\n".join([f"- [{a['title']}]({a['url']})" for a in existing_articles[:20]])

    prompt = f"""Tu es un Internal Linking Agent expert. Analyse cet article et suggère des liens internes naturels.

ARTICLE EN COURS :
{article_md[:2000]}

ARTICLES EXISTANTS SUR LE SITE :
{articles_list}

Identifie 3-5 endroits dans l'article où un lien interne vers un article existant serait NATUREL (pas forcé).
Pour chaque lien :
- Cite la phrase exacte où insérer le lien
- Indique l'article cible
- Propose le texte d'ancre

Réponds en JSON :
[
  {{
    "sentence": "phrase du contexte dans l'article",
    "anchor_text": "texte à transformer en lien",
    "target_url": "url de l'article cible",
    "target_title": "titre de l'article cible"
  }}
]"""

    text = call_haiku(prompt)
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except:
        return []


def apply_links_to_markdown(article_md, links):
    """Insert markdown links into the article."""
    modified = article_md
    applied = 0
    for link in links:
        anchor = link.get("anchor_text", "")
        url = link.get("target_url", "")
        if anchor and url and anchor in modified:
            # Only replace first occurrence, and only if not already a link
            if f"[{anchor}]" not in modified:
                modified = modified.replace(anchor, f"[{anchor}]({url})", 1)
                applied += 1
    return modified, applied


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--mode", default="pre", choices=["pre", "retro"])
    args = parser.parse_args()

    queue = json.loads(QUEUE_FILE.read_text()) if QUEUE_FILE.exists() else []
    art = next((a for a in queue if a["id"] == args.id), None)
    if not art:
        print(f"Article {args.id} not found")
        sys.exit(1)

    site = art["site"]
    article_md = art.get("article", {}).get("markdown", "")
    keyword = art["proposal"]["keyword"]

    print(f"[internal_linking] {art['id']} — mode={args.mode}")

    # Get existing articles
    existing = get_existing_articles(site)
    print(f"  Found {len(existing)} existing articles on {site}")

    if not existing:
        print("  No articles to link to — skipping")
        return

    # Suggest links
    links = suggest_internal_links(article_md, keyword, existing)
    print(f"  Suggested {len(links)} internal links")

    if links and args.mode == "pre":
        # Apply links to the article markdown
        modified, applied = apply_links_to_markdown(article_md, links)
        art["article"]["markdown"] = modified
        art["article"]["internal_links"] = links
        art["article"]["internal_links_applied"] = applied
        QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False))
        print(f"  Applied {applied} links to article")

    for l in links:
        print(f"    → [{l.get('anchor_text', '?')}] → {l.get('target_title', '?')}")

    print("[internal_linking] Done!")


if __name__ == "__main__":
    main()
