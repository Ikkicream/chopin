#!/usr/bin/env python3
"""Une seule table pour les cold emails ET les newsletters (Lot C, 2026-08-26).

Décision de Camille : « finalement cold email et newsletters sont la même chose ». Les
deux vivaient dans deux écrans, avec deux stockages qui ne se ressemblent pas — les cold
emails dans `email_templates`, les newsletters dans des FICHIERS `structures/*.html` plus
une table `html_templates` aujourd'hui vide.

Le piège de la fusion est là : lire la table sans lire les fichiers donnerait un onglet
« Emailing » désespérément vide alors que huit newsletters existent sur le disque.
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


import email_templates_backend as etb
import html_templates_backend as htb

t = etb.tableau("lcr")
emails = t["emails"]
froids = [e for e in emails if e["type"] == "cold"]
lettres = [e for e in emails if e["type"] == "emailing"]

print("\nLes deux sources sont dans la même table")
verifie("des cold emails", len(froids) > 0, f"({len(froids)})")
verifie("des newsletters", len(lettres) > 0, f"({len(lettres)})")
verifie("les huit structures du disque sont là, malgré html_templates vide",
        len(lettres) >= len(htb.list_structures()),
        f"({len(lettres)} lignes pour {len(htb.list_structures())} fichiers)")
verifie("chaque ligne porte son type", all(e.get("type") in ("cold", "emailing") for e in emails))

print("\nChaque modèle est identifiable et affichable")
ids = [e["modele_id"] for e in emails]
verifie("les identifiants sont uniques", len(set(ids)) == len(ids),
        f"({len(ids) - len(set(ids))} doublon(s))")
non_resolus = [i for i in ids if not (htb.resolve_campaign_message("lcr", i) or {}).get("html")]
verifie("tous les modèles se résolvent (donc l'aperçu s'ouvrira)",
        not non_resolus, f"({non_resolus[:3]})")
verifie("les identifiants de structure sont ceux d'une campagne (`struct:<stem>`)",
        all(not e["modele_id"].endswith(".html") for e in lettres))

print("\nLe filtre par secteur vaut pour les deux types")
verifie("chaque ligne a une icône", all(e.get("emoji") for e in emails))
verifie("chaque ligne a un libellé lisible",
        all(e.get("secteur_label") and e["secteur_label"] != e.get("sector") or not e.get("sector")
            for e in emails) or all(e.get("secteur_label") for e in emails))
sans_secteur = [e["modele_id"] for e in lettres if not e["sector"]]
verifie("aucune newsletter n'échappe au filtre par secteur",
        not sans_secteur, f"({sans_secteur[:3]})")
codes = {e["sector"] for e in froids if e["sector"]}
verifie("les secteurs des newsletters existent vraiment côté cold email",
        {e["sector"] for e in lettres} <= codes,
        f"({ {e['sector'] for e in lettres} - codes })")

print("\nCe qui n'appartient qu'au cold email n'est pas prêté aux newsletters")
verifie("aucune newsletter n'est marquée favorite", not any(e["favori"] for e in lettres))
verifie("aucune newsletter n'est verrouillée", not any(e["locked"] for e in lettres))
verifie("le récapitulatif compte les deux types",
        t["totaux"].get("cold") == len(froids) and t["totaux"].get("emailing") == len(lettres),
        f"({t['totaux'].get('cold')} / {t['totaux'].get('emailing')})")

print("\nL'écran ne redemande plus les icônes à une autre route")
galerie = (RACINE.parent / "genesis-ui" / "src" / "app" / "site" / "[code]"
           / "cold-email" / "galerie.tsx")
if galerie.exists():
    src = galerie.read_text()
    verifie("la galerie a des pastilles de secteur", "setSecteurActif" in src)
    verifie("la galerie a un filtre de type", "setTypeActif" in src)
    verifie("la colonne Objet n'affiche plus le début du corps",
            "{e.extrait}" not in src)
    verifie("la clé de ligne est le modèle, pas secteur+kind",
            "const cle = e.modele_id" in src)
else:
    print("  … genesis-ui absent, contrôle de l'écran ignoré")

print("\n" + "=" * 62)
if ECHECS:
    print(f"{len(ECHECS)} ÉCHEC(S) : " + ", ".join(ECHECS))
    raise SystemExit(1)
print("Tout est vert.")
