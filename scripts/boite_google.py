"""
boite_google.py — « Connecter avec Google » pour Ma boîte d'envoi (2026-11-02).

Demande de Camille, après la connexion de Sylvie : le mot de passe d'application exige la
validation en deux étapes, et les commerciaux ne s'en sortent pas seuls. Ici, un clic sur
le bouton, Google affiche « Cheffer veut accéder à votre compte », on accepte : fini.

## Pourquoi c'est possible sans la validation Google de l'application
L'accès complet à Gmail (`https://mail.google.com/`, seul scope qui ouvre SMTP et IMAP) est
« restreint » : pour une application PUBLIQUE, Google exige une validation et un audit de
sécurité annuel (c'était la raison du mot de passe d'application, cf. boite_commercial.py).
Une application INTERNE à un Workspace en est dispensée : seuls les comptes du domaine
peuvent s'y connecter. D'où un projet Google Cloud à part, créé par camille@leclientroi.com
DANS l'organisation leclientroi.com — le projet de « Se connecter avec Google »
(auth_google.py) appartient au Gmail perso et n'a pas d'organisation.

## Le flux
  1. POST /api/sites/{site}/ma-boite/google → l'URL Google ; le `state` est lié à
     l'utilisateur de la session ET posé en cookie (sinon quelqu'un pourrait faire accepter
     son lien à un autre et récupérer sa boîte sur son propre compte Cheffer).
  2. GET /api/boite/google/callback → code échangé contre un jeton de rafraîchissement,
     boîte testée en SMTP + IMAP, enregistrée chiffrée (Fernet) comme l'ancien mot de passe.
  3. Retour sur /site/{site}/ma-boite?google=ok (ou le code d'erreur).

Le jeton de rafraîchissement ne périme pas tant que la personne ne le révoque pas (ou ne
change pas de mot de passe Google). Chaque connexion SMTP/IMAP prend un jeton d'accès
d'une heure, gardé en mémoire.

Clés dans genesis/.env : GOOGLE_BOITE_CLIENT_ID, GOOGLE_BOITE_CLIENT_SECRET.
"""
from __future__ import annotations

import base64
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

ENV_FILE = Path("/home/autoblog/genesis/.env")
URL_PUBLIQUE = "https://api.cheffer.email"
REDIRECT_URI = URL_PUBLIQUE + "/api/boite/google/callback"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
SCOPES = "openid email profile https://mail.google.com/"
COOKIE = "cheffer_boite_state"
CHEMIN_COOKIE = "/api/boite/google"
DUREE_STATE_S = 600

# state → (expiration, utilisateur, site). En mémoire, comme auth_google : un seul process.
_EN_COURS: dict[str, tuple[float, str, str]] = {}
# jeton de rafraîchissement → (expiration, jeton d'accès)
_ACCES: dict[str, tuple[float, str]] = {}


def _config() -> dict:
    env = {}
    if ENV_FILE.exists():
        for ligne in ENV_FILE.read_text().splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                k, _, v = ligne.partition("=")
                env[k.strip()] = v.strip().strip("'\"")
    return {"client_id": env.get("GOOGLE_BOITE_CLIENT_ID", ""),
            "client_secret": env.get("GOOGLE_BOITE_CLIENT_SECRET", "")}


def actif() -> bool:
    c = _config()
    return bool(c["client_id"] and c["client_secret"])


