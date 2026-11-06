"""
auth_google.py — « Se connecter avec Google » pour Cheffer (2026-10-27).

Demande de Camille : ne plus sortir son téléphone pour le code Authenticator à chaque
connexion. Les comptes Workspace ont de toute façon la validation en 2 étapes (elle est
obligatoire pour créer le mot de passe d'application de « Ma boîte d'envoi »), et Google
sait la passer par l'empreinte ou le PIN de l'ordinateur et mémoriser l'appareil.

Flux OpenID Connect « code » classique, côté serveur :
  1. /api/auth/google/start    → redirection vers Google (state + nonce, cookie lié)
  2. /api/auth/google/callback → échange du code contre l'id_token, contrôles, session
  3. redirection vers /login/google#token=… (le jeton reste hors des journaux nginx)

Le client OAuth est de type « Interne » dans Google Cloud : seules les adresses du
Workspace peuvent s'y connecter, et Google n'exige aucune validation de l'application
(les scopes openid/email/profile ne sont pas « sensibles »).

Clés dans genesis/.env : GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET,
et en option GOOGLE_AUTH_DOMAINES (défaut : leclientroi.com).
"""

import base64
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

ENV_FILE = Path("/home/autoblog/genesis/.env")
URL_PUBLIQUE = "https://api.cheffer.email"
REDIRECT_URI = URL_PUBLIQUE + "/api/auth/google/callback"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
COOKIE = "cheffer_google_state"
DUREE_STATE_S = 600

# state → (expiration, nonce). En mémoire : l'API tourne en un seul process uvicorn ;
# un redémarrage pendant une connexion fait juste échouer cette tentative-là.
_EN_COURS: dict[str, tuple[float, str]] = {}


def _config() -> dict:
    env = {}
    if ENV_FILE.exists():
        for ligne in ENV_FILE.read_text().splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                k, _, v = ligne.partition("=")
                env[k.strip()] = v.strip().strip("'\"")
    domaines = env.get("GOOGLE_AUTH_DOMAINES", "leclientroi.com")
    return {
        "client_id": env.get("GOOGLE_OAUTH_CLIENT_ID", ""),
        "client_secret": env.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        "domaines": {d.strip().lower() for d in domaines.split(",") if d.strip()},
    }


def actif() -> bool:
    c = _config()
    return bool(c["client_id"] and c["client_secret"])


def debut() -> tuple[str, str]:
    """Renvoie (url Google, state). Le state va aussi dans un cookie, vérifié au retour."""
    c = _config()
    maintenant = time.time()
    for s, (exp, _) in list(_EN_COURS.items()):
        if exp < maintenant:
            _EN_COURS.pop(s, None)
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    _EN_COURS[state] = (maintenant + DUREE_STATE_S, nonce)
    params = {
        "client_id": c["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    }
    # Un seul domaine : Google ne propose que les comptes de ce Workspace.
    if len(c["domaines"]) == 1:
        params["hd"] = next(iter(c["domaines"]))
    return AUTH_URL + "?" + urlencode(params), state


def _charge_utile(id_token: str) -> dict:
    partie = id_token.split(".")[1]
    partie += "=" * (-len(partie) % 4)
    return json.loads(base64.urlsafe_b64decode(partie))


def verifier_retour(code: str, state: str, state_cookie: str) -> dict:
    """Renvoie {"email": …} ou {"erreur": code court}.

    L'id_token arrive directement de Google, en TLS, en échange de notre secret client :
    la spécification OpenID autorise alors à se passer de la vérification de signature.
    On contrôle quand même destinataire, émetteur, expiration, nonce et domaine.
    """
    if not state or not secrets.compare_digest(state, state_cookie or ""):
        return {"erreur": "session_expiree"}
    attente = _EN_COURS.pop(state, None)
    if not attente or attente[0] < time.time():
        return {"erreur": "session_expiree"}
    nonce = attente[1]
    c = _config()
    try:
        r = requests.post(TOKEN_URL, data={
            "code": code,
            "client_id": c["client_id"],
            "client_secret": c["client_secret"],
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }, timeout=15)
    except requests.RequestException:
        return {"erreur": "google_injoignable"}
    if r.status_code != 200 or "id_token" not in r.json():
        return {"erreur": "google_refus"}
    infos = _charge_utile(r.json()["id_token"])

    if infos.get("aud") != c["client_id"] or infos.get("iss") not in ISSUERS:
        return {"erreur": "jeton_invalide"}
    if int(infos.get("exp", 0)) < time.time() or infos.get("nonce") != nonce:
        return {"erreur": "jeton_invalide"}
    email = (infos.get("email") or "").lower()
    if not email or not infos.get("email_verified"):
        return {"erreur": "email_non_verifie"}
    # `hd` n'existe que pour un compte Workspace : un @gmail.com n'en a pas.
    if (infos.get("hd") or "").lower() not in c["domaines"] or email.split("@")[-1] not in c["domaines"]:
        return {"erreur": "domaine_refuse"}
    return {"email": email}
