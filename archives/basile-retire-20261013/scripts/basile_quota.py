#!/usr/bin/env python3
"""basile_quota.py — compteur de quota Basile et journal de rendement par segment.

Pourquoi ce fichier existe (constat du 2026-09-22) : le quota mensuel Basile (250 000
enregistrements sur le plan `api`) s'est épuisé le 21/09 sans que rien ne l'ait vu venir.
La table `scrape_quota_usage` était vide, `run_segment` calculait `collected`/`valid`/
`rejected` à chaque passe puis jetait tout, et l'épuisement s'est découvert par un 402 en
pleine nuit — après quoi les passes ont tourné à vide en consommant les créneaux du jour.

Deux manques, deux réponses ici :

1. **On ne savait pas où on en était.** `consomme_mois()` additionne ce qui a été
   RÉELLEMENT facturé (un enregistrement ramené par `/find` = un enregistrement facturé,
   qu'on le garde ou non), et `alerter_si_besoin()` prévient à 80 % puis à 95 %. Le
   compteur est une ESTIMATION locale : seul Basile fait foi, et il ne dit son reste que
   dans le corps d'un 402. `reconcilier()` recale le compteur quand il le dit.

2. **On ne savait pas ce qui rend.** Chaque passe laisse désormais une ligne : combien
   facturé, combien gardé, pour quel secteur, quel département, quels filtres. C'est la
   seule façon de répondre à « quel segment mérite le quota du mois prochain ».

Le quota est PERDU s'il n'est pas consommé — il se remet à zéro le 1er à 00 h 00 UTC, il
ne se reporte pas. Payer 250 000 et en utiliser 200 000, c'est jeter 50 000.
`restant()` sert à `basile_brulage.py`, qui dépense le reliquat avant qu'il expire.

Usage :
  python3 scripts/basile_quota.py etat              # où on en est ce mois-ci
  python3 scripts/basile_quota.py rendement         # quels segments rendent
  python3 scripts/basile_quota.py alerter           # cron : prévient aux seuils
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"

# Plan `api` (cf. docs/basile-api.md §10). Surchargeable par .env si le forfait change.
PLAN_MENSUEL_DEFAUT = 250_000
SEUILS_ALERTE = (0.80, 0.95)


def _plan_mensuel() -> int:
    try:
        for ligne in (BASE_DIR / ".env").read_text().splitlines():
            if ligne.startswith("BASILE_PLAN_MENSUEL="):
                return max(1, int(ligne.split("=", 1)[1].strip() or PLAN_MENSUEL_DEFAUT))
    except Exception:  # noqa: BLE001
        pass
    return PLAN_MENSUEL_DEFAUT


def _conn(lecture_seule: bool = False):
    """Toujours par `duck_ouverture` : god_mode est ouvert par une quinzaine de modules
    dans le process de l'API, et une ouverture nue en configuration différente lève
    « Can't open a connection to same database file with a different configuration »."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from duck_ouverture import ouvrir
    return ouvrir(GOD_DB)


def _mois(quand: datetime | None = None) -> str:
    return (quand or datetime.now(timezone.utc)).strftime("%Y-%m")


