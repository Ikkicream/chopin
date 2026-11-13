#!/usr/bin/env python3
"""programmation.py — la file d'envoi ne doit jamais se vider.

Constat de Camille (2026-08-23) : « nous allons scrapper plus de 500 contacts par jour,
donc 140 emails/jour ne sera pas un problème — sauf s'il n'y a pas de programmation. »
C'est exact, et c'est le vrai risque du Lot 4. La matière ne manque pas : 5 659 contacts
piochables ce soir, plus de 500 collectés chaque jour. Ce qui manque, c'est la CERTITUDE
qu'une campagne aura quelque chose à dispatcher demain matin. La cadence posée sur la
campagne en cours s'épuise samedi ; le dimanche suivant, plus rien ne part, et personne
n'est prévenu — le tableau de bord affiche « done », ce qui ressemble à un succès.

Le module fait donc deux choses, et la frontière entre les deux est délibérée :

  - **il PROLONGE tout seul** ce qui est mécanique : une campagne en cours dont la
    cadence arrive à son terme alors que le vivier est plein n'a besoin d'aucune décision
    humaine. Même message, même ciblage, on ajoute des jours ;
  - **il ALERTE** sur ce qui est un choix : plus aucune campagne active, ou un vivier
    épuisé sur les secteurs visés. Choisir un message et une cible n'est pas automatisable,
    et prétendre le faire produirait des envois que personne n'a validés.

L'objectif quotidien n'est pas un nombre écrit en dur : c'est **la somme des plafonds des
boîtes actives**. Il se règle donc tout seul — si `maildoso_ramp` abaisse un plafond après
une plainte, l'objectif baisse avec lui, et la programmation cesse de réclamer un volume
que la délivrabilité ne permet plus.

Usage :
    python3 scripts/programmation.py              # état de la file, n'écrit rien
    python3 scripts/programmation.py --apply      # prolonge ce qui doit l'être
    python3 scripts/programmation.py --jours 14
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

HORIZON_JOURS = 7           # on veut voir venir une semaine d'envois
SEUIL_ALERTE_JOURS = 3      # moins de 3 jours couverts → on prévient
MARGE_VIVIER = 1.2          # on ne planifie pas plus de 80 % du vivier piochable


def _jours_ouvres(depart: date, combien: int) -> list[date]:
    """Lundi à samedi. Le dimanche ne compte pas : rien n'y part, et le planifier
    donnerait l'illusion d'une couverture qui n'existe pas."""
    out, j = [], depart
    while len(out) < combien:
        if j.weekday() != 6:
            out.append(j)
        j += timedelta(days=1)
    return out


def objectif_jour(site: str) -> int:
    """Le volume visé par jour : la somme des plafonds des boîtes ACTIVES.

    Pas une constante : c'est la délivrabilité qui commande. `maildoso_ramp` baisse un
    plafond dès qu'une plainte, un rebond ou une chute d'ouverture apparaît ; l'objectif
    suit, et la programmation cesse de réclamer un volume qu'on ne peut plus tenir.
    """
    import expediteur
    # Ad hoc seulement : la programmation d'une campagne ne peut pas compter sur les
    # adresses réservées aux scénarios Mozart.
    return sum(b["daily_cap"] for b in expediteur.boites(site, usage="adhoc") if b["active"])


def vivier(site: str, secteurs: list[str] | None) -> int:
    """Combien de contacts sont piochables MAINTENANT sur ces secteurs.

    Sert de borne haute au plan : promettre 140 envois par jour pendant une semaine quand
    le vivier en contient 200, c'est écrire une cadence qui ne sera jamais tenue et
    masquer le vrai problème — qui est de collecte, pas de programmation.
    """
    import pool_pg
    vus = 0
    for sec in (secteurs or []):
        vus += pool_pg.count_available_for_sector(site, sec)
    return vus


def diagnostic(site: str = "lcr", jours: int = HORIZON_JOURS) -> dict:
    """Ce qui partira réellement chaque jour ouvré de l'horizon, et ce qui manque."""
    import campaign_engine as ce

    objectif = objectif_jour(site)
    campagnes = [c for c in (ce.list_campaigns(site) or [])
                 if c.get("status") in ce.ACTIVE_STATUSES]

    # Projection JOUR APRÈS JOUR, en décrémentant ce qui reste à mesure. Sans cela, chaque
    # jour est calculé sur le `sent_count` d'aujourd'hui : une campagne à qui il reste 691
    # envois « couvre » sept jours à 140, alors qu'elle s'épuise au cinquième. L'alerte
    # partirait le lendemain du jour où plus rien n'est parti — c'est-à-dire trop tard,
    # et c'est précisément le trou que ce module est là pour voir venir.
    couverture: dict[str, int] = {}
    restes = {c.get("id"): max(0, (c.get("target_size") or 0) - (c.get("sent_count") or 0))
              for c in campagnes}
    envoye_simule = {c.get("id"): (c.get("sent_count") or 0) for c in campagnes}
    for j in _jours_ouvres(date.today() + timedelta(days=1), jours):
        total = 0
        for c in campagnes:
            if str(c.get("schedule_start", ""))[:10] > j.isoformat():
                continue
            cid = c.get("id")
            if restes[cid] <= 0:
                continue
            vue = dict(c, sent_count=envoye_simule[cid])
            part = min(ce._todays_allowance(vue, j), restes[cid])
            restes[cid] -= part
            envoye_simule[cid] += part
            total += part
        couverture[j.isoformat()] = total

    # Un jour est COUVERT dès qu'il a du volume prévu, pas seulement quand il atteint la
    # capacité des boîtes. La distinction compte : cette semaine est une montée en charge
    # délibérée (80 puis 100 puis 120…), et exiger 160 dès lundi ferait crier l'alerte
    # contre un plan qu'on vient de poser exprès. Ce que Camille redoute, et ce qu'on
    # surveille ici, c'est le jour où il n'y a RIEN à envoyer.
    jours_couverts = 0
    for j in sorted(couverture):
        if couverture[j] > 0:
            jours_couverts += 1
        else:
            break

    return {
        "site": site,
        "objectif_par_jour": objectif,
        "campagnes_actives": [{"id": c.get("id"), "nom": c.get("name"),
                               "canal": c.get("channel"),
                               "reste": max(0, (c.get("target_size") or 0)
                                            - (c.get("sent_count") or 0)),
                               "secteurs": c.get("sectors") or []}
                              for c in campagnes],
        "couverture": couverture,
        "jours_pleins_devant": jours_couverts,
        # Le premier jour SANS RIEN — même définition que la couverture ci-dessus, sans
        # quoi les deux se contredisent et l'alerte annonce un creux le jour où la montée
        # en charge commence.
        "premier_jour_creux": next((j for j in sorted(couverture)
                                    if couverture[j] <= 0), None),
        "sous_objectif": {j: v for j, v in couverture.items() if 0 < v < objectif},
        "suffisant": jours_couverts >= SEUIL_ALERTE_JOURS,
    }


