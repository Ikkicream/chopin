#!/usr/bin/env python3
"""Un nœud email peut suivre le secteur du contact (Lot E, 2026-08-26).

Un nœud portait UN message figé. Avec huit secteurs, il fallait huit scénarios en
parallèle — et une correction de tuyauterie à faire huit fois. Le principe posé pour
Mozart est que **le graphe affiché est celui qui s'exécute** : huit copies divergentes le
trahissent au premier correctif.

Un nœud porte donc `auto:first`, `auto:relance1` ou `auto:relance2` : « le cold email de
CE contact, à cette étape ». Le secteur est lu sur la fiche AU MOMENT DE L'ENVOI.

**La règle qui compte, et que ce fichier existe pour protéger : aucun repli.** Si le
secteur du contact n'a pas ce message, le nœud refuse. Envoyer l'email « immobilier » à un
plombier parce qu'il fallait bien envoyer quelque chose, c'est un message hors sujet, donc
un signalement pour spam, sur une adresse qu'on cherche justement à chauffer.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


import mozart
import email_templates_backend as etb

print("\nLe modèle est choisi d'après le secteur, jamais deviné")
_vrai_secteur = mozart._secteur_du_contact
try:
    mozart._secteur_du_contact = lambda e: "immobilier"
    sec, mid = mozart._modele_du_secteur("lcr", "x@y.fr", "first")
    verifie("un contact immobilier reçoit le cold email immobilier",
            mid == "cold:immobilier:first", f"({sec} → {mid})")

    sec, mid = mozart._modele_du_secteur("lcr", "x@y.fr", "relance1")
    verifie("l'étape demandée est respectée",
            mid == "cold:immobilier:relance1", f"({mid})")

    # Un secteur réel mais SANS modèle : c'est le cas qui pourrait produire un repli.
    mozart._secteur_du_contact = lambda e: "banque"
    sec, mid = mozart._modele_du_secteur("lcr", "x@y.fr", "first")
    verifie("un secteur sans modèle ne se replie sur AUCUN autre",
            mid == "", f"(secteur={sec}, modele={mid!r})")

    mozart._secteur_du_contact = lambda e: ""
    sec, mid = mozart._modele_du_secteur("lcr", "x@y.fr", "first")
    verifie("un contact sans secteur ne reçoit rien plutôt que n'importe quoi",
            mid == "", f"({mid!r})")

    mozart._secteur_du_contact = lambda e: "immobilier"
    sec, mid = mozart._modele_du_secteur("lcr", "x@y.fr", "etape-inventee")
    verifie("une étape inconnue ne résout rien", mid == "", f"({mid!r})")
finally:
    mozart._secteur_du_contact = _vrai_secteur

print("\nLe nœud refuse proprement, et le dit")
noeud = {"id": "n1", "type": "email",
         "data": {"message_id": "auto:first", "canal": "maildoso", "nom": "1er message"}}
sc = {"id": "0123456789ab", "site_code": "lcr"}
_vrai = mozart._secteur_du_contact
try:
    mozart._secteur_du_contact = lambda e: "banque"
    res, detail = mozart._envoyer(sc, noeud, {"email": "personne@exemple.fr"}, dry_run=True)
    verifie("refus quand le secteur n'a pas le message", res == "refuse", f"({res})")
    verifie("le refus nomme le secteur ET l'absence de repli",
            "banque" in detail and "repli" in detail, f"« {detail} »")
finally:
    mozart._secteur_du_contact = _vrai

print("\nL'activation prévient AVANT que des gens soient dans le scénario")
graphe_tous = {
    "nodes": [{"id": "d", "type": "declencheur", "data": {"secteurs": []}},
              {"id": "n1", "type": "email", "data": {"message_id": "auto:first", "nom": "1er"}}],
    "edges": [{"source": "d", "target": "n1"}],
}
pbs = mozart.verifier(graphe_tous)
sans_modele = [s["sector"] for s in etb.list_sectors("lcr")
               if not etb._get_one("lcr", s["sector"], "first")]
if sans_modele:
    verifie("les secteurs non couverts sont signalés",
            any("secteur du contact" in p for p in pbs), f"({sans_modele})")
else:
    verifie("aucun faux problème quand tous les secteurs sont couverts",
            not any("secteur du contact" in p for p in pbs), f"({pbs})")

graphe_ciblé = {
    "nodes": [{"id": "d", "type": "declencheur", "data": {"secteurs": ["immobilier"]}},
              {"id": "n1", "type": "email", "data": {"message_id": "auto:first", "nom": "1er"}}],
    "edges": [{"source": "d", "target": "n1"}],
}
verifie("un déclencheur ciblé sur un secteur couvert ne lève rien",
        not [p for p in mozart.verifier(graphe_ciblé) if "secteur du contact" in p],
        f"({[p for p in mozart.verifier(graphe_ciblé) if 'secteur' in p]})")

graphe_etape_fausse = {
    "nodes": [{"id": "d", "type": "declencheur", "data": {"secteurs": ["immobilier"]}},
              {"id": "n1", "type": "email", "data": {"message_id": "auto:relance9", "nom": "1er"}}],
    "edges": [{"source": "d", "target": "n1"}],
}
verifie("une étape inventée bloque l'activation",
        any("n'existe pas" in p for p in mozart.verifier(graphe_etape_fausse)))

print("\nCe qui existait continue de marcher")
graphe_fige = {
    "nodes": [{"id": "d", "type": "declencheur", "data": {}},
              {"id": "n1", "type": "email",
               "data": {"message_id": "cold:immobilier:first", "nom": "1er"}}],
    "edges": [{"source": "d", "target": "n1"}],
}
verifie("un message figé ne déclenche aucun contrôle de secteur",
        not [p for p in mozart.verifier(graphe_fige) if "secteur du contact" in p])
verifie("un nœud sans message reste bloquant",
        any("n'a pas de message" in p for p in mozart.verifier(
            {"nodes": [{"id": "d", "type": "declencheur", "data": {}},
                       {"id": "n1", "type": "email", "data": {"nom": "1er"}}],
             "edges": [{"source": "d", "target": "n1"}]})))

print("\nLe journal retient le modèle RÉSOLU, pas le raccourci")
src = (RACINE / "scripts" / "mozart.py").read_text()
verifie("`mid` est réécrit avant l'envoi", "mid = resolu" in src)
i_res, i_mark = src.find("mid = resolu"), src.rfind("modele=mid")
verifie("l'attribution utilise donc le vrai modèle, pas « auto:first »",
        i_res > 0 and i_mark > i_res, f"({i_res} < {i_mark})")

print("\nUne campagne n'a pas cette option")
import time

import html_templates_backend as htb


def _cles(auto: bool):
    """`god_mode.duckdb` n'admet qu'un écrivain : le scraping ou l'API le tiennent
    régulièrement. On réessaie, puis on renonce — un contrôle ignoré vaut mieux qu'un
    échec qui n'apprend rien sur le code."""
    for _ in range(6):
        try:
            return {g["key"] for g in htb.campaign_message_options("lcr", auto=auto)["groups"]}
        except Exception:  # noqa: BLE001
            time.sleep(3)
    return None


cles_campagne, cles_scenario = _cles(False), _cles(True)
if cles_campagne is None or cles_scenario is None:
    print("  …  base occupée, contrôle des options ignoré")
else:
    verifie("pas de message variable dans une campagne", "auto" not in cles_campagne)
    verifie("mais bien dans un scénario", "auto" in cles_scenario)

print("\n" + "=" * 62)
if ECHECS:
    print(f"{len(ECHECS)} ÉCHEC(S) : " + ", ".join(ECHECS))
    raise SystemExit(1)
print("Tout est vert.")
