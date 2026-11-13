#!/usr/bin/env python3
"""mass_mailing/infra/ouvertures.py — qui a VRAIMENT ouvert : humain, Apple Mail ou machine (20/10/2026).

Constat sur Zylio (138 ouvertures, Resend) : 86 viennent de machines — antivirus Microsoft 365
(IP Microsoft, Chrome 109), scanner Google (74.125.x, faux « Edge 12 » de 2015), passerelles sur
Amazon, Proofpoint… — qui ouvrent le mail quelques secondes après la livraison. 28 viennent du
préchargement d'Apple Mail (« Mozilla/5.0 » seul, via Cloudflare / Fastly / Akamai) : automatique,
on ne sait pas si quelqu'un a lu. 24 seulement sont sûres : box ou réseau d'entreprise français,
Outlook bureau (« ms-office »), proxy d'images Gmail (« ggpht »).

Chaque événement d'ouverture Resend porte l'IP et le logiciel. L'organisation de l'IP vient du
registre public (whois), mise en cache dans `ip_organisations` (une recherche par IP, jamais refaite).
"""
from __future__ import annotations

import re
import subprocess

from . import pg

HUMAIN = "humain"
APPLE = "apple"
MACHINE = "machine"

# Accès internet de particuliers ou d'entreprises (France surtout) : derrière, une personne.
_FAI = re.compile(r"orange|wanadoo|free sas|proxad|\bsfr\b|sfr-|ip2000|bouyg|sewan|blue sas|bretagne|hexanet|"
                  r"korrigan|openip|btbroadband|unyc|zscaler|numericable|completel|nordnet|k-net|coriolis|"
                  r"swisscom|proximus|telenet|vodafone|telefonica|deutsche telekom|xs4all|ziggo", re.I)
# Relais du préchargement d'Apple Mail (Mail Privacy Protection).
_RELAIS_APPLE = re.compile(r"cloudflarewarp|cloudflare|fastly|skyca|akamai|apple", re.I)


def appliquer_schema() -> None:
    with pg.espace(pg.SCHEMA):
        pg.ecrire("""CREATE TABLE IF NOT EXISTS ip_organisations (
                         ip   TEXT PRIMARY KEY,
                         org  TEXT NOT NULL,
                         at   TIMESTAMPTZ NOT NULL DEFAULT now())""")


def _whois(ip: str) -> str:
    try:
        sortie = subprocess.run(["whois", ip], capture_output=True, text=True, timeout=20).stdout
    except (subprocess.SubprocessError, OSError):
        return ""
    champs = [l.split(":", 1)[1].strip() for l in sortie.splitlines()
              if re.match(r"(?i)^(OrgName|org-name|netname|descr|Organization)\s*:", l)]
    org = " ".join(champs[:2])
    if org.upper().startswith("RIPE"):          # renvoi ARIN → RIPE : on interroge RIPE directement
        try:
            s2 = subprocess.run(["whois", "-h", "whois.ripe.net", ip], capture_output=True, text=True, timeout=20).stdout
            org = " ".join(l.split(":", 1)[1].strip() for l in s2.splitlines()
                           if re.match(r"(?i)^(netname|descr|org-name)\s*:", l))[:200] or org
        except (subprocess.SubprocessError, OSError):
            pass
    return org[:200]


def organisation(ip: str) -> str:
    """Organisation propriétaire de l'IP (cache en base, whois au premier passage)."""
    if not ip:
        return ""
    with pg.espace(pg.SCHEMA):
        o = pg.valeur("SELECT org FROM ip_organisations WHERE ip = %(i)s", {"i": ip})
    if o is not None:
        return o
    o = _whois(ip)
    if o:
        with pg.espace(pg.SCHEMA):
            pg.ecrire("INSERT INTO ip_organisations (ip, org) VALUES (%(i)s, %(o)s) ON CONFLICT (ip) DO NOTHING",
                      {"i": ip, "o": o})
    return o


DELAI_MACHINE = 60   # secondes après la livraison : en deçà, une « box » est une passerelle d'entreprise


def classer(org: str, ua: str, secondes: float | None = None) -> tuple[str, str]:
    """Fonction PURE : (verdict, source) d'UN événement d'ouverture. `secondes` = délai depuis la
    livraison (22/10/2026) : une ouverture « box ou réseau d'entreprise » 17 s après la livraison était
    la passerelle de sécurité de l'agence sortant par sa connexion internet, pas une lectrice."""
    ua = ua or ""
    rapide = secondes is not None and secondes < DELAI_MACHINE
    if "ggpht" in ua or "GoogleImageProxy" in ua:
        return HUMAIN, "Gmail (proxy d’images)"
    if "ms-office" in ua or "Microsoft Outlook" in ua:
        return HUMAIN, "Outlook bureau"
    if org and _FAI.search(org):
        if rapide:
            return MACHINE, f"passerelle d’entreprise ({int(secondes)} s après la livraison)"
        return HUMAIN, "box ou réseau d’entreprise"
    if ua.strip() == "Mozilla/5.0" and (not org or _RELAIS_APPLE.search(org)):
        return APPLE, "Apple Mail (préchargement)"
    return MACHINE, (org.split()[0] if org else "inconnu")


def verdict_destinataire(verdicts: list[str]) -> str:
    """Fonction PURE : un destinataire est « humain » si UNE de ses ouvertures l'est."""
    return HUMAIN if HUMAIN in verdicts else APPLE if APPLE in verdicts else MACHINE
