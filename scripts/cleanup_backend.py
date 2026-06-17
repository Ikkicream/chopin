"""Module de nettoyage Mailnjoy — opère sur le POOL `contacts.duckdb` (table `contacts`).

C'est la vraie base unifiée (~5000+ contacts du scraper + imports). La table per-site
`acquisition_contacts` ne contient que les contacts du funnel (cold_email/lead/prm/crm).

Fonctions :
- count_unverified()                : contacts du pool sans mailnjoy_check
- count_stale(days=180)              : contacts vérifiés > N jours
- list_pool(limit=500)               : liste pour la table UI
- list_for_cleanup(mode, limit)      : liste à traiter
- run_cleanup(mode, limit)           : valide + supprime invalid + log dans god_mode_logs

Les contacts globaux blacklisted sont exclus de tous les traitements.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
POOL_DB = BASE_DIR / "data" / "contacts.duckdb"
sys.path.insert(0, str(BASE_DIR / "scripts"))


def _pool(read_only: bool = False):
    return duckdb.connect(str(POOL_DB), read_only=read_only)


def _log(site: str, action: str, email: str, payload: dict, success: bool, error: str | None = None) -> None:
    try:
        import god_mode_backend as gm
        gm.log_action(site, "system", "cleanup", action, resource="email", resource_id=email,
                      payload=payload, success=success, error=error)
    except Exception:
        pass


def _parse_mn(mn) -> dict | None:
    if mn is None:
        return None
    if isinstance(mn, str):
        s = mn.strip()
        if not s:
            return None
        try:
            d = json.loads(s)
        except Exception:
            return None
        return d if isinstance(d, dict) and d else None
    if isinstance(mn, dict) and mn:
        return mn
    return None


# ── COUNTS ────────────────────────────────────────────────────────────────────
def count_unverified() -> int:
    c = _pool(read_only=True)
    try:
        return c.execute(
            "SELECT COUNT(*) FROM contacts "
            "WHERE (mailnjoy_check IS NULL OR LENGTH(mailnjoy_check) = 0) "
            "AND (global_blacklisted IS NULL OR global_blacklisted = FALSE)"
        ).fetchone()[0]
    finally:
        c.close()


def count_stale(days: int = 180) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    c = _pool(read_only=True)
    try:
        rows = c.execute(
            "SELECT mailnjoy_check FROM contacts "
            "WHERE mailnjoy_check IS NOT NULL AND LENGTH(mailnjoy_check) > 0 "
            "AND (global_blacklisted IS NULL OR global_blacklisted = FALSE)"
        ).fetchall()
    finally:
        c.close()
    n = 0
    for (mn,) in rows:
        d = _parse_mn(mn)
        ts = d.get("checked_at") if d else None
        if ts and ts < cutoff:
            n += 1
    return n


# ── LIST POOL (pour la page Cleanup) ──────────────────────────────────────────
def list_pool(limit: int = 500) -> list[dict]:
    """Renvoie un échantillon des contacts du pool pour l'UI cleanup."""
    c = _pool(read_only=True)
    try:
        rows = c.execute(
            "SELECT id, email, societe, COALESCE(primary_source, '') AS source, "
            "       created_at, mailnjoy_check, "
            "       COALESCE(global_blacklisted, FALSE) AS blacklisted "
            "FROM contacts "
            "ORDER BY created_at DESC NULLS LAST "
            "LIMIT ?", [limit]
        ).fetchall()
    finally:
        c.close()
    return [{
        "id": r[0], "email": r[1], "societe": r[2] or "", "source": r[3] or "",
        "created_at": str(r[4]) if r[4] else "",
        "mailnjoy_check": _parse_mn(r[5]),
        "blacklisted": bool(r[6]),
    } for r in rows]


# ── ACTIONS ───────────────────────────────────────────────────────────────────
def list_for_cleanup(mode: str, days: int = 180, limit: int = 200) -> list[dict]:
    c = _pool(read_only=True)
    try:
        if mode == "unverified":
            rows = c.execute(
                "SELECT id, email FROM contacts "
                "WHERE (mailnjoy_check IS NULL OR LENGTH(mailnjoy_check) = 0) "
                "AND (global_blacklisted IS NULL OR global_blacklisted = FALSE) "
                "LIMIT ?", [limit]
            ).fetchall()
            return [{"id": r[0], "email": r[1]} for r in rows]
        if mode == "error":
            # Check Mailnjoy avec décision != valid (souvent erreur transitoire) -> re-valide.
            rows = c.execute(
                "SELECT id, email FROM contacts "
                "WHERE mailnjoy_check IS NOT NULL AND LENGTH(mailnjoy_check) > 0 "
                "AND COALESCE(json_extract_string(mailnjoy_check, '$.decision'), '') <> 'valid' "
                "AND (global_blacklisted IS NULL OR global_blacklisted = FALSE) "
                "LIMIT ?", [limit]
            ).fetchall()
            return [{"id": r[0], "email": r[1]} for r in rows]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = c.execute(
            "SELECT id, email, mailnjoy_check FROM contacts "
            "WHERE mailnjoy_check IS NOT NULL AND LENGTH(mailnjoy_check) > 0 "
            "AND (global_blacklisted IS NULL OR global_blacklisted = FALSE)"
        ).fetchall()
    finally:
        c.close()
    out: list[dict] = []
    for (cid, email, mn) in rows:
        d = _parse_mn(mn)
        ts = d.get("checked_at") if d else None
        if ts and ts < cutoff:
            out.append({"id": cid, "email": email})
            if len(out) >= limit:
                break
    return out


