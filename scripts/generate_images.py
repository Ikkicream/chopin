#!/usr/bin/env python3
"""
generate_images.py — Génération d'infographies via Higgsfield AI
Utilise le template identité visuelle leclientroi.com.
Uploade automatiquement dans Emdash et retourne les URLs.

Usage:
  python3 generate_images.py --content "Flowchart RCS vs SMS" --slug mon-article
  python3 generate_images.py --schemas schemas.json --post-id 01KQGA2TFHC8EA25BZPH8KKKQ1
"""

import sys
import json
import time
import requests
import argparse
from pathlib import Path

BASE_DIR     = Path(__file__).parent.parent
ENV_FILE     = BASE_DIR / ".env"
TEMPLATE_FILE = BASE_DIR / "context" / "shared" / "image-prompt-template.txt"
EMDASH_URL   = "http://localhost:4321/_emdash/api"
HIGGSFIELD_URL = "https://platform.higgsfield.ai"
# popcorn/auto = meilleur modèle Higgsfield pour les layouts (mais texte encore imprécis)
# Pour infographies avec texte précis → utiliser scripts/infographic.py (Pillow local)
ENDPOINT     = f"{HIGGSFIELD_URL}/higgsfield-ai/popcorn/auto"
POPCORN_PARAMS = {"task": "text-to-image", "model": "gpt-image", "width": 800, "height": 800, "quality": "hd", "steps": 50}


def load_env():
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def build_prompt(schema_content: str) -> str:
    template = TEMPLATE_FILE.read_text()
    return template.replace("{{SCHEMA_CONTENT}}", schema_content)


def generate_image(prompt: str, auth: str, aspect_ratio: str = "1:1", resolution: str = "1080p") -> str | None:
    """Lance la génération et poll jusqu'au résultat. Retourne l'URL CloudFront."""
    resp = requests.post(ENDPOINT,
        headers={"Authorization": auth, "Content-Type": "application/json", "Accept": "application/json"},
        json={**POPCORN_PARAMS, "prompt": prompt},
        timeout=30
    )
    if resp.status_code != 200:
        print(f"  ⚠ Erreur génération: {resp.status_code} {resp.text[:200]}")
        return None

    data = resp.json()
    request_id = data.get("request_id")
    status_url = data.get("status_url")
    print(f"  Queued → {request_id}")

    # Poll jusqu'à completed (max 3 min)
    for attempt in range(36):
        time.sleep(5)
        r = requests.get(status_url, headers={"Authorization": auth}, timeout=15)
        d = r.json()
        status = d.get("status")
        if status == "completed" and d.get("images"):
            url = d["images"][0]["url"]
            print(f"  ✓ Générée: {url[:80]}...")
            return url
        if status == "failed":
            print(f"  ✗ Échec génération")
            return None
        if attempt % 3 == 0:
            print(f"  ... {status} ({attempt*5}s)")

    print("  ✗ Timeout")
    return None


def upload_to_emdash(image_url: str, filename: str, emdash_token: str) -> str | None:
    """Télécharge depuis CloudFront et uploade dans Emdash. Retourne l'URL publique."""
    img_data = requests.get(image_url, timeout=60).content
    print(f"  Téléchargé: {len(img_data)//1024}KB")

    resp = requests.post(f"{EMDASH_URL}/media",
        headers={"Authorization": f"Bearer {emdash_token}", "Origin": "http://localhost:4321"},
        files={"file": (filename, img_data, "image/png")}
    )
    if resp.status_code != 200:
        print(f"  ⚠ Erreur upload Emdash: {resp.status_code}")
        return None

    item = resp.json()["data"]["item"]
    public_url = "https://blog.leclientroi.com" + item["url"]
    print(f"  ✓ Uploadé: {public_url}")
    return public_url


def insert_into_article(post_id: str, schemas: list[dict], emdash_token: str) -> bool:
    """
    Insère les schémas dans un article Emdash.
    schemas = [{"key": "kschema01", "url": "...", "alt": "...", "caption": "..."}]
    """
    headers_json = {"Authorization": f"Bearer {emdash_token}", "Content-Type": "application/json"}
    headers_form = {"Authorization": f"Bearer {emdash_token}", "Origin": "http://localhost:4321"}

    # Récupérer l'article
    post = requests.get(f"{EMDASH_URL}/content/posts/{post_id}",
        headers={"Authorization": f"Bearer {emdash_token}"}).json()["data"]["item"]
    content = post["data"]["content"]

    # Trouver les clés existantes ou ajouter à la fin
    key_map = {s["key"]: s for s in schemas}
    updated = 0

    for i, block in enumerate(content):
        if block.get("_key") in key_map:
            s = key_map[block["_key"]]
            content[i] = {
                "_type": "htmlBlock",
                "_key": block["_key"],
                "html": f'<figure><img src="{s["url"]}" alt="{s["alt"]}" width="800" loading="lazy"><figcaption>{s["caption"]}</figcaption></figure>'
            }
            updated += 1

    # Si les clés n'existent pas encore, ajouter après l'intro
    for s in schemas:
        if not any(b.get("_key") == s["key"] for b in content):
            content.append({
                "_type": "htmlBlock",
                "_key": s["key"],
                "html": f'<figure><img src="{s["url"]}" alt="{s["alt"]}" width="800" loading="lazy"><figcaption>{s["caption"]}</figcaption></figure>'
            })
            updated += 1

    print(f"  {updated} bloc(s) mis à jour dans l'article")

    post["data"]["content"] = content
    r = requests.put(f"{EMDASH_URL}/content/posts/{post_id}", headers=headers_json, json={"data": post["data"]})
    if r.status_code != 200:
        print(f"  ⚠ PUT échoué: {r.status_code}")
        return False

    pub = requests.post(f"{EMDASH_URL}/content/posts/{post_id}/publish", headers=headers_form)
    return pub.status_code == 200


