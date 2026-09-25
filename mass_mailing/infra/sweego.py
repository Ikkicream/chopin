#!/usr/bin/env python3
"""mass_mailing/infra/sweego.py — routage d'envoi, copie autonome.

COPIE AUTONOME de `scripts/sweego_backend.py`, avec une omission délibérée : **aucune
persistance locale**. L'original mélangeait client HTTP et stockage DuckDB, et c'est
précisément son `duckdb.connect()` en dur qui fait redémarrer le dashboard une
vingtaine de fois par jour depuis des semaines. Ici, tout l'état vit dans PostgreSQL,
via `infra/pg.py` — ce module ne fait qu'une chose : parler à Sweego.

L'expéditeur n'est PAS lu dans `.env` comme dans l'original : il vient du profil
d'expédition de la campagne (`sender_profiles`). Une console qui gère plusieurs
profils ne peut pas avoir un expéditeur câblé en dur.

⚠️ Sur `delivered` : au 2026-09-25, les 12 411 événements reçus par le webhook
Cheffer ne contiennent AUCUN `delivered` — seulement `email_opened`, `hard_bounce`,
`email_clicked`, `complaint`, `list_unsub`. Tant que ce point n'est pas tranché avec
Sweego, le taux de livraison doit s'afficher « Non disponible », jamais « 0 % ».
"""
from __future__ import annotations

import html as _html
import os
import re
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"
SWEEGO_URL = "https://api.sweego.io"

# Au-delà, Sweego refuse ou tronque : la taille de lot d'envoi se règle dans
# `settings.sending_batch_size`, mais jamais au-dessus de ce plafond dur.
PLAFOND_DESTINATAIRES = 1000


def _env(cle: str, defaut: str = "") -> str:
    v = os.environ.get(cle)
    if v:
        return v
    if ENV_FILE.exists():
        for ligne in ENV_FILE.read_text().splitlines():
            ligne = ligne.strip()
            if ligne.startswith(f"{cle}=") and not ligne.startswith("#"):
                return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    return defaut


def _headers() -> dict:
    return {"Api-Key": _env("SWEEGO_API_KEY"), "Content-Type": "application/json"}


def configure() -> bool:
    return bool(_env("SWEEGO_API_KEY"))


# ── Préparation du message ──────────────────────────────────────────────────────
def nettoyer_html(html_str: str) -> str:
    """Retire les jetons de personnalisation restants. En V1 il n'y a AUCUNE variable
    (seule la première colonne du CSV est lue) : un `{{prenom}}` oublié dans le HTML
    partirait tel quel chez le destinataire."""
    return re.sub(r"\{\{[^}]*\}\}", "", html_str or "")


def html_vers_texte(html_str: str) -> str:
    """Version texte de secours. Une campagne marketing sans partie texte est un
    signal négatif pour les filtres anti-spam."""
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_str or "")
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</p\s*>", "\n\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = _html.unescape(t)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def liens_du_html(html_str: str) -> list[str]:
    """Tous les href du message — matière première des contrôles de préflight."""
    return re.findall(r'(?is)<a[^>]+href=["\']([^"\']+)["\']', html_str or "")


