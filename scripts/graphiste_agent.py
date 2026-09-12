#!/usr/bin/env python3
"""graphiste_agent.py — Agent graphiste autonome qui enrichit les articles emdash.

Boucle agent_core :
- observe : liste les posts emdash sans `seo.image`
- recall : actions graphiste passées (via agent_actions)
- decide : DeepSeek (playbook skills/graphiste.md) choisit l'article + rédige le brief
  visuel anglais selon les règles LeClientROI (patron 55-65, photo doc iPhone/Portra,
  ancrage métier, pas de cliché « jeune Parisienne en café »)
- act : Imagen 3 → resize 800px + JPEG 88 (pas de logo, pas de texte overlay) →
  upload emdash → PUT le post pour mettre seo.image

Cron suggéré : 11h UTC (après les publications de 10h) ou au fil de l'eau.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
EMDASH_URL = "http://localhost:4321/_emdash/api"
sys.path.insert(0, str(BASE_DIR / "scripts"))

from agent_core import (  # noqa: E402
    decide, ensure_schema, load_playbook, recall, record_action,
)


def _env() -> dict:
    env = {}
    for line in (BASE_DIR / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def _hdrs(env: dict) -> dict:
    return {"Authorization": f"Bearer {env['EMDASH_API_TOKEN']}",
            "Content-Type": "application/json", "Origin": "http://localhost:4321"}


def list_posts_without_image(env: dict, limit: int = 50) -> list[dict]:
    r = requests.get(f"{EMDASH_URL}/content/posts?limit={limit}",
                     headers={"Authorization": f"Bearer {env['EMDASH_API_TOKEN']}"},
                     timeout=15)
    r.raise_for_status()
    items = r.json().get("data", {}).get("items", [])
    return [p for p in items
            if p.get("status") == "published" and not (p.get("seo") or {}).get("image")]


def observe_articles(site: str, env: dict) -> dict:
    """Snapshot : articles publiés sans image header."""
    posts = list_posts_without_image(env)
    return {
        "site": site,
        "at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "emdash": {
                "total_without_image": len(posts),
                "candidates": [
                    {
                        "id": p["id"],
                        "slug": p.get("slug"),
                        "title": p.get("data", {}).get("title"),
                        "published_at": p.get("publishedAt"),
                    }
                    for p in posts[:15]
                ],
            }
        },
    }


def update_post_image(post_id: str, image_url: str, env: dict) -> None:
    """PUT du post pour mettre seo.image = image_url (les autres champs inchangés)."""
    r = requests.get(f"{EMDASH_URL}/content/posts/{post_id}",
                     headers={"Authorization": f"Bearer {env['EMDASH_API_TOKEN']}"},
                     timeout=15)
    r.raise_for_status()
    item = r.json()["data"]["item"]
    seo = item.get("seo") or {}
    seo["image"] = image_url
    payload = {"slug": item["slug"], "status": item["status"],
               "data": item["data"], "seo": seo}
    r2 = requests.put(f"{EMDASH_URL}/content/posts/{post_id}",
                      headers=_hdrs(env), json=payload, timeout=20)
    r2.raise_for_status()


def write_image(item: dict, snapshot: dict, *, env: dict, dry_run: bool):
    """writer_fn pour run_cycle : génère image + upload emdash + update seo.image."""
    if item.get("action_type") != "generate_header":
        print(f"  [graphiste] action_type non géré: {item.get('action_type')!r} — skip")
        return
    tags = item.get("tags") or {}
    post_id = item.get("target")
    brief = tags.get("image_brief")
    aspect = tags.get("aspect", "16:9")
    slug = tags.get("post_slug") or post_id

    if not (post_id and brief):
        raise ValueError("plan sans target (post_id) ou image_brief")

    if dry_run:
        print(f"  [graphiste] DRY-RUN post={post_id} brief={brief[:120]}…")
        item["dry_run"] = True
        return

    sys.path.insert(0, str(BASE_DIR / "scripts"))
    if "imagen_generate" in sys.modules:
        del sys.modules["imagen_generate"]
    from imagen_generate import STYLE_PREFIX, generate as imagen_gen, postprocess, upload_emdash
    full_prompt = f"{STYLE_PREFIX} {brief}"
    print(f"  [graphiste] génération image post={post_id}…")
    raw = imagen_gen(full_prompt, aspect=aspect, n=1)[0]
    jpeg = postprocess(raw, overlay_text=None, with_logo=False)

    # Sauve local pour audit
    local = BASE_DIR / "data" / "generated_images" / f"{slug}.jpg"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(jpeg)
    print(f"  [graphiste] local: {local} ({len(jpeg)//1024} KB)")

    image_url = upload_emdash(jpeg, f"{slug}.jpg", env)
    if not image_url:
        raise RuntimeError("upload emdash a renvoyé None")
    print(f"  [graphiste] upload: {image_url}")

    update_post_image(post_id, image_url, env)
    print(f"  [graphiste] post {post_id} → seo.image posée")
    item["image_url"] = image_url


def run_cycle(site: str = "lcr", dry_run: bool = True) -> dict:
    ensure_schema()
    cycle_id = str(uuid.uuid4())
    env = _env()
    snap = observe_articles(site, env)
    mem = recall("graphiste", site)
    playbook = load_playbook("graphiste", site)
    plan = decide("graphiste", site, playbook, snap, mem)
    items = plan.get("plan", []) if isinstance(plan, dict) else []
    reasoning = plan.get("reasoning", "") if isinstance(plan, dict) else ""
    n_candidates = snap["sources"]["emdash"]["total_without_image"]
    print(f"[graphiste] cycle {cycle_id[:8]} : {n_candidates} articles sans image, "
          f"{len(items)} item(s) à traiter")

    written = 0
    if not items:
        record_action(cycle_id, "graphiste", site, snap,
                      reasoning or "rien à faire (aucun article sans image)",
                      "noop", None, {}, status="done")
        written = 1

    for it in items:
        status = "planned"
        try:
            write_image(it, snap, env=env, dry_run=dry_run)
            status = "done"
        except Exception as e:  # noqa: BLE001
            it["error"] = str(e)
            status = "error"
            print(f"  [error] {e}")
        record_action(cycle_id, "graphiste", site, snap, reasoning,
                      it.get("action_type", "?"), it.get("target"),
                      it.get("tags") or {}, status=status)
        written += 1

    return {"cycle_id": cycle_id, "agent": "graphiste", "site": site,
            "candidates": n_candidates, "reasoning": reasoning,
            "plan_items": len(items), "actions_written": written}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="lcr")
    ap.add_argument("--live", action="store_true",
                    help="Exécute pour de vrai (sinon dry-run)")
    args = ap.parse_args()
    out = run_cycle(site=args.site, dry_run=not args.live)
    print(json.dumps(out, ensure_ascii=False, default=str))
