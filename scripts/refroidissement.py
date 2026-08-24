#!/usr/bin/env python3
"""refroidissement.py — après une plainte, la boîte se tait 48 heures.

Une plainte n'est pas un incident isolé : c'est un signal envoyé au FOURNISSEUR du
destinataire, qui le retient et l'agrège. Google Postmaster bloque autour de 0,3 % et ce
seuil se franchit en une journée. Continuer d'envoyer depuis la même adresse dans les
heures qui suivent, c'est empiler les signaux sur une réputation déjà entamée — et le
temps de s'en apercevoir, l'adresse est grillée pour des semaines.

D'où la règle, volontairement plus dure que ce que le volume commanderait :

  - **une plainte** sur une boîte → cette boîte se tait **48 heures** ;
  - **un pic de rebonds durs** (au-delà du seuil, sur la fenêtre) → **24 heures**, le temps
    de comprendre si c'est la liste ou le domaine ;
  - la reprise est **automatique** à l'échéance : une pause qu'il faut penser à lever est
    une pause qu'on oublie de lever, et le volume ne revient jamais.

Ce que la pause ne fait PAS, et c'est délibéré : elle ne réattribue pas les contacts de la
boîte à une autre. Un contact qui a ouvert depuis cette adresse la garde — voir
`expediteur`. Il attend, comme la boîte. Perdre deux jours d'envoi sur un quart du vivier
coûte moins cher que de repartir de zéro sur la réputation de tous ces destinataires.

Usage :
    python3 scripts/refroidissement.py               # état des pauses
    python3 scripts/refroidissement.py --controler   # pose/lève ce qui doit l'être
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

HEURES_PLAINTE = 48
HEURES_REBOND = 24
# Fenêtre d'observation pour décider d'une pause. Volontairement courte : une plainte
# d'il y a six jours ne dit rien de l'état d'aujourd'hui, et laisserait la boîte au repos
# pour un incident déjà digéré.
FENETRE_HEURES = 48


def _q(sql: str, params=None) -> list[tuple]:
    import pool_pg
    return pool_pg._q(sql, params or {})


def _ecrire(sql: str, params=None) -> int:
    import pool_pg
    return pool_pg._ecrire(sql, params)


def pauses_en_cours(site: str) -> dict[str, dict]:
    return {r[0]: {"jusqu_a": str(r[1]), "motif": r[2], "posee_a": str(r[3])}
            for r in _q("""
                SELECT email::text, pause_jusqu_a, pause_motif, pause_posee_a
                FROM mailboxes
                WHERE site_code = %(site)s AND pause_jusqu_a IS NOT NULL
                  AND pause_jusqu_a > now()""", {"site": site})}


def mettre_au_repos(mailbox: str, heures: int, motif: str) -> bool:
    """Pose une pause. Une pause déjà plus longue n'est jamais raccourcie.

    Deux plaintes à une heure d'intervalle ne doivent pas remettre le compteur à 48 h
    depuis la seconde — mais elles ne doivent pas non plus le raccourcir. On garde la
    plus lointaine des deux échéances.
    """
    jusqu_a = datetime.now(timezone.utc) + timedelta(hours=heures)
    return _ecrire("""
        UPDATE mailboxes
        SET pause_jusqu_a = GREATEST(COALESCE(pause_jusqu_a, %(j)s), %(j)s),
            pause_motif = %(m)s, pause_posee_a = COALESCE(pause_posee_a, now())
        WHERE email = %(mb)s
          AND (pause_jusqu_a IS NULL OR pause_jusqu_a < %(j)s)""",
        {"mb": mailbox, "j": jusqu_a, "m": motif}) > 0


def lever_les_echues(site: str) -> list[str]:
    """Reprise automatique. Sans elle, une pause de 48 h dure jusqu'à ce qu'on y pense."""
    levees = [r[0] for r in _q("""
        SELECT email::text FROM mailboxes
        WHERE site_code = %(site)s AND pause_jusqu_a IS NOT NULL
          AND pause_jusqu_a <= now()""", {"site": site})]
    if levees:
        _ecrire("""UPDATE mailboxes SET pause_jusqu_a = NULL, pause_motif = NULL,
                                        pause_posee_a = NULL
                   WHERE site_code = %(site)s AND pause_jusqu_a <= now()""", {"site": site})
    return levees


def _signaux(site: str) -> dict[str, dict]:
    """Plaintes et rebonds RÉCENTS par boîte expéditrice.

    L'attribution se fait par l'envoi : une plainte ne porte pas de boîte, seule la ligne
    « sent » en porte une. On rattache donc chaque plainte à la boîte qui a écrit à cette
    adresse — c'est elle qui en subit la réputation.
    """
    out: dict[str, dict] = {}
    for boite, plaintes, rebonds, envois in _q("""
            WITH envois AS (
                SELECT DISTINCT ev.email, ev.mailbox FROM email_events ev
                WHERE ev.site_code = %(site)s AND ev.event_type = 'sent'
                  AND ev.mailbox IS NOT NULL
                  AND ev.occurred_at >= now() - make_interval(hours => %(h)s)),
            reactions AS (
                SELECT e.mailbox, ev.event_type FROM email_events ev
                JOIN envois e ON e.email = ev.email
                WHERE ev.site_code = %(site)s
                  AND ev.event_type IN ('complaint', 'bounce')
                  AND ev.occurred_at >= now() - make_interval(hours => %(h)s))
            SELECT e.mailbox,
                   count(*) FILTER (WHERE r.event_type = 'complaint'),
                   count(*) FILTER (WHERE r.event_type = 'bounce'),
                   count(DISTINCT e.email)
            FROM envois e LEFT JOIN reactions r ON r.mailbox = e.mailbox
            GROUP BY 1""", {"site": site, "h": FENETRE_HEURES}):
        out[boite] = {"plaintes": int(plaintes or 0), "rebonds": int(rebonds or 0),
                      "envois": int(envois or 0)}
    return out


def controler(site: str = "lcr", appliquer: bool = True) -> dict:
    """Lève les pauses échues, en pose de nouvelles si les signaux le commandent."""
    from sante_envoi import SEUIL_REBOND

    bilan: dict = {"site": site, "levees": [], "posees": [], "signaux": {}}
    if appliquer:
        bilan["levees"] = lever_les_echues(site)

    signaux = _signaux(site)
    bilan["signaux"] = signaux
    for boite, s in signaux.items():
        if s["plaintes"] > 0:
            motif = (f"{s['plaintes']} plainte(s) sur {s['envois']} envois "
                     f"en {FENETRE_HEURES} h")
            bilan["posees"].append({"boite": boite, "heures": HEURES_PLAINTE,
                                    "motif": motif})
            if appliquer:
                mettre_au_repos(boite, HEURES_PLAINTE, motif)
            continue
        taux_rebond = (100.0 * s["rebonds"] / s["envois"]) if s["envois"] else 0.0
        if s["envois"] >= 20 and taux_rebond > SEUIL_REBOND:
            motif = (f"{s['rebonds']} rebonds sur {s['envois']} envois "
                     f"({taux_rebond:.1f} %) en {FENETRE_HEURES} h")
            bilan["posees"].append({"boite": boite, "heures": HEURES_REBOND,
                                    "motif": motif})
            if appliquer:
                mettre_au_repos(boite, HEURES_REBOND, motif)

    bilan["en_cours"] = pauses_en_cours(site)
    return bilan


def problemes(site: str = "lcr") -> dict[str, str]:
    """Les boîtes au repos, au format de `alertes.py` — pour que la baisse de volume
    s'explique. Une capacité qui chute sans raison visible se lit comme une panne."""
    out: dict[str, str] = {}
    try:
        for boite, p in pauses_en_cours(site).items():
            out[f"repos:{boite}"] = (
                f"🧊 *{boite} au repos* jusqu'au {p['jusqu_a'][:16]}.\n"
                f"   Motif : {p['motif']}.\n"
                f"   Reprise automatique à l'échéance. Les contacts attitrés à cette "
                f"boîte attendent — ils ne changent pas d'expéditeur.")
    except Exception as e:  # noqa: BLE001
        out["refroidissement"] = f"🧊 L'état des mises au repos est illisible : {e}"
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="lcr")
    ap.add_argument("--controler", action="store_true")
    a = ap.parse_args()
    print(json.dumps(controler(a.site, appliquer=a.controler), indent=2,
                     ensure_ascii=False, default=str))
