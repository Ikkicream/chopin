import os, json, re
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

ARTICLES_DIR = "/home/autoblog/blog/articles"
BLOG_URL     = "https://leclientroi.com/blog"
SECRET       = os.getenv("ARVOW_WEBHOOK_SECRET", "f60774f9-143b-4ca5-8224-0382029d9560")

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[àâä]', 'a', text)
    text = re.sub(r'[éèêë]', 'e', text)
    text = re.sub(r'[îï]', 'i', text)
    text = re.sub(r'[ôö]', 'o', text)
    text = re.sub(r'[ùûü]', 'u', text)
    text = re.sub(r'[ç]', 'c', text)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s]+', '-', text)
    return text[:80].strip('-')

@app.route("/", methods=["GET"])
def health():
    count = len([f for f in os.listdir(ARTICLES_DIR) if f.endswith('.md')])
    return jsonify({"status": "ok", "articles": count}), 200

@app.route("/arvow-webhook", methods=["POST"])
def arvow_webhook():
    # Vérifier le secret
    if request.headers.get("X-Secret") != SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True)
    if not data or not data.get("title"):
        return jsonify({"error": "Invalid payload"}), 400

    title     = data.get("title", "").strip()
    content   = data.get("content_markdown") or data.get("content", "")
    meta      = data.get("metadescription", "")
    keyword   = data.get("keyword_seed", "")
    thumbnail = data.get("thumbnail", "")
    tags      = data.get("tags", [])
    arvow_id  = data.get("id", "")
    date_str  = datetime.utcnow().strftime("%Y-%m-%d")

    slug = slugify(title)
    filename = f"{date_str}-{slug}.md"
    filepath = os.path.join(ARTICLES_DIR, filename)

    # Frontmatter + contenu
    md = f"""---
title: "{title}"
date: "{date_str}"
slug: "{slug}"
keyword: "{keyword}"
metadescription: "{meta}"
thumbnail: "{thumbnail}"
tags: {json.dumps(tags, ensure_ascii=False)}
arvow_id: "{arvow_id}"
status: "draft"
---

{content}
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)

    url = f"{BLOG_URL}/{slug}"
    print(f"[{date_str}] Article sauvegardé : {filename} → {url}")
    return jsonify({"url": url}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5055)
