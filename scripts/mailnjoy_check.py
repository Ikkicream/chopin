#!/usr/bin/env python3
"""
mailnjoy_check.py — Vérification de délivrabilité via Mailnjoy /v2/unitary.

Pipeline : scrape → validator → scrappe_pending → Mailnjoy → scrappe ou DELETE.

Spec : mailnjoy-api-reference.md + mailnjoy-integration-prompt.md (PAPERCLIP).

Décisions activées (selon décisions user 2026-05-22) :
  - mailnjoy_valid → INSERT scrappe, DELETE pending
  - mailnjoy_risky → DELETE pending (kill, jamais en scrappe — décision 1.b)
  - mailnjoy_invalid → DELETE pending (kill)
  - mailnjoy_error (500/network) → laisse en pending pour retry
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
DELETIONS_LOG = LOG_DIR / "mailnjoy_deletions.log"

API_BASE = "https://api.mailnjoy.com"
UNITARY_URL = f"{API_BASE}/v2/unitary"
CREDIT_URL = f"{API_BASE}/v1/credit"


def _load_env_var(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    if v:
        return v
    env_f = BASE_DIR / ".env"
    if env_f.exists():
        for ln in env_f.read_text().splitlines():
            ln = ln.strip()
            if ln.startswith(f"{key}=") and not ln.startswith("#"):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return default


def _headers() -> dict:
    return {
        "mailnjoy-id":     _load_env_var("MAILNJOY_ID"),
        "mailnjoy-secret": _load_env_var("MAILNJOY_SECRET"),
        "Content-Type":    "text/plain",
    }


def _log_deletion(email: str, decision: str, mn_result: dict, reason: str) -> None:
    # Unwrap Mailnjoy v2 (wrapped in unitaryCheck)
    payload = mn_result.get("unitaryCheck") if isinstance(mn_result, dict) and "unitaryCheck" in mn_result else (mn_result or {})
    line = json.dumps({
        "ts":       datetime.now(timezone.utc).isoformat(),
        "email":    email,
        "decision": decision,
        "status":   payload.get("status"),
        "category": payload.get("category"),
        "reason":   reason,
    }, ensure_ascii=False)
    with open(DELETIONS_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _delete_unverified_pool_copy(email: str) -> None:
    """Supprime du pool (contacts.duckdb) la copie NON VÉRIFIÉE d'un email tué au drain.

    Le scrape fait un dual-write pending + pool ; quand le drain tue le pending,
    la copie pool restait « unverified » et le cleanup nocturne re-payait un crédit
    Mailnjoy pour la re-checker. On ne touche jamais à un contact déjà vérifié ou
    blacklisted."""
    if not email:
        return
    try:
        import duckdb
        c = duckdb.connect(str(BASE_DIR / "data" / "contacts.duckdb"))
        try:
            rows = c.execute(
                "SELECT id FROM contacts WHERE lower(email) = ? "
                "AND (mailnjoy_check IS NULL OR LENGTH(mailnjoy_check) = 0) "
                "AND (global_blacklisted IS NULL OR global_blacklisted = FALSE)",
                [email.strip().lower()]).fetchall()
            for (cid,) in rows:
                c.execute("DELETE FROM contact_site_history WHERE contact_id = ?", [cid])
                c.execute("DELETE FROM contacts WHERE id = ?", [cid])
        finally:
            c.close()
    except Exception:
        pass


def is_configured() -> bool:
    """True si les credentials Mailnjoy sont remplis dans .env."""
    return bool(_load_env_var("MAILNJOY_ID")) and bool(_load_env_var("MAILNJOY_SECRET"))


def get_credit() -> int | None:
    """Récupère le solde de crédit. None si pas configuré ou erreur."""
    if not is_configured():
        return None
    try:
        r = requests.get(CREDIT_URL, headers={
            "mailnjoy-id":     _load_env_var("MAILNJOY_ID"),
            "mailnjoy-secret": _load_env_var("MAILNJOY_SECRET"),
        }, timeout=10)
        if r.status_code == 200:
            return int(r.text.strip())
    except Exception:
        pass
    return None


def check_email_mailnjoy(email: str, retry: int = 5) -> dict:
    """Appel /v2/unitary?type=simple avec backoff exponentiel sur 429/503/500.

    Returns: {ok, decision, raw, status_code, error}
      decision ∈ {valid, risky, invalid, error, config_missing, credit_exhausted}
    """
    if not is_configured():
        return {"ok": False, "decision": "config_missing", "raw": None,
                "status_code": 0, "error": "MAILNJOY_ID/SECRET manquants dans .env"}

    backoff = 1.0
    last_err = ""
    for attempt in range(retry):
        try:
            r = requests.post(
                f"{UNITARY_URL}?type=simple",
                data=email,
                headers=_headers(),
                timeout=30,
            )
            sc = r.status_code

            if sc == 200:
                raw = r.json()
                return {"ok": True, "decision": classify_response(raw),
                        "raw": raw, "status_code": 200, "error": None}

            if sc == 401:
                # Peut être : credentials invalides OU clé read-only sans permission de dépenser
                body = (r.text or "").strip()
                err = body[:200] if body else "Auth échouée"
                return {"ok": False, "decision": "config_missing", "raw": None,
                        "status_code": 401, "error": f"401 Mailnjoy : {err}"}

            if sc == 403:
                return {"ok": False, "decision": "credit_exhausted", "raw": None,
                        "status_code": 403, "error": "Crédit Mailnjoy insuffisant"}

            if sc == 400:
                # Email mal formé côté Mailnjoy → équivalent à invalid
                return {"ok": True, "decision": "invalid", "raw": None,
                        "status_code": 400, "error": "Email malformé"}

            if sc in (429, 503):
                wait = r.headers.get("Retry-After")
                sleep_for = float(wait) if wait else backoff
                time.sleep(min(sleep_for, 30))
                backoff = min(backoff * 2, 30)
                last_err = f"http_{sc}"
                continue

            if sc == 500:
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                last_err = "http_500"
                continue

            last_err = f"http_{sc}: {r.text[:100]}"

        except requests.exceptions.RequestException as e:
            last_err = f"network: {e}"
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)

    return {"ok": False, "decision": "error", "raw": None,
            "status_code": 0, "error": last_err or "max_retries"}


def classify_response(raw: dict) -> str:
    """Mappe la réponse Mailnjoy → 'valid' | 'risky' | 'invalid'.
    La réponse v2 est wrappée dans {"unitaryCheck": {...}} — on unwrap si présent.
    """
    payload = raw.get("unitaryCheck") if isinstance(raw, dict) and "unitaryCheck" in raw else raw
    status = (payload.get("status") or "").upper()
    category = (payload.get("category") or "").upper()
    attrs = payload.get("attributs", {}) or {}

    def attr(name: str) -> bool:
        a = attrs.get(name, {})
        return bool(a.get("value")) if isinstance(a, dict) else bool(a)

    # INVALID (kill)
    if status in ("INVALID", "INCORRECT", "SUSPECT", "FULL"):
        return "invalid"
    if category == "UNSAFE":
        return "invalid"
    if attr("spamtrap") or attr("disposable"):
        return "invalid"

    # RISKY (kill aussi selon décision user 2026-05-22)
    if category == "RISKY":
        return "risky"
    if attr("catchall") or attr("role") or attr("suspect"):
        return "risky"

    # VALID
    if status == "VALID" and category in ("VERY_SAFE", "SAFE"):
        return "valid"

    # Cas non couverts → on est prudent
    return "risky"


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline drain : appelle Mailnjoy pour tout ce qui est en scrappe_pending
# ──────────────────────────────────────────────────────────────────────────────
def check_pending_queue(site_code: str | None = None, delay_ms: int = 200, max_rows: int = 200) -> dict:
    """Draine la table scrappe_pending pour un site (ou tous).

    Pour chaque pending row :
      - Appelle Mailnjoy
      - Si valid → move_pending_to_scrappe + supprime du pending
      - Si risky/invalid → DELETE pending + log
      - Si error → laisse en pending (mailnjoy_attempts incrémenté)

    Returns: {valid, risky, invalid, errored, skipped, total, credit_left}
    """
    # Lazy imports pour éviter circular
    import sys
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import god_mode_backend as gm

    stats = {"valid": 0, "risky": 0, "invalid": 0, "errored": 0, "skipped": 0, "total": 0}

    if not is_configured():
        stats["error"] = "Mailnjoy non configuré (MAILNJOY_ID/SECRET vides dans .env)"
        return stats

    # Garde-fou crédit (alerte si bas)
    credit = get_credit()
    stats["credit_left"] = credit
    if credit is not None and credit < 100:
        stats["error"] = f"Crédit Mailnjoy bas ({credit}) — abort"
        return stats

    pending = gm.list_pending(site_code=site_code, limit=max_rows)
    stats["total"] = len(pending)

    for row in pending:
        pid = row["id"]
        email = row["email"]

        # Email déjà rejeté par le passé (tombstone) → on ne re-dépense PAS un
        # crédit Mailnjoy : suppression directe du pending + de la copie pool.
        try:
            if gm.email_rejected(email):
                gm.delete_pending(pid)
                _delete_unverified_pool_copy(email)
                stats["skipped"] += 1
                continue
        except Exception:
            pass

        result = check_email_mailnjoy(email)

        # Crédit épuisé ou config foireuse : arrêt immédiat
        if result["decision"] in ("credit_exhausted", "config_missing"):
            stats["error"] = result["error"]
            break

        # Persiste l'info dans le row pending (utile en cas d'erreur ou de move)
        # Unwrap payload Mailnjoy v2 (wrapped dans unitaryCheck)
        _raw = result.get("raw") or {}
        _payload = _raw.get("unitaryCheck") if isinstance(_raw, dict) and "unitaryCheck" in _raw else _raw
        mn_check = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "result":     f"{_payload.get('status', '?')}/{_payload.get('category', '?')}" if _payload else None,
            "decision":   result["decision"],
            "raw_id":     _payload.get("userId") or _payload.get("id"),
        }

        # Log dans god_mode_logs (visible /admin/logs)
        try:
            gm.log_action(row.get("site_code") or "lcr", "system", "drain", "mailnjoy_check",
                          resource="email", resource_id=email,
                          payload={"decision": result["decision"], "result": mn_check.get("result")},
                          success=result["decision"] == "valid",
                          error=result["decision"] if result["decision"] != "valid" else None)
        except Exception:
            pass
        if result["decision"] == "valid":
            gm.move_pending_to_scrappe(pid, mn_check=mn_check)
            stats["valid"] += 1
        elif result["decision"] == "risky":
            _log_deletion(email, "risky", result.get("raw") or {}, "kill par décision user 2026-05-22")
            gm.delete_pending(pid)
            gm.mark_email_rejected(email, "risky", mn_check.get("result") or "",
                                   row.get("site_code") or "")
            _delete_unverified_pool_copy(email)
            stats["risky"] += 1
        elif result["decision"] == "invalid":
            _log_deletion(email, "invalid", result.get("raw") or {}, "mailnjoy invalid")
            gm.delete_pending(pid)
            gm.mark_email_rejected(email, "invalid", mn_check.get("result") or "",
                                   row.get("site_code") or "")
            _delete_unverified_pool_copy(email)
            stats["invalid"] += 1
        else:  # error
            gm.bump_pending_error(pid, result.get("error") or "unknown")
            stats["errored"] += 1

        time.sleep(delay_ms / 1000.0)

    return stats


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "credit":
        c = get_credit()
        print(f"Crédit Mailnjoy : {c}" if c is not None else "Non configuré ou erreur")
    elif len(sys.argv) > 1 and sys.argv[1] == "drain":
        site = sys.argv[2] if len(sys.argv) > 2 else None
        print(json.dumps(check_pending_queue(site_code=site), indent=2))
    elif len(sys.argv) > 1:
        email = sys.argv[1]
        print(json.dumps(check_email_mailnjoy(email), indent=2))
    else:
        print("Usage:")
        print("  python3 mailnjoy_check.py credit                     → solde")
        print("  python3 mailnjoy_check.py drain [lcr|mkd]            → draine pending")
        print("  python3 mailnjoy_check.py user@example.com           → check unitaire")
