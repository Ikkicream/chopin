#!/usr/bin/env python3
"""mass_mailing/infra/images.py — héberger les images intégrées en base64 (13/10/2026).

Une image collée dans le HTML (« data:image/…;base64,… ») alourdit le mail, est bloquée par
Outlook et mal vue par les filtres. L'éditeur visuel en produit dès qu'on y glisse une image
de l'ordinateur. Ici : chaque image intégrée est déposée dans le stockage (adressée par son
empreinte : impossible à deviner, jamais réécrite) et remplacée par une URL https publique.
"""
from __future__ import annotations

import base64
import binascii
import re

from . import desinscription, stockage

TYPES = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
RE_DATA = re.compile(r"data:image/(png|jpe?g|gif|webp);base64,([A-Za-z0-9+/=\s]+)", re.I)
MAX_OCTETS = 5 * 1024 * 1024
CHEMIN = "/api/public/mass-mailing/img/"


def url(sha: str, genre: str) -> str:
    return f"{desinscription.BASE_PUBLIQUE}{CHEMIN}{sha}.{'jpg' if genre in ('jpeg', 'jpg') else genre}"


def heberger(html: str) -> tuple[str, int]:
    """(HTML avec des URL à la place des images intégrées, nombre d'images hébergées)."""
    n = 0

    def remplacer(m: re.Match) -> str:
        nonlocal n
        genre = m.group(1).lower()
        try:
            contenu = base64.b64decode(re.sub(r"\s+", "", m.group(2)), validate=True)
        except (binascii.Error, ValueError):
            return m.group(0)
        if not contenu or len(contenu) > MAX_OCTETS:
            return m.group(0)
        d = stockage.deposer(contenu, "img")
        n += 1
        return url(d["sha256"], genre)

    return RE_DATA.sub(remplacer, html or ""), n


def lire(nom: str) -> tuple[bytes, str] | None:
    m = re.fullmatch(r"([0-9a-f]{64})\.(png|jpg|jpeg|gif|webp)", nom or "")
    if not m:
        return None
    try:
        return stockage.lire(f"img/{m.group(1)[:2]}/{m.group(1)}.img"), TYPES[m.group(2)]
    except stockage.StockageErreur:
        return None


def reparer_corps(html: str) -> tuple[str, bool]:
    """Un seul </body> (13/10/2026 : l'éditeur visuel ajoutait ses styles APRÈS la fin du corps,
    d'où un second </body>). Les <style> égarés entre les deux sont retirés : l'en-tête d'origine
    porte déjà les styles du mail."""
    fins = [m.start() for m in re.finditer(r"(?i)</body\s*>", html or "")]
    if len(fins) < 2:
        return html, False
    premier = fins[0]
    fin_balise = html.index(">", premier) + 1
    entre = re.sub(r"(?is)<style\b[^>]*>.*?</style\s*>", "", html[fin_balise:fins[-1]])
    return html[:premier] + entre.strip() + html[fins[-1]:], True
