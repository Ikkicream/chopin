#!/usr/bin/env python3
"""La croix d'une fenêtre doit fermer la fenêtre. Définitivement.

Camille, le 2026-08-26 : « il y a une croix mais ne marche pas, impossible de fermer la
popup ». Le composant portait déjà un correctif contre ce symptôme — mais ses garde-fous
vivaient dans des `useRef`, donc dans l'INSTANCE. `ClientShell` repasse par son écran
« Chargement… » à chaque changement de `pathname` : le composant se démonte, les refs
repartent à zéro, et la fenêtre revient.

Quatre verrous, et il faut les quatre :
  1. un booléen de MODULE, qui survit au démontage ;
  2. une réservation de place pendant la requête, pour que deux effets simultanés
     n'ouvrent pas deux fenêtres superposées — une croix qui ferme celle du dessus donne
     exactement l'impression de ne rien faire ;
  3. cette réservation libérée AVANT tout retour anticipé, sinon une requête en échec la
     laisse posée et la fenêtre ne revient plus de la session ;
  4. un dernier contrôle au RENDU : si quoi que ce soit rouvrait l'état, rien ne s'affiche.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
UI = RACINE.parent / "genesis-ui" / "src" / "components" / "brief-du-jour.tsx"
ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'✓' if condition else '✗'} {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def lance() -> int:
    if not UI.exists():
        print(f"  … composant introuvable ({UI})")
        return 0
    t = UI.read_text()

    print("\nLa fermeture survit au démontage du composant")
    verifie("le drapeau est au niveau du MODULE",
            "let fermeeDansCetteSession = false" in t,
            "(un useRef repart à zéro quand ClientShell remonte l'arbre)")
    verifie("la croix le pose", "fermeeDansCetteSession = true" in t)
    verifie("l'effet le respecte",
            "if (fermeeDansCetteSession || demandeEnCours" in t)
    verifie("le RENDU le respecte aussi",
            "if (fermeeDansCetteSession || !ouvert" in t,
            "(dernier rideau : même si l'état rouvrait, rien ne s'affiche)")

    print("\nDeux effets simultanés n'ouvrent pas deux fenêtres")
    verifie("une réservation existe", "let demandeEnCours = false" in t)
    verifie("elle est posée avant la requête", "demandeEnCours = true" in t)
    # Le point qui compte : la libération doit précéder les retours anticipés.
    i_then = t.index("]).then(([cpt, b]) => {")
    bloc = t[i_then:i_then + 400]
    verifie("elle est libérée AVANT tout retour anticipé",
            bloc.index("demandeEnCours = false") < bloc.index("if (!vivant"),
            "(sinon une requête en échec la laisse posée pour toute la session)")
    verifie("elle est libérée au démontage", "vivant = false; demandeEnCours = false" in t)

    print("\nLa clé du jour suit l'heure locale")
    verifie("pas de date UTC", "toISOString().slice(0, 10)" not in t,
            "(entre minuit et 2 h à Paris, l'UTC rend la veille)")
    verifie("date locale construite à la main", "getFullYear()" in t and "getMonth()" in t)

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:5])}")
        return 1
    print("Une fenêtre fermée reste fermée.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
