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
import time
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
                        # Tombstone : les scrapers re-trouveront cet email dans leurs
                        # sources — sans mémoire du rejet on le ré-insère demain.
                        try:
                            import god_mode_backend as _gm
                            _gm.mark_email_rejected(email, v.get("decision") or "invalid",
                                                    v.get("reason") or "", site)
                        except Exception:
                            pass
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
                      progress_cb=None, should_stop=None, source: str = "manual",
                      max_seconds: float | None = None) -> dict:
    """Drain complet : enchaîne des chunks de `chunk_size` jusqu'à épuisement,
    atteinte de `total_limit`, ou stop demandé. Log final `cleanup_drain`.

    `max_seconds` borne la duree totale du drain. Sans borne, cette boucle garde le
    verrou d ecriture de contacts.duckdb - base a UN SEUL ecrivain - pendant toute la
    validation reseau : le 2026-09-21 le nettoyage nocturne l a tenu de 03:00 a 13:40,
    et tout le reste (pixel d ouverture, compteurs, pages contacts) est tombe en silence.
    Un drain qui n a pas fini rend la main et reprend au run suivant : le pool n est
    jamais perdu, il est seulement traite plus tard.

    progress_cb(cumulative, chunk_stats, chunk_processed, email) — appelé après
    chaque contact, avec :
      - cumulative : agrégats cross-chunks (chunks_done, total, valid, removed, ...)
      - chunk_stats : stats du chunk en cours (live)
      - chunk_processed : nb traités dans le chunk courant
      - email : dernier email traité
    """
    cum = {"chunks_done": 0, "total": 0, "valid": 0, "removed": 0,
           "skipped": 0, "errors": 0, "drained": False, "stopped": False,
           "timed_out": False, "source": source}
    _debut = time.monotonic()

    def _chunk_progress(chunk_stats, processed, email):
        if progress_cb:
            try: progress_cb(cum, chunk_stats, processed, email)
            except Exception: pass

    while True:
        if max_seconds is not None and (time.monotonic() - _debut) >= max_seconds:
            # Budget epuise : on sort AVANT d ouvrir un nouveau chunk, donc sans couper
            # un contact en cours de traitement. Le reliquat part au run suivant.
            cum["timed_out"] = True
            break
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


# ── Lot 2 (07/10) : le pool est dans PostgreSQL ────────────────────────────────
# Mêmes fonctions, mêmes retours. Une différence voulue : une adresse invalide n'est plus
# SUPPRIMÉE mais marquée « ko » (décision du 20/08 : on garde la mémoire d'avoir écarté
# quelqu'un, sinon on le re-scrape trois semaines plus tard). Le tombstone est posé aussi.
def _pool_pg() -> bool:
    try:
        import pool_ecriture_pg
        return pool_ecriture_pg.actif()
    except Exception:  # noqa: BLE001
        return False


def _q(sql, params=None):
    import pool_pg
    return pool_pg._q(sql, params or {})


_NON_BL = "NOT COALESCE(global_blacklisted, false)"


def _pg_count_unverified() -> int:
    return int(_q(f"SELECT count(*) FROM contacts WHERE mailnjoy_decision IS NULL AND {_NON_BL}")[0][0])


def _pg_count_stale(days: int = 180) -> int:
    return int(_q(f"""SELECT count(*) FROM contacts WHERE mailnjoy_checked_at IS NOT NULL
                      AND mailnjoy_checked_at < now() - make_interval(days => %(d)s)
                      AND {_NON_BL}""", {"d": int(days)})[0][0])


def _pg_list_pool(limit: int = 500) -> list[dict]:
    rows = _q(f"""SELECT id::text, email::text, societe, COALESCE(primary_source, ''),
                         created_at, mailnjoy_check, COALESCE(global_blacklisted, false)
                  FROM contacts ORDER BY created_at DESC NULLS LAST LIMIT %(n)s""",
              {"n": int(limit)})
    return [{"id": r[0], "email": r[1], "societe": r[2] or "", "source": r[3] or "",
             "created_at": str(r[4]) if r[4] else "", "mailnjoy_check": _parse_mn(r[5]),
             "blacklisted": bool(r[6])} for r in rows]


