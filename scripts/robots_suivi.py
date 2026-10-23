#!/usr/bin/env python3
"""scripts/robots_suivi.py — une ouverture ou un clic Cheffer : une personne ou un robot ? (21/10/2026)

Jusqu'ici le pixel et la redirection de clic de Cheffer ne gardaient que l'HEURE. Impossible de
séparer un lecteur d'un antivirus : le tableau de bord affichait 53 % d'ouvertures et 14 % de clics,
alors que 47 des 58 « cliqueurs » de la semaine avaient cliqué moins d'une minute après l'envoi. Et
chaque clic, robot compris, faisait passer le contact en lead (« prm ») dans le CRM.

Chaque événement porte désormais l'IP réelle (Nginx, derrière Cloudflare), le logiciel, et le délai
depuis l'envoi à ce contact. Le verdict réutilise le classifieur de Mass Email (mass_mailing/infra/
ouvertures.py : propriétaire de l'IP par whois, mis en cache dans mass_mailing.ip_organisations) :

    OUVERTURE  humain  : proxy d'images Gmail (« GoogleImageProxy », chargé quand la PERSONNE ouvre),
                         Outlook bureau, box ou réseau d'entreprise
               apple   : préchargement Apple Mail (on ne sait pas si c'est lu)
               robot   : IP Google sans le proxy (scanner de sécurité Gmail, « Chrome/42 »),
                         antivirus et passerelles (Microsoft, Proofpoint…), ou < 60 s sans autre preuve
    CLIC       robot   : IP de centre de données, ou < 60 s après l'envoi
               humain  : sinon (box, réseau d'entreprise, mobile…)
               incertain : ni IP ni délai connus

    classer(kind, ip, ua, secondes, org) — fonction PURE, testée (tests/test_robots_suivi.py)
    evaluer(kind, email, ip, ua)        — résout l'organisation et le délai, rend le meta à journaliser
"""
from __future__ import annotations

import ipaddress
import re
import sys
from pathlib import Path

HUMAIN, APPLE, ROBOT, INCERTAIN = "humain", "apple", "robot", "incertain"
DELAI_ROBOT = 60      # secondes : en deçà, c'est un scanner (Mass Email L1/L3, guide § 7)

_PROXY_GMAIL = re.compile(r"GoogleImageProxy|ggpht", re.I)
_OUTLOOK = re.compile(r"ms-office|Microsoft Outlook", re.I)
_FAI = re.compile(r"orange|wanadoo|free sas|proxad|\bsfr\b|sfr-|ip2000|bouyg|sewan|blue sas|bretagne|hexanet|"
                  r"korrigan|openip|btbroadband|unyc|numericable|completel|nordnet|k-net|coriolis|"
                  r"swisscom|proximus|telenet|vodafone|telefonica|deutsche telekom|xs4all|ziggo|"
                  r"free mobile|bouygues telecom|lycamobile|prixtel", re.I)
_RELAIS_APPLE = re.compile(r"cloudflarewarp|cloudflare|fastly|skyca|akamai|apple", re.I)
# Passerelles et antivirus de messagerie : leurs IP ne portent JAMAIS une personne.
_PASSERELLES = re.compile(r"proofpoint|mimecast|barracuda|cisco|ironport|forcepoint|trend ?micro|sophos|symantec|"
                          r"broadcom|fortinet|vade|mailcontrol|zscaler-scan", re.I)
# Hébergeurs : un robot le plus souvent, mais une personne peut y passer (Outlook web via Microsoft,
# iCloud Private Relay via Cloudflare/Akamai/Fastly) — on ne tranche que s'il y a une autre preuve.
_HEBERGEURS = re.compile(r"microsoft|msft|azure|google|amazon|aws|digitalocean|hetzner|linode|akamai|cloudflare|"
                         r"fastly|scaleway|online s\.a\.s|netcup|ionos|contabo|leaseweb|oracle|"
                         r"\bcloud\b|hosting|datacent|\bserver|\bvps\b|colo|cie-us", re.I)
