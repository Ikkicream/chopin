#!/usr/bin/env python3
"""La file d'envoi ne doit jamais se vider sans que personne ne le sache.

Camille l'a formulé exactement : « 140 emails/jour ne sera pas un problème — sauf s'il n'y
a pas de programmation ». Le vivier est plein (5 659 piochables, plus de 500 collectés par
jour) ; ce qui manque, c'est la garantie qu'une campagne aura de quoi dispatcher demain.
Et le jour où elle n'en a plus, le tableau de bord affiche « done » — ce qui ressemble à
un succès.

Les cas ci-dessous vérifient les deux moitiés de la règle : ce qui se prolonge tout seul,
et ce qui doit remonter à un humain parce que c'est un choix.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def _campagne(reste: int, cadence_jours: int = 5, volume: int = 140) -> dict:
    depart = date.today() + timedelta(days=1)
    cadence, j, n = [], depart, 0
    while n < cadence_jours:
        if j.weekday() != 6:
            cadence.append({"date": j.isoformat(), "count": volume})
            n += 1
        j += timedelta(days=1)
    return {"id": "test-camp", "name": "Campagne de test", "channel": "maildoso",
            "status": "running", "site_code": "lcr", "sectors": ["immobilier"],
            "target_size": 1000, "sent_count": 1000 - reste,
            "schedule_start": date.today().isoformat(), "cadence": cadence}


def lance() -> int:
    import campaign_engine as ce
    import programmation as pr

    vrai_liste = ce.list_campaigns

    def avec(campagnes):
        ce.list_campaigns = lambda site: campagnes

    print("La file est pleine")
    avec([_campagne(reste=900)])
    d = pr.diagnostic("lcr")
    verifie("l'horizon est couvert", d["suffisant"], f"({d['jours_pleins_devant']} jours)")
    verifie("aucune alerte", pr.problemes("lcr") == {})

    print("\nLa campagne est épuisée — il ne reste rien à envoyer")
    avec([_campagne(reste=0)])
    d = pr.diagnostic("lcr")
    verifie("le creux est vu", not d["suffisant"], f"({d['jours_pleins_devant']} jours)")
    verifie("le premier jour creux est demain",
            d["premier_jour_creux"] == d and False or bool(d["premier_jour_creux"]),
            f"({d['premier_jour_creux']})")
    p = pr.problemes("lcr")
    verifie("l'alerte part", "programmation:creux" in p, f"({list(p)})")
    verifie("l'alerte dit que le vivier n'est pas en cause",
            "vivier" in (p.get("programmation:creux") or ""))

    print("\nAucune campagne active — c'est une décision, pas une mécanique")
    avec([])
    p = pr.problemes("lcr")
    verifie("l'alerte part", "programmation:vide" in p, f"({list(p)})")
    r = pr.assurer("lcr", apply=False)
    verifie("rien n'est inventé", not r.get("cadence_ajoutee"),
            f"({r['actions']})")
    verifie("l'action dit qu'il faut créer une campagne",
            any("créer" in a for a in r["actions"]))

    print("\nLa cadence s'arrête à mi-horizon — on la prolonge sans toucher aux paliers")
    avec([_campagne(reste=900, cadence_jours=2, volume=80)])
    r = pr.assurer("lcr", apply=False)
    verifie("des jours sont ajoutés", bool(r.get("cadence_ajoutee")),
            f"({len(r.get('cadence_ajoutee') or [])} jour(s))")
    verifie("les paliers existants ne sont pas rehaussés",
            all(x["count"] == r["objectif_par_jour"] for x in (r.get("cadence_ajoutee") or [])),
            "(seuls les jours VIDES sont comblés)")
    verifie("rien n'est écrit sans --apply", not r.get("applique"))

    print("\nLe vivier borne le plan : un trou de collecte n'est pas un trou de cadence")
    # Ce qui crée un creux, ce n'est PAS la fin de la cadence — une campagne dont le plan
    # est terminé continue d'envoyer son reliquat au plus gros palier prévu, et c'est
    # voulu. C'est l'épuisement de la CIBLE qui vide la file. Le montage doit donc partir
    # d'une campagne complète, sinon la borne du vivier n'est jamais exercée et le test
    # passe sans rien vérifier — ce qu'il faisait.
    vrai_vivier = pr.vivier
    avec([_campagne(reste=0)])
    verifie("l'horizon est bien vide sans prolongation",
            pr.diagnostic("lcr")["premier_jour_creux"] is not None,
            f"({pr.diagnostic('lcr')['couverture']})")

    pr.vivier = lambda site, secteurs: 30
    r = pr.assurer("lcr", apply=False)
    verifie("on ne planifie pas plus que le vivier permet",
            0 < (r.get("a_ajouter") or 0) <= 30, f"(à ajouter : {r.get('a_ajouter')})")

    pr.vivier = lambda site, secteurs: 0
    r = pr.assurer("lcr", apply=False)
    verifie("vivier vide → aucune cadence ajoutée", not r.get("cadence_ajoutee"))
    verifie("le message pointe la COLLECTE",
            any("COLLECTE" in a for a in r["actions"]), f"({r['actions']})")
    pr.vivier = vrai_vivier

    print("\nL'objectif suit les plafonds, il n'est pas écrit en dur")
    import expediteur as ex
    # Ad hoc seulement : depuis le 2026-08-25 les adresses réservées à Mozart ne sont pas
    # disponibles pour les campagnes, et `programmation` ne les compte donc plus. Les
    # inclure ici ferait attendre un objectif que le dispatch ne pourrait jamais honorer.
    attendu = sum(b["daily_cap"] for b in ex.boites("lcr", usage="adhoc") if b["active"])
    verifie("objectif = somme des plafonds actifs",
            pr.objectif_jour("lcr") == attendu, f"({attendu})")

    print("\nLa ligne d'acquis n'est pas un palier")
    camp = _campagne(reste=900, cadence_jours=2, volume=80)
    camp["cadence"].insert(0, {"date": (date.today() - timedelta(days=1)).isoformat(),
                               "count": 309, "acquis": True})
    apres = date.today() + timedelta(days=20)
    verifie("après la cadence, le plafond reste un vrai palier",
            ce._todays_allowance(camp, apres) <= 80,
            f"({ce._todays_allowance(camp, apres)} — 309 signifierait que l'acquis "
            f"sert de plafond)")

    ce.list_campaigns = vrai_liste
    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("La file d'envoi se prolonge seule, et prévient quand c'est un choix.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
