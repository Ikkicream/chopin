#!/usr/bin/env python3
"""Chaque envoi doit dire QUEL modèle est parti (Lot B, 2026-08-26).

Le journal ne retenait que la campagne. La galerie ne pouvait donc afficher que des
chiffres par SECTEUR, partagés par les trois emails du secteur — et prêtait à chacun le
mérite du seul qui partait réellement. Mesuré le jour de la bascule : `cold:immobilier:first`
avait produit 1 103 envois et 506 ouvertures ; les 23 autres modèles, zéro. Les trois
emails « immobilier » affichaient pourtant les mêmes 46 %.

Ce test ne touche PAS la base : il remplace le miroir PostgreSQL par un espion et vérifie
que `modele` traverse toute la chaîne. Un envoi réel, lui, poserait une ligne de
suppression de 120 jours sur une vraie adresse.
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


print("\nLa signature accepte le modèle")
import inspect

import pg_sync
import contacts_pool_backend as cpb

verifie("pg_sync.record_send prend `modele`",
        "modele" in inspect.signature(pg_sync.record_send).parameters)
verifie("mark_pushed_to_emelia prend `modele`",
        "modele" in inspect.signature(cpb.mark_pushed_to_emelia).parameters)


print("\nLe modèle descend jusqu'au journal")
vu: dict = {}


def _faux_record_event(email, event_type, site_code, channel, **k):
    vu.update({"email": email, "type": event_type, "meta": k.get("meta")})
    return True


_vrai = pg_sync.record_event
pg_sync.record_event = _faux_record_event
try:
    pg_sync.record_send("a@exemple.fr", "lcr", campaign_id="lcr-abc-2026-08-26",
                        mailbox="j.durand@leclient-roi.com", modele="cold:immobilier:first")
    verifie("record_send écrit meta.modele",
            (vu.get("meta") or {}).get("modele") == "cold:immobilier:first",
            f"({vu.get('meta')})")

    vu.clear()
    pg_sync.record_send("b@exemple.fr", "lcr", campaign_id="lcr-abc-2026-08-26")
    verifie("sans modèle, meta reste vide (jamais de valeur inventée)",
            not (vu.get("meta") or {}).get("modele"), f"({vu.get('meta')})")
finally:
    pg_sync.record_event = _vrai


print("\nLes deux chemins d'envoi transmettent le modèle")
for fichier, attendu in (("campaign_engine.py", "modele=modele"),
                         ("mozart.py", "modele=mid")):
    src = (RACINE / "scripts" / fichier).read_text()
    appels = src.count("mark_pushed_to_emelia(")
    avec = src.count(attendu)
    # `campaign_engine` porte un appel de plus dans `reconcile_from_sent_log`, qui répare
    # un historique et n'a pas le message sous la main : la reprise le lui donnera.
    verifie(f"{fichier} passe le modèle à ses envois",
            avec >= 1 and avec >= appels - 2, f"({avec} sur {appels} appels)")

src = (RACINE / "scripts" / "campaign_engine.py").read_text()
verifie("campaign_engine tire le modèle de la campagne, pas d'une constante",
        'modele = camp.get("message_id") or None' in src)


print("\nUn modèle jamais envoyé affiche zéro, pas les chiffres du secteur")
import email_templates_backend as etb

t = etb.tableau("lcr")
lignes = {f"{e['sector']}:{e['kind']}": e for e in t["emails"]}
verifie("la galerie répond", bool(lignes), f"({len(lignes)} modèles)")

if lignes:
    envoyes_par_modele = {k: e["envoyes"] for k, e in lignes.items()}
    partis = {k: v for k, v in envoyes_par_modele.items() if v}
    verifie("tous les modèles ne partagent plus le même volume",
            len(set(envoyes_par_modele.values())) > 1,
            f"({len(partis)} modèle(s) réellement envoyé(s) sur {len(lignes)})")

    for k, e in lignes.items():
        if not e["attribue"] and e["envoyes"]:
            ECHECS.append(f"{k} non attribué mais compté")
    verifie("aucun modèle non attribué ne porte de volume",
            not [k for k, e in lignes.items() if not e["attribue"] and e["envoyes"]])

    # Le piège qu'on vient de retirer : recopier le volume du secteur sur chaque modèle.
    faux = [k for k, e in lignes.items()
            if not e["attribue"] and e["envoyes"] == e["secteur_envoyes"] and e["secteur_envoyes"]]
    verifie("le volume du secteur n'est pas recopié sur les modèles muets",
            not faux, f"({faux[:3]})")

    verifie("la note explique que zéro veut dire « jamais envoyé »",
            "jamais été envoyé" in t.get("note_attribution", ""))


print("\n" + "=" * 62)
if ECHECS:
    print(f"{len(ECHECS)} ÉCHEC(S) : " + ", ".join(ECHECS))
    raise SystemExit(1)
print("Tout est vert.")
