#!/usr/bin/env python3
"""Un scénario n'inscrit jamais plus que ce que les adresses peuvent envoyer.

Le 2026-08-25, le scénario « Immobilier — nouveaux arrivants » vise **3 869 contacts**.
`inscrire()` en prenait 500 par passage, et le cron tourne toutes les heures : douze mille
personnes en file pour une capacité de **soixante par jour** — et zéro tant que les quatre
adresses sont en chauffe, jusqu'au 8 septembre.

Ce que ça produirait, concrètement : des contacts qui attendent des mois, reçoivent un
message périmé, et que la fenêtre de non-recontact de 120 jours bloque entre-temps. Le
nombre de contacts d'un secteur ne dit RIEN de ce qui partira — c'est la chauffe et le
plafond par boîte qui décident.
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


def lance() -> int:
    import mozart

    print("\nLa capacité se lit sur les ADRESSES, pas sur le nombre de contacts")
    cap = mozart.capacite_jour("lcr")
    verifie("la capacité est chiffrée", isinstance(cap.get("capacite"), int),
            f"({cap.get('capacite')}/jour)")
    verifie("elle ne compte que les adresses de Mozart",
            "usage=\"mozart\"" in (RACINE / "scripts" / "mozart.py").read_text(),
            "(les boîtes des campagnes ne sont pas disponibles pour un scénario)")
    verifie("chaque adresse dit POURQUOI elle est à zéro",
            all("motif" in b for b in cap.get("boites") or []),
            "(« en chauffe » et « au repos » n'appellent pas la même réaction)")

    print("\nLa file est bornée par un HORIZON, pas par un nombre arbitraire")
    src = (RACINE / "scripts" / "mozart.py").read_text()
    verifie("l'horizon est explicite", "HORIZON_FILE_JOURS" in src,
            f"({mozart.HORIZON_FILE_JOURS} jours)")
    verifie("le plafond se calcule capacité × horizon",
            "cap[\"capacite\"] * HORIZON_FILE_JOURS" in src)
    verifie("on ne pioche pas plus que la place restante",
            "min(limite, place)" in src,
            "(inutile de lire 500 contacts pour en jeter 480)")

    print("\nÀ capacité nulle, rien ne s'inscrit — et le motif est dit")
    scenarios = [s for s in mozart.scenarios("lcr") if s.get("nom", "")[:1].isdigit()]
    verifie("des scénarios existent", bool(scenarios), f"({len(scenarios)})")
    if scenarios and cap["capacite"] == 0:
        r = mozart.inscrire(scenarios[0], dry_run=False)
        verifie("aucune inscription", r.get("inscrits") == 0, f"({r.get('inscrits')})")
        verifie("le refus est explicite", bool(r.get("bride")) and bool(r.get("note")),
                f"({r.get('note')})")
    elif scenarios:
        # Capacité non nulle : on vérifie que la borne existe quand même dans le retour.
        r = mozart.inscrire(scenarios[0], dry_run=True)
        verifie("la simulation reste bornée", r.get("candidats", 0) <= cap["capacite"] *
                mozart.HORIZON_FILE_JOURS, f"({r.get('candidats')})")

    print("\nL'écran le dit AVANT qu'on active")
    api = (RACINE / "scripts" / "api.py").read_text()
    verifie("la route de capacité existe", "/mozart-capacite" in api)
    page = RACINE.parent / "genesis-ui" / "src" / "app" / "site" / "[code]" / "mozart" / "page.tsx"
    if page.exists():
        t = page.read_text()
        verifie("la page interroge la capacité", "mozart-capacite" in t)
        verifie("elle annonce la chauffe", "en chauffe" in t)
        verifie("elle explique la borne de file", "jours de" in t and "capacité" in t)

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:5])}")
        return 1
    print("Un scénario ne peut plus mettre en file plus que ce qui partira.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
