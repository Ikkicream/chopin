#!/usr/bin/env python3
"""Connecteur Onoff Business — téléphonie professionnelle.

CE QUE L'API SAIT FAIRE, ET CE QU'ELLE NE SAIT PAS
--------------------------------------------------
Vérifié le 2026-08-24 sur la documentation officielle (navigation complète de
docs.onoffbusiness.com) et sur la page produit :

  ✅ lire les journaux d'appels        GET /api/v1/calls
  ✅ lire un appel                     GET /api/v1/calls/{id}
  ✅ récupérer un enregistrement       GET /api/v1/calls/{id}/recording
  ✅ récupérer une messagerie vocale   GET /api/v1/calls/{id}/voicemail
  ✅ lire les SMS et leurs fils        GET /api/v1/messages, /api/v1/messages/thread
  ✅ membres, numéros, départements, contacts (CRUD), statistiques

  ❌ PASSER un appel — aucun endpoint. Onoff passe par son extension Chrome
     « Click2Call » ou par l'application. C'est pourquoi le bouton d'appel de Cheffer
     délègue au système via `tel:` plutôt que de prétendre composer lui-même.
  ❌ ENVOYER un SMS — annoncé « à venir » sur la page produit officielle : « SMS
     management: send messages directly via the API (listing is already live) ».
     `envoyer_sms()` tente quand même l'appel : le jour où Onoff l'ouvre, il marchera
     sans qu'on touche à quoi que ce soit, et d'ici là il rend un refus explicite.
  ❌ CRÉDIT / SOLDE — aucun endpoint, nulle part. La page affiche donc la consommation
     (appels, minutes, SMS) et dit clairement que le solde n'est pas exposé.

L'API entière demande le plan **Max**. Le webhook, lui, fonctionne indépendamment : c'est
la source PRIMAIRE des journaux ici, l'API n'étant qu'un enrichissement. Un abonnement qui
change ne doit pas faire disparaître une messagerie non lue de l'écran.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA = Path(__file__).resolve().parent / "onoff_schema.sql"

BASE_URL = "https://public-apigateway.onoffapp.net"

# Même leçon que les connecteurs du tableau de bord (2026-08-24) : un délai trop court
# fabrique de fausses pannes. 8 s, et une seconde chance sur incident réseau uniquement.
DELAI_S = 8.0
ESSAIS = 2

# Statuts d'appel renvoyés par Onoff.
STATUT_MESSAGERIE = "VMS"
TYPES = ("CDR", "VM", "RECORDING", "SMS")


# ── Configuration ────────────────────────────────────────────────────────────

def _env() -> dict[str, str]:
    """Relit .env à chaque appel : une clé saisie dans l'écran doit valoir immédiatement,
    sans redémarrage de l'API."""
    out: dict[str, str] = {}
    p = BASE_DIR / ".env"
    if not p.exists():
        return out
    for ligne in p.read_text().splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        k, v = ligne.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def cle(site: str) -> str:
    """Clé du site, avec repli sur une clé globale. Un compte Onoff peut couvrir les deux
    marques : imposer une clé par site obligerait à la saisir deux fois."""
    e = _env()
    return e.get(f"ONOFF_API_KEY_{site.upper()}", "") or e.get("ONOFF_API_KEY", "")


def configure(site: str) -> bool:
    return bool(cle(site))


def jeton_webhook() -> str:
    """Le jeton attendu dans l'URL du webhook (`?token=…`), déjà utilisé par les autres
    intégrations. On ne réinvente pas un second mécanisme."""
    e = _env()
    return e.get("WEBHOOK_TOKEN_1", "") or e.get("WEBHOOK_TOKEN_2", "")


def url_webhook(site: str) -> str:
    jeton = jeton_webhook()
    base = _env().get("PUBLIC_API_URL", "https://api.cheffer.email").rstrip("/")
    return f"{base}/api/webhook/onoff/{site}" + (f"?token={jeton}" if jeton else "")


# ── Appels HTTP ──────────────────────────────────────────────────────────────

