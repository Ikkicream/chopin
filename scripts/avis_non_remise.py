#!/usr/bin/env python3
"""scripts/avis_non_remise.py — lire un avis de non-remise (DSN, RFC 3464). Fonctions PURES.

Pourquoi (audit du 2026-11-23) : 3 469 envois Maildoso en 30 jours, ZÉRO rebond enregistré.
Maildoso n'a pas de webhook de rebond : un refus revient comme un email « Mail Delivery
System » / MAILER-DAEMON dans la boîte expéditrice. `reponses_imap.py` relevait bien ces
boîtes, mais ne gardait que les messages venant d'une adresse à qui Cheffer avait écrit —
un avis de non-remise vient du serveur, jamais du destinataire : il était jeté, toujours.

    analyser(msg) -> {"adresses": {adresse: statut}, "action": "failed"|"delayed"|None}

Le statut est le code étendu SMTP (« 5.1.1 », « 4.2.2 »…) ou None s'il n'est pas lisible.
"""
from __future__ import annotations

import re

_EXPEDITEUR = re.compile(r"mailer-daemon|postmaster|mail delivery (sub)?system", re.I)
_STATUT = re.compile(r"\b([245]\.\d{1,3}\.\d{1,3})\b")
_ADRESSE = re.compile(r"(?:Final|Original)-Recipient:\s*rfc822;\s*<?([^\s>;]+@[^\s>;]+)", re.I)


def est_avis(msg) -> bool:
    """Un avis de non-remise, d'après son type (multipart/report) ou son expéditeur."""
    if msg.get_content_type() == "multipart/report" and \
            "delivery-status" in (msg.get_param("report-type") or "").lower():
        return True
    return bool(_EXPEDITEUR.search(str(msg.get("From", ""))))


def analyser(msg) -> dict:
    adresses: dict[str, str | None] = {}
    actions: set[str] = set()
    for h in msg.get_all("X-Failed-Recipients") or []:
        for a in str(h).split(","):
            if "@" in a:
                adresses.setdefault(a.strip().lower(), None)
    for part in msg.walk():
        ct = part.get_content_type()
        if ct in ("message/delivery-status", "message/global-delivery-status"):
            charge = part.get_payload()
            blocs = charge if isinstance(charge, list) else []
            for bloc in blocs:
                adr = None
                for champ in ("Final-Recipient", "Original-Recipient"):
                    v = str(bloc.get(champ) or "")
                    if "@" in v:
                        adr = v.split(";")[-1].strip(" <>").lower()
                        break
                action = str(bloc.get("Action") or "").strip().lower()
                if action:
                    actions.add(action)
                if adr:
                    m = _STATUT.search(str(bloc.get("Status") or ""))
                    adresses[adr] = m.group(1) if m else adresses.get(adr)
        elif ct == "text/plain" and not adresses:
            try:
                corps = part.get_payload(decode=True)
                corps = corps.decode(part.get_content_charset() or "utf-8", "replace") if corps \
                    else str(part.get_payload())
            except Exception:  # noqa: BLE001
                continue
            for a in _ADRESSE.findall(corps):
                adresses.setdefault(a.lower(), None)
            m = re.search(r"^Action:\s*(\w+)", corps, re.I | re.M)
            if m:
                actions.add(m.group(1).lower())
            s = _STATUT.search(corps)
            if s:
                for a in adresses:
                    adresses[a] = adresses[a] or s.group(1)
    if "failed" in actions:
        action = "failed"
    elif actions and actions <= {"delayed", "relayed", "delivered", "expanded"}:
        action = "delayed"          # un retard n'est pas un rebond : on ne l'enregistre pas
    else:
        sujet = str(msg.get("Subject", ""))
        action = "delayed" if re.search(r"delay|retard|d[ée]lai", sujet, re.I) else \
            ("failed" if adresses else None)
    return {"adresses": adresses, "action": action}


def nature(statut: str | None) -> str:
    """'hard' (5.x.x, ou illisible : un avis d'échec définitif) | 'soft' (4.x.x)."""
    return "soft" if statut and statut.startswith("4.") else "hard"