RAFALE_S = 30         # 3 liens différents en 30 s : un antivirus qui visite tout (22/10 : 10 « humains » de ce type)
# Logiciels automatiques (revue du 21/10, n°5) : un vrai clic vient d'un navigateur.
_UA_ROBOT = re.compile(r"bot\b|crawl|spider|curl|wget|python|java/|go-http|okhttp|headless|scan|preview|"
                       r"facebookexternalhit|slack|whatsapp|discord|axios|node-fetch", re.I)
# Signature du scanner de sécurité Gmail : faux « Edge 12 / Chrome 42 » de 2015 (Mass Email, leçon L1).
_SCANNER_GMAIL = re.compile(r"Chrome/42\.|Edge/12\.", re.I)
_SAFARI_IOS = re.compile(r"iPhone|iPad|Macintosh.*Safari", re.I)


def classer(kind: str, ip: str, ua: str, secondes: float | None, org: str) -> tuple[str, str]:
    """Fonction PURE : (verdict, raison) d'UN événement 'open' ou 'click'."""
    ua, org = ua or "", org or ""
    rapide = secondes is not None and secondes < DELAI_ROBOT
    if ua and _UA_ROBOT.search(ua):
        return ROBOT, "logiciel automatique (" + _UA_ROBOT.search(ua).group(0) + ")"
    if org and _PASSERELLES.search(org):
        return ROBOT, f"IP de {org.split()[0]} (passerelle ou antivirus de messagerie)"
    if kind == "open":
        if _PROXY_GMAIL.search(ua):
            # La signature se copie : elle ne vaut que si l'IP est bien celle de Google (essai du 21/10 :
            # la même signature envoyée depuis un serveur Hetzner était crue).
            if not org or re.search(r"google", org, re.I):
                return HUMAIN, "Gmail : images chargées à l'ouverture par la personne"
            return ROBOT, f"fausse signature Gmail depuis {org.split()[0]}"
        if _OUTLOOK.search(ua):
            return HUMAIN, "Outlook sur ordinateur"
        if ua.strip() == "Mozilla/5.0" and (not org or _RELAIS_APPLE.search(org)):
            return APPLE, "préchargement Apple Mail"
        if _SCANNER_GMAIL.search(ua) and re.search(r"google", org, re.I):
            return ROBOT, "scanner de sécurité Gmail"
        if rapide:
            return ROBOT, f"ouvert {int(secondes)} s après l'envoi"
        if org and _HEBERGEURS.search(org):
            return INCERTAIN, f"IP de {org.split()[0]}, ouverture tardive"
        if org and _FAI.search(org):
            return HUMAIN, "box ou réseau d'entreprise"
        if not ip and secondes is None:
            return INCERTAIN, "ni IP ni délai connus"
        return (HUMAIN, "réseau " + org.split()[0]) if org else (INCERTAIN, "organisation inconnue")
    # clic
    if rapide:
        return ROBOT, f"cliqué {int(secondes)} s après l'envoi"
    if org and _HEBERGEURS.search(org):
        if _RELAIS_APPLE.search(org) and _SAFARI_IOS.search(ua):
            return INCERTAIN, "relais privé iCloud possible"
        return ROBOT, f"IP de {org.split()[0]} (hébergeur, pas un navigateur de bureau)"
    if not ip and secondes is None:
        return INCERTAIN, "ni IP ni délai connus"
    return HUMAIN, ("réseau " + org.split()[0]) if org else "clic tardif, réseau non identifié"


def _organisation(ip: str) -> str:
    """Propriétaire de l'IP : cache whois partagé avec Mass Email (une recherche par IP, jamais refaite).
    Import par le paquet `mass_mailing` (déjà utilisé par l'API) : pas de second `infra.pg` ni de
    second pool de connexions (revue n°9)."""
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return ""
    try:
        racine = str(Path(__file__).resolve().parent.parent)
        if racine not in sys.path:
            sys.path.append(racine)
        from mass_mailing.infra import ouvertures
        return ouvertures.organisation(ip) or ""
    except Exception as e:  # noqa: BLE001
        print(f"[robots_suivi] organisation({ip}) : {type(e).__name__}: {e}", flush=True)
        return ""


