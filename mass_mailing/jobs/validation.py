#!/usr/bin/env python3
"""mass_mailing/jobs/validation.py — la mécanique de lots, de la cible à l'envoi.

UNE unité partout : le lot de 1 000 (`settings.validation_batch_size`).
Mailnjoy vérifie adresse par adresse, Sweego accepte 1 000 destinataires par
appel : le lot de validation k devient le lot d'envoi k, sans attendre les autres
(Camille, 2026-09-25 : « je ne veux pas attendre que tout soit nettoyé »).

    creer_lots           cible figée → N lots de 1 000 → N jobs `valider_lot`
    valider_lot (×N)     1 000 verdicts Mailnjoy → politique → lot d'envoi k

Trois garanties, parce qu'un lot de validation coûte des crédits :

- **Jamais deux fois la même adresse facturée.** Un lot repris (worker tué,
  erreur réseau) ne revérifie que ses destinataires encore `pending` ; chaque
  verdict est écrit par paquets de 50 dès qu'il arrive.
- **Arrêt net sur 401 / 403** (clé refusée, crédit épuisé) : le lot passe en
  échec définitif. Réessayer ne rendrait pas la clé valide.
- **Un lot validé = un seul lot d'envoi**, garanti par un index unique
  (`sb_un_envoi_par_lot`), pas par la prudence du code.

Ce module ne PART PAS chez Sweego : il crée des lots d'envoi `pending`. Le
départ réel est l'affaire de `dispatch_sweego_batch`, qui n'enverra que si la
campagne est autorisée à envoyer (`status = 'sending'`).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import mailnjoy, pg  # noqa: E402
from jobs import file  # noqa: E402
from jobs.file import ErreurDefinitive  # noqa: E402

import psycopg2.extras  # noqa: E402

JOB_CREER = "campaign.create_validation_batches"
JOB_VALIDER = "campaign.validate_batch"

# Décision Mailnjoy (infra/mailnjoy.DECISIONS) → clé de `settings.eligibility_policy`.
CLE_POLITIQUE = {"valid": "deliverable", "risky": "risky", "unknown": "unknown",
                 "invalid": "invalid", "disposable": "disposable", "role": "role"}

PAQUET_ECRITURE = 50

# Adresses que Mailnjoy ne sait pas vérifier (constaté le 2026-09-26 : des yahoo.fr/.com
# qui répondent « HTTP 500 — Une erreur est survenue » au bout de ~28 s, à chaque fois).
# Relancer le lot ne sert à rien : il brûlait ses 5 essais puis mourait, et ses ~1 000
# autres adresses, déjà vérifiées, ne partaient jamais. Après ECHECS_AVANT_INCONNUE
# passages en échec, l'adresse est classée `unknown` (écartée par la politique par défaut)
# et le lot se termine — mais SEULEMENT si le reste du lot est vérifié : une vraie panne
# Mailnjoy (beaucoup d'échecs) reste une erreur passagère, rien n'est classé à tort.
ECHECS_AVANT_INCONNUE = 2
PART_MAX_INVERIFIABLES = 0.02   # au plus 2 % du lot


def _reglages() -> dict:
    return pg.ligne("""SELECT eligibility_policy, validation_batch_size, mailnjoy_concurrency
                         FROM settings""")


def _audit(cur, campaign_id: str, event: str, resume: str, charge: dict) -> None:
    cur.execute("""
        INSERT INTO campaign_events (campaign_id, actor_type, event_type, summary, payload)
        VALUES (%(c)s, 'worker', %(e)s, %(r)s, %(p)s::jsonb)
    """, {"c": campaign_id, "e": event, "r": resume,
          "p": json.dumps(charge, ensure_ascii=False, default=str)})


# ── 1. Découper ──────────────────────────────────────────────────────────────

def creer_lots(job: dict, *, credit: Callable[[], dict] = mailnjoy.credit) -> dict:
    """Fige la cible, la découpe en lots, empile un job de validation par lot.

    Appelé après la confirmation explicite du superadmin (« Vous allez soumettre
    N emails à Mailnjoy »). Idempotent : si les lots existent déjà, rien n'est recréé.
    """
    campaign_id = job.get("campaign_id")
    if not campaign_id:
        raise ErreurDefinitive("campaign_id requis")
    r = _reglages()
    taille = max(1, min(int(r["validation_batch_size"]), 1000))

    with pg.connexion() as cur:
        cur.execute("""SELECT status, target_version_id FROM campaigns
                        WHERE id = %(c)s FOR UPDATE""", {"c": campaign_id})
        camp = cur.fetchone()
        if not camp or not camp["target_version_id"]:
            raise ErreurDefinitive("campagne ou cible introuvable")
        tv = camp["target_version_id"]

        cur.execute("SELECT count(*) n FROM validation_batches WHERE target_version_id = %(t)s",
                    {"t": tv})
        if cur.fetchone()["n"]:
            existants = _empiler_lots_en_attente(cur, campaign_id, tv)
            return {"deja_decoupe": True, "jobs_empiles": existants}

        if camp["status"] != "ready_for_validation":
            raise ErreurDefinitive(
                f"validation impossible depuis le statut « {camp['status']} »")

        cur.execute("""SELECT id FROM recipients
                        WHERE target_version_id = %(t)s AND import_status = 'imported'
                          AND eligibility_status = 'pending'
                        ORDER BY original_row_number, id""", {"t": tv})
        ids = [x["id"] for x in cur.fetchall()]
        if not ids:
            raise ErreurDefinitive("aucune adresse à valider dans cette cible")

        # Garde-fou crédits AVANT de figer quoi que ce soit.
        c = credit()
        if not c.get("ok"):
            raise ErreurDefinitive(f"crédit Mailnjoy illisible : {c.get('erreur')}")
        if int(c.get("credit") or 0) < len(ids):
            raise ErreurDefinitive(
                f"crédit Mailnjoy insuffisant : {c.get('credit')} pour {len(ids)} adresses")

        cur.execute("""UPDATE campaign_target_versions SET frozen_at = now()
                        WHERE id = %(t)s AND frozen_at IS NULL""", {"t": tv})

        lots = []
        for seq, debut in enumerate(range(0, len(ids), taille), start=1):
            tranche = ids[debut:debut + taille]
            cur.execute("""
                INSERT INTO validation_batches (campaign_id, target_version_id,
                                                sequence_number, total_recipients)
                VALUES (%(c)s, %(t)s, %(s)s, %(n)s) RETURNING id
            """, {"c": campaign_id, "t": tv, "s": seq, "n": len(tranche)})
            lot_id = cur.fetchone()["id"]
            cur.execute("""UPDATE recipients SET validation_batch_id = %(l)s, updated_at = now()
                            WHERE id = ANY(%(ids)s)""", {"l": lot_id, "ids": tranche})
            lots.append(str(lot_id))

        cur.execute("""UPDATE campaigns SET status = 'validating_list', updated_at = now()
                        WHERE id = %(c)s""", {"c": campaign_id})
        _audit(cur, campaign_id, "validation.started",
               f"{len(ids)} adresses soumises à Mailnjoy en {len(lots)} lots de {taille} max",
               {"lots": len(lots), "adresses": len(ids), "credit_avant": c.get("credit")})
        empiles = _empiler_lots_en_attente(cur, campaign_id, tv)

    return {"deja_decoupe": False, "lots": len(lots), "adresses": len(ids),
            "jobs_empiles": empiles}


def _empiler_lots_en_attente(cur, campaign_id: str, tv) -> int:
    """Un job par lot non terminé. Les lots partent dans l'ordre (priorité = rang) :
    le lot 1 est validé — et peut donc partir — avant le lot 2."""
    cur.execute("""SELECT id, sequence_number FROM validation_batches
                    WHERE target_version_id = %(t)s AND status IN ('pending','running')
                    ORDER BY sequence_number""", {"t": tv})
    n = 0
    for lot in cur.fetchall():
        cur.execute("""
            INSERT INTO jobs (job_type, campaign_id, payload, idempotency_key, priority)
            VALUES (%(t)s, %(c)s, %(p)s::jsonb, %(k)s, %(pr)s)
            ON CONFLICT DO NOTHING
        """, {"t": JOB_VALIDER, "c": campaign_id,
              "p": json.dumps({"validation_batch_id": str(lot["id"])}),
              "k": f"validate:{lot['id']}", "pr": 100 + lot["sequence_number"]})
        n += cur.rowcount
    return n


# ── 2. Valider un lot ────────────────────────────────────────────────────────

def valider_lot(job: dict, *, verifier: Callable[[str], dict] = mailnjoy.verifier,
                fils: int | None = None) -> dict:
    """Vérifie les adresses encore `pending` du lot, puis le finalise."""
    lot_id = (job.get("payload") or {}).get("validation_batch_id")
    if not lot_id:
        raise ErreurDefinitive("validation_batch_id requis")
    r = _reglages()
    fils = max(1, min(fils or int(r["mailnjoy_concurrency"]), 20))

    lot = pg.ligne("""UPDATE validation_batches
                         SET status = 'running', attempts = attempts + 1,
                             started_at = COALESCE(started_at, now())
                       WHERE id = %(l)s AND status IN ('pending','running','failed')
                   RETURNING id, campaign_id, sequence_number, total_recipients""", {"l": lot_id})
    if not lot:
        etat = pg.valeur("SELECT status FROM validation_batches WHERE id = %(l)s", {"l": lot_id})
        if etat == "completed":
            return {"deja_valide": True}
        raise ErreurDefinitive(f"lot introuvable ou dans l'état « {etat} »")

    a_faire = pg.lignes("""SELECT id, email_normalized FROM recipients
                            WHERE validation_batch_id = %(l)s AND validation_status = 'pending'
                            ORDER BY id""", {"l": lot_id})

    tampon: list[tuple] = []
    echecs: list[tuple] = []          # (id, erreur) des appels en échec passager
    arret: str | None = None

    def vider():
        if not tampon:
            return
        with pg.connexion(curseur_dict=False) as cur:
            psycopg2.extras.execute_values(cur, """
                UPDATE recipients r
                   SET validation_status = v.dec, validation_provider_status = v.brut,
                       validation_reason = v.motif, validated_at = now(), updated_at = now()
                  FROM (VALUES %s) AS v(id, dec, brut, motif)
                 WHERE r.id = v.id AND r.validation_status = 'pending'
            """, tampon)
            cur.execute("""UPDATE validation_batches
                              SET processed_count = (SELECT count(*) FROM recipients
                                                      WHERE validation_batch_id = %s
                                                        AND validation_status <> 'pending')
                            WHERE id = %s""", (lot_id, lot_id))
        tampon.clear()

    with ThreadPoolExecutor(fils) as ex:
        for dest, res in zip(a_faire, ex.map(lambda d: verifier(d["email_normalized"]), a_faire)):
            if arret:
                continue          # les appels déjà lancés se terminent, on n'écrit plus rien
            if res.get("ok"):
                brut = res.get("raw")
                statut_brut = None
                if isinstance(brut, dict):
                    p = brut.get("unitaryCheck", brut)
                    statut_brut = f"{p.get('status', '')}/{p.get('category', '')}".strip("/") or None
                tampon.append((dest["id"], res["decision"], statut_brut, res.get("reason")))
                if len(tampon) >= PAQUET_ECRITURE:
                    vider()
            elif res.get("status_code") in (401, 403):
                arret = res.get("error") or res.get("reason")
            else:
                echecs.append((dest["id"], str(res.get("error") or res.get("reason") or "inconnu")[:200]))
    vider()

    if arret:
        pg.ecrire("""UPDATE validation_batches SET status = 'failed', error_code = 'provider',
                            error_message = %(e)s WHERE id = %(l)s""", {"l": lot_id, "e": arret})
        raise ErreurDefinitive(f"lot {lot['sequence_number']} arrêté : {arret}")
    if echecs:
        restants = _classer_inverifiables(lot_id, lot, echecs)
        if restants:
            # Le job repartira ; seules les adresses encore `pending` seront revérifiées.
            raise RuntimeError(f"{restants} vérifications en échec transitoire, lot à reprendre")

    return finaliser_lot(lot_id)


def _classer_inverifiables(lot_id: str, lot: dict, echecs: list[tuple]) -> int:
    """Compte un échec de plus pour chaque adresse en échec ; classe `unknown` celles qui
    en sont à ECHECS_AVANT_INCONNUE, si le reste du lot est vérifié. Renvoie le nombre
    d'adresses encore en échec passager (le lot doit alors être repris)."""
    ids = [i for i, _ in echecs]
    erreurs = dict(echecs)
    with pg.connexion() as cur:
        cur.execute("""UPDATE recipients
                          SET provider_raw_metadata = COALESCE(provider_raw_metadata, '{}'::jsonb)
                              || jsonb_build_object('echecs_mailnjoy',
                                     COALESCE((provider_raw_metadata->>'echecs_mailnjoy')::int, 0) + 1),
                              updated_at = now()
                        WHERE id = ANY(%(ids)s) AND validation_status = 'pending'
                    RETURNING id, (provider_raw_metadata->>'echecs_mailnjoy')::int AS n""", {"ids": ids})
        comptes = {x["id"]: x["n"] for x in cur.fetchall()}
        cur.execute("""SELECT count(*) FILTER (WHERE validation_status = 'pending') AS pending, count(*) AS total
                         FROM recipients WHERE validation_batch_id = %(l)s""", {"l": lot_id})
        etat = cur.fetchone()
        mures = [i for i, n in comptes.items() if n >= ECHECS_AVANT_INCONNUE]
        # Garde-fou : on ne classe que si les adresses encore en attente du lot sont
        # toutes des « invérifiables » et qu'elles pèsent peu. Sinon, c'est une panne.
        if not mures or etat["pending"] > len(mures) or etat["pending"] > max(1, PART_MAX_INVERIFIABLES * etat["total"]):
            return len(comptes)
        psycopg2.extras.execute_values(cur, """
            UPDATE recipients r
               SET validation_status = 'unknown', validation_provider_status = 'erreur_mailnjoy',
                   validation_reason = v.motif, validated_at = now(), updated_at = now()
              FROM (VALUES %s) AS v(id, motif)
             WHERE r.id = v.id AND r.validation_status = 'pending'
        """, [(i, f"Mailnjoy n'a pas pu la vérifier ({comptes[i]} passages en échec : {erreurs[i]})") for i in mures])
        cur.execute("""UPDATE validation_batches
                          SET processed_count = (SELECT count(*) FROM recipients
                                                  WHERE validation_batch_id = %(l)s AND validation_status <> 'pending')
                        WHERE id = %(l)s""", {"l": lot_id})
        _audit(cur, lot["campaign_id"], "validation.inverifiables",
               f"Lot {lot['sequence_number']} : {len(mures)} adresse(s) que Mailnjoy ne sait pas vérifier, classées « inconnues »",
               {"lot": str(lot_id), "adresses": len(mures)})
    return len(comptes) - len(mures)


