#!/usr/bin/env python3
"""L'heure à laquelle on a le droit d'envoyer. Une seule fois (Lot F, 2026-08-26).

La même mécanique était écrite trois fois : `deliverability_agent.within_send_window`
pour les campagnes, `mozart.fenetre_ouverte` pour les scénarios, et le rythme intra-lot de
`maildoso_backend._cadence`. Trois copies d'une règle divergent toujours — celles-ci
différaient d'une heure de chaque côté, sans raison retrouvée.

**Mais la duplication n'était pas le vrai danger.** Le vrai danger, c'est que ni
`send_email` ni `send_batch` ne contrôlaient l'heure : ce sont les APPELANTS qui le
faisaient. Un nouveau chemin d'appel — un script de rattrapage, un bouton d'écran, un cron
ajouté un soir — envoyait donc à 3 h du matin sans que rien ne s'y oppose. La règle vit
désormais dans `send_email`, le seul point par lequel tout envoi passe, comme la fenêtre
de non-recontact de 120 jours avant elle.

Alignement du 2026-08-26, décidé par Camille : les scénarios adoptent la fenêtre des
campagnes. Mozart visait 09:01–18:30, plus étroit au matin et plus tard le soir ; c'était
délibéré (un scénario part sans que personne le regarde partir, autant viser le cœur de la
journée) mais cela faisait deux vérités pour une même question.

Ce qui NE passe PAS par une fenêtre, et ne doit pas y passer : les emails transactionnels
— confirmation de rendez-vous — et les BAT. Ils répondent à un geste que quelqu'un vient
de faire ; les retenir jusqu'à lundi 8h01 serait absurde.
"""
from __future__ import annotations

from datetime import datetime, timedelta

FUSEAU = "Europe/Paris"

# 0 = lundi … 6 = dimanche (convention `weekday()`, identique au champ `days` d'Emelia —
# vérifiée le 2026-07-30 par un envoi réel).
_LUNDI_SAMEDI = (0, 1, 2, 3, 4, 5)

# Un profil par nature d'envoi. Ils sont identiques depuis l'alignement : les garder
# séparés permet d'en rouvrir un sans toucher à l'autre, et surtout de LIRE dans le code
# quelle nature d'envoi on est en train de régler.
PROFILS: dict[str, dict] = {
    "campagne": {"jours": _LUNDI_SAMEDI, "debut": "08:01", "fin": "17:59",
                 "libelle": "campagnes"},
    "scenario": {"jours": _LUNDI_SAMEDI, "debut": "08:01", "fin": "17:59",
                 "libelle": "scénarios"},
}

DEFAUT = "campagne"


def maintenant():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(FUSEAU))
    except Exception:  # noqa: BLE001
        # Repli sans fuseau : mieux vaut une heure approchée qu'une exception dans le
        # chemin d'envoi. Le serveur vit en UTC, donc la fenêtre se décale — c'est
        # volontairement le cas le moins grave, il ne survient que si zoneinfo manque.
        return datetime.now()


def profil(nom: str | None) -> dict:
    return PROFILS.get((nom or DEFAUT), PROFILS[DEFAUT])


def ouverte(nom: str | None = None, quand=None) -> tuple[bool, str]:
    """(autorisé, motif du refus). Le motif est rendu pour être affiché tel quel."""
    p = profil(nom)
    q = quand or maintenant()
    if q.weekday() not in p["jours"]:
        return False, "dimanche — aucun envoi ce jour"
    hhmm = q.strftime("%H:%M")
    if hhmm < p["debut"]:
        return False, (f"trop tôt — les envois reprennent à {p['debut']} "
                       f"(il est {hhmm} à Paris)")
    if hhmm > p["fin"]:
        return False, (f"trop tard — plus d'envoi après {p['fin']} "
                       f"(il est {hhmm} à Paris)")
    return True, ""


def prochaine_ouverture(nom: str | None = None, quand=None):
    """Le prochain instant où la fenêtre sera ouverte. Sert à REPORTER proprement.

    Sans lui, un contact bloqué à 18h31 serait réessayé toutes les heures de la nuit.
    """
    p = profil(nom)
    q = quand or maintenant()
    h, m = (int(x) for x in p["debut"].split(":"))
    cible = q.replace(hour=h, minute=m, second=0, microsecond=0)
    if q.strftime("%H:%M") >= p["debut"]:
        cible = cible + timedelta(days=1)
    # Au plus sept sauts : on ne peut pas tomber sur sept dimanches d'affilée.
    for _ in range(8):
        if cible.weekday() in p["jours"]:
            return cible
        cible = cible + timedelta(days=1)
    return cible


def est_lot_de_campagne(campaign_id: str | None) -> bool:
    """Un lot de campagne vaut « {site}-{campagne}-{AAAA}-{MM}-{JJ} », donc six segments.

    Même règle que `maildoso_backend._journaliser_hors_campagne` : tout le reste — chaîne
    vide, « lcr-bat », un nom de gabarit — est un envoi hors campagne, donc immédiat.
    Une seule définition de « lot de campagne », sinon les deux dérivent.
    """
    return len((campaign_id or "").split("-")) >= 6


def profil_pour(campaign_id: str | None, usage: str | None) -> str | None:
    """Quelle fenêtre s'applique à CET envoi ? `None` = aucune (BAT, test, transactionnel).

    On ne devine pas au hasard : un scénario se reconnaît à son `usage`, un lot de
    campagne à la forme de son identifiant. Ce qui n'est ni l'un ni l'autre répond à un
    geste humain immédiat et part tout de suite.
    """
    if (usage or "") == "mozart" or "-mozart-" in (campaign_id or ""):
        return "scenario"
    if est_lot_de_campagne(campaign_id):
        return "campagne"
    return None