def _requete(site: str, chemin: str, params: dict | None = None,
             methode: str = "GET", corps: dict | None = None) -> dict:
    """Un appel à l'API Onoff. Rend toujours un dict, jamais d'exception.

    La forme du retour reprend le vocabulaire des connecteurs du tableau de bord —
    `raison` vaut `cle`, `service`, `reseau` ou `absente` — pour qu'un écran sache quoi
    proposer sans réinterpréter un message d'erreur.
    """
    k = cle(site)
    if not k:
        return {"ok": False, "raison": "absente",
                "error": "aucune clé Onoff enregistrée pour ce site"}

    url = f"{BASE_URL}{chemin}"
    entetes = {"x-api-key": k, "Accept": "application/json"}
    dernier: dict = {}
    for _ in range(ESSAIS):
        t0 = time.time()
        try:
            if methode == "POST":
                r = requests.post(url, headers={**entetes, "Content-Type": "application/json"},
                                  json=corps or {}, timeout=DELAI_S)
            else:
                r = requests.get(url, headers=entetes, params=params or {}, timeout=DELAI_S)
            ms = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                try:
                    return {"ok": True, "latence_ms": ms, "data": r.json()}
                except ValueError:
                    return {"ok": True, "latence_ms": ms, "data": {}, "brut": r.text[:500]}
            # 404/405 sur un POST = l'endpoint n'existe pas (encore). Ce n'est pas une panne.
            raison = ("cle" if r.status_code in (401, 403)
                      else "absent" if r.status_code in (404, 405)
                      else "service")
            return {"ok": False, "raison": raison, "http": r.status_code, "latence_ms": ms,
                    "error": (r.text or "")[:300] or f"HTTP {r.status_code}"}
        except (requests.Timeout, requests.ConnectionError) as e:
            dernier = {"ok": False, "raison": "reseau", "latence_ms": int((time.time() - t0) * 1000),
                       "error": str(e)[:200]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "raison": "service", "error": str(e)[:200]}
    return dernier


def verifier(site: str) -> dict:
    """Sonde vivante : la clé passe-t-elle ? Sert à la page de configuration."""
    if not configure(site):
        return {"status": "missing_key", "raison": "absente"}
    r = _requete(site, "/api/v1/members", {"limit": 1})
    if r.get("ok"):
        return {"status": "ok", "latence_ms": r.get("latence_ms")}
    return {"status": "error", "raison": r.get("raison"), "http": r.get("http"),
            "latence_ms": r.get("latence_ms"), "error": r.get("error")}


# ── Numéros de téléphone ─────────────────────────────────────────────────────

def e164(tel: str, pays: str = "FR") -> str:
    """Normalise un numéro pour `tel:` et pour le rapprochement avec les journaux Onoff.

    Le pool stocke des numéros français en format national (`0428384508`). Onoff renvoie
    des numéros internationaux. Sans normalisation des DEUX côtés, aucun rapprochement ne
    peut aboutir et le journal d'appels resterait décoratif.
    """
    if not tel:
        return ""
    n = re.sub(r"[^\d+]", "", str(tel))
    if not n:
        return ""
    if n.startswith("+"):
        return n
    if n.startswith("00"):
        return "+" + n[2:]
    if pays == "FR":
        if n.startswith("33") and len(n) >= 11:
            return "+" + n
        if n.startswith("0") and len(n) == 10:
            return "+33" + n[1:]
    return n if n.startswith("+") else "+" + n


def lisible(tel: str) -> str:
    """`+33428384508` → `04 28 38 45 08`. Un numéro se lit par paires, pas d'un bloc."""
    n = e164(tel)
    if n.startswith("+33") and len(n) == 12:
        national = "0" + n[3:]
        return " ".join(national[i:i + 2] for i in range(0, 10, 2))
    return n or tel


# ── Lectures API ─────────────────────────────────────────────────────────────

def _liste(r: dict) -> list[dict]:
    """Onoff n'est pas constant sur l'enveloppe : parfois une liste nue, parfois `data`,
    `items` ou `results`. On accepte les quatre plutôt que de casser sur la variante."""
    if not r.get("ok"):
        return []
    d = r.get("data")
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in ("data", "items", "results", "content", "members", "numbers", "calls", "messages"):
            v = d.get(k)
            if isinstance(v, list):
                return v
    return []


