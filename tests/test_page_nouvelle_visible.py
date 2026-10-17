#!/usr/bin/env python3
"""Une page ajoutée après le réglage d'un rôle ne doit pas disparaître (2026-08-26).

Le piège s'est refermé QUATRE fois : Mozart le 24/08, Onoff et les adresses d'envoi le
25/08, la page « Nouveautés et versions » le 26/08 — celle-ci existait depuis mai et
n'avait jamais été inscrite au catalogue, donc invisible de la barre de gauche, du réglage
par rôle et du guide. Camille l'a signalée elle-même : « je ne le vois pas ».

Deux causes, deux protections ici :

1. **Une page absente de `PAGES` n'existe pour personne.** Ce n'est pas « ouverte à
   tous » : c'est invisible, et impossible à attribuer à qui que ce soit.

2. **Une page ajoutée APRÈS le réglage d'un rôle restait invisible pour toujours.** Seules
   les pages autorisées étaient enregistrées ; impossible ensuite de distinguer « décochée »
   de « n'existait pas encore ». On enregistre désormais les refus aussi, et `matrice()`
   applique le défaut aux pages qu'un rôle n'a jamais vues passer.
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


import roles_backend as rbk

print("\nToute page servie par l'application est au catalogue")
cles = {p["cle"] for p in rbk.PAGES}
pages_ui = RACINE.parent / "genesis-ui" / "src" / "app"
if pages_ui.exists():
    # Les routes de premier niveau hors site/[code] : /versions, /costs, /admin/*…
    urls = {p["url"] for p in rbk.PAGES}
    attendues = {"/versions": "versions", "/costs": "couts"}
    for url, cle in attendues.items():
        chemin = pages_ui / url.strip("/") / "page.tsx"
        if chemin.exists():
            verifie(f"la route {url} est déclarée", url in urls and cle in cles,
                    f"(cherché « {cle} »)")
else:
    print("  … genesis-ui absent, contrôle des routes ignoré")

verifie("la page Nouveautés existe au catalogue", "versions" in cles)
p = next((x for x in rbk.PAGES if x["cle"] == "versions"), None)
if p:
    verifie("elle est gardée par sa route API", p.get("api") == ["/api/versions"], f"({p.get('api')})")
    verifie("elle porte une phrase d'aide", bool((p.get("aide") or "").strip()))

print("\nQui la voit")
verifie("superadmin la voit", "versions" in rbk.pages_autorisees("superadmin"))
verifie("admin la voit", "versions" in rbk.pages_autorisees("admin"))
verifie("un commercial ne la voit pas", "versions" not in rbk.pages_autorisees("commercial"))

print("\nUne page nouvelle survit à un rôle déjà réglé")
# On simule : le rôle « contenu » a été réglé AVANT l'ajout de deux pages.
vrai_q = rbk._pool()._q
reglees = set(rbk.DEFAUT["contenu"]) - {"newsletters"}          # newsletters décochée
nouvelles = {"versions", "mozart"}                              # ajoutées après le réglage


def faux_q(sql, params=None):
    if "FROM role_pages" in sql:
        lignes = []
        for pg in (set(rbk.DEFAUT["contenu"]) | {"newsletters"}) - nouvelles:
            lignes.append(("contenu", pg, pg in reglees))
        return lignes
    return vrai_q(sql, params)


try:
    rbk._pool()._q = faux_q
    m = rbk.matrice(force=True)
    droits = m.get("contenu", set())
    verifie("une page explicitement décochée le reste",
            "newsletters" not in droits, f"({'newsletters' in droits})")
    verifie("une page ajoutée après le réglage réapparaît si le défaut la donne",
            all((n in droits) == (n in rbk.DEFAUT["contenu"]) for n in nouvelles),
            f"(versions={'versions' in droits}, mozart={'mozart' in droits})")
    verifie("les pages réglées et autorisées restent autorisées",
            reglees <= droits, f"({sorted(reglees - droits)})")
finally:
    rbk._pool()._q = vrai_q
    rbk.matrice(force=True)

print("\nL'enregistrement garde la trace des REFUS")
src = (RACINE / "scripts" / "roles_backend.py").read_text()
i = src.index("def enregistrer(")
corps = src[i:i + 2200]
verifie("toutes les pages connues sont écrites, pas seulement les cochées",
        "sorted(connues)" in corps and "pg in choisies" in corps)
verifie("matrice() lit la colonne autorise",
        "SELECT role, page, autorise FROM role_pages" in src)
verifie("et distingue « jamais vue » de « refusée »",
        "connues_du_role" in src and "nouvelles" in src)

print("\n" + "=" * 62)
if ECHECS:
    print(f"{len(ECHECS)} ÉCHEC(S) : " + ", ".join(ECHECS))
    raise SystemExit(1)
print("Tout est vert.")
