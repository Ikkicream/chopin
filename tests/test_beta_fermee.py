#!/usr/bin/env python3
"""Une bêta fermée doit l'être vraiment — y compris pour un superadmin.

Demande de Camille (2026-08-24) : Mozart porte une étiquette « bêta » dans la sidebar et
reste grisé pour tout le monde sauf son compte, le temps de ses tests.

Le piège serait de fonder ce contrôle sur le RÔLE. Camille est superadmin, et le
superadmin est justement exempté de la matrice des droits : la bêta serait alors ouverte à
tous les superadmins présents et futurs, ce qui vide « réservé à mes tests » de son sens.
Le contrôle porte donc sur le COMPTE, et il est posé AVANT la matrice.

L'écran, lui, se contente d'être poli : il grise et il étiquette. La barrière est côté
serveur — un menu grisé n'a jamais empêché personne de taper l'URL.
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))

ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def lance() -> int:
    import roles_backend as rb

    testeurs = rb.beta_testeurs()
    print(f"Comptes autorisés sur les bêtas : {sorted(testeurs)}")
    verifie("la liste vient du .env et n'est pas vide", bool(testeurs))
    verifie("Mozart est bien marqué en bêta", "mozart" in rb.pages_beta(),
            f"({sorted(rb.pages_beta())})")

    print("\nQui peut, qui ne peut pas")
    for compte in sorted(testeurs):
        verifie(f"{compte} accède à Mozart",
                rb.beta_interdite("/api/sites/lcr/mozart", compte, "lcr") is None)
    for compte in ("Gilles", "Romeo", "test", "inconnu"):
        verifie(f"{compte} en est écarté",
                rb.beta_interdite("/api/sites/lcr/mozart", compte, "lcr") is not None,
                f"({rb.beta_interdite('/api/sites/lcr/mozart', compte, 'lcr')})")

    print("\nLa casse ne doit pas ouvrir une porte")
    for variante in [next(iter(testeurs)).upper(), f"  {next(iter(testeurs))}  "]:
        verifie(f"« {variante} » est reconnu",
                rb.beta_interdite("/api/sites/lcr/mozart", variante, "lcr") is None)

    print("\nToutes les routes de la bêta sont couvertes, pas seulement la première")
    for chemin in ("/api/sites/lcr/mozart",
                   "/api/sites/lcr/mozart/abc-123",
                   "/api/sites/lcr/mozart-expediteurs"):
        verifie(f"{chemin} est fermé aux autres",
                rb.beta_interdite(chemin, "Romeo", "lcr") is not None)

    print("\nLe reste de la plateforme n'est pas touché")
    for chemin in ("/api/sites/lcr/campaigns", "/api/sites/lcr/acquisition",
                   "/api/sites/lcr/segments"):
        verifie(f"{chemin} reste ouvert", rb.beta_interdite(chemin, "Romeo", "lcr") is None)

    print("\nLe contrôle est posé AVANT la matrice des rôles dans le middleware")
    api = (BASE / "scripts" / "api.py").read_text()
    i_beta = api.find("beta_interdite")
    i_matrice = api.find("rbk.route_interdite")
    verifie("l'ordre est le bon", 0 < i_beta < i_matrice,
            "(sinon un superadmin passerait par l'exemption de la matrice)")

    print("\nLa sidebar reçoit de quoi griser")
    verifie("`/api/mes-pages` annonce les bêtas et le droit d'y accéder",
            '"beta": beta' in api and '"beta_autorise": beta_ok' in api)

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("La bêta est fermée pour de vrai, et le reste de la plateforme intact.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
