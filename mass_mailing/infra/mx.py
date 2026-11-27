#!/usr/bin/env python3
"""mass_mailing/infra/mx.py — le VRAI serveur de messagerie d'un domaine pro (21/10/2026).

Avant, tout domaine qui n'était pas un webmail grand public tombait dans « Autres (B2B) » : orpi.com
(206 contacts Zylio) était traité comme century21.fr ou foncia.fr. Or orpi.com est chez Google
Workspace (même filtre que Gmail), century21.fr chez Microsoft 365, foncia.fr derrière Proofpoint.
Chacun a ses propres règles et sa propre réputation : ce sont des files différentes.

    famille_de_mx(texte)      fonction PURE : enregistrements MX → famille
    resoudre(domaines)        résout les domaines inconnus (DNS, 16 en parallèle) et les met en cache
    charger()                 charge le cache en mémoire ; `famille(d)` le lit sans jamais toucher au réseau

Cache : table `mx_domaines` du schéma plateforme (partagée par tous les clients), revue après 30 jours.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import pg

GOOGLE_PRO = "google_pro"
MICROSOFT_PRO = "microsoft_pro"
PASSERELLE = "passerelle"
OVH = "ovh"
AUTRES = "autres"
FAMILLES = (GOOGLE_PRO, MICROSOFT_PRO, PASSERELLE, OVH)

_REGLES = [
    (re.compile(r"google\.com|googlemail\.com|smtp\.google", re.I), GOOGLE_PRO),
    (re.compile(r"\.outlook\.com|protection\.outlook|\.office365\.|mail\.protection", re.I), MICROSOFT_PRO),
    # Passerelles de sécurité : elles ouvrent et cliquent tout (antivirus), filtrent fort.
    (re.compile(r"pphosted|proofpoint|mimecast|barracuda|messagelabs|symantec|iphmx|ironport|trendmicro|"
                r"sophos|forcepoint|mailcontrol|altospam|mailinblack|vadesecure|vade\.|hornetsecurity|"
                r"spamexperts|cisco", re.I), PASSERELLE),
    (re.compile(r"ovh\.net|ovh\.com|mail\.ovh", re.I), OVH),
]

_CACHE: dict[str, str] = {}
_CHARGE_A = 0.0


def famille_de_mx(texte: str) -> str:
    """Fonction PURE : texte des MX (un par ligne, n'importe quel format) → famille."""
    for motif, fam in _REGLES:
        if motif.search(texte or ""):
            return fam
    return AUTRES


def famille(domaine: str) -> str | None:
    """Famille connue d'un domaine (cache mémoire uniquement), None si jamais résolu."""
    return _CACHE.get((domaine or "").lower().strip())


def appliquer_schema() -> None:
    with pg.espace(pg.SCHEMA):
        pg.ecrire("""CREATE TABLE IF NOT EXISTS mx_domaines (
                         domaine TEXT PRIMARY KEY,
                         famille TEXT NOT NULL,
                         mx      TEXT,
                         at      TIMESTAMPTZ NOT NULL DEFAULT now())""")


def charger(force: bool = False) -> int:
    """Charge le cache en mémoire (au plus une fois toutes les 10 minutes)."""
    global _CHARGE_A
    if not force and _CACHE and time.time() - _CHARGE_A < 600:
        return len(_CACHE)
    appliquer_schema()
    with pg.espace(pg.SCHEMA):
        _CACHE.update({x["domaine"]: x["famille"] for x in pg.lignes("SELECT domaine, famille FROM mx_domaines")})
    _CHARGE_A = time.time()
    return len(_CACHE)


def _mx(domaine: str) -> str | None:
    import dns.exception
    import dns.resolver
    try:
        rep = dns.resolver.resolve(domaine, "MX", lifetime=4)
        return " ".join(sorted(str(r.exchange).rstrip(".").lower() for r in rep))
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        return ""
    except dns.exception.DNSException:
        return None          # panne passagère : on réessaiera


def resoudre(domaines, limite: int = 1500) -> int:
    """Résout les domaines absents du cache (ou vus il y a plus de 30 jours). Renvoie le nombre résolu."""
    charger()
    with pg.espace(pg.SCHEMA):
        frais = {x["domaine"] for x in pg.lignes(
            "SELECT domaine FROM mx_domaines WHERE at > now() - interval '30 days' AND domaine = ANY(%(d)s)",
            {"d": list({(d or "").lower().strip() for d in domaines})})}
    a_faire = [d for d in {(d or "").lower().strip() for d in domaines} if d and d not in frais][:limite]
    if not a_faire:
        return 0
    with ThreadPoolExecutor(16) as ex:
        resultats = list(zip(a_faire, ex.map(_mx, a_faire)))
    n = 0
    with pg.espace(pg.SCHEMA):
        for d, mx in resultats:
            if mx is None:
                continue
            fam = famille_de_mx(mx)
            pg.ecrire("""INSERT INTO mx_domaines (domaine, famille, mx) VALUES (%(d)s, %(f)s, %(m)s)
                         ON CONFLICT (domaine) DO UPDATE SET famille = EXCLUDED.famille, mx = EXCLUDED.mx, at = now()""",
                      {"d": d, "f": fam, "m": mx[:300]})
            _CACHE[d] = fam
            n += 1
    return n