def membres(site: str) -> dict:
    r = _requete(site, "/api/v1/members")
    return {"ok": r.get("ok", False), "membres": _liste(r), "erreur": r.get("error"),
            "raison": r.get("raison")}


def numeros(site: str) -> dict:
    r = _requete(site, "/api/v1/numbers")
    return {"ok": r.get("ok", False), "numeros": _liste(r), "erreur": r.get("error"),
            "raison": r.get("raison")}


def statistiques(site: str, depuis: str = "", jusqu_a: str = "") -> dict:
    params = {}
    if depuis:
        params["startDate"] = depuis
    if jusqu_a:
        params["endDate"] = jusqu_a
    r = _requete(site, "/api/v1/statistics", params)
    return {"ok": r.get("ok", False), "stats": r.get("data") or {}, "erreur": r.get("error"),
            "raison": r.get("raison")}


def url_messagerie(site: str, appel_id: str) -> dict:
    """URL audio signée d'une messagerie. Onoff ne sert pas le fichier directement."""
    r = _requete(site, f"/api/v1/calls/{appel_id}/voicemail")
    d = r.get("data") or {}
    url = d.get("url") or d.get("voicemailUrl") or (d if isinstance(d, str) else "")
    return {"ok": bool(r.get("ok") and url), "url": url, "erreur": r.get("error")}


def envoyer_sms(site: str, depuis: str, vers: str, texte: str) -> dict:
    """Tente l'envoi d'un SMS.

    Onoff annonce cette capacité « à venir ». On tente quand même : le jour où l'endpoint
    ouvre, l'envoi fonctionnera sans modification. En attendant, un refus EXPLICITE vaut
    mieux qu'un bouton qui semble marcher — l'écran propose alors la main au téléphone.
    """
    texte = (texte or "").strip()
    if not texte:
        return {"ok": False, "raison": "vide", "error": "message vide"}
    if len(texte) > 1600:
        return {"ok": False, "raison": "trop_long",
                "error": f"message de {len(texte)} caractères (1600 maximum)"}
    vers_n = e164(vers)
    if not vers_n:
        return {"ok": False, "raison": "numero", "error": "numéro destinataire invalide"}

    r = _requete(site, "/api/v1/messages", methode="POST",
                 corps={"from": e164(depuis), "to": vers_n, "text": texte})
    if r.get("ok"):
        return {"ok": True, "data": r.get("data")}
    if r.get("raison") == "absent":
        return {"ok": False, "raison": "indisponible",
                "error": "L'API Onoff n'ouvre pas encore l'envoi de SMS "
                         "(annoncé « à venir » par l'éditeur). Utiliser l'application Onoff."}
    return {"ok": False, "raison": r.get("raison"), "error": r.get("error")}


# ── Journal local (alimenté par le webhook) ──────────────────────────────────

def assurer_schema() -> bool:
    """Applique le schéma s'il manque. Idempotent."""
    import pool_pg
    c = pool_pg._conn()
    try:
        with c.cursor() as cur:
            cur.execute(SCHEMA.read_text())
        c.commit()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[onoff] schéma non appliqué ({type(e).__name__}: {e})", flush=True)
        return False


def _texte(d: dict, *cles: str) -> str:
    for k in cles:
        v = d.get(k)
        if v not in (None, ""):
            return str(v)
    return ""


