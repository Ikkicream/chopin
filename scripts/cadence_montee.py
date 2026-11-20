#!/usr/bin/env python3
"""cadence_montee.py — pose une cadence de montée en charge sur une campagne.

Objectif de Camille (2026-08-23) : **140 emails/jour d'ici la fin de la semaine**, puis
40/jour et par compte à partir de septembre — soit 160/jour sur quatre boîtes.

On monte par paliers plutôt que d'ouvrir le robinet d'un coup. Un domaine jeune qui passe
de 25 à 160 envois quotidiens se signale tout seul : le volume est le premier critère de
filtrage des fournisseurs, avant même le contenu. La progression laisse aussi le temps aux
signaux de remonter — un rebond met quelques minutes, une plainte quelques heures, une
chute du taux d'ouverture un à deux jours. Monter plus vite que ces délais, c'est décider
sans jamais lire la réponse.

Deux garde-fous, tenus ailleurs et rappelés ici :
  - le plafond par boîte (`maildoso_ramp`) redescend tout seul sur une plainte, un rebond
    ou une chute d'ouverture — la cadence PROPOSE, les boîtes DISPOSENT ;
  - le dimanche et les heures hors 08h01–17h59 sont refusés par `deliverability_agent` :
    un jour sauté est rattrapé le lendemain, pas perdu.

Usage :
    python3 scripts/cadence_montee.py <campagne>              # montre la cadence proposée
    python3 scripts/cadence_montee.py <campagne> --apply
    python3 scripts/cadence_montee.py <campagne> --paliers 80,100,120,130,140
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

# Paliers par défaut, en emails par JOUR OUVRÉ (lundi-samedi). Le dernier est répété
# jusqu'à épuisement de la cible.
PALIERS = [80, 100, 120, 130, 140]


def _jours_ouvres(depart: date, combien: int) -> list[date]:
    """Les prochains jours d'envoi : lundi à samedi, le dimanche est sauté."""
    out, j = [], depart
    while len(out) < combien:
        if j.weekday() != 6:          # 6 = dimanche
            out.append(j)
        j += timedelta(days=1)
    return out


def proposer(legacy_id: str, paliers: list[int] | None = None,
             depart: date | None = None) -> dict:
    import campaign_engine as ce

    camp = ce.get_campaign(legacy_id)
    if not camp:
        return {"ok": False, "error": f"campagne {legacy_id} introuvable"}

    cible = int(camp.get("target_size") or 0)
    envoyes = int(camp.get("sent_count") or 0)
    reste = max(0, cible - envoyes)
    if reste == 0:
        return {"ok": False, "error": "campagne déjà complète", "cible": cible,
                "envoyes": envoyes}

    paliers = paliers or PALIERS
    # Demain, jamais aujourd'hui : le lot du jour a pu partir sous l'ancienne cadence.
    depart = depart or (date.today() + timedelta(days=1))

    # Ce qui est DÉJÀ parti doit figurer dans le plan. `_todays_allowance` compare le
    # cumul prévu au `sent_count` TOTAL de la campagne : une cadence qui ne planifie que
    # le reliquat démarre donc en dette de tout l'historique, et n'autorise aucun envoi
    # tant que le cumul n'a pas rattrapé les 309 déjà partis — soit rien du lundi au
    # mercredi, puis 140 d'un coup. On ouvre donc le plan par une ligne datée d'hier qui
    # porte l'acquis : elle ne déclenche aucun envoi (elle est au passé) et remet le
    # cumul à zéro relatif.
    cadence, cumul = [], 0
    if envoyes:
        cadence.append({"date": (depart - timedelta(days=1)).isoformat(),
                        "count": envoyes, "acquis": True})
    # Assez de jours pour épuisier le reliquat au dernier palier, plus une marge.
    besoin = len(paliers) + (reste // max(1, paliers[-1])) + 2
    for i, j in enumerate(_jours_ouvres(depart, besoin)):
        if cumul >= reste:
            break
        volume = paliers[i] if i < len(paliers) else paliers[-1]
        volume = min(volume, reste - cumul)
        cadence.append({"date": j.isoformat(), "count": volume})
        cumul += volume

    return {"ok": True, "campagne": legacy_id, "nom": camp.get("name"),
            "cible": cible, "envoyes": envoyes, "reste": reste,
            "cadence": cadence, "total_planifie": cumul,
            "dernier_jour": cadence[-1]["date"] if cadence else None,
            "atteint_140_le": next((c["date"] for c in cadence if c["count"] >= 140), None)}


def appliquer(legacy_id: str, cadence: list[dict]) -> dict:
    import campaign_engine as ce
    ce._ecrire("UPDATE campaigns SET cadence = %s::jsonb WHERE legacy_id = %s",
               [json.dumps(cadence), legacy_id])
    camp = ce.get_campaign(legacy_id)
    return {"ok": True, "cadence_en_base": camp.get("cadence")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("campagne")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--paliers", default=None,
                    help="volumes par jour ouvré, séparés par des virgules")
    a = ap.parse_args()
    paliers = [int(x) for x in a.paliers.split(",")] if a.paliers else None
    p = proposer(a.campagne, paliers)
    if p.get("ok") and a.apply:
        p["applique"] = appliquer(a.campagne, p["cadence"])
    print(json.dumps(p, indent=2, ensure_ascii=False))
