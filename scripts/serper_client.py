#!/usr/bin/env python3
"""
serper_client.py — Wrapper minimal pour l'API Serper.dev (Google SERP).

Doc : https://serper.dev/
Endpoint principal : POST https://google.serper.dev/search

Crédit consommé : 1 par requête (10 résultats), 2 si num=20-30, etc.
Pour batch (jusqu'à 100 queries) : POST https://google.serper.dev/search avec une liste.
"""

import json
import os
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"

SERPER_URL = "https://google.serper.dev/search"


def _load_key() -> str:
    if k := os.environ.get("SERPER_API_KEY"):
        return k
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("SERPER_API_KEY=") and "=" in line:
                return line.split("=", 1)[1].strip("'\"")
    raise RuntimeError("SERPER_API_KEY introuvable (env ou .env)")


def search(q: str, gl: str = "fr", hl: str = "fr", num: int = 10, page: int = 1, tbs: str | None = None) -> dict:
    """Recherche Google via Serper. Retourne le JSON complet.

    Args:
        q: requête
        gl: country code (fr, us, uk, de, …)
        hl: langue ISO
        num: nombre de résultats (10 = 1 crédit, 20-30 = 2 crédits)
        page: pagination (1, 2, 3…)
        tbs: filtre dates (ex: "qdr:y" = past year, "qdr:m" = past month)
    """
    payload = {"q": q, "gl": gl, "hl": hl, "num": num, "page": page}
    if tbs:
        payload["tbs"] = tbs
    r = requests.post(
        SERPER_URL,
        headers={"X-API-KEY": _load_key(), "Content-Type": "application/json"},
        json=payload, timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    _log_cost(q, num, data.get("credits", 1))
    return data


def search_batch(queries: list[dict]) -> list[dict]:
    """Batch jusqu'à 100 queries (chacune = 1 dict {q, gl, hl, num...}). Retourne une liste."""
    if len(queries) > 100:
        raise ValueError("max 100 queries par batch")
    r = requests.post(
        SERPER_URL,
        headers={"X-API-KEY": _load_key(), "Content-Type": "application/json"},
        json=queries, timeout=60,
    )
    r.raise_for_status()
    results = r.json()
    if isinstance(results, list):
        total_credits = sum(rr.get("credits", 1) for rr in results)
        _log_cost(f"batch:{len(queries)}", sum(q.get("num", 10) for q in queries), total_credits)
    return results


def search_organic(q: str, **kwargs) -> list[dict]:
    """Retourne uniquement la liste organic. Helper."""
    data = search(q, **kwargs)
    return data.get("organic", [])


def _log_cost(query: str, num: int, credits: int) -> None:
    """Logge dans memory/shared/costs-log.json via cost_tracker (model=serper)."""
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR))
        from scripts.cost_tracker import track
        # Serper : ~$0.001 par crédit (forfait ~$50 pour 50K crédits)
        usd_per_credit = 0.001
        # On encode le coût dans le cost-tracker via model="serper-search"
        # input_tok=0, output_tok=0 — c'est plat, on patche cost_usd manuellement
        from datetime import datetime, timezone
        entry = {
            "date":      datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action":    f"serper-search",
            "module":    "scraping",
            "model":     "serper-search",
            "input_tok": 0, "output_tok": 0, "total_tok": 0,
            "cost_usd":  round(credits * usd_per_credit, 6),
            "cost_eur":  round(credits * usd_per_credit * 0.92, 6),
            "cost_cents": round(credits * usd_per_credit * 100, 4),
            "note":      f"q={query[:60]} credits={credits}",
            "site":      "",
        }
        log_path = BASE_DIR / "memory" / "shared" / "costs-log.json"
        log = json.loads(log_path.read_text()) if log_path.exists() else []
        if not isinstance(log, list):
            log = []
        log.append(entry)
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2))
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "restaurant Lyon"
    data = search(q, num=5)
    for r in data.get("organic", [])[:5]:
        print(f"{r.get('position',0)}. {r.get('title','')[:70]}")
        print(f"   {r.get('link','')}")
