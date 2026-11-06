#!/usr/bin/env python3
"""mass_mailing/infra/fournisseurs.py — quel fournisseur d'envoi pour l'espace courant.

- Espace interne (`mass_mailing`) : Sweego, comme avant.
- Espace client (`mmc_<slug>`)    : Resend ou SES selon la fiche client — JAMAIS Sweego
  (décision de Camille, 13/10/2026). Si la fiche est introuvable, on refuse : mieux vaut
  un envoi bloqué qu'un client qui part sur la réputation interne.

Chaque module renvoyé expose la même interface que `infra/sweego.py`.
"""
from __future__ import annotations

from . import pg


class FournisseurInterdit(RuntimeError):
    pass


def client_courant() -> dict | None:
    schema = pg.schema_courant()
    if schema == pg.SCHEMA:
        return None
    with pg.espace(pg.SCHEMA):
        fiche = pg.ligne("SELECT * FROM clients WHERE schema_pg = %(s)s", {"s": schema})
    if not fiche:
        raise FournisseurInterdit(f"aucun client pour le schéma {schema}")
    return fiche


def nom() -> str:
    c = client_courant()
    return "sweego" if c is None else c["fournisseur"]


def module():
    n = nom()
    if n == "sweego":
        from . import sweego
        return sweego
    if n == "resend":
        from . import resend
        return resend
    if n == "ses":
        raise FournisseurInterdit("SES n'est pas encore branché (configuration prévue plus tard)")
    raise FournisseurInterdit(f"fournisseur inconnu : {n}")


def libelle() -> str:
    return {"sweego": "Sweego", "resend": "Resend", "ses": "Amazon SES"}.get(nom(), nom())
