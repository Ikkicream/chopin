"""
Editorial Pipeline API — endpoints for the article queue.
Integrated into the main Genesis FastAPI app.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

EDITORIAL_DIR = Path("/home/autoblog/genesis/memory/editorial")
EDITORIAL_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_FILE = EDITORIAL_DIR / "articles-queue.json"


def _load_queue():
    if QUEUE_FILE.exists():
        return json.loads(QUEUE_FILE.read_text())
    return []


def _save_queue(queue):
    QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False))


def _find_article(queue, article_id):
    for i, art in enumerate(queue):
        if art["id"] == article_id:
            return i, art
    return -1, None


# --- Endpoint handlers (to be registered in api.py) ---

async def editorial_queue_get():
    """GET /api/editorial/queue"""
    return {"articles": _load_queue()}


async def editorial_queue_post(data: dict):
    """POST /api/editorial/queue — create a new proposal."""
    queue = _load_queue()
    now = datetime.now(timezone.utc).isoformat()
    site = data.get("site", "lcr")
    count = len([a for a in queue if a["site"] == site]) + 1
    article_id = f"art_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{site}_{count:03d}"

    article = {
        "id": article_id,
        "site": site,
        "status": "proposed",
        "created_at": now,
        "updated_at": now,
        "proposal": {
            "title": data.get("title", ""),
            "summary": data.get("summary", ""),
            "keyword": data.get("keyword", ""),
            "volume": data.get("volume", 0),
            "kd": data.get("kd", 0),
            "rationale": data.get("rationale", ""),
        },
        "seo_check": data.get("seo_check"),
        "article": None,
        "qc_report": None,
        "human_notes": None,
    }
    queue.append(article)
    _save_queue(queue)
    return {"ok": True, "id": article_id, "article": article}


async def editorial_approve(article_id: str):
    """POST /api/editorial/{id}/approve"""
    queue = _load_queue()
    idx, art = _find_article(queue, article_id)
    if idx == -1:
        return {"error": "not found"}
    art["status"] = "approved"
    art["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_queue(queue)

    # Trigger content agent in background
    subprocess.Popen(
        ["python3", "scripts/editorial_writer.py", "--id", article_id],
        cwd="/home/autoblog/genesis",
        stdout=open(f"/home/autoblog/genesis/memory/editorial/{article_id}-content.log", "w"),
        stderr=subprocess.STDOUT,
    )
    return {"ok": True, "status": "approved", "message": "Rédaction lancée"}


async def editorial_reject(article_id: str):
    """POST /api/editorial/{id}/reject"""
    queue = _load_queue()
    idx, art = _find_article(queue, article_id)
    if idx == -1:
        return {"error": "not found"}
    art["status"] = "rejected"
    art["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_queue(queue)
    return {"ok": True, "status": "rejected"}


async def editorial_publish(article_id: str):
    """POST /api/editorial/{id}/publish"""
    queue = _load_queue()
    idx, art = _find_article(queue, article_id)
    if idx == -1:
        return {"error": "not found"}
    if art["status"] not in ("ready_to_review", "ready_to_publish"):
        return {"error": "article not ready", "current_status": art["status"]}

    # Publish via CMS
    art["status"] = "publishing"
    art["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_queue(queue)

    subprocess.Popen(
        ["python3", "scripts/publish_agent.py", "--editorial-id", article_id],
        cwd="/home/autoblog/genesis",
        stdout=open(f"/home/autoblog/genesis/memory/editorial/{article_id}-publish.log", "w"),
        stderr=subprocess.STDOUT,
    )
    return {"ok": True, "status": "publishing", "message": "Publication en cours"}


async def editorial_revision(article_id: str, data: dict):
    """POST /api/editorial/{id}/revision"""
    queue = _load_queue()
    idx, art = _find_article(queue, article_id)
    if idx == -1:
        return {"error": "not found"}
    art["status"] = "revision_needed"
    art["human_notes"] = data.get("notes", "")
    art["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_queue(queue)
    return {"ok": True, "status": "revision_needed"}


async def editorial_detail(article_id: str):
    """GET /api/editorial/{id}"""
    queue = _load_queue()
    _, art = _find_article(queue, article_id)
    if art is None:
        return {"error": "not found"}
    return art


async def editorial_patch(article_id: str, data: dict):
    """PATCH /api/editorial/{id}"""
    queue = _load_queue()
    idx, art = _find_article(queue, article_id)
    if idx == -1:
        return {"error": "not found"}
    if "title" in data and art.get("proposal"):
        art["proposal"]["title"] = data["title"]
    if "summary" in data and art.get("proposal"):
        art["proposal"]["summary"] = data["summary"]
    if "status" in data:
        art["status"] = data["status"]
    if "markdown" in data:
        art.setdefault("article", {})
        art["article"]["markdown"] = data["markdown"]
        try:
            art["article"]["word_count"] = len(data["markdown"].split())
        except Exception:
            pass
    art["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_queue(queue)
    return {"ok": True, "article": art}
