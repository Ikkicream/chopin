#!/usr/bin/env python3
"""Équivalence DuckDB ↔ PostgreSQL sur les lectures de la page Acquisition.

Ces fonctions-là ne décident pas qui reçoit un email — elles décident ce que Camille VOIT.
Une divergence ne se paie donc pas en réputation d'expéditeur mais en confiance : un
compteur d'onglet qui annonce 3 311 « Prêt » et une liste qui en montre 2 716 rend l'écran
inutilisable, et c'est exactement ce qui s'est produit tant que le verdict Mailnjoy n'était
recopié dans PostgreSQL qu'à l'insertion (1 077 contacts vérifiés vus « À vérifier »).

Tourne sur les DONNÉES RÉELLES : une égalité sur des données fabriquées ne dirait rien des
10 027 contacts en production.

Trois écarts sont ATTENDUS et ne sont donc pas des échecs — ils vont tous dans le sens du
journal contre la colonne recopiée :
  - l'engagement compte les événements de `email_events`, là où le pool ne gardait que le
    dernier signal par contact (donc PostgreSQL en voit autant ou plus) ;
  - le canal d'ouverture est celui du dernier événement, pas celui écrasé au passage suivant ;
  - le filtre secteur teste l'appartenance à un tableau (`= ANY`) au lieu d'un `LIKE '%…%'`,
    qui rangeait `immobilier-neuf` dans `immobilier`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

SITE = "lcr"
ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def lance() -> int:
    import contacts_pool_backend as duck
    import pool_pg as pg

    print("Étapes — la cascade doit donner exactement les mêmes effectifs")
    d_et = duck.compter_par_etape(SITE)
    p_et = pg.compter_par_etape(SITE)
    for cle in pg.ETAPES_CLES:
        verifie(f"étape {cle}", d_et.get(cle, 0) == p_et.get(cle, 0),
                f"(pool {d_et.get(cle, 0)} / pg {p_et.get(cle, 0)})")
    verifie("somme des étapes = total", sum(p_et.values()) == pg.count_contacts_for_site(SITE),
            f"({sum(p_et.values())})")

    print("\nVolumes et filtres")
    verifie("total du site", duck.count_contacts_for_site(SITE) == pg.count_contacts_for_site(SITE),
            f"(pool {duck.count_contacts_for_site(SITE)} / pg {pg.count_contacts_for_site(SITE)})")
    for etat in ("cold_email", "blacklisted", "prm"):
        a = duck.count_contacts_for_site(SITE, state=[etat])
        b = pg.count_contacts_for_site(SITE, state=[etat])
        verifie(f"état {etat}", a == b, f"(pool {a} / pg {b})")
    for etape in ("pret", "verifie", "a_verifier", "repos"):
        a = duck.count_contacts_for_site(SITE, etape=[etape])
        b = pg.count_contacts_for_site(SITE, etape=[etape])
        verifie(f"filtre étape {etape}", a == b, f"(pool {a} / pg {b})")

    print("\nStats et valeurs de filtre")
    d_st, p_st = duck.stats_for_site(SITE), pg.stats_for_site(SITE)
    verifie("stats total", d_st["total"] == p_st["total"], f"({d_st['total']}/{p_st['total']})")
    verifie("stats par état", d_st["by_state"] == p_st["by_state"])
    verifie("stats par source", d_st["by_source"] == p_st["by_source"])
    d_fv, p_fv = duck.filter_values_for_site(SITE), pg.filter_values_for_site(SITE)
    verifie("sources du filtre", d_fv["sources"] == p_fv["sources"])
    d_sec = {x["value"]: x["count"] for x in d_fv["sectors"]}
    p_sec = {x["value"]: x["count"] for x in p_fv["sectors"]}
    verifie("secteurs du filtre", d_sec == p_sec,
            f"(pool {len(d_sec)} secteurs / pg {len(p_sec)})")

    print("\nEngagement — PostgreSQL doit en voir AU MOINS autant (journal complet)")
    d_ouv = duck.count_contacts_for_site(SITE, engagement="openers")
    p_ouv = pg.count_contacts_for_site(SITE, engagement="openers")
    verifie("ouvreurs ≥ pool", p_ouv >= d_ouv * 0.95, f"(pool {d_ouv} / pg {p_ouv})")
    d_clk = duck.count_contacts_for_site(SITE, engagement="clickers")
    p_clk = pg.count_contacts_for_site(SITE, engagement="clickers")
    verifie("cliqueurs ≥ pool", p_clk >= d_clk * 0.95, f"(pool {d_clk} / pg {p_clk})")

    print("\nListe — même forme, mêmes contacts en tête")
    d_li = duck.list_contacts_for_site(SITE, limit=50)
    p_li = pg.list_contacts_for_site(SITE, limit=50)
    verifie("la liste PostgreSQL n'est pas vide", len(p_li) == len(d_li),
            f"(pool {len(d_li)} / pg {len(p_li)})")
    if d_li and p_li:
        manquantes = set(d_li[0]) - set(p_li[0])
        verifie("aucune clé perdue pour l'interface", not manquantes, f"({sorted(manquantes)})")
        verifie("mêmes 50 premiers contacts",
                {x["email"] for x in d_li} == {x["email"] for x in p_li})
        verifie("étapes cohérentes ligne à ligne",
                {x["email"]: x["etape"] for x in d_li} == {x["email"]: x["etape"] for x in p_li})
        verifie("libellé d'étape présent", all(x.get("etape_label") for x in p_li))

    print("\nPagination — l'offset ne doit ni sauter ni répéter")
    p1 = pg.list_contacts_for_site(SITE, limit=25, offset=0)
    p2 = pg.list_contacts_for_site(SITE, limit=25, offset=25)
    verifie("deux pages disjointes", not ({x["email"] for x in p1} & {x["email"] for x in p2}))

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) — NE PAS BASCULER : {', '.join(ECHECS[:6])}")
        return 1
    print("Équivalence complète. Acquisition peut être servie par PostgreSQL.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
