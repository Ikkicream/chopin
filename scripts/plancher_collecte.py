#!/usr/bin/env python3
"""plancher_collecte.py — la journée ne se termine pas sous 500 contacts.

Demande de Camille (2026-08-24) : « à minuit, si aucun scrape ne tourne, déclenche un
scrape sur n'importe quel secteur ; et tant que tu n'as pas collecté 500 contacts, tu
continues pendant la soirée. »

Le constat qui la motive, mesuré sur dix jours : 2 264 contacts le 20/08, puis **292 le
21**, **313 le 22**, 747 le 23. La machine sait collecter ; elle ne garantit pas de le
faire. `autoscrape_daily tick` tourne toutes les quinze minutes et décide seul de passer
son tour — plafond de cibles atteint, créneau réservé, fenêtre fermée, passe en cours mal
close. Chacune de ces raisons est bonne prise isolément ; leur somme fait des journées à
292 contacts sans que rien ne s'en émeuve.

Ce module ne remplace pas le scraper : **il le réveille et il compte.** Deux gestes, et
c'est tout :

  - si on est sous le plancher, qu'aucun scrape ne tourne et que rien ne l'interdit, il
    lance une passe — n'importe quel secteur autorisé, celui que la file propose ;
  - si on est sous le plancher et qu'il ne PEUT pas lancer, il dit pourquoi. C'est la
    moitié qui manquait : une journée à 292 contacts ne produisait aucun signal.

Ce qu'il ne fait jamais : forcer un créneau réservé (enrichissement, dispatch), dépasser
le quota Serper du jour, ou toucher à un secteur interdit. Un plancher qui piétine les
garde-fous existants n'est plus un plancher, c'est une fuite.

Usage :
    python3 scripts/plancher_collecte.py            # état, ne lance rien
    python3 scripts/plancher_collecte.py --assurer  # lance si nécessaire
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

PLANCHER = 500          # contacts par jour, demande de Camille
SITE = "lcr"


def collectes_du_jour(site: str = SITE) -> dict:
    """Contacts créés aujourd'hui, en heure de Paris, par source.

    En UTC, tout ce qui entre entre minuit et 2 h compterait pour la veille — or c'est
    précisément la tranche où le scraping nocturne travaille le plus.
    """
    import pool_pg
    lignes = pool_pg._q("""
        SELECT COALESCE(primary_source, '?'), count(*)
        FROM contacts
        WHERE timezone('Europe/Paris', created_at)::date
              = timezone('Europe/Paris', now())::date
        GROUP BY 1 ORDER BY 2 DESC""")
    par_source = {r[0]: int(r[1]) for r in lignes}
    return {"total": sum(par_source.values()), "par_source": par_source}


def etat(site: str = SITE, plancher: int = PLANCHER) -> dict:
    """Où on en est, et ce qui empêche d'avancer si on n'avance pas."""
    import autoscrape_daily as ad
    import autoscrape_backend as asb

    jour = collectes_du_jour(site)
    manque = max(0, plancher - jour["total"])

    live = {}
    try:
        live = asb.read_status(site) or {}
    except Exception as e:  # noqa: BLE001
        live = {"status": f"illisible: {type(e).__name__}"}
    en_cours = live.get("status") == "running"

    decision = {}
    try:
        decision = ad.decide()
    except Exception as e:  # noqa: BLE001
        decision = {"action": "erreur", "why": f"{type(e).__name__}: {e}"[:160]}

    fenetre_ok, pourquoi_fenetre = asb.within_scrape_window()

    return {
        "site": site, "plancher": plancher,
        "collectes": jour["total"], "par_source": jour["par_source"],
        "manque": manque, "atteint": manque == 0,
        "scrape_en_cours": en_cours,
        "scrape_bloque": bool(live.get("blocked")),
        "fenetre_ouverte": fenetre_ok, "fenetre": pourquoi_fenetre,
        "decision": {"action": decision.get("action"), "pourquoi": decision.get("why")},
    }


def assurer(site: str = SITE, plancher: int = PLANCHER, appliquer: bool = False) -> dict:
    """Réveille le scraper si le plancher n'est pas atteint et que rien ne l'interdit."""
    import autoscrape_daily as ad

    e = etat(site, plancher)
    e["appliquer"] = appliquer
    e["actions"] = []

    if e["atteint"]:
        e["actions"].append(f"plancher atteint ({e['collectes']}/{plancher})")
        return e
    if e["scrape_en_cours"]:
        e["actions"].append("un scrape tourne déjà — on le laisse travailler")
        return e
    if not e["fenetre_ouverte"]:
        e["actions"].append(f"hors fenêtre de collecte : {e['fenetre']}")
        return e
    if e["decision"]["action"] in ("skip", "erreur"):
        # Le scraper refuse de partir. La raison est bonne (créneau réservé, quota) ou
        # elle ne l'est pas (file vide, fournisseur bloqué) — dans les deux cas elle doit
        # SE VOIR, puisqu'on finit la journée sous le plancher.
        e["actions"].append(f"le scraper ne peut pas partir : {e['decision']['pourquoi']}")
        return e

    e["actions"].append(f"réveil du scraper — il manque {e['manque']} contact(s) "
                        f"({e['decision']['action']} : {e['decision']['pourquoi']})")
    if appliquer:
        try:
            e["lancement"] = ad.tick(launch=True)
        except Exception as ex:  # noqa: BLE001
            e["lancement"] = {"ok": False, "erreur": f"{type(ex).__name__}: {ex}"[:160]}
    return e


def problemes(site: str = SITE) -> dict[str, str]:
    """Alerte de fin de journée : on va terminer sous le plancher.

    Volontairement tardive — avant 20 h, être sous le plancher est normal, la nuit n'a pas
    encore travaillé. Une alerte qui part à midi pour un chiffre qui se rattrape le soir
    n'apprend rien à personne, et on cesse de la lire.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    heure = datetime.now(ZoneInfo("Europe/Paris")).hour
    if heure < 20:
        return {}
    try:
        e = etat(site)
    except Exception as ex:  # noqa: BLE001
        return {"plancher": f"🕷 L'état de la collecte est illisible : {ex}"}
    if e["atteint"]:
        return {}
    detail = e["decision"]["pourquoi"] or "raison inconnue"
    return {"plancher:collecte": (
        f"🕷 *Collecte sous le plancher* : {e['collectes']} contacts aujourd'hui "
        f"pour un objectif de {e['plancher']}.\n"
        f"   Scrape en cours : {'oui' if e['scrape_en_cours'] else 'NON'}. "
        f"Le scraper dit : « {detail} ».")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=SITE)
    ap.add_argument("--plancher", type=int, default=PLANCHER)
    ap.add_argument("--assurer", action="store_true")
    a = ap.parse_args()
    print(json.dumps(assurer(a.site, a.plancher, appliquer=a.assurer),
                     indent=1, ensure_ascii=False, default=str))