# ── 3. Finaliser : politique d'éligibilité + lot d'envoi ─────────────────────

def finaliser_lot(lot_id: str) -> dict:
    politique = _reglages()["eligibility_policy"]
    with pg.connexion() as cur:
        cur.execute("""SELECT id, campaign_id, sequence_number, status FROM validation_batches
                        WHERE id = %(l)s FOR UPDATE""", {"l": lot_id})
        lot = cur.fetchone()
        if lot["status"] == "completed":
            return {"deja_valide": True}
        cid = lot["campaign_id"]

        # La suppression est relue ICI, pas seulement à l'import : entre l'import
        # et la fin de validation, quelqu'un a pu se désinscrire.
        cur.execute("""
            SELECT r.id, r.validation_status,
                   EXISTS (SELECT 1 FROM suppressions s
                            WHERE s.email_hash = r.email_hash AND """ + pg.SUPPRESSION_ACTIVE.format(t="s") + """
                              AND (s.scope = 'global'
                                   OR (s.scope = 'campaign' AND s.scope_id = r.campaign_id))) AS supprime
              FROM recipients r WHERE r.validation_batch_id = %(l)s
        """, {"l": lot_id})
        maj, decisions = [], Counter()
        for d in cur.fetchall():
            decisions[d["validation_status"]] += 1
            if d["supprime"]:
                maj.append((d["id"], "excluded", "suppressed"))
                continue
            regle = politique.get(CLE_POLITIQUE.get(d["validation_status"], "unknown"), "excluded")
            maj.append((d["id"], "eligible" if regle == "eligible" else "excluded",
                        d["validation_status"]))
        psycopg2.extras.execute_values(cur, """
            UPDATE recipients r SET eligibility_status = v.e, eligibility_reason = v.m,
                                    updated_at = now()
              FROM (VALUES %s) AS v(id, e, m) WHERE r.id = v.id
        """, maj)
        eligibles = sum(1 for m in maj if m[1] == "eligible")

        cur.execute("""UPDATE validation_batches
                          SET status = 'completed', completed_at = now(),
                              processed_count = total_recipients,
                              eligible_count = %(e)s, excluded_count = %(x)s,
                              decisions = %(d)s::jsonb
                        WHERE id = %(l)s""",
                    {"l": lot_id, "e": eligibles, "x": len(maj) - eligibles,
                     "d": json.dumps(dict(decisions))})

        cur.execute("SELECT dispatch_mode FROM campaigns WHERE id = %(c)s", {"c": cid})
        mode = cur.fetchone()["dispatch_mode"]
        envoi = None
        if mode == "progressive":
            envoi = _creer_lot_envoi(cur, cid, lot_id, lot["sequence_number"], eligibles)
            # Rattrapage : si le mode est passé de « tout d'un coup » à « au fil de l'eau »
            # en cours de validation, les lots déjà validés n'ont pas de lot d'envoi.
            cur.execute("""SELECT v.id, v.sequence_number, v.eligible_count FROM validation_batches v
                            WHERE v.campaign_id = %(c)s AND v.status = 'completed' AND v.id <> %(l)s
                              AND NOT EXISTS (SELECT 1 FROM sending_batches s WHERE s.validation_batch_id = v.id)""",
                        {"c": cid, "l": lot_id})
            for manquant in cur.fetchall():
                _creer_lot_envoi(cur, cid, manquant["id"], manquant["sequence_number"], manquant["eligible_count"])

        cur.execute("""SELECT count(*) FILTER (WHERE status <> 'completed') AS restants,
                              count(*) AS total, sum(eligible_count) AS eligibles
                         FROM validation_batches WHERE campaign_id = %(c)s""", {"c": cid})
        bilan = cur.fetchone()
        _audit(cur, cid, "validation.batch_completed",
               f"Lot {lot['sequence_number']}/{bilan['total']} validé : {eligibles} éligibles",
               {"lot": str(lot_id), "decisions": dict(decisions), "envoi": envoi})

        if bilan["restants"] == 0:
            if mode == "after_validation":
                for s, (vb, n) in enumerate(_lots_termines(cur, cid), start=1):
                    _creer_lot_envoi(cur, cid, vb, s, n)   # déjà créés : ignorés (index unique)
            cur.execute("""UPDATE campaigns SET status = 'ready_to_schedule', updated_at = now()
                            WHERE id = %(c)s AND status = 'validating_list'""", {"c": cid})
            _audit(cur, cid, "validation.completed",
                   f"Validation terminée : {bilan['eligibles']} destinataires éligibles",
                   {"lots": bilan["total"], "eligibles": bilan["eligibles"]})

    # Hors transaction : le lot d'envoi est désormais visible par le worker.
    # Alias : `envoi` est déjà le nom local de l'identifiant du lot d'envoi.
    from jobs import envoi as module_envoi
    module_envoi.apres_lot_valide(str(cid))
    return {"lot": lot["sequence_number"], "eligibles": eligibles,
            "decisions": dict(decisions), "lot_envoi": envoi,
            "lots_restants": bilan["restants"]}


