#!/usr/bin/env python3
"""mass_mailing/worker.py — le processus qui vide la file de jobs.

Lancé par PM2 (`mass-mailing-worker`), séparé de l'API : un import de 100 000 lignes
ou une validation de plusieurs heures ne doit jamais bloquer une requête HTTP, et un
plantage ici ne doit pas faire tomber Cheffer.

Boucle : battement de cœur → orphelins rendus à la file → un job tiré → exécuté →
terminé, reprogrammé ou déclaré mort. Un job à la fois : la validation d'un lot
parallélise déjà ses appels Mailnjoy (`settings.mailnjoy_concurrency`), et traiter
les lots dans l'ordre est ce qui fait partir le lot 1 avant le lot 2.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from infra import pg  # noqa: E402
from jobs import analyze_csv, envoi, file, validation  # noqa: E402
from jobs.file import ErreurDefinitive  # noqa: E402

EXECUTEURS = {analyze_csv.JOB_TYPE: analyze_csv.executer, **validation.EXECUTEURS,
              **envoi.EXECUTEURS}
IDENTITE = f"{socket.gethostname()}:{os.getpid()}"
PAUSE_VIDE_S = 3
_arret = False


def _log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def _battement(etat: str, job: dict | None = None) -> None:
    try:
        pg.ecrire("""INSERT INTO workers (id, seen_at, info) VALUES (%(i)s, now(), %(x)s::jsonb)
                     ON CONFLICT (id) DO UPDATE SET seen_at = now(), info = EXCLUDED.info""",
                  {"i": IDENTITE, "x": json.dumps({"etat": etat,
                                                   "job": job and job.get("id"),
                                                   "type": job and job.get("job_type")})})
    except Exception as e:  # noqa: BLE001 — la base peut hoqueter, le worker continue
        _log(f"battement impossible : {e}")


def _stop(*_):
    global _arret
    _arret = True
    _log("arrêt demandé : fin du job en cours puis sortie")


def boucle() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    _log(f"worker démarré ({IDENTITE}), types : {', '.join(EXECUTEURS)}")
    dernier_menage = 0.0
    while not _arret:
        _battement("attente")
        if time.time() - dernier_menage > 300:
            try:
                n = file.liberer_orphelins(minutes=180)
                if n:
                    _log(f"{n} job(s) orphelin(s) rendu(s) à la file")
                pg.ecrire("DELETE FROM workers WHERE seen_at < now() - interval '1 day'")
            except Exception as e:  # noqa: BLE001
                _log(f"ménage impossible : {e}")
            dernier_menage = time.time()

        try:
            job = file.tirer(list(EXECUTEURS))
        except Exception as e:  # noqa: BLE001
            _log(f"file illisible : {e}")
            time.sleep(10)
            continue
        if not job:
            time.sleep(PAUSE_VIDE_S)
            continue

        _battement("travail", job)
        debut = time.time()
        _log(f"job {job['id']} {job['job_type']} (essai {job['attempts']}/{job['max_attempts']})")
        try:
            resultat = EXECUTEURS[job["job_type"]](job)
            file.terminer(job["id"], resultat)
            _log(f"job {job['id']} terminé en {time.time() - debut:.0f} s")
        except ErreurDefinitive as e:
            r = file.echouer(job["id"], str(e), definitif=True)
            _log(f"job {job['id']} ÉCHEC DÉFINITIF : {e} → {r}")
        except Exception as e:  # noqa: BLE001
            r = file.echouer(job["id"], f"{type(e).__name__}: {e}")
            _log(f"job {job['id']} échec transitoire : {e} → {r}")
            traceback.print_exc()
    _battement("arrêté")


if __name__ == "__main__":
    boucle()
