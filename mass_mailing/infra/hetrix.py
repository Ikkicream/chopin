"""mass_mailing/infra/hetrix.py — surveillance HetrixTools de Mass Email (27/09/2026).

Doc : .claude/skills/hetrixtools/SKILL.md (+ doc/). Compte gratuit de Camille : 15 moniteurs
d'uptime, 32 moniteurs de listes noires, API v3 sans plafond mensuel mais **20 requêtes/min**
(et 3 à 10/min par endpoint), API v1/v2 (création / modification / suppression) 2 000 appels/mois.

- LECTURE (v3, `Authorization: Bearer`) : mise en CACHE dans le process de l'API (60 s pour la
  liste, 5 min pour le détail) — la clé ne va jamais dans le navigateur.
- ÉCRITURE (v2, clé dans l'URL) : ajout / modification / suppression de moniteurs (CRUD de l'écran
  « Surveillance »), avec un compteur mensuel local pour rester loin du quota.
- Sans clé (`HETRIXTOOLS_API_KEY` absent de .env) : tout renvoie `configure: False`, jamais d'erreur.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import requests

V3 = "https://api.hetrixtools.com/v3"
V2 = "https://api.hetrixtools.com/v2"
TTL_LISTE_S = 60
TTL_DETAIL_S = 300
QUOTA_V2_MOIS = 2000
# Emplacements de test (4 au plus en gratuit) : Europe, au plus près des destinataires.
EMPLACEMENTS = ("fra", "ams", "lon", "waw")

_cache: dict[str, tuple[float, object]] = {}
_verrou = threading.Lock()


def cle() -> str | None:
    k = os.environ.get("HETRIXTOOLS_API_KEY")
    if k:
        return k.strip()
    env = Path(__file__).resolve().parents[2] / ".env"
    try:
        for ligne in env.read_text().splitlines():
            if ligne.startswith("HETRIXTOOLS_API_KEY="):
                return ligne.split("=", 1)[1].strip() or None
    except OSError:
        pass
    return None


def configure() -> bool:
    return bool(cle())


class ErreurHetrix(Exception):
    pass


def _v3(chemin: str, params: dict | None = None) -> dict:
    r = requests.get(f"{V3}/{chemin.lstrip('/')}", headers={"Authorization": f"Bearer {cle()}"},
                     params=params or {}, timeout=20)
    if r.status_code == 429:
        raise ErreurHetrix("HetrixTools : trop de requêtes (limite 20/min), réessayez dans une minute")
    if r.status_code >= 400:
        raise ErreurHetrix(f"HetrixTools {r.status_code} : {(r.text or '')[:200]}")
    return r.json() if r.content else {}


def _en_cache(nom: str, ttl: float, charger):
    with _verrou:
        v = _cache.get(nom)
        if v and time.time() - v[0] < ttl:
            return v[1]
    donnees = charger()
    with _verrou:
        _cache[nom] = (time.time(), donnees)
    return donnees


def vider_cache() -> None:
    with _verrou:
        _cache.clear()


# ── Lecture ────────────────────────────────────────────────────────────────

def _tout(chemin: str) -> list[dict]:
    out, page = [], 1
    while True:
        d = _v3(chemin, {"per_page": 200, "page": page})
        lot = d.get("monitors") or d.get("data") or []
        out += lot
        pag = (d.get("meta") or {}).get("pagination") or {}
        if not lot or page >= int(pag.get("last") or 1):
            return out
        page += 1


def resume() -> dict:
    """Tous les moniteurs (uptime + listes noires), normalisés pour les badges et le tableau."""
    if not configure():
        return {"configure": False}

    def charger():
        uptime = [_uptime(m) for m in _tout("uptime-monitors")]
        blacklist = [_blacklist(m) for m in _tout("blacklist-monitors")]
        return {"configure": True, "uptime": uptime, "blacklist": blacklist, "lu_a": int(time.time())}
    return _en_cache("resume", TTL_LISTE_S, charger)


def _uptime(m: dict) -> dict:
    locs = m.get("locations") or {}
    if isinstance(locs, list):
        locs = {str(i): x for i, x in enumerate(locs)}
    temps = [x.get("response_time") for x in locs.values() if isinstance(x, dict) and x.get("response_time") is not None]
    return {
        "id": m.get("id"), "nom": m.get("name"), "type": m.get("type"), "cible": m.get("target"),
        "etat": m.get("uptime_status"),                  # up / down / unknown
        "statut": m.get("monitor_status"),               # active / paused / maint…
        "uptime": _float(m.get("uptime")),
        "depuis": m.get("last_status_change"), "dernier_test": m.get("last_check"),
        "mot_cle": m.get("keyword"), "frequence": m.get("check_frequency") or m.get("frequency"),
        "temps_reponse_ms": round(sum(temps) / len(temps)) if temps else None,
        "emplacements": {k: {"etat": (v or {}).get("uptime_status"), "temps_ms": (v or {}).get("response_time"),
                             "dernier_test": (v or {}).get("last_check")}
                         for k, v in locs.items() if isinstance(v, dict)},
    }


def _blacklist(m: dict) -> dict:
    listes = m.get("listed") or []
    return {
        "id": m.get("id") or m.get("target"), "nom": m.get("name") or m.get("label") or m.get("target"), "cible": m.get("target"),
        "type": m.get("type"), "listee": bool(listes),
        # Une entrée en texte brut est une liste à part entière (revue du 30/09 : l'ignorer pouvait faire passer
        # « Spamhaus + UCEPROTECT 3 » pour une simple alerte réseau).
        "listes": [{"rbl": x.get("rbl"), "retrait": x.get("delist")} if isinstance(x, dict) else {"rbl": str(x), "retrait": None}
                   for x in listes],
        "dernier_test": m.get("last_check"),
    }


# IP d'envoi Sweego vue sur 100 % des envois (webhook « delivered », 27/09) : filet si aucun
# moniteur de liste noire n'est libellé « … IP envoi ».
IPS_ENVOI_DEFAUT = ("185.255.28.17",)


# Listes qui inscrivent un RÉSEAU ENTIER (voisins, hébergeur, ASN), pas notre IP : UCEPROTECT niveau 2
# (plage) et 3 (tout l'ASN de l'hébergeur de Sweego), retrait payant, ignorées par Gmail, Microsoft,
# Orange, etc. Seules, elles valent un AVERTISSEMENT, pas un blocage (30/09 : le niveau 3 avait
# suspendu le routage d'Omoda). Toute autre liste reste bloquante.
LISTES_RESEAU = ("dnsbl-2.uceprotect.net", "dnsbl-3.uceprotect.net")


def etat_moniteur(m: dict | None) -> str:
    """propre | listee | reseau (listé seulement sur des listes de réseau entier) | non_surveille."""
    if not m:
        return "non_surveille"
    if not m.get("listee"):
        return "propre"
    rbl = [str(x.get("rbl") or "").strip().lower().rstrip(".") for x in m.get("listes") or []]
    return "reseau" if rbl and all(r in LISTES_RESEAU for r in rbl) else "listee"


def reputation_envoi(domaines: list[str]) -> dict:
    """Avant chaque campagne (Camille, 27/09) : l'IP d'envoi Sweego et le(s) domaine(s) d'envoi
    sont-ils absents des listes noires ? Lu dans les moniteurs HetrixTools (cache 60 s).

    Renvoie {verifie, ok, elements:[{cible, role, etat: propre|listee|non_surveille, listes}]}.
    `verifie` faux si HetrixTools est absent ou injoignable (le contrôle devient un avertissement)."""
    try:
        r = resume()
    except ErreurHetrix as e:
        return {"verifie": False, "ok": None, "raison": str(e), "elements": []}
    if not r.get("configure"):
        return {"verifie": False, "ok": None, "raison": "HetrixTools non configuré", "elements": []}
    moniteurs = {m["cible"]: m for m in r.get("blacklist") or []}
    # Espace client (Resend/SES) : ses domaines seulement. Les IP d'envoi sont celles du
    # fournisseur, partagées et non surveillables ici — l'IP Sweego ne le concerne pas.
    from . import fournisseurs
    if fournisseurs.nom() == "sweego":
        ips = [m["cible"] for m in r.get("blacklist") or []
               if "envoi" in (m.get("nom") or "").lower() and m.get("type") == "ipv4" and _tag(m) is None] or list(IPS_ENVOI_DEFAUT)
        cibles = [(ip, "IP d'envoi Sweego") for ip in ips] + [(d, "Domaine d'envoi") for d in domaines]
    else:
        cibles = [(d, "Domaine d'envoi") for d in domaines] + \
                 [(o, "Domaine organisationnel") for o in sorted({".".join(d.split(".")[-2:]) for d in domaines} - set(domaines))]
    elements = []
    for cible, role in cibles:
        m = moniteurs.get(cible)
        etat = etat_moniteur(m)
        elements.append({"cible": cible, "role": role, "etat": etat, "listes": (m or {}).get("listes") or [],
                         "dernier_test": (m or {}).get("dernier_test")})
    listees = [e for e in elements if e["etat"] == "listee"]
    non_surv = [e for e in elements if e["etat"] == "non_surveille"]
    reseau = [e for e in elements if e["etat"] == "reseau"]
    raisons = ([("non surveillé par HetrixTools : " + ", ".join(e["cible"] for e in non_surv))] if non_surv else []) \
        + ([("listé seulement sur une liste de réseau entier (UCEPROTECT 2/3, non bloquant) : "
             + ", ".join(e["cible"] for e in reseau))] if reseau else [])
    return {"verifie": not non_surv, "ok": not listees and not non_surv, "elements": elements,
            "avertissement": bool(reseau), "raison": " ; ".join(raisons) or None}


def _float(v):
    try:
        return round(float(v), 3)
    except (TypeError, ValueError):
        return None


def detail_uptime(monitor_id: str) -> dict:
    """Carte de détail : uptime par jour (30 j) et derniers incidents."""
    if not configure():
        return {"configure": False}

    def charger():
        rapport, pannes = {}, {}
        try:
            rapport = _v3(f"uptime-monitors/{monitor_id}/report", {"days": 30})
        except ErreurHetrix as e:
            rapport = {"erreur": str(e)}
        try:
            pannes = _v3(f"uptime-monitors/{monitor_id}/downtimes", {"per_page": 5})
        except ErreurHetrix as e:
            pannes = {"erreur": str(e)}
        return {"configure": True, "rapport": rapport, "pannes": pannes}
    return _en_cache(f"detail:{monitor_id}", TTL_DETAIL_S, charger)


# ── Écriture (v2) : CRUD de l'écran Surveillance ────────────────────────────

def contact_defaut() -> str:
    """Liste de contacts par défaut du compte (alertes à l'email de Camille). Obligatoire pour
    les moniteurs de listes noires (« invalid contact list » sinon) ; sans elle, pas d'alerte."""
    def charger():
        for c in _v3("contact-lists").get("contact_lists") or []:
            if c.get("default"):
                return c.get("id") or ""
        return ""
    return _en_cache("contact_defaut", 3600, charger)


def _compteur_v2() -> int:
    from infra import pg
    mois = time.strftime("%Y-%m")
    return int(pg.valeur("""INSERT INTO hetrix_quota (mois, appels) VALUES (%(m)s, 1)
                            ON CONFLICT (mois) DO UPDATE SET appels = hetrix_quota.appels + 1
                            RETURNING appels""", {"m": mois}) or 0)


def _v2(chemin: str, json_body: dict | None = None, data: dict | None = None) -> dict:
    if not configure():
        raise ErreurHetrix("HetrixTools non configuré (HETRIXTOOLS_API_KEY absent)")
    if _compteur_v2() > QUOTA_V2_MOIS * 0.9:
        raise ErreurHetrix("quota mensuel d'appels HetrixTools v2 presque atteint : création/modification suspendues")
    r = requests.post(f"{V2}/{cle()}/{chemin.strip('/')}/", json=json_body, data=data, timeout=30)
    try:
        d = r.json()
    except ValueError:
        raise ErreurHetrix(f"HetrixTools {r.status_code} : réponse illisible")
    if r.status_code >= 400 or str(d.get("status", "")).upper() == "ERROR":
        raise ErreurHetrix(f"HetrixTools : {d.get('error_message') or d.get('message') or d}")
    vider_cache()
    return d


def corps_site(nom: str, url: str, mot_cle: str = "", codes: str = "200", mid: str = "") -> dict:
    return {"MID": mid, "Type": 1, "Name": nom, "Target": url, "Timeout": 10, "Frequency": 1,
            "FailsBeforeAlert": 3, "FailedLocations": "", "ContactList": contact_defaut(), "Category": "Mass Email",
            "AlertAfter": "", "RepeatTimes": "", "RepeatEvery": "", "Public": False, "ShowTarget": False,
            "VerSSLCert": True, "VerSSLHost": True,
            "Locations": {k: (k in EMPLACEMENTS) for k in ("nyc", "sfo", "dal", "ams", "lon", "fra", "sgp", "syd", "sao", "tok", "mba", "waw")},
            "Method": "GET", "Keyword": mot_cle[:128], "HTTPCodes": codes, "MaxRedirects": "5",
            "SSLExpiryReminder": "15", "DomainExpiryReminder": "30", "NSChangeAlert": "0"}


def ajouter_site(nom: str, url: str, mot_cle: str = "", codes: str = "200") -> dict:
    return _v2("uptime/add", json_body=corps_site(nom, url, mot_cle, codes))


def modifier_site(mid: str, nom: str, url: str, mot_cle: str = "", codes: str = "200") -> dict:
    # ⚠️ « uptime/add » avec MID CRÉE UN DOUBLON (constaté le 27/09, 7 doublons à supprimer) :
    # la modification passe par « uptime/edit », jamais par l'ajout.
    return _v2("uptime/edit", json_body=corps_site(nom, url, mot_cle, codes, mid))


def supprimer_uptime(mid: str) -> dict:
    return _v2("uptime/delete", json_body={"MID": mid})


def ajouter_blacklist(cible: str, libelle: str = "") -> dict:
    return _v2("blacklist/add", data={"target": cible, "label": libelle, "contact": contact_defaut()})


def supprimer_blacklist(cible: str) -> dict:
    return _v2("blacklist/delete", data={"target": cible})


# ── Multi-clients (SaaS, 13/10/2026) ─────────────────────────────────────────
# Convention de nommage, seule façon de rattacher un moniteur à un espace (HetrixTools n'a
# pas d'étiquette exploitable en lecture, et n'accepte que [A-Za-z0-9 .-] dans les noms) :
#   « Client <slug> - … »       → moniteur d'un client (ses domaines, sa page de désinscription) ;
#   « Fournisseur <nom> - … »   → infrastructure partagée par les clients d'un fournisseur (webhook) ;
#   autre                       → infrastructure interne (Sweego, domaines LeClientRoi).
def _tag(m: dict) -> str | None:
    nom = (m.get("nom") or "").strip()
    for prefixe in ("Client ", "Fournisseur "):
        if nom.startswith(prefixe) and " - " in nom:
            return nom[len(prefixe):nom.index(" - ")].strip().lower()
    return None


def nom_client(slug: str, quoi: str) -> str:
    return f"Client {slug} - {quoi}"


# Services de la PLATEFORME, communs à tous les espaces (même serveur, même worker) : un
# client les voit aussi — c'est sa disponibilité autant que la nôtre. Les éléments propres à
# Sweego (webhook Sweego, IP Sweego) et la désinscription interne restent hors des espaces clients.
PLATEFORME_PARTAGEE = ("Mass Email - API et base", "Mass Email - Interface", "Mass Email - Worker",
                       "Mass Email - Preferences", "Mass Email - Version en ligne")


def resume_espace(slug: str | None, fournisseur: str = "sweego") -> dict:
    """Le résumé filtré pour UN espace : un client ne voit jamais l'infrastructure interne,
    l'espace interne ne voit pas les moniteurs des clients."""
    r = resume()
    if not r.get("configure"):
        return r
    if slug:
        garder = lambda m: _tag(m) in (slug, fournisseur) or (m.get("nom") or "") in PLATEFORME_PARTAGEE  # noqa: E731
    else:
        garder = lambda m: _tag(m) is None  # noqa: E731
    return {**r, "uptime": [m for m in r["uptime"] if garder(m)],
            "blacklist": [m for m in r["blacklist"] if garder(m)], "espace": slug or "interne"}


# API du fournisseur, joignable sans clé (200 sur la racine) : si elle tombe, plus aucun envoi.
API_FOURNISSEURS = {"resend": "https://api.resend.com/"}


def assurer_surveillance_client(slug: str, domaines: list[str], url_desinscription: str,
                                fournisseur: str = "resend", url_webhook: str = "") -> dict:
    """Crée ce qui manque pour un client (idempotent : rien n'est créé deux fois).
    Listes noires : chaque domaine d'envoi + son domaine organisationnel. Disponibilité : sa
    page de désinscription (lien signé de son espace) ; webhook du fournisseur, une fois pour tous."""
    r = resume()
    if not r.get("configure"):
        return {"ok": False, "raison": "HetrixTools non configuré"}
    cibles_bl = {m["cible"] for m in r["blacklist"]}
    noms_up = {m["nom"] for m in r["uptime"]}
    faits, deja = [], []
    a_surveiller = []
    for d in domaines:
        a_surveiller.append((d, nom_client(slug, "Domaine envoi")))
        org = ".".join(d.split(".")[-2:])
        if org != d:
            a_surveiller.append((org, nom_client(slug, "Domaine organisationnel")))
    for cible, libelle in a_surveiller:
        if cible in cibles_bl:
            deja.append(cible); continue
        ajouter_blacklist(cible, libelle); cibles_bl.add(cible); faits.append(f"liste noire {cible}")
    nom = nom_client(slug, "Desinscription")
    if nom in noms_up:
        deja.append(nom)
    else:
        ajouter_site(nom, url_desinscription, "", "200"); faits.append(f"disponibilité {nom}")
    if url_webhook:
        nw = f"Fournisseur {fournisseur} - Webhook {fournisseur.capitalize()}"
        if nw in noms_up:
            deja.append(nw)
        else:
            ajouter_site(nw, url_webhook, "", "200"); faits.append(f"disponibilité {nw}")
    api = API_FOURNISSEURS.get(fournisseur)
    if api:
        na = f"Fournisseur {fournisseur} - API {fournisseur.capitalize()}"
        if na in noms_up:
            deja.append(na)
        else:
            ajouter_site(na, api, "", "200"); faits.append(f"disponibilité {na}")
    vider_cache()
    return {"ok": True, "crees": faits, "deja": deja}


def etat_surveillance_client(slug: str, domaines: list[str], fournisseur: str = "resend") -> dict:
    r = resume_espace(slug, fournisseur)
    if not r.get("configure"):
        return {"configure": False, "complet": False}
    cibles = {m["cible"] for m in r["blacklist"]}
    attendus = set(domaines) | {".".join(d.split(".")[-2:]) for d in domaines}
    up = {m["nom"] for m in r["uptime"]}
    manque = sorted(attendus - cibles) + ([] if nom_client(slug, "Desinscription") in up else ["désinscription"])
    return {"configure": True, "complet": not manque, "manque": manque,
            "listes_noires": len(r["blacklist"]), "disponibilite": len(r["uptime"])}
