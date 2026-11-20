#!/usr/bin/env python3
"""mass_mailing/jobs/file.py — la file de travaux, sur PostgreSQL.

Ce qui remplace BullMQ, sans Redis (choix de Camille, 2026-09-25).

Le mécanisme tient en une requête : `SELECT … FOR UPDATE SKIP LOCKED`. Plusieurs
workers peuvent dépiler la même table en parallèle sans jamais tirer la même ligne —
PostgreSQL saute les lignes déjà verrouillées par une autre transaction au lieu
d'attendre. C'est la primitive de file la plus simple qui soit correcte, et elle ne
coûte aucune infrastructure supplémentaire.

Trois propriétés exigées par la spec, et comment elles sont tenues :

- **Idempotence** — `idempotency_key` porte un index unique partiel, limité aux
  statuts `pending` et `running`. Empiler deux fois le même travail ne crée pas de
  doublon ; une fois terminé, la clé se libère et le travail peut être rejoué
  volontairement.
- **Rejouabilité** — un échec transitoire repart avec un délai exponentiel. Un échec
  DÉFINITIF (clé invalide, quota épuisé, CSV illisible) ne repart jamais : le
  réessayer ne fait que brûler du temps. C'est l'appelant qui tranche, via
  `echouer(definitif=True)`.
- **Observabilité** — chaque travail garde ses tentatives, sa dernière erreur, son
  résultat et ses horodatages. Un travail mort part en `dead`, jamais en silence.
"""
from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import pg  # noqa: E402

# Palier de reprise : 1 min, 5 min, 15 min, 1 h, 6 h. Au-delà des tentatives
# autorisées, le travail est déclaré mort et attend une main humaine.
PALIERS_MIN = (1, 5, 15, 60, 360)


class ErreurDefinitive(Exception):
    """Levée par un job quand réessayer ne changera rien (CSV illisible, campagne
    verrouillée, quota épuisé). Le worker la traduit en `echouer(definitif=True)`."""


def _identite() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def empiler(job_type: str, *, campaign_id: str | None = None,
            payload: dict | None = None, idempotency_key: str | None = None,
            priority: int = 100, run_after: datetime | None = None,
            max_attempts: int = 5) -> dict | None:
    """Ajoute un travail. Renvoie None si un travail identique est déjà en attente."""
    sql = """
        INSERT INTO jobs (job_type, campaign_id, payload, idempotency_key,
                          priority, run_after, max_attempts)
        VALUES (%(t)s, %(c)s, %(p)s::jsonb, %(k)s, %(pr)s,
                COALESCE(%(r)s, now()), %(m)s)
        ON CONFLICT DO NOTHING
        RETURNING id, job_type, status
    """
    return pg.ligne(sql, {"t": job_type, "c": campaign_id,
                          "p": json.dumps(payload or {}, ensure_ascii=False),
                          "k": idempotency_key, "pr": priority,
                          "r": run_after, "m": max_attempts})


def tirer(types: list[str] | None = None) -> dict | None:
    """Réserve UN travail et le passe en `running`, atomiquement.

    `SKIP LOCKED` est ce qui rend l'opération sûre entre workers concurrents : sans
    lui, deux workers liraient la même ligne avant que l'un ne la marque.
    """
    filtre = "AND job_type = ANY(%(types)s)" if types else ""
    sql = f"""
        WITH suivant AS (
            SELECT id FROM jobs
             WHERE status = 'pending' AND run_after <= now() {filtre}
             ORDER BY priority ASC, run_after ASC, id ASC
             LIMIT 1
             FOR UPDATE SKIP LOCKED
        )
        UPDATE jobs j
           SET status = 'running', attempts = j.attempts + 1,
               locked_at = now(), locked_by = %(qui)s, started_at = now()
          FROM suivant s
         WHERE j.id = s.id
     RETURNING j.id, j.job_type, j.campaign_id, j.payload, j.attempts, j.max_attempts
    """
    return pg.ligne(sql, {"types": types, "qui": _identite()})


