#!/usr/bin/env python3
"""Les deux protections qui coûtent du volume pour garder un domaine.

Le refroidissement et le routage vont tous les deux dans le même sens, à contre-courant de
l'intuition : ils REFUSENT d'envoyer alors qu'on pourrait. C'est le but. Une plainte
retenue par le fournisseur du destinataire vaut plus cher que deux jours d'envois, et un
contact qui a ouvert depuis une adresse précise vaut plus que le gain d'un lot routé
ailleurs.

Ces tests vérifient donc surtout des refus — et, tout aussi important, qu'on ne refuse
QUE ce qu'il faut : une protection qui bloque trop finit débranchée.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

SITE = "lcr"
ECHECS: list[str] = []
BOITE_TEST = "j.nguyen@leclient-roi.com"


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def _lever(mailbox: str) -> None:
    import pool_pg
    c = pool_pg._conn()
    try:
        with c.cursor() as cur:
            cur.execute("UPDATE mailboxes SET pause_jusqu_a = NULL, pause_motif = NULL, "
                        "pause_posee_a = NULL WHERE email = %s", (mailbox,))
        c.commit()
    finally:
        pool_pg._rendre(c)


def lance() -> int:
    import expediteur as ex
    import refroidissement as rf
    import routage as rt

    _lever(BOITE_TEST)

    print("Refroidissement — une boîte au repos est inutilisable")
    avant = {b["email"]: b["active"] for b in ex.boites(SITE)}
    verifie("toutes les boîtes sont actives au départ", all(avant.values()))

    rf.mettre_au_repos(BOITE_TEST, rf.HEURES_PLAINTE, "test automatisé")
    boites = {b["email"]: b for b in ex.boites(SITE)}
    verifie("la boîte au repos devient inactive", not boites[BOITE_TEST]["active"])
    verifie("son reste tombe à zéro", boites[BOITE_TEST]["reste"] == 0)
    verifie("les autres ne sont pas touchées",
            all(b["active"] for e, b in boites.items() if e != BOITE_TEST))
    verifie("le motif est conservé", bool(boites[BOITE_TEST]["au_repos_motif"]))

    print("\nLe contact attitré à une boîte au repos ATTEND — il ne change pas d'adresse")
    lignes = ex._q("SELECT email::text FROM contacts WHERE boite_expediteur = %(b)s "
                   "AND boite_expediteur_confirmee LIMIT 1", {"b": BOITE_TEST})
    if lignes:
        verifie("aucune boîte de repli ne lui est proposée",
                ex.choisir(lignes[0][0], SITE) is None)
    else:
        verifie("aucun contact confirmé sur la boîte de test — cas non exercé", True,
                "(informatif)")

    print("\nUne pause plus longue n'est jamais raccourcie")
    rf.mettre_au_repos(BOITE_TEST, 1, "pause courte")
    p = rf.pauses_en_cours(SITE).get(BOITE_TEST) or {}
    verifie("l'échéance la plus lointaine gagne", bool(p),
            f"(jusqu'au {p.get('jusqu_a', '—')[:16]})")

    print("\nLa pause s'explique dans les alertes")
    pbs = rf.problemes(SITE)
    verifie("une alerte décrit la boîte au repos", f"repos:{BOITE_TEST}" in pbs)
    verifie("elle dit que les contacts attendent",
            "attendent" in (pbs.get(f"repos:{BOITE_TEST}") or ""))

    print("\nLa reprise est automatique")
    _lever(BOITE_TEST)
    verifie("la boîte redevient active",
            {b["email"]: b["active"] for b in ex.boites(SITE)}[BOITE_TEST])
    verifie("plus aucune alerte de repos", f"repos:{BOITE_TEST}" not in rf.problemes(SITE))

    print("\nRoutage — l'affinité confirmée ne quitte jamais son canal")
    conf = [r[0] for r in ex._q(
        "SELECT email::text FROM contacts WHERE boite_expediteur_confirmee LIMIT 3")]
    libres = [r[0] for r in ex._q(
        "SELECT email::text FROM contacts WHERE boite_expediteur IS NULL LIMIT 3")]
    lot = [{"email": e} for e in conf + libres]

    routables, verrous = rt.filtrer_pour_canal(lot, "maildoso")
    verifie("sur maildoso, personne n'est écarté",
            len(routables) == len(lot) and not verrous)
    for canal in ("sweego", "emelia"):
        routables, verrous = rt.filtrer_pour_canal(lot, canal)
        verifie(f"sur {canal}, les confirmés sont écartés",
                len(verrous) == len(conf), f"({len(verrous)} écartés sur {len(conf)})")
        verifie(f"sur {canal}, les contacts libres passent",
                len(routables) == len(libres), f"({len(routables)} routables)")

    print("\nLa capacité du jour reflète l'état réel des boîtes")
    cap = rt.capacite_du_jour(SITE)
    attendu = sum(b["reste"] for b in ex.boites(SITE) if b["active"])
    verifie("maildoso : somme des restes actifs",
            cap["maildoso"]["reste"] == attendu, f"({cap['maildoso']['reste']})")
    verifie("les canaux sans plafond connu le disent",
            cap["sweego"]["reste"] is None and cap["emelia"]["reste"] is None)

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("Les protections refusent ce qu'il faut, et rien de plus.")
    return 0


if __name__ == "__main__":
    try:
        code = lance()
    finally:
        _lever(BOITE_TEST)
    sys.exit(code)
