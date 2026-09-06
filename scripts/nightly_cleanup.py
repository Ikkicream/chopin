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


def _retry_lock(fn, label: str):
    """Exécute fn() avec retry si la pool DuckDB est verrouillée (1 seul writer DuckDB).

    Couvre AUSSI count_unverified() (lecture), qui s'exécute avant le drain : sans ça
    un verrou à l'heure du job faisait tout planter (cf. crash 2026-06-21)."""
    last_err = None
    for attempt in range(1, MAX_LOCK_RETRIES + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last_err = e
            if "lock" in str(e).lower() and attempt < MAX_LOCK_RETRIES:
                print(f"[{label}] DB verrouillée (tentative {attempt}/{MAX_LOCK_RETRIES}), retry dans {LOCK_WAIT_S}s…", flush=True)
                time.sleep(LOCK_WAIT_S)
                continue
            raise
    raise last_err  # type: ignore


def _drain_with_retry(site: str) -> dict:
    """run_cleanup_drain avec retry si la DB du pool est verrouillée (1 writer DuckDB)."""
    return _retry_lock(
        lambda: cb.run_cleanup_drain(mode="unverified", site=site, source="cron-nightly"),
        site,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", help="lcr|mkd (défaut: les deux)")
    args = ap.parse_args()
    sites = [args.site] if args.site else SITES

    before = _retry_lock(cb.count_unverified, "count-before")
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

    after = _retry_lock(cb.count_unverified, "count-after")
    print(f"[nightly_cleanup] non-vérifiés après: {after} (supprimés/validés: {before - after})", flush=True)

    if problems:
        notify_telegram("🧹 *Nettoyage nocturne* — incidents:\n" + "\n".join(problems) +
                        f"\nNon-vérifiés restants: {after}")


if __name__ == "__main__":
    # Un verrou pool persistant = un AUTRE nettoyage tient déjà la DB (cleanup manuelle
    # via l'API, enrich, import…). À fréquence horaire ces collisions sont attendues :
    # on sort proprement (exit 0, pas de traceback ni d'alerte) — le run suivant reprendra.
    try:
        main()
    except Exception as e:  # noqa: BLE001
        if "lock" in str(e).lower():
            print(f"[nightly_cleanup] SKIP — pool occupé par un autre nettoyage "
                  f"({e.__class__.__name__}); le prochain run horaire reprendra.", flush=True)
            sys.exit(0)
        raise