def _lots_termines(cur, cid) -> list[tuple]:
    cur.execute("""SELECT id, eligible_count FROM validation_batches
                    WHERE campaign_id = %(c)s ORDER BY sequence_number""", {"c": cid})
    return [(x["id"], x["eligible_count"]) for x in cur.fetchall()]


def _creer_lot_envoi(cur, cid, vb_id, seq: int, eligibles: int) -> str | None:
    """Lot d'envoi k ← lot de validation k. `skipped` s'il n'a aucun éligible."""
    cur.execute("""
        INSERT INTO sending_batches (campaign_id, sequence_number, recipients_count,
                                     status, validation_batch_id)
        VALUES (%(c)s, %(s)s, %(n)s, %(st)s, %(v)s)
        ON CONFLICT DO NOTHING
        RETURNING id
    """, {"c": cid, "s": seq, "n": eligibles, "v": vb_id,
          "st": "pending" if eligibles else "skipped"})
    row = cur.fetchone()
    if not row:
        return None
    cur.execute("""UPDATE recipients SET sending_batch_id = %(sb)s, send_status = 'queued',
                                         updated_at = now()
                    WHERE validation_batch_id = %(v)s AND eligibility_status = 'eligible'""",
                {"sb": row["id"], "v": vb_id})
    return str(row["id"])