# ── Envoi ───────────────────────────────────────────────────────────────────────
def envoyer_un(*, destinataire: str, subject: str, html_str: str, texte: str,
               expediteur: dict, campagne: str, tags: list[str] | None = None,
               dry_run: bool = False) -> dict:
    """UN mail à UN destinataire, via `/send`. C'est le chemin des campagnes Mass Mailing.

    Pourquoi pas `/send/bulk/email` : chaque mail porte son propre lien de
    désinscription signé, et la doc Sweego ne garantit les variables par destinataire
    qu'avec un modèle hébergé chez eux (`template-id`). Un appel par destinataire rend
    le un-pour-un impossible à rater, et donne un `swg_uid` par mail.

    Ne lève jamais. `definitif` dit si réessayer a un sens.
    """
    if not configure():
        return {"ok": False, "erreur": "SWEEGO_API_KEY manquante", "definitif": True}
    if not destinataire or "@" not in destinataire:
        return {"ok": False, "erreur": "destinataire invalide", "definitif": True}
    corps = {
        "channel": "email",
        "provider": "sweego",                       # valeur de la doc (SKILL.md § 1)
        "campaign-type": "market",
        "campaign-id": campagne,
        "campaign-tags": [t for t in (tags or []) if re.fullmatch(r"[A-Za-z0-9-]{1,20}", t)][:5],
        "subject": subject,
        "from": {"email": expediteur["from_email"],
                 "name": expediteur.get("from_name") or expediteur["from_email"]},
        "recipients": [{"email": destinataire}],     # UN seul, toujours
        "message-html": html_str,
        "message-txt": texte,
        "dry-run": bool(dry_run),
    }
    if expediteur.get("reply_to"):
        corps["reply-to"] = {"email": expediteur["reply_to"]}   # objet, pas chaîne (doc)
    assert len(corps["recipients"]) == 1
    try:
        r = requests.post(SWEEGO_URL + "/send", headers=_headers(), json=corps, timeout=30)
    except requests.RequestException as e:
        # Délai dépassé : Sweego a PEUT-ÊTRE accepté. On ne rejoue pas automatiquement,
        # sinon la même personne risque de recevoir deux fois le même mail.
        return {"ok": False, "incertain": True, "definitif": True,
                "erreur": f"réseau : {str(e)[:200]}"}
    if r.status_code == 200:
        d = r.json() if r.content else {}
        uids = d.get("swg_uids") or {}
        return {"ok": True, "transaction_id": d.get("transaction_id"),
                "swg_uid": uids.get(destinataire) or next(iter(uids.values()), None)}
    return {"ok": False, "statut": r.status_code,
            "definitif": 400 <= r.status_code < 500 and r.status_code != 429,
            "erreur": f"sweego {r.status_code} : {(r.text or '')[:300]}"}


def logs_campagne(tag: str, debut: str, fin: str) -> list[dict]:
    """Tous les messages Sweego d'une étiquette de campagne (POST /logs, 500 par page).
    Source des statistiques : les statuts y sont cumulatifs (livré → ouvert → cliqué)."""
    sortie, offset = [], 0
    while True:
        r = requests.post(SWEEGO_URL + "/logs", headers=_headers(), timeout=60, json={
            "channel": "email", "campaign-tags": [tag], "start_date": debut,
            "end_date": fin, "size": 500, "offset": offset})
        r.raise_for_status()
        res = r.json().get("result") or []
        sortie += res
        if len(res) < 500:
            return sortie
        offset += 500