def generate_article_schemas(post_id: str, schema_contents: list[dict], env: dict) -> list[str]:
    """
    Workflow complet : génère N schémas, uploade dans Emdash, insère dans l'article.

    schema_contents = [
        {"key": "kschema01", "content": "...", "alt": "...", "caption": "...", "filename": "..."},
        ...
    ]
    Retourne les URLs Emdash des images générées.
    """
    auth = f"Key {env['HIGGSFIELD_API_KEY']}:{env['HIGGSFIELD_API_SECRET']}"
    emdash_token = env["EMDASH_API_TOKEN"]

    # 1. Lancer toutes les générations en parallèle (soumission)
    pending = {}
    for sc in schema_contents:
        print(f"\n[generate] Soumission: {sc['key']}")
        prompt = build_prompt(sc["content"])
        resp = requests.post(ENDPOINT,
            headers={"Authorization": auth, "Content-Type": "application/json", "Accept": "application/json"},
            json={**POPCORN_PARAMS, "prompt": prompt},
            timeout=30
        )
        data = resp.json()
        pending[sc["key"]] = {**sc, "request_id": data["request_id"], "status_url": data["status_url"]}
        print(f"  Queued → {data['request_id']}")

    # 2. Poll tous jusqu'à completion
    cloudfront_urls = {}
    print("\n[generate] Attente des images...")
    for attempt in range(36):
        time.sleep(5)
        for key, job in pending.items():
            if key in cloudfront_urls:
                continue
            r = requests.get(job["status_url"], headers={"Authorization": auth}, timeout=15)
            d = r.json()
            if d.get("status") == "completed" and d.get("images"):
                cloudfront_urls[key] = d["images"][0]["url"]
                print(f"  ✓ {key} prête")
        if len(cloudfront_urls) == len(pending):
            break
        if attempt % 3 == 0:
            print(f"  ... {len(cloudfront_urls)}/{len(pending)} ({attempt*5}s)")

    # 3. Upload dans Emdash
    emdash_schemas = []
    for sc in schema_contents:
        key = sc["key"]
        if key not in cloudfront_urls:
            print(f"  ✗ {key} non générée")
            continue
        print(f"\n[upload] {key}")
        public_url = upload_to_emdash(cloudfront_urls[key], sc["filename"], emdash_token)
        if public_url:
            emdash_schemas.append({
                "key": key,
                "url": public_url,
                "alt": sc["alt"],
                "caption": sc["caption"],
            })

    # 4. Insérer dans l'article
    if post_id and emdash_schemas:
        print(f"\n[insert] Article {post_id}")
        ok = insert_into_article(post_id, emdash_schemas, emdash_token)
        print(f"  {'✓ Publié' if ok else '✗ Erreur publication'}")

    return [s["url"] for s in emdash_schemas]


def main():
    parser = argparse.ArgumentParser(description="Génération d'images infographiques Higgsfield")
    parser.add_argument("--content", help="Contenu du schéma (texte libre)")
    parser.add_argument("--post-id", help="ID Emdash de l'article à mettre à jour")
    parser.add_argument("--schemas", help="Fichier JSON avec les schémas à générer")
    parser.add_argument("--aspect", default="1:1", choices=["1:1", "16:9", "9:16"])
    parser.add_argument("--resolution", default="1080p", choices=["720p", "1080p"])
    args = parser.parse_args()

    env = load_env()
    auth = f"Key {env['HIGGSFIELD_API_KEY']}:{env['HIGGSFIELD_API_SECRET']}"

    if args.content:
        print("[generate_images] Génération simple...")
        prompt = build_prompt(args.content)
        url = generate_image(prompt, auth, args.aspect, args.resolution)
        if url:
            emdash_url = upload_to_emdash(url, "infographic.png", env["EMDASH_API_TOKEN"])
            print(f"\nURL finale: {emdash_url}")
    elif args.schemas:
        schemas = json.loads(Path(args.schemas).read_text())
        generate_article_schemas(args.post_id, schemas, env)
    else:
        print("Usage: --content 'texte' ou --schemas fichier.json")
        print("Exemple: python3 generate_images.py --content 'Comparaison RCS vs SMS avec tableau'")


if __name__ == "__main__":
    main()