def _pg_list_for_cleanup(mode: str, days: int = 180, limit: int = 200) -> list[dict]:
    if mode == "unverified":
        cond = "mailnjoy_decision IS NULL"
    elif mode == "error":
        cond = "mailnjoy_decision IS NOT NULL AND mailnjoy_decision <> 'valid'"
    else:
        cond = ("mailnjoy_checked_at IS NOT NULL "
                "AND mailnjoy_checked_at < now() - make_interval(days => %(d)s)")
    rows = _q(f"SELECT id::text, email::text FROM contacts WHERE {cond} AND {_NON_BL} "
              f"AND NOT est_test LIMIT %(n)s", {"d": int(days), "n": int(limit)})
    return [{"id": r[0], "email": r[1]} for r in rows]


def _pg_run_cleanup(mode: str, site: str = "lcr", days: int = 180, limit: int = 200,
                    progress_cb=None, should_stop=None, source: str = "manual") -> dict:
    from acquisition_backend import _validate_address  # type: ignore
    import acq_pg
    import god_mode_backend as _gm
    targets = _pg_list_for_cleanup(mode=mode, days=days, limit=limit)
    stats = {"mode": mode, "total": len(targets), "valid": 0, "removed": 0, "skipped": 0,
             "errors": 0, "stopped": False, "source": source}

    def _emit(processed, email):
        if progress_cb:
            try:
                progress_cb(stats, processed, email)
            except Exception:  # noqa: BLE001
                pass

    _emit(0, None)
    for i, t in enumerate(targets, start=1):
        if should_stop and should_stop():
            stats["stopped"] = True
            break
        email = t["email"]
        try:
            try:
                v = _validate_address(email)
            except Exception as e:  # noqa: BLE001
                stats["errors"] += 1
                _log(site, "cleanup_error", email, {"mode": mode, "err": str(e)}, False, str(e))
                continue
            if not v.get("ok"):
                # Marquée « ko » (via le tombstone → pg_sync.sync_rejet), jamais supprimée.
                _gm.mark_email_rejected(email, v.get("decision") or "invalid",
                                        v.get("reason") or "", site)
                if v.get("mailnjoy_check"):
                    acq_pg.appliquer_verdict(email, v["mailnjoy_check"])
                stats["removed"] += 1
                _log(site, "cleanup_removed", email,
                     {"mode": mode, "decision": v.get("decision"), "reason": v.get("reason"),
                      "marque_ko": True}, True)
                continue
            mnc = v.get("mailnjoy_check")
            if mnc is None:
                stats["skipped"] += 1
                continue
            acq_pg.appliquer_verdict(email, mnc)
            stats["valid"] += 1
            _log(site, "cleanup_validated", email,
                 {"mode": mode, "result": mnc.get("result"), "decision": mnc.get("decision")}, True)
        except Exception as e:  # noqa: BLE001
            stats["errors"] += 1
            _log(site, "cleanup_error", email, {"err": str(e)}, False, str(e))
        finally:
            _emit(i, email)
    _log(site, "cleanup_batch", "-", stats, True)
    return stats


def _bascule(nom: str, version_pg):
    origine = globals()[nom]

    def f(*a, **k):
        return version_pg(*a, **k) if _pool_pg() else origine(*a, **k)
    f.__name__, f.__doc__ = nom, origine.__doc__
    return f


for _n, _v in (("count_unverified", _pg_count_unverified), ("count_stale", _pg_count_stale),
               ("list_pool", _pg_list_pool), ("list_for_cleanup", _pg_list_for_cleanup),
               ("run_cleanup", _pg_run_cleanup)):
    globals()[_n] = _bascule(_n, _v)
