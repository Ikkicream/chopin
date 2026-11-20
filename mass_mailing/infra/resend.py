#!/usr/bin/env python3
"""mass_mailing/infra/resend.py — envoi par Resend pour les espaces CLIENTS (SaaS, 13/10/2026).

Même interface que `infra/sweego.py` (`configure`, `envoyer_un`, `domaines_verifies`,
`valider_corps`, `sante`) : le pipeline d'envoi ne sait pas quel fournisseur il appelle,
c'est `infra/fournisseurs.py` qui choisit selon l'espace courant.

Règles tenues ici, pas seulement documentées :
- **1 destinataire = 1 mail** : `to` contient UNE adresse, jamais de cc/bcc, jamais
  `/emails/batch` (verrou `_verrou_un_a_un`, comme Cheffer depuis le mail de groupe du 30/07).
- **Désinscription en un clic (RFC 8058)** : `List-Unsubscribe` + `List-Unsubscribe-Post`
  posés à la main — Resend ne les ajoute pas sur `/emails`.
- **Rattachement** : tags `tenant` (slug client) et `campaign` (mm-<uuid>) → le webhook
  unique du compte route chaque événement vers le bon schéma.
- **Idempotence** : `Idempotency-Key` par destinataire et par campagne (24 h chez Resend) :
  un réseau qui coupe ne produit jamais deux mails.

Doc : `.claude/skills/saas-email-stack/references/resend.md`.
"""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

import requests

RESEND_URL = "https://api.resend.com"
ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TAG = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
# Débit (20/10/2026) : Resend plafonne à 10 requêtes/s pour TOUT le compte (lectures comprises).
# Les 4 fils d'envoi en rafale le dépassaient : chaque 429 était pris pour un quota et le reste du
# lot partait le lendemain (A/B test Zylio bloqué 4 jours). On garde de la marge : 5 envois/s.
ENVOIS_PAR_SECONDE = 5
ESSAIS_429 = 5
_cadence = {"verrou": threading.Lock(), "prochain": 0.0}


def _attendre_tour() -> None:
    with _cadence["verrou"]:
        attente = _cadence["prochain"] - time.monotonic()
        _cadence["prochain"] = max(_cadence["prochain"], time.monotonic()) + 1.0 / ENVOIS_PAR_SECONDE
    if attente > 0:
        time.sleep(attente)
_CACHE_DOMAINES: dict = {"t": 0.0, "v": []}


class EnvoiGroupeInterdit(RuntimeError):
    """Un corps qui viserait plus d'une adresse. Ne doit jamais partir."""


def _env(cle: str, defaut: str = "") -> str:
    v = os.environ.get(cle, "")
    if v:
        return v
    if ENV_FILE.exists():
        for l in ENV_FILE.read_text().splitlines():
            if l.strip().startswith(cle + "="):
                return l.split("=", 1)[1].strip().strip("'\"")
    return defaut


def _headers(idempotence: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {_env('RESEND_API_KEY')}", "Content-Type": "application/json",
         "User-Agent": "mass-email/1.0"}
    if idempotence:
        h["Idempotency-Key"] = idempotence[:256]
    return h


def configure() -> bool:
    return bool(_env("RESEND_API_KEY"))


# ── Domaines ─────────────────────────────────────────────────────────────────
def domaines(force: bool = False) -> list[dict]:
    if not force and time.time() - _CACHE_DOMAINES["t"] < 600:
        return _CACHE_DOMAINES["v"]
    r = requests.get(RESEND_URL + "/domains", headers=_headers(), timeout=20)
    r.raise_for_status()
    v = [{"domain": d["name"], "id": d["id"], "status": d.get("status"), "region": d.get("region"),
          "is_verified": d.get("status") == "verified"} for d in (r.json() or {}).get("data", [])]
    _CACHE_DOMAINES.update(t=time.time(), v=v)
    return v


def domaines_verifies() -> set[str]:
    return {d["domain"] for d in domaines() if d.get("is_verified")}


def creer_domaine(nom: str, region: str = "eu-west-1", return_path: str = "send") -> dict:
    r = requests.post(RESEND_URL + "/domains", headers=_headers(), timeout=30,
                      json={"name": nom, "region": region, "custom_return_path": return_path})
    r.raise_for_status()
    _CACHE_DOMAINES["t"] = 0
    return r.json()


