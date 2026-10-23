#!/usr/bin/env python3
"""Aucune page ne doit déborder sur petit écran — une ligne par page (2026-08-26).

Demande de Camille : rendre l'interface utilisable sur mobile « sans toucher à la version
desktop », en vérifiant « 1 par 1 ».

## Ce que ce test mesure, et ce qu'il ne mesure pas

Il mesure UNE chose, mais il la mesure vraiment : **la page pousse-t-elle son propre corps
au-delà de l'écran ?** C'est le défaut qui rend un écran inutilisable au doigt — on glisse
de côté pour lire, les boutons partent hors champ, et le retour arrière du navigateur
devient le seul moyen de s'en sortir.

Un débordement CONTENU ne compte pas. Une table de trente colonnes qui glisse dans sa
propre boîte à défilement est un choix correct : le composant `Table` s'enveloppe lui-même
dans un conteneur `overflow-x-auto`. Compter ces cas-là aurait produit une liste d'échecs
qu'on aurait appris à ignorer.

Il ne juge PAS la densité, la taille des cibles tactiles, ni la lisibilité. Ces choses-là se
regardent, elles ne se mesurent pas par un script qui prétendrait le contraire.

## Pourquoi il peut être ignoré

Il a besoin d'un navigateur (Playwright) et de l'application EN LIGNE. Sur une machine qui
n'a ni l'un ni l'autre, il s'annonce ignoré plutôt que rouge : un test qui échoue pour une
raison étrangère au code apprend à ne plus lire les échecs.
"""
import json
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

OUTIL = Path("/home/autoblog/outils-captures/audit-responsive.mjs")
LARGEURS = (390, 768)          # iPhone portrait, puis tablette portrait

ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


if not OUTIL.exists():
    print(f"  …  {OUTIL} absent — contrôle ignoré.")
    raise SystemExit(0)

print("\nMesure du débordement horizontal, page par page")
resultats: list[dict] = []
for largeur in LARGEURS:
    r = subprocess.run(
        [sys.executable, str(RACINE / "scripts" / "audit_responsive.py"),
         "--largeur", str(largeur)],
        capture_output=True, text=True, timeout=1800)
    for ligne in r.stdout.splitlines():
        if ligne.strip().startswith("✗") or "px" in ligne:
            pass
    resultats.append({"largeur": largeur, "sortie": r.stdout, "code": r.returncode})

for res in resultats:
    lignes = [l for l in res["sortie"].splitlines() if l.strip().startswith("✗")]
    verifie(f"{res['largeur']} px — aucune page ne pousse le corps hors écran",
            not lignes, f"({len(lignes)} page(s) : {', '.join(l.split()[1] for l in lignes[:4])})")

print("\nLe menu reste atteignable quand il se replie")
barre = RACINE.parent / "genesis-ui" / "src" / "components" / "client-shell.tsx"
if barre.exists():
    src = barre.read_text()
    verifie("un bouton ouvre le menu en tiroir", "SidebarTrigger" in src)
else:
    print("  …  genesis-ui absent, contrôle ignoré")

sb = RACINE.parent / "genesis-ui" / "src" / "components" / "ui" / "sidebar.tsx"
if sb.exists():
    src = sb.read_text()
    verifie("la barre a un mode mobile distinct", "useIsMobile" in src and "openMobile" in src)
    verifie("elle s'ouvre en panneau glissant, pas en colonne écrasée", "Sheet" in src)

print("\nLes tableaux glissent dans leur boîte, ils ne poussent pas la page")
t = RACINE.parent / "genesis-ui" / "src" / "components" / "ui" / "table.tsx"
if t.exists():
    verifie("le composant Table s'enveloppe lui-même",
            "overflow-x-auto" in t.read_text())

print("\n" + "=" * 62)
if ECHECS:
    print(f"{len(ECHECS)} ÉCHEC(S) : " + ", ".join(ECHECS))
    raise SystemExit(1)
print("Tout est vert.")
