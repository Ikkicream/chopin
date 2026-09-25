#!/usr/bin/env python3
"""basile_brulage.py — dépenser le quota Basile avant qu'il expire.

Pourquoi ce fichier existe (demande de Camille, 2026-09-22 : « si en fin de mois sur
basile il y a trop de crédit, burn ceux-ci… sinon je paye pour rien »).

Le quota Basile est **à usage perdu** : 250 000 enregistrements par mois qui se remettent
à zéro le 1er à 00 h 00 UTC, sans report. Finir le mois avec 40 000 non consommés, c'est
40 000 payés et jetés. Ce script ferme ce robinet-là.

Il ne se contente pas de dépenser : il dépense **là où ça rapporte**, dans cet ordre.

  1. **Les sociétés récemment créées** (`creation_date_min`). C'est la cible que Camille a
     désignée, et c'est aussi la plus économe : une société née il y a six mois s'équipe,
     cherche des prestataires, et n'a pas encore reçu trente sollicitations. Segment
     petit, donc peu coûteux en quota ; intention forte, donc meilleur taux de réponse.
  2. **Les secteurs au meilleur rendement mesuré**, d'après le journal de
     `basile_quota` — combien d'enregistrements facturés pour un contact réellement gardé.
     Tant que le journal est vide (premier mois), on suit l'ordre des cibles en attente.

Trois garde-fous, parce que ce script dépense pour de vrai :

  - **`--appliquer` obligatoire.** Sans lui, il compte et montre ce qu'il ferait. Une
    dépense de quota ne doit jamais être le comportement par défaut d'un script.
  - **Budget étalé.** Le reliquat est divisé par le nombre de jours restants, jamais dépensé
    d'un coup : le plan `api` plafonne à 50 000 requêtes/jour, et un seul segment est borné
    à 20 000 (`EXPORT_HARD_CAP`).
  - **Fenêtre nocturne.** Comme tout ce qui écrit dans le pool — `contacts.duckdb` n'a
    qu'un écrivain, et le prendre en journée aveugle le reste de la plateforme
    (cf. l'incident du 21/09).

Usage :
  python3 scripts/basile_brulage.py                    # ce qu'il ferait, sans rien dépenser
  python3 scripts/basile_brulage.py --appliquer        # dépense pour de vrai
  python3 scripts/basile_brulage.py --des-le 5         # commencer à J-5 (défaut : 4)

Cron (une fois par nuit, dans la fenêtre de collecte) :
  30 23 * * * cd /home/autoblog/genesis && python3 scripts/basile_brulage.py --appliquer >> logs/basile_brulage.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

import basile_backend as bb          # noqa: E402
import basile_quota as bq            # noqa: E402

# En dessous, le reliquat ne vaut pas une nuit de collecte : on laisse filer.
PLANCHER = 2_000
# Fenêtre de création considérée comme « récente » (en années civiles).
FENETRE_CREATION_ANS = 1
# Jamais plus que ça sur un seul segment, même si le budget le permet.
PLAFOND_SEGMENT = 5_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def dans_la_fenetre() -> tuple[bool, str]:
    """Même fenêtre que le scraping : 22 h → 8 h. Le pool n'a qu'un écrivain."""
    h = _now().hour
    if h >= 22 or h < 8:
        return True, f"{h}h UTC — dans la fenêtre de collecte"
    return False, f"{h}h UTC — hors fenêtre 22h-8h, le pool doit rester libre"


def segments_prioritaires(site: str = "lcr", limite: int = 40) -> list[dict]:
    """Les couples secteur × département à traiter, les plus rentables d'abord.

    Le rendement mesuré prime sur tout le reste : un secteur qui rend 4 % mérite le
    quota avant un secteur qui rend 0,4 %, quelle que soit la taille de son univers.
    """
    rendements = {r["secteur"]: r["rendement_pct"] for r in bq.rendement(limite=50)}

    cibles: list[dict] = []
    try:
        from duck_ouverture import ouvrir
        c = ouvrir(BASE_DIR / "data" / "god_mode.duckdb")
        try:
            for r in c.execute("""
                SELECT sector, dept_code, COALESCE(valid_total, 0), COALESCE(status, '')
                  FROM autoscrape_targets
                 WHERE site_code = ? AND sector IS NOT NULL AND dept_code IS NOT NULL
            """, [site]).fetchall():
                cibles.append({"secteur": r[0], "dept": str(r[1]),
                               "deja": int(r[2]), "statut": r[3]})
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        print(f"[brulage] cibles illisibles : {str(e)[:150]}", flush=True)
        return []

    # Un secteur jamais mesuré passe devant un secteur mesuré mauvais, mais derrière un
    # secteur mesuré bon : on explore sans renoncer à ce qu'on sait déjà.
    def cle(x: dict):
        r = rendements.get(x["secteur"])
        return (-(r if r is not None else 1.5), x["deja"])

    cibles.sort(key=cle)
    return cibles[:limite]


def filtres_societes_recentes(secteur: str, dept: str) -> dict | None:
    """NAF du secteur + département + créées récemment + encore actives."""
    nafs = bb._nafs(secteur)
    if not nafs:
        return None
    return {
        "naf_code": {"include": nafs},
        "company_ceased": False,
        "headquarters_department_code": {"include": [str(dept)]},
        # `creation_date_min` est une ANNÉE, et Basile l'exige en CHAÎNE :
        # un entier fait « validation_error: must be a string » (constaté le 2026-09-22).
        "creation_date_min": str(_now().year - FENETRE_CREATION_ANS),
    }


def bruler(site: str = "lcr", appliquer: bool = False, des_le: int = 4,
           budget_force: int | None = None) -> dict:
    e = bq.etat()
    jours = e["jours_restants"]
    reste = e["restant"]
    rapport = {"quand": _now().isoformat(timespec="seconds"), "site": site,
               "restant": reste, "jours_restants": jours, "appliquer": appliquer,
               "segments": [], "factures": 0, "gardes": 0}

    if jours > des_le and budget_force is None:
        rapport["action"] = f"rien — J-{jours}, le brûlage commence à J-{des_le}"
        return rapport
    if reste < PLANCHER and budget_force is None:
        rapport["action"] = f"rien — reliquat {reste} sous le plancher de {PLANCHER}"
        return rapport

    ok, pourquoi = dans_la_fenetre()
    if appliquer and not ok:
        rapport["action"] = f"rien — {pourquoi}"
        return rapport

    # Étalé sur les nuits restantes : une seule nuit ne doit pas tout absorber.
    budget = budget_force if budget_force is not None else max(
        PLANCHER, reste // max(1, jours if jours > 0 else 1))
    rapport["budget"] = budget
    rapport["action"] = ("dépense" if appliquer else "simulation") + f" de {budget} enregistrements"

    depense = 0
    for cible in segments_prioritaires(site):
        if depense >= budget:
            break
        filtres = filtres_societes_recentes(cible["secteur"], cible["dept"])
        if not filtres:
            continue
        try:
            univers = bb.count("companies", filtres)          # gratuit
        except Exception as ex:  # noqa: BLE001
            msg = str(ex)[:150]
            rapport["segments"].append({**cible, "erreur": msg})
            if "BASILE_BLOCKED" in msg:
                rapport["action"] = "interrompu — Basile refuse (quota ou plan)"
                break
            continue

        if univers <= 0:
            rapport["segments"].append({**cible, "univers": 0, "pris": 0})
            continue

        a_prendre = min(univers, PLAFOND_SEGMENT, budget - depense)
        ligne = {**cible, "univers": univers, "pris": a_prendre}

        if appliquer:
            res = bb.run_segment(site, "companies", filtres,
                                 sector=cible["secteur"], dept_code=cible["dept"],
                                 max_contacts=a_prendre)
            ligne["factures"] = res.get("collected", 0)
            ligne["gardes"] = res.get("valid", 0)
            ligne["statut"] = res.get("status")
            depense += ligne["factures"]
            rapport["factures"] += ligne["factures"]
            rapport["gardes"] += ligne["gardes"]
            if res.get("status") == "blocked":
                rapport["segments"].append(ligne)
                rapport["action"] = "interrompu — Basile bloqué en cours de brûlage"
                break
        else:
            depense += a_prendre

        rapport["segments"].append(ligne)

    if appliquer and rapport["factures"]:
        try:
            from autoscrape_backend import notify_telegram
            rdt = (100 * rapport["gardes"] / rapport["factures"]) if rapport["factures"] else 0
            notify_telegram(
                f"\U0001f525 *Brûlage Basile* — {rapport['factures']} enregistrements "
                f"dépensés avant expiration, {rapport['gardes']} contacts gardés "
                f"({rdt:.1f} %).\nSociétés créées depuis {FENETRE_CREATION_ANS} an. "
                f"Reliquat : {bq.restant()}.")
        except Exception:  # noqa: BLE001
            pass
    return rapport


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="lcr")
    ap.add_argument("--appliquer", action="store_true",
                    help="dépenser pour de vrai (sans ce drapeau : simulation)")
    ap.add_argument("--des-le", type=int, default=4,
                    help="nombre de jours avant la fin du mois où le brûlage démarre")
    ap.add_argument("--budget", type=int, default=None,
                    help="forcer un budget d'enregistrements (ignore les garde-fous de date)")
    a = ap.parse_args()
    r = bruler(site=a.site, appliquer=a.appliquer, des_le=a.des_le, budget_force=a.budget)
    print(json.dumps(r, ensure_ascii=False, indent=1))
