#!/usr/bin/env python3
"""serper_solde.py — solde Serper toujours à jour + alerte de recharge (Camille, 05/10/2026).

Le solde qu'utilise la collecte (`memory/seo/serper-balance.json`) n'était rafraîchi QUE quand
quelqu'un ouvrait la page Scrapper : après une recharge, la collecte croyait encore être sous la
réserve et n'utilisait pas Serper. Ce script (cron toutes les 15 min) relit le solde live
(serper.dev /account), réécrit le fichier, et prévient sur Telegram quand le solde AUGMENTE
(= recharge, manuelle ou automatique).

Usage : python3 scripts/serper_solde.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))
FICHIER = BASE_DIR / "memory" / "seo" / "serper-balance.json"
SEUIL_RECHARGE = 1000      # en dessous, une hausse est du bruit, pas une recharge


def main() -> dict:
    import autoscrape_backend as asb
    from god_mode_agents import serper_balance
    b = serper_balance()
    if not b.get("ok") or b.get("balance") is None:
        return {"ok": False, "erreur": "solde Serper illisible", "detail": b}
    live = int(b["balance"])
    estime = asb.serper_available()          # ce que la collecte croyait avoir
    try:
        ancien = json.loads(FICHIER.read_text())
    except Exception:  # noqa: BLE001
        ancien = {}
    plafond = max(int(ancien.get("plan_total") or 0), live)
    FICHIER.write_text(json.dumps({
        "plan_total": plafond, "balance": live, "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "note": "Rafraîchi toutes les 15 min par scripts/serper_solde.py (solde live serper.dev /account)."},
        ensure_ascii=False, indent=2))
    out = {"ok": True, "solde": live, "estime_avant": estime}
    if estime is not None and live - estime >= SEUIL_RECHARGE:
        asb.notify_telegram(f"💳 Recharge Serper détectée : +{live - estime:,} crédits. "
                            f"Nouveau solde : {live:,} crédits — la collecte l'utilise dès maintenant.".replace(",", " "))
        out["recharge"] = live - estime
    return out


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False))