def assurer_table() -> None:
    c = _conn()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS basile_consommation (
                id              BIGINT,
                mois            VARCHAR,
                quand           TIMESTAMP,
                site_code       VARCHAR,
                kind            VARCHAR,
                secteur         VARCHAR,
                dept_code       VARCHAR,
                filtres         VARCHAR,
                univers         BIGINT,   -- `total` : taille du segment, gratuit à compter
                factures        BIGINT,   -- `collected` : ce que Basile facture
                gardes          BIGINT,   -- `valid`  : ce qui entre au pool
                rejetes         BIGINT,
                doublons        BIGINT,
                source          VARCHAR
            )
        """)
        c.execute("CREATE SEQUENCE IF NOT EXISTS seq_basile_conso START 1")
    finally:
        c.close()


def enregistrer(out: dict, filters: dict | None = None, source: str = "autoscrape") -> bool:
    """Journalise une passe. Ne lève jamais : une collecte ne doit pas échouer parce que
    sa comptabilité échoue."""
    try:
        if out.get("dry_run") or not out.get("collected"):
            return False          # un dry-run ne facture rien, une passe vide non plus
        assurer_table()
        c = _conn()
        try:
            c.execute("""
                INSERT INTO basile_consommation
                SELECT nextval('seq_basile_conso'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            """, [_mois(), datetime.now(timezone.utc),
                  out.get("site"), out.get("kind"), out.get("sector"),
                  str(out.get("dept_code") or ""),
                  json.dumps(filters or {}, ensure_ascii=False)[:2000],
                  int(out.get("total") or 0), int(out.get("collected") or 0),
                  int(out.get("valid") or 0), int(out.get("rejected") or 0),
                  int(out.get("duplicates") or 0), source])
        finally:
            c.close()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[basile_quota] journalisation impossible : {str(e)[:200]}", flush=True)
        return False


def consomme_mois(mois: str | None = None) -> int:
    try:
        assurer_table()
        c = _conn()
        try:
            r = c.execute("SELECT COALESCE(SUM(factures), 0) FROM basile_consommation "
                          "WHERE mois = ?", [mois or _mois()]).fetchone()
            return int(r[0]) if r else 0
        finally:
            c.close()
    except Exception:  # noqa: BLE001
        return 0


def restant() -> int:
    """Estimation LOCALE du reliquat. Basile seul fait foi — voir `reconcilier`."""
    return max(0, _plan_mensuel() - consomme_mois())


def reconcilier(restant_officiel: int) -> None:
    """Recale le compteur sur le chiffre donné par Basile lui-même (corps d'un 402, ou
    tout futur en-tête de quota). On n'efface pas l'historique : on pose une ligne
    d'ajustement, pour que le journal reste une trace de ce qui s'est passé."""
    ecart = (_plan_mensuel() - restant_officiel) - consomme_mois()
    if ecart == 0:
        return
    try:
        assurer_table()
        c = _conn()
        try:
            c.execute("""
                INSERT INTO basile_consommation
                SELECT nextval('seq_basile_conso'), ?, ?, 'ajustement', '-', NULL, '',
                       '{}', 0, ?, 0, 0, 0, 'reconciliation'
            """, [_mois(), datetime.now(timezone.utc), int(ecart)])
        finally:
            c.close()
        print(f"[basile_quota] compteur recale sur Basile : ecart {ecart:+d}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[basile_quota] reconciliation impossible : {str(e)[:200]}", flush=True)


def rendement(mois: str | None = None, limite: int = 15) -> list[dict]:
    """Rendement par secteur : combien d'enregistrements facturés pour un contact gardé.
    C'est le chiffre qui dit où mettre le quota du mois prochain."""
    try:
        assurer_table()
        c = _conn()
        try:
            lignes = c.execute("""
                SELECT secteur,
                       SUM(factures) f, SUM(gardes) g,
                       SUM(rejetes) r, SUM(doublons) d, COUNT(*) passes
                  FROM basile_consommation
                 WHERE mois = ? AND secteur IS NOT NULL
                 GROUP BY 1 ORDER BY f DESC LIMIT ?
            """, [mois or _mois(), limite]).fetchall()
        finally:
            c.close()
        return [{"secteur": l[0], "factures": l[1], "gardes": l[2], "rejetes": l[3],
                 "doublons": l[4], "passes": l[5],
                 "cout_par_contact": round(l[1] / l[2], 1) if l[2] else None,
                 "rendement_pct": round(100 * l[2] / l[1], 2) if l[1] else 0.0}
                for l in lignes]
    except Exception:  # noqa: BLE001
        return []


def etat() -> dict:
    plan = _plan_mensuel()
    pris = consomme_mois()
    return {"mois": _mois(), "plan": plan, "consomme": pris, "restant": max(0, plan - pris),
            "pct": round(100 * pris / plan, 1) if plan else 0.0,
            "jours_restants": _jours_restants()}


def _jours_restants() -> int:
    """Jours pleins avant la remise à zéro (1er du mois suivant, 00 h 00 UTC)."""
    n = datetime.now(timezone.utc)
    mois, an = (1, n.year + 1) if n.month == 12 else (n.month + 1, n.year)
    return max(0, (datetime(an, mois, 1, tzinfo=timezone.utc) - n).days)


def alerter_si_besoin() -> dict:
    """Prévient au franchissement de 80 % puis de 95 %. Une alerte par seuil et par mois :
    le but est d'avertir une semaine avant le mur, pas de klaxonner tous les jours."""
    e = etat()
    marque = BASE_DIR / "logs" / f"basile_quota_alerte_{e['mois']}.json"
    try:
        deja = set(json.loads(marque.read_text()).get("seuils", []))
    except Exception:  # noqa: BLE001
        deja = set()

    franchis = [s for s in SEUILS_ALERTE if e["pct"] >= s * 100 and str(s) not in deja]
    if not franchis:
        return {**e, "alerte": False}

    sys.path.insert(0, str(BASE_DIR / "scripts"))
    try:
        from autoscrape_backend import notify_telegram
        notify_telegram(
            f"\U0001f4ca *Quota Basile* — {e['pct']:.0f} % consommé "
            f"({e['consomme']:,} / {e['plan']:,}).\n"
            f"Reste {e['restant']:,} enregistrements pour {e['jours_restants']} jours.\n"
            f"Le quota NON UTILISÉ est perdu le 1er à 00 h 00 UTC : il ne se reporte pas."
            .replace(",", " "))
    except Exception as ex:  # noqa: BLE001
        print(f"[basile_quota] alerte impossible : {str(ex)[:150]}", flush=True)

    try:
        marque.parent.mkdir(parents=True, exist_ok=True)
        marque.write_text(json.dumps({"seuils": sorted(deja | {str(s) for s in franchis})}))
    except Exception:  # noqa: BLE001
        pass
    return {**e, "alerte": True, "seuils": franchis}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "etat"
    if cmd == "etat":
        e = etat()
        plein = int(e["pct"] // 5)
        print(f"Quota Basile {e['mois']}")
        print(f"  [{'#' * plein}{'.' * (20 - plein)}] {e['pct']:.1f} %")
        print(f"  consomme : {e['consomme']:,}".replace(",", " "))
        print(f"  restant  : {e['restant']:,}".replace(",", " ")
              + f"  ({e['jours_restants']} jours avant remise a zero)")
    elif cmd == "rendement":
        r = rendement()
        if not r:
            print("Aucune passe journalisee ce mois-ci.")
        for l in r:
            print(f"  {l['secteur']:<18} facture {l['factures']:>7} · garde {l['gardes']:>6}"
                  f" · {l['rendement_pct']:>5} % · {l['cout_par_contact']} factures/contact")
    elif cmd == "alerter":
        print(json.dumps(alerter_si_besoin(), ensure_ascii=False))
    else:
        print(__doc__)
