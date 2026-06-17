#!/usr/bin/env python3
"""nightly_cleanup.py — nettoyage nocturne des emails NON VÉRIFIÉS du pool.

Pourquoi : le scraper insère dans le pool (`create_in_pool`) SANS validation mailnjoy
(intake brute), et le nettoyage n'était que manuel/ponctuel → backlog de contacts
`mailnjoy_check` NULL. Ce job draine ce backlog chaque nuit (re-valide, supprime les
invalides) via le pipeline existant `cleanup_backend.run_cleanup_drain` (chunks de 100,
verrou séquentiel, log `cleanup_drain`).

Lancé par PM2 cron `0 3 * * *` (`--no-autorestart`), en user autoblog.
Robustesse : retry si la DuckDB du pool est verrouillée (autoscrape/enrich en cours).
"""
import argparse
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

import cleanup_backend as cb

try:
    from autoscrape_backend import notify_telegram
except Exception:  # pragma: no cover
    def notify_telegram(_msg):  # type: ignore
        pass

SITES = ["lcr", "mkd"]
MAX_LOCK_RETRIES = 5
LOCK_WAIT_S = 30


def _drain_with_retry(site: str) -> dict:
    """run_cleanup_drain avec retry si la DB du pool est verrouillée (1 writer DuckDB)."""
    last_err = None
    for attempt in range(1, MAX_LOCK_RETRIES + 1):
        try:
            return cb.run_cleanup_drain(mode="unverified", site=site, source="cron-nightly")
        except Exception as e:  # noqa: BLE001
            last_err = e
            if "lock" in str(e).lower() and attempt < MAX_LOCK_RETRIES:
                print(f"[{site}] DB verrouillée (tentative {attempt}/{MAX_LOCK_RETRIES}), retry dans {LOCK_WAIT_S}s…", flush=True)
                time.sleep(LOCK_WAIT_S)
                continue
            raise
    raise last_err  # type: ignore


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", help="lcr|mkd (défaut: les deux)")
    args = ap.parse_args()
    sites = [args.site] if args.site else SITES

    before = cb.count_unverified()
    print(f"[nightly_cleanup] non-vérifiés avant: {before}", flush=True)

    problems = []
    for site in sites:
        try:
            res = _drain_with_retry(site)
            print(f"[{site}] {res}", flush=True)
            if res.get("errors"):
                problems.append(f"{site}: {res.get('errors')} erreurs")
        except Exception as e:  # noqa: BLE001
            print(f"[{site}] ÉCHEC: {e}", flush=True)
            problems.append(f"{site}: {e}")

    after = cb.count_unverified()
    print(f"[nightly_cleanup] non-vérifiés après: {after} (supprimés/validés: {before - after})", flush=True)

    if problems:
        notify_telegram("🧹 *Nettoyage nocturne* — incidents:\n" + "\n".join(problems) +
                        f"\nNon-vérifiés restants: {after}")


if __name__ == "__main__":
    main()
