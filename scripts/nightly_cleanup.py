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
import os
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

import cleanup_backend as cb

try:
    from autoscrape_backend import notify_telegram
except Exception:  # pragma: no cover
    def notify_telegram(_msg):  # type: ignore
        pass

MSG_INCIDENT = "\U0001f9f9 *Nettoyage nocturne* - incidents:\n"
MSG_BUDGET = ("\U0001f9f9 *Nettoyage nocturne* - budget epuise sur {sites} "
              "apres {budget} min. Verrou rendu, {reste} non-verifies en attente.")

SITES = ["lcr", "mkd"]
MAX_LOCK_RETRIES = 5
LOCK_WAIT_S = 30

# Budget de temps par site. Le drain garde le verrou d ecriture de contacts.duckdb -
# base a UN SEUL ecrivain - pendant toute sa validation reseau. Sans borne, le run du
# 2026-09-21 l a tenu de 03:00 a 13:40 : le pixel d ouverture a perdu une journee
# entiere d ouvertures en silence, et les pages contacts etaient aveugles.
# 45 min par site = tout est rendu avant 04:30, donc bien avant la chaine de 06:30 et
# la fenetre d envoi de 08:00. Le reliquat repart la nuit suivante.
DRAIN_BUDGET_S = float(os.environ.get("NIGHTLY_CLEANUP_BUDGET_S", 45 * 60))

# Fenetre autorisee (heure locale). Ce job prend le verrou d ecriture du pool : hors
# de la nuit, le prendre aveugle le pixel d ouverture, les compteurs et les pages
# contacts. La fenetre ferme AVANT la chaine de 06:30 et bien avant les envois de 08:00.
# Elle protege aussi des demarrages accidentels : un `pm2 start` en pleine journee
# relance ce script immediatement - c est exactement ce qui pendait au nez le 21/09.
FENETRE_DEBUT, FENETRE_FIN = 2, 6


def dans_la_fenetre() -> tuple[bool, str]:
    h = datetime.now().hour
    if FENETRE_DEBUT <= h < FENETRE_FIN:
        return True, f"{h}h - dans la fenetre {FENETRE_DEBUT}h-{FENETRE_FIN}h"
    return False, f"{h}h - hors fenetre {FENETRE_DEBUT}h-{FENETRE_FIN}h"


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
        lambda: cb.run_cleanup_drain(mode="unverified", site=site, source="cron-nightly",
                                     max_seconds=DRAIN_BUDGET_S),
        site,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", help="lcr|mkd (défaut: les deux)")
    ap.add_argument("--force", action="store_true",
                    help="passer outre la fenetre nocturne (prend le verrou du pool)")
    args = ap.parse_args()
    sites = [args.site] if args.site else SITES

    ok, pourquoi = dans_la_fenetre()
    if not ok and not args.force:
        print(f"[nightly_cleanup] rien a faire - {pourquoi}. "
              f"Le pool reste libre pour le pixel d ouverture et les compteurs.", flush=True)
        return

    before = _retry_lock(cb.count_unverified, "count-before")
    print(f"[nightly_cleanup] non-vérifiés avant: {before}", flush=True)

    problems = []
    timeouts = []
    for site in sites:
        try:
            res = _drain_with_retry(site)
            print(f"[{site}] {res}", flush=True)
            if res.get("timed_out"):
                # Pas un incident : le budget a fait son travail. On le dit quand meme,
                # parce que plusieurs nuits d affilee = le backlog grossit plus vite
                # qu on ne le draine, et la c est un vrai sujet.
                print(f"[{site}] budget de {DRAIN_BUDGET_S:.0f}s epuise - "
                      f"verrou rendu, reliquat repris la nuit prochaine", flush=True)
                timeouts.append(site)
            if res.get("errors"):
                problems.append(f"{site}: {res.get('errors')} erreurs")
        except Exception as e:  # noqa: BLE001
            print(f"[{site}] ÉCHEC: {e}", flush=True)
            problems.append(f"{site}: {e}")

    after = _retry_lock(cb.count_unverified, "count-after")
    print(f"[nightly_cleanup] non-vérifiés après: {after} (supprimés/validés: {before - after})", flush=True)

    if problems:
        notify_telegram(MSG_INCIDENT + "\n".join(problems) +
                        f"\nNon-verifies restants: {after}")
    elif timeouts and after > 0:
        notify_telegram(MSG_BUDGET.format(sites=", ".join(timeouts),
                                          budget=int(DRAIN_BUDGET_S // 60), reste=after))


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
