#!/usr/bin/env python3
"""
leads_api.py — Dashboard leads (cold email + SMS) sur port 8081
Endpoints: /api/overview, /api/tab/{source}, /api/search, /api/export
"""
import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).parent.parent
LEADS_LOG = BASE_DIR / "data" / "leads-log.json"
HTML_FILE = BASE_DIR / "dashboard" / "leads.html"

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_entries() -> list[dict]:
    if not LEADS_LOG.exists():
        return []
    data = json.loads(LEADS_LOG.read_text())
    return data.get("entries", [])


def save_entry(entry: dict):
    data = json.loads(LEADS_LOG.read_text()) if LEADS_LOG.exists() else {"version": 1, "entries": []}
    data["entries"].append(entry)
    LEADS_LOG.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def status_bucket(status: str) -> str:
    s = (status or "").lower()
    if s in ("ok", "contacted", "sent", "replied", "opened"):
        return "ok"
    if s in ("rejected", "bounced", "invalid", "error"):
        return "rejected"
    if s in ("dropped", "unsubscribed", "blacklisted", "optout"):
        return "dropped"
    return "error"


def parse_date(entry: dict) -> str:
    """Retourne YYYY-MM-DD ou '' """
    raw = entry.get("date") or entry.get("datetime") or ""
    return raw[:10] if raw else ""


def parse_month(entry: dict) -> str:
    return parse_date(entry)[:7]  # YYYY-MM


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_html():
    if HTML_FILE.exists():
        return HTMLResponse(content=HTML_FILE.read_text())
    return HTMLResponse(content="<h1>leads.html introuvable</h1>")


@app.get("/api/overview")
def overview():
    entries = load_entries()

    totals = {"total": 0, "ok": 0, "rejected": 0, "dropped": 0, "error": 0}
    sources: dict[str, dict] = {}
    monthly: dict[str, dict] = {}

    for e in entries:
        bucket = status_bucket(e.get("status", ""))
        src = e.get("source", "inconnu")
        month = parse_month(e)

        # Totals
        totals["total"] += 1
        totals[bucket] = totals.get(bucket, 0) + 1

        # By source
        if src not in sources:
            sources[src] = {"total": 0, "ok": 0, "rejected": 0, "dropped": 0, "error": 0}
        sources[src]["total"] += 1
        sources[src][bucket] += 1

        # By month
        if month:
            if month not in monthly:
                monthly[month] = {"total": 0, "ok": 0, "rejected": 0, "dropped": 0, "error": 0}
            monthly[month]["total"] += 1
            monthly[month][bucket] += 1

    return {
        "totals": totals,
        "sources": sources,
        "monthly": dict(sorted(monthly.items())),
    }


@app.get("/api/tab/{source}")
def tab(source: str):
    entries = load_entries()
    filtered = [e for e in entries if e.get("source", "inconnu") == source]

    stats = {"total": 0, "ok": 0, "rejected": 0, "dropped": 0, "error": 0}
    by_day: dict[str, dict] = {}

    for e in filtered:
        bucket = status_bucket(e.get("status", ""))
        day = parse_date(e)
        stats["total"] += 1
        stats[bucket] += 1
        if day:
            if day not in by_day:
                by_day[day] = {"sent": 0, "ok": 0, "rejected": 0, "dropped": 0, "error": 0}
            by_day[day]["sent"] += 1
            by_day[day][bucket] += 1

    return {"source": source, "stats": stats, "by_day": dict(sorted(by_day.items()))}


@app.get("/api/search")
def search(q: str = ""):
    if len(q) < 4:
        return {"count": 0, "results": []}
    q_lower = q.lower()
    entries = load_entries()
    results = [
        e for e in entries
        if q_lower in (e.get("email") or "").lower()
        or q_lower in (e.get("gsm") or "").lower()
        or q_lower in (e.get("firstName") or "").lower()
        or q_lower in (e.get("lastName") or "").lower()
    ]
    return {"count": len(results), "results": results[:50]}


@app.get("/api/export")
def export(from_date: str = "", to_date: str = "", alias="from"):
    # Parse DD/MM/YYYY → YYYY-MM-DD
    def parse(s: str) -> str:
        try:
            parts = s.strip().split("/")
            if len(parts) == 3:
                return f"{parts[2]}-{parts[1]}-{parts[0]}"
        except Exception:
            pass
        return s

    f = parse(from_date)
    t = parse(to_date)
    entries = load_entries()

    filtered = [
        e for e in entries
        if (not f or parse_date(e) >= f) and (not t or parse_date(e) <= t)
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["date", "source", "email", "gsm",
                                                "firstName", "lastName", "status", "campaign_name", "error_msg"])
    writer.writeheader()
    for e in filtered:
        writer.writerow({
            "date": e.get("date", ""),
            "source": e.get("source", ""),
            "email": e.get("email", ""),
            "gsm": e.get("gsm", ""),
            "firstName": e.get("firstName", ""),
            "lastName": e.get("lastName", ""),
            "status": e.get("status", ""),
            "campaign_name": e.get("campaign_name", ""),
            "error_msg": e.get("error_msg", ""),
        })

    fname = f"leads_{f or 'all'}_{t or 'all'}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/leads/ingest")
def ingest(payload: dict):
    """
    Endpoint webhook pour ingérer un lead depuis n'importe quel script.
    Payload attendu:
    {
      "source": "nom_fichier_csv",
      "email": "xxx@xxx.com",
      "gsm": "+33612345678",      // optionnel
      "firstName": "",            // optionnel
      "lastName": "",             // optionnel
      "status": "ok|rejected|dropped|error",
      "campaign_name": "",        // optionnel
      "error_msg": ""             // optionnel
    }
    """
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "id": f"lead_{now}_{payload.get('email','')}",
        "date": now[:10],
        "datetime": now,
        "source": payload.get("source", "inconnu"),
        "email": payload.get("email", ""),
        "gsm": payload.get("gsm", ""),
        "firstName": payload.get("firstName", ""),
        "lastName": payload.get("lastName", ""),
        "status": payload.get("status", "ok"),
        "campaign_name": payload.get("campaign_name", ""),
        "error_msg": payload.get("error_msg", ""),
    }
    save_entry(entry)
    return {"ok": True, "id": entry["id"]}


@app.get("/api/stats")
def stats():
    entries = load_entries()
    return {"total_entries": len(entries), "log_file": str(LEADS_LOG)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
