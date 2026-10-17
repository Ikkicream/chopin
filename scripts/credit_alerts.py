#!/usr/bin/env python3
"""credit_alerts.py — Alerte Telegram quand les crédits d'envoi sont bas/épuisés.

Surveille les soldes LIVE des fournisseurs du pipeline d'envoi :
  - Emelia   : crédits d'envoi/enrichissement (emelia_credits.fetch_live_balance)
  - Mailnjoy : crédits de vérification (mailnjoy_check.get_credit) — requis avant tout envoi

Deux niveaux : 'low' (avertissement préventif) et 'empty' (panne sèche). Anti-spam :
on n'alerte qu'au FRANCHISSEMENT d'un palier (état mémorisé dans memory/credit_alerts.json),
et on réarme quand le solde repasse au-dessus du seuil bas (recharge détectée).

Branché sur le dispatch de campagnes (campaign_engine.dispatch_due + send-now). Réutilise
le canal Telegram déjà câblé (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).

CLI :
  python3 scripts/credit_alerts.py            # check + alerte si palier franchi
  python3 scripts/credit_alerts.py --force    # force l'envoi de l'état courant (test)
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = BASE_DIR / "memory" / "credit_alerts.json"

# --- chargement .env (token Telegram + clés fournisseurs) ---
_envf = BASE_DIR / ".env"
if _envf.exists():
    for _l in _envf.read_text().splitlines():
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _v = _l.split("=", 1)
            os.environ.setdefault(_k, _v.strip("'\""))

# Seuil bas par fournisseur (au-dessous → alerte 'low', à 0 → alerte 'empty').
THRESHOLDS = {
    "emelia":   {"low": 50,  "label": "Emelia (crédits envoi/enrichissement)"},
    "mailnjoy": {"low": 100, "label": "Mailnjoy (crédits de vérification)"},
}
_RANK = {"ok": 0, "low": 1, "empty": 2}


def _send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    try:
        data = urllib.parse.urlencode(
            {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        ).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=6, context=ctx):
            return True
    except Exception:  # noqa: BLE001
        return False


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {}


def _save_state(d: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    except Exception:  # noqa: BLE001
        pass


def _read_balances() -> dict:
    """Soldes LIVE par fournisseur. None = illisible (on n'alerte alors PAS)."""
    out: dict = {}
    try:
        import emelia_credits
        live = emelia_credits.fetch_live_balance()
        out["emelia"] = live.get("remaining") if live.get("ok") else None
    except Exception:  # noqa: BLE001
        out["emelia"] = None
    try:
        import mailnjoy_check
        configured = getattr(mailnjoy_check, "is_configured", lambda: True)()
        out["mailnjoy"] = mailnjoy_check.get_credit() if configured else None
    except Exception:  # noqa: BLE001
        out["mailnjoy"] = None
    return out


def _level(balance, low: int) -> str:
    if balance is None:
        return "unknown"
    if balance <= 0:
        return "empty"
    if balance < low:
        return "low"
    return "ok"


def check_and_alert(force: bool = False) -> dict:
    """Lit les soldes et alerte Telegram au franchissement d'un palier. Best-effort.

    Retourne {provider: {balance, level, alerted}}. N'alerte que si le niveau s'aggrave
    (ok→low, ok→empty, low→empty) ou si `force=True`. Un retour à 'ok' réarme l'alerte.
    """
    state = _load_state()
    balances = _read_balances()
    result: dict = {}
    for prov, cfg in THRESHOLDS.items():
        bal = balances.get(prov)
        lvl = _level(bal, cfg["low"])
        result[prov] = {"balance": bal, "level": lvl, "alerted": False}
        if lvl == "unknown":
            continue  # solde illisible : on ne touche ni l'état ni l'alerte
        if lvl == "ok":
            state.pop(prov, None)  # réarme : ré-alerte au prochain creux
            continue
        prev = state.get(prov, "ok")
        if force or _RANK.get(lvl, 0) > _RANK.get(prev, 0):
            if lvl == "empty":
                msg = (f"🛑 *Crédits épuisés — {cfg['label']}*\n"
                       f"Solde : *{bal}*. Les envois sont bloqués tant que tu ne recharges pas.")
            else:
                msg = (f"⚠️ *Crédits bas — {cfg['label']}*\n"
                       f"Solde : *{bal}* (seuil {cfg['low']}). Recharge avant la panne sèche.")
            if _send_telegram(msg):
                result[prov]["alerted"] = True
        state[prov] = lvl
    _save_state(state)
    return result


if __name__ == "__main__":
    print(json.dumps(check_and_alert(force="--force" in sys.argv[1:]),
                     ensure_ascii=False, indent=2))
