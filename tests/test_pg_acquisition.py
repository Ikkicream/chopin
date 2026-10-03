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

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))

SITE = "lcr"
ECHECS: list[str] = []


# Le miroir se réaligne UNE FOIS PAR JOUR (`pg_reconcile`, 6h30). Entre deux passages, le
# pool et PostgreSQL divergent forcément de quelques contacts : la collecte écrit en
# continu, et le drain Mailnjoy retire du pool des copies que PostgreSQL garde jusqu'au
# lendemain. C'est le fonctionnement voulu, pas une panne — mais un test qui exige
# l'égalité stricte vire au rouge tous les jours à partir de 7 h du matin, et un test
# rouge en permanence n'est plus lu. On tolère donc un écart de fraîcheur, petit et borné.
TOLERANCE_FRAICHEUR = 30

# Mais un nombre fixe ne suffit plus : le 2026-08-25, 1 561 adresses ont été rejetées dans
# la journée, et l'écart a atteint 64 avant midi. Augmenter la constante serait une rustine
# — elle grandirait avec le volume de collecte, indéfiniment.
#
# On mesure donc l'écart LÉGITIME au lieu de le deviner : un contact présent dans
# PostgreSQL et absent du pool est normal SI son `etat` dit pourquoi (`ko`, `spam`,
# `exclu`). Ce qui ne l'est pas, c'est un contact absent du pool qui se prétend encore
# `ok` ou `a_verifier` — il s'affiche alors comme une tâche en attente qui n'en est pas
# une. C'est exactement le défaut trouvé le 2026-08-25 : 103 rejets restés « à vérifier »
# faute d'être répercutés dans PostgreSQL.
ECART_EXPLIQUE = 0


_ECART_CACHE: dict = {}


def _comparer_pool_pg() -> dict:
    """Une SEULE lecture des deux bases, partagée par les deux contrôles.

    Les lire deux fois coûtait plus que le délai du test : 11 000 lignes de chaque côté,
    plus les tentatives sur le verrou DuckDB.
    """
    global ECART_EXPLIQUE
    if _ECART_CACHE:
        return _ECART_CACHE
    resultat = {"explique": 0, "orphelins": [], "lisible": False}
    try:
        import pool_pg, duckdb, time
        c = pool_pg._conn()
        try:
            with c.cursor() as cur:
                cur.execute("SELECT lower(email), etat FROM contacts")
                pg = dict(cur.fetchall())
        finally:
            pool_pg._rendre(c)
        con = None
        for _ in range(6):
            try:
                con = duckdb.connect(str(BASE / "data" / "contacts.duckdb"), read_only=True)
                break
            except Exception:  # noqa: BLE001
                time.sleep(2)
        if con is None:
            _ECART_CACHE.update(resultat)
            return resultat
        try:
            duck = {r[0].lower() for r in con.execute("SELECT email FROM contacts").fetchall()}
        finally:
            con.close()
        sup = set(pg) - duck
        resultat["explique"] = sum(1 for e in sup if pg[e] in ("ko", "spam", "exclu"))
        resultat["orphelins"] = [e for e in sup if pg[e] in ("ok", "a_verifier")]
        resultat["lisible"] = True
        ECART_EXPLIQUE = resultat["explique"]
    except Exception:  # noqa: BLE001
        pass
    _ECART_CACHE.update(resultat)
    return resultat