def assurer(site: str = "lcr", jours: int = HORIZON_JOURS, apply: bool = False) -> dict:
    """Prolonge les campagnes en cours pour couvrir l'horizon. Ne crée jamais de campagne.

    Créer une campagne, c'est choisir un message et une cible : une décision, pas une
    mécanique. Quand il n'y a plus rien à prolonger, on alerte au lieu d'inventer.
    """
    import campaign_engine as ce

    d = diagnostic(site, jours)
    d["apply"] = apply
    d["actions"] = []
    if d["suffisant"]:
        d["actions"].append("rien à faire — la file couvre l'horizon")
        return d

    campagnes = [c for c in (ce.list_campaigns(site) or [])
                 if c.get("status") in ce.ACTIVE_STATUSES]
    if not campagnes:
        d["actions"].append("AUCUNE campagne active — il faut en créer une "
                            "(choix du message et du ciblage : décision humaine)")
        return d

    # On prolonge la campagne active la plus avancée : c'est celle dont le message a déjà
    # été jugé sur ses résultats, donc celle qu'on prolonge avec le moins de risque.
    camp = max(campagnes, key=lambda c: c.get("sent_count") or 0)
    dispo = vivier(site, camp.get("sectors"))
    objectif = d["objectif_par_jour"]
    besoin_jours = _jours_ouvres(date.today() + timedelta(days=1), jours)
    # On ne comble que les jours VIDES, et à hauteur de l'objectif : rehausser un palier
    # de montée en charge reviendrait à défaire la montée elle-même.
    manquant = sum(objectif for j in besoin_jours
                   if d["couverture"].get(j.isoformat(), 0) <= 0)

    plafond_vivier = int(dispo / MARGE_VIVIER)
    a_ajouter = min(manquant, plafond_vivier)
    d["vivier_piochable"] = dispo
    d["manquant_sur_horizon"] = manquant
    d["a_ajouter"] = a_ajouter

    if a_ajouter <= 0:
        d["actions"].append(
            f"vivier insuffisant sur {', '.join(camp.get('sectors') or []) or 'ces secteurs'} "
            f"({dispo} piochables) — c'est un problème de COLLECTE, pas de programmation")
        return d

    cadence = list(camp.get("cadence") or [])
    dernier = max((str(x.get("date", "")) for x in cadence), default="")
    ajoutes, cumul = [], 0
    for j in besoin_jours:
        if cumul >= a_ajouter:
            break
        if j.isoformat() <= dernier:
            continue
        volume = min(objectif, a_ajouter - cumul)
        ajoutes.append({"date": j.isoformat(), "count": volume})
        cumul += volume

    d["cadence_ajoutee"] = ajoutes
    d["nouvelle_cible"] = (camp.get("target_size") or 0) + cumul
    d["actions"].append(
        f"prolonger « {camp.get('name')} » de {cumul} envois sur {len(ajoutes)} jour(s), "
        f"cible {camp.get('target_size')} → {d['nouvelle_cible']}")

    if apply and ajoutes:
        ce._ecrire("UPDATE campaigns SET cadence = %s::jsonb, target_size = %s "
                   "WHERE legacy_id = %s",
                   [json.dumps(cadence + ajoutes), d["nouvelle_cible"], camp.get("id")])
        d["applique"] = True
        d["verification"] = diagnostic(site, jours)
    return d


def problemes(site: str = "lcr") -> dict[str, str]:
    """Trous de programmation, au format de `alertes.py`."""
    try:
        d = diagnostic(site)
    except Exception as e:  # noqa: BLE001
        return {"programmation": f"📭 La programmation des envois est illisible : {e}"}
    if d["suffisant"]:
        return {}
    if not d["campagnes_actives"]:
        return {"programmation:vide": (
            "📭 *Aucune campagne active* — plus aucun email ne partira.\n"
            "   Le vivier est plein, c'est la programmation qui manque : créer une "
            "campagne (message + ciblage).")}
    return {"programmation:creux": (
        f"📭 *Trou de programmation* : plus rien de prévu à partir du "
        f"{d['premier_jour_creux']} — {d['jours_pleins_devant']} jour(s) d'envois "
        f"devant nous.\n"
        f"   Le vivier n'est pas en cause : c'est la cadence qui s'arrête. "
        f"Prolonger une campagne ou en créer une.")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="lcr")
    ap.add_argument("--jours", type=int, default=HORIZON_JOURS)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    print(json.dumps(assurer(a.site, a.jours, apply=a.apply), indent=2,
                     ensure_ascii=False, default=str))
