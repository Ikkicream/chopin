#!/usr/bin/env python3
"""
publish_agent.py - Publish an approved article to the CMS.
LCR -> Emdash API (Portable Text with proper bold/italic marks)
MKD -> WordPress REST API (HTML)
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
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

EMDASH_URL = os.environ.get("EMDASH_API_URL", "http://localhost:4321/_emdash/api")
EMDASH_TOKEN = os.environ.get("EMDASH_API_TOKEN", "")
WP_URL = os.environ.get("WP_SITE_URL", "")
WP_USER = os.environ.get("WP_USERNAME", "")
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")


def load_queue():
    if QUEUE_FILE.exists():
        return json.loads(QUEUE_FILE.read_text())
    return []

def save_queue(queue):
    QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False))


def slugify(title, max_len=45):
    slug = unicodedata.normalize("NFD", title.lower())
    slug = re.sub(r"[\u0300-\u036f]", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0]
    return slug


def parse_inline(text):
    """Parse **bold** and *italic* into Portable Text children with marks."""
    children = []
    kc = [0]
    def nk():
        kc[0] += 1
        return f"s{kc[0]:03d}"

    remaining = text
    while remaining:
        bold = re.search(r"\*\*(.+?)\*\*", remaining)
        italic = re.search(r"(?<!\*)\*([^*]+?)\*(?!\*)", remaining)
        first = None
        mtype = None
        if bold and (not italic or bold.start() <= italic.start()):
            first, mtype = bold, "strong"
        elif italic:
            first, mtype = italic, "em"
        if not first:
            if remaining:
                children.append({"_type": "span", "_key": nk(), "text": remaining, "marks": []})
            break
        if first.start() > 0:
            children.append({"_type": "span", "_key": nk(), "text": remaining[:first.start()], "marks": []})
        children.append({"_type": "span", "_key": nk(), "text": first.group(1), "marks": [mtype]})
        remaining = remaining[first.end():]
    return children or [{"_type": "span", "_key": "s000", "text": text, "marks": []}]


def md_to_portable_text(markdown):
    """Convert markdown to Emdash Portable Text blocks."""
    blocks = []
    kc = [0]
    def nk():
        kc[0] += 1
        return f"k{kc[0]:04d}"

    for para in markdown.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if para.startswith("# "):
            blocks.append({"_type": "block", "_key": nk(), "style": "h2", "markDefs": [], "children": parse_inline(para[2:])})
        elif para.startswith("## "):
            blocks.append({"_type": "block", "_key": nk(), "style": "h3", "markDefs": [], "children": parse_inline(para[3:])})
        elif para.startswith("### "):
            blocks.append({"_type": "block", "_key": nk(), "style": "h3", "markDefs": [], "children": parse_inline(para[4:])})
        elif para.startswith("> "):
            blocks.append({"_type": "block", "_key": nk(), "style": "blockquote", "markDefs": [], "children": parse_inline(para[2:])})
        elif para.startswith("- "):
            for item in para.split("\n"):
                if item.startswith("- "):
                    blocks.append({"_type": "block", "_key": nk(), "style": "normal", "listItem": "bullet", "level": 1, "markDefs": [], "children": parse_inline(item[2:])})
        else:
            blocks.append({"_type": "block", "_key": nk(), "style": "normal", "markDefs": [], "children": parse_inline(para.replace("\n", " "))})
    return blocks


def md_to_html(md):
    """Convert markdown to HTML for WordPress."""
    html = md
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", html)
    html = re.sub(r"^> (.+)$", r"<blockquote>\1</blockquote>", html, flags=re.MULTILINE)
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"(<li>.*?</li>\n?)+", lambda m: "<ul>" + m.group(0) + "</ul>", html)
    paras = html.split("\n\n")
    result = []
    for p in paras:
        p = p.strip()
        if not p:
            continue
        if p.startswith(("<h", "<ul", "<blockquote")):
            result.append(p)
        else:
            result.append(f"<p>{p}</p>")
    return "\n".join(result)


def publish_emdash(title, slug, content_md):
    """Create + publish on Emdash CMS."""
    headers = {"Authorization": f"Bearer {EMDASH_TOKEN}", "Content-Type": "application/json"}
    blocks = md_to_portable_text(content_md)

    # Add featured image if available
    image_data = {}
    if art.get('article', {}).get('image'):
        img = art['article']['image']
        image_data = {
            'featured_image': {
                'id': '',
                'provider': 'external',
                'src': img['url'],
                'width': 1080,
                'height': 720,
                'alt': img.get('alt', title),
            }
        }

    # Create post
    payload = {"data": {"title": title, "content": blocks, **image_data}}
    r = requests.post(f"{EMDASH_URL}/content/posts", json=payload, headers=headers, timeout=30)
    if r.status_code not in (200, 201):
        return False, f"Emdash create error {r.status_code}: {r.text[:200]}", None

    post_id = r.json().get("data", {}).get("item", {}).get("id", "")
    if not post_id:
        return False, "No post ID returned", None

    # Publish
    r2 = requests.post(f"{EMDASH_URL}/content/posts/{post_id}/publish", headers=headers, timeout=30)
    if r2.status_code == 200:
        actual_slug = r2.json().get("data", {}).get("item", {}).get("slug", slug)
        url = f"https://blog.leclientroi.com/posts/{actual_slug}"
        return True, url, post_id
    return False, f"Emdash publish error {r2.status_code}", post_id


def publish_wordpress(title, slug, content_md):
    """Publish on WordPress."""
    html = md_to_html(content_md)
    payload = {"title": title, "slug": slug, "content": html, "status": "publish"}
    r = requests.post(f"{WP_URL}/wp-json/wp/v2/posts", json=payload, auth=(WP_USER, WP_PASS), timeout=30)
    if r.status_code in (200, 201):
        data = r.json()
        return True, data.get("link", f"{WP_URL}/{slug}"), data.get("id")
    return False, f"WP error {r.status_code}: {r.text[:200]}", None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--editorial-id", required=True)
    args = parser.parse_args()

    queue = load_queue()
    art = next((a for a in queue if a["id"] == args.editorial_id), None)
    if not art:
        print(f"ERROR: {args.editorial_id} not found")
        sys.exit(1)
    if not art.get("article", {}).get("markdown"):
        print("ERROR: No content")
        art["status"] = "revision_needed"
        save_queue(queue)
        sys.exit(1)

    title = art["proposal"]["title"]
    slug = slugify(title)
    content_md = art["article"]["markdown"]
    site = art["site"]

    print(f"[publish] {art['id']} -> {site.upper()} -- {title}")

    if site == "lcr":
        ok, url_or_err, post_id = publish_emdash(title, slug, content_md)
    elif site == "mkd":
        ok, url_or_err, post_id = publish_wordpress(title, slug, content_md)
    else:
        print(f"Unknown site: {site}")
        sys.exit(1)

    if ok:
        art["status"] = "published"
        art["published_at"] = datetime.now(timezone.utc).isoformat()
        art["published_url"] = url_or_err
        print(f"  Published: {url_or_err}")
    else:
        art["status"] = "revision_needed"
        art["human_notes"] = f"Erreur: {url_or_err}"
        print(f"  ERROR: {url_or_err}")

    art["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_queue(queue)


if __name__ == "__main__":
    main()
