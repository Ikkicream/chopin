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


# ── Mode agentique (boucle agent_core) ──────────────────────────────────────
# observe GSC/GA4 → recall liens posés précédemment → decide via playbook
# skills/internal-linking.md (format JSON add_internal_link + anchor + destination)
# → act = ouvre l'article cible, insère le lien dans le markdown, sauve la queue.

def _agentic_writer(item: dict, snapshot: dict, *, site: str, dry_run: bool):
    if item.get("action_type") != "add_internal_link":
        print(f"  [agentic] action_type non géré: {item.get('action_type')!r} — skip")
        return
    target = item.get("target")  # URL/title de l'article source qui doit recevoir le lien
    tags = item.get("tags") or {}
    anchor = tags.get("anchor_text")
    dest = tags.get("destination_url")
    if not (target and anchor and dest):
        raise ValueError("plan sans target/anchor_text/destination_url")
    if dry_run:
        print(f"  [agentic] DRY-RUN link {anchor!r} → {dest} dans {target!r}")
        item["dry_run"] = True
        return
    if not QUEUE_FILE.exists():
        raise FileNotFoundError("queue éditoriale introuvable")
    queue = json.loads(QUEUE_FILE.read_text())
    art = next((a for a in queue
                if a.get("published_url") == target
                or a.get("proposal", {}).get("title", "").lower() == target.lower()
                or a.get("id") == target), None)
    if not art:
        raise ValueError(f"article source introuvable : {target!r}")
    md = art.get("article", {}).get("markdown", "")
    if not md:
        raise ValueError(f"article {art['id']} sans markdown")
    modified, applied = apply_links_to_markdown(md, [{"anchor_text": anchor, "target_url": dest}])
    if applied == 0:
        item["skipped"] = "ancre introuvable dans le markdown"
        return
    art["article"]["markdown"] = modified
    art["article"].setdefault("internal_links", []).append(
        {"anchor_text": anchor, "target_url": dest, "source": "agentic",
         "applied_at": datetime.now(timezone.utc).isoformat()})
    art["article"]["internal_links_applied"] = art["article"].get("internal_links_applied", 0) + applied
    QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False))
    item["article_id"] = art["id"]
    item["applied"] = applied


def run_agentic(site: str, dry_run: bool = True) -> dict:
    from functools import partial
    print(f"[internal_linking_agent agentic] Site: {site.upper()} — "
          f"{'DRY-RUN' if dry_run else 'LIVE'}")
    sys.path.insert(0, str(Path(__file__).parent))
    from agent_core import run_cycle
    writer = partial(_agentic_writer, site=site, dry_run=dry_run)
    result = run_cycle(agent="internal-linking", site=site,
                       sources=("gsc", "ga4"), writer_fn=writer)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--id")
    parser.add_argument("--mode", default="pre", choices=["pre", "retro"])
    parser.add_argument("--site", choices=["lcr", "mkd", "both"], default="lcr")
    parser.add_argument("--agentic", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    if args.agentic:
        sites = ["lcr", "mkd"] if args.site == "both" else [args.site]
        for s in sites:
            run_agentic(s, dry_run=not args.live)
        return

    if not args.id:
        parser.error("--id requis en mode classique (sinon utiliser --agentic)")

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
