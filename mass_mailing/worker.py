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
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from infra import pg  # noqa: E402
from jobs import analyze_csv, capacite, clics, envoi, file, rebonds, risque_adresses, routage, score_clics, validation  # noqa: E402
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


def _liberer_jobs_de_workers_morts() -> int:
    """Un redémarrage (déploiement, plantage) laisse le job en cours marqué `running` :
    on le rend à la file dès que son worker n'existe plus, sans attendre le délai de
    sécurité. La reprise ne revérifie que ce qui n'a pas de verdict : pas de double coût."""
    import os
    n = 0
    for j in pg.lignes("SELECT id, locked_by FROM jobs WHERE status = 'running'"):
        hote, _, pid = (j["locked_by"] or "").rpartition(":")
        if hote != socket.gethostname() or not pid.isdigit() or f"{hote}:{pid}" == IDENTITE:
            continue
        try:
            os.kill(int(pid), 0)          # le processus existe encore : on n'y touche pas
            continue
        except ProcessLookupError:
            pass
        except PermissionError:
            continue
        n += pg.ecrire("""UPDATE jobs SET status = 'pending', locked_at = NULL, locked_by = NULL,
                                 last_error = COALESCE(last_error, '') || ' [repris : worker arrêté]'
                           WHERE id = %(i)s AND status = 'running'""", {"i": j["id"]})
    return n


def _stop(*_):
    global _arret
    _arret = True
    _log("arrêt demandé : fin du job en cours puis sortie")


def boucle() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    _log(f"worker démarré ({IDENTITE}), types : {', '.join(EXECUTEURS)}")
    try:
        n = _liberer_jobs_de_workers_morts()
        if n:
            _log(f"{n} job(s) d'un worker arrêté repris")
    except Exception as e:  # noqa: BLE001
        _log(f"reprise impossible : {e}")
    dernier_menage = 0.0
    dernier_clics = 0.0
    dernier_score = 0.0
    dernier_capacite = 0.0
    dernier_routage = 0.0
    dernier_rebonds = 0.0
    jour_risque = None                              # date (Paris) du dernier apprentissage
    derniere_synchro = 0.0
    while not _arret:
        _battement("attente")
        if time.time() - dernier_menage > 300:
            try:
                n = file.liberer_orphelins(minutes=180) + _liberer_jobs_de_workers_morts()
                if n:
                    _log(f"{n} job(s) orphelin(s) rendu(s) à la file")
                pg.ecrire("DELETE FROM workers WHERE seen_at < now() - interval '1 day'")
            except Exception as e:  # noqa: BLE001
                _log(f"ménage impossible : {e}")
            dernier_menage = time.time()

        if time.time() - dernier_clics > 30:
            try:
                n = clics.traiter()
                if n:
                    _log(f"{n} événement(s) Sweego traité(s) (clics)")
            except Exception as e:  # noqa: BLE001
                _log(f"clics non traités : {e}")
            dernier_clics = time.time()
        if time.time() - dernier_routage > 60:
            # Agent de routage (jobs/routage.py) : vagues horaires par messagerie, 8h-22h.
            try:
                for r in routage.tour():
                    _log(f"routage : {r.get('campaign_id', '')[:8]} {({k: v for k, v in r.items() if k != 'plan'})}")
            except Exception as e:  # noqa: BLE001
                _log(f"routage en erreur : {e}")
            dernier_routage = time.time()
        if time.time() - dernier_rebonds > 3600:
            # Rebonds (jobs/rebonds.py) : relit les échecs Sweego de TOUT le compte (3 derniers jours),
            # les classe (hard / soft / expéditeur) et alimente la liste noire globale.
            try:
                r = rebonds.importer(jours=3)
                _log(f"rebonds : {r}")
            except Exception as e:  # noqa: BLE001
                _log(f"rebonds non importés : {e}")
            dernier_rebonds = time.time()
        maintenant_paris = datetime.now(ZoneInfo("Europe/Paris"))
        if maintenant_paris.hour == 3 and jour_risque != maintenant_paris.date():
            # Agent « adresses à risque » (jobs/risque_adresses.py) : réapprend chaque nuit à 3 h (heure de
            # Paris), hors de la fenêtre d'envoi : l'apprentissage relit des mois de logs et bloque la boucle
            # quelques minutes (revue du 30/09).
            try:
                r = risque_adresses.apprendre()
                _log(f"risque adresses : modèle réappris ({r['n']} adresses, AUC {r['auc']})")
            except Exception as e:  # noqa: BLE001
                _log(f"risque adresses non réappris : {e}")
            jour_risque = maintenant_paris.date()
        if time.time() - dernier_capacite > 900:
            # Pilotage adaptatif (jobs/capacite.py) : apprend la capacité par file (IP + identité +
            # flux + messagerie) à partir des réponses SMTP. Conseil seulement : n'envoie rien.
            try:
                r = capacite.tourner()
                if r.get("ingeres") or r.get("suppressions_corrigees"):
                    _log(f"capacité : {r}")
            except Exception as e:  # noqa: BLE001
                _log(f"capacité non évaluée : {e}")
            dernier_capacite = time.time()
        if time.time() - dernier_score > 300:
            # Score anti-robot en DOUBLE CALCUL (jobs/score_clics.py) : n'écrit que click_scores.
            try:
                n = score_clics.recalculer_recents()
                if n:
                    _log(f"score anti-robot recalculé pour {n} campagne(s)")
            except Exception as e:  # noqa: BLE001
                _log(f"score anti-robot non calculé : {e}")
            dernier_score = time.time()
        if time.time() - derniere_synchro > envoi.SYNCHRO_TOUTES_LES_S:
            try:
                n = envoi.synchroniser_recentes()
                if n:
                    _log(f"statistiques Sweego relues pour {n} campagne(s)")
            except Exception as e:  # noqa: BLE001 — Sweego injoignable : on réessaie au tour suivant
                _log(f"statistiques non relues : {e}")
            derniere_synchro = time.time()
        try:
            for cid in envoi.declencher_programmations():
                _log(f"campagne {cid} : départ programmé déclenché")
        except Exception as e:  # noqa: BLE001
            _log(f"programmations illisibles : {e}")
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
