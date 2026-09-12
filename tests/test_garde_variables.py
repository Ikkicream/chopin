#!/usr/bin/env python3
"""Le garde-fou des variables : aucun email ne doit partir avec un trou dedans.

Chaque cas est un email qu'on a failli envoyer — ou qu'on doit pouvoir envoyer sans que
le garde-fou s'y oppose. Les faux positifs comptent autant que les faux négatifs : un
garde qui refuse un gabarit HTML normal serait débranché au premier lot bloqué.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def lance() -> int:
    import garde_variables as gv

    print("Ce qui DOIT bloquer — la variable est restée dans le texte")
    for libelle, sujet, texte in (
        ("accolades doubles", "Bonjour", "Bonjour {{prenom}}, une idée pour vous."),
        ("accolades dans le sujet", "Une idée pour {{entreprise}}", "Bonjour."),
        ("accolade simple", "Bonjour", "Bonjour {prenom}, une idée."),
        ("crochets doubles", "Bonjour", "Bonjour [[prenom]], une idée."),
        ("crochet simple", "Bonjour", "Bonjour [prenom], une idée."),
        ("pourcentages", "Bonjour", "Bonjour %PRENOM%, une idée."),
        ("dollar-accolade", "Bonjour", "Bonjour ${prenom}, une idée."),
        ("chevrons", "Bonjour", "Bonjour <<prenom>>, une idée."),
        ("variable inconnue", "Bonjour", "Votre {{secteur_activite}} nous intéresse."),
    ):
        r = gv.verifier_avant_envoi(sujet, texte, None)
        verifie(libelle, not r["ok"], f"({r['motifs'][:1]})")

    print("\nCe qui NE doit PAS bloquer — sinon le garde sera débranché")
    for libelle, sujet, texte, html in (
        ("texte entièrement résolu", "Une idée pour Dupont Immo",
         "Bonjour Marie, une idée pour Dupont Immo.", None),
        ("HTML avec feuille de style", "Bonjour",
         "Bonjour Marie.",
         "<style>.wrap{max-width:600px;padding:0}@media(max-width:600px){.wrap{width:100%}}"
         "</style><p>Bonjour Marie.</p>"),
        ("HTML avec script et commentaire", "Bonjour", "Bonjour Marie.",
         "<!-- {{gabarit}} --><script>var a={b:1};</script><p>Bonjour Marie.</p>"),
        ("prix entre parenthèses", "Offre", "Le tarif (39 € / mois) reste valable.", None),
        ("accolade sans identifiant", "Bonjour", "Un smiley : {•} et voilà.", None),
    ):
        r = gv.verifier_avant_envoi(sujet, texte, html)
        verifie(libelle, r["ok"], f"({r['motifs'][:2]})")

    print("\nVariables vides — le contact incomplet est écarté, pas le lot")
    gabarit = "Bonjour {{prenom}}, j'ai vu {{entreprise}} à {{ville}}."
    complet = {"prenom": "Marie", "societe": "Dupont Immo", "city": "Nantes"}
    verifie("contact complet : rien ne manque", gv.manques([gabarit], complet) == [],
            f"({gv.manques([gabarit], complet)})")
    sans_societe = {"prenom": "Marie", "city": "Nantes"}
    verifie("société absente : bloque", "entreprise" in gv.manques([gabarit], sans_societe))
    sans_prenom = {"societe": "Dupont Immo", "city": "Nantes"}
    verifie("prénom absent : toléré", gv.manques([gabarit], sans_prenom) == [],
            f"({gv.manques([gabarit], sans_prenom)})")
    vide = {"prenom": "   ", "societe": "Dupont Immo", "city": "Nantes"}
    verifie("prénom fait d'espaces : traité comme vide",
            gv.manques([gabarit], vide) == [])

    print("\nPonctuation orpheline laissée par une variable tolérée")
    for avant, apres in (
        ("Bonjour , une idée.", "Bonjour, une idée."),
        ("Bonjour  , une idée.", "Bonjour, une idée."),
        ("Merci  beaucoup .", "Merci beaucoup."),
        ("Cordialement ,,", "Cordialement,"),
        ("Une agence «  » réputée.", "Une agence réputée."),
    ):
        obtenu = gv.nettoyer_ponctuation(avant)
        verifie(f"« {avant} »", obtenu == apres, f"→ « {obtenu} »")

    print("\nContrôle à l'enregistrement d'un message")
    verifie("variable inconnue détectée",
            gv.variables_inconnues("Bonjour {{prenom}}, votre {{secteur}}")== {"secteur"})
    verifie("gabarit sain : rien à signaler",
            gv.variables_inconnues("Bonjour {{prenom}} de {{entreprise}}") == set())

    print("\nAlignement avec le moteur de remplacement")
    import maildoso_backend as md
    boite = {"email": "j.test@leclient-roi.com", "sender_name": "Juliette Test"}
    for v in sorted(gv.VARIABLES_CONNUES - {"UNSUBSCRIBE_LINK", "unsubscribe"}):
        rendu = md._apply_tokens("[%s]" % ("{{" + v + "}}"), complet, boite)
        verifie(f"{{{{{v}}}}} est bien remplacée", "{{" not in rendu, f"→ {rendu}")

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("Le garde-fou tient. Aucun email ne peut partir avec une variable non résolue.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