def debut(utilisateur: str, site: str, email_indice: str = "") -> tuple[str, str]:
    """Renvoie (url Google, state)."""
    c = _config()
    maintenant = time.time()
    for s, (exp, _, _) in list(_EN_COURS.items()):
        if exp < maintenant:
            _EN_COURS.pop(s, None)
    state = secrets.token_urlsafe(24)
    _EN_COURS[state] = (maintenant + DUREE_STATE_S, utilisateur, site)
    params = {
        "client_id": c["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        # offline + consent : sans eux, Google ne renvoie pas de jeton de rafraîchissement
        # à la deuxième connexion, et la boîte tomberait au bout d'une heure.
        "access_type": "offline",
        "prompt": "consent select_account",
    }
    if "@" in email_indice:
        # Ouvre Google directement sur la bonne adresse (vécu le 02/11 : avec plusieurs
        # comptes dans Chrome, Google prend sinon le compte par défaut).
        params["login_hint"] = email_indice
        params["hd"] = email_indice.split("@")[-1]
    return AUTH_URL + "?" + urlencode(params), state


def _charge_utile(id_token: str) -> dict:
    partie = id_token.split(".")[1]
    partie += "=" * (-len(partie) % 4)
    return json.loads(base64.urlsafe_b64decode(partie))


def verifier_retour(code: str, state: str, state_cookie: str) -> dict:
    """Renvoie {utilisateur, site, email, nom, jeton} ou {erreur, site?}.

    Même raisonnement que auth_google.verifier_retour pour l'id_token (reçu de Google en
    TLS contre notre secret : contrôles de contenu, pas de signature)."""
    if not state or not secrets.compare_digest(state, state_cookie or ""):
        return {"erreur": "session_expiree"}
    attente = _EN_COURS.pop(state, None)
    if not attente or attente[0] < time.time():
        return {"erreur": "session_expiree"}
    _, utilisateur, site = attente
    c = _config()
    try:
        r = requests.post(TOKEN_URL, data={
            "code": code, "client_id": c["client_id"], "client_secret": c["client_secret"],
            "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code",
        }, timeout=15)
    except requests.RequestException:
        return {"erreur": "google_injoignable", "site": site}
    d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200 or "id_token" not in d:
        return {"erreur": "google_refus", "site": site}
    if "https://mail.google.com/" not in (d.get("scope") or "").split():
        # La case « Lire, rédiger, envoyer… » décochée sur l'écran de Google.
        return {"erreur": "acces_gmail_refuse", "site": site}
    if not d.get("refresh_token"):
        return {"erreur": "sans_jeton", "site": site}
    infos = _charge_utile(d["id_token"])
    if infos.get("aud") != c["client_id"] or infos.get("iss") not in ISSUERS \
            or int(infos.get("exp", 0)) < time.time():
        return {"erreur": "jeton_invalide", "site": site}
    email = (infos.get("email") or "").lower()
    if not email or not infos.get("email_verified"):
        return {"erreur": "email_non_verifie", "site": site}
    _ACCES[d["refresh_token"]] = (time.time() + int(d.get("expires_in", 3600)) - 120,
                                  d["access_token"])
    return {"utilisateur": utilisateur, "site": site, "email": email,
            "nom": infos.get("name") or "", "jeton": d["refresh_token"]}


def jeton_acces(jeton_rafraichissement: str) -> str:
    """Un jeton d'accès valide (≈ 1 h). Lève RuntimeError si Google refuse : jeton révoqué."""
    deja = _ACCES.get(jeton_rafraichissement)
    if deja and deja[0] > time.time():
        return deja[1]
    c = _config()
    r = requests.post(TOKEN_URL, data={
        "client_id": c["client_id"], "client_secret": c["client_secret"],
        "refresh_token": jeton_rafraichissement, "grant_type": "refresh_token",
    }, timeout=15)
    if r.status_code != 200:
        raise RuntimeError("Google a révoqué l'accès de Cheffer à cette boîte : "
                           "reconnecte-la avec le bouton « Connecter avec Google ».")
    d = r.json()
    _ACCES[jeton_rafraichissement] = (time.time() + int(d.get("expires_in", 3600)) - 120,
                                      d["access_token"])
    return d["access_token"]


def revoquer(jeton_rafraichissement: str) -> None:
    """À la déconnexion : Cheffer disparaît aussi de « Applications tierces » côté Google."""
    _ACCES.pop(jeton_rafraichissement, None)
    try:
        requests.post(REVOKE_URL, data={"token": jeton_rafraichissement}, timeout=10)
    except requests.RequestException:
        pass


def xoauth2(email: str, jeton_rafraichissement: str) -> str:
    """La chaîne SASL XOAUTH2, avant base64 (smtplib et imaplib l'encodent eux-mêmes)."""
    return f"user={email}\x01auth=Bearer {jeton_acces(jeton_rafraichissement)}\x01\x01"
