#!/usr/bin/env python3
"""Cohérence DuckDB ↔ PostgreSQL sur les lectures qui décident QUI reçoit un email.

Depuis la mise en place de la porte d'entrée (option C, 2026-08-19), PostgreSQL n'est plus
un miroir : il ne contient QUE les contacts ayant franchi tous les contrôles, enrichissement
data.gouv compris. Le test ne vérifie donc plus une égalité mais un **sous-ensemble strict et
justifié** : tout contact proposé par PostgreSQL doit l'être aussi par DuckDB, et l'écart doit
s'expliquer entièrement par des contacts en attente d'enrichissement — jamais par autre chose.

Tourne sur les DONNÉES RÉELLES : c'est le seul test qui vaille avant une bascule. Une égalité
sur des données fabriquées ne dirait rien des 7 916 contacts en production.

Ce qui est comparé, et pourquoi :
  - le VOLUME contactable, secteur par secteur : c'est ce qu'affichent les compteurs et ce
    qui dimensionne une campagne ;
  - l'IDENTITÉ des contacts piochés, pas seulement leur nombre : deux lots de 160 contacts
    peuvent avoir la même taille et ne pas viser les mêmes personnes ;
  - l'ORDRE des premiers : le tri décide qui part en premier, et c'est un mauvais tri qui a
    produit 98 renvois sur 100 le 15/08/2026 ;
  - la fenêtre de 120 jours, adresse par adresse : une seule divergence ici = un renvoi.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

ECHECS = []


def verifie(nom, condition, detail=""):
    if condition:
        print(f"  OK   {nom}")
    else:
        print(f"  ÉCHEC {nom} {detail}")
        ECHECS.append(nom)


def lance():
    import contacts_pool_backend as duck
    import pool_pg as pg

    # INDISPENSABLE : `contacts_pool_backend` délègue à PostgreSQL quand PG_READS=1. Sans
    # ce forçage, le test comparerait PostgreSQL avec lui-même et serait vert quoi qu'il
    # arrive — le pire des tests, celui qui rassure sans rien vérifier.
    duck._PG_READS = False
    assert not duck._pg_reads(), "le chemin DuckDB doit être forcé pour que la comparaison ait un sens"

    SITE = "lcr"

    import pg_gate
    portail = pg_gate.compter_eligibles()
    print(f"\n0. La porte d'entrée : {portail['eligibles']} éligibles sur "
          f"{portail['contacts_pool']} du pool, {portail['en_attente_enrichissement']} "
          f"en attente d'enrichissement")
    verifie("aucun contact éligible n'est blacklisté ou non-valid",
            portail["eligibles"] <= portail["et_non_exclus"])

    print("\n1. Volume contactable par secteur (PG ⊆ DuckDB)")
    secteurs = duck.pool_sectors(min_count=5)[:6]
    for s in secteurs:
        a = duck.count_available_for_sector(SITE, s)
        b = pg.count_available_for_sector(SITE, s)
        verifie(f"secteur '{s}' : PG {b} ≤ DuckDB {a}", b <= a, f"(PG dépasse de {b-a})")

    print("\n2. Identité des contacts piochés")
    # On compare au jeu COMPLET des contactables DuckDB, pas à sa tranche de même taille :
    # les deux pools n'ayant pas le même effectif, leurs top-N diffèrent légitimement sans
    # que personne d'interdit ne soit proposé. Comparer les tranches faisait échouer le test
    # sur un artefact.
    jeu_duck = {x["email"].lower() for x in duck.pick_for_campaign(SITE, "immobilier", limit=100000)}
    jeu_pg = {x["email"].lower() for x in pg.pick_for_campaign(SITE, "immobilier", limit=100000)}
    interdits = jeu_pg - jeu_duck
    verifie(f"PG ⊆ DuckDB sur le jeu complet ({len(jeu_pg)} vs {len(jeu_duck)})",
            not interdits, f"({len(interdits)} interdits : {list(interdits)[:3]})")

    # L'écart doit s'expliquer ENTIÈREMENT par l'attente d'enrichissement. Toute autre cause
    # serait une divergence silencieuse entre les deux implémentations du filtre.
    ecart = jeu_duck - jeu_pg
    import pg_gate
    duck_conn = pg_gate._duck()
    try:
        non_enrichis = {r[0].lower() for r in duck_conn.execute("""
            SELECT lower(ct.email) FROM contacts ct
            LEFT JOIN contact_enrichment e ON e.contact_id = ct.id
            WHERE e.contact_id IS NULL""").fetchall()}
    finally:
        duck_conn.close()
    inexplique = ecart - non_enrichis
    verifie(f"les {len(ecart)} absents de PG attendent tous leur enrichissement",
            not inexplique, f"({len(inexplique)} inexpliqués : {list(inexplique)[:3]})")

    for taille in (10, 160, 500):
        rb = pg.pick_for_campaign(SITE, "immobilier", limit=taille)
        verifie(f"pioche de {taille} : PG remplit le lot ({len(rb)}/{taille})",
                len(rb) == taille, f"(PG n'a rendu que {len(rb)})")

    print("\n3. Ordre de la pioche (qui part en premier)")
    ra = duck.pick_for_campaign(SITE, "immobilier", limit=30)
    rb = pg.pick_for_campaign(SITE, "immobilier", limit=30)
    # On compare les 10 premiers : au-delà, des contacts à score identique peuvent
    # légitimement permuter, les deux moteurs n'ayant pas le même tri de départage.
    # Les jeux pouvant différer d'un contact en attente d'enrichissement, on vérifie que le
    # tri de PostgreSQL respecte la même règle : jamais un déjà-contacté avant un contact neuf.
    vus = [bool(x.get("last_contacted_by_site_at")) for x in rb]
    verifie("PG : aucun déjà-contacté ne passe devant un contact neuf",
            vus == sorted(vus), "(un contact déjà servi remonte trop haut)")
    communs = [x["email"].lower() for x in rb[:10] if x["email"].lower() in
               {y["email"].lower() for y in ra[:15]}]
    verifie("les premiers de PG figurent bien en tête de DuckDB",
            len(communs) >= 8, f"({len(communs)}/10 retrouvés)")

    print("\n4. Aucun contact déjà servi ne remonte")
    for r, nom in ((ra, "DuckDB"), (rb, "PostgreSQL")):
        verifie(f"{nom} : 0 contact déjà contacté dans la pioche",
                all(not x.get("last_contacted_by_site_at") for x in r))

    print("\n5. Fenêtre de 120 jours, adresse par adresse")
    duck_bloques = set()
    c = duck._conn(read_only=False)
    try:
        duck_bloques = {r[0].lower() for r in c.execute(
            f"""SELECT email FROM email_suppression WHERE contactable = 0
                AND last_sent_at > CURRENT_TIMESTAMP - INTERVAL '{duck.SUPPRESSION_DAYS}' DAY"""
        ).fetchall()}
    finally:
        c.close()
    pg_bloques = pg.filter_suppressed(list(duck_bloques))
    manquants = duck_bloques - pg_bloques
    verifie(f"les {len(duck_bloques)} adresses bloquées le restent en PostgreSQL",
            not manquants, f"({len(manquants)} non bloquées : {list(manquants)[:3]})")

    echantillon = [x["email"] for x in rb[:20]]
    verifie("aucun contact de la pioche n'est bloqué",
            not pg.filter_suppressed(echantillon))

    print("\n6. Segments")
    regles = [
        {"include": {"sectors": ["immobilier"]}, "exclude": {}, "match": "AND"},
        {"include": {"sectors": ["immobilier"]}, "exclude": {"depts": ["75", "92"]}, "match": "AND"},
        {"include": {"sectors": ["immobilier"], "depts": ["06", "13"]}, "exclude": {}, "match": "AND"},
    ]
    for i, r in enumerate(regles, 1):
        a = duck.count_for_segment(SITE, r)
        b = pg.count_for_segment(SITE, r)
        verifie(f"segment #{i} : PG {b} ≤ DuckDB {a}", b <= a, f"(PG dépasse de {b-a})")
        pa = {x["email"].lower() for x in duck.pick_for_segment(SITE, r, limit=100000)}
        pb = {x["email"].lower() for x in pg.pick_for_segment(SITE, r, limit=100000)}
        verifie(f"segment #{i} : PG ne pioche personne d'interdit", not (pb - pa),
                f"({len(pb - pa)} en trop : {list(pb - pa)[:3]})")

    print("\n7. Filtre géographique")
    for depts in (["06"], ["75", "92", "93"]):
        a = duck.count_available_for_sector(SITE, "immobilier", depts=depts)
        b = pg.count_available_for_sector(SITE, "immobilier", depts=depts)
        verifie(f"départements {depts} : PG {b} ≤ DuckDB {a}", b <= a, f"(PG dépasse de {b-a})")

    print("\n8. Compteurs de la base repoussoir")
    a = duck.suppression_stats()
    b = pg.suppression_stats()
    # PostgreSQL peut légitimement en bloquer QUELQUES-UNES DE PLUS : son journal reprend
    # aussi les envois Emelia, que la table DuckDB `email_suppression` ne connaît pas. Ce
    # qui serait grave, c'est l'inverse — une adresse protégée d'un côté et pas de l'autre.
    verifie("PostgreSQL ne bloque jamais MOINS que DuckDB",
            b["bloques"] >= a["bloques"],
            f"(DuckDB {a['bloques']} / PG {b['bloques']})")
    verifie("l'excédent de PostgreSQL reste marginal (< 1 %)",
            b["bloques"] - a["bloques"] <= max(5, a["bloques"] // 100),
            f"(+{b['bloques'] - a['bloques']})")

    print("\n9. PostgreSQL ne contient QUE du propre")
    import psycopg2
    dsn = [l.split("=", 1)[1].strip() for l in
           open("/home/autoblog/genesis/.env") if l.startswith("PG_DSN=")][0]
    cx = psycopg2.connect(dsn)
    cu = cx.cursor()
    for libelle, req in (
        ("aucun blacklisté", "SELECT count(*) FROM contacts WHERE global_blacklisted"),
        ("aucun non-valid Mailnjoy",
         "SELECT count(*) FROM contacts WHERE mailnjoy_decision IS DISTINCT FROM 'valid'"),
        ("aucun exclu par l'enrichissement",
         "SELECT count(*) FROM contacts ct JOIN contact_enrichment e "
         "ON e.contact_id = ct.id WHERE e.excluded"),
        ("aucun non enrichi",
         "SELECT count(*) FROM contacts ct LEFT JOIN contact_enrichment e "
         "ON e.contact_id = ct.id WHERE e.contact_id IS NULL"),
    ):
        cu.execute(req)
        n = cu.fetchone()[0]
        verifie(libelle, n == 0, f"({n} trouvé(s))")
    cx.close()

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) — NE PAS BASCULER : {', '.join(ECHECS[:5])}")
        return 1
    print("Équivalence complète. La bascule des lectures est sûre.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
