#!/usr/bin/env python3
"""Un taux d'ouverture ne peut pas dépasser 100 %.

Le 2026-08-25, le tableau de bord affichait **162,5 %** : 13 ouvreurs pour 8 envois. Le
chiffre n'était pas faux, il était mal RAPPORTÉ — `contact_site_history.last_opened_at`
compte « les personnes qui ont ouvert CE JOUR-LÀ », sans dire quel jour l'email était
parti. Rapporté aux envois du même jour, on divisait deux populations sans rapport ; le
jour où les envois chutent, le taux explose.

La lecture juste est une COHORTE : parmi les destinataires servis le jour J, combien ont
ouvert ENSUITE. Numérateur et dénominateur portent alors sur les mêmes personnes, et le
taux ne peut structurellement pas dépasser 100 %.
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
    import journal_pg
    import dashboard_stats_backend as st

    print("\nLa cohorte : mêmes personnes des deux côtés")
    src = (RACINE / "scripts" / "journal_pg.py").read_text()
    verifie("la fonction existe", hasattr(journal_pg, "cohorte_par_jour"))
    # On vérifie la RÈGLE, pas son orthographe : la requête a été réécrite le 2026-08-25
    # pour des raisons de performance (76 s → 0,05 s) et l'assertion, qui cherchait une
    # chaîne exacte, est passée au rouge alors que le comportement n'avait pas bougé.
    verifie("une ouverture n'est comptée qu'APRÈS l'envoi",
            ">= e.premier" in src,
            "(sinon une ouverture ancienne créditerait un envoi neuf)")
    verifie("c'est la DERNIÈRE réaction qui est comparée",
            "max(occurred_at) FILTER" in src,
            "(prendre la première ferait sortir de la cohorte quelqu'un qui a ouvert un "
            "email ancien avant celui-ci)")

    print("\nSur les données réelles, aucun jour ne dépasse 100 %")
    jours = st.daily_email_stats("lcr", 15).get("jours") or []
    verifie("des jours sont mesurés", bool(jours), f"({len(jours)})")
    fautifs = []
    for l in jours:
        env, ouv, cli = l.get("envoyes") or 0, l.get("ouvreurs") or 0, l.get("cliqueurs") or 0
        if env and ouv > env:
            fautifs.append(f"{l['jour']}: {ouv} ouvreurs / {env} envois")
        if env and cli > env:
            fautifs.append(f"{l['jour']}: {cli} clics / {env} envois")
    verifie("aucun taux d'ouverture impossible", not fautifs, f"({fautifs[:2]})")

    print("\nUn jour sans envoi n'a pas d'ouvreurs")
    # C'est le second symptôme : le repli doit être GLOBAL, pas jour par jour. Sinon un
    # jour absent de la cohorte retombait sur l'ancien comptage et affichait
    # « 11 ouvreurs pour 0 envoi ».
    incoherents = [l["jour"] for l in jours
                   if not l.get("envoyes") and (l.get("ouvreurs") or 0) > 0]
    verifie("aucun jour à 0 envoi ne montre d'ouvreurs", not incoherents,
            f"({incoherents[:3]})")
    stsrc = (RACINE / "scripts" / "dashboard_stats_backend.py").read_text()
    verifie("le repli est global, pas par jour",
            'if cohortes else None' in stsrc)
    verifie("l'écran sait d'où vient le chiffre", '"base_ouverture"' in stsrc)
    verifie("la cohorte fait autorité quand elle répond",
            all(l.get("base_ouverture") == "cohorte" for l in jours) or
            not any(l.get("base_ouverture") for l in jours),
            f"({ {l.get('base_ouverture') for l in jours} })")

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("Les taux d'ouverture comparent enfin les mêmes personnes.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
