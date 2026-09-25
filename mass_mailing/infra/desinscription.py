#!/usr/bin/env python3
"""mass_mailing/infra/desinscription.py — le lien de désinscription de chaque mail.

Chaque mail porte un lien PROPRE à son destinataire :
    https://api.cheffer.email/api/public/mass-mailing/desinscription?t=<jeton>

Le jeton = identifiant du destinataire + signature HMAC-SHA256. Il ne contient pas
l'adresse (un lien transféré ne la révèle pas) et ne se fabrique pas sans le secret :
personne ne peut désinscrire quelqu'un d'autre en devinant un numéro.

Le secret vit dans le stockage privé du module (0600), créé au premier usage — pas
dans `.env`, que ce module ne doit pas modifier.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from pathlib import Path

from . import stockage

BASE_PUBLIQUE = os.environ.get("GENESIS_PUBLIC_URL", "https://api.cheffer.email").rstrip("/")
CHEMIN = "/api/public/mass-mailing/desinscription"
_SECRET_FICHIER = stockage.RACINE / ".secret_desinscription"


def _secret() -> bytes:
    if not _SECRET_FICHIER.exists():
        stockage.RACINE.mkdir(parents=True, exist_ok=True)
        fd = os.open(_SECRET_FICHIER, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    return bytes.fromhex(Path(_SECRET_FICHIER).read_text().strip())


def _signe(recipient_id: int) -> str:
    mac = hmac.new(_secret(), f"mm-unsub:{recipient_id}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac[:16]).decode().rstrip("=")


def jeton(recipient_id: int) -> str:
    return f"{recipient_id}.{_signe(recipient_id)}"


def lire_jeton(t: str) -> int | None:
    """Identifiant du destinataire si la signature est bonne, sinon None."""
    try:
        rid_txt, sig = (t or "").split(".", 1)
        rid = int(rid_txt)
    except ValueError:
        return None
    return rid if hmac.compare_digest(sig, _signe(rid)) else None


def url(recipient_id: int) -> str:
    return f"{BASE_PUBLIQUE}{CHEMIN}?t={jeton(recipient_id)}"


def pied_de_mail(html: str, recipient_id: int, expediteur_nom: str) -> str:
    """Ajoute le pied obligatoire (lien de désinscription) juste avant </body>.

    `data-url-type="unsub"` : Sweego compte ce clic comme une désinscription et non
    comme un clic d'intérêt (doc : SKILL.md § 3)."""
    pied = (
        '<div style="margin-top:32px;padding-top:12px;border-top:1px solid #e5e5e5;'
        'font-family:Arial,sans-serif;font-size:12px;color:#888;text-align:center">'
        f'Vous recevez cet email de la part de {expediteur_nom}. '
        f'<a href="{url(recipient_id)}" data-url-type="unsub" style="color:#888">'
        'Se désinscrire</a></div>'
    )
    bas = html.lower()
    i = bas.rfind("</body>")
    return html[:i] + pied + html[i:] if i >= 0 else html + pied


def texte_pied(recipient_id: int) -> str:
    return f"\n\n--\nSe désinscrire : {url(recipient_id)}\n"
