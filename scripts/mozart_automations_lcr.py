#!/usr/bin/env python3
"""Les cinq automatisations Mozart de LCR — choisies sur les volumes, pas au jugé.

Mesuré le 2026-08-25 sur les contacts du site :

    secteur            contactables   collectés en 30 j
    immobilier                3 869               2 692
    restaurant                1 162               1 979   ← aucun email disponible
    agence-marketing          1 113                 862
    autre                     1 112                  41
    retail / artisan…            ~45                  ~1

Deux enseignements. D'abord **immobilier et agences portent tout** : 4 982 contacts
contactables à eux deux, contre une cinquantaine pour l'ensemble des commerces de
proximité. Ensuite **restaurant est le premier gisement de la collecte** — 1 979 fiches en
trente jours — et il n'a aucun argumentaire : ces contacts dorment.

Les cinq scénarios ci-dessous sont créés en **brouillon**. Aucun n'envoie tant que Camille
ne l'active pas : mettre en route un envoi automatique n'est pas une décision d'outil.

Trois principes tenus dans chaque graphe :
  - **J+1 avant le premier message.** Le contact vient d'être collecté et vérifié ; écrire
    dans la minute n'apporte rien et concentre les envois sur une heure.
  - **Les relances ne partent qu'aux non-réactifs.** Relancer quelqu'un qui a ouvert, c'est
    le punir d'avoir lu.
  - **Délais croissants (J+4 puis J+7).** Au-delà, une relance ne relance plus rien : elle
    recommence.

Usage :
    python3 scripts/mozart_automations_lcr.py --site lcr           # état
    python3 scripts/mozart_automations_lcr.py --site lcr --creer
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

X, Y, PAS = 120, 40, 150


def _n(nid, type_, rang, data, colonne=0):
    return {"id": nid, "type": type_,
            "position": {"x": X + colonne * 260, "y": Y + rang * PAS}, "data": data}


def _sequence(secteur: str, messages: list[str], sur: str = "ouvert",
              delais: list[int] | None = None, depuis_jours: int = 7) -> dict:
    """Un graphe : déclencheur → J+1 → message, puis une branche par relance.

    `messages` porte les identifiants `cold:secteur:kind`, dans l'ordre. `sur` dit sur quoi
    la condition tranche — « ouvert » pour une prospection froide, « clique » quand on veut
    trier des gens qui lisent déjà.
    """
    delais = delais or [4, 7]
    noeuds = [
        _n("declencheur", "declencheur", 0,
           {"nom": "Nouveaux contacts", "depuis_jours": depuis_jours, "secteurs": [secteur]}),
        _n("attente1", "delai", 1, {"nom": "Laisser passer 1 jour", "duree": 1, "unite": "jours"}),
        _n("message1", "email", 2,
           {"nom": "Premier message", "canal": "maildoso", "message_id": messages[0]}),
    ]
    liens = [{"id": "l0", "source": "declencheur", "target": "attente1"},
             {"id": "l1", "source": "attente1", "target": "message1"}]
    precedent, rang = "message1", 3

    for i, mid in enumerate(messages[1:], start=1):
        att, cond, msg = f"attente{i+1}", f"reaction{i}", f"relance{i}"
        d = delais[i - 1] if i - 1 < len(delais) else delais[-1]
        noeuds += [
            _n(att, "delai", rang, {"nom": f"Laisser passer {d} jours", "duree": d,
                                    "unite": "jours"}),
            _n(cond, "condition", rang + 1,
               {"nom": "A-t-il ouvert ?" if sur == "ouvert" else "A-t-il cliqué ?",
                "sur": sur}),
            _n(msg, "email", rang + 2,
               {"nom": f"Relance {i}", "canal": "maildoso", "message_id": mid}, colonne=1),
        ]
        liens += [
            {"id": f"a{i}", "source": precedent, "target": att},
            {"id": f"c{i}", "source": att, "target": cond},
            {"id": f"o{i}", "source": cond, "target": "fin", "sourceHandle": "oui"},
            {"id": f"r{i}", "source": cond, "target": msg, "sourceHandle": "non"},
        ]
        precedent, rang = msg, rang + 3

    noeuds.append(_n("fin", "fin", rang, {"nom": "Fin du parcours"}))
    liens.append({"id": "lf", "source": precedent, "target": "fin"})
    return {"nodes": noeuds, "edges": liens}


AUTOMATISATIONS = [
    {
        "nom": "1 · Immobilier — nouveaux arrivants",
        "description": ("Le gisement principal : 3 869 agences contactables, 2 692 "
                        "collectées en trente jours. Séquence complète — accroche sur la "
                        "fin du démarchage téléphonique, relance chiffrée, puis rupture. "
                        "Les relances ne partent qu'aux non-ouvreurs."),
        "graphe": _sequence("immobilier",
                            ["cold:immobilier:first", "cold:immobilier:relance1",
                             "cold:immobilier:relance2"]),
    },
    {
        "nom": "2 · Agences marketing — nouveaux arrivants",
        "description": ("1 113 agences contactables. L'angle est la MARGE qui sort de chez "
                        "elles quand un client demande du SMS, pas la fonctionnalité. "
                        "Séquence complète, relances aux non-ouvreurs."),
        "graphe": _sequence("agence-marketing",
                            ["cold:agence-marketing:first", "cold:agence-marketing:relance1",
                             "cold:agence-marketing:relance2"]),
    },
    {
        "nom": "3 · Agences — celles qui lisent mais ne cliquent pas",
        "description": ("Même population, autre moment : on attend une semaine, et on ne "
                        "relance QUE ceux qui n'ont pas cliqué. Ceux qui ont cliqué sont "
                        "déjà en conversation — les rappeler les fait reculer. L'angle "
                        "bascule sur la conformité des leads (LeLead), un sujet différent "
                        "du premier message."),
        "graphe": _sequence("agence-marketing",
                            ["cold:lelead:first", "cold:lelead:relance1"],
                            sur="clique", delais=[7], depuis_jours=30),
    },
    {
        "nom": "4 · Immobilier — reprise à froid (90 jours)",
        "description": ("Les agences collectées il y a plus d'un mois et jamais relancées. "
                        "Un seul message, celui de rupture : il obtient 10 à 15 % de "
                        "réponses sur une cible froide, précisément parce qu'il ne demande "
                        "rien. À lancer une fois, pas en continu."),
        "graphe": _sequence("immobilier", ["cold:immobilier:relance2"], depuis_jours=90),
    },
    {
        "nom": "5 · Restaurant — EN ATTENTE D'ARGUMENTAIRE",
        "description": ("1 979 fiches collectées en trente jours, 1 162 contactables — le "
                        "premier gisement de la collecte, et il dort. Le scénario est prêt "
                        "mais SANS message : l'argumentaire restaurant est en attente "
                        "(décision du 2026-08-23). Dès qu'il existe, il suffit de le "
                        "choisir sur les nœuds et d'activer."),
        "graphe": _sequence("restaurant", ["", ""], delais=[4]),
    },
]


def etat(site: str) -> list[dict]:
    import mozart
    connus = {a["nom"] for a in AUTOMATISATIONS}
    return [{"nom": s["nom"], "statut": s["statut"], "id": s["id"]}
            for s in mozart.scenarios(site) if s["nom"] in connus]


def creer(site: str) -> list[dict]:
    """Crée ce qui manque, en brouillon. Idempotent : un scénario du même nom est ignoré."""
    import mozart
    existants = {s["nom"] for s in mozart.scenarios(site)}
    faits = []
    for a in AUTOMATISATIONS:
        if a["nom"] in existants:
            faits.append({"nom": a["nom"], "cree": False, "raison": "existe déjà"})
            continue
        # `_ecrire` et NON `_q` : le second est l'assistant de LECTURE, il ne valide pas la
        # transaction. L'INSERT s'exécutait puis disparaissait au rollback, pendant que ce
        # script annonçait « créé ». Un message de succès n'est pas une vérification.
        n = mozart._ecrire("""
            INSERT INTO mozart_scenarios (site_code, nom, description, statut, graphe, cree_par)
            VALUES (%(s)s, %(n)s, %(d)s, 'brouillon', %(g)s::jsonb, 'automations-lcr')""",
            {"s": site, "n": a["nom"], "d": a["description"],
             "g": json.dumps(a["graphe"], ensure_ascii=False)})
        faits.append({"nom": a["nom"], "cree": bool(n)})
    return faits


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="lcr")
    ap.add_argument("--creer", action="store_true")
    args = ap.parse_args()
    if args.creer:
        for f in creer(args.site):
            print(("  créé   " if f["cree"] else "  ignoré ") + f["nom"]
                  + ("" if f["cree"] else f" ({f.get('raison','')})"))
        # On relit la base : c'est elle qui dit ce qui existe, pas le retour de l'INSERT.
        presents = {e["nom"] for e in etat(args.site)}
        manquants = [a["nom"] for a in AUTOMATISATIONS if a["nom"] not in presents]
        print(f"\n  vérification : {len(presents)}/{len(AUTOMATISATIONS)} en base"
              + (f" — MANQUANTS : {manquants}" if manquants else ""))
    else:
        for e in etat(args.site):
            print(f"  {e['statut']:10} {e['nom']}")