def lire_domaine(fournisseur_id: str) -> dict:
    r = requests.get(f"{RESEND_URL}/domains/{fournisseur_id}", headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def verifier_domaine(fournisseur_id: str) -> dict:
    """Asynchrone chez Resend : le statut repasse à `pending`, puis évolue (relire ensuite)."""
    r = requests.post(f"{RESEND_URL}/domains/{fournisseur_id}/verify", headers=_headers(), timeout=20)
    _CACHE_DOMAINES["t"] = 0
    return {"ok": r.status_code < 300, "statut": r.status_code, "corps": (r.text or "")[:300]}


SOUS_DOMAINE_SUIVI = "links"


def regler_suivi(fournisseur_id: str, ouvertures: bool = True, clics: bool = True) -> dict:
    """Active le suivi des ouvertures. Depuis 2026, Resend ne l'APPLIQUE que si un sous-domaine de
    suivi (`tracking_subdomain`) est configuré ET vérifié : sans lui, le PATCH répond 200 et ne
    change rien (vécu sur Zylio le 14/10 : 0 ouverture sur les 20 premiers envois). On pose donc
    le sous-domaine (CNAME `links.<domaine>` à publier) et on RELIT le domaine pour constater."""
    r = requests.patch(f"{RESEND_URL}/domains/{fournisseur_id}", headers=_headers(), timeout=20,
                       json={"open_tracking": ouvertures, "click_tracking": clics,
                             "tracking_subdomain": SOUS_DOMAINE_SUIVI})
    _CACHE_DOMAINES["t"] = 0
    etat = etat_suivi(lire_domaine(fournisseur_id)) if r.status_code < 300 else {}
    return {"ok": r.status_code < 300 and etat.get("demande") == ouvertures, "statut": r.status_code, **etat}


def etat_suivi(brut: dict) -> dict:
    """Le suivi des ouvertures fonctionne-t-il VRAIMENT ? Réglage actif + sous-domaine posé +
    enregistrement « Tracking » vérifié chez Resend."""
    pistes = [x for x in brut.get("records") or [] if x.get("record") == "Tracking"]
    verifie = any(x.get("status") == "verified" for x in pistes)
    demande = bool(brut.get("open_tracking"))
    return {"demande": demande, "sous_domaine": brut.get("tracking_subdomain"),
            "dns_verifie": verifie, "actif": demande and bool(brut.get("tracking_subdomain")) and verifie}


# ── Contrôle du corps (doc Resend, POST /emails) ─────────────────────────────
def _verrou_un_a_un(corps: dict) -> None:
    to = corps.get("to")
    n = len(to) if isinstance(to, list) else (1 if isinstance(to, str) and to else 0)
    if n != 1 or corps.get("cc") or corps.get("bcc"):
        raise EnvoiGroupeInterdit(f"{n} destinataire(s), cc={bool(corps.get('cc'))}, bcc={bool(corps.get('bcc'))}")


def valider_corps(corps: dict, verifies: set[str] | None = None) -> list[dict]:
    lignes = []

    def l(champ, ok, valeur, regle):
        lignes.append({"champ": champ, "ok": bool(ok), "valeur": valeur, "regle": regle})

    frm = corps.get("from") or ""
    adresse = (re.search(r"<([^>]+)>", frm) or [None, frm])[1] if frm else ""
    dom = (adresse or "").rsplit("@", 1)[-1].lower()
    to = corps.get("to") or []
    l("from", bool(_EMAIL.match(adresse or "")) and (verifies is None or dom in verifies), frm,
      "Obligatoire ; « Nom <adresse> » sur un domaine VÉRIFIÉ chez Resend")
    l("to", isinstance(to, list) and len(to) == 1 and bool(_EMAIL.match(to[0] or "")),
      f"{len(to) if isinstance(to, list) else '?'} destinataire(s)", "UN seul destinataire par mail (règle Cheffer)")
    l("cc / bcc", not corps.get("cc") and not corps.get("bcc"), "aucun", "Interdits : exposeraient des adresses")
    l("subject", bool((corps.get("subject") or "").strip()), corps.get("subject"), "Obligatoire")
    l("html / text", bool(corps.get("html") or corps.get("text")), "html" if corps.get("html") else "texte",
      "Au moins un des deux")
    l("html < 102 Ko", len((corps.get("html") or "").encode()) < 102_000, f"{len((corps.get('html') or '').encode())} o",
      "Gmail tronque au-delà de 102 Ko (le lien de désinscription disparaît)")
    rt = corps.get("reply_to")
    l("reply_to", rt is None or bool(_EMAIL.match(rt if isinstance(rt, str) else "")), rt,
      "Facultatif ; une vraie boîte lue (le sous-domaine d'envoi n'a pas de MX)")
    hd = corps.get("headers") or {}
    marketing = corps.get("_marketing", True)
    l("List-Unsubscribe", (not marketing) or (bool(hd.get("List-Unsubscribe"))
                                              and hd.get("List-Unsubscribe-Post") == "List-Unsubscribe=One-Click"),
      "présent" if hd.get("List-Unsubscribe") else "absent", "Obligatoire en marketing (Gmail/Yahoo/Microsoft, RFC 8058)")
    tags = corps.get("tags") or []
    l("tags", len(tags) <= 75 and all(_TAG.match(t.get("name", "")) and _TAG.match(t.get("value", "")) for t in tags),
      [f"{t.get('name')}={t.get('value')}" for t in tags], "[A-Za-z0-9_-] ; « tenant » et « campaign » requis au routage")
    l("tag tenant", any(t.get("name") == "tenant" for t in tags), "", "Sans lui, le webhook ne sait pas à quel client rendre l'événement")
    return lignes


# ── Envoi ────────────────────────────────────────────────────────────────────
def envoyer_un(*, destinataire: str, subject: str, html_str: str, texte: str,
               expediteur: dict, campagne: str, tags: list[str] | None = None,
               dry_run: bool = False, url_desinscription: str | None = None) -> dict:
    """UN mail à UN destinataire via POST /emails. Ne lève jamais (sauf verrou un-à-un).

    `expediteur` : {from_name, from_email, reply_to, campaign_type, tenant, idempotence?}.
    Renvoie {"ok", "transaction_id", "swg_uid"} — `swg_uid` porte l'id Resend pour que le
    pipeline existant l'enregistre sans changement — ou {"ok": False, "erreur", "definitif"}.
    """
    if not configure():
        return {"ok": False, "erreur": "RESEND_API_KEY manquante", "definitif": True}
    if not destinataire or "@" not in destinataire:
        return {"ok": False, "erreur": "destinataire invalide", "definitif": True}
    tenant = (expediteur.get("tenant") or "").strip()
    marketing = (expediteur.get("campaign_type") or "market") != "transac"
    etiquettes = [{"name": "tenant", "value": tenant or "interne"},
                  {"name": "campaign", "value": re.sub(r"[^A-Za-z0-9_-]", "-", campagne)[:256]}]
    for t in (tags or [])[:10]:
        if _TAG.match(t):
            etiquettes.append({"name": "t_" + t[:60], "value": "1"})
    nom = (expediteur.get("from_name") or "").replace('"', "").strip()
    corps = {
        "from": f'"{nom}" <{expediteur["from_email"]}>' if nom else expediteur["from_email"],
        "to": [destinataire],                       # UNE adresse, toujours
        "subject": subject,
        "html": html_str,
        "text": texte,
        "tags": etiquettes,
        "headers": {},
        "_marketing": marketing,
    }
    if expediteur.get("reply_to"):
        corps["reply_to"] = expediteur["reply_to"]
    if url_desinscription:
        corps["headers"]["List-Unsubscribe"] = f"<{url_desinscription}>"
        corps["headers"]["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    _verrou_un_a_un(corps)
    fautes = [x for x in valider_corps(corps) if not x["ok"]]
    if fautes:
        return {"ok": False, "definitif": True,
                "erreur": "requête refusée par le contrôle : " + ", ".join(f["champ"] for f in fautes)}
    if expediteur.get("_corps_seulement") or dry_run:
        return {"ok": True, "corps": {k: v for k, v in corps.items() if not k.startswith("_")}, "dry_run": True}
    envoi = {k: v for k, v in corps.items() if not k.startswith("_")}
    if not envoi["headers"]:
        envoi.pop("headers")
    cle = expediteur.get("idempotence") or f"{campagne}:{destinataire.lower()}"
    for essai in range(ESSAIS_429):
        _attendre_tour()
        try:
            r = requests.post(RESEND_URL + "/emails", headers=_headers(cle), json=envoi, timeout=30)
        except requests.RequestException as e:
            # Resend a PEUT-ÊTRE accepté. La clé d'idempotence rend un rejeu sûr pendant 24 h,
            # mais on garde la prudence du pipeline : pas de rejeu automatique.
            return {"ok": False, "incertain": True, "definitif": True, "erreur": f"réseau : {str(e)[:200]}"}
        # 429 de DÉBIT (rate_limit_exceeded) : refus net, rien n'est parti → on attend et on rejoue
        # (même clé d'idempotence). Un 429 de QUOTA (daily/monthly_quota_exceeded) n'est pas rejoué.
        if r.status_code != 429 or "rate_limit" not in (r.text or ""):
            break
        try:
            pause = float(r.headers.get("retry-after") or 1)
        except ValueError:
            pause = 1.0
        time.sleep(min(10.0, max(0.5, pause)) * (essai + 1))
    if r.status_code in (200, 201):
        d = r.json() if r.content else {}
        return {"ok": True, "transaction_id": d.get("id"), "swg_uid": d.get("id"), "provider": "resend"}
    corps_err = (r.text or "")[:300]
    return {"ok": False, "statut": r.status_code,
            "definitif": 400 <= r.status_code < 500 and r.status_code not in (409, 429),
            "quota": "quota_exceeded" in corps_err,
            "debit": r.status_code == 429 and "rate_limit" in corps_err,
            "erreur": f"resend {r.status_code} : {corps_err}"}


def statut_email(email_id: str) -> dict:
    """Dernier état connu d'un mail chez Resend (GET /emails/{id}) : sent, delivered, bounced,
    delivery_delayed, complained… Ne lève jamais."""
    try:
        r = requests.get(f"{RESEND_URL}/emails/{email_id}", headers=_headers(), timeout=15)
        if r.status_code != 200:
            return {"ok": False, "statut": r.status_code}
        d = r.json()
        return {"ok": True, "dernier": d.get("last_event"), "a": d.get("to"), "le": d.get("created_at")}
    except requests.RequestException as e:
        return {"ok": False, "erreur": str(e)[:150]}


def sante() -> dict:
    try:
        d = domaines(force=True)
        return {"ok": True, "domaines": [(x["domain"], x["status"]) for x in d]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erreur": str(e)[:200]}
