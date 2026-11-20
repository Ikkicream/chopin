#!/usr/bin/env python3
"""mass_mailing/infra/compteur_envois.py — compteur d'envois du superadmin (Camille, 21/10/2026).

« un compteur en haut dans le header des quotas journalier, hebdo, au mois, envoyé par envoyé ».

Tous les espaces CLIENTS partagent UN compte Resend (clé `RESEND_API_KEY`) : c'est lui qui a un
quota. Le 21/10 à midi, le compte était encore en offre gratuite et Resend a coupé l'envoi après
217 mails dans la journée ; personne ne le voyait venir.

    jour     envoyés aujourd'hui (Paris) / somme des plafonds de warm-up des adresses actives
    semaine  envoyés depuis lundi        / somme des plafonds de warm-up de lundi à dimanche
    mois     envoyés depuis le 1er       / quota mensuel du compte Resend (`RESEND_QUOTA_MOIS`)

« Envoyé » = accepté par Resend (`recipients.submitted_at`), tous clients confondus. Les BAT et
les tests hors campagne n'y sont pas : Resend les compte, nous non (écart de quelques unités).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import clients, pg

PARIS = ZoneInfo("Europe/Paris")
# Offre Transactional Pro prise le 21/10/2026 : 50 000 mails par mois, pas de quota par jour.
QUOTA_MOIS = int(os.environ.get("RESEND_QUOTA_MOIS") or 50_000)


def bornes(maintenant: datetime | None = None) -> dict:
    """Fonction PURE : début du jour, de la semaine (lundi) et du mois, à Paris."""
    m = (maintenant or datetime.now(PARIS)).astimezone(PARIS)
    jour = m.replace(hour=0, minute=0, second=0, microsecond=0)
    return {"jour": jour, "semaine": jour - timedelta(days=jour.weekday()), "mois": jour.replace(day=1)}


def etat() -> dict:
    b = bornes()
    total = {"jour": 0, "semaine": 0, "mois": 0}
    plafond = {"jour": 0, "semaine": 0}
    for c in clients.lister():
        if c.get("statut") != "actif":
            continue
        try:
            with pg.espace(clients.schema_de(c["slug"])):
                n = pg.ligne("""SELECT count(*) FILTER (WHERE submitted_at >= %(j)s) AS jour,
                                       count(*) FILTER (WHERE submitted_at >= %(s)s) AS semaine,
                                       count(*) AS mois
                                  FROM recipients WHERE submitted_at >= %(m)s""",
                             {"j": b["jour"], "s": b["semaine"], "m": b["mois"]}) or {}
                exps = pg.lignes("SELECT * FROM expediteurs WHERE actif")
        except Exception:  # noqa: BLE001 — espace pas encore provisionné
            continue
        for k in total:
            total[k] += int(n.get(k) or 0)
        for e in exps:
            plafond["jour"] += clients.plafond_du_jour(e, b["jour"].date())
            plafond["semaine"] += sum(clients.plafond_du_jour(e, (b["semaine"] + timedelta(days=i)).date()) for i in range(7))
    return {"jour": {"envoyes": total["jour"], "quota": plafond["jour"], "source": "warm-up"},
            "semaine": {"envoyes": total["semaine"], "quota": plafond["semaine"], "source": "warm-up"},
            "mois": {"envoyes": total["mois"], "quota": QUOTA_MOIS, "source": "Resend"},
            "a": datetime.now(PARIS).isoformat()}
