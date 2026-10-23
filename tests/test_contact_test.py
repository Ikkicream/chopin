#!/usr/bin/env python3
"""La fiche de test : visible, protégée, et jamais dans une campagne.

Camille utilise `afchain.camille@gmail.com` pour éprouver un envoi, un rendu, une prise de
rendez-vous. Cette fiche vit donc DANS le pool, au milieu des prospects — et c'est
exactement ce qui la rend dangereuse : rien ne la distinguait, elle était `etat = 'ok'`
avec le secteur `immobilier`, donc éligible à toute campagne immobilier.

Trois protections, et la deuxième est celle qu'on oublie :
  1. elle n'entre dans aucune pioche d'envoi ;
  2. le passage de `pg_reconcile` à 6h30 ne la remet pas « ok » — il réaligne `etat` DEPUIS
     le pool, qui ignore tout de cette intention. Une protection posée sur `etat` seul se
     serait effacée toute seule la nuit suivante ;
  3. le serveur refuse de la supprimer.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

EMAIL = "afchain.camille@gmail.com"
ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'✓' if condition else '✗'} {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def lance() -> int:
    import pool_pg

    print("\nLa fiche existe et porte le bon numéro")
    r = pool_pg._q("SELECT id::text, tel, COALESCE(est_test,false), etat FROM contacts "
                   "WHERE lower(email) = %(e)s", {"e": EMAIL})
    verifie("la fiche est en base", bool(r))
    if not r:
        print("\n1 ÉCHEC : fiche absente")
        return 1
    cid, tel, test, etat = r[0]
    verifie("le numéro est celui de Camille", tel == "0621040063", f"({tel})")
    verifie("elle est marquée comme fiche de test", test is True)

    print("\nElle n'entre dans AUCUNE pioche d'envoi")
    src = (RACINE / "scripts" / "pool_pg.py").read_text()
    verifie("la pioche de campagne l'écarte",
            src.count("AND NOT COALESCE(ct.est_test, false)") >= 2,
            f"({src.count('AND NOT COALESCE(ct.est_test, false)')} clause(s) sur 2)")
    n = pool_pg._q("SELECT count(*) FROM contacts ct WHERE lower(ct.email) = %(e)s "
                   "AND NOT COALESCE(ct.est_test, false)", {"e": EMAIL})
    verifie("elle ne passe pas le filtre", int(n[0][0]) == 0)

    print("\nLe passage de nuit ne la réveille pas")
    rec = (RACINE / "scripts" / "pg_reconcile.py").read_text()
    verifie("pg_reconcile respecte le drapeau",
            "AND NOT COALESCE(est_test, false)" in rec,
            "(sinon `etat` serait réaligné depuis le pool et redeviendrait « ok »)")

    print("\nLe serveur refuse de la supprimer")
    api = (RACINE / "scripts" / "api.py").read_text()
    i = api.index("async def api_pool_contact_delete")
    corps = api[i:i + 1800]
    verifie("le contrôle porte sur est_test", "est_test" in corps)
    verifie("le refus est un 409, pas un 500", "status_code=409" in corps)
    verifie("le contrôle précède toute écriture",
            corps.index("est_test") < corps.index("import duckdb as _dd"))

    print("\nElle se voit à l'écran, en tête et grisée")
    verifie("la colonne voyage jusqu'à l'écran", '"est_test",' in src)
    verifie("elle est épinglée en tête",
            "ORDER BY COALESCE(ct.est_test, false) DESC" in src)
    ui = RACINE.parent / "genesis-ui" / "src" / "app" / "site" / "[code]" / "acquisition" / "page.tsx"
    if ui.exists():
        t = ui.read_text()
        verifie("la ligne est grisée", "c.est_test" in t and "bg-muted/60" in t)
        verifie("l'étiquette « test » est posée", ">\n                              test\n" in t or "test\n" in t)
        verifie("ni suppression ni blacklist proposées",
                t.index("protégée") < t.index('title="Blacklister"'))
        verifie("exclue des actions groupées", "exclue des actions groupées" in t)
    else:
        print("  … écran introuvable, contrôles ignorés")

    # La première liste de contacts doit la porter en tête, sans filtre particulier.
    liste = pool_pg.list_contacts_for_site("lcr", limit=1)
    verifie("elle arrive en première position",
            bool(liste) and liste[0].get("est_test") is True,
            f"({liste[0]['email'] if liste else 'liste vide'})")

    print("\nDans « À rappeler » : visible du SEUL superadmin")
    import followup_backend as fb
    vus = {}
    for role, user in (("superadmin", "camille"), ("admin", "Gilles"), ("commercial", "test")):
        cs = fb.lister("lcr", role, user, vue="tous").get("contacts") or []
        vus[role] = [c for c in cs if c.get("est_test")]
    verifie("le superadmin la voit", len(vus["superadmin"]) == 1, f"({len(vus['superadmin'])})")
    verifie("elle arrive en tête de liste",
            bool(vus["superadmin"]) and
            (fb.lister("lcr", "superadmin", "camille", vue="tous")["contacts"][0].get("est_test") is True))
    verifie("un admin ne la voit PAS", not vus["admin"], f"({len(vus['admin'])})")
    verifie("un commercial ne la voit pas", not vus["commercial"])
    # Elle ne doit pas gonfler la pastille du menu : la vue `v_a_rappeler` l'ignore, et
    # c'est elle qui alimente les compteurs. Un chiffre faux dans le menu ferait chercher
    # un contact qui n'existe pas.
    cpt = fb.lister("lcr", "superadmin", "camille", vue="tous")["compteurs"]
    verifie("elle n'est pas comptée dans la pastille",
            cpt["suivis"] == len([c for c in fb.lister("lcr", "admin", "Gilles", vue="tous")["contacts"]]),
            f"(suivis {cpt['suivis']})")

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("La fiche de test se voit, ne part jamais, et ne se supprime pas.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
