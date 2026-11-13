#!/usr/bin/env python3
"""Simuler un rôle doit tenir plus de deux secondes (2026-08-26).

Camille : « dans la barre de superadmin je peux plus changer de rôle […] après 2 [secondes]
le menu de superadmin remplace celui du rôle que je veux contrôler ».

Le menu se dessinait bien avec le rôle simulé — puis `/api/mes-pages` répondait avec les
pages du rôle RÉEL, et le bloc qui complète le menu depuis le catalogue les rajoutait
toutes. Le superadmin retrouvait son propre menu, sans rien avoir fait.

D'où `?apercu=<role>`. Le point délicat est qu'un paramètre d'URL ne doit JAMAIS pouvoir
élargir des droits : il n'est honoré que pour un superadmin, et ne sert qu'à regarder moins.
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


def role_vu(role_reel: str, apercu: str) -> str:
    """La règle exacte de la route, rejouée ici."""
    return apercu if (apercu and role_reel == "superadmin") else role_reel


print("\nUn superadmin peut regarder avec les yeux d'un autre")
for r in ("commercial", "contenu", "strategie", "admin"):
    verifie(f"aperçu « {r} » accepté", role_vu("superadmin", r) == r)
verifie("sans paramètre, il voit tout",
        len(rbk.pages_autorisees(role_vu("superadmin", ""))) == len(rbk.PAGES),
        f"({len(rbk.pages_autorisees('superadmin'))} pages)")
verifie("l'aperçu RESTREINT vraiment",
        len(rbk.pages_autorisees(role_vu("superadmin", "commercial")))
        < len(rbk.pages_autorisees("superadmin")),
        f"({len(rbk.pages_autorisees('commercial'))} contre {len(rbk.pages_autorisees('superadmin'))})")

print("\nPersonne d'autre ne peut s'en servir")
for r in ("admin", "user", "commercial", "contenu", "strategie"):
    verifie(f"un « {r} » qui demande l'aperçu superadmin reste {r}",
            role_vu(r, "superadmin") == r)
verifie("un admin ne gagne aucune page par ce chemin",
        set(rbk.pages_autorisees(role_vu("admin", "superadmin")))
        == set(rbk.pages_autorisees("admin")))

print("\nLa route est écrite comme ça")
api = (RACINE / "scripts" / "api.py").read_text()
i = api.index("def api_mes_pages")
# Jusqu'à la fonction SUIVANTE, et non une fenêtre de N caractères : la fonction fait
# 3 900 caractères, une fenêtre de 3 200 coupait juste avant le contrôle qu'on vérifie —
# le test échouait sur du code parfaitement correct.
fin = api.index("\n@app.", i)
corps = api[i:fin]
verifie("elle accepte `apercu`", "apercu: str = \"\"" in corps)
verifie("elle le refuse à qui n'est pas superadmin",
        'role_reel == "superadmin"' in corps)
verifie("le rôle réel vient toujours de la session", 'sess.get("role")' in corps)
verifie("elle dit si c'est un aperçu", '"apercu": role_vu != role_reel' in corps)

print("\nL'écran le demande quand il simule")
barre = (RACINE.parent / "genesis-ui" / "src" / "components" / "app-sidebar.tsx")
if barre.exists():
    src = barre.read_text()
    verifie("la barre passe le rôle simulé", "apercu=${encodeURIComponent(simule)}" in src)
    verifie("elle lit la simulation au montage, pas depuis l'état",
            "const simule = roleSimule()" in src)
    # Le piège d'origine : c'est ce bloc qui rajoutait les pages du rôle réel.
    verifie("le menu se complète toujours depuis le catalogue",
            "pagesAutorisees !== null && catalogue.length" in src)
else:
    print("  … genesis-ui absent, contrôle de l'écran ignoré")

print("\nCe que la simulation n'est PAS")
verifie("le module le dit noir sur blanc",
        "pas un changement de droits" in
        (RACINE.parent / "genesis-ui" / "src" / "lib" / "role.ts").read_text()
        if (RACINE.parent / "genesis-ui" / "src" / "lib" / "role.ts").exists() else True)

print("\n" + "=" * 62)
if ECHECS:
    print(f"{len(ECHECS)} ÉCHEC(S) : " + ", ".join(ECHECS))
    raise SystemExit(1)
print("Tout est vert.")