def envoyer_lot(*, campaign_id: str, subject: str, html_str: str,
                destinataires: list[str], expediteur: dict,
                texte: str | None = None, dry_run: bool = False,
                reference: str | None = None) -> dict:
    """Soumet UN lot à Sweego.

    `expediteur` : {from_name, from_email, reply_to}. `reference` est la clé
    d'idempotence du lot — elle voyage dans `campaign-id` pour qu'un même lot
    resoumis soit reconnaissable côté fournisseur et dans les événements retour.

    Ne lève jamais : renvoie toujours un dict, parce qu'un lot en échec doit pouvoir
    être journalisé et rejoué, pas faire tomber le worker.
    """
    if not configure():
        return {"ok": False, "erreur": "SWEEGO_API_KEY manquante", "definitif": True}

    emails = [e for e in (destinataires or []) if e and "@" in e]
    if not emails:
        return {"ok": False, "erreur": "aucun destinataire valide", "definitif": True}
    if len(emails) > PLAFOND_DESTINATAIRES:
        return {"ok": False, "definitif": True,
                "erreur": f"{len(emails)} destinataires : au-delà du plafond de "
                          f"{PLAFOND_DESTINATAIRES} par lot"}
    if not (subject or "").strip():
        return {"ok": False, "erreur": "sujet requis", "definitif": True}
    if not (expediteur or {}).get("from_email"):
        return {"ok": False, "erreur": "profil d'expédition incomplet", "definitif": True}

    corps = {
        "provider": "email",
        "campaign-type": "market",
        "campaign-id": reference or campaign_id,
        "subject": subject,
        "from": {"email": expediteur["from_email"],
                 "name": expediteur.get("from_name") or expediteur["from_email"]},
        "recipients": [{"email": e} for e in emails],
        "message-html": nettoyer_html(html_str),
        "message-txt": texte or html_vers_texte(html_str),
        "dry-run": bool(dry_run),
    }
    if expediteur.get("reply_to"):
        corps["reply-to"] = {"email": expediteur["reply_to"]}   # objet, pas chaîne (doc)

    # ⚠️ `/send` avec plusieurs destinataires = UN mail de GROUPE : chacun voit les
    # adresses de tous les autres dans le champ « À » (doc Sweego, « Method 1 »).
    # Pour un envoi de masse, c'est `/send/bulk/email` : un mail séparé par
    # destinataire, mêmes champs, 2 destinataires minimum. `/send` n'est gardé que
    # pour un destinataire unique. Doc : .claude/skills/sweego/SKILL.md § 1.
    route = "/send/bulk/email" if len(emails) >= 2 else "/send"
    try:
        r = requests.post(SWEEGO_URL + route, headers=_headers(), json=corps, timeout=60)
    except requests.RequestException as e:
        # Réseau : transitoire par nature, donc rejouable.
        return {"ok": False, "erreur": f"réseau : {str(e)[:200]}", "definitif": False}

    if r.status_code == 200:
        d = r.json() if r.content else {}
        # Réponse documentée (ModelOutSend, doc/api/send-bulk-email-*.api.md) :
        # `transaction_id` = cet appel, `swg_uids` = {destinataire: swg_uid}. Les deux
        # reviennent dans chaque webhook. Réponse brute gardée pour la stocker.
        return {"ok": True, "route": route, "transaction_id": d.get("transaction_id"),
                "acceptes": len(emails), "dry_run": dry_run, "brut": d}

    # 4xx = faute de notre côté, inutile de réessayer ; 5xx et 429 = transitoire.
    definitif = 400 <= r.status_code < 500 and r.status_code != 429
    return {"ok": False, "definitif": definitif, "statut": r.status_code,
            "erreur": f"sweego {r.status_code} : {(r.text or '')[:300]}"}


def verifier_message(*, subject: str, html_str: str, destinataire_test: str,
                     expediteur: dict) -> dict:
    """Validation par Sweego SANS envoi (`dry-run`), avant de planifier une campagne."""
    return envoyer_lot(campaign_id="preflight", subject=subject, html_str=html_str,
                       destinataires=[destinataire_test], expediteur=expediteur,
                       dry_run=True)


# ── Diagnostic ──────────────────────────────────────────────────────────────────
def stats_msp() -> dict:
    """Délivrabilité par messagerie (gmail, microsoft, yahoo…)."""
    if not configure():
        return {"ok": False, "erreur": "SWEEGO_API_KEY manquante"}
    try:
        r = requests.post(SWEEGO_URL + "/stats/msp", headers=_headers(),
                          json={"channel": "email"}, timeout=25)
        if r.status_code != 200:
            return {"ok": False, "erreur": f"http {r.status_code}"}
        d = r.json()
        return {"ok": True, "msps": d.get("msps", []), "result": d.get("result", [])}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erreur": str(e)[:200]}


def sante() -> dict:
    if not configure():
        return {"ok": False, "configure": False, "erreur": "SWEEGO_API_KEY manquante"}
    s = stats_msp()
    return {"ok": s.get("ok", False), "configure": True, "erreur": s.get("erreur")}


if __name__ == "__main__":
    import json
    print(json.dumps(sante(), ensure_ascii=False, indent=1))