# ── Progression (pour la fiche campagne) ─────────────────────────────────────

def progression(campaign_id: str) -> dict:
    v = pg.ligne("""SELECT count(*) lots, count(*) FILTER (WHERE status = 'completed') valides,
                           -- En échec : le lot lui-même, ou son job mort (essais épuisés) —
                           -- sinon le bouton « Relancer » n'apparaissait jamais.
                           count(*) FILTER (WHERE status = 'failed' OR (status <> 'completed' AND EXISTS (
                               SELECT 1 FROM jobs j WHERE j.status = 'dead' AND j.job_type = 'campaign.validate_batch'
                                  AND j.payload->>'validation_batch_id' = validation_batches.id::text))) en_echec,
                           COALESCE(sum(total_recipients), 0) adresses,
                           COALESCE(sum(processed_count), 0) verifiees,
                           COALESCE(sum(eligible_count), 0) eligibles
                      FROM validation_batches WHERE campaign_id = %(c)s""", {"c": campaign_id})
    # Estimation en cours de lot : les verdicts déjà reçus, passés à la politique
    # d'éligibilité, sans attendre la finalisation du lot.
    politique = (pg.ligne("SELECT eligibility_policy FROM settings") or {}).get("eligibility_policy") or {}
    ok_statuts = [s for s, cle in CLE_POLITIQUE.items() if politique.get(cle) == "eligible"]
    est = pg.ligne("""SELECT count(*) FILTER (WHERE r.validation_status = ANY(%(ok)s)) AS ok,
                             count(*) FILTER (WHERE r.validation_status NOT IN ('pending','error')) AS verifies
                        FROM recipients r JOIN validation_batches b ON b.id = r.validation_batch_id
                       WHERE b.campaign_id = %(c)s
                         AND r.eligibility_reason IS DISTINCT FROM 'suppressed'""", {"c": campaign_id, "ok": ok_statuts})
    if v is not None:
        v["verdicts_eligibles"] = est["ok"] if est else 0
        v["verdicts_rendus"] = est["verifies"] if est else 0
    e = pg.lignes("""SELECT status, count(*) n, sum(recipients_count) dest
                       FROM sending_batches WHERE campaign_id = %(c)s GROUP BY 1""",
                  {"c": campaign_id})
    return {"validation": v, "envoi": {x["status"]: {"lots": x["n"], "destinataires": x["dest"]}
                                       for x in e}}


EXECUTEURS = {JOB_CREER: creer_lots, JOB_VALIDER: valider_lot}
