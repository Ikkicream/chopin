#!/usr/bin/env python3
"""Le guide parle des pages qu'on a, et d'elles seules (Lot G, 2026-08-26).

La documentation était un texte unique, écrit une fois, qui décrivait des écrans que la
moitié des comptes ne voit pas : un commercial y lisait comment lancer un scraping — page
qu'il n'a pas. Un mode d'emploi qui décrit un bouton absent n'apprend rien, il fait douter
de sa propre application.

Le catalogue `roles_backend.PAGES` porte maintenant une phrase d'aide par page. La même
table décide donc ce qu'on VOIT (le menu) et ce qu'on LIT (le guide) — ajouter un écran
sans expliquer ce qu'il fait se remarque, et le guide ne peut plus décrire une page
supprimée.
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

print("\nChaque page dit ce qu'elle fait")
sans_aide = [p["cle"] for p in rbk.PAGES if not (p.get("aide") or "").strip()]
verifie("aucune page sans phrase d'aide", not sans_aide, f"({sans_aide})")
trop_court = [p["cle"] for p in rbk.PAGES if len((p.get("aide") or "")) < 25]
verifie("aucune aide qui ne dit rien", not trop_court, f"({trop_court})")
verifie("les clés sont uniques",
        len({p["cle"] for p in rbk.PAGES}) == len(rbk.PAGES))
verifie("chaque page a un groupe", all((p.get("groupe") or "").strip() for p in rbk.PAGES))


def _guide(role: str) -> dict:
    """Rejoue ce que sert `/api/mon-guide`, sans passer par HTTP."""
    autorisees = set(rbk.pages_autorisees(role))
    groupes: dict = {}
    for p in rbk.PAGES:
        if p["cle"] in autorisees:
            groupes.setdefault(p.get("groupe") or "Autres", []).append(p["cle"])
    return {"pages": autorisees, "groupes": groupes}


print("\nLe guide est différent selon le rôle")
vues = {r["cle"]: _guide(r["cle"])["pages"] for r in rbk.ROLES}
verifie("un commercial ne voit pas les mêmes pages qu'un admin",
        vues["commercial"] != vues["admin"],
        f"({len(vues['commercial'])} vs {len(vues['admin'])})")
verifie("un commercial n'a pas la page Scraping",
        "scrapper" not in vues["commercial"], f"({sorted(vues['commercial'])})")
verifie("un commercial n'a pas la page Campagnes",
        "campagnes" not in vues["commercial"])
verifie("mais il a bien sa liste d'appels",
        "a_rappeler" in vues["commercial"])
verifie("le rôle Contenu n'a pas non plus le scraping",
        "scrapper" not in vues["contenu"], f"({sorted(vues['contenu'])})")
verifie("aucun rôle ne voit une page absente du catalogue",
        all(v <= {p["cle"] for p in rbk.PAGES} for v in vues.values()))

print("\nLes sections du guide sont rattachées à des pages RÉELLES")
guide = (RACINE.parent / "genesis-ui" / "src" / "app" / "site" / "[code]"
         / "guide" / "page.tsx")
if not guide.exists():
    print("  … genesis-ui absent, contrôle de l'écran ignoré")
else:
    src = guide.read_text()
    import re

    cles_catalogue = {p["cle"] for p in rbk.PAGES}
    bloc = src[src.index("const SECTIONS"):src.index("type PageGuide")]
    citees = set(re.findall(r'"([a-z_]+)"\]', bloc)) | set(re.findall(r'"([a-z_]+)",\s*"', bloc))
    inconnues = {c for c in re.findall(r'\["([a-z_]+)"(?:,\s*"([a-z_]+)")?\]', bloc)
                 for c in c if c} - cles_catalogue
    verifie("aucune section ne cite une page qui n'existe pas",
            not inconnues, f"({inconnues})")

    verifie("le guide interroge la route du rôle", '"/api/mon-guide"' in src)
    verifie("les sections sont conditionnées", src.count("{montre([") >= 5,
            f"({src.count('{montre([')})")
    verifie("chaque condition est refermée",
            src.count("{montre([") == src.count("\n      )}\n"),
            f"({src.count('{montre([')} ouvertes / {src.count(chr(10) + '      )}' + chr(10))} fermées)")
    verifie("l'inventaire des pages n'est plus écrit en dur",
            "SidebarSchema" not in src)
    verifie("le rôle est affiché au lecteur", "role_label" in src)
    verifie("une panne réseau ne vide pas le guide", "!guide ||" in src)

print("\nLa route ne laisse pas choisir son rôle")
api = (RACINE / "scripts" / "api.py").read_text()
i = api.index("def api_mon_guide")
corps = api[i:i + 2600]
verifie("le rôle vient de la session", 'sess.get("role")' in corps)
verifie("aucun rôle en paramètre de la route",
        "def api_mon_guide(request: Request)" in corps)
verifie("les pages en bêta restent documentées mais marquées",
        '"beta"' in corps and '"accessible"' in corps)

print("\n" + "=" * 62)
if ECHECS:
    print(f"{len(ECHECS)} ÉCHEC(S) : " + ", ".join(ECHECS))
    raise SystemExit(1)
print("Tout est vert.")
