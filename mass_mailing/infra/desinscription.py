#!/usr/bin/env python3
"""mass_mailing/infra/desinscription.py — le lien de désinscription de chaque mail.

Chaque mail porte un lien PROPRE à son destinataire :
    https://mail.cheffer.email/api/public/mass-mailing/desinscription?t=<jeton>

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

# Depuis le 2026-09-26, Mass Email a son propre nom : les nouveaux liens (désinscription,
# page de rappel, version en ligne, piège) y pointent. Les liens déjà envoyés sur
# api.cheffer.email restent servis — Nginx les confie au même service.
BASE_PUBLIQUE = os.environ.get("MM_PUBLIC_URL", "https://mail.cheffer.email").rstrip("/")
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


# ── Page miroir (« Voir la version en ligne ») ──────────────────────────────
CHEMIN_MIROIR = "/api/public/mass-mailing/vue"


def _signe_campagne(campaign_id: str) -> str:
    mac = hmac.new(_secret(), f"mm-vue:{campaign_id}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac[:12]).decode().rstrip("=")


def url_miroir(campaign_id: str) -> str:
    return f"{BASE_PUBLIQUE}{CHEMIN_MIROIR}?c={campaign_id}.{_signe_campagne(str(campaign_id))}"


def lire_jeton_miroir(c: str) -> str | None:
    try:
        cid, sig = (c or "").rsplit(".", 1)
    except ValueError:
        return None
    return cid if hmac.compare_digest(sig, _signe_campagne(cid)) else None


def pied_de_mail(html: str, recipient_id: int, expediteur_nom: str, *,
                 raison_sociale: str | None = None, adresse: str | None = None) -> str:
    """Ajoute le pied obligatoire juste avant </body> : identité de l'expéditeur, raison
    de la réception, adresse postale si connue, lien de désinscription personnel.

    `data-url-type="unsub"` : Sweego compte ce clic comme une désinscription et non
    comme un clic d'intérêt (doc : SKILL.md § 3)."""
    import html as _h
    import re as _re
    # Le lien « se désabonner » de la newsletter d'origine est souvent vide (« # ») : il
    # reçoit le lien de désinscription personnel, comme celui du pied.
    lien = _h.escape(url(recipient_id), quote=True)
    # Tout lien de désinscription de la newsletter (marqué à l'import) pointe vers NOTRE
    # désinscription : c'est elle qui alimente la liste de suppression.
    html = _re.sub(r'(?is)<a\b(?=[^>]*data-url-type=["\']unsub)[^>]*>',
                   lambda m: _re.sub(r'(?is)\bhref=(["\']).*?\1', f'href="{lien}"', m.group(0), count=1), html or "")
    from .harmonisation import a_desinscription
    if a_desinscription(html, marque_seulement=True):
        # La newsletter a déjà son pied (RGPD, expéditeur, se désinscrire) : pas de doublon.
        return html
    qui = _h.escape(raison_sociale or expediteur_nom)
    ligne_adresse = f"<br>{_h.escape(adresse)}" if adresse else ""
    pied = (
        '<div style="margin-top:32px;padding-top:12px;border-top:1px solid #e5e5e5;'
        'font-family:Arial,sans-serif;font-size:12px;line-height:1.5;color:#888;text-align:center">'
        f'Vous recevez ce message de la part de {qui}.'
        f'{ligne_adresse}<br>'
        f'<a href="{url(recipient_id)}" data-url-type="unsub" style="color:#888">'
        'Se désinscrire</a></div>'
    )
    bas = html.lower()
    i = bas.rfind("</body>")
    return html[:i] + pied + html[i:] if i >= 0 else html + pied


def texte_pied(recipient_id: int) -> str:
    return f"\n\n--\nSe désinscrire : {url(recipient_id)}\n"