def enregistrer_evenement(site: str, charge: dict) -> dict:
    """Range un log Onoff (webhook) dans le journal local. Idempotent sur `id`.

    Onoff peut rejouer un log ; sans `ON CONFLICT`, une messagerie déjà lue redeviendrait
    non lue à chaque rejeu. La marque de lecture est donc préservée explicitement.
    """
    import pool_pg
    ident = _texte(charge, "id", "callId", "messageId")
    if not ident:
        return {"ok": False, "error": "log sans identifiant"}

    nom_ev = (_texte(charge, "eventName") or "CDR").upper()
    statut = _texte(charge, "callStatus")
    # Une messagerie se reconnaît par l'événement VM ou par le statut VMS — Onoff utilise
    # les deux selon le chemin. S'en tenir à un seul en perdrait la moitié.
    if nom_ev == "VM" or statut == STATUT_MESSAGERIE or _texte(charge, "voicemailUrl"):
        type_ev = "VM"
    elif nom_ev == "SMS" or _texte(charge, "text", "smsText", "message"):
        type_ev = "SMS"
    else:
        type_ev = nom_ev if nom_ev in TYPES else "CDR"

    duree = charge.get("callDuration")
    audio = _texte(charge, "voicemailUrl", "callRecordingUrl")

    sql = """
        INSERT INTO onoff_evenements
            (id, site_code, type, direction, statut, membre_nom, membre_email,
             numero_onoff, numero_externe, nom_externe, societe_externe,
             debut, fin, duree_s, texte, url_audio, duree_audio_s, notes, brut)
        VALUES (%(id)s, %(site)s, %(type)s, %(dir)s, %(statut)s, %(mnom)s, %(mmail)s,
                %(non)s, %(next)s, %(nom)s, %(societe)s,
                %(debut)s, %(fin)s, %(duree)s, %(texte)s, %(audio)s, %(daudio)s,
                %(notes)s, %(brut)s)
        ON CONFLICT (id) DO UPDATE SET
            statut     = EXCLUDED.statut,
            duree_s    = EXCLUDED.duree_s,
            url_audio  = COALESCE(EXCLUDED.url_audio, onoff_evenements.url_audio),
            texte      = COALESCE(EXCLUDED.texte, onoff_evenements.texte),
            notes      = COALESCE(EXCLUDED.notes, onoff_evenements.notes),
            brut       = EXCLUDED.brut
        -- `lu_at` n'est JAMAIS réécrit : un rejeu d'Onoff ne doit pas remettre en non lu
        -- une messagerie déjà écoutée.
    """
    n = pool_pg._ecrire(sql, {
        "id": ident, "site": site, "type": type_ev,
        "dir": _texte(charge, "callDirection") or None,
        "statut": statut or None,
        "mnom": _texte(charge, "onoffUserName") or None,
        "mmail": (_texte(charge, "onoffUserEmail") or "").lower() or None,
        "non": e164(_texte(charge, "onoffUserNumber")) or None,
        "next": e164(_texte(charge, "externalNumber")) or None,
        "nom": _texte(charge, "externalName") or None,
        "societe": _texte(charge, "externalCompanyName") or None,
        "debut": _texte(charge, "callStarted", "sentAt", "createdAt") or None,
        "fin": _texte(charge, "callEnded") or None,
        "duree": int(duree) if isinstance(duree, (int, float)) else None,
        "texte": _texte(charge, "text", "smsText", "message") or None,
        "audio": audio or None,
        "daudio": charge.get("voicemailDuration"),
        "notes": _texte(charge, "callNotes") or None,
        "brut": json.dumps(charge, ensure_ascii=False)[:200000],
    })
    return {"ok": True, "id": ident, "type": type_ev, "lignes": n}


def _lignes(sql: str, params: dict) -> list[dict]:
    import pool_pg
    c = pool_pg._conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        pool_pg._rendre(c)


def messagerie(site: str, seulement_non_lus: bool = False, limite: int = 100) -> dict:
    """Les messages vocaux, non lus d'abord."""
    sql = """
        SELECT id, direction, statut, membre_nom, numero_onoff, numero_externe,
               nom_externe, societe_externe, debut, duree_audio_s, url_audio, notes,
               (lu_at IS NULL) AS non_lu, lu_at
          FROM onoff_evenements
         WHERE site_code = %(site)s AND type = 'VM'
           AND (%(tous)s OR lu_at IS NULL)
         ORDER BY (lu_at IS NULL) DESC, debut DESC NULLS LAST
         LIMIT %(lim)s
    """
    lignes = _lignes(sql, {"site": site, "tous": not seulement_non_lus,
                           "lim": max(1, min(int(limite or 100), 500))})
    for l in lignes:
        l["numero_lisible"] = lisible(l.get("numero_externe") or "")
    return {"ok": True, "messages": lignes,
            "non_lus": sum(1 for l in lignes if l.get("non_lu"))}


def compter_non_lus(site: str) -> int:
    r = _lignes("SELECT count(*) AS n FROM onoff_evenements "
                "WHERE site_code = %(site)s AND type = 'VM' AND lu_at IS NULL",
                {"site": site})
    return int(r[0]["n"]) if r else 0