def run_cleanup(mode: str, site: str = "lcr", days: int = 180, limit: int = 200,
                progress_cb=None, should_stop=None, source: str = "manual") -> dict:
    """Re-valide + supprime du pool si invalid/risky.
    progress_cb(stats, processed, email) appelé après chaque contact (best-effort).
    should_stop() callable → si retourne True, arrête proprement (stats["stopped"]=True).
    source : 'manual' (UI) | 'auto-scrape' (déclenché en fin de scrape) — tracé dans le log."""
    from acquisition_backend import _validate_address  # type: ignore
    targets = list_for_cleanup(mode=mode, days=days, limit=limit)
    stats = {"mode": mode, "total": len(targets), "valid": 0, "removed": 0, "skipped": 0, "errors": 0, "stopped": False, "source": source}

    def _emit(processed: int, email):
        if progress_cb:
            try: progress_cb(stats, processed, email)
            except Exception: pass

    _emit(0, None)
    if not targets:
        return stats

    c = _pool(read_only=False)
    try:
        for i, t in enumerate(targets, start=1):
            if should_stop and should_stop():
                stats["stopped"] = True
                break
            email = t["email"]; cid = t["id"]
            try:
                try:
                    v = _validate_address(email)
                except Exception as e:  # noqa: BLE001
                    stats["errors"] += 1
                    _log(site, "cleanup_error", email, {"mode": mode, "err": str(e)}, False, str(e))
                    continue
                if not v.get("ok"):
                    try:
                        # Cascade : on supprime aussi l'historique pour ne pas laisser
                        # d'orphelins (qui gonflaient le « Tous » de l'UI).
                        c.execute("DELETE FROM contact_site_history WHERE contact_id = ?", [cid])
                        c.execute("DELETE FROM contacts WHERE id = ?", [cid])
                        stats["removed"] += 1
                        _log(site, "cleanup_removed", email,
                             {"mode": mode, "decision": v.get("decision"), "reason": v.get("reason")}, True)
                    except Exception as e:  # noqa: BLE001
                        stats["errors"] += 1
                        _log(site, "cleanup_error", email, {"err": str(e)}, False, str(e))
                    continue
                mnc = v.get("mailnjoy_check")
                if mnc is None:
                    stats["skipped"] += 1
                    continue
                try:
                    c.execute(
                        "UPDATE contacts SET mailnjoy_check = ?, updated_at = ? WHERE id = ?",
                        [json.dumps(mnc), datetime.now(timezone.utc), cid],
                    )
                    stats["valid"] += 1
                    _log(site, "cleanup_validated", email,
                         {"mode": mode, "result": mnc.get("result"), "decision": mnc.get("decision")}, True)
                except Exception as e:  # noqa: BLE001
                    stats["errors"] += 1
                    _log(site, "cleanup_error", email, {"err": str(e)}, False, str(e))
            finally:
                _emit(i, email)
    finally:
        c.close()
    _log(site, "cleanup_batch", "-", stats, True)
    return stats


def run_cleanup_drain(mode: str, site: str = "lcr", days: int = 180,
                      chunk_size: int = 100, total_limit=None,
                      progress_cb=None, should_stop=None, source: str = "manual") -> dict:
    """Drain complet : enchaîne des chunks de `chunk_size` jusqu'à épuisement,
    atteinte de `total_limit`, ou stop demandé. Log final `cleanup_drain`.

    progress_cb(cumulative, chunk_stats, chunk_processed, email) — appelé après
    chaque contact, avec :
      - cumulative : agrégats cross-chunks (chunks_done, total, valid, removed, ...)
      - chunk_stats : stats du chunk en cours (live)
      - chunk_processed : nb traités dans le chunk courant
      - email : dernier email traité
    """
    cum = {"chunks_done": 0, "total": 0, "valid": 0, "removed": 0,
           "skipped": 0, "errors": 0, "drained": False, "stopped": False, "source": source}

    def _chunk_progress(chunk_stats, processed, email):
        if progress_cb:
            try: progress_cb(cum, chunk_stats, processed, email)
            except Exception: pass

    while True:
        if should_stop and should_stop():
            cum["stopped"] = True
            break
        if total_limit is not None and cum["total"] >= total_limit:
            break
        remaining = (total_limit - cum["total"]) if total_limit is not None else chunk_size
        nb = min(chunk_size, remaining)
        cs = run_cleanup(mode=mode, site=site, days=days, limit=nb,
                         progress_cb=_chunk_progress, should_stop=should_stop, source=source)
        cum["chunks_done"] += 1
        for k in ("total", "valid", "removed", "skipped", "errors"):
            cum[k] += cs.get(k, 0)
        if cs.get("stopped"):
            cum["stopped"] = True
            break
        if cs.get("total", 0) < nb:
            # pool épuisé pour ce mode
            cum["drained"] = True
            break

    _log(site, "cleanup_drain", "-", cum, True)
    return cum