def _secondes_depuis_envoi(email: str) -> float | None:
    try:
        import pool_pg
        r = pool_pg._q("""SELECT EXTRACT(EPOCH FROM (now() - max(occurred_at))) FROM email_events
                           WHERE email = %(e)s AND event_type = 'sent'""", {"e": (email or "").strip().lower()})
        return float(r[0][0]) if r and r[0] and r[0][0] is not None else None
    except Exception:  # noqa: BLE001
        return None


def _rafale(email: str, url: str) -> int:
    """Nombre de liens DIFFÉRENTS (celui-ci compris) cliqués par ce contact dans les RAFALE_S dernières secondes.
    Si c'est une rafale, les clics précédents de la rafale sont reclassés robot eux aussi."""
    try:
        import pool_pg
        r = pool_pg._q("""SELECT count(DISTINCT COALESCE(meta->>'url', url, '')) FROM email_events
                           WHERE email = %(e)s AND event_type = 'click'
                             AND occurred_at > now() - make_interval(secs => %(s)s)
                             AND COALESCE(meta->>'url', url, '') <> %(u)s""",
                       {"e": (email or "").strip().lower(), "s": RAFALE_S, "u": url or ""})
        n = int(r[0][0] or 0) + 1
        if n >= 3:
            pool_pg._ecrire("""UPDATE email_events
                                  SET meta = meta || '{"verdict": "robot", "proxy": true, "raison": "rafale de liens (antivirus)"}'::jsonb
                                WHERE email = %(e)s AND event_type = 'click'
                                  AND occurred_at > now() - make_interval(secs => %(s)s)""",
                            {"e": (email or "").strip().lower(), "s": RAFALE_S})
        return n
    except Exception:  # noqa: BLE001
        return 1


def evaluer(kind: str, email: str, ip: str, ua: str, url: str = "") -> dict:
    """Le meta à journaliser avec l'événement : ip, logiciel, délai, organisation, verdict, raison."""
    org = _organisation(ip)
    secondes = _secondes_depuis_envoi(email)
    verdict, raison = classer(kind, ip, ua, secondes, org)
    if kind == "click" and verdict != ROBOT and _rafale(email, url) >= 3:
        verdict, raison = ROBOT, f"rafale : 3 liens ou plus en {RAFALE_S} s (antivirus)"
    return {"ip": ip or None, "ua": (ua or "")[:300] or None, "org": org[:120] or None,
            "secondes_depuis_envoi": int(secondes) if secondes is not None else None,
            "verdict": verdict, "raison": raison,
            # Convention déjà lue par Mozart, l'affinité expéditeur et le webhook Sweego : un
            # événement « proxy » n'est pas un geste de la personne (revue n°2).
            "proxy": verdict in (ROBOT, APPLE)}


# ── RGPD : l'IP et le logiciel ne servent qu'au verdict (revue du 21/10, n°7) ──
CONSERVATION_IP_JOURS = 30


def purger_ip(jours: int = CONSERVATION_IP_JOURS) -> int:
    """Retire l'IP et le logiciel des ouvertures et clics de plus de `jours` jours. Le verdict, la
    raison et l'organisation restent (statistiques). Lancé chaque nuit (cron 03:40)."""
    import pool_pg
    return pool_pg._ecrire("""UPDATE email_events SET meta = meta - 'ip' - 'ua'
                               WHERE event_type IN ('open', 'click')
                                 AND occurred_at < now() - make_interval(days => %(j)s)
                                 AND (meta ? 'ip' OR meta ? 'ua')""", {"j": jours}) or 0


if __name__ == "__main__" and sys.argv[1:2] == ["purger-ip"]:
    print(f"[robots_suivi] IP et logiciel retirés de {purger_ip()} événement(s) de plus de {CONSERVATION_IP_JOURS} jours")