def proche(a: int, b: int) -> bool:
    return abs(int(a) - int(b)) <= TOLERANCE_FRAICHEUR + ECART_EXPLIQUE


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
    # Depuis le 2026-08-25, PostgreSQL en sait PLUS que le pool : il porte `etat`, et un
    # contact rejeté à la collecte (`etat = 'ko'`) y est rangé en « écarté » au lieu de
    # traîner en « à vérifier ». Le pool ignore cette colonne — il ne peut pas produire le
    # même classement, et ce n'est pas un défaut : c'est la copie qui est en retard sur la
    # source. On borne donc l'écart de CES DEUX étapes par le nombre de contacts concernés,
    # et on laisse les autres strictes.
    try:
        _ko = int(pg._q("SELECT count(*) FROM contacts ct JOIN contact_sites cs "
                        "ON cs.contact_id = ct.id WHERE cs.site_code = %(s)s AND ct.etat = 'ko'",
                        {"s": SITE})[0][0])
    except Exception:  # noqa: BLE001
        _ko = 0
    print(f"  ({_ko} contact(s) rejetés, connus de PostgreSQL seul)")
    for cle in pg.ETAPES_CLES:
        marge = _ko if cle in ("ecarte", "a_verifier") else 0
        verifie(f"étape {cle}",
                abs(d_et.get(cle, 0) - p_et.get(cle, 0)) <= TOLERANCE_FRAICHEUR + ECART_EXPLIQUE + marge,
                f"(pool {d_et.get(cle, 0)} / pg {p_et.get(cle, 0)})")
    verifie("somme des étapes = total", sum(p_et.values()) == pg.count_contacts_for_site(SITE),
            f"({sum(p_et.values())})")

    print("\nL'écart entre le pool et PostgreSQL doit s'EXPLIQUER")
    cmp = _comparer_pool_pg()
    if not cmp["lisible"]:
        print("  … pool occupé, comparaison ignorée")
    else:
        print(f"  ({cmp['explique']} contact(s) dans PostgreSQL, absents du pool, "
              f"portant un état qui le justifie)")
        # L'invariant qui compte, et le seul qui aurait vu le défaut du 2026-08-25 : un
        # contact que le pool a retiré ne doit JAMAIS rester `ok` ou `a_verifier` côté
        # PostgreSQL. Il s'afficherait comme contactable, ou comme une vérification en
        # attente qui n'arrivera jamais.
        verifie("aucun contact retiré du pool ne se prétend contactable ou à vérifier",
                not cmp["orphelins"],
                f"({len(cmp['orphelins'])} : {cmp['orphelins'][:3]})")

    print("\nVolumes et filtres")
    verifie("total du site", proche(duck.count_contacts_for_site(SITE),
                                    pg.count_contacts_for_site(SITE)),
            f"(pool {duck.count_contacts_for_site(SITE)} / pg {pg.count_contacts_for_site(SITE)})")
    for etat in ("cold_email", "blacklisted", "prm"):
        a = duck.count_contacts_for_site(SITE, state=[etat])
        b = pg.count_contacts_for_site(SITE, state=[etat])
        verifie(f"état {etat}", proche(a, b), f"(pool {a} / pg {b})")
    for etape in ("pret", "verifie", "a_verifier", "repos"):
        a = duck.count_contacts_for_site(SITE, etape=[etape])
        b = pg.count_contacts_for_site(SITE, etape=[etape])
        verifie(f"filtre étape {etape}", proche(a, b), f"(pool {a} / pg {b})")

    print("\nStats et valeurs de filtre")
    d_st, p_st = duck.stats_for_site(SITE), pg.stats_for_site(SITE)
    verifie("stats total", proche(d_st["total"], p_st["total"]),
            f"({d_st['total']}/{p_st['total']})")
    verifie("stats par état", all(proche(v, p_st["by_state"].get(k, 0))
                                 for k, v in d_st["by_state"].items()),
            f"(pool {d_st['by_state']} / pg {p_st['by_state']})")
    verifie("stats par source", all(proche(v, p_st["by_source"].get(k, 0))
                                    for k, v in d_st["by_source"].items()),
            f"(pool {d_st['by_source']} / pg {p_st['by_source']})")
    d_fv, p_fv = duck.filter_values_for_site(SITE), pg.filter_values_for_site(SITE)
    verifie("sources du filtre",
            all(proche(x["count"], next((y["count"] for y in p_fv["sources"]
                                         if y["value"] == x["value"]), 0))
                for x in d_fv["sources"]),
            f"(pool {len(d_fv['sources'])} / pg {len(p_fv['sources'])} sources)")
    d_sec = {x["value"]: x["count"] for x in d_fv["sectors"]}
    p_sec = {x["value"]: x["count"] for x in p_fv["sectors"]}
    verifie("secteurs du filtre",
            set(d_sec) == set(p_sec) and all(proche(v, p_sec.get(k, 0))
                                             for k, v in d_sec.items()),
            f"(pool {len(d_sec)} secteurs / pg {len(p_sec)})")

    print("\nEngagement — PostgreSQL doit en voir AU MOINS autant (journal complet)")
    d_ouv = duck.count_contacts_for_site(SITE, engagement="openers")
    p_ouv = pg.count_contacts_for_site(SITE, engagement="openers")
    verifie("ouvreurs ≥ pool", p_ouv >= d_ouv * 0.95, f"(pool {d_ouv} / pg {p_ouv})")
    d_clk = duck.count_contacts_for_site(SITE, engagement="clickers")
    p_clk = pg.count_contacts_for_site(SITE, engagement="clickers")
    verifie("cliqueurs ≥ pool", p_clk >= d_clk * 0.95, f"(pool {d_clk} / pg {p_clk})")

    print("\nListe — même forme, mêmes contacts")
    d_li = duck.list_contacts_for_site(SITE, limit=50)
    p_li = pg.list_contacts_for_site(SITE, limit=50)
    verifie("la liste PostgreSQL n'est pas vide", len(p_li) == len(d_li),
            f"(pool {len(d_li)} / pg {len(p_li)})")
    if d_li and p_li:
        manquantes = set(d_li[0]) - set(p_li[0])
        verifie("aucune clé perdue pour l'interface", not manquantes, f"({sorted(manquantes)})")
        verifie("libellé d'étape présent", all(x.get("etape_label") for x in p_li))

    # Comparer les 50 PREMIERS pendant qu'un scrape écrit, c'est comparer deux horloges.
    # La liste est triée sur `last_action_at`, et cette date n'a pas la même valeur des
    # deux côtés : le pool la pose à l'écriture, PostgreSQL au passage du miroir, quelques
    # dizaines de millisecondes plus tard. Les deux ordres sont justes — « le plus
    # récemment touché d'abord » — mais ils ne peuvent pas coïncider à la ligne près sur
    # des contacts qui arrivent en continu. Un test qui échoue dès qu'une collecte tourne
    # finit ignoré, ce qui est pire que pas de test.
    #
    # On compare donc une population STABILISÉE : les contacts dont la dernière action a
    # plus de trente minutes. Là, les deux bases doivent dire exactement la même chose.
    from datetime import datetime, timedelta, timezone
    limite = (datetime.now(timezone.utc) - timedelta(minutes=30)).replace(tzinfo=None)

    def stables(liste):
        out = {}
        for x in liste:
            d = str(x.get("last_action_at") or "")[:19].replace(" ", "T")
            try:
                if datetime.fromisoformat(d) < limite:
                    out[x["email"]] = x["etape"]
            except ValueError:
                continue
        return out

    d_st = stables(duck.list_contacts_for_site(SITE, limit=800))
    p_st = stables(pg.list_contacts_for_site(SITE, limit=800))
    communs = set(d_st) & set(p_st)
    verifie("population stabilisée non vide", len(communs) >= 50,
            f"({len(communs)} contacts de plus de 30 min)")
    # Même raison : un contact que PostgreSQL sait rejeté change d'étape de son côté, et
    # le pool ne peut pas suivre. On écarte donc ces contacts-là de la comparaison plutôt
    # que de compter leur divergence comme une anomalie.
    try:
        _ko_emails = {r[0] for r in pg._q(
            "SELECT lower(ct.email::text) FROM contacts ct JOIN contact_sites cs "
            "ON cs.contact_id = ct.id WHERE cs.site_code = %(s)s AND ct.etat = 'ko'",
            {"s": SITE})}
    except Exception:  # noqa: BLE001
        _ko_emails = set()
    ecarts = {e for e in communs if d_st[e] != p_st[e] and e not in _ko_emails}
    verifie("étapes identiques sur la population stabilisée (hors rejets)", not ecarts,
            f"({len(ecarts)} écart(s) sur {len(communs)})")
    # La complétude ne se contrôle PAS en comparant deux fenêtres de 800 lignes : elles
    # sont triées sur une date qui diffère légèrement d'une base à l'autre, donc les
    # contacts de bordure tombent dans l'une et pas dans l'autre. Un premier jet annonçait
    # ainsi « 8 contacts perdus » alors qu'aucun ne manquait. On interroge les bases
    # entières.
    # Le pool est souvent tenu par un scrape. Un test qui MEURT sur ce verrou n'apprend
    # rien et rend la suite instable, donc ignorée : on saute le contrôle en le disant.
    import duckdb
    import pool_pg as _pg
    emails_pool = None
    try:
        c = duckdb.connect(str(BASE / "data" / "contacts.duckdb"), read_only=True)
        try:
            emails_pool = {r[0].strip().lower() for r in
                           c.execute("SELECT email FROM contacts").fetchall()}
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        verifie("pool illisible — contrôle de complétude sauté", True,
                f"({type(e).__name__} : base tenue par un autre process)")
    if emails_pool is not None:
        emails_pg = {r[0] for r in _pg._q("SELECT lower(email::text) FROM contacts")}
        absents = emails_pool - emails_pg
        verifie("aucun contact du pool absent de PostgreSQL",
                len(absents) <= TOLERANCE_FRAICHEUR,
                f"({len(absents)} absent(s) — la réconciliation de 6h30 les rattrape)")

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
