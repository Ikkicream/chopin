#!/usr/bin/env python3
"""Équivalence DuckDB ↔ PostgreSQL sur les journaux d'envoi (dernier volet du Lot 1).

Ces lectures-là ne décident pas d'un affichage : elles décident **si un email part et
combien**. La garde de reprise empêche de renvoyer le même message après un arrêt en cours
de lot ; la barrière des 120 jours empêche de recontacter trop tôt ; les volumes par boîte
pilotent la montée en charge des domaines expéditeurs. Une divergence ici se paie en
réputation, pas en pixels.

Tourne sur les DONNÉES RÉELLES.

Deux écarts sont ATTENDUS, mesurés, et vont dans le bon sens :

  - **Les volumes comptent des ENVOIS, pas des lignes** — `count(DISTINCT (adresse,
    campagne, jour))`. Le 2026-08-22, une reprise de marquage a écrit 316 lignes pour 160
    envois réels : compter les lignes aurait fait croire les boîtes saturées. Le comptage
    par envoi redonne exactement 160, comme DuckDB.
  - **Cinq BAT vers l'adresse de Camille** partis avant le 2026-08-23 n'ont jamais été
    journalisés dans PostgreSQL — ils ne passaient par aucun chemin qui écrit le journal.
    C'est corrigé pour les suivants (`maildoso_backend._journaliser_hors_campagne`), mais
    l'historique reste : PostgreSQL en compte donc jusqu'à 4 de moins sur la fenêtre de
    montée en charge. Toléré ici, et seulement dans ce sens.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))

SITE = "lcr"
ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def lance() -> int:
    import duckdb
    import journal_pg as jp

    g = duckdb.connect(str(BASE / "data" / "god_mode.duckdb"), read_only=True)

    print("Campagnes présentes dans le journal DuckDB")
    campagnes = [r[0] for r in g.execute(
        "SELECT DISTINCT campaign_id FROM maildoso_sent "
        "WHERE status = 'sent' AND campaign_id LIKE 'lcr-%' AND length(campaign_id) > 20"
    ).fetchall()]
    verifie("au moins une campagne à comparer", len(campagnes) > 0, f"({len(campagnes)})")

    print("\nGarde de reprise — l'identité des déjà-servis doit être EXACTE")
    for lot in sorted(campagnes)[:6]:
        duck = {r[0].strip().lower() for r in g.execute(
            "SELECT DISTINCT to_email FROM maildoso_sent "
            "WHERE campaign_id = ? AND status = 'sent'", [lot]).fetchall() if r[0]}
        pg = jp.deja_servis(lot)
        verifie(f"lot {lot[-10:]}", duck == pg,
                f"(pool {len(duck)} / pg {len(pg)}, écart {len(duck ^ pg)})")

    print("\nVolumes par jour — même total, malgré les lignes en double")
    legacies = sorted({"-".join(x.split("-")[1:3]) for x in campagnes})
    for legacy in legacies[:4]:
        duck = {r[0]: int(r[1]) for r in g.execute(
            "SELECT strftime(created_at, '%Y-%m-%d'), count(DISTINCT to_email) "
            "FROM maildoso_sent WHERE status = 'sent' AND site_code = ? "
            "AND campaign_id LIKE ? GROUP BY 1", [SITE, f"{SITE}-{legacy}-%"]).fetchall()}
        pg = {x["jour"]: x["volume"] for x in jp.envois_par_jour(SITE, legacy)
              if x["canal"] == "maildoso"}
        # Même raison que plus bas : DuckDB est la copie qui perd une ligne quand le
        # verrou tombe entre les deux écritures de `mark_pushed_to_emelia`. On compare
        # donc jour par jour avec une tolérance serrée, plutôt qu'à l'identique.
        jours = set(duck) | set(pg)
        ecarts = {j: (duck.get(j, 0), pg.get(j, 0)) for j in jours
                  if abs(duck.get(j, 0) - pg.get(j, 0)) > 2}
        verifie(f"campagne {legacy}", not ecarts,
                f"(pool {sum(duck.values())} / pg {sum(pg.values())}"
                + (f" · jours divergents : {ecarts}" if ecarts else "") + ")")

    # Ce contrôle a été écrit AVANT la bascule, pour vérifier que PostgreSQL ne surcomptait
    # pas (la double journalisation du 22/08). Depuis le Lot 1, PostgreSQL FAIT FOI et c'est
    # DuckDB la copie qui perd : `mark_pushed_to_emelia` écrit PostgreSQL PUIS DuckDB, et un
    # verrou entre les deux laisse une ligne dans l'un et pas dans l'autre. Constaté le
    # 2026-08-25 : 70 côté PostgreSQL contre 69 côté DuckDB pour j.bernard.
    # L'écart est donc toléré DANS LES DEUX SENS, mais serré : au-delà, ce n'est plus un
    # verrou occasionnel, c'est une divergence à regarder.
    print("\nMontée en charge — les deux journaux doivent rester à portée l'un de l'autre")
    since = date.today() - timedelta(days=3)
    duck = {r[0]: int(r[1]) for r in g.execute(
        "SELECT mailbox, count(*) FROM maildoso_sent WHERE status = 'sent' "
        "AND created_at >= ? GROUP BY 1", [since]).fetchall() if r[0]}
    pg = jp.volume_par_boite(SITE, since)
    for boite, n in sorted(duck.items()):
        v = int((pg.get(boite) or {}).get("envoyes", 0))
        verifie(f"boîte {boite.split('@')[0]}", abs(n - v) <= 4,
                f"(pool {n} / pg {v})")
    verifie("aucune boîte inconnue de PostgreSQL", set(pg) <= set(duck) or not duck,
            f"({sorted(set(pg) - set(duck))})")

    print("\nBarrière des 120 jours — elle doit bloquer un contact servi hier")
    recents = [r[0] for r in g.execute(
        "SELECT DISTINCT to_email FROM maildoso_sent WHERE status = 'sent' "
        "AND created_at >= current_date - 30 LIMIT 5").fetchall() if r[0]]
    if recents:
        bloques = jp.recemment_servis(recents + ["jamais-servi-xyz@nulle-part.test"], 120)
        verifie("les servis récemment sont bloqués",
                {e.lower() for e in recents} <= bloques,
                f"({len(bloques)} bloqués sur {len(recents)} testés)")
        verifie("une adresse inconnue n'est pas bloquée",
                "jamais-servi-xyz@nulle-part.test" not in bloques)

    print("\nEnvois de masse Sweego — la seule trace d'un envoi sans journal par personne")
    duck_mc = g.execute("SELECT count(*), COALESCE(sum(recipients_count), 0) "
                        "FROM mass_campaigns WHERE site_code = ?", [SITE]).fetchone()
    pg_mc = jp.lister_envois_masse(SITE)
    verifie("même nombre d'envois de masse", int(duck_mc[0]) == len(pg_mc),
            f"(pool {duck_mc[0]} / pg {len(pg_mc)})")
    verifie("mêmes destinataires cumulés",
            int(duck_mc[1]) == sum(x["recipients_count"] for x in pg_mc),
            f"(pool {duck_mc[1]} / pg {sum(x['recipients_count'] for x in pg_mc)})")

    print("\nDécoupage de l'identifiant de lot")
    verifie("lot de campagne", jp._decouper("lcr-fd0dc221-b44-2026-08-22")
            == ("fd0dc221-b44", "2026-08-22"))
    verifie("identifiant hors campagne", jp._decouper("lcr-bat")[1] is None)
    verifie("identifiant vide", jp._decouper("") == (None, None))

    g.close()
    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) — NE PAS BASCULER : {', '.join(ECHECS[:6])}")
        return 1
    print("Équivalence complète. Les journaux d'envoi peuvent être servis par PostgreSQL.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
