#!/usr/bin/env python3
"""dirigeants_runner.py — la voie « dirigeants nommés », par petites passes nocturnes.

Basile donne le NOM du gérant d'une société (gratuit, source légale) ; Emelia devine son
email nominatif à partir du nom et du site (**1 crédit par email trouvé**). Le résultat :
un contact avec un prénom, là où la liste noire des adresses de rôle ne laissait plus
qu'un `contact@` inexploitable.

**Pourquoi un lanceur séparé plutôt qu'un appel direct.** La recherche d'email chez Emelia
est asynchrone et LENTE : mesuré le 2026-08-23, quatre contacts en quatorze minutes après
vingt minutes de collecte Basile. Consommer 844 crédits d'une traite demanderait plusieurs
jours de processus ininterrompu — le genre de tâche qu'un redémarrage, un délai d'attente
ou une fermeture de session tue en silence, après avoir dépensé. On découpe donc en passes
courtes, une par nuit, chacune avec son budget.

Deux garde-fous, hérités de `basile_backend.run_dirigeant_segment` :
  - le solde RÉEL est relu chez Emelia avant de partir et toutes les 25 recherches ;
  - un solde illisible ANNULE la passe. Dépenser sans pouvoir compter est le seul cas où
    mieux vaut ne rien faire.

Et un troisième, propre à ce lanceur : **la fenêtre de collecte**. Ces passes tournent la
nuit, comme le scraping, pour ne pas disputer le pool aux envois du matin.

Usage :
    python3 scripts/dirigeants_runner.py --dry-run
    python3 scripts/dirigeants_runner.py --budget 100
    python3 scripts/dirigeants_runner.py --budget 100 --secteur immobilier --dept 44
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

ETAT = BASE_DIR / "memory" / "dirigeants_runner.json"

# Budget par nuit. Volontairement modeste : une passe courte qui aboutit vaut mieux qu'une
# longue qui se fait tuer au milieu après avoir dépensé.
BUDGET_DEFAUT = 100
# Sociétés examinées par passe. Il en faut plus que de crédits : toutes n'ont pas de
# dirigeant renseigné, et tous les emails ne se trouvent pas.
SOCIETES_PAR_PASSE = 250


def _etat() -> dict:
    try:
        return json.loads(ETAT.read_text())
    except Exception:  # noqa: BLE001
        return {"passes": [], "credits_depenses": 0, "contacts": 0}


def _sauver(e: dict) -> None:
    try:
        ETAT.parent.mkdir(parents=True, exist_ok=True)
        ETAT.write_text(json.dumps(e, indent=1, ensure_ascii=False, default=str))
    except Exception as ex:  # noqa: BLE001
        print(f"[dirigeants] état non enregistré : {ex}", flush=True)


def passe(secteur: str = "immobilier", dept: str = "44", region: str | None = "52",
          budget: int = BUDGET_DEFAUT, societes: int = SOCIETES_PAR_PASSE,
          dry_run: bool = False) -> dict:
    import basile_backend as bb

    nafs = bb._nafs(secteur)
    if not nafs:
        return {"ok": False, "erreur": f"aucun code NAF pour le secteur « {secteur} »"}

    filtres = {"naf_code": {"include": nafs},
               "company_ceased": False,
               "headquarters_department_code": {"include": [str(dept)]}}

    debut = datetime.now(timezone.utc)
    r = bb.run_dirigeant_segment("lcr", filtres, sector=secteur, dept_code=str(dept),
                                 region_code=region, max_companies=societes,
                                 use_emelia=not dry_run, dry_run=dry_run,
                                 budget_credits=budget)
    r["secteur"] = secteur
    r["dept"] = str(dept)
    r["debut"] = debut.isoformat(timespec="seconds")
    r["duree_min"] = round((datetime.now(timezone.utc) - debut).total_seconds() / 60, 1)

    if not dry_run:
        e = _etat()
        e["passes"] = (e.get("passes") or [])[-19:] + [{
            "quand": r["debut"], "secteur": secteur, "dept": str(dept),
            "credits": r.get("emelia_calls", 0), "contacts": r.get("valid", 0),
            "statut": r.get("status"), "duree_min": r["duree_min"]}]
        e["credits_depenses"] = e.get("credits_depenses", 0) + r.get("emelia_calls", 0)
        e["contacts"] = e.get("contacts", 0) + r.get("valid", 0)
        e["solde_apres"] = bb._solde_emelia()
        _sauver(e)
        r["cumul"] = {"credits_depenses": e["credits_depenses"],
                      "contacts": e["contacts"], "solde": e["solde_apres"]}
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--secteur", default="immobilier")
    ap.add_argument("--dept", default="44")
    ap.add_argument("--region", default="52")
    ap.add_argument("--budget", type=int, default=BUDGET_DEFAUT)
    ap.add_argument("--societes", type=int, default=SOCIETES_PAR_PASSE)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    out = passe(a.secteur, a.dept, a.region, a.budget, a.societes, a.dry_run)
    print(json.dumps({k: v for k, v in out.items() if not isinstance(v, list)},
                     indent=1, ensure_ascii=False, default=str), flush=True)