def terminer(job_id: int, resultat: dict | None = None) -> None:
    pg.ecrire("""
        UPDATE jobs SET status = 'completed', finished_at = now(),
                        result = %(r)s::jsonb, last_error = NULL,
                        locked_at = NULL, locked_by = NULL
         WHERE id = %(id)s
    """, {"id": job_id, "r": json.dumps(resultat or {}, ensure_ascii=False)})


def echouer(job_id: int, erreur: str, *, definitif: bool = False) -> dict:
    """Marque un échec. Reprogramme si c'est transitoire et qu'il reste des essais.

    Un échec définitif va directement en `dead` : réessayer une clé invalide ou un
    quota épuisé ne le rendra pas valide, et masque le vrai problème derrière des
    tentatives qui échouent poliment.
    """
    j = pg.ligne("SELECT attempts, max_attempts FROM jobs WHERE id = %(id)s", {"id": job_id})
    if not j:
        return {"statut": "introuvable"}

    epuise = j["attempts"] >= j["max_attempts"]
    if definitif or epuise:
        pg.ecrire("""
            UPDATE jobs SET status = 'dead', finished_at = now(), last_error = %(e)s,
                            locked_at = NULL, locked_by = NULL
             WHERE id = %(id)s
        """, {"id": job_id, "e": erreur[:2000]})
        return {"statut": "dead",
                "motif": "définitif" if definitif else "tentatives épuisées"}

    minutes = PALIERS_MIN[min(j["attempts"] - 1, len(PALIERS_MIN) - 1)]
    pg.ecrire("""
        UPDATE jobs SET status = 'pending', last_error = %(e)s, run_after = %(r)s,
                        locked_at = NULL, locked_by = NULL
         WHERE id = %(id)s
    """, {"id": job_id, "e": erreur[:2000],
          "r": datetime.now(timezone.utc) + timedelta(minutes=minutes)})
    return {"statut": "reprogramme", "dans_minutes": minutes}


def liberer_orphelins(minutes: int = 30) -> int:
    """Rend à la file les travaux d'un worker mort en cours de route.

    Sans ce filet, un worker tué pendant un travail laisse la ligne en `running`
    pour toujours : la campagne semble avancer alors que plus rien ne la pousse.
    """
    return pg.ecrire("""
        UPDATE jobs SET status = 'pending', locked_at = NULL, locked_by = NULL,
                        last_error = COALESCE(last_error, '') ||
                                     ' [repris : worker disparu]'
         WHERE status = 'running' AND locked_at < now() - (%(m)s || ' minutes')::interval
    """, {"m": minutes})


def etat(campaign_id: str | None = None) -> dict:
    ou = "WHERE campaign_id = %(c)s" if campaign_id else ""
    lignes = pg.lignes(f"SELECT status, count(*) n FROM jobs {ou} GROUP BY 1",
                       {"c": campaign_id} if campaign_id else None)
    return {l["status"]: l["n"] for l in lignes}


def morts(limite: int = 50) -> list[dict]:
    return pg.lignes("""
        SELECT id, job_type, campaign_id, attempts, last_error, finished_at
          FROM jobs WHERE status = 'dead' ORDER BY finished_at DESC LIMIT %(l)s
    """, {"l": limite})


def relancer_morts(campaign_id: str | None = None, job_type: str | None = None) -> int:
    """« Relancer les lots en erreur » de la spec : remet les morts en attente."""
    conditions = ["status = 'dead'"]
    params: dict = {}
    if campaign_id:
        conditions.append("campaign_id = %(c)s")
        params["c"] = campaign_id
    if job_type:
        conditions.append("job_type = %(t)s")
        params["t"] = job_type
    return pg.ecrire(f"""
        UPDATE jobs SET status = 'pending', attempts = 0, run_after = now(),
                        last_error = NULL, finished_at = NULL
         WHERE {' AND '.join(conditions)}
    """, params)


if __name__ == "__main__":
    import sys as _sys
    cmd = _sys.argv[1] if len(_sys.argv) > 1 else "etat"
    if cmd == "etat":
        print(json.dumps(etat(), ensure_ascii=False, indent=1))
    elif cmd == "morts":
        print(json.dumps(morts(), ensure_ascii=False, indent=1, default=str))
    elif cmd == "orphelins":
        print(json.dumps({"liberes": liberer_orphelins()}, ensure_ascii=False))