def marquer_lu(site: str, ident: str, lu: bool = True) -> dict:
    """Marque une messagerie lue, ou la remet en non lu. `site` est dans le WHERE : une
    marque posée depuis un site ne doit pas pouvoir toucher l'événement d'un autre."""
    import pool_pg
    n = pool_pg._ecrire(
        "UPDATE onoff_evenements SET lu_at = CASE WHEN %(lu)s THEN now() ELSE NULL END "
        "WHERE id = %(id)s AND site_code = %(site)s AND type = 'VM'",
        {"lu": bool(lu), "id": ident, "site": site})
    return {"ok": n > 0, "lignes": n}


def appels(site: str, limite: int = 100, numero: str = "") -> dict:
    """Journal d'appels local. `numero` filtre sur un interlocuteur (E.164 ou national)."""
    sql = """
        SELECT id, type, direction, statut, membre_nom, numero_onoff, numero_externe,
               nom_externe, societe_externe, debut, duree_s, url_audio, notes
          FROM onoff_evenements
         WHERE site_code = %(site)s AND type IN ('CDR', 'VM', 'RECORDING')
           AND (%(num)s = '' OR numero_externe = %(num)s)
         ORDER BY debut DESC NULLS LAST
         LIMIT %(lim)s
    """
    lignes = _lignes(sql, {"site": site, "num": e164(numero) if numero else "",
                           "lim": max(1, min(int(limite or 100), 500))})
    for l in lignes:
        l["numero_lisible"] = lisible(l.get("numero_externe") or "")
    return {"ok": True, "appels": lignes}


def fils_sms(site: str, numero: str = "", limite: int = 200) -> dict:
    """Les SMS, groupés par interlocuteur — un fil par numéro."""
    sql = """
        SELECT id, direction, membre_nom, numero_onoff, numero_externe, nom_externe,
               debut, texte
          FROM onoff_evenements
         WHERE site_code = %(site)s AND type = 'SMS'
           AND (%(num)s = '' OR numero_externe = %(num)s)
         ORDER BY debut DESC NULLS LAST
         LIMIT %(lim)s
    """
    lignes = _lignes(sql, {"site": site, "num": e164(numero) if numero else "",
                           "lim": max(1, min(int(limite or 200), 1000))})
    fils: dict[str, dict] = {}
    for l in lignes:
        k = l.get("numero_externe") or "?"
        f = fils.setdefault(k, {"numero": k, "numero_lisible": lisible(k),
                                "nom": l.get("nom_externe"), "messages": []})
        f["messages"].append(l)
    for f in fils.values():
        f["messages"].reverse()          # ordre de lecture : du plus ancien au plus récent
        f["dernier"] = f["messages"][-1]["debut"] if f["messages"] else None
    return {"ok": True, "fils": sorted(fils.values(),
                                       key=lambda f: f["dernier"] or "", reverse=True)}


def resume(site: str) -> dict:
    """Le bandeau de la page ON/OFF : ce qui s'est passé sur 30 jours + non-lus."""
    sql = """
        SELECT count(*) FILTER (WHERE type IN ('CDR','VM','RECORDING'))            AS appels,
               -- Le sens ne compte QUE les appels : un SMS entrant gonflait « entrants »
               -- et le total ne s'additionnait plus (2 appels, 2 entrants, 1 sortant).
               count(*) FILTER (WHERE direction = 'INBOUND'
                                  AND type IN ('CDR','VM','RECORDING'))            AS entrants,
               count(*) FILTER (WHERE direction = 'OUTBOUND'
                                  AND type IN ('CDR','VM','RECORDING'))            AS sortants,
               count(*) FILTER (WHERE statut = 'MISSED_CALL')                      AS manques,
               count(*) FILTER (WHERE type = 'SMS')                                AS sms,
               count(*) FILTER (WHERE type = 'VM')                                 AS messagerie,
               COALESCE(sum(duree_s), 0)                                           AS secondes
          FROM onoff_evenements
         WHERE site_code = %(site)s AND debut >= now() - interval '30 days'
    """
    r = _lignes(sql, {"site": site})
    d = dict(r[0]) if r else {}
    d["non_lus"] = compter_non_lus(site)
    d["minutes"] = round((d.get("secondes") or 0) / 60)
    return d
