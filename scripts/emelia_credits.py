#!/usr/bin/env python3
"""emelia_credits.py — Solde des crédits Emelia (lecture LIVE + suivi local).

✅ SOLDE LIVE (2026-06-17) : l'API GraphQL Emelia expose le solde réel via
   `me { subscription { enrich { creditsRemaining creditsSubscription } } }`
   (requête extraite du front app.emelia.io). `fetch_live_balance()` la lit directement —
   donc pas besoin de saisie manuelle. Vérifié : 949.75 crédits (≈ le 950 annoncé).

Le suivi LOCAL (record/spent) reste utile pour : prédire le coût AVANT un lot, et tracer
l'historique. Coûts waterfall (facturé seulement si trouvé) : find_phone = 50 crédits/numéro
(confirmé), find_email/verify/ai_action à confirmer.

Stockage local : memory/emelia/credits.json
CLI :
  python3 scripts/emelia_credits.py balance       # solde LIVE depuis l'API Emelia
  python3 scripts/emelia_credits.py status        # live + suivi local + historique
  python3 scripts/emelia_credits.py record find_phone   # trace un usage (sinon auto via le code)
"""
from __future__ import annotations

import json
import os
import sys
import ssl
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CREDITS_FILE = BASE_DIR / "memory" / "emelia" / "credits.json"

# --- chargement .env pour la clé Emelia ---
_envf = BASE_DIR / ".env"
if _envf.exists():
    for _l in _envf.read_text().splitlines():
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _v = _l.split("=", 1)
            os.environ.setdefault(_k, _v.strip("'\""))


def fetch_live_balance() -> dict:
    """Lit le solde RÉEL via l'API GraphQL Emelia. Retourne {remaining, subscription, ok}.
    Aucune saisie manuelle requise. Best-effort : {ok:False, error:…} si l'appel échoue."""
    key = os.environ.get("EMELIA_API_KEY") or os.environ.get("EMELIA_KEY", "")
    if not key:
        return {"ok": False, "error": "EMELIA_API_KEY manquante"}
    q = ("{ me { subscription { enrich { creditsRemaining creditsSubscription "
         "expiration } } } }")
    try:
        req = urllib.request.Request(
            "https://api.emelia.io/graphql",
            data=json.dumps({"query": q}).encode(),
            headers={"Authorization": key, "Content-Type": "application/json"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            data = json.loads(r.read())
        enrich = (((data.get("data") or {}).get("me") or {}).get("subscription") or {}).get("enrich") or {}
        raw = enrich.get("creditsRemaining")
        # Le dashboard Emelia AFFICHE l'arrondi (ex. 949.75 → 950). On garde l'arrondi comme
        # référence affichée (`remaining`) + la valeur brute (`remaining_raw`) pour le calcul fin.
        return {"ok": True,
                "remaining": round(raw) if isinstance(raw, (int, float)) else raw,
                "remaining_raw": raw,
                "subscription_credits": enrich.get("creditsSubscription"),
                "expiration": enrich.get("expiration")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}

# Coût en crédits par type d'action (waterfall : compté seulement si TROUVÉ).
#   find_phone = 50    → CONFIRMÉ user (2026-06-17 : « 1 numéro trouvé = 50 crédits »).
#   verify     = 0.25  → CONFIRMÉ user (2026-06-17 : « 0.25 crédit par vérification »).
#   Réconciliation : 1 find_phone (50) + 1 verify (0.25) = 50.25 → 1000-50.25 = 949.75 (affiché 950). ✓
#   find_email / ai_action → À CONFIRMER (valeurs provisoires).
COST = {"find_email": 1, "find_phone": 50, "verify": 0.25, "ai_action": 1}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict:
    if CREDITS_FILE.exists():
        try:
            return json.loads(CREDITS_FILE.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {"balance_set": None, "balance_set_at": None,
            "spent": {"find_email": 0, "find_phone": 0, "verify": 0, "ai_action": 0},
            "events": []}


def _save(d: dict) -> None:
    CREDITS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDITS_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2))


def set_balance(n: int, note: str = "") -> dict:
    """Resynchronise sur le solde réel lu dans le dashboard Emelia. Remet le spent à 0."""
    d = _load()
    d["balance_set"] = int(n)
    d["balance_set_at"] = _now()
    d["spent"] = {"find_email": 0, "find_phone": 0, "verify": 0, "ai_action": 0}
    d["events"].append({"ts": _now(), "type": "set", "value": int(n), "note": note})
    d["events"] = d["events"][-500:]
    _save(d)
    return status()


def record(kind: str, found: bool = True, note: str = "") -> None:
    """Enregistre une action Emelia. `found=False` (waterfall non facturé) → coût 0.
    Best-effort : n'interrompt jamais le flux d'enrichissement si l'écriture échoue."""
    try:
        if kind not in COST:
            return
        cost = COST[kind] if found else 0
        d = _load()
        d["spent"].setdefault(kind, 0)
        d["spent"][kind] += 1                  # nb d'appels (info)
        d.setdefault("charged", 0)
        d["charged"] += cost                   # crédits réellement débités
        d["events"].append({"ts": _now(), "type": kind, "found": bool(found),
                            "cost": cost, "note": note})
        d["events"] = d["events"][-500:]
        _save(d)
    except Exception:  # noqa: BLE001
        pass


def remaining() -> int | None:
    d = _load()
    if d.get("balance_set") is None:
        return None
    charged = d.get("charged")
    if charged is None:  # rétro-compat : dérive du spent si 'charged' absent
        sp = d.get("spent", {})
        charged = sum(COST.get(k, 0) * v for k, v in sp.items())
    return d["balance_set"] - charged


def status() -> dict:
    d = _load()
    charged = d.get("charged")
    if charged is None:
        sp = d.get("spent", {})
        charged = sum(COST.get(k, 0) * v for k, v in sp.items())
    live = fetch_live_balance()
    return {
        "live_balance": live.get("remaining") if live.get("ok") else None,
        "live_ok": live.get("ok"),
        "live_error": live.get("error"),
        "subscription_credits": live.get("subscription_credits") if live.get("ok") else None,
        "cost_per_action": COST,
        "local_charged_since_set": charged,
        "local_calls": d.get("spent", {}),
        "local_balance_set": d.get("balance_set"),
    }


def main():
    a = sys.argv[1:]
    if not a:
        print(json.dumps(status(), ensure_ascii=False, indent=2)); return
    cmd = a[0]
    if cmd == "balance":
        print(json.dumps(fetch_live_balance(), ensure_ascii=False, indent=2))
    elif cmd == "set" and len(a) >= 2:
        print(json.dumps(set_balance(int(a[1]), " ".join(a[2:])), ensure_ascii=False, indent=2))
    elif cmd == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    elif cmd == "record" and len(a) >= 2:
        record(a[1], found=("--notfound" not in a))
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    else:
        sys.exit("Usage: set <N> [note] | status | record <find_email|find_phone|verify> [--notfound]")


if __name__ == "__main__":
    main()
