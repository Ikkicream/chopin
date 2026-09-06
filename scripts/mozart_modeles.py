#!/usr/bin/env python3
"""mozart_modeles.py — les trois scénarios de départ, verrouillés.

Trois formes, et pas trente : **un message**, **une relance**, **deux relances**. Elles
couvrent l'écrasante majorité des séquences de prospection, et surtout elles se lisent en
entier. Un catalogue de modèles qu'on doit parcourir coûte plus de temps qu'il n'en fait
gagner.

Chacun est **verrouillé**. Ce n'est pas une méfiance : on ouvre un modèle pour s'en
inspirer, on ajuste un délai « juste pour voir », et trois clics plus tard le point de
départ commun n'existe plus. Le cadenas force le geste juste — **dupliquer** — et le
modèle reste intact pour la fois suivante et pour tout le monde.

Les délais retenus viennent de la pratique du cold email, pas d'un tirage :
  - **J+1** avant le premier message : le contact vient d'être collecté et vérifié ;
    écrire dans la minute n'apporte rien et concentre les envois.
  - **J+4** pour la première relance : assez pour qu'un message non lu le reste, assez peu
    pour qu'on se souvienne du premier.
  - **J+7** pour la seconde : au-delà, la relance ne relance plus rien, elle recommence.

Chaque relance est branchée sur la branche « n'a pas ouvert ». Relancer quelqu'un qui a
ouvert, c'est le punir d'avoir lu.

Usage :
    python3 scripts/mozart_modeles.py --site lcr            # état
    python3 scripts/mozart_modeles.py --site lcr --creer
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

X, Y = 120, 40
PAS = 150


def _n(nid, type_, rang, data, colonne=0):
    return {"id": nid, "type": type_,
            "position": {"x": X + colonne * 260, "y": Y + rang * PAS},
            "data": data}


def _graphe(relances: int) -> dict:
    """Le graphe d'un modèle à `relances` relance(s)."""
    noeuds = [
        _n("declencheur", "declencheur", 0,
           {"nom": "Nouveaux contacts", "depuis_jours": 7, "secteurs": []}),
        _n("attente1", "delai", 1, {"nom": "Laisser passer 1 jour", "duree": 1, "unite": "jours"}),
        _n("message1", "email", 2,
           {"nom": "Premier message", "canal": "maildoso", "message_id": ""}),
    ]
    liens = [
        {"id": "l0", "source": "declencheur", "target": "attente1"},
        {"id": "l1", "source": "attente1", "target": "message1"},
    ]
    precedent, rang = "message1", 3
    delais = [4, 7]

    for i in range(1, relances + 1):
        att, cond, msg = f"attente{i+1}", f"ouvert{i}", f"relance{i}"
        noeuds += [
            _n(att, "delai", rang,
               {"nom": f"Laisser passer {delais[i-1]} jours", "duree": delais[i-1],
                "unite": "jours"}),
            _n(cond, "condition", rang + 1,
               {"nom": "A-t-il ouvert ?", "sur": "ouvert"}),
            _n(msg, "email", rang + 2,
               {"nom": f"Relance {i}", "canal": "maildoso", "message_id": ""}, colonne=1),
        ]
        liens += [
            {"id": f"a{i}", "source": precedent, "target": att},
            {"id": f"c{i}", "source": att, "target": cond},
            # « Oui » sort du parcours : relancer quelqu'un qui a ouvert, c'est le punir
            # d'avoir lu. « Non » relance.
            {"id": f"o{i}", "source": cond, "target": "fin", "sourceHandle": "oui"},
            {"id": f"r{i}", "source": cond, "target": msg, "sourceHandle": "non"},
        ]
        precedent, rang = msg, rang + 3

    noeuds.append(_n("fin", "fin", rang, {"nom": "Fin du parcours"}))
    liens.append({"id": "lf", "source": precedent, "target": "fin"})
    return {"nodes": noeuds, "edges": liens}


MODELES = [
    {"nom": "Modèle · 1 message, sans relance",
     "description": "Un seul envoi, un jour après la collecte. Le plus sobre : à utiliser "
                    "quand le message se suffit ou que la liste est fragile.",
     "relances": 0},
    {"nom": "Modèle · 1 message + 1 relance",
     "description": "Le message, puis une relance à J+4 pour ceux qui n'ont pas ouvert. "
                    "Le meilleur rapport effort/résultat dans la plupart des cas.",
     "relances": 1},
    {"nom": "Modèle · 1 message + 2 relances",
     "description": "Deux relances, à J+4 puis J+7, toujours réservées aux non-ouvreurs. "
                    "Pour une cible froide qu'on veut travailler au corps.",
     "relances": 2},
]


def etat(site: str) -> list[dict]:
    import mozart
    return [{"nom": s["nom"], "verrouille": s["verrouille"], "id": s["id"]}
            for s in mozart.scenarios(site) if s.get("est_modele")]


def creer(site: str, refaire: bool = False) -> dict:
    """Crée les modèles manquants. Idempotent : ne double jamais un modèle existant."""
    import mozart
    import pool_pg

    presents = {s["nom"] for s in mozart.scenarios(site) if s.get("est_modele")}
    crees, ignores = [], []
    for m in MODELES:
        if m["nom"] in presents and not refaire:
            ignores.append(m["nom"])
            continue
        g = _graphe(m["relances"])
        c = pool_pg._conn()
        try:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO mozart_scenarios (site_code, nom, description, statut,
                                                  graphe, cree_par, est_modele, verrouille)
                    VALUES (%s, %s, %s, 'brouillon', %s::jsonb, 'modeles', true, true)
                    RETURNING id""",
                    (site, m["nom"], m["description"], json.dumps(g)))
                crees.append({"nom": m["nom"], "id": str(cur.fetchone()[0]),
                              "noeuds": len(g["nodes"])})
            c.commit()
        finally:
            pool_pg._rendre(c)
    return {"crees": crees, "deja_presents": ignores}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="lcr")
    ap.add_argument("--creer", action="store_true")
    a = ap.parse_args()
    print(json.dumps(creer(a.site) if a.creer else {"modeles": etat(a.site)},
                     indent=1, ensure_ascii=False))
