#!/usr/bin/env python3
"""mass_mailing/serveur.py — l'API de Mass Email, séparée de Cheffer (2026-09-26).

Pourquoi : Mass Email vivait dans le process de l'API Cheffer. Quand Cheffer se figeait
sur DuckDB (rafale de hard bounces, 26/09 midi), la remontée comportementale, la page de
rappel, la désinscription et la version en ligne tombaient avec. Ici : un process à part
(PM2 `mass-mailing-api`, 127.0.0.1:8090, derrière https://mail.cheffer.email), PostgreSQL
seul, aucun import de `scripts/` Cheffer, jamais DuckDB.

Accès :
- `/api/mass-mailing/*` : session Mass Email (jeton `mm_…`, table `mass_mailing.sessions`).
- `/api/public/mass-mailing/*` : public (désinscription, page de rappel, miroir, webhook).
- `/api/mm-auth/*` : connexion (mot de passe + double authentification), activation.
- `/api/auth/me` et `/api/ui-build` : mêmes contrats que Cheffer, pour l'interface Next.

Lancement : `python3 -m uvicorn mass_mailing.serveur:app --host 127.0.0.1 --port 8090`
depuis /home/autoblog/genesis.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))          # les modules de Mass Email s'importent en `infra.*`, `jobs.*`

from infra import auth, clients, pg, stockage  # noqa: E402
from api import ab, routes, saas  # noqa: E402
from jobs.clics import enregistrer_webhook  # noqa: E402

app = FastAPI(title="Mass Email", docs_url=None, redoc_url=None, openapi_url=None)
BUILD_ID = ICI.parent.parent / "genesis-ui" / ".next" / "BUILD_ID"


def _ip(request: Request) -> str:
    # Nginx pose X-Real-IP (vraie IP restaurée depuis Cloudflare) ; jamais le 1er X-Forwarded-For.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "")


def _jeton(request: Request) -> str:
    h = request.headers.get("authorization") or ""
    return h[7:].strip() if h.lower().startswith("bearer ") else ""


@app.middleware("http")
async def controle_acces(request: Request, suite):
    chemin = request.url.path
    if chemin.startswith("/api/mass-mailing") or chemin.startswith("/api/mm-admin"):
        u = auth.session(_jeton(request))
        if not u:
            return JSONResponse({"detail": "Session Mass Email requise"}, status_code=401)
        # SaaS (13/10) : chaque requête travaille dans le schéma d'UN client.
        #  - compte client  → son schéma, et lui seul (aucun en-tête ne peut l'en faire sortir) ;
        #  - superadmin     → l'espace interne, ou le client choisi par l'en-tête X-MM-Client.
        if u["role"] == "client":
            if u.get("client_statut") != "actif":
                return JSONResponse({"detail": "Espace client suspendu"}, status_code=403)
            if chemin.startswith("/api/mm-admin"):
                return JSONResponse({"detail": "Réservé au superadmin"}, status_code=403)
            schema, client = u["client_schema"], u["client_slug"]
        else:
            client = (request.headers.get("x-mm-client") or "").strip().lower()
            if client:
                fiche = clients.par_slug(client)
                if not fiche:
                    return JSONResponse({"detail": f"Client inconnu : {client}"}, status_code=404)
                schema = fiche["schema_pg"]
            else:
                schema = pg.SCHEMA
        request.state.session = {"role": u["role"], "username": u["identifiant"], "prenom": u.get("prenom"),
                                 "client": client or None, "schema": schema}
        jeton_schema = pg.poser_schema(schema)
        try:
            return await suite(request)
        finally:
            pg._SCHEMA_COURANT.reset(jeton_schema)
    if chemin.startswith("/api/public/mass-mailing"):
        # Liens publics d'un espace client : `e=<slug>`. Les signatures dépendent de l'espace
        # (desinscription._secret), donc changer `e` à la main ne fait qu'invalider le lien.
        e = (request.query_params.get("e") or "").strip().lower()
        if e:
            fiche = clients.par_slug(e)
            if not fiche:
                return JSONResponse({"detail": "lien invalide"}, status_code=404)
            jeton_schema = pg.poser_schema(fiche["schema_pg"])
            try:
                return await suite(request)
            finally:
                pg._SCHEMA_COURANT.reset(jeton_schema)
    return await suite(request)


# ── Contrats attendus par l'interface Next ───────────────────────────────────

@app.get("/api/auth/me")
def moi(request: Request):
    u = auth.session(_jeton(request))
    if not u:
        return JSONResponse({"ok": False, "detail": "non connecté"}, status_code=401)
    return {"ok": True, "username": u["identifiant"], "role": u["role"], "email": u["email"], "prenom": u.get("prenom"),
            "mfa_enabled": True, "application": "mass-email",
            "client": u.get("client_slug"),
            "fournisseur": (clients.par_slug(u["client_slug"]) or {}).get("fournisseur") if u.get("client_slug") else None,
            "clients": ([{"slug": c["slug"], "nom": c["nom"], "statut": c["statut"], "fournisseur": c["fournisseur"]}
                                                         for c in clients.lister()] if u["role"] == "superadmin" else None)}


@app.get("/api/ui-build")
def ui_build():
    try:
        return {"build": BUILD_ID.read_text().strip() if BUILD_ID.exists() else ""}
    except Exception:  # noqa: BLE001
        return {"build": ""}


# ── Connexion (mot de passe + double authentification) ───────────────────────
# Anti force brute : 8 échecs par IP sur 15 min → attente. En mémoire du process : le
# serveur est seul derrière Nginx, et un redémarrage qui remet à zéro reste tolérable.
_ECHECS: dict[str, deque] = defaultdict(deque)
FENETRE_S, MAX_ECHECS = 900, 8


def _bloque(ip: str) -> bool:
    d = _ECHECS[ip]
    while d and d[0] < time.time() - FENETRE_S:
        d.popleft()
    return len(d) >= MAX_ECHECS


@app.post("/api/mm-auth/connexion")
async def connexion(request: Request):
    ip = _ip(request)
    if _bloque(ip):
        return JSONResponse({"ok": False, "detail": "Trop d'essais. Réessayez dans 15 minutes."}, status_code=429)
    b = await request.json()
    u = auth.verifier_identifiants(b.get("identifiant") or "", b.get("mot_de_passe") or "")
    if not u or not auth.verifier_totp(u["totp_secret"], b.get("code") or ""):
        _ECHECS[ip].append(time.time())
        return JSONResponse({"ok": False, "detail": "Identifiant, mot de passe ou code incorrect."}, status_code=401)
    _ECHECS.pop(ip, None)
    return {"ok": True, "token": auth.ouvrir_session(u["id"], ip, request.headers.get("user-agent") or ""),
            "user": {"username": u["identifiant"], "role": u["role"], "client": u.get("client_id")}}


@app.post("/api/mm-auth/deconnexion")
def deconnexion(request: Request):
    auth.fermer_session(_jeton(request))
    return {"ok": True}


@app.get("/api/mm-auth/activation")
def invitation(jeton: str = ""):
    u = auth.lire_invitation(jeton)
    if not u:
        return JSONResponse({"ok": False, "detail": "Lien d'activation invalide ou expiré."}, status_code=404)
    secret = u["totp_en_attente"]            # stable : recharger la page garde le même QR
    uri = auth.uri_totp(u["identifiant"], secret)
    # QR code dessiné ICI (SVG) : jamais par un service extérieur, qui verrait la clé.
    try:
        import io
        import qrcode
        import qrcode.image.svg
        tampon = io.BytesIO()
        qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2).save(tampon)
        svg = tampon.getvalue().decode()
    except Exception:  # noqa: BLE001 — la clé en clair suffit à configurer l'application
        svg = ""
    return {"ok": True, "identifiant": u["identifiant"], "secret": secret, "uri": uri, "qr_svg": svg}


@app.post("/api/mm-auth/activation")
async def activation(request: Request):
    ip = _ip(request)
    if _bloque(ip):
        return JSONResponse({"ok": False, "detail": "Trop d'essais. Réessayez dans 15 minutes."}, status_code=429)
    b = await request.json()
    u, motif = auth.activer(b.get("jeton") or "", b.get("mot_de_passe") or "", b.get("code") or "")
    if not u:
        _ECHECS[ip].append(time.time())
        return JSONResponse({"ok": False, "detail": motif}, status_code=400)
    return {"ok": True, "token": auth.ouvrir_session(u["id"], ip, request.headers.get("user-agent") or "")}


# ── Webhook Sweego dédié à Mass Email ────────────────────────────────────────
# Jeton secret dans l'URL (Sweego n'envoie pas de signature exploitable ici) ; secret
# rangé dans le stockage privé du module, comme celui de la désinscription.
_SECRET_WEBHOOK = stockage.RACINE / ".secret_webhook"


def jeton_webhook() -> str:
    if not _SECRET_WEBHOOK.exists():
        stockage.RACINE.mkdir(parents=True, exist_ok=True)
        fd = os.open(_SECRET_WEBHOOK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(32))
    return _SECRET_WEBHOOK.read_text().strip()


@app.post("/api/public/mass-mailing/webhook")
async def webhook(request: Request, token: str = ""):
    if not hmac.compare_digest(token, jeton_webhook()):
        return JSONResponse({"ok": False}, status_code=403)
    data = await request.json()
    evenements = data if isinstance(data, list) else [data]
    ranges = sum(1 for e in evenements if isinstance(e, dict) and enregistrer_webhook(e))
    return {"ok": True, "ranges": ranges}


# ── Webhook Resend (espaces clients, SaaS 13/10) ─────────────────────────────
# Un seul endpoint pour le compte Resend ; signature Svix obligatoire ; le tag `tenant`
# de chaque mail désigne le schéma client où ranger l'événement.
@app.get("/api/public/mm/resend/webhook")
def webhook_resend_sante():
    """Pour la surveillance (HetrixTools) : l'endpoint répond et son secret est en place.
    Les vrais événements arrivent en POST signé."""
    from jobs import resend_webhook
    return {"ok": True, "secret": bool(resend_webhook._secret())}


@app.post("/api/public/mm/resend/webhook")
async def webhook_resend(request: Request):
    from jobs import resend_webhook
    brut = await request.body()
    h = request.headers
    if not resend_webhook.signature_valide(brut, h.get("svix-id", ""), h.get("svix-timestamp", ""),
                                           h.get("svix-signature", "")):
        return JSONResponse({"ok": False, "detail": "signature invalide"}, status_code=401)
    try:
        evenement = json.loads(brut)
    except ValueError:
        return JSONResponse({"ok": False, "detail": "corps illisible"}, status_code=400)
    return resend_webhook.traiter(evenement, h.get("svix-id", ""))


@app.get("/api/public/mass-mailing/sante")
def sante():
    return {"ok": True, "base": pg.sante(), "service": "mass-email"}


app.include_router(saas.router)
app.include_router(ab.router)
app.include_router(routes.router)
app.include_router(routes.public_router)

auth.appliquer_schema()
