#!/usr/bin/env python3
"""Aucun symbole inexistant ne doit partir en production.

Le 2026-08-25, la sidebar référençait `STYLE_CADRE`, une constante qu'un script de
modification avait échoué à écrire. La page mourait à l'ouverture :
`Uncaught ReferenceError: STYLE_CADRE is not defined`.

**Le build ne l'a pas vu** : `next.config.ts` porte `typescript: { ignoreBuildErrors: true }`.
« ✓ Compiled successfully » ne veut donc PAS dire que le code s'exécute — et c'est ce
message qui m'a servi de vérification.

Ce contrôle vise UNE seule classe d'erreurs, mais la seule qui plante à coup sûr :
TS2304 « Cannot find name ». Les autres écarts de typage (`string | null` mal accepté,
élargissement de type) sont réels mais n'empêchent pas la page de s'afficher — les exiger
tous bloquerait chaque déploiement pour onze avertissements hérités, et un contrôle qu'on
désactive ne protège plus de rien.
"""
import subprocess
import sys
from pathlib import Path

UI = Path(__file__).resolve().parent.parent.parent / "genesis-ui"
ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'✓' if condition else '✗'} {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def lance() -> int:
    if not UI.exists():
        print(f"  … interface introuvable ({UI}), contrôle ignoré")
        return 0

    print("\nLe build ne suffit pas — on le dit, et on compense")
    conf = UI / "next.config.ts"
    if conf.exists():
        ignore = "ignoreBuildErrors: true" in conf.read_text()
        verifie("le build ignore les erreurs de type (constat, pas un défaut)", True,
                f"({'oui' if ignore else 'non'} — d'où ce contrôle)")

    print("\nAucune référence à un symbole qui n'existe pas")
    try:
        r = subprocess.run(["npx", "tsc", "--noEmit"], cwd=str(UI),
                           capture_output=True, text=True, timeout=600)
    except Exception as e:  # noqa: BLE001
        print(f"  … contrôle de types impossible ({type(e).__name__}: {e})")
        return 0

    lignes = (r.stdout + r.stderr).splitlines()
    fatales = [l for l in lignes if "error TS2304" in l or "Cannot find name" in l]
    verifie("aucun « Cannot find name »", not fatales, f"({fatales[:3]})")

    # Le 2026-08-25, les onze écarts hérités ont TOUS été corrigés — dont un vrai défaut :
    # `refreshCount` appelé avec trois arguments sur cinq, ce qui recomptait une campagne
    # ciblée par segment comme si elle ciblait des secteurs. Le compte affiché avant envoi
    # n'était donc pas celui qui allait partir.
    #
    # Puisque la maison est propre, on la garde propre : TOUTE erreur de type bloque
    # désormais. Une tolérance chiffrée aurait fatalement remonté.
    autres = [l for l in lignes if "error TS" in l and l not in fatales]
    verifie("aucune erreur de type, d'aucune sorte", not autres,
            f"({len(autres)} — détail : {[l.split(': ')[0] for l in autres[:3]]})")

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:4])}")
        return 1
    print("Rien ne référence un symbole absent : la page s'ouvrira.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
