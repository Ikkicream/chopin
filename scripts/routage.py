#!/usr/bin/env python3
"""routage.py — quel canal pour quel contact, sans jamais trahir l'affinité.

Cheffer dispose de trois canaux : Maildoso (SMTP, une boîte nommée par envoi, suivi par
pixel et redirection), Sweego (envoi de masse, aucun suivi par destinataire) et Emelia
(payant). Router automatiquement, ce serait basculer un lot d'un canal à l'autre quand le
premier est saturé — et c'est là que le piège se referme.

**Changer de canal, c'est changer d'adresse expéditrice.** Or la décision de Camille du
2026-08-23 est exactement l'inverse : un contact qui a ouvert ou cliqué garde son
expéditeur pour toujours, parce que ce geste vaut signal positif dans son client de
messagerie. Un routage qui ignore cette règle détruirait, en cherchant du volume, le
capital que l'affinité est là pour protéger.

La règle du module tient donc en une phrase : **le volume se cherche sur les contacts qui
n'ont rien à perdre.** Un contact dont l'affinité est CONFIRMÉE ne sort jamais de son
canal ; il attend. Un contact neuf, ou attitré sans avoir jamais réagi, peut partir par
n'importe quel canal disponible.

Le module ne bascule rien tout seul : il dit ce qui est routable et ce qui ne l'est pas.
Le basculement d'un lot reste déclenché par une campagne, donc par une décision.
"""
from __future__ import annotations

CANAUX = ("maildoso", "sweego", "emelia")

# Le canal qui porte l'affinité. Les autres n'ont pas de notion de boîte expéditrice par
# contact : Sweego envoie en masse depuis un domaine, Emelia depuis sa propre
# infrastructure. Passer par eux revient donc toujours à changer d'expéditeur.
CANAL_AFFINITE = "maildoso"


def _q(sql: str, params=None) -> list[tuple]:
    import pool_pg
    return pool_pg._q(sql, params or {})


def capacite_du_jour(site: str) -> dict[str, dict]:
    """Ce que chaque canal peut encore absorber aujourd'hui.

    Maildoso se calcule boîte par boîte (plafonds, repos, envois déjà faits). Les deux
    autres n'ont pas de plafond côté Cheffer : leur limite est contractuelle, pas
    technique — on la rend explicitement inconnue plutôt que de l'inventer.
    """
    import expediteur
    boites = expediteur.boites(site)
    return {
        "maildoso": {
            "reste": sum(b["reste"] for b in boites if b["active"]),
            "boites_actives": sum(1 for b in boites if b["active"]),
            "boites_au_repos": sum(1 for b in boites if b.get("au_repos_jusqu_a")),
            "detail": {b["email"]: b["reste"] for b in boites},
        },
        "sweego": {"reste": None, "note": "plafond contractuel, non connu de Cheffer"},
        "emelia": {"reste": None, "note": "plafond contractuel, non connu de Cheffer"},
    }


def contacts_verrouilles(emails: list[str]) -> set[str]:
    """Parmi ces adresses, celles qui ne peuvent PAS quitter leur canal.

    Ce sont les affinités confirmées : le prospect a ouvert ou cliqué depuis une adresse
    précise. Lui écrire d'ailleurs, c'est repartir de zéro auprès de lui.
    """
    ems = [(e or "").strip().lower() for e in emails if e]
    if not ems:
        return set()
    return {r[0] for r in _q("""
        SELECT lower(email::text) FROM contacts
        WHERE lower(email::text) = ANY(%(ems)s)
          AND boite_expediteur_confirmee AND boite_expediteur IS NOT NULL""",
        {"ems": ems})}


def filtrer_pour_canal(contacts: list[dict], canal: str) -> tuple[list[dict], list[dict]]:
    """Sépare ce qui peut partir par CE canal de ce qui doit rester sur le sien.

    Rend `(routables, verrouilles)`. Sur `maildoso`, rien n'est verrouillé — c'est le canal
    qui porte l'affinité, chacun y retrouve sa boîte. Sur les autres, tout contact à
    l'affinité confirmée est écarté du lot et le reste : ce n'est pas une erreur, c'est la
    règle qui s'applique.
    """
    if canal == CANAL_AFFINITE:
        return list(contacts), []
    verrous = contacts_verrouilles([c.get("email") for c in contacts])
    routables = [c for c in contacts
                 if (c.get("email") or "").strip().lower() not in verrous]
    bloques = [c for c in contacts
               if (c.get("email") or "").strip().lower() in verrous]
    return routables, bloques


def diagnostic(site: str = "lcr") -> dict:
    """Ce que le routage peut et ne peut pas faire aujourd'hui."""
    import expediteur
    repartition = expediteur.repartition(site)
    confirmes = sum(v["confirmes"] for k, v in repartition.items()
                    if k != "(non attribué)")
    attribues = sum(v["contacts"] for k, v in repartition.items()
                    if k != "(non attribué)")
    libres = (repartition.get("(non attribué)") or {}).get("contacts", 0)
    return {
        "site": site,
        "capacite": capacite_du_jour(site),
        "contacts_verrouilles_sur_maildoso": confirmes,
        "contacts_attitres_non_confirmes": attribues - confirmes,
        "contacts_sans_affinite": libres,
        "note": ("Seuls les contacts sans affinité confirmée peuvent changer de canal. "
                 f"{confirmes} contacts ont gagné un signal positif sur leur adresse "
                 f"actuelle : les router ailleurs le détruirait."),
    }
