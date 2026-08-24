#!/usr/bin/env python3
"""Chaque entrée de menu doit exister dans le catalogue des droits — sinon elle clignote.

La sidebar affiche tout tant que la réponse de `/api/mes-pages` n'est pas arrivée, puis
retire ce qu'elle ne reconnaît pas. Une entrée de menu absente du catalogue serveur
(`roles_backend.PAGES`) n'a donc aucune correspondance : **elle s'affiche au chargement
puis disparaît.** Le symptôme ressemble à un bug d'affichage ; la cause est un oubli de
synchronisation entre deux listes.

C'est arrivé à Mozart le jour de sa mise en ligne. La cause première est corrigée — le
serveur renvoie désormais l'URL de chaque page avec sa clé, donc une seule source de
vérité — mais l'oubli reste possible dans l'autre sens : une page ajoutée au menu sans
être déclarée aux droits ne serait ni filtrable ni protégée.

Ce test compare les deux listes. Il n'a pas besoin de la base ni du réseau.
"""
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))

SIDEBAR = BASE.parent / "genesis-ui" / "src" / "components" / "app-sidebar.tsx"
ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def lance() -> int:
    import roles_backend as rbk

    if not SIDEBAR.exists():
        print(f"  (sidebar introuvable : {SIDEBAR} — contrôle sauté)")
        return 0

    source = SIDEBAR.read_text()
    catalogue = {p["cle"]: p["url"] for p in rbk.PAGES}
    chemins_serveur = {u.replace("/site/{site}/", "").rstrip("/") for u in catalogue.values()}

    liens_menu = set(re.findall(r'url: `/site/\$\{siteCode\}/([a-z0-9\-/]+)`', source))
    verifie("des entrées de menu ont été trouvées", len(liens_menu) > 5,
            f"({len(liens_menu)} entrées)")

    print("\nChaque entrée de menu a-t-elle sa page côté serveur ?")
    orphelines = sorted(l for l in liens_menu if l.rstrip("/") not in chemins_serveur)
    verifie("aucune entrée de menu orpheline", not orphelines,
            f"({', '.join(orphelines) or 'aucune'})")
    if orphelines:
        print("     Ces entrées s'afficheraient au chargement puis disparaîtraient,")
        print("     et aucun rôle ne pourrait se les voir retirer.")

    print("\nLe serveur fournit-il bien les URL avec les clés ?")
    api = (BASE / "scripts" / "api.py").read_text()
    verifie("`/api/mes-pages` renvoie les URL",
            '"urls": urls' in api,
            "(sans elles, la sidebar retombe sur sa copie locale)")

    print("\nLa table de secours de la sidebar reste-t-elle cohérente ?")
    bloc = re.search(r"const URLS_PAGES[^=]*= \{(.*?)\n\}", source, re.S)
    if bloc:
        cles_locales = set(re.findall(r"(\w+):\s*\"/site/\{site\}", bloc.group(1)))
        manquantes = sorted(c for c in cles_locales if c not in catalogue)
        verifie("aucune clé locale inconnue du serveur", not manquantes,
                f"({', '.join(manquantes) or 'aucune'})")
    else:
        verifie("table de secours lisible", False, "(bloc URLS_PAGES introuvable)")

    print("\nLes pages déclarées ont toutes une clé, une URL et un libellé")
    incompletes = [p.get("cle") or "?" for p in rbk.PAGES
                   if not (p.get("cle") and p.get("url") and p.get("label"))]
    verifie("catalogue complet", not incompletes, f"({incompletes})")

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("Menu et droits disent la même chose : aucune entrée ne peut clignoter.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
