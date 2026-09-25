#!/usr/bin/env python3
"""Le ping des connecteurs doit désigner la BONNE cause.

Le 2026-08-24, le tableau de bord annonçait « Erreur — Ahrefs (SEO) » avec pour action
« Vérifier la clé et la connectivité réseau ». La clé était parfaitement valide : Ahrefs
répondait HTTP 200. Le ping était simplement coupé à 3 secondes, sans seconde chance,
alors que ce fournisseur oscille entre 200 ms et près de 6 secondes selon les moments.

Deux défauts, donc, et pas un seul :
  1. un délai trop court, qui transformait une lenteur passagère en panne ;
  2. un message qui accusait la clé dans TOUS les cas, y compris quand elle était hors
     de cause — c'est ce qui envoie chercher un problème là où il n'y en a pas.

Ce test fige les deux : le délai, et la traduction d'un échec en cause.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'✓' if condition else '✗'} {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def _charger():
    """Extrait _ping_connector de api.py sans démarrer l'API (qui ouvre des bases)."""
    import requests
    from datetime import datetime, timezone
    src = (RACINE / "scripts" / "api.py").read_text()
    debut = src.index("def _ping_connector(")
    fin = src.index("# Connecteurs propres à un site")
    ns = {"requests": requests, "BASE_DIR": RACINE, "datetime": datetime, "timezone": timezone}
    exec(compile(src[debut:fin], "api.py:_ping_connector", "exec"), ns)
    return ns


def lance() -> int:
    import requests
    ns = _charger()
    ping = ns["_ping_connector"]

    print("\nLe délai laissé aux fournisseurs")
    src = (RACINE / "scripts" / "api.py").read_text()
    verifie("le ping ne coupe plus à 3 secondes",
            "def _http(url, method=\"GET\", headers=None, json_body=None, timeout=3.0)" not in src)
    verifie("une seconde tentative existe", "essais=2" in src or "essais: int = 2" in src)

    print("\nLa cause de l'échec, connecteur par connecteur")

    # Clé refusée → on doit pointer la clé, et seulement dans ce cas.
    r = ping("ahrefs", {"AHREFS_API_KEY": "clef-volontairement-fausse"})
    verifie("clé refusée → raison 'cle'", r.get("raison") == "cle", f"(reçu : {r.get('raison')})")

    # Réseau muet → la clé n'est PAS en cause. C'est le cas qui a induit en erreur.
    vrai_get = requests.get

    def _muet(url, **kw):
        raise requests.Timeout("simulé")

    requests.get = _muet
    try:
        r = ping("ahrefs", {"AHREFS_API_KEY": "une-clef-valide"})
    finally:
        requests.get = vrai_get
    verifie("délai dépassé → raison 'reseau'", r.get("raison") == "reseau", f"(reçu : {r.get('raison')})")
    verifie("délai dépassé → jamais 'cle'", r.get("raison") != "cle")

    # Clé absente : ce n'est pas une erreur, c'est une configuration à faire.
    r = ping("ahrefs", {})
    verifie("clé absente → 'missing_key', pas 'error'", r.get("status") == "missing_key",
            f"(reçu : {r.get('status')})")

    print("\nL'écran propose une action par cause")
    tsx = (RACINE.parent / "genesis-ui" / "src" / "components" / "connector-alerts.tsx")
    if tsx.exists():
        t = tsx.read_text()
        for cause in ("cle", "service", "reseau"):
            verifie(f"cause '{cause}' a sa propre action", f"{cause}:" in t)
        verifie("une cause réseau n'envoie plus vers Setup & API",
                "reseau:" in t and "lien: false" in t)
    else:
        print("  … composant introuvable, contrôle ignoré")

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("Un connecteur en panne dit maintenant POURQUOI, et n'accuse plus la clé à tort.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
