#!/usr/bin/env python3
"""
api.py — Backend FastAPI pour le dashboard Genesis.
Agrège les données de Emdash, Emelia, CRM interne (DuckDB), pm2, orchestrateur.

Lancer: uvicorn scripts.api:app --host 127.0.0.1 --port 8080 --reload
        (127.0.0.1 : joignable seulement par Nginx en local — ne PAS exposer 8080 à Internet)
Ou:     python3 scripts/api.py
"""

import json
import sys
import subprocess
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from god_mode_api import router as god_mode_router
from auth_backend import login as auth_login, reset_password as auth_reset, send_password_telegram as auth_send_telegram, log_login as auth_log_login, get_login_logs as auth_get_logs, verify_session as auth_verify, logout as auth_logout, list_users as auth_list_users, create_user as auth_create_user, delete_user as auth_delete_user, update_user as auth_update_user, count_online_users as auth_count_online, list_online_users as auth_list_online
from emelia_campaign_manager import (
    get_sector_breakdown as emelia_sectors, get_prospects_by_sector as emelia_prospects,
    create_emelia_campaign as emelia_create, configure_steps as emelia_steps,
    configure_settings as emelia_settings, add_contact as emelia_add_contact,
    get_default_steps as emelia_default_steps, list_campaigns as emelia_list,
    get_campaign_stats as emelia_stats
)
# NB: anciens imports crm_backend (CRM/PRM legacy) supprimés le 2026-05-20.
# Toute la logique passe désormais par scripts/acquisition_backend.py.
import time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from editorial_api import (
    editorial_queue_get, editorial_queue_post, editorial_approve,
    editorial_reject, editorial_publish, editorial_revision,
    editorial_detail, editorial_patch
)
from scripts.health_check import check_all_sites
from typing import Any

import requests
from fastapi import FastAPI, Request, UploadFile, File
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR      = Path(__file__).parent.parent
ENV_FILE      = BASE_DIR / ".env"
DASHBOARD_DIR = BASE_DIR / "dashboard"
DATA_FILE     = BASE_DIR / "data" / "dashboard.json"
COSTS_FILE    = BASE_DIR / "memory" / "shared" / "costs-log.json"
SESSIONS_FILE = BASE_DIR / "memory" / "shared" / "agent-logs" / "sessions.jsonl"


def load_env() -> dict:
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _pool_conn():
    """Connexion au pool `contacts.duckdb`, via son propre connecteur.

    On conserve la préférence LECTURE SEULE ici — le pool pèse 1 Go et le scraping nocturne
    a besoin du verrou d'écriture — mais on passe par `contacts_pool_backend`, qui sait
    réessayer sur verrou ET basculer de configuration si une autre partie du process a déjà
    ouvert la base autrement.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import contacts_pool_backend as _pool
    return _pool._conn(read_only=True)


def _duck(chemin):
    """Ouvre une base DuckDB pour l'API. Voir `duck_ouverture` : dans ce process, tout le
    monde ouvre avec la MÊME configuration, sinon DuckDB refuse la seconde connexion."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from duck_ouverture import ouvrir
    return ouvrir(chemin)


app = FastAPI(title="Genesis Dashboard API", version="1.0")
app.include_router(god_mode_router)


# ── Auth middleware sécurisé ──────────────────────────────────────────────────
# Politique :
#   - /api/auth/login, /api/auth/me, /api/auth/mfa/* en clair (le check est fait dans le handler)
#   - tout autre /api/* : Bearer (session token) obligatoire
#   - /api/auth/users (CRUD), /api/auth/users/{id}/* : role=admin obligatoire
#   - /webhook : token via query param, comparé à WEBHOOK_TOKEN_1/2 lus de .env
#   - Pas de bypass Referer/Origin (forgeable)

def _load_env_keys() -> dict:
    """Lecture paresseuse des tokens webhook depuis .env."""
    out = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip("'\"")
    return out

_AUTH_OPEN_PATHS = {
    "/api/auth/login", "/api/auth/me", "/api/auth/mfa/login",
    "/api/auth/mfa/setup-start", "/api/auth/mfa/setup-confirm",
    # État de maintenance : lu par la page de login AVANT toute authentification. En lecture
    # seule, sans donnée sensible (un booléen et un message d'accueil).
    "/api/maintenance",
}
# Préfixes ouverts SANS authentification. La plaquette est un document commercial destiné
# à des prospects qui n'ont évidemment pas de compte : le lien de l'email doit s'ouvrir.
# Elle est ENGENDRÉE à la volée depuis `argumentaire.py` et ne contient aucune donnée de
# la base — ni contact, ni chiffre, ni nom de client.
_AUTH_OPEN_PREFIXES = ("/api/public/",)
_ADMIN_PREFIXES = ("/api/auth/users", "/api/auth/logs", "/api/enrichment/run",
                   "/api/admin/maintenance", "/api/admin/database",
                   "/api/admin/secteurs")

# Codes site connus (isolation multi-tenant). Chargé une fois depuis le registre, fallback statique.
_KNOWN_SITE_CODES: set | None = None


def _known_site_codes() -> set:
    global _KNOWN_SITE_CODES
    if _KNOWN_SITE_CODES is None:
        try:
            from scripts.sites_config import load_all_sites
            _KNOWN_SITE_CODES = set(load_all_sites().keys()) or {"lcr", "mkd", "tst"}
        except Exception:
            _KNOWN_SITE_CODES = {"lcr", "mkd", "tst"}
    return _KNOWN_SITE_CODES


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Routes non-API : passent (servies par Nginx/Next.js de toute façon)
    if not path.startswith("/api/"):
        return await call_next(request)

    # Webhooks : token via query param uniquement
    if "/webhook" in path:
        env_keys = _load_env_keys()
        allowed = {env_keys.get(k, "") for k in ("WEBHOOK_TOKEN_1", "WEBHOOK_TOKEN_2")} - {""}
        token = request.query_params.get("token", "")
        if token and token in allowed:
            return await call_next(request)
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"error": "webhook token invalid"})

    # Routes d'auth publiques (handler valide les credentials)
    if any(path.startswith(pref) for pref in _AUTH_OPEN_PREFIXES):
        return await call_next(request)

    if path in _AUTH_OPEN_PATHS:
        return await call_next(request)

    # Tracking de clic public : le lien est dans un email (pas de session). La sécurité
    # vient du token aléatoire dans l'URL. L'endpoint ne fait qu'enregistrer + rediriger.
    if path == "/api/sweego/click":
        return await call_next(request)

    # Pixel de tracking d'ouverture (public — chargé par les clients mail)
    if path == "/api/track/open":
        return await call_next(request)

    # Prise de RDV publique (type Calendly) : page + créneaux + soumission. Pas de session
    # (lien public partagé). Les handlers valident le site + le créneau ; aucune donnée
    # sensible n'est exposée (lecture seule des créneaux, écriture d'un RDV uniquement).
    if path.startswith("/api/book/"):
        return await call_next(request)

    # Endpoints de test interne loopback-only (dryrun non destructif + test-batch run synchrone)
    if path.endswith("/cleanup/dryrun") or path.endswith("/cleanup/test-batch"):
        client_host = (request.client.host if request.client else "")
        if client_host in ("127.0.0.1", "::1", "localhost"):
            return await call_next(request)

    # Sinon : Bearer session token obligatoire
    bearer = request.headers.get("authorization", "")
    token = bearer[7:] if bearer.startswith("Bearer ") else ""
    sess = auth_verify(token) if token else None
    if not sess:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"error": "Bearer token required"})

    # Rôles disposant de tous les accès (bypass admin-only + isolation site)
    _SUPER = ("admin", "superadmin")

    # Endpoints admin-only (gestion users / logs)
    if any(path.startswith(p) for p in _ADMIN_PREFIXES) and sess.get("role") not in _SUPER:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={"error": "admin role required"})

    # Isolation multi-tenant GÉNÉRALE : un user n'accède qu'à SES sites (superadmin = tous).
    # On détecte un code site dans N'IMPORTE quel segment d'URL OU le query param `site`,
    # pas seulement /api/sites/{site}/* — sinon /api/crm/{site}, /api/dashboard/{site},
    # /api/seo-ahrefs/{site}, /api/agents/{site}/*, etc. fuitent les données d'un autre client.
    if sess.get("role") not in _SUPER:
        codes = _known_site_codes()
        user_sites = set(sess.get("sites") or [])
        seen = {seg for seg in path.split("/") if seg in codes}
        q_site = request.query_params.get("site")
        if q_site and q_site in codes:
            seen.add(q_site)
        forbidden = sorted(seen - user_sites)
        if forbidden:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403,
                content={"error": f"access denied for site '{forbidden[0]}'"})

    # ── Bêtas fermées : réservées à des comptes nommés ────────────────────────
    # Contrôlé sur le COMPTE et non sur le rôle, et AVANT la matrice : « réservé à mes
    # tests » ne veut rien dire si tous les superadmins y ont accès. Le superadmin est
    # exempté de la matrice de rôles ; il ne l'est pas d'une bêta.
    try:
        _chemin_scripts = str(BASE_DIR / "scripts")
        if _chemin_scripts not in sys.path:
            sys.path.insert(0, _chemin_scripts)
        import roles_backend as rbk_beta
        refus_beta = rbk_beta.beta_interdite(path, sess.get("username") or "",
                                             next((seg for seg in path.split("/")
                                                   if seg in _known_site_codes()), None))
        if refus_beta:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={
                "error": "fonctionnalité en test",
                "detail": f"« {refus_beta} » est en bêta fermée, réservée aux comptes de "
                          f"test. Elle sera ouverte quand elle sera prête.",
                "page": refus_beta, "beta": True})
    except Exception as e:  # noqa: BLE001
        print(f"[api] contrôle des bêtas inopérant ({type(e).__name__}: {e}) — "
              f"accès laissé passer sur {path}", flush=True)

    # ── Droits par rôle : la matrice page → routes ────────────────────────────
    # C'est ICI que se joue l'interdiction, pas dans le menu. Le rôle vient de la SESSION
    # vérifiée côté serveur ; ce que le navigateur raconte de son rôle n'a aucun effet.
    # Quelqu'un qui réécrit `localStorage` verra peut-être un menu réapparaître, mais les
    # routes qui l'alimentent répondront 403 : une page sans données est une page vide.
    #
    # `superadmin` n'est jamais filtré (cf. `roles_backend`, règle 1). Et si la matrice est
    # illisible, on laisse passer : couper la plateforme sur une panne de base serait un
    # déni de service qu'on se serait infligé (règle 3).
    # `_SUPER` vaut ("admin", "superadmin") — il sert à l'isolation multi-tenant, où admin
    # et superadmin voient bien tous les sites. Mais la MATRICE DES DROITS, elle, n'exempte
    # QUE le superadmin (règle 1 de `roles_backend`) : le rôle `admin` est configurable
    # depuis /admin/users/roles, et la case décochée doit avoir un effet. En réutilisant
    # `_SUPER` ici, on rendait ce réglage décoratif — la case se cochait, se sauvegardait,
    # s'affichait, et la route répondait quand même.
    if sess.get("role") != "superadmin":
        try:
            sys.path.insert(0, str(BASE_DIR / "scripts"))
            import roles_backend as rbk
            codes = _known_site_codes()
            site_vu = next((seg for seg in path.split("/") if seg in codes), None)
            refus = rbk.route_interdite(path, sess.get("role") or "", site_vu)
            if refus:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=403, content={
                    "error": "accès refusé",
                    "detail": f"Votre rôle n'a pas accès à « {refus} ».",
                    "page": refus})
        except Exception as e:  # noqa: BLE001
            # Laisser passer sur panne de la matrice reste la bonne règle (couper la
            # plateforme serait un déni de service qu'on s'infligerait). Mais le faire en
            # SILENCE, c'est désactiver toutes les permissions sans que personne ne le
            # sache — le pire des deux mondes. On laisse passer, et on le crie.
            print(f"[api] MATRICE DES DROITS INOPÉRANTE ({type(e).__name__}: {e}) — "
                  f"accès laissé passer pour le rôle {sess.get('role')!r} sur {path}",
                  flush=True)

    # Attache la session au request pour les handlers
    request.state.session = sess
    return await call_next(request)


# ── Cheffer Telegram Bot ──────────────────────────────────────────────────────
def send_cheffer_telegram(message):
    """Send message via Cheffer bot."""
    import os
    bot_token = os.environ.get("CHEFFER_TELEGRAM_BOT", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        return False
    try:
        requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        return True
    except:
        return False

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir les assets statiques du dashboard
if (DASHBOARD_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(DASHBOARD_DIR / "assets")), name="assets")


# ── Root ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=FileResponse)
def root():
    return FileResponse(str(DASHBOARD_DIR / "index.html"))


# ── /api/runs ─────────────────────────────────────────────────────────────────

@app.get("/api/runs")
def get_runs():
    if not DATA_FILE.exists():
        return {"runs": [], "error": "dashboard.json not found"}
    data = json.loads(DATA_FILE.read_text())
    runs = data.get("runs", [])
    return {"runs": runs[-50:], "total": len(runs)}


# ── /api/campaigns ────────────────────────────────────────────────────────────

@app.get("/api/campaigns")
def get_campaigns(request: Request):
    try:
        env = load_env()
        key = env.get("EMELIA_API_KEY", "")

        query = """{ campaigns { _id name status createdAt } }"""
        resp = requests.post(
            "https://api.emelia.io/graphql",
            headers={"Authorization": key, "Content-Type": "application/json"},
            json={"query": query},
            timeout=10,
        )
        campaigns = resp.json().get("data", {}).get("campaigns", [])

        # Stats par campagne
        enriched = []
        for c in campaigns:
            stats_q = f"""{{
                contacts(query: "campaignId:{c['_id']}") {{ _id status }}
            }}"""
            sr = requests.post(
                "https://api.emelia.io/graphql",
                headers={"Authorization": key, "Content-Type": "application/json"},
                json={"query": stats_q},
                timeout=8,
            )
            contacts = sr.json().get("data", {}).get("contacts", [])
            total    = len(contacts)
            replied  = sum(1 for x in contacts if x.get("status") == "REPLIED")
            bounced  = sum(1 for x in contacts if x.get("status") == "BOUNCED")
            enriched.append({
                **c,
                "total":       total,
                "replied":     replied,
                "bounced":     bounced,
                "replyRate":   round(replied / total * 100, 1) if total else 0,
                "bounceRate":  round(bounced / total * 100, 1) if total else 0,
            })
        # Isolation : un non-superadmin ne voit que les campagnes de SON site (convention de
        # nommage `lcr-…` / `mkd-…`). Les campagnes non préfixées par un de ses sites sont masquées.
        sess = getattr(request.state, "session", None)
        if sess and sess.get("role") not in ("admin", "superadmin"):
            user_sites = [s.lower() for s in (sess.get("sites") or [])]
            enriched = [c for c in enriched
                        if any((c.get("name") or "").lower().startswith(s) for s in user_sites)]
        return {"campaigns": enriched}
    except Exception as e:
        return {"campaigns": [], "error": str(e)}


# ── /api/admin/superadmin-bar (barre superadmin temps réel) ─────────────────────
_SB_CACHE = {"ts": 0.0, "routing": 0}

@app.get("/api/admin/superadmin-bar")
async def api_superadmin_bar(request: Request):
    """Stats pour la top bar superadmin : IP de connexion, users connectés, campagnes en routage."""
    sess = getattr(request.state, "session", None)
    if not sess or sess.get("role") not in ("admin", "superadmin"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={"error": "superadmin only"})

    # Même source d'IP que partout : celle que pose Nginx, pas la première valeur d'un
    # en-tête que le client contrôle. Ici c'est cosmétique (l'IP affichée dans la barre),
    # mais afficher une IP falsifiée induirait en erreur qui la lit.
    ip = _real_ip(request)

    try:
        users_online = auth_count_online()
        try:
            users_online_list = auth_list_online()
        except Exception:  # noqa: BLE001 — le détail est un confort, le compteur est l'essentiel
            users_online_list = []
    except Exception:
        users_online = 0
        users_online_list = []

    import time as _t, os as _os
    routing = _SB_CACHE["routing"]
    if _t.time() - _SB_CACHE["ts"] > 60:  # cache 60s — évite de spammer Emelia à chaque poll
        try:
            key = _os.environ.get("EMELIA_API_KEY", "") or load_env().get("EMELIA_API_KEY", "")
            r = requests.post("https://api.emelia.io/graphql",
                              headers={"Authorization": key, "Content-Type": "application/json"},
                              json={"query": "{ campaigns { status } }"}, timeout=8)
            camps = r.json().get("data", {}).get("campaigns", []) or []
            routing = sum(1 for c in camps if str(c.get("status", "")).upper() in ("RUNNING", "STARTED", "ONGOING", "SENDING"))
            _SB_CACHE.update(ts=_t.time(), routing=routing)
        except Exception:
            pass

    return {"ok": True, "ip": ip, "users_online": users_online,
            "users_online_list": users_online_list, "campaigns_routing": routing}


# ── /api/articles ─────────────────────────────────────────────────────────────

@app.get("/api/articles")
def get_articles():
    articles = []
    try:
        env = load_env()

        # LCR — Emdash
        r = requests.get(
            "http://localhost:4321/_emdash/api/content/posts?limit=10",
            headers={"Authorization": f"Bearer {env['EMDASH_API_TOKEN']}"},
            timeout=5,
        )
        for item in r.json().get("data", {}).get("items", []):
            articles.append({
                "site":   "LCR",
                "slug":   item["slug"],
                "title":  item["data"].get("title", item["slug"]),
                "status": item["status"],
                "url":    f"https://blog.leclientroi.com/posts/{item['slug']}",
                "date":   item.get("updatedAt") or item.get("createdAt", ""),
            })
    except Exception as e:
        articles.append({"site": "LCR", "error": str(e)})

    try:
        # MKD — WordPress
        env = load_env()
        import base64
        auth = base64.b64encode(
            f"{env['WP_USERNAME']}:{env['WP_APP_PASSWORD']}".encode()
        ).decode()
        r = requests.get(
            f"{env['WP_SITE_URL']}/wp-json/wp/v2/posts?per_page=5&status=publish",
            headers={"Authorization": f"Basic {auth}"},
            timeout=8,
        )
        for item in r.json():
            articles.append({
                "site":   "MKD",
                "slug":   item.get("slug", ""),
                "title":  item.get("title", {}).get("rendered", ""),
                "status": "published",
                "url":    item.get("link", ""),
                "date":   item.get("date", ""),
            })
    except Exception as e:
        articles.append({"site": "MKD", "error": str(e)})

    return {"articles": articles}


# ── /api/crm ──────────────────────────────────────────────────────────────────

@app.get("/api/crm")
def get_crm():
    """Vue agrégée du CRM interne (DuckDB) — somme des contacts LCR + MKD.
    L'ancien endpoint pointait sur Twenty CRM (supprimé le 2026-05-20)."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(BASE_DIR))
        from scripts.crm_backend import list_contacts as _list_contacts

        lcr = _list_contacts("lcr", limit=10)
        mkd = _list_contacts("mkd", limit=10)
        sync_log = {}
        sync_path = BASE_DIR / "memory" / "shared" / "crm-sync-log.json"
        if sync_path.exists():
            try:
                sync_log = json.loads(sync_path.read_text())
            except Exception:
                sync_log = {}
        synced_count = len(sync_log) if isinstance(sync_log, list) else len(sync_log.get("synced", {}))

        return {
            "total":    len(lcr) + len(mkd),
            "contacts": (lcr + mkd)[:10],
            "synced":   synced_count,
        }
    except Exception as e:
        return {"total": 0, "error": str(e)}


# ── /api/budget ───────────────────────────────────────────────────────────────

LEADS_LOG = BASE_DIR / "data" / "leads-log.json"

@app.get("/api/budget")
def get_budget(request: Request, site: str = ""):
    import sys
    sys.path.insert(0, str(BASE_DIR))
    from scripts.cost_tracker import get_summary, PRICING

    # Isolation : un non-superadmin ne voit QUE le budget de son site (il en a exactement 1).
    sess = getattr(request.state, "session", None)
    if sess and sess.get("role") not in ("admin", "superadmin"):
        user_sites = sess.get("sites") or []
        if user_sites:
            site = user_sites[0]

    try:
        week  = get_summary(7)
        month = get_summary(30)
        all_  = get_summary(3650)

        # Filtrer par site si demandé (reconstruit by_module / by_model / by_site)
        if site:
            for summary in (week, month, all_):
                filtered = [e for e in summary["entries"] if e.get("site", "") == site]
                summary["entries"]   = filtered
                summary["total_usd"] = round(sum(e.get("cost_usd", 0) for e in filtered), 4)
                summary["total_eur"] = round(sum(e.get("cost_eur", 0) for e in filtered), 4)
                summary["total_tok"] = sum(e.get("total_tok", 0) for e in filtered)
                by_mod, by_mdl = {}, {}
                for e in filtered:
                    m = e.get("module", "unknown")
                    by_mod.setdefault(m, {"usd": 0, "eur": 0, "tok": 0, "calls": 0})
                    by_mod[m]["usd"] += e.get("cost_usd", 0); by_mod[m]["eur"] += e.get("cost_eur", 0)
                    by_mod[m]["tok"] += e.get("total_tok", 0); by_mod[m]["calls"] += 1
                    mdl = e.get("model", "unknown")
                    by_mdl.setdefault(mdl, {"usd": 0, "eur": 0, "tok": 0, "calls": 0})
                    by_mdl[mdl]["usd"] += e.get("cost_usd", 0); by_mdl[mdl]["eur"] += e.get("cost_eur", 0)
                    by_mdl[mdl]["tok"] += e.get("total_tok", 0); by_mdl[mdl]["calls"] += 1
                summary["by_module"] = by_mod
                summary["by_model"]  = by_mdl
                summary["by_site"]   = {site: {"eur": summary["total_eur"], "tok": summary["total_tok"], "usd": summary["total_usd"], "calls": len(filtered)}}

        # Budget hebdo max = 10 USD
        budget_usd = 10.0
        week_pct   = min(100, round((week["total_usd"] / budget_usd) * 100, 1))

        # Top 5 actions les plus coûteuses (7 jours)
        by_action: dict = {}
        for e in week["entries"]:
            a = e.get("action", "")
            by_action.setdefault(a, {"action": a, "module": e.get("module", ""), "site": e.get("site", ""), "calls": 0, "cost_eur": 0, "tok": 0})
            by_action[a]["calls"] += 1
            by_action[a]["cost_eur"] = round(by_action[a]["cost_eur"] + e.get("cost_eur", 0), 6)
            by_action[a]["tok"] += e.get("total_tok", 0)
        top5 = sorted(by_action.values(), key=lambda x: -x["cost_eur"])[:5]

        return {
            "week":      week,
            "month":     month,
            "all":       all_,
            "budgetUsd": budget_usd,
            "budgetEur": round(budget_usd * 0.92, 2),
            "weekPct":   week_pct,
            "top5":      top5,
            "pricing":   PRICING,
        }
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/budget/entry")
def delete_budget_entry(timestamp: str):
    if not COSTS_FILE.exists():
        return {"error": "no file"}
    entries = json.loads(COSTS_FILE.read_text())
    if not isinstance(entries, list):
        return {"error": "invalid format"}
    entries = [e for e in entries if e.get("timestamp") != timestamp]
    COSTS_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2))
    return {"ok": True, "remaining": len(entries)}


# ── /api/system ───────────────────────────────────────────────────────────────

# Processus cron Genesis — s'arrêtent intentionnellement après exécution
CRON_PROCESSES = {"genesis-briefing", "genesis-crm-sync", "genesis-campaign-status"}

@app.get("/api/system")
def get_system():
    processes = []

    # Derniers runs par module (pour afficher "last run" sur les crons)
    last_runs: dict = {}
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text())
        for run in data.get("runs", []):
            mod = run.get("module", "")
            last_runs[mod] = run  # on garde le plus récent (dernier dans la liste)

    MODULE_MAP = {
        "genesis-briefing":        "briefing",
        "genesis-crm-sync":        "crm_sync",
        "genesis-campaign-status": "campaigns",
    }

    try:
        result = subprocess.run(
            ["pm2", "jlist"], capture_output=True, text=True, timeout=5
        )
        pm2_list = json.loads(result.stdout)
        for p in pm2_list:
            name   = p.get("name")
            status = p.get("pm2_env", {}).get("status", "unknown")
            is_cron = name in CRON_PROCESSES

            last_run = None
            if is_cron:
                mod_key = MODULE_MAP.get(name)
                run = last_runs.get(mod_key)
                if run:
                    last_run = run.get("date")

            processes.append({
                "name":     name,
                "status":   status,
                "isCron":   is_cron,
                "lastRun":  last_run,
                "uptime":   p.get("pm2_env", {}).get("pm_uptime"),
                "memory":   p.get("monit", {}).get("memory", 0),
                "cpu":      p.get("monit", {}).get("cpu", 0),
            })
    except Exception as e:
        processes = [{"error": str(e)}]

    return {
        "processes":  processes,
        "serverTime": datetime.now(timezone.utc).isoformat(),
    }


# ── /api/status (agrégé) ──────────────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    """Endpoint principal — tout en un pour le dashboard."""
    data = json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}
    meta = data.get("meta", {})
    runs = data.get("runs", [])

    # Derniers runs par module
    last_runs: dict[str, Any] = {}
    for run in runs:
        mod = run.get("module", "unknown")
        if mod not in last_runs:
            last_runs[mod] = run

    return {
        "meta":      meta,
        "lastRuns":  last_runs,
        "runCount":  len(runs),
        "recentRuns": runs[-5:],
        "serverTime": datetime.now(timezone.utc).isoformat(),
    }


# ── /api/services ─────────────────────────────────────────────────────────────

SERVICES_DEF = [
    {"id": "genesis-dashboard",       "label": "Dashboard API",      "type": "service", "cron": None,            "module": None},
    {"id": "genesis-briefing",        "label": "Briefing quotidien", "type": "cron",    "cron": "0 7 * * *",     "module": "briefing"},
    {"id": "genesis-crm-sync",        "label": "Sync CRM",           "type": "cron",    "cron": "0 8 * * 1-5",   "module": "crm_sync"},
    {"id": "genesis-campaign-status", "label": "Statut campagnes",   "type": "cron",    "cron": "0 9 * * 1",     "module": "campaigns"},
    {"id": "paperclip",               "label": "Paperclip (legacy)", "type": "service", "cron": None,            "module": None},
    {"id": "emdashcms",               "label": "Emdash CMS (LCR)",   "type": "service", "cron": None,            "module": None},
]

def send_telegram_alert(message: str, env: dict):
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=5,
        )
    except Exception:
        pass


@app.get("/api/services")
def get_services():
    now = datetime.now(timezone.utc)
    env = load_env()

    # pm2 status
    pm2_status: dict = {}
    try:
        result = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=5)
        for p in json.loads(result.stdout):
            pm2_status[p["name"]] = {
                "status": p.get("pm2_env", {}).get("status", "unknown"),
                "uptime": p.get("pm2_env", {}).get("pm_uptime"),
                "memory": p.get("monit", {}).get("memory", 0),
                "cpu":    p.get("monit", {}).get("cpu", 0),
                "restarts": p.get("pm2_env", {}).get("restart_time", 0),
            }
    except Exception:
        pass

    # Derniers runs par module
    last_runs: dict = {}
    if DATA_FILE.exists():
        for run in json.loads(DATA_FILE.read_text()).get("runs", []):
            last_runs[run.get("module", "")] = run

    alerts_sent = []
    services = []

    for svc in SERVICES_DEF:
        pm2 = pm2_status.get(svc["id"], {})
        pm2_live = pm2.get("status") == "online"

        last_run_date = None
        last_run_status = None
        hours_since = None
        overdue = False

        if svc["module"] and svc["module"] in last_runs:
            run = last_runs[svc["module"]]
            last_run_date = run.get("date")
            last_run_status = run.get("status")
            if last_run_date:
                dt = datetime.fromisoformat(last_run_date.replace("Z", "+00:00"))
                hours_since = round((now - dt).total_seconds() / 3600, 1)
                overdue = hours_since > 24

        # Service permanent → alerte si pm2 offline
        if svc["type"] == "service" and not pm2_live and svc["id"] not in ("paperclip", "emdashcms", "lcr-webhook"):
            overdue = True

        if overdue:
            msg = f"⚠️ *Genesis Alert*\n`{svc['label']}` — "
            if svc["type"] == "cron":
                msg += f"pas de run depuis *{hours_since}h* (>{24}h attendu)"
            else:
                msg += f"service *hors ligne* (pm2 status: {pm2.get('status','?')})"
            send_telegram_alert(msg, env)
            alerts_sent.append(svc["id"])

        # Déterminer l'état affiché
        if svc["type"] == "service":
            display_status = "online" if pm2_live else "offline"
        else:
            # Cron : on regarde le dernier run
            if not last_run_date:
                display_status = "never"
            elif overdue:
                display_status = "overdue"
            else:
                display_status = "ok"

        services.append({
            "id":            svc["id"],
            "label":         svc["label"],
            "type":          svc["type"],
            "cron":          svc["cron"],
            "pm2Status":     pm2.get("status"),
            "pm2Live":       pm2_live,
            "displayStatus": display_status,
            "lastRunDate":   last_run_date,
            "lastRunStatus": last_run_status,
            "hoursSince":    hours_since,
            "overdue":       overdue,
            "memory":        pm2.get("memory", 0),
            "restarts":      pm2.get("restarts", 0),
        })

    return {
        "services":    services,
        "alerts":      alerts_sent,
        "checkedAt":   now.isoformat(),
    }


# ── /api/connectors ───────────────────────────────────────────────────────────

@app.get("/api/connectors")
def get_connectors(request: Request):
    """Vérifie la disponibilité de chaque connecteur, filtré par les sites de l'utilisateur."""
    env = load_env()
    results = {}

    # Emdash (LCR CMS)
    emdash_token = env.get("EMDASH_API_TOKEN", "")
    emdash_url   = env.get("EMDASH_API_URL", "http://localhost:4321/_emdash/api").rstrip("/")
    emdash_ok    = False
    if emdash_token:
        try:
            r = requests.get(f"{emdash_url}/content/posts?limit=1",
                             headers={"Authorization": f"Bearer {emdash_token}"}, timeout=2)
            emdash_ok = r.status_code < 400
        except Exception:
            pass
    results["emdash"] = {"ok": emdash_ok, "label": "Emdash CMS (LCR)", "key_set": bool(emdash_token), "env_var": "EMDASH_API_TOKEN"}

    # WordPress (MKD)
    wp_url  = env.get("WP_SITE_URL", "")
    wp_user = env.get("WP_USERNAME", "")
    wp_pass = env.get("WP_APP_PASSWORD", "")
    wp_ok   = False
    if wp_url and wp_user and wp_pass:
        try:
            import base64
            creds = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
            r = requests.get(f"{wp_url}/wp-json/wp/v2/posts?per_page=1",
                             headers={"Authorization": f"Basic {creds}"}, timeout=4)
            wp_ok = r.status_code < 400
        except Exception:
            pass
    results["wordpress"] = {"ok": wp_ok, "label": "WordPress (MKD)", "key_set": bool(wp_url and wp_user and wp_pass), "env_var": "WP_SITE_URL + WP_USERNAME + WP_APP_PASSWORD"}

    # Ahrefs
    ahrefs_key = env.get("AHREFS_API_KEY", "")
    results["ahrefs"] = {"ok": bool(ahrefs_key), "label": "Ahrefs API", "key_set": bool(ahrefs_key), "env_var": "AHREFS_API_KEY"}

    # Telegram
    tg_token = env.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat  = env.get("TELEGRAM_CHAT_ID", "")
    results["telegram"] = {"ok": bool(tg_token and tg_chat), "label": "Telegram Bot", "key_set": bool(tg_token and tg_chat), "env_var": "TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID"}

    # Emelia
    emelia_key = env.get("EMELIA_API_KEY", "")
    results["emelia"] = {"ok": bool(emelia_key), "label": "Emelia (cold email)", "key_set": bool(emelia_key), "env_var": "EMELIA_API_KEY"}

    # CRM interne (DuckDB) — toujours OK, pas de clé externe
    try:
        crm_lcr_db = (BASE_DIR / "data" / "crm" / "lcr.duckdb").exists()
        crm_mkd_db = (BASE_DIR / "data" / "crm" / "mkd.duckdb").exists()
        results["crm_interne"] = {
            "ok": crm_lcr_db or crm_mkd_db,
            "label": "CRM interne (DuckDB)",
            "key_set": True,
            "env_var": "",
        }
    except Exception:
        results["crm_interne"] = {"ok": False, "label": "CRM interne (DuckDB)", "key_set": False, "env_var": ""}

    # DeepSeek
    ds_key = env.get("DEEPSEEK_API_KEY", "")
    results["deepseek"] = {"ok": bool(ds_key), "label": "DeepSeek API", "key_set": bool(ds_key), "env_var": "DEEPSEEK_API_KEY"}

    # Anthropic Claude
    claude_key = env.get("ANTHROPIC_API_KEY", "")
    results["claude"] = {"ok": bool(claude_key), "label": "Claude / Anthropic", "key_set": bool(claude_key), "env_var": "ANTHROPIC_API_KEY"}

    return _scope_connectors({"connectors": results, "checkedAt": datetime.now(timezone.utc).isoformat()}, request)


# ── /api/connectors/health — vrai ping live des APIs (cache 5 min) ────────────

CONNECTORS_HEALTH_CACHE = BASE_DIR / "memory" / "shared" / "connectors-health.json"
CONNECTORS_HEALTH_TTL_S = 5 * 60  # 5 minutes


def _ping_connector(name: str, env: dict) -> dict:
    """Ping un connecteur et retourne {status, latency_ms?, error?, kind}.
    Status : 'ok' | 'missing_key' | 'error' | 'key_only' | 'internal'
    """
    import time as _t
    now = _t.time()

    def _http(url, method="GET", headers=None, json_body=None, timeout=8.0, essais=2):
        """Un appel, avec une seconde chance sur incident réseau.

        Le délai était à 3 s : la toute première requête paie la poignée de main TLS
        (mesuré ~950 ms sur Ahrefs, 200 ms ensuite) et un pic chez le fournisseur
        suffisait à afficher une panne. Un dépassement de délai ne dit RIEN de la clé,
        donc on réessaie une fois avant de crier.
        """
        dernier = None
        for _ in range(max(1, essais)):
            t0 = _t.time()
            try:
                if method == "POST":
                    r = requests.post(url, headers=headers or {}, json=json_body, timeout=timeout)
                else:
                    r = requests.get(url, headers=headers or {}, timeout=timeout)
                return r.status_code, int((_t.time() - t0) * 1000), None
            except (requests.Timeout, requests.ConnectionError) as e:
                dernier = (0, int((_t.time() - t0) * 1000), str(e)[:200])
            except Exception as e:
                return 0, int((_t.time() - t0) * 1000), str(e)[:200]
        return dernier

    def _verdict(code, ms, err, kind="external", note=None):
        """Traduit un ping en statut ET en cause.

        Une clé refusée et un réseau qui traîne n'appellent pas la même action : sans
        cette distinction l'écran envoyait vérifier une clé parfaitement valide.
        """
        if code == 200:
            out = {"status": "ok", "latency_ms": ms, "kind": kind}
        else:
            out = {"status": "error", "latency_ms": ms, "kind": kind,
                   "raison": "cle" if code in (401, 403) else "service" if code else "reseau",
                   "error": err or f"HTTP {code}"}
        if note:
            out["note"] = note
        return out

    if name == "deepseek":
        key = env.get("DEEPSEEK_API_KEY", "")
        if not key: return {"status": "missing_key", "kind": "external"}
        code, ms, err = _http("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {key}"})
        return _verdict(code, ms, err)

    if name == "ahrefs":
        key = env.get("AHREFS_API_KEY", "")
        if not key: return {"status": "missing_key", "kind": "external"}
        code, ms, err = _http("https://api.ahrefs.com/v3/subscription-info/limits-and-usage", headers={"Authorization": f"Bearer {key}"})
        return _verdict(code, ms, err)

    if name == "emelia":
        # On utilise la clé globale pour le check générique (sinon serait par site)
        key = env.get("EMELIA_API_KEY", "")
        # Fallback : si pas de globale, prend la 1re clé site dispo
        if not key:
            for s in ("LCR", "MKD"):
                key = env.get(f"EMELIA_API_KEY_{s}", "")
                if key: break
        if not key: return {"status": "missing_key", "kind": "external"}
        code, ms, err = _http("https://api.emelia.io/graphql", method="POST",
                              headers={"Authorization": key, "Content-Type": "application/json"},
                              json_body={"query": "{ campaigns { _id } }"})
        return _verdict(code, ms, err)

    if name == "telegram":
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        if not token: return {"status": "missing_key", "kind": "external"}
        code, ms, err = _http(f"https://api.telegram.org/bot{token}/getMe", timeout=4.0)
        return _verdict(code, ms, err)

    if name == "emdash":
        token = env.get("EMDASH_API_TOKEN", "")
        if not token: return {"status": "missing_key", "kind": "external"}
        url = env.get("EMDASH_API_URL", "http://localhost:4321/_emdash/api").rstrip("/")
        code, ms, err = _http(f"{url}/content/posts?limit=1", headers={"Authorization": f"Bearer {token}"}, timeout=2.0)
        return _verdict(code, ms, err)

    if name == "wordpress":
        wp_url = env.get("WP_SITE_URL", "")
        wp_user = env.get("WP_USERNAME", "")
        wp_pass = env.get("WP_APP_PASSWORD", "")
        if not (wp_url and wp_user and wp_pass): return {"status": "missing_key", "kind": "external"}
        import base64
        creds = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
        code, ms, err = _http(f"{wp_url}/wp-json/wp/v2/posts?per_page=1", headers={"Authorization": f"Basic {creds}"}, timeout=4.0)
        return _verdict(code, ms, err)

    if name == "serper":
        # Pas de ping live (chaque appel = 1 crédit payant)
        key = env.get("SERPER_API_KEY", "")
        return {"status": "key_only" if key else "missing_key", "kind": "external", "note": "ping désactivé (coût crédit)"}

    if name == "unsplash":
        # Idem, quota limité, pas de ping live
        key = env.get("UNSPLASH_LCR_ACCESS_KEY", "") or env.get("UNSPLASH_MKD_ACCESS_KEY", "")
        return {"status": "key_only" if key else "missing_key", "kind": "external", "note": "ping désactivé (quota)"}

    if name == "crm_interne":
        ok = (BASE_DIR / "data" / "crm" / "lcr.duckdb").exists() or (BASE_DIR / "data" / "crm" / "mkd.duckdb").exists()
        return {"status": "ok" if ok else "error", "kind": "internal"}

    if name == "acquisition_db":
        return {"status": "ok", "kind": "internal"}

    return {"status": "missing_key", "kind": "external"}


# Connecteurs propres à un site (les autres sont mutualisés). Sert à l'isolation multi-tenant.
_CONNECTOR_SITE = {"emdash": "lcr", "wordpress": "mkd", "tally_lcr": "lcr", "tally_mkd": "mkd"}


def _scope_connectors(payload: dict, request) -> dict:
    """Masque les connecteurs d'un site auquel l'utilisateur n'a pas accès (superadmin = tout)."""
    sess = getattr(getattr(request, "state", None), "session", None)
    if not sess or sess.get("role") in ("admin", "superadmin"):
        return payload
    sites = set(sess.get("sites") or [])
    conns = payload.get("connectors") or {}
    out = dict(payload)
    out["connectors"] = {n: v for n, v in conns.items()
                         if _CONNECTOR_SITE.get(n) is None or _CONNECTOR_SITE[n] in sites}
    return out


@app.get("/api/connectors/health")
def api_connectors_health(request: Request, force: bool = False):
    """Retourne le statut santé live de tous les connecteurs (cache 5 min), filtré par les sites de l'utilisateur."""
    import time as _t
    # Cache hit ?
    if not force and CONNECTORS_HEALTH_CACHE.exists():
        try:
            cached = json.loads(CONNECTORS_HEALTH_CACHE.read_text())
            age = _t.time() - cached.get("_ts", 0)
            if age < CONNECTORS_HEALTH_TTL_S:
                cached["_cache_age_s"] = int(age)
                return _scope_connectors(cached, request)
        except Exception:
            pass

    # Ping tout
    env = load_env()
    connectors = ["deepseek", "ahrefs", "emelia", "telegram", "emdash", "wordpress", "serper", "unsplash", "crm_interne", "acquisition_db"]
    # De front, pas en file indienne : 10 connecteurs × (8 s × 2 essais) en séquence
    # feraient attendre l'écran deux minutes. En parallèle, le tout coûte le plus lent.
    from concurrent.futures import ThreadPoolExecutor

    def _sonder(name: str) -> tuple[str, dict]:
        try:
            return name, _ping_connector(name, env)
        except Exception as e:
            return name, {"status": "error", "kind": "external", "error": str(e)[:200]}

    with ThreadPoolExecutor(max_workers=len(connectors)) as pool:
        results = dict(pool.map(_sonder, connectors))

    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "_ts":        _t.time(),
        "_cache_age_s": 0,
        "connectors": results,
    }
    try:
        CONNECTORS_HEALTH_CACHE.parent.mkdir(parents=True, exist_ok=True)
        CONNECTORS_HEALTH_CACHE.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    except Exception:
        pass
    return _scope_connectors(payload, request)


# ── /api/site/{site} ──────────────────────────────────────────────────────────

SITE_MODULES = {
    "lcr": ["content", "briefing", "infographic"],
    "mkd": ["content", "crm_sync", "campaigns"],
}

@app.get("/api/site/{site}")
def get_site(site: str):
    import sys
    sys.path.insert(0, str(BASE_DIR))
    from scripts.cost_tracker import get_summary

    if site not in ("lcr", "mkd"):
        return {"error": "site inconnu"}

    env = load_env()
    articles = []
    runs_for_site = []

    # Articles
    try:
        if site == "lcr":
            r = requests.get(
                "http://localhost:4321/_emdash/api/content/posts?limit=20",
                headers={"Authorization": f"Bearer {env['EMDASH_API_TOKEN']}"},
                timeout=5,
            )
            for item in r.json().get("data", {}).get("items", []):
                articles.append({
                    "title":  item["data"].get("title", item["slug"]),
                    "slug":   item["slug"],
                    "status": item["status"],
                    "date":   item.get("updatedAt") or item.get("createdAt", ""),
                    "url":    f"https://blog.leclientroi.com/posts/{item['slug']}",
                })
        else:
            import base64
            auth = base64.b64encode(
                f"{env['WP_USERNAME']}:{env['WP_APP_PASSWORD']}".encode()
            ).decode()
            r = requests.get(
                f"{env['WP_SITE_URL']}/wp-json/wp/v2/posts?per_page=10&status=any",
                headers={"Authorization": f"Basic {auth}"},
                timeout=8,
            )
            for item in r.json():
                articles.append({
                    "title":  item.get("title", {}).get("rendered", ""),
                    "slug":   item.get("slug", ""),
                    "status": item.get("status", ""),
                    "date":   item.get("date", ""),
                    "url":    item.get("link", ""),
                })
    except Exception as e:
        articles = [{"error": str(e)}]

    # Runs filtrés par modules du site
    if DATA_FILE.exists():
        all_runs = json.loads(DATA_FILE.read_text()).get("runs", [])
        site_modules = SITE_MODULES.get(site, [])
        runs_for_site = [r for r in all_runs if r.get("module") in site_modules][-20:]

    # Coûts filtrés par modules du site
    all_costs = get_summary(7)
    site_modules = SITE_MODULES.get(site, [])
    site_cost_eur = sum(
        v["eur"] for m, v in all_costs["by_module"].items()
        if m in site_modules
    )
    site_entries = [
        e for e in all_costs["entries"]
        if e.get("module") in site_modules
    ]

    return {
        "site":        site,
        "articles":    articles,
        "runs":        runs_for_site,
        "costEur":     round(site_cost_eur, 4),
        "costEntries": site_entries,
    }


# ── /api/dashboard/{site} ─────────────────────────────────────────────────────

AGENT_DEFS = {
    "lcr": [
        {"module": "briefing",    "label": "Briefing Telegram",  "pm2": "genesis-briefing",         "cron": "0 7 * * *",    "max_hours": 25},
        {"module": "content",     "label": "Content Agent",      "pm2": None,                       "cron": "mer 10h",      "max_hours": 168},
        {"module": "seo",         "label": "Analyse SEO Ahrefs", "pm2": "genesis-seo",              "cron": "lun 6h UTC",   "max_hours": 170},
        {"module": "indexation",  "label": "Indexation Agent",   "pm2": "genesis-indexation",       "cron": "lun 6h30 UTC", "max_hours": 170},
        {"module": "infographic", "label": "Infographic Pillow", "pm2": None,                       "cron": "par article",  "max_hours": 500},
    ],
    "mkd": [
        {"module": "briefing",    "label": "Briefing Telegram",  "pm2": "genesis-briefing",         "cron": "0 7 * * *",    "max_hours": 25},
        {"module": "content",     "label": "Content Agent",      "pm2": None,                       "cron": "mer 10h",      "max_hours": 168},
        {"module": "crm_sync",    "label": "Sync CRM (Emelia→DuckDB)", "pm2": "genesis-crm-sync",   "cron": "lun-ven 8h",   "max_hours": 25},
        {"module": "campaigns",   "label": "Statut campagnes",   "pm2": "genesis-campaign-status",  "cron": "lun 9h UTC",   "max_hours": 170},
        {"module": "seo",         "label": "Analyse SEO Ahrefs", "pm2": "genesis-seo",              "cron": "lun 6h UTC",   "max_hours": 170},
    ],
}

# Note: Ahrefs subscription cost not tracked here — only API usage via cost_tracker

@app.get("/api/dashboard/{site}")
def get_site_dashboard(site: str):
    if site not in ("lcr", "mkd"):
        return {"error": "site inconnu"}

    import sys as _sys
    _sys.path.insert(0, str(BASE_DIR))
    from scripts.cost_tracker import get_summary

    now = datetime.now(timezone.utc)
    env = load_env()

    # ── SEO metrics (from cache) ──────────────────────────────────────────────
    seo_data = {}
    cache_file = BASE_DIR / "memory" / "seo" / f"{site}-latest.json"
    if cache_file.exists():
        try:
            seo_data = json.loads(cache_file.read_text())
        except Exception:
            pass
    seo = {
        "dr":         seo_data.get("domain_rating", 0),
        "traffic":    seo_data.get("org_traffic", 0),
        "keywords":   seo_data.get("org_keywords", 0),
        "checked_at": seo_data.get("date") or seo_data.get("checked_at", ""),
    }

    # ── Articles count ────────────────────────────────────────────────────────
    articles_count = 0
    try:
        if site == "lcr":
            r = requests.get(
                "http://localhost:4321/_emdash/api/content/posts?limit=1",
                headers={"Authorization": f"Bearer {env['EMDASH_API_TOKEN']}"},
                timeout=3,
            )
            d = r.json().get("data", {})
            articles_count = d.get("total", 0) or len(d.get("items", []))
        else:
            import base64 as _b64
            auth = _b64.b64encode(f"{env['WP_USERNAME']}:{env['WP_APP_PASSWORD']}".encode()).decode()
            r = requests.get(
                f"{env['WP_SITE_URL']}/wp-json/wp/v2/posts?per_page=1&status=publish",
                headers={"Authorization": f"Basic {auth}"},
                timeout=5,
            )
            articles_count = int(r.headers.get("X-WP-Total", 0))
    except Exception:
        pass

    # ── Indexation ────────────────────────────────────────────────────────────
    indexation = {"sitemap_count": 0, "published_count": 0, "missing_count": 0}
    idx_file = BASE_DIR / "memory" / "seo" / f"{site}-indexation-audit.json"
    if idx_file.exists():
        try:
            idx = json.loads(idx_file.read_text())
            indexation = {
                "sitemap_count":   idx.get("sitemap_count", 0),
                "published_count": idx.get("published_count", 0),
                "missing_count":   len(idx.get("missing_from_sitemap", [])),
            }
        except Exception:
            pass

    # ── Costs by provider ─────────────────────────────────────────────────────
    def _group_costs(entries):
        p = {
            "claude":   {"label": "Claude (Anthropic)",  "usd": 0.0, "calls": 0},
            "deepseek": {"label": "DeepSeek",            "usd": 0.0, "calls": 0},
            "ahrefs":   {"label": "Ahrefs",              "usd": 0.0, "calls": 0},
            "other":    {"label": "Autres",              "usd": 0.0, "calls": 0},
        }
        for e in entries:
            if e.get("site", "") not in (site, ""):
                continue
            model = e.get("model", "")
            cost  = e.get("cost_usd", 0)
            if model.startswith("claude-"):
                p["claude"]["usd"]   += cost; p["claude"]["calls"] += 1
            elif model.startswith("deepseek-"):
                p["deepseek"]["usd"] += cost; p["deepseek"]["calls"] += 1
            elif model.startswith("ahrefs-"):
                p["ahrefs"]["usd"]   += cost; p["ahrefs"]["calls"] += 1
            elif model.startswith("higgsfield-") or model == "unsplash":
                p["other"]["usd"]    += cost; p["other"]["calls"] += 1
            else:
                p["other"]["usd"]    += cost; p["other"]["calls"] += 1
        return p

    month_entries = get_summary(30).get("entries", [])
    year_entries  = get_summary(365).get("entries", [])
    month_costs   = _group_costs(month_entries)
    year_costs    = _group_costs(year_entries)
    for grp in (month_costs, year_costs):
        for v in grp.values():
            v["usd"] = round(v["usd"], 4)

    # ── Agent checklist ───────────────────────────────────────────────────────
    last_runs: dict = {}
    if DATA_FILE.exists():
        for run in json.loads(DATA_FILE.read_text()).get("runs", []):
            m = run.get("module", "")
            if m and m not in last_runs:
                last_runs[m] = run

    pm2_status: dict = {}
    try:
        result = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=5)
        for p in json.loads(result.stdout):
            pm2_status[p["name"]] = p.get("pm2_env", {}).get("status", "unknown")
    except Exception:
        pass

    checklist = []
    for agent in AGENT_DEFS.get(site, []):
        run = last_runs.get(agent["module"])
        hours_since, last_run_str, status = None, None, "never"
        if run:
            last_run_str = run.get("date")
            if last_run_str:
                try:
                    dt = datetime.fromisoformat(last_run_str.replace("Z", "+00:00"))
                    hours_since = round((now - dt).total_seconds() / 3600, 1)
                    status = "ok" if hours_since <= agent["max_hours"] else "overdue"
                except Exception:
                    pass
        checklist.append({
            "module":          agent["module"],
            "label":           agent["label"],
            "cron":            agent["cron"],
            "status":          status,
            "hours_since":     hours_since,
            "last_run":        last_run_str,
            "pm2_status":      pm2_status.get(agent["pm2"]) if agent["pm2"] else None,
            "last_run_status": run.get("status") if run else None,
        })

    return {
        "site":         site,
        "seo":          seo,
        "articles_count": articles_count,
        "indexation":   indexation,
        "month_costs":  month_costs,
        "year_costs":   year_costs,
        "checklist":    checklist,
        "checkedAt":    now.isoformat(),
    }


# ── /api/seo ──────────────────────────────────────────────────────────────────

@app.get("/api/sites/{site}/seo/dashboard")
def api_seo_dashboard(site: str):
    """KPI SEO + recos (GSC + Ahrefs + Stratège Trafic) pour la page /seo."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import traffic_strategist as ts
    return ts.dashboard(site)


@app.get("/api/seo")
def get_seo():
    env = load_env()
    api_key = env.get("AHREFS_API_KEY", "")

    seo_dir = BASE_DIR / "memory" / "seo"
    sites_data: dict = {}

    for site in ["lcr", "mkd"]:
        cache_file = seo_dir / f"{site}-latest.json"
        if cache_file.exists():
            try:
                sites_data[site] = json.loads(cache_file.read_text())
            except Exception:
                sites_data[site] = {"error": "cache read error"}
        else:
            sites_data[site] = {"status": "no_data"}

    # Unités Ahrefs : appel direct API pour les vraies données
    units_used = 0
    units_limit = 0
    units_reset = ""
    try:
        ahrefs_r = requests.get("https://api.ahrefs.com/v3/subscription-info/limits-and-usage",
                               headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
        if ahrefs_r.status_code == 200:
            info = ahrefs_r.json().get("limits_and_usage", {})
            units_used = info.get("units_usage_api_key", 0)
            units_limit = info.get("units_limit_api_key") or 26000
            units_reset = info.get("usage_reset_date", "")
    except Exception:
        pass

    return {
        "configured": bool(api_key),
        "sites":      sites_data,
        "unitsUsed": units_used, "unitsLimit": units_limit, "unitsReset": units_reset,
        "checkedAt":  datetime.now(timezone.utc).isoformat(),
    }


# ── /api/seo/directories ──────────────────────────────────────────────────────

@app.get("/api/seo/directories")
def get_directories():
    """Retourne l'état des soumissions d'annuaires."""
    seo_dir  = BASE_DIR / "memory" / "seo"
    dirs_log = seo_dir / "directories-log.json"
    todo_md  = seo_dir / "annuaires-todo.md"

    log = {}
    if dirs_log.exists():
        try:
            log = json.loads(dirs_log.read_text())
        except Exception:
            pass

    submitted = log.get("submitted", {})

    # Import la liste depuis seo_agent
    import sys
    sys.path.insert(0, str(BASE_DIR))
    try:
        from scripts.seo_agent import DIRECTORIES
        dirs = DIRECTORIES
    except Exception:
        dirs = []

    result = []
    for d in dirs:
        name = d["name"]
        sub  = submitted.get(name)
        result.append({
            "name":         name,
            "url":          d.get("url", ""),
            "submit_url":   d.get("submit_url", ""),
            "free":         d.get("free", True),
            "submitted":    sub is not None,
            "submitted_at": sub.get("date", "") if sub else None,
        })

    todo_content = todo_md.read_text() if todo_md.exists() else ""

    return {
        "directories":      result,
        "submitted_count":  len(submitted),
        "total":            len(dirs),
        "pending_count":    len([d for d in result if not d["submitted"]]),
        "todo_md":          todo_content,
    }


# ── /api/seo/directories/submit ───────────────────────────────────────────────

@app.post("/api/seo/directories/submit")
def submit_directory(name: str):
    """Marque un annuaire comme soumis."""
    seo_dir  = BASE_DIR / "memory" / "seo"
    dirs_log = seo_dir / "directories-log.json"
    log = {}
    if dirs_log.exists():
        try:
            log = json.loads(dirs_log.read_text())
        except Exception:
            pass
    log.setdefault("submitted", {})[name] = {
        "date": datetime.now(timezone.utc).isoformat(),
        "note": "marqué depuis le dashboard",
    }
    dirs_log.write_text(json.dumps(log, ensure_ascii=False, indent=2))
    return {"ok": True, "name": name}


# ── /api/seo/run ───────────────────────────────────────────────────────────────

@app.post("/api/seo/run")
def run_seo(site: str = "both", report: str = "full"):
    """Lance une analyse SEO en arrière-plan."""
    import subprocess as sp
    env = load_env()
    if not env.get("AHREFS_API_KEY"):
        return {"error": "AHREFS_API_KEY non configuré dans .env"}
    try:
        cmd = ["python3", str(BASE_DIR / "scripts" / "seo.py"), "--site", site, "--report", report]
        proc = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, cwd=str(BASE_DIR))
        return {"started": True, "pid": proc.pid, "cmd": " ".join(cmd)}
    except Exception as e:
        return {"error": str(e)}



# ── /api/sites ───────────────────────────────────────────────────────────────

@app.get("/api/sites")
def get_sites():
    """Liste tous les sites enregistrés (sans credentials)."""
    try:
        sys.path.insert(0, str(BASE_DIR))
        from scripts.sites_config import load_all_sites
        sites = load_all_sites()
        safe = {}
        for code, data in sites.items():
            entry = {k: v for k, v in data.items() if k != "cms_credentials"}
            safe[code] = entry
        return {"sites": safe, "count": len(safe)}
    except Exception as e:
        return {"error": str(e)}


class SiteCreateRequest(BaseModel):
    code: str
    label: str
    domain: str
    url: str
    country: str = "fr"
    language: str = "fr"
    primary_color: str = "#3b82f6"
    cms: str = "emdash"
    blog_url: str = ""
    tone: str = ""
    cta: str = ""
    keywords: list[str] = []
    sitemap_url: str = ""
    blog_prefix: str = ""
    rss_sources: list[dict] = []
    is_directory_target: bool = False
    # Newsletter
    from_name: str = ""
    from_email: str = ""
    subject_tpl: str = "Newsletter {month}"
    footer_desc: str = ""
    topics: list[str] = []
    cta_url: str = ""
    cta_label: str = "En savoir plus"
    audience_id: str = ""
    # RAG context
    business_description: str = ""
    primary_audience: str = ""
    industry: str = ""
    value_proposition: str = ""
    competitors: list[str] = []
    tone_of_voice: str = ""
    seo_goals: str = ""
    products_services: list[str] = []
    # CMS credentials (optionnel)
    emdash_token: str = ""
    emdash_url: str = "http://localhost:4321"
    wp_url: str = ""
    wp_username: str = ""
    wp_app_password: str = ""


@app.post("/api/sites")
def create_site(req: SiteCreateRequest):
    """Enregistre un nouveau site + crée la structure + chunk RAG + .env vars."""
    import re
    from datetime import datetime, timezone
    sys.path.insert(0, str(BASE_DIR))
    from scripts.sites_config import register_site, write_site_context

    # Validation code
    if not re.match(r"^[a-z][a-z0-9]{1,15}$", req.code):
        return {"error": "Code invalide (doit être alphanumérique minuscule, 2-16 chars)"}

    now = datetime.now(timezone.utc).isoformat()
    site_url = req.url or f"https://{req.domain}"
    sitemap  = req.sitemap_url or f"{site_url}/sitemap.xml"
    blog_pfx = req.blog_prefix or req.blog_url or f"{site_url}/blog/"

    site_data = {
        "_meta": {"created_at": now, "status": "onboarding"},
        "core": {
            "code": req.code, "label": req.label, "domain": req.domain,
            "url": site_url, "country": req.country, "language": req.language,
            "primary_color": req.primary_color,
        },
        "seo": {"keywords": req.keywords},
        "content": {
            "cms": req.cms, "blog_url": req.blog_url or blog_pfx,
            "tone": req.tone, "cta": req.cta,
        },
        "seo_agent": {
            "rss_sources": req.rss_sources,
            "is_directory_target": req.is_directory_target,
        },
        "newsletter": {
            "from_name": req.from_name or req.label,
            "from_email": req.from_email,
            "subject_tpl": req.subject_tpl,
            "accent": req.primary_color,
            "audience_id": req.audience_id,
            "topics": req.topics,
            "cta_url": req.cta_url or site_url,
            "cta_label": req.cta_label,
            "footer_desc": req.footer_desc,
        },
        "indexation": {
            "sitemap_url": sitemap,
            "blog_prefix": blog_pfx,
            "indexnow_key": f"genesis-{req.code}-indexnow-2026",
        },
        "api": {"site_modules": ["content", "seo", "indexation"]},
        "cms_credentials": {
            "emdash_token_env": f"EMDASH_API_TOKEN_{req.code.upper()}" if req.cms == "emdash" else "",
            "emdash_url_env":   f"EMDASH_API_URL_{req.code.upper()}"   if req.cms == "emdash" else "",
            "wp_url_env":       f"WP_SITE_URL_{req.code.upper()}"       if req.cms == "wordpress" else "",
            "wp_user_env":      f"WP_USERNAME_{req.code.upper()}"       if req.cms == "wordpress" else "",
            "wp_pass_env":      f"WP_APP_PASSWORD_{req.code.upper()}"   if req.cms == "wordpress" else "",
        },
        "rag_context": {
            "business_description": req.business_description,
            "primary_audience":     req.primary_audience,
            "industry":             req.industry,
            "value_proposition":    req.value_proposition,
            "competitors":          req.competitors,
            "tone_of_voice":        req.tone_of_voice,
            "seo_goals":            req.seo_goals,
            "products_services":    req.products_services,
        },
    }

    try:
        register_site(req.code, site_data)
    except ValueError as e:
        return {"error": str(e)}

    # Créer les dossiers memory
    mem_dir = BASE_DIR / "memory" / req.code
    (mem_dir / "weekly-reports").mkdir(parents=True, exist_ok=True)
    (mem_dir / "articles-published.md").write_text(
        f"# Articles publiés — {req.label}\n\n"
        "| Date | Slug | Titre | Mot-clé | Source | URL |\n"
        "|------|------|-------|---------|--------|-----|\n"
    )

    # Chunk RAG
    write_site_context(req.code)

    # Append credentials to .env
    env_lines = []
    if req.cms == "emdash" and req.emdash_token:
        env_lines += [
            f"EMDASH_API_TOKEN_{req.code.upper()}={req.emdash_token}",
            f"EMDASH_API_URL_{req.code.upper()}={req.emdash_url}",
        ]
    elif req.cms == "wordpress" and req.wp_url:
        env_lines += [
            f"WP_SITE_URL_{req.code.upper()}={req.wp_url}",
            f"WP_USERNAME_{req.code.upper()}={req.wp_username}",
            f"WP_APP_PASSWORD_{req.code.upper()}={req.wp_app_password}",
        ]
    if env_lines:
        with open(BASE_DIR / ".env", "a") as f:
            f.write("\n# Site: " + req.label + "\n")
            f.write("\n".join(env_lines) + "\n")

    return {
        "ok": True,
        "code": req.code,
        "label": req.label,
        "memory_dir": str(mem_dir),
        "context_file": str(mem_dir / "site-context.md"),
    }


class CMSTestRequest(BaseModel):
    cms: str
    emdash_url: str = "http://localhost:4321"
    emdash_token: str = ""
    wp_url: str = ""
    wp_username: str = ""
    wp_app_password: str = ""


@app.post("/api/sites/test-cms")
def test_cms(req: CMSTestRequest):
    """Teste la connexion CMS avant soumission du form."""
    import requests as req_lib
    try:
        if req.cms == "emdash":
            from urllib.parse import urlparse
            parsed = urlparse(req.emdash_url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            r = req_lib.get(
                f"{base}/_emdash/api/content/posts?limit=1",
                headers={"Authorization": f"Bearer {req.emdash_token}"},
                timeout=5,
            )
            return {"ok": r.status_code == 200, "status_code": r.status_code}
        elif req.cms == "wordpress":
            import base64
            auth = base64.b64encode(f"{req.wp_username}:{req.wp_app_password}".encode()).decode()
            r = req_lib.get(
                f"{req.wp_url}/wp-json/wp/v2/posts?per_page=1",
                headers={"Authorization": f"Basic {auth}"},
                timeout=8,
            )
            return {"ok": r.status_code in (200, 401), "status_code": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "cms type inconnu"}


@app.get("/api/sites/{code}/status")
def get_site_onboarding_status(code: str):
    """Statut d'onboarding d'un site (lit onboarding-log.json)."""
    path = BASE_DIR / "memory" / code / "onboarding-log.json"
    if not path.exists():
        return {"code": code, "status": "not_started"}
    return json.loads(path.read_text())


@app.post("/api/sites/{code}/onboard")
def onboard_site(code: str, dry_run: bool = True):
    """Lance onboarding_agent.py en arrière-plan."""
    import subprocess as sp
    try:
        cmd = [
            "python3", str(BASE_DIR / "scripts" / "onboarding_agent.py"),
            "--site", code,
        ]
        if not dry_run:
            cmd.append("--live")
        proc = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, cwd=str(BASE_DIR))
        return {"started": True, "pid": proc.pid, "dry_run": dry_run, "code": code}
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/sites/{code}")
def delete_site(code: str):
    """Soft-delete: met status=paused (ne supprime pas les données)."""
    if code in ("lcr", "mkd"):
        return {"error": "Impossible de supprimer les sites principaux"}
    try:
        sys.path.insert(0, str(BASE_DIR))
        from scripts.sites_config import update_site
        update_site(code, {"_meta": {"status": "paused"}})
        return {"ok": True, "code": code, "status": "paused"}
    except Exception as e:
        return {"error": str(e)}


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    # 127.0.0.1 et non 0.0.0.0 : l'API ne doit être joignable QUE par Nginx (qui passe par
    # la boucle locale). Écouter sur 0.0.0.0 exposait le port 8080 à Internet en direct,
    # court-circuitant Nginx et la protection anti-force-brute (revue de sécurité 2026-08-21).
    # Pour ouvrir volontairement à toutes les interfaces : HOST_API=0.0.0.0 dans .env.
    import os as _os
    uvicorn.run("scripts.api:app", host=_os.environ.get("HOST_API", "127.0.0.1"),
                port=8080, reload=False)


# ── /api/indexation ──────────────────────────────────────────────────────────

@app.get("/api/indexation")
def get_indexation(site: str = "lcr"):
    """Retourne le rapport d'audit d'indexation pour un site."""
    slug = "lcr" if site == "lcr" else "mkd"
    path = BASE_DIR / "memory" / "seo" / f"{slug}-indexation-audit.json"
    if not path.exists():
        return {"error": "Rapport non trouvé — lancez indexation_agent.py --task audit"}
    return json.loads(path.read_text())


@app.get("/api/indexation/sitemap")
def get_sitemap_xml():
    """Retourne le sitemap dynamique LCR généré."""
    path = BASE_DIR / "data" / "sitemap-lcr.xml"
    if not path.exists():
        return {"error": "Sitemap non généré"}
    from fastapi.responses import Response
    return Response(content=path.read_text(), media_type="application/xml")


@app.post("/api/indexation/run")
def run_indexation(site: str = "both", task: str = "all"):
    """Lance l'agent d'indexation en arrière-plan."""
    import subprocess as sp
    try:
        cmd = [
            "python3", str(BASE_DIR / "scripts" / "indexation_agent.py"),
            "--task", task, "--site", site, "--live"
        ]
        proc = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, cwd=str(BASE_DIR))
        return {"started": True, "pid": proc.pid}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/indexation/daily")
def get_indexation_daily(site: str = "lcr"):
    """Retourne le rapport quotidien d'indexation (nouvelles URLs soumises)."""
    slug = "lcr" if site == "lcr" else "mkd"
    report_path = BASE_DIR / "memory" / "seo" / f"{slug}-daily-report.json"
    submitted_path = BASE_DIR / "memory" / "seo" / f"{slug}-submitted-urls.json"

    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    submitted_log = json.loads(submitted_path.read_text()) if submitted_path.exists() else {}

    return {
        "site": slug,
        "last_report": report,
        "total_submitted": len(submitted_log),
        "submitted_log_preview": dict(list(submitted_log.items())[-5:]),
    }


@app.post("/api/indexation/daily/run")
def run_indexation_daily(site: str = "both"):
    """Lance le pipeline quotidien d'indexation (diff + seulement nouveaux articles)."""
    import subprocess as sp
    try:
        cmd = [
            "python3", str(BASE_DIR / "scripts" / "indexation_agent.py"),
            "--task", "daily", "--site", site, "--live"
        ]
        proc = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, cwd=str(BASE_DIR))
        return {"started": True, "pid": proc.pid, "task": "daily", "site": site}
    except Exception as e:
        return {"error": str(e)}


# ── /api/cold-email ───────────────────────────────────────────────────────────

LEADS_LOG = BASE_DIR / "data" / "leads-log.json"

def _load_leads() -> list[dict]:
    if not LEADS_LOG.exists():
        return []
    return json.loads(LEADS_LOG.read_text()).get("entries", [])

def _status_bucket(s: str) -> str:
    s = (s or "").lower()
    if s in ("ok", "contacted", "sent", "replied", "opened"): return "ok"
    if s in ("rejected", "bounced", "invalid"): return "rejected"
    if s in ("dropped", "unsubscribed", "blacklisted"): return "dropped"
    return "error"

@app.get("/api/cold-email/overview")
def ce_overview():
    entries = _load_leads()
    totals = {"total": 0, "ok": 0, "rejected": 0, "dropped": 0, "error": 0}
    sources = {}
    monthly = {}
    for e in entries:
        b = _status_bucket(e.get("status", ""))
        src = e.get("source", "inconnu")
        month = (e.get("date") or e.get("datetime") or "")[:7]
        totals["total"] += 1
        totals[b] += 1
        if src not in sources:
            sources[src] = {"total": 0, "ok": 0, "rejected": 0, "dropped": 0, "error": 0}
        sources[src]["total"] += 1
        sources[src][b] += 1
        if month:
            if month not in monthly:
                monthly[month] = {"total": 0, "ok": 0, "rejected": 0, "dropped": 0, "error": 0}
            monthly[month]["total"] += 1
            monthly[month][b] += 1
    return {"totals": totals, "sources": sources, "monthly": dict(sorted(monthly.items()))}

@app.get("/api/cold-email/tab/{source}")
def ce_tab(source: str):
    entries = _load_leads()
    filtered = [e for e in entries if e.get("source", "inconnu") == source]
    stats = {"total": 0, "ok": 0, "rejected": 0, "dropped": 0, "error": 0}
    by_day = {}
    for e in filtered:
        b = _status_bucket(e.get("status", ""))
        day = (e.get("date") or e.get("datetime") or "")[:10]
        stats["total"] += 1
        stats[b] += 1
        if day:
            if day not in by_day:
                by_day[day] = {"sent": 0, "ok": 0, "rejected": 0, "dropped": 0, "error": 0}
            by_day[day]["sent"] += 1
            by_day[day][b] += 1
    return {"source": source, "stats": stats, "by_day": dict(sorted(by_day.items()))}

@app.get("/api/cold-email/search")
def ce_search(q: str = ""):
    if len(q) < 4:
        return {"count": 0, "results": []}
    q_low = q.lower()
    results = [e for e in _load_leads()
               if q_low in (e.get("email") or "").lower()
               or q_low in (e.get("gsm") or "").lower()]
    return {"count": len(results), "results": results[:50]}

@app.get("/api/cold-email/export")
def ce_export(from_date: str = "", to_date: str = ""):
    import io, csv as csv_mod
    from fastapi.responses import StreamingResponse
    def parse(s):
        try:
            p = s.strip().split("/")
            return f"{p[2]}-{p[1]}-{p[0]}" if len(p) == 3 else s
        except Exception:
            return s
    f, t = parse(from_date), parse(to_date)
    entries = [e for e in _load_leads()
               if (not f or (e.get("date") or "")[:10] >= f)
               and (not t or (e.get("date") or "")[:10] <= t)]
    out = io.StringIO()
    w = csv_mod.DictWriter(out, fieldnames=["date","source","email","gsm","firstName","lastName","status","campaign_name","error_msg"])
    w.writeheader()
    for e in entries:
        w.writerow({k: e.get(k, "") for k in ["date","source","email","gsm","firstName","lastName","status","campaign_name","error_msg"]})
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="cold-email-export.csv"'})

@app.post("/api/cold-email/ingest")
def ce_ingest(payload: dict):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    entry = {"id": f"lead_{now}", "date": now[:10], "datetime": now,
             "source": payload.get("source", "inconnu"),
             "email": payload.get("email", ""),
             "gsm": payload.get("gsm", ""),
             "firstName": payload.get("firstName", ""),
             "lastName": payload.get("lastName", ""),
             "status": payload.get("status", "ok"),
             "campaign_name": payload.get("campaign_name", ""),
             "error_msg": payload.get("error_msg", "")}
    data = json.loads(LEADS_LOG.read_text()) if LEADS_LOG.exists() else {"version": 1, "entries": []}
    data["entries"].append(entry)
    LEADS_LOG.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return {"ok": True}


# ── /api/analytics ────────────────────────────────────────────────────────────

@app.get("/api/analytics")
def get_analytics(site: str = "lcr"):
    """Retourne les données analytiques complètes pour un site (Ahrefs + indexation)."""
    # SEO data
    seo_path = BASE_DIR / "memory" / "seo" / f"{site}-latest.json"
    seo = json.loads(seo_path.read_text()) if seo_path.exists() else {}

    # Indexation data
    idx_path = BASE_DIR / "memory" / "seo" / f"{site}-indexation-audit.json"
    idx = json.loads(idx_path.read_text()) if idx_path.exists() else {}

    # Compute health score (0-100)
    dr           = float(seo.get("domain_rating", 0))
    traffic      = int(seo.get("org_traffic", 0))
    kw_count     = int(seo.get("org_keywords", 0))
    published    = int(idx.get("published_count", 0))
    missing      = len(idx.get("missing_articles", []))
    indexed      = max(0, published - missing)
    idx_ratio    = (indexed / published) if published > 0 else 0

    score_dr     = min(dr / 30 * 40, 40)
    score_idx    = idx_ratio * 30
    score_kw     = min(kw_count / 20 * 20, 20)
    score_traf   = min(traffic / 1000 * 10, 10)
    health_score = round(score_dr + score_idx + score_kw + score_traf)

    # Priority alerts
    alerts = []
    if missing > 0:
        alerts.append({"level": "critique", "msg": f"{missing} articles publiés mais absents du sitemap (invisibles à Google)"})
    if dr < 5:
        alerts.append({"level": "critique", "msg": f"Domain Rating très bas ({dr}) — priorité aux backlinks et annuaires"})
    opps = seo.get("opportunities", [])
    if opps:
        alerts.append({"level": "important", "msg": f"{len(opps)} opportunités KD<30 non exploitées (contenu facile à ranker)"})
    if traffic < 100:
        alerts.append({"level": "important", "msg": f"Trafic organique faible ({traffic}/mois) — publier plus de contenu long-tail"})

    # SERP analysis (qui est en #1 sur nos mots-clés cibles)
    kw_overview = seo.get("kw_overview", [])
    serp_top    = seo.get("serp_top", [])

    return {
        "site": site,
        "date": seo.get("date", ""),
        "health_score": health_score,
        "kpis": {
            "domain_rating":   dr,
            "ahrefs_rank":     seo.get("ahrefs_rank", 0),
            "organic_traffic": traffic,
            "org_keywords":    kw_count,
            "articles_published": published,
            "articles_indexed":   indexed,
            "articles_missing":   missing,
            "indexation_rate":    round(idx_ratio * 100),
        },
        "alerts": alerts,
        "keywords":     seo.get("organic_keywords", [])[:15],
        "opportunities": opps[:10],
        "kw_overview":  kw_overview,
        "serp_top":     serp_top[:5],
        "top_pages":    seo.get("top_pages", [])[:10],
        "competitors":  seo.get("organic_competitors", [])[:8],
        "missing_articles": idx.get("missing_articles", [])[:10],
        "score_breakdown": {
            "domain_rating": round(score_dr, 1),
            "indexation":    round(score_idx, 1),
            "keywords":      round(score_kw, 1),
            "traffic":       round(score_traf, 1),
        }
    }


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/api/health-check")
async def api_health_check(request: Request):
    """Check health of all configured sites: HTTP, SSL, sitemap, robots.txt.
    Filtré par les sites de l'utilisateur (un non-superadmin ne voit QUE ses sites)."""
    # Sites to check
    sites = [
        {"code": "lcr", "name": "LeClientROI", "url": "https://leclientroi.com"},
        {"code": "mkd", "name": "MKDgroupe", "url": "https://mkdgroupe.com"},
    ]
    # Also load from sites-config.json if it exists
    sites_config = BASE_DIR / "memory" / "sites-config.json"
    if sites_config.exists():
        try:
            import json as _json
            cfg = _json.loads(sites_config.read_text())
            for s in cfg.get("sites", []):
                if s.get("url") and s.get("code") not in [x["code"] for x in sites]:
                    sites.append(s)
        except Exception:
            pass

    # Isolation multi-tenant : un non-superadmin ne reçoit QUE ses sites.
    sess = getattr(request.state, "session", None)
    if sess and sess.get("role") not in ("admin", "superadmin"):
        allowed = set(sess.get("sites") or [])
        sites = [s for s in sites if s.get("code") in allowed]

    results = check_all_sites(sites)
    return {"sites": results, "checked_at": datetime.now(timezone.utc).isoformat()}


# ── Competitor SEO Analysis (sortie de competitor_seo_analyzer.py) ───────────

@app.get("/api/sites/{site}/competitor-analysis")
def api_competitor_analysis(site: str):
    """Retourne l'analyse concurrentielle (seed + top opportunités + gaps + plan)."""
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    f = BASE_DIR / "memory" / "seo" / f"{site}-competitor-analysis.json"
    if not f.exists():
        return {"error": "no analysis yet (run competitor_seo_analyzer.py first)", "site": site}
    try:
        return json.loads(f.read_text())
    except Exception as e:
        return {"error": str(e)}


# ── Versions & Backups ────────────────────────────────────────────────────────

@app.get("/api/versions")
async def api_versions(limit: int = 50):
    """Version actuelle + changelog (git log) + ZIP backups + diff vs origin."""
    # Version courante
    count = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=str(BASE_DIR), capture_output=True, text=True, timeout=5).stdout.strip()
    sha   = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(BASE_DIR), capture_output=True, text=True, timeout=5).stdout.strip()
    head_date = subprocess.run(["git", "log", "-1", "--format=%cI"], cwd=str(BASE_DIR), capture_output=True, text=True, timeout=5).stdout.strip()

    # Diff vs origin (best-effort, sans bloquer si pas de réseau)
    ahead, behind = 0, 0
    try:
        subprocess.run(["git", "fetch", "--no-tags", "--depth=1", "origin", "main"], cwd=str(BASE_DIR), timeout=8, capture_output=True)
        ab = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=5,
        ).stdout.strip().split()
        if len(ab) >= 2:
            behind, ahead = int(ab[0]), int(ab[1])
    except Exception:
        pass

    # Commits récents
    commits = []
    try:
        result = subprocess.run(
            ["git", "log", f"-{max(1, min(limit, 200))}", "--pretty=format:%h\t%an\t%cI\t%s"],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.split("\n"):
            line = line.strip()
            if not line: continue
            parts = line.split("\t", 3)
            if len(parts) < 4: continue
            sha_c, author, date_c, msg = parts
            low = msg.lower()
            if low.startswith("feat"):       tag = "feat"
            elif low.startswith("fix") or low.startswith("bug"): tag = "fix"
            elif low.startswith("refactor"): tag = "refactor"
            elif low.startswith("doc"):       tag = "doc"
            elif low.startswith("chore"):    tag = "chore"
            elif low.startswith("auto:") or "backup" in low: tag = "backup"
            elif low.startswith("init"):      tag = "init"
            else: tag = "other"
            commits.append({"sha": sha_c, "author": author, "date": date_c, "message": msg, "tag": tag})
    except Exception:
        pass

    # Backups ZIP + LOGs (rotation 3 conservée par backup.sh)
    backups = []
    backup_dir = BASE_DIR / "backups"
    if backup_dir.exists():
        for z in sorted(backup_dir.glob("genesis-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
            stat = z.stat()
            # Cherche le .log correspondant (même nom mais extension .log)
            log_name = z.name.replace(".zip", ".log")
            log_path = backup_dir / log_name
            backups.append({
                "name": z.name,
                "size_mb": round(stat.st_size / (1024 * 1024), 1),
                "date": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "log_available": log_path.exists(),
                "log_name": log_name if log_path.exists() else None,
            })

    return {
        "version":       f"v{count}.{sha}" if count and sha else (sha or "dev"),
        "commit_count":  int(count) if count.isdigit() else None,
        "head_sha":      sha,
        "head_date":     head_date,
        "ahead":         ahead,
        "behind":        behind,
        "remote":        "origin/main",
        "commits":       commits,
        "backups":       backups,
        # Compat avec l'ancien format (au cas où d'autres consommateurs l'utilisent)
        "git_log":       [{"hash": c["sha"], "date": c["date"][:16], "message": c["message"]} for c in commits[:20]],
    }


@app.get("/api/version")
def api_version():
    """Version courante (rapide, sans réseau) — pour l'affichage sidebar.

    `version` = v{nb_commits}.{sha} ; `deployed_at` = date du dernier backup ZIP
    (= snapshot de mise en prod)."""
    try:
        count = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=str(BASE_DIR),
                               capture_output=True, text=True, timeout=5).stdout.strip()
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(BASE_DIR),
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        count, sha = "", ""
    version = f"v{count}.{sha}" if count and sha else (sha or "dev")

    deployed_at, backup_name = None, None
    backup_dir = BASE_DIR / "backups"
    if backup_dir.exists():
        zips = sorted(backup_dir.glob("genesis-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        if zips:
            backup_name = zips[0].name
            deployed_at = datetime.fromtimestamp(zips[0].stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

    return {"version": version, "deployed_at": deployed_at, "backup": backup_name}


# ── SEO Ahrefs Data ───────────────────────────────────────────────────────────

@app.get("/api/seo-ahrefs/{site}")
async def api_seo_ahrefs(site: str):
    """Métriques Ahrefs en cache pour un site.

    Lit `{site}-metrics-latest.json`, le fichier que `ahrefs_daily.py` écrit chaque matin à
    6 h. L'ancien nom `{site}-ahrefs-latest.json` n'est plus produit depuis le 21/05/2026 :
    l'endpoint servait donc des chiffres vieux de trois mois sans que rien ne le signale.
    On garde l'ancien fichier en repli — il contient `domain_rating`, que le format récent
    n'inclut pas toujours — et on expose `fetched_at` pour que la fraîcheur soit visible.
    """
    seo_dir = BASE_DIR / "memory" / "seo"
    frais = seo_dir / f"{site}-metrics-latest.json"
    ancien = seo_dir / f"{site}-ahrefs-latest.json"
    cache_file = frais if frais.exists() else ancien
    if not cache_file.exists():
        return {"error": "no data", "site": site}
    if frais.exists() and ancien.exists():
        try:
            data = json.loads(frais.read_text())
            vieux = json.loads(ancien.read_text())
            # Champs que le format récent ne porte pas : on complète sans écraser.
            for cle in ("domain_rating", "ahrefs_rank", "top_keywords", "competitors"):
                data.setdefault(cle, vieux.get(cle))
            return data
        except Exception:
            pass
    try:
        data = json.loads(cache_file.read_text())
        return data
    except Exception as e:
        return {"error": str(e), "site": site}


# ── Editorial Pipeline ────────────────────────────────────────────────────────

@app.get("/api/editorial/queue")
async def api_editorial_queue():
    return await editorial_queue_get()

@app.post("/api/editorial/queue")
async def api_editorial_create(request: Request):
    data = await request.json()
    return await editorial_queue_post(data)

@app.post("/api/editorial/{article_id}/approve")
async def api_editorial_approve(article_id: str):
    return await editorial_approve(article_id)

@app.post("/api/editorial/{article_id}/reject")
async def api_editorial_reject(article_id: str):
    return await editorial_reject(article_id)

@app.post("/api/editorial/{article_id}/publish")
async def api_editorial_publish(article_id: str):
    return await editorial_publish(article_id)

@app.post("/api/editorial/{article_id}/revision")
async def api_editorial_revision(article_id: str, request: Request):
    data = await request.json()
    return await editorial_revision(article_id, data)

@app.get("/api/editorial/{article_id}")
async def api_editorial_detail(article_id: str):
    return await editorial_detail(article_id)

@app.patch("/api/editorial/{article_id}")
async def api_editorial_update(article_id: str, request: Request):
    data = await request.json()
    return await editorial_patch(article_id, data)


# ── SEO Strategy Recommendations ──────────────────────────────────────────────

@app.get("/api/seo-strategy/{site}")
async def api_seo_strategy(site: str):
    """Get SEO recommendations for a site."""
    reco_file = BASE_DIR / "memory" / "seo" / "recommendations.json"
    if not reco_file.exists():
        return {"recommendations": []}
    data = json.loads(reco_file.read_text())
    return {"recommendations": data.get(site, [])}

@app.post("/api/seo-strategy/{reco_id}/validate")
async def api_seo_strategy_validate(reco_id: str):
    """Validate a recommendation."""
    reco_file = BASE_DIR / "memory" / "seo" / "recommendations.json"
    if not reco_file.exists():
        return {"error": "no data"}
    data = json.loads(reco_file.read_text())
    for site in data:
        for r in data[site]:
            if r.get("id") == reco_id:
                r["status"] = "validated"
                r["validated_at"] = datetime.now(timezone.utc).isoformat()
                reco_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                return {"ok": True, "status": "validated"}
    return {"error": "not found"}

@app.post("/api/seo-strategy/{reco_id}/ignore")
async def api_seo_strategy_ignore(reco_id: str):
    """Ignore a recommendation."""
    reco_file = BASE_DIR / "memory" / "seo" / "recommendations.json"
    if not reco_file.exists():
        return {"error": "no data"}
    data = json.loads(reco_file.read_text())
    for site in data:
        for r in data[site]:
            if r.get("id") == reco_id:
                r["status"] = "ignored"
                reco_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                return {"ok": True, "status": "ignored"}
    return {"error": "not found"}

@app.post("/api/seo-strategy/{reco_id}/done")
async def api_seo_strategy_done(reco_id: str):
    """Mark a recommendation as done."""
    reco_file = BASE_DIR / "memory" / "seo" / "recommendations.json"
    if not reco_file.exists():
        return {"error": "no data"}
    data = json.loads(reco_file.read_text())
    for site in data:
        for r in data[site]:
            if r.get("id") == reco_id:
                r["status"] = "done"
                r["done_at"] = datetime.now(timezone.utc).isoformat()
                reco_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                return {"ok": True, "status": "done"}
    return {"error": "not found"}

@app.post("/api/seo-strategy/run")
async def api_seo_strategy_run(request: Request):
    """Trigger SEO strategy analysis now."""
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    site = data.get("site", "both")
    subprocess.Popen(
        ["python3", "scripts/seo_strategy_agent.py", "--site", site],
        cwd=str(BASE_DIR),
        stdout=open(str(BASE_DIR / "memory/seo/strategy-run.log"), "w"),
        stderr=subprocess.STDOUT,
    )
    return {"ok": True, "message": f"Analyse lancée pour {site}"}


@app.post("/api/seo-strategy/analyze-competitor")
async def api_analyze_competitor(request: Request):
    """Trigger competitor analysis — scrape their strategy via Ahrefs data."""
    data = await request.json()
    domain = data.get("domain", "")
    site = data.get("site", "lcr")
    if not domain:
        return {"error": "domain required"}

    subprocess.Popen(
        ["python3", "scripts/competitor_analyzer.py", "--domain", domain, "--site", site],
        cwd=str(BASE_DIR),
        stdout=open(str(BASE_DIR / f"memory/seo/competitor-{domain.replace('.','_')}.log"), "w"),
        stderr=subprocess.STDOUT,
    )
    return {"ok": True, "message": f"Analyse de {domain} lancée"}


# ── Agents ─ endpoints actifs ────────────
# Source de vérité : memory/agents-pm2-state.json (gen_agents_state.py).
# L'ancien AGENTS_REGISTRY hardcodé + agent-crons.json (absent) + /planner ont
# été retirés le 2026-06-10 (transformation agentique, chantier 6).

@app.get("/api/agents/{site}/{agent_id}/instructions")
async def api_agent_site_instructions(site: str, agent_id: str):
    """Get contextualized instructions for an agent on a specific site."""
    # Try site-specific first, then generic
    site_file = BASE_DIR / "skills" / site / f"{agent_id}.md"
    generic_file = BASE_DIR / "skills" / f"{agent_id}.md"

    if site_file.exists():
        return {"id": agent_id, "site": site, "instructions": site_file.read_text(), "contextualized": True}
    elif generic_file.exists():
        return {"id": agent_id, "site": site, "instructions": generic_file.read_text(), "contextualized": False}
    return {"id": agent_id, "site": site, "instructions": "Instructions non trouv\u00e9es.", "error": True}

@app.get("/api/agents/{site}/state")
async def api_agents_state(site: str):
    """Vrai état PM2 des agents (memory/agents-pm2-state.json, refresh si stale)."""
    f = BASE_DIR / "memory" / "agents-pm2-state.json"
    stale_after_s = 300
    needs_refresh = (not f.exists()
                     or (time.time() - f.stat().st_mtime) > stale_after_s)
    if needs_refresh:
        try:
            subprocess.run(
                ["python3", str(BASE_DIR / "scripts" / "gen_agents_state.py")],
                capture_output=True, timeout=20, check=False)
        except Exception:  # noqa: BLE001
            pass  # fallback : on lit le fichier existant s'il y en a un
    if not f.exists():
        return {"site": site, "agents": [], "stale": True,
                "error": "snapshot pm2 indisponible"}
    data = json.loads(f.read_text(encoding="utf-8"))
    agents = [a for a in data.get("agents", [])
              if a.get("site") in (None, site)]
    age_s = int(time.time() - f.stat().st_mtime)
    return {"site": site, "generated_at": data.get("generated_at"),
            "host": data.get("host"), "age_s": age_s, "agents": agents}


# ── Full Onboarding (creates skills + RAG) ────────────────────────────────────

@app.post("/api/sites/onboard-full")
async def api_onboard_full(request: Request):
    """Full onboarding: create site config, contextualized skills, and RAG knowledge base."""
    data = await request.json()
    code = data.get("code", "")
    if not code:
        return {"error": "code required"}

    # Save full site context
    site_dir = BASE_DIR / "memory" / code
    site_dir.mkdir(parents=True, exist_ok=True)

    context = {
        "code": code,
        "label": data.get("label", code),
        "domain": data.get("domain", ""),
        "url": data.get("url", ""),
        "cms": data.get("cms", ""),
        "niche": data.get("niche", ""),
        "audience": data.get("audience", ""),
        "tone": data.get("tone", ""),
        "goal_seo": data.get("goal_seo", ""),
        "description": data.get("description", ""),
        "cta": data.get("cta", ""),
        "cta_url": data.get("cta_url", ""),
        "keywords": data.get("keywords", []),
        "competitors": data.get("competitors", []),
        "sitemap": data.get("sitemap", ""),
        "blog_prefix": data.get("blog_prefix", ""),
        "rss_feeds": data.get("rss_feeds", []),
        "linkedin": data.get("linkedin", ""),
        "twitter": data.get("twitter", ""),
        "instagram": data.get("instagram", ""),
        "facebook": data.get("facebook", ""),
        "color": data.get("color", "#3b82f6"),
        "color2": data.get("color2", "#10b981"),
        "logo": data.get("logo", ""),
        "hashtags": data.get("hashtags", ""),
    }

    # Save site context
    (site_dir / "site-context.json").write_text(json.dumps(context, indent=2, ensure_ascii=False))
    # === ONBOARD_V2_2026-05-22 : enrichissement context avec champs 16 steps ===
    context_v2 = {
        "persona":              data.get("persona", data.get("audience", "")),
        "geo_target":           data.get("geo_target", "FR"),
        "dept_priority":        data.get("dept_priority", []),
        "city_min_pop":         data.get("city_min_pop", 10000),
        "target_keywords":      data.get("target_keywords", data.get("keywords", [])),
        "competitors_v2":       data.get("competitors", []),
        "traffic_goal":         data.get("traffic_goal", ""),
        "tone":                 data.get("tone", ""),
        "cta_default":          data.get("cta_default", data.get("cta", "")),
        "signature":            data.get("signature", ""),
        "banned_words":         data.get("banned_words", ""),
        "sectors_enabled":      data.get("sectors_enabled", []),
        "daily_quota_per_sector": data.get("daily_quota_per_sector", 10),
        "sender_email":         data.get("sender_email", ""),
        "sender_name":          data.get("sender_name", ""),
        "provider_type":        data.get("provider_type", "Gmail"),
        "raison_sociale":       data.get("raison_sociale", ""),
        "adresse_postale":      data.get("adresse_postale", ""),
        "source_label":         data.get("source_label", "via votre présence professionnelle publique"),
        "privacy_url":          data.get("privacy_url", ""),
        "dpo_email":            data.get("dpo_email", ""),
        "templates_option":     data.get("templates_option", "ia"),
        "warmup_plan":          data.get("warmup_plan", "A"),
        "warmup_start_today":   data.get("warmup_start_today", True),
        "modules_enabled":      data.get("modules_enabled", ["emelia", "mailnjoy"]),
        "ahrefs_project_id":    data.get("ahrefs_project_id", ""),
        "emelia_daily_limit":   data.get("emelia_daily_limit", 50),
        "cooldown_same_site":   data.get("cooldown_same_site", 7),
        "cooldown_global":      data.get("cooldown_global", 30),
        "account_id":           data.get("account_id", ""),
        "account_role":         data.get("account_role", "owner"),
        "test_email":           data.get("test_email", ""),
    }
    context.update(context_v2)

    # ── Crée pied de mail B2B ─────────────────────────────────────────────────
    footer_md = f"""# Pied de mail B2B — {context_v2['raison_sociale']}

—
{context_v2['raison_sociale']} — {context_v2['adresse_postale']}
{context_v2['source_label']}
{f'Vous pouvez vous désinscrire : ' + '{{UNSUBSCRIBE_LINK}}' if True else ''}
{f"Contact DPO : {context_v2['dpo_email']}" if context_v2['dpo_email'] else ''}
{f"Politique : {context_v2['privacy_url']}" if context_v2['privacy_url'] else ''}
"""
    ctx_dir = BASE_DIR / "context" / code
    ctx_dir.mkdir(parents=True, exist_ok=True)
    (ctx_dir / "footer.md").write_text(footer_md)

    # ── Sauvegarde audience, prospection, editorial-style ─────────────────────
    (ctx_dir / "audience.md").write_text(
        f"# Persona — {context.get('label')}\n\n{context_v2['persona']}\n\n"
        f"## Zone géographique : {context_v2['geo_target']}\n"
        f"## Départements prioritaires : {', '.join(context_v2['dept_priority']) if context_v2['dept_priority'] else 'tous'}\n"
        f"## Population min commune : {context_v2['city_min_pop']}\n"
    )
    (ctx_dir / "editorial-style.md").write_text(
        f"# Style éditorial — {context.get('label')}\n\n"
        f"## Ton : {context_v2['tone']}\n"
        f"## CTA par défaut : {context_v2['cta_default']}\n"
        f"## Signature : {context_v2['signature']}\n"
        f"## Mots interdits : {context_v2['banned_words']}\n"
    )

    # ── Insère email_senders si fourni ────────────────────────────────────────
    if context_v2['sender_email']:
        try:
            import duckdb as _dd
            from datetime import date as _date
            _c = _dd.connect(str(BASE_DIR / "data" / "god_mode.duckdb"))
            try:
                _c.execute("""
                    INSERT OR REPLACE INTO email_senders
                    (sender_email, sender_name, site_code, warmup_start_date, warmup_finished, status, notes)
                    VALUES (?, ?, ?, ?, FALSE, 'active', ?)
                """, [context_v2['sender_email'], context_v2['sender_name'], code,
                      _date.today() if context_v2['warmup_start_today'] else None,
                      f"onboarded — plan={context_v2['warmup_plan']}"])
            finally:
                _c.close()
        except Exception as e:
            print(f"  [onboard][email_senders] {e}")

    # ── god_mode_settings + state ─────────────────────────────────────────────
    try:
        import duckdb as _dd
        import json as _json
        _c = _dd.connect(str(BASE_DIR / "data" / "god_mode.duckdb"))
        try:
            # Settings (upsert)
            _c.execute("""
                INSERT OR REPLACE INTO god_mode_settings
                (site_code, sectors_enabled, daily_quota_per_sector, emelia_daily_limit,
                 cooldown_same_site_days, cooldown_global_days, account_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [code, _json.dumps(context_v2['sectors_enabled']),
                  context_v2['daily_quota_per_sector'], context_v2['emelia_daily_limit'],
                  context_v2['cooldown_same_site'], context_v2['cooldown_global'],
                  context_v2['account_id']])
            # State (default disabled until step 16 mail test OK)
            _c.execute("""
                INSERT OR REPLACE INTO god_mode_state
                (site_code, enabled, enabled_by, updated_at)
                VALUES (?, FALSE, ?, CURRENT_TIMESTAMP)
            """, [code, "onboarding"])
        finally:
            _c.close()
    except Exception as e:
        print(f"  [onboard][settings] {e}")

    # ── site_credentials (clés API) — chiffrement AES via Fernet ─────────────
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        from site_credentials_backend import set_credential as _set_cred
        for kn, kv in (
            ("EMELIA_API_KEY",  data.get("emelia_key", "")),
            ("SERPER_API_KEY",  data.get("serper_key", "")),
            ("TALLY_API_KEY",   data.get("tally_key", "")),
            ("TELEGRAM_BOT",    data.get("telegram_bot", "")),
            ("TELEGRAM_CHAT",   data.get("telegram_chat", "")),
        ):
            if kv:
                _set_cred(code, kn, kv)
    except Exception as e:
        print(f"  [onboard][credentials AES] {e}")

    # ── account (multi-tenant) ────────────────────────────────────────────────
    if context_v2['account_id']:
        try:
            import duckdb as _dd
            _c = _dd.connect(str(BASE_DIR / "data" / "god_mode.duckdb"))
            try:
                _c.execute("""
                    INSERT OR REPLACE INTO accounts (id, label, plan)
                    VALUES (?, ?, 'free')
                """, [context_v2['account_id'], context_v2['account_id']])
            finally:
                _c.close()
        except Exception as e:
            print(f"  [onboard][accounts] {e}")

    # ── modules config (modules_backend JSON par site) ────────────────────────
    try:
        modules_file = BASE_DIR / "memory" / code / "modules.json"
        modules_file.parent.mkdir(parents=True, exist_ok=True)
        modules_state = {m: True for m in context_v2['modules_enabled']}
        modules_file.write_text(json.dumps({"site": code, "modules": modules_state}, indent=2))
    except Exception as e:
        print(f"  [onboard][modules] {e}")


    # Generate contextualized skills
    skills_dir = BASE_DIR / "skills" / code
    skills_dir.mkdir(parents=True, exist_ok=True)

    kw_list = "\n".join([f"- {k}" for k in context["keywords"]])
    comp_list = "\n".join([f"- {c}" for c in context["competitors"]])

    agents_templates = {
        "editorial-manager": f"# Editorial Manager \u2014 {context['label']}\n\n## Mission\nOrchestrer le pipeline \u00e9ditorial pour **{context['label']}** ({context['domain']}).\n\n## Contexte\n- Niche : {context['niche']}\n- Audience : {context['audience']}\n- CMS : {context['cms']}\n- Objectif SEO : {context['goal_seo']}\n- Description : {context['description']}\n\n## Mots-cl\u00e9s\n{kw_list}\n\n## Concurrents\n{comp_list}\n\n## Ton\n{context['tone']}\n\n## CTA\n{context['cta']} \u2192 {context['cta_url']}",
        "content-writer": f"# Content Writer \u2014 {context['label']}\n\n## Mission\nR\u00e9diger des articles SEO pour **{context['label']}** ({context['domain']}).\n\n## Standards\n- Ton : {context['tone']}\n- Audience : {context['audience']}\n- 800-1200 mots, fran\u00e7ais\n- Hook puissant, voix active, pas de filler\n- 6+ gras, 3+ italique, 1 citation, 1 liste\n- Keyword dans les 100 premiers mots + 2 H2\n\n## Mots-cl\u00e9s\n{kw_list}\n\n## CTA\n{context['cta']} \u2192 {context['cta_url']}",
        "seo-strategist": f"# SEO Strategist \u2014 {context['label']}\n\n## Mission\nBriefs SEO pour **{context['label']}** ({context['domain']}).\n\n## Objectif\n{context['goal_seo']}\n\n## Mots-cl\u00e9s cibles\n{kw_list}\n\n## Concurrents\n{comp_list}\n\n## Brief \u00e0 produire\n1. H1 + H2/H3\n2. Meta title \u226460 chars\n3. Meta desc \u2264155 chars\n4. Secondary keywords\n5. Internal links plan\n6. Schema type",
        "quality-editor": f"# Quality Editor \u2014 {context['label']}\n\n## Mission\nContr\u00f4le qualit\u00e9 /100 pour **{context['label']}**.\n\n## Scoring\n1. Substance (25pts)\n2. Exactitude (20pts)\n3. Lisibilit\u00e9 (20pts)\n4. SEO (20pts)\n5. Engagement (15pts)\n\nSeuil : 70/100\nTon attendu : {context['tone']}\nAudience : {context['audience']}",
        "linkedin-specialist": f"# LinkedIn Specialist \u2014 {context['label']}\n\n## Page : {context['linkedin'] or context['label']}\n## Hashtags : {context['hashtags']}\n\n## R\u00e8gles\n- Post J+3 apr\u00e8s publication\n- Accroche forte + 2-3 paragraphes + URL + question\n- Max 2-3 emojis, ton pro et direct\n- 3 hashtags niche",
        "competitive-intel": f"# Competitive Intelligence \u2014 {context['label']}\n\n## Concurrents\n{comp_list}\n\n## RSS\n{'chr(10)'.join(context.get('rss_feeds', []))}\n\n## Mots-cl\u00e9s de r\u00e9f\u00e9rence\n{kw_list}",
        "visual-agent": f"# Visual Agent \u2014 {context['label']}\n\n## Sources\n1. ImageKit (si URL fournie)\n2. Unsplash (fallback)\n\n## Logo : {context['logo']}\n## Couleurs : {context['color']}, {context['color2']}",
        "internal-linking": f"# Internal Linking \u2014 {context['label']}\n\n## CMS : {context['cms']}\n## Mots-cl\u00e9s\n{kw_list}\n\n## R\u00e8gles\n- 3-7 liens internes par article\n- Anchor text naturel",
    }

    for agent_id, md_content in agents_templates.items():
        (skills_dir / f"{agent_id}.md").write_text(md_content)

    # Create RAG documents directory
    rag_docs = BASE_DIR / "tools" / "knowledge-rag" / "documents" / code
    rag_docs.mkdir(parents=True, exist_ok=True)

    # Copy skills to RAG
    import shutil
    for f in skills_dir.iterdir():
        if f.is_file():
            shutil.copy2(f, rag_docs / f.name)

    # Save context as RAG document
    (rag_docs / "site-context.md").write_text(
        f"# {context['label']} \u2014 Contexte\n\n"
        f"**URL** : {context['url']}\n"
        f"**Niche** : {context['niche']}\n"
        f"**Audience** : {context['audience']}\n"
        f"**Ton** : {context['tone']}\n"
        f"**Objectif SEO** : {context['goal_seo']}\n"
        f"**Description** : {context['description']}\n"
        f"**CTA** : {context['cta']} \u2192 {context['cta_url']}\n"
        f"**LinkedIn** : {context['linkedin']}\n"
        f"**Logo** : {context['logo']}\n"
        f"**Couleurs** : {context['color']}, {context['color2']}\n"
        f"\n## Mots-cl\u00e9s\n{kw_list}\n"
        f"\n## Concurrents\n{comp_list}\n"
    )

    # Also create empty tracking files
    (site_dir / "articles-published.md").write_text(f"# Articles publi\u00e9s \u2014 {context['label']}\n\n| Date | Slug | Titre |\n|---|---|---|\n")
    (site_dir / "keywords-targeted.md").write_text(f"# Keywords cibl\u00e9s \u2014 {context['label']}\n\n{kw_list}\n")

    return {
        "ok": True,
        "code": code,
        "skills_created": len(agents_templates),
        "rag_documents": len(list(rag_docs.iterdir())),
        "message": f"Site {context['label']} cr\u00e9\u00e9 avec {len(agents_templates)} agents contextualis\u00e9s"
    }


# ── CRM legacy endpoints supprimés le 2026-05-20 (remplacés par /api/sites/{site}/acquisition) ──
# Le webhook reste car Tally Forms pointe encore dessus (redirige vers acquisition_contacts).

@app.post("/api/crm/{site}/webhook")
async def api_crm_webhook(site: str, request: Request):
    """Webhook for forms (Tally + TidyCal). Insert dans acquisition_contacts avec state=lead."""
    data = await request.json()
    # Determine source
    source = "formulaire"
    if data.get("tidycal") or "tidycal" in str(data.get("source", "")):
        source = "tidycal"
    elif data.get("emelia"):
        source = "emelia"

    full_name = data.get("name", "")
    if full_name and not data.get("nom") and not data.get("prenom"):
        parts = full_name.strip().split(" ", 1)
        _prenom = parts[0] if parts else ""
        _nom = parts[1] if len(parts) > 1 else ""
    else:
        _prenom = data.get("prenom", data.get("firstName", ""))
        _nom = data.get("nom", data.get("lastName", ""))

    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.acquisition_backend import create as acq_create
    res = acq_create(site, {
        "nom":     _nom,
        "prenom":  _prenom,
        "email":   data.get("email", ""),
        "tel":     data.get("tel", data.get("phone", "")),
        "societe": data.get("societe", data.get("company", "")),
        "source":  source,
        "state":   "lead",  # remplir un formulaire = signal d'intérêt fort
        "notes":   data.get("message", data.get("notes", "")),
    }, by="webhook_form")
    contact_id = res.get("id", "")

    # Telegram notification
    try:
        import os
        tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
        if tg_token and tg_chat:
            msg = f"\U0001f4e5 *Nouveau contact ({site.upper()})*\n"
            msg += f"\u2022 {data.get('prenom','')} {data.get('nom','')}\n"
            msg += f"\u2022 {data.get('email','')}\n"
            msg += f"\u2022 Source: {source}"
            requests.post(f"https://api.telegram.org/bot{tg_token}/sendMessage",
                json={"chat_id": tg_chat, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except Exception:
        pass

    # Telegram alert
    _name = (data.get("prenom", data.get("firstName", "")) + " " + data.get("nom", data.get("name", ""))).strip()
    send_cheffer_telegram(
        f"\U0001f4e5 *Nouveau contact CRM*\n"
        f"\u2022 {_name}\n"
        f"\u2022 {data.get('email', '')}\n"
        f"\u2022 {data.get('societe', data.get('company', ''))}\n"
        f"\u2022 Source: {source}"
    )
    return {"ok": True, "id": contact_id, "source": source}

# Endpoint /api/sites/{site}/acquisition/{contact_id}/email supprim\u00e9 le 2026-05-21
# (Resend retir\u00e9 du projet \u2014 utiliser Emelia pour les envois en masse)


# ── Auth System ───────────────────────────────────────────────────────────────

def _real_ip(request: Request) -> str:
    """L'IP RÉELLE du client — celle que pose Nginx, jamais celle qu'envoie le client.

    Défaut corrigé le 2026-08-21 (revue de sécurité). L'ancienne version prenait la
    PREMIÈRE valeur de `X-Forwarded-For`. Or Nginx est configuré avec
    `$proxy_add_x_forwarded_for`, qui AJOUTE l'IP réelle À LA FIN de ce que le client a
    envoyé. La première valeur est donc entièrement contrôlée par le client : un attaquant
    changeait cet en-tête à chaque requête et obtenait un compteur anti-force-brute neuf à
    chaque fois — limite ET fail2ban contournés (démontré en test : 15 essais, 0 blocage).

    L'ordre de confiance, du plus sûr au moins sûr :

    1. **`X-Real-IP`** — Nginx le pose avec `proxy_set_header X-Real-IP $remote_addr`, ce
       qui ÉCRASE toute valeur reçue du client. C'est l'IP du pair TCP réel, non falsifiable
       tant que la requête passe par Nginx.
    2. **La DERNIÈRE valeur de `X-Forwarded-For`** — celle que Nginx a ajoutée en bout, donc
       le pair réel, si `X-Real-IP` venait à manquer.
    3. **Le pair de la socket** — dernier recours (accès direct hors proxy).

    Un seul proxy de confiance : Nginx. Si l'application était un jour exposée en direct,
    ces en-têtes redeviendraient falsifiables — mais alors le pair de la socket (3) serait
    la vraie IP, et le repli tomberait juste.
    """
    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        # La DERNIÈRE valeur = l'IP ajoutée par Nginx (le pair réel), pas la première.
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else ""


# ── Maintenance, statistiques hebdo, inventaire des bases ─────────────────────

@app.get("/api/maintenance")
async def api_maintenance_status():
    """État de maintenance. PUBLIC : la page de login l'interroge avant authentification."""
    import maintenance_backend as maint
    etat = maint.get_status()
    return {"enabled": etat["enabled"], "message": etat["message"],
            "since": etat.get("since"), "eta": etat.get("eta", "")}


@app.get("/api/admin/maintenance")
async def api_maintenance_get(request: Request):
    """État complet, avec l'auteur de la bascule (admin only via _ADMIN_PREFIXES)."""
    import maintenance_backend as maint
    return maint.get_status()


@app.post("/api/admin/maintenance")
async def api_maintenance_set(request: Request):
    """Active ou lève la maintenance (admin only via _ADMIN_PREFIXES)."""
    import maintenance_backend as maint
    sess = getattr(request.state, "session", None) or {}
    data = await request.json()
    etat = maint.set_status(
        bool(data.get("enabled")),
        message=data.get("message", ""),
        by=sess.get("username", "?"),
        eta=data.get("eta", ""),
    )
    try:
        import god_mode_backend as gm_log
        gm_log.log_action("system", sess.get("username", "?"), sess.get("user_id", ""),
                          "maintenance", resource="platform",
                          payload={"enabled": etat["enabled"], "eta": etat.get("eta", "")},
                          success=True)
    except Exception:
        pass
    return etat


# Périodes proposées par l'interface. Une valeur libre est ramenée à la plus proche : le
# tableau doit rester lisible, et une demande à 400 jours ferait un mur de chiffres.
_PERIODES_JOURS = (7, 15, 31)


@app.get("/api/sites/{site}/daily-stats")
async def api_daily_stats(site: str, request: Request, days: int = 7):
    """Les deux tableaux JOURNALIERS du tableau de bord : ce qui sort, ce qui entre.

    Deux jeux distincts et non un seul agrégat : mélanger envois et scraping est ce qui
    rendait la page illisible.
    """
    import dashboard_stats_backend as stats
    demande = int(days or 7)
    jours = min(_PERIODES_JOURS, key=lambda v: abs(v - demande))
    out = {"site": site, "jours_demandes": jours, "periodes": list(_PERIODES_JOURS)}
    try:
        out["emails"] = stats.daily_email_stats(site, jours)
    except Exception as e:  # noqa: BLE001
        out["emails"] = {"jours": [], "erreur": str(e)[:200]}
    try:
        out["scraping"] = stats.daily_scraping_stats(site, jours)
    except Exception as e:  # noqa: BLE001
        out["scraping"] = {"jours": [], "erreur": str(e)[:200]}
    return out


@app.get("/api/admin/database")
async def api_database_inventory(request: Request):
    """Toutes les bases, leurs tables et le nombre de lignes (admin only)."""
    import dashboard_stats_backend as stats
    return stats.database_inventory()


@app.post("/api/auth/login")
async def api_auth_login(request: Request):
    """Login username/password (+ TOTP optional). Returns session token or {mfa_required}."""
    data = await request.json()
    client_ip = _real_ip(request)
    result = auth_login(
        data.get("username", ""),
        data.get("password", ""),
        totp_code=data.get("totp_code", ""),
        ip=client_ip,
    )
    from fastapi.responses import JSONResponse
    if result.get("error") == "rate_limit":
        return JSONResponse(status_code=429, content=result)
    if result.get("error") == "invalid_credentials":
        return JSONResponse(status_code=401, content=result)
    if result.get("error") in ("invalid_totp", "mfa_misconfigured"):
        return JSONResponse(status_code=401, content=result)
    if result.get("mfa_required"):
        return {"mfa_required": True}

    # Maintenance : le contrôle est ici et pas seulement dans l'UI. Sans lui, un onglet déjà
    # ouvert ou un appel direct à l'API continuerait de faire entrer tout le monde.
    # Les admins passent toujours — sinon plus personne ne peut lever la maintenance.
    try:
        import maintenance_backend as _maint
        if not _maint.login_allowed(result.get("role", "")):
            auth_logout(result.get("token", ""))  # pas de session en suspens
            etat = _maint.get_status()
            return JSONResponse(status_code=503, content={
                "error": "maintenance", "message": etat["message"],
                "since": etat.get("since"), "eta": etat.get("eta", "")})
    except ImportError:
        pass

    # Succès : on log aussi dans la table login_logs DuckDB pour compat dashboard
    user_agent = request.headers.get("user-agent", "")[:100]
    auth_log_login(result.get("user_id", ""), result.get("username", ""), client_ip, user_agent)
    return {"ok": True, **result}

@app.post("/api/auth/logout")
async def api_auth_logout(request: Request):
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        auth_logout(auth[7:])
    return {"ok": True}

@app.get("/api/auth/me")
async def api_auth_me(request: Request):
    """Check current session."""
    auth = request.headers.get("authorization", "")
    token = request.cookies.get("genesis_token", "")
    session_token = auth[7:] if auth.startswith("Bearer ") else token
    if not session_token:
        return {"error": "not authenticated"}
    user = auth_verify(session_token)
    if not user:
        return {"error": "session expired"}
    return {"ok": True, **user}

@app.get("/api/auth/users")
async def api_auth_users():
    """List all users (admin only)."""
    return {"users": auth_list_users()}

@app.post("/api/auth/users")
async def api_auth_create(request: Request):
    """Crée un user (superadmin). Génère un mot de passe temporaire si absent, accepte
    role + 1 site + phone, et renvoie le mdp en clair + un bloc d'accès copiable
    (à transmettre par un canal hors-email). Telegram optionnel."""
    import secrets, json as _json
    data = await request.json()
    username = (data.get("username") or "").strip()
    if not username:
        return {"error": "username requis"}
    role = data.get("role") or "commercial"
    password = data.get("password") or secrets.token_urlsafe(9)  # mdp temp si non fourni

    # Sites : exactement 1 pour les non-superadmin
    sites = data.get("sites")
    if isinstance(sites, list):
        sites_json = _json.dumps(sites)
    elif isinstance(sites, str) and sites.strip():
        sites_json = sites
    else:
        sites_json = "[]"
    if role != "superadmin":
        try:
            arr = _json.loads(sites_json)
        except Exception:
            arr = []
        if len(arr) != 1:
            return {"error": "un utilisateur non-superadmin doit avoir exactement 1 site"}

    uid = auth_create_user(
        username, password, role=role,
        nom=data.get("nom", ""), prenom=data.get("prenom", ""),
        email=data.get("email", ""), phone=data.get("phone", ""),
        sites=sites_json,
    )
    if not uid:
        return {"error": "username already exists"}

    login_url = "https://api.cheffer.email"
    access_text = (
        "Acces Genesis\n"
        "--------------------\n"
        f"URL : {login_url}\n"
        f"Identifiant : {username}\n"
        f"Mot de passe : {password}\n\n"
        "Securite - active la double authentification (obligatoire) :\n"
        "1. Connecte-toi, menu en bas -> Securite (MFA).\n"
        "2. Clique Activer MFA : un QR code s'affiche.\n"
        "3. Scanne-le avec Google Authenticator / Authy / 1Password.\n"
        "4. Saisis le code a 6 chiffres pour valider.\n"
        "A la prochaine connexion, le code 2FA te sera demande."
    )
    telegram_sent = False
    if data.get("phone"):
        try:
            telegram_sent = auth_send_telegram(data["phone"], username, password)
        except Exception:
            telegram_sent = False
    return {"ok": True, "id": uid, "username": username, "password": password,
            "access_text": access_text, "telegram_sent": telegram_sent}

@app.delete("/api/auth/users/{user_id}")
async def api_auth_delete(user_id: str):
    auth_delete_user(user_id)
    return {"ok": True}


# ── MFA TOTP ──────────────────────────────────────────────────────────────────

@app.post("/api/auth/mfa/setup-start")
async def api_mfa_setup_start(request: Request):
    """Démarre l'enrôlement MFA pour l'utilisateur connecté.
    Retourne {secret, uri} — le client affiche le QR à partir de l'URI otpauth://."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    sess = auth_verify(token) if token else None
    if not sess:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"error": "not authenticated"})
    from scripts.auth_backend import mfa_setup_start
    return mfa_setup_start(sess["user_id"])


@app.post("/api/auth/mfa/setup-confirm")
async def api_mfa_setup_confirm(request: Request):
    """Valide un code TOTP après scan QR → active le MFA pour cet utilisateur."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    sess = auth_verify(token) if token else None
    if not sess:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"error": "not authenticated"})
    data = await request.json()
    from scripts.auth_backend import mfa_setup_confirm
    result = mfa_setup_confirm(sess["user_id"], data.get("totp_code", ""))
    if result.get("error"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content=result)
    return result


@app.post("/api/auth/mfa/disable")
async def api_mfa_disable(request: Request):
    """Désactive le MFA. Doit fournir le mot de passe pour confirmation."""
    sess = getattr(request.state, "session", None)
    if not sess:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"error": "not authenticated"})
    data = await request.json()
    # Confirme avec mdp
    confirm = auth_login(sess["username"], data.get("password", ""), ip=_real_ip(request))
    if not confirm.get("ok") and not confirm.get("token"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"error": "password required"})
    from scripts.auth_backend import mfa_disable
    return mfa_disable(sess["user_id"])

# ── Site API Keys ─────────────────────────────────────────────────────────────

SITE_KEYS_FILE = BASE_DIR / "memory" / "site-api-keys.json"

@app.get("/api/sites/{site}/api-keys")
async def api_site_keys(site: str):
    """Get API keys for a site."""
    keys = json.loads(SITE_KEYS_FILE.read_text()) if SITE_KEYS_FILE.exists() else {}
    site_keys = keys.get(site, {})
    return {"site": site, "keys": site_keys}

@app.post("/api/sites/{site}/api-keys")
async def api_site_create_key(site: str, request: Request):
    """Create or regenerate an API key for a site connector."""
    data = await request.json()
    connector = data.get("connector", "webhook")

    import secrets as _sec
    new_key = _sec.token_urlsafe(32)

    keys = json.loads(SITE_KEYS_FILE.read_text()) if SITE_KEYS_FILE.exists() else {}
    if site not in keys:
        keys[site] = {}
    keys[site][connector] = {
        "key": new_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "connector": connector,
    }
    SITE_KEYS_FILE.write_text(json.dumps(keys, indent=2, ensure_ascii=False))
    return {"ok": True, "connector": connector, "key": new_key}

@app.delete("/api/sites/{site}/api-keys/{connector}")
async def api_site_delete_key(site: str, connector: str):
    """Revoke an API key."""
    keys = json.loads(SITE_KEYS_FILE.read_text()) if SITE_KEYS_FILE.exists() else {}
    if site in keys and connector in keys[site]:
        del keys[site][connector]
        SITE_KEYS_FILE.write_text(json.dumps(keys, indent=2, ensure_ascii=False))
    return {"ok": True}


@app.get("/api/seo/credits-log")
async def api_ahrefs_credits_log():
    """Return Ahrefs credits usage log with period breakdown."""
    from datetime import timedelta
    entries = []
    if COSTS_FILE.exists():
        try:
            data = json.loads(COSTS_FILE.read_text())
            all_entries = data if isinstance(data, list) else data.get("entries", [])
            entries = [e for e in all_entries if "seo" in str(e.get("module","")) or "ahrefs" in str(e.get("model",""))]
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    d7 = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    d30 = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    d365 = (now - timedelta(days=365)).strftime("%Y-%m-%d")

    w7 = [e for e in entries if e.get("date","") >= d7]
    w30 = [e for e in entries if e.get("date","") >= d30]
    w365 = [e for e in entries if e.get("date","") >= d365]

    return {
        "periods": {
            "7j": {"credits": sum(e.get("input_tok",0) for e in w7), "actions": len(w7)},
            "30j": {"credits": sum(e.get("input_tok",0) for e in w30), "actions": len(w30)},
            "1an": {"credits": sum(e.get("input_tok",0) for e in w365), "actions": len(w365)},
        },
        "log": [{"date": e.get("date",""), "action": e.get("action",""), "units": e.get("input_tok",0), "note": e.get("note","")} for e in reversed(entries[-100:])]
    }


@app.post("/api/editorial/{article_id}/auto-revise")
async def api_editorial_auto_revise(article_id: str):
    """Send article + QC feedback to DeepSeek for automatic revision."""
    queue_file = BASE_DIR / "memory" / "editorial" / "articles-queue.json"
    if not queue_file.exists():
        return {"error": "no queue"}

    queue = json.loads(queue_file.read_text())
    art = next((a for a in queue if a["id"] == article_id), None)
    if not art:
        return {"error": "not found"}

    art["status"] = "writing"
    art["updated_at"] = datetime.now(timezone.utc).isoformat()
    queue_file.write_text(json.dumps(queue, indent=2, ensure_ascii=False))

    # Launch revision in background
    subprocess.Popen(
        ["python3", "scripts/editorial_reviser.py", "--id", article_id],
        cwd=str(BASE_DIR),
        stdout=open(str(BASE_DIR / f"memory/editorial/{article_id}-revision.log"), "w"),
        stderr=subprocess.STDOUT,
    )
    return {"ok": True, "message": "Revision DeepSeek lancée"}


# ── Campaign Management ───────────────────────────────────────────────────────

@app.get("/api/campaign/sectors")
async def api_campaign_sectors():
    """Get prospect count by sector."""
    return emelia_sectors()

@app.get("/api/campaign/prospects/{sector}")
async def api_campaign_prospects(sector: str, limit: int = 50):
    """Get prospects for a sector."""
    prospects = emelia_prospects(sector, limit)
    return {"sector": sector, "count": len(prospects), "prospects": prospects[:10]}

@app.post("/api/campaign/prepare")
async def api_campaign_prepare(request: Request):
    """Prepare a campaign: DeepSeek generates personalized email sequence."""
    data = await request.json()
    sector = data.get("sector", "retail")
    volume = data.get("volume", 50)
    email_count = data.get("emailCount", 2)
    relance_delay = data.get("relanceDelay", 3)
    prospects = emelia_prospects(sector, volume)

    # Load cold email rules
    rules_file = BASE_DIR / "context" / "shared" / "cold-email-rules.md"
    rules = rules_file.read_text()[:800] if rules_file.exists() else ""

    # Generate with DeepSeek
    import os
    dk_key = os.environ.get("DEEPSEEK_API_KEY", "")
    # Load RAG cold email knowledge
    rag_context = ""
    rag_files = [
        BASE_DIR / "memory" / "rag" / "cold-email" / "cahier_cold_email_v2.md",
        BASE_DIR / "memory" / "rag" / "cold-email" / "base_connaissance_cold_email_rag.md",
        BASE_DIR / "memory" / "rag" / "cold-email" / "lcr_site_knowledge.md",
    ]
    for rag_file in rag_files:
        if rag_file.exists():
            text = rag_file.read_text()
            # Extract hard rules and relevant chunks for the sector
            # Take the first 2000 chars of cahier (rules) + search for sector in RAG
            if "lcr_site_knowledge" in str(rag_file):
                # Extract the chunk matching the selected sector
                sector_map = {
                    "immobilier": "secteur_immobilier",
                    "restaurant": "secteur_restauration",
                    "hotel": "secteur_restauration",
                    "auto": "secteur_automobile",
                    "beaute": "secteur_beaute",
                    "retail": "secteur_retail",
                }
                # Always include general offer
                for chunk_id in ["lcr.offre_generale", "lcr.fonctionnalites"]:
                    idx = text.find("## chunk:" + chunk_id)
                    if idx >= 0:
                        end = text.find("## chunk:", idx + 10)
                        rag_context += text[idx:end if end > 0 else idx + 800] + "\n\n"
                # Include sector-specific chunk
                for sect_key, chunk_suffix in sector_map.items():
                    if sect_key in sector.lower():
                        idx = text.find("## chunk:lcr." + chunk_suffix)
                        if idx >= 0:
                            end = text.find("## chunk:", idx + 10)
                            rag_context += text[idx:end if end > 0 else idx + 1000] + "\n\n"
                        break
            elif "cahier" in str(rag_file):
                # Extract hard_rules section and mode operatoire
                for section in ["hard_rules", "Mode op", "Checklist", "INTERDIT"]:
                    idx = text.find(section)
                    if idx >= 0:
                        rag_context += text[max(0, idx-50):idx+800] + "\n\n"
            else:
                # Search for relevant chunks — prioritize critical ones
                chunks = text.split("## chunk:")
                # Priority 1: icebreaker, objet, cta, sequence structure, checklist
                priority_kw = ["icebreaker", "objet_regles", "objet_formule", "cta_principe", "sequence.structure", "mots_a_bannir", "template_maitre", "checklist_finale", "corps_longueur"]
                # Priority 2: redaction, framework
                secondary_kw = ["framework_pas", "framework_aida", "signature", "ton_par_audience", "salutation"]

                for chunk in chunks:
                    chunk_lower = chunk.lower()
                    if any(kw in chunk_lower for kw in priority_kw):
                        rag_context += "## chunk:" + chunk[:500] + "\n\n"

                for chunk in chunks:
                    chunk_lower = chunk.lower()
                    if any(kw in chunk_lower for kw in secondary_kw) and len(rag_context) < 6000:
                        rag_context += "## chunk:" + chunk[:400] + "\n\n" 

    prompt = f"""Tu es un expert en cold email B2B. Tu dois respecter STRICTEMENT les règles ci-dessous.

=== BASE DE CONNAISSANCES COLD EMAIL ===
{rag_context[:8000]}

=== MISSION ===

LIENS SECTEUR LECLIENTROI (a inclure dans l'email) :
Les URLs secteurs sont :
- immobilier : https://leclientroi.com/secteurs/immobilier
- restaurant : https://leclientroi.com/secteurs/sms-restauration
- automobile : https://leclientroi.com/secteurs/sms-automobile
- beaute : https://leclientroi.com/secteurs/beaute-bien-etre
- retail : https://leclientroi.com/secteurs/sms-retail-franchise
- services : https://leclientroi.com/secteurs/services-personne
- homepage : https://leclientroi.com

L'email initial DOIT contenir un lien vers la page secteur correspondante.
La relance DOIT contenir un lien vers la homepage ou la page secteur.

G\u00e9n\u00e8re {email_count} email{"s" if email_count > 1 else ""} pour des entreprises du secteur "{sector}".

CONTEXTE :
- Entreprise : LeClientROI (leclientroi.com) - solution SMS marketing pour entreprises
- CTA : lien TidyCal https://tidycal.com/1rr6kv1/15-minute-meeting

FORMAT HTML OBLIGATOIRE :
- Chaque paragraphe dans un <p> distinct (pas tout dans un seul bloc)
- Sauts de ligne entre les paragraphes
- Le lien TidyCal doit être un <a href="...">texte du lien</a>
- TOUJOURS inclure en fin d'email un lien vers la page secteur : <a href="URL_SECTEUR">Découvrir notre solution pour SECTEUR</a>
- TOUJOURS terminer avec la signature HTML ci-dessous (ne pas l'inventer)

SIGNATURE OBLIGATOIRE (copier tel quel en fin d'email) :
<p style="margin-top:16px;font-size:13px;color:#555">
Camille<br>
<strong>LeClientROI</strong> — SMS géolocalisés pour commerces de proximité<br>
<a href="https://leclientroi.com" style="color:#6468f0">leclientroi.com</a> | <a href="https://leclientroi.com" style="color:#6468f0">Inscription gratuite</a>
</p>

R\u00c8GLES STRICTES :
- Ton humain, direct, PAS corporate
- JAMAIS : "je me permets", "j'esp\u00e8re que vous allez bien", "je prends la libert\u00e9"
- JAMAIS d'emoji dans l'objet
- Max 150 mots par email
- 1 seul CTA par email (lien TidyCal)
- Icebreaker : commencer par un fait concret li\u00e9 au secteur {sector}
- Email 1 (J+0) : icebreaker + proposition de valeur + CTA
- Email 2 (J+3) : relance courte + preuve sociale
- Email 3 (J+7) : derni\u00e8re relance, bref et respectueux

VARIABLES DISPONIBLES :
- {{{{firstName}}}} : pr\u00e9nom du prospect
- {{{{field1}}}} : nom de l'entreprise

R\u00e8gles pour les relances :
- PAS de "je me permets de relancer"
- Chaque relance : nouvel angle (preuve sociale, chiffre, question directe)
- Inclure un lien vers la homepage ou la page secteur
- Relances plus courtes que l email initial (max 80 mots)
- D\u00e9lai entre relances : {relance_delay} jours

R\u00e9ponds UNIQUEMENT en JSON valide (un tableau de {email_count} emails) :
[
  {{"subject": "objet email 1", "body_html": "<p>corps</p>", "delay_days": 0}}
  // ajouter les relances si email_count > 1
]

Chaque email a : subject, body_html, delay_days (0 pour le premier, {relance_delay} pour le 2e, {relance_delay}*2 pour le 3e)"""

    try:
        r2 = requests.post("https://api.deepseek.com/chat/completions", json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 2000,
        }, headers={"Authorization": f"Bearer {dk_key}", "Content-Type": "application/json"}, timeout=90)
        r2.raise_for_status()
        text = r2.json()["choices"][0]["message"]["content"].strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        emails = json.loads(text)
        if isinstance(emails, dict):
            # Single email or {email, relance} format
            if "email" in emails:
                emails = [emails["email"]]
                if "relance" in emails:
                    emails.append(emails["relance"])
            else:
                emails = [emails]
        # Ensure it's a list
        if not isinstance(emails, list):
            emails = [emails]
    except Exception as e:
        emails = [{
            "subject": "SMS g\u00e9olocalis\u00e9 pour {{field1}}",
            "body_html": "<p>Bonjour {{firstName}},</p><p>LeClientROI met \u00e0 votre disposition 18 millions de prospects g\u00e9olocalis\u00e9s autour de votre \u00e9tablissement.</p><p><a href=\"https://leclientroi.com\">D\u00e9couvrir LeClientROI</a></p>",
            "delay_days": 0,
        }]

    # Post-process HTML: ensure proper paragraphs + append signature
    # Signature en TEXTE : une image distante dans la signature est un marqueur fort
    # pour les filtres, et elle n'apporte rien qu'un texte ne fasse (guide Maildoso).
    signature = ('<p>Juliette<br>LeClientROI</p>'
                 '<p><a href="{{UNSUBSCRIBE_LINK}}" rel="noopener noreferrer" target="_blank">'
                 "Si vous ne souhaitez plus recevoir d'email de ma part, cliquez ici</a></p>")

    # Remove any signature DeepSeek might have generated
    for em in emails:
        body = em.get("body_html", "")
        # Remove DeepSeek signature attempts (Camille + LeClientROI at the end)
        import re
        body = re.sub(r"<p[^>]*>\s*Camille\s*<br.*?</p>", "", body, flags=re.DOTALL)
        body = re.sub(r"Camille\s*<br>\s*<strong>LeClientROI</strong>.*?</p>", "", body, flags=re.DOTALL)
        body = re.sub(r"Camille\n.*?LeClientROI.*?Inscription gratuite.*", "", body, flags=re.DOTALL)
        em["body_html"] = body.strip()

    for em in emails:
        body = em.get("body_html", "")
        # If body doesn't have <p> tags, wrap paragraphs
        if "<p>" not in body:
            paragraphs = body.split("\n\n")
            body = "".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())
        # Replace bare \n with <br> inside <p> tags
        body = body.replace("\n", "<br>")
        # Append signature
        body = body + signature
        em["body_html"] = body

    # Build Emelia steps
    steps = []
    for i, em in enumerate(emails[:email_count]):
        delay = em.get("delay_days", i * relance_delay) if i > 0 else 0
        steps.append({
            "delay": {"amount": delay, "unit": "DAYS" if delay > 0 else "MINUTES"},
            "versions": [{
                "subject": em.get("subject", ""),
                "disabled": False,
                "message": em.get("body_html", ""),
                "rawHtml": True,
                "attachments": [],
            }],
        })

    return {
        "sector": sector,
        "volume": len(prospects),
        "steps": steps,
        "preview_contacts": prospects[:5],
        "generated_by": "deepseek",
    }

@app.post("/api/campaign/launch")
async def api_campaign_launch(request: Request):
    """Create campaign on Emelia, add contacts, configure steps. Does NOT start."""
    data = await request.json()
    sector = data.get("sector", "retail")
    volume = data.get("volume", 50)
    steps = data.get("steps")  # Modified steps from user
    name = data.get("name", f"LCR-{sector.upper()}-{datetime.now().strftime('%b%Y')}")

    try:
        # 1. Use existing campaign or create new one
        existing_id = data.get("campaignId", "")
        if existing_id:
            campaign_id = existing_id
        else:
            campaign = emelia_create(name)
            resp = campaign.get("campaign", campaign)
            campaign_id = resp.get("_id") or resp.get("id") or campaign.get("_id", "")
            if not campaign_id:
                return {"error": "Failed to create campaign", "response": campaign}
            # Configure steps on new campaign
            if steps:
                emelia_steps(campaign_id, steps)
            else:
                emelia_steps(campaign_id, emelia_default_steps(sector))

        # 4. Add contacts
        prospects = emelia_prospects(sector, volume)
        added = 0
        for p in prospects:
            ok = emelia_add_contact(campaign_id, {
                "email": p["email"],
                "firstName": p.get("firstName", ""),
                "lastName": p.get("lastName", ""),
                "field1": p.get("company", ""),
            })
            if ok:
                added += 1

        return {
            "ok": True,
            "campaign_id": campaign_id,
            "name": name,
            "contacts_added": added,
            "message": f"Campagne '{name}' creee avec {added} contacts. Allez sur Emelia pour la demarrer."
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/campaign/all-stats")
async def api_campaign_all_stats():
    """Get stats for all Emelia campaigns."""
    try:
        campaigns = emelia_list()
        return {"campaigns": campaigns}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/campaign/create-draft")
async def api_campaign_create_draft(request: Request):
    """Create campaign on Emelia, configure settings + steps. Does NOT add contacts."""
    data = await request.json()
    name = data.get("name", "LCR-Campaign")
    settings = data.get("settings", {})
    steps = data.get("steps", [])

    import os
    EMELIA_KEY = os.environ.get("EMELIA_API_KEY", "")
    EMELIA_URL = "https://api.emelia.io"
    H = {"Authorization": EMELIA_KEY, "Content-Type": "application/json"}

    try:
        # 1. Create campaign
        r = requests.post(EMELIA_URL + "/emails/campaigns", headers=H, json={"name": name}, timeout=15)
        r.raise_for_status()
        camp_data = r.json()
        campaign_id = camp_data.get("campaign", {}).get("_id") or camp_data.get("_id", "")
        if not campaign_id:
            return {"error": "No campaign ID returned", "response": camp_data}

        # 2. Settings — schedule is configured via Emelia dashboard (API /settings returns 404)
        # Skip settings PATCH — not supported by current API

        # 3. Configure steps (emails)
        if steps:
            r3 = requests.patch(EMELIA_URL + f"/emails/campaigns/{campaign_id}/steps", headers=H, json={"steps": steps}, timeout=15)
            if r3.status_code != 200:
                return {"error": f"Steps failed: {r3.status_code}", "detail": r3.text[:200]}

        return {"ok": True, "campaign_id": campaign_id, "name": name}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/campaign/send-test")
async def api_campaign_send_test(request: Request):
    """Send a test email (BAT) via Emelia."""
    data = await request.json()
    campaign_id = data.get("campaignId", "")
    email = data.get("email", "")

    if not campaign_id or not email:
        return {"error": "campaignId and email required"}

    import os
    EMELIA_KEY = os.environ.get("EMELIA_API_KEY", "")
    EMELIA_URL = "https://api.emelia.io"
    H = {"Authorization": EMELIA_KEY, "Content-Type": "application/json"}

    try:
        step = data.get("step", 0)
        r = requests.post(EMELIA_URL + "/emails/test", headers=H, json={"campaignId": campaign_id, "email": email, "step": step}, timeout=15)
        if r.status_code == 200:
            return {"ok": True, "message": f"Test envoy\u00e9 \u00e0 {email}"}
        else:
            return {"error": f"Emelia returned {r.status_code}", "detail": r.text[:200]}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/campaign/stats/{campaign_id}")
async def api_campaign_stats_single(campaign_id: str):
    """Get stats for a single campaign."""
    import os
    EMELIA_KEY = os.environ.get("EMELIA_API_KEY", "")
    H = {"Authorization": EMELIA_KEY, "Content-Type": "application/json"}

    try:
        r = requests.get(f"https://api.emelia.io/stats?campaignId={campaign_id}", headers=H, timeout=15)
        if r.status_code == 200:
            return {"ok": True, "stats": r.json()}
        return {"error": f"Status {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/campaigns/{campaign_id}/stats")
def get_campaign_stats_flat(campaign_id: str):
    """Stats Emelia d'une campagne, a plat (mailsSent, uniqueOpensPercent, ...) — consomme par /site/[code]/campaigns."""
    try:
        key = load_env().get("EMELIA_API_KEY", "")
        H = {"Authorization": key, "Content-Type": "application/json"}
        r = requests.get(f"https://api.emelia.io/stats?campaignId={campaign_id}", headers=H, timeout=15)
        if r.status_code == 200:
            return r.json()
        return {"error": f"emelia status {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


# ── PRM endpoints supprimés le 2026-05-20 (remplacés par /api/sites/{site}/acquisition) ──

@app.get("/api/campaigns/list-with-stats")
async def api_campaigns_with_stats():
    """List all Emelia campaigns with their stats."""
    import os
    EMELIA_KEY = os.environ.get("EMELIA_API_KEY", "")
    H = {"Authorization": EMELIA_KEY, "Content-Type": "application/json"}

    try:
        r = requests.get("https://api.emelia.io/emails/campaigns", headers=H, timeout=15)
        camps = r.json().get("campaigns", [])

        results = []
        for c in camps:
            cid = c.get("_id", "")
            # Get stats
            stats = {}
            try:
                r2 = requests.get(f"https://api.emelia.io/stats?campaignId={cid}", headers=H, timeout=10)
                if r2.status_code == 200:
                    stats = r2.json()
            except Exception:
                pass

            results.append({
                "id": cid,
                "name": c.get("name", ""),
                "status": c.get("status", "DRAFT"),
                "createdAt": c.get("createdAt", ""),
                "steps": len(c.get("steps", [])),
                "recipients": c.get("recipients", 0),
                "stats": {
                    "sent": stats.get("mailsSent", 0),
                    "opens": stats.get("uniqueOpensPercent", 0),
                    "clicks": stats.get("linkClickedPercent", 0),
                    "replies": stats.get("repliedPercent", 0),
                    "bounces": stats.get("bouncedPercent", 0),
                    "unsubscribes": stats.get("unsubscribePercent", 0),
                    "progress": stats.get("progressPercent", 0),
                },
            })

        return {"campaigns": results}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/campaigns/{campaign_id}/start")
async def api_campaign_start(campaign_id: str):
    import os
    EMELIA_KEY = os.environ.get("EMELIA_API_KEY", "")
    H = {"Authorization": EMELIA_KEY, "Content-Type": "application/json"}
    r = requests.post(f"https://api.emelia.io/emails/campaigns/{campaign_id}/start", headers=H, timeout=15)
    return {"ok": r.status_code == 200, "status": r.status_code}


@app.post("/api/campaigns/{campaign_id}/pause")
async def api_campaign_pause(campaign_id: str):
    import os
    EMELIA_KEY = os.environ.get("EMELIA_API_KEY", "")
    H = {"Authorization": EMELIA_KEY, "Content-Type": "application/json"}
    r = requests.post(f"https://api.emelia.io/emails/campaigns/{campaign_id}/pause", headers=H, timeout=15)
    return {"ok": r.status_code == 200, "status": r.status_code}


# cache nom de campagne Emelia -> _id (les webhooks Emelia n'envoient que le nom)
_emelia_camp_id_cache: dict = {}


@app.post("/api/emelia/webhook")
async def api_emelia_webhook(request: Request):
    """Receive Emelia webhook events: opened, clicked, replied, bounced.
    Injects contacts into PRM for lcr site."""
    data = await request.json()

    # Emelia sends events like: {event: "OPENED"|"opened", contact: {email, firstName, ...}, campaign: "name-str" | {name, ...}}
    event_type = (data.get("event") or data.get("type") or "").lower()  # normalise UPPERCASE/lowercase
    contact = data.get("contact", data.get("data", {}).get("contact", {})) or {}
    campaign_raw = data.get("campaign", data.get("data", {}).get("campaign", {}))
    # Emelia peut envoyer campaign en string (le nom) ou en dict {name, _id}
    campaign = {"name": campaign_raw} if isinstance(campaign_raw, str) else (campaign_raw or {})

    email = contact.get("email", "")
    if not email:
        return {"ok": False, "error": "no email"}

    # === Log audit TOUS les events Emelia (incl. SENT/OPENED) ===
    try:
        import duckdb as _dd, uuid as _uuid, json as _json
        from datetime import datetime as _dt
        camp_name = campaign.get("name", "") if isinstance(campaign, dict) else str(campaign)
        # site detect via campaign name
        site_detect = "lcr"
        cn = (camp_name or "").upper()
        if cn.startswith("MKD") or "MKD-" in cn:
            site_detect = "mkd"
        elif cn.startswith("LCR") or "LCR-" in cn or "LECLIENTROI" in cn.replace(" ", ""):
            site_detect = "lcr"
        # Résout campaign name -> _id (payload Emelia = nom string, jamais l'id).
        # Sans ça, campaign_id reste vide et /api/campaigns/{id}/stats-by-day ne matche rien.
        camp_id = campaign.get("_id", "") if isinstance(campaign, dict) else ""
        if not camp_id and camp_name:
            camp_id = _emelia_camp_id_cache.get(camp_name, "")
            if not camp_id:
                try:
                    import workflow_emelia_push as _wep
                    _key = _wep._get_key(site_detect)
                    if _key:
                        for _cmp in _wep.list_campaigns(_key):
                            _nm, _cid = _cmp.get("name") or "", _wep._camp_id(_cmp) or ""
                            if _nm and _cid:
                                _emelia_camp_id_cache[_nm] = _cid
                        camp_id = _emelia_camp_id_cache.get(camp_name, "")
                except Exception:
                    pass
        _c = _dd.connect(str(BASE_DIR / "data" / "god_mode.duckdb"))
        try:
            emelia_date_str = data.get("date", "")
            emelia_date = None
            if emelia_date_str:
                try:
                    emelia_date = _dt.fromisoformat(emelia_date_str.replace("Z", "+00:00"))
                except Exception:
                    pass
            _c.execute("""INSERT INTO emelia_events
                (id, event_type, email, first_name, last_name, campaign_name, campaign_id, site_code, step, emelia_date, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [str(_uuid.uuid4()), event_type.upper(), email,
                 contact.get("firstName", ""), contact.get("lastName", ""),
                 camp_name, camp_id,
                 site_detect, data.get("step", 0), emelia_date, _json.dumps(data, ensure_ascii=False)])
        finally:
            _c.close()
    except Exception as _e:
        print(f"[emelia_webhook] audit log failed: {_e}")

    # Determine action
    action_map = {"opened": "opened", "clicked": "clicked", "replied": "replied", "bounced": "bounced", "unsubscribed": "unsubscribed",
                  "email_opened": "opened", "email_clicked": "clicked", "email_replied": "replied", "email_bounced": "bounced"}
    action = action_map.get(event_type, event_type or "unknown")

    # Insère/promote dans acquisition_contacts (default site: lcr)
    site = "lcr"
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.acquisition_backend import create as acq_create, find_by_email as acq_find, change_state as acq_change_state, STATE_RANK
    # action → state cible : click→prm, reply→lead, bounce/unsub→blacklisted, open=ignore
    state_map = {"opened": None, "clicked": "prm", "replied": "lead", "bounced": "blacklisted", "unsubscribed": "blacklisted"}
    target_state = state_map.get(action)
    if target_state:
        existing = acq_find(site, email)
        if existing:
            if STATE_RANK.get(target_state, 0) > STATE_RANK.get(existing["state"], 0) and existing["state"] != "blacklisted":
                acq_change_state(site, existing["id"], target_state, by="emelia_webhook", note=f"campaign={campaign.get('name','')} action={action}")
        else:
            acq_create(site, {
                "email":   email,
                "prenom":  contact.get("firstName", ""),
                "nom":     contact.get("lastName", ""),
                "societe": contact.get("company", contact.get("custom", {}).get("companyName", "")),
                "notes":   f"emelia webhook campaign={campaign.get('name','')} action={action}",
                "state":   target_state,
                "source":  f"emelia:{campaign.get('name','')}"[:60],
            }, by="emelia_webhook")

    # === DUAL-WRITE 2026-05-22 : alimente AUSSI le pool mutualisé contacts.duckdb ===
    # Webhook events depuis Emelia → update contact_site_history + global_blacklist si applicable
    try:
        import contacts_pool_backend as cpb_pool
        # 1. Assurer la présence du contact dans le pool
        pool_cid = cpb_pool.create_in_pool({
            "email":   email,
            "prenom":  contact.get("firstName", ""),
            "nom":     contact.get("lastName", ""),
            "societe": contact.get("company", contact.get("custom", {}).get("companyName", "")),
        }, primary_source="serper")  # source par défaut webhook = scraped via Emelia
        if pool_cid:
            # 2. Record l'event raw
            cpb_pool.record_emelia_event(pool_cid, site, event_type.upper())
            # 3. Update state si applicable
            if target_state:
                cpb_pool.change_state_for_site(pool_cid, site, target_state,
                    by="emelia_webhook",
                    note=f"campaign={campaign.get('name','')} action={action}")
            # 4. Blacklist globale (RGPD)
            if action in ("bounced", "unsubscribed"):
                cpb_pool.set_global_blacklist(email,
                    reason=f"{action.upper()} via emelia webhook (site={site})")
    except Exception as _pool_err:
        print(f"[webhook][pool dual-write] failed: {_pool_err}")

    # Telegram notification for replies
    if action == "replied":
        try:
            import os
            tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
            if tg_token and tg_chat:
                name = (contact.get("firstName", "") + " " + contact.get("lastName", "")).strip()
                msg = f"\U0001f525 *R\u00e9ponse Emelia!*\n\u2022 {name} ({email})\n\u2022 Campagne: {campaign.get('name', '?')}"
                requests.post(f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat, "text": msg, "parse_mode": "Markdown"}, timeout=5)
        except Exception:
            pass

    return {"ok": True, "action": action, "email": email}


@app.get("/api/track/open")
async def api_track_open(t: str = ""):
    """Pixel de tracking d'ouverture (public). Résout le token → email et enregistre
    la date d'ouverture la plus récente dans le pool. Retourne toujours un GIF 1×1."""
    from fastapi.responses import Response
    _GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04"
            b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D"
            b"\x01\x00;")
    if t:
        try:
            sys.path.insert(0, str(BASE_DIR / "scripts"))
            import sweego_backend as sw
            import contacts_pool_backend as _cpb
            info = sw.resolve_click(t)  # token dédié pixel : clicked_at = date d'ouverture
            email = ((info or {}).get("email") or "").strip().lower()
            if email and "@" in email:
                _cpb.record_engagement(info.get("site") or "lcr", email, "open",
                                       info.get("channel") or "maildoso")
                # Pixel maison : c'est notre propre lien, pas un relais Sweego — pas de
                # drapeau proxy à transmettre, le défaut convient.
        except Exception as _e:
            print(f"[track][open] {_e}")
    return Response(content=_GIF, media_type="image/gif",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@app.get("/api/sweego/click")
async def api_sweego_click(t: str = "", request: Request = None):
    """Lien de tracking de clic Sweego (public). Résout le token → email, promeut le
    contact en `prm` dans acquisition, puis redirige (302) vers l'URL de destination.
    Indépendant du webhook Sweego — fonctionne pour le test bout-en-bout."""
    from fastapi.responses import RedirectResponse
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import sweego_backend as sw
    fallback = "https://leclientroi.com"
    if not t:
        return RedirectResponse(fallback, status_code=302)
    info = sw.resolve_click(t)
    if not info:
        return RedirectResponse(fallback, status_code=302)

    email = (info.get("email") or "").strip().lower()
    site = info.get("site") or "lcr"
    campaign_id = info.get("campaign_id") or ""
    dest = info.get("dest_url") or fallback
    if dest.startswith("pixel:"):  # token de pixel d'ouverture égaré ici → pas un clic
        return RedirectResponse(fallback, status_code=302)

    # Table comportementale : clic (implique aussi ouverture), date la plus récente
    if email and "@" in email:
        try:
            import contacts_pool_backend as _cpb
            _cpb.record_engagement(site, email, "click", info.get("channel") or "sweego")
        except Exception as _ee:
            print(f"[track][click] {_ee}")

    if email and "@" in email:
        try:
            from scripts.acquisition_backend import (
                create as acq_create, find_by_email as acq_find,
                change_state as acq_change_state, STATE_RANK)
            note = f"sweego click campaign={campaign_id}"
            existing = acq_find(site, email)
            if existing:
                if (STATE_RANK.get("prm", 0) > STATE_RANK.get(existing["state"], 0)
                        and existing["state"] != "blacklisted"):
                    acq_change_state(site, existing["id"], "prm", by="sweego_click", note=note)
            else:
                acq_create(site, {
                    "email": email, "notes": note, "state": "prm",
                    "source": f"sweego:{campaign_id}"[:60],
                }, by="sweego_click", skip_validation=True)
            # Dual-write pool
            try:
                import contacts_pool_backend as cpb_pool
                pool_cid = cpb_pool.create_in_pool({"email": email}, primary_source="sweego")
                if pool_cid:
                    cpb_pool.change_state_for_site(pool_cid, site, "prm", by="sweego_click", note=note)
            except Exception as _pe:
                print(f"[sweego_click][pool] {_pe}")
        except Exception as _e:
            print(f"[sweego_click] promote failed: {_e}")

    return RedirectResponse(dest, status_code=302)


@app.post("/api/sweego/webhook")
async def api_sweego_webhook(request: Request):
    """Webhook Sweego (email events). Payload par destinataire — doc learn.sweego.io/docs/webhooks.
    event_type ∈ email_sent, delivered, soft-bounce, hard_bounce, list_unsub, complaint,
                 email_opened, email_clicked.
    Champs clés : recipient (email), campaign_id, campaign_type, click.url, open.proxy.
    Action → état : email_clicked→prm, hard_bounce/list_unsub/complaint→blacklisted,
                    email_opened (humain)→horodatage seul, reste→ignoré.
    """
    data = await request.json()
    # event_type peut arriver sous plusieurs clés/formats : Sweego envoie 'clicked',
    # 'clicked-human/-proxy', 'opened-human', 'Hard bounce', 'List Unsub', 'clicked_unsub'…
    raw_et = (data.get("event_type") or data.get("status") or data.get("event") or "")
    event_type = str(raw_et).strip().lower().replace("-", "_").replace(" ", "_")
    email = (data.get("recipient") or data.get("email") or data.get("to") or "").strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "no recipient"}

    campaign_id = data.get("campaign_id") or ""
    # site detect via campaign_id (on génère lcr-… / mkd-… dans sweego_backend)
    site = "mkd" if str(campaign_id).lower().startswith("mkd") else "lcr"

    # Proxy = bot / scanner de sécurité / prefetch → ce n'est PAS un humain, on ne promeut pas.
    is_proxy_open = bool((data.get("open") or {}).get("proxy")) or ("proxy" in event_type)

    # action → état cible. Noms Sweego normalisés (underscores) + tolérance aux variantes.
    if "unsub" in event_type:                       # list_unsub, clicked_unsub → désinscription
        target_state = "blacklisted"
    elif event_type.startswith("clicked") or event_type == "email_clicked":
        target_state = None if is_proxy_open else "prm"   # clic HUMAIN → lead
    elif event_type.startswith("opened") or event_type == "email_opened":
        target_state = None                         # ouverture → horodatage seul, pas de promo
    elif "hard_bounce" in event_type or event_type == "hardbounce":
        target_state = "blacklisted"
    elif "complaint" in event_type:
        target_state = "blacklisted"
    else:                                           # delivered, sent, soft_bounce, *_proxy…
        target_state = None

    # === Refroidissement immédiat sur plainte ===
    # Une plainte est le signal le plus coûteux : le fournisseur du destinataire l'agrège
    # et bloque autour de 0,3 %, seuil qui se franchit en une journée. On ne peut pas
    # attendre le balayage horaire — la boîte qui a écrit à cette adresse se tait tout de
    # suite, pour 48 h. Voir `refroidissement`.
    if "complaint" in event_type or "unsub" in event_type:
        try:
            sys.path.insert(0, str(BASE_DIR / "scripts"))
            import refroidissement as _rf
            import journal_pg as _jpg
            boite = _jpg._q("""
                SELECT ev.mailbox FROM email_events ev
                WHERE lower(ev.email::text) = %(e)s AND ev.event_type = 'sent'
                  AND ev.mailbox IS NOT NULL
                ORDER BY ev.occurred_at DESC LIMIT 1""", {"e": email})
            if boite and boite[0][0] and "complaint" in event_type:
                _rf.mettre_au_repos(boite[0][0], _rf.HEURES_PLAINTE,
                                    f"plainte de {email} ({event_type})")
                print(f"[sweego_webhook] plainte → {boite[0][0]} au repos "
                      f"{_rf.HEURES_PLAINTE} h", flush=True)
        except Exception as _e:
            print(f"[sweego_webhook] refroidissement non appliqué : {_e}")

    # === Journal PostgreSQL (fin du Lot 1) ===
    # Écrit AVANT DuckDB, comme tout ce qui porte une règle métier : un rebond dur ou une
    # plainte doit être enregistré même si `god_mode.duckdb` est verrouillé par un dispatch.
    # Le drapeau `proxy` est conservé plutôt que filtré : 57 % des ouvertures Sweego sont
    # des pré-chargements antispam, et « une ouverture proxy compte-t-elle ? » ne se
    # répond pas pareil selon qu'on mesure la délivrabilité ou l'intérêt d'un prospect.
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        import pg_sync as _pgs
        _TYPES_JOURNAL = {"email_opened": "open", "email_clicked": "click",
                          "hard_bounce": "bounce", "hardbounce": "bounce",
                          "complaint": "complaint", "list_unsub": "unsub",
                          "clicked_unsub": "unsub"}
        _cible = _TYPES_JOURNAL.get(event_type)
        if _cible:
            _pgs.record_event(email, _cible, site, "sweego",
                              url=(data.get("click") or {}).get("url") or None,
                              provider_msg_id=data.get("transaction_id") or None,
                              meta={"source": "sweego_webhook", "proxy": bool(is_proxy_open),
                                    "campagne_sweego": str(campaign_id)})
    except Exception as _e:
        print(f"[sweego_webhook] journal PostgreSQL indisponible : {_e}")

    # === Audit log des events Sweego (table créée à la volée) ===
    try:
        import duckdb as _dd, uuid as _uuid, json as _json
        from datetime import datetime as _dt, timezone as _tz
        _c = _dd.connect(str(BASE_DIR / "data" / "god_mode.duckdb"))
        try:
            _c.execute("""CREATE TABLE IF NOT EXISTS sweego_events (
                id VARCHAR, event_type VARCHAR, email VARCHAR, campaign_id VARCHAR,
                site_code VARCHAR, url VARCHAR, proxy BOOLEAN, transaction_id VARCHAR,
                received_at TIMESTAMP, raw_payload VARCHAR, PRIMARY KEY (id))""")
            _c.execute("INSERT INTO sweego_events VALUES (?,?,?,?,?,?,?,?,?,?)",
                [str(_uuid.uuid4()), event_type, email, str(campaign_id), site,
                 (data.get("click") or {}).get("url", ""), is_proxy_open,
                 data.get("transaction_id", ""), _dt.now(_tz.utc),
                 _json.dumps(data, ensure_ascii=False)])
        finally:
            _c.close()
    except Exception as _e:
        print(f"[sweego_webhook] audit log failed: {_e}")

    # === Promotion acquisition_contacts ===
    if target_state:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        from scripts.acquisition_backend import (
            create as acq_create, find_by_email as acq_find,
            change_state as acq_change_state, STATE_RANK)
        existing = acq_find(site, email)
        note = f"sweego campaign={campaign_id} event={event_type}"
        if existing:
            if (STATE_RANK.get(target_state, 0) > STATE_RANK.get(existing["state"], 0)
                    and existing["state"] != "blacklisted"):
                acq_change_state(site, existing["id"], target_state, by="sweego_webhook", note=note)
        else:
            acq_create(site, {
                "email": email, "notes": note, "state": target_state,
                "source": f"sweego:{campaign_id}"[:60],
            }, by="sweego_webhook", skip_validation=True)

        # Dual-write pool mutualisé + blacklist globale RGPD
        try:
            import contacts_pool_backend as cpb_pool
            pool_cid = cpb_pool.create_in_pool({"email": email}, primary_source="sweego")
            if pool_cid:
                cpb_pool.change_state_for_site(pool_cid, site, target_state,
                    by="sweego_webhook", note=note)
                if target_state == "blacklisted":
                    cpb_pool.set_global_blacklist(email,
                        reason=f"{event_type.upper()} via sweego webhook (site={site})")
        except Exception as _pool_err:
            print(f"[sweego_webhook][pool] {_pool_err}")

    # Cliqueur promu lead → enrichissement téléphone best-effort (waterfall Basile → Emelia),
    # en tâche de fond pour NE PAS bloquer la réponse au webhook (Basile/Emelia ~90s).
    if target_state == "prm":
        try:
            import threading

            def _enrich_phone_bg(_site=site, _email=email):
                try:
                    import phone_enrich_backend as _pe
                    _pe.enrich_phone(_site, _email)
                except Exception as _e:  # noqa: BLE001
                    print(f"[sweego_webhook][phone] {_e}")

            threading.Thread(target=_enrich_phone_bg, daemon=True).start()
        except Exception as _e:  # noqa: BLE001
            print(f"[sweego_webhook][phone-spawn] {_e}")

    return {"ok": True, "event": event_type, "email": email, "state": target_state}


@app.post("/api/auth/users/{user_id}/reset-password")
async def api_auth_reset_password(user_id: str):
    new_pass = auth_reset(user_id)
    # Get user info for telegram
    users = auth_list_users()
    user = next((u for u in users if u["id"] == user_id), None)
    telegram_sent = False
    if user and user.get("phone"):
        telegram_sent = auth_send_telegram(user["phone"], user["username"], new_pass)
    return {"ok": True, "password": new_pass, "telegram_sent": telegram_sent}


@app.get("/api/auth/logs")
async def api_auth_logs():
    return {"logs": auth_get_logs(50)}

@app.patch("/api/auth/users/{user_id}")
async def api_auth_update_user(user_id: str, request: Request):
    data = await request.json()
    auth_update_user(user_id, data)
    return {"ok": True}


@app.delete("/api/campaigns/{campaign_id}")
async def api_campaign_delete(campaign_id: str):
    import os
    EMELIA_KEY = os.environ.get("EMELIA_API_KEY", "")
    H = {"Authorization": EMELIA_KEY, "Content-Type": "application/json"}
    r = requests.delete(f"https://api.emelia.io/emails/campaigns/{campaign_id}", headers=H, timeout=15)
    return {"ok": r.status_code == 200, "status": r.status_code}


@app.post("/api/crm/{site}/prm/webhook")
async def api_prm_webhook(site: str, request: Request):
    """Webhook PRM legacy → insère dans acquisition_contacts avec state=lead (formulaire = signal fort).
    Body: {email, firstName?, lastName?, company?, phone?, source?, action?} ou liste.
    """
    data = await request.json()
    contacts = data if isinstance(data, list) else [data]

    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.acquisition_backend import create as acq_create, find_by_email as acq_find

    added, skipped, errors = 0, 0, []
    for contact in contacts:
        email = (contact.get("email") or "").strip().lower()
        if not email or "@" not in email:
            errors.append(f"email manquant ou invalide: {email}")
            continue

        if acq_find(site, email):
            skipped += 1
            continue

        full_name = contact.get("name", contact.get("nom_complet", ""))
        if full_name and not contact.get("firstName"):
            parts = full_name.strip().split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""
        else:
            first_name = contact.get("firstName", contact.get("first_name", contact.get("prenom", "")))
            last_name = contact.get("lastName", contact.get("last_name", contact.get("nom", "")))

        source = contact.get("source", contact.get("campaign", "formulaire"))
        message = contact.get("message", "")
        phone = contact.get("phone", contact.get("telephone", contact.get("tel", "")))

        acq_create(site, {
            "email":   email,
            "prenom":  first_name,
            "nom":     last_name,
            "societe": contact.get("company", contact.get("entreprise", contact.get("societe", ""))),
            "tel":     phone,
            "notes":   message,
            "source":  source,
            "state":   "lead",
        }, by="webhook_prm")
        added += 1

    # Telegram alert for new leads
    if added > 0:
        first_contact = contacts[0] if contacts else {}
        _name = first_contact.get("name", first_contact.get("firstName", ""))
        _email = first_contact.get("email", "")
        _company = first_contact.get("company", first_contact.get("entreprise", ""))
        if added == 1:
            send_cheffer_telegram(
                f"\U0001f3af *Nouveau lead*\n"
                f"\u2022 {_name}\n"
                f"\u2022 {_email}\n"
                f"\u2022 {_company}"
            )
        else:
            send_cheffer_telegram(f"\U0001f3af *{added} nouveaux leads* import\u00e9s")
    return {"ok": True, "added": added, "skipped": skipped, "errors": errors}


# \u2500\u2500 /api/costs \u2014 Matrice co\u00fbts filtrable par p\u00e9riode \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

@app.get("/api/costs")
def get_costs_matrix(start: str = "", end: str = "", site: str = ""):
    """Retourne les entr\u00e9es costs-log filtr\u00e9es par p\u00e9riode (YYYY-MM-DD).

    Si start/end absents : 30 derniers jours.
    Renvoie aussi des agr\u00e9gats par projet, module, mod\u00e8le.
    """
    from datetime import timedelta
    import sys
    sys.path.insert(0, str(BASE_DIR))
    from scripts.cost_tracker import PRICING, EUR_RATE

    try:
        log_path = BASE_DIR / "memory" / "shared" / "costs-log.json"
        if not log_path.exists():
            return {"entries": [], "start": start, "end": end, "totals": {}, "by_site": {}, "by_module": {}, "by_model": {}, "pricing": PRICING}

        entries = json.loads(log_path.read_text())
        if not isinstance(entries, list):
            entries = []

        today = datetime.now(timezone.utc).date()
        if not end:
            end = today.isoformat()
        if not start:
            start_dt = today - timedelta(days=30)
            start = start_dt.isoformat()

        filtered = []
        for e in entries:
            d = e.get("date", "")
            if not d:
                continue
            if start <= d <= end:
                if site and e.get("site", "") != site:
                    continue
                filtered.append(e)

        total_usd = round(sum(e.get("cost_usd", 0) for e in filtered), 6)
        total_eur = round(sum(e.get("cost_eur", 0) for e in filtered), 6)
        total_tok = sum(e.get("total_tok", 0) for e in filtered)
        total_in  = sum(e.get("input_tok", 0) for e in filtered)
        total_out = sum(e.get("output_tok", 0) for e in filtered)

        def _agg():
            return {"usd": 0.0, "eur": 0.0, "tok": 0, "in_tok": 0, "out_tok": 0, "calls": 0, "models": set()}

        by_site, by_module, by_model = {}, {}, {}
        for e in filtered:
            s = e.get("site") or "(shared)"
            m = e.get("module", "unknown")
            mdl = e.get("model", "unknown")
            for bucket, key in ((by_site, s), (by_module, m), (by_model, mdl)):
                bucket.setdefault(key, _agg())
                bucket[key]["usd"]     = round(bucket[key]["usd"] + e.get("cost_usd", 0), 6)
                bucket[key]["eur"]     = round(bucket[key]["eur"] + e.get("cost_eur", 0), 6)
                bucket[key]["tok"]    += e.get("total_tok", 0)
                bucket[key]["in_tok"] += e.get("input_tok", 0)
                bucket[key]["out_tok"]+= e.get("output_tok", 0)
                bucket[key]["calls"]  += 1
            by_site[s]["models"].add(mdl)
            by_module[m]["models"].add(mdl)

        for bucket in (by_site, by_module):
            for k in bucket:
                bucket[k]["models"] = sorted(bucket[k]["models"])
        for k in by_model:
            by_model[k].pop("models", None)

        # Co\u00fbt quotidien pour graph
        daily: dict = {}
        for e in filtered:
            d = e.get("date", "")
            daily.setdefault(d, {"usd": 0.0, "eur": 0.0, "calls": 0})
            daily[d]["usd"] = round(daily[d]["usd"] + e.get("cost_usd", 0), 6)
            daily[d]["eur"] = round(daily[d]["eur"] + e.get("cost_eur", 0), 6)
            daily[d]["calls"] += 1
        daily_sorted = [{"date": k, **v} for k, v in sorted(daily.items())]

        return {
            "start":     start,
            "end":       end,
            "entries":   sorted(filtered, key=lambda x: x.get("timestamp", ""), reverse=True),
            "totals": {
                "usd": total_usd, "eur": total_eur, "tok": total_tok,
                "in_tok": total_in, "out_tok": total_out, "calls": len(filtered),
            },
            "by_site":   by_site,
            "by_module": by_module,
            "by_model":  by_model,
            "daily":     daily_sorted,
            "pricing":   PRICING,
            "eur_rate":  EUR_RATE,
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/deepseek/balance")
def get_deepseek_balance():
    """Solde DeepSeek en live (appel \u00e0 api.deepseek.com/user/balance)."""
    try:
        key = ""
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text().splitlines():
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY=") and "=" in line:
                    key = line.split("=", 1)[1].strip("'\"")
                    break
        if not key:
            return {"error": "DEEPSEEK_API_KEY introuvable"}

        r = requests.get(
            "https://api.deepseek.com/user/balance",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10,
        )
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "body": r.text[:200]}
        data = r.json()
        infos = data.get("balance_infos", [{}])[0]
        total = float(infos.get("total_balance", 0))
        return {
            "available":   data.get("is_available", False),
            "currency":    infos.get("currency", "USD"),
            "total":       total,
            "granted":     float(infos.get("granted_balance", 0)),
            "topped_up":   float(infos.get("topped_up_balance", 0)),
            "total_eur":   round(total * 0.92, 2),
            "fetched_at":  datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"error": str(e)}


# ── Ahrefs credits passthrough (pour sidebar) ─────────────────────────────────

@app.get("/api/ahrefs/usage")
def get_ahrefs_usage():
    """Lit les crédits Ahrefs depuis le fichier de cache (mis à jour par ahrefs_daily.py cron)."""
    try:
        cache_path = BASE_DIR / "memory" / "seo" / "ahrefs-usage.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text())
        return {"used": 0, "total": 10000, "reset_at": ""}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/serper/usage")
def get_serper_usage():
    """Crédits Serper.

    Serper.dev n'expose AUCUNE API de solde restant (endpoints /account, /balance,
    /credits => 403). On part donc d'un snapshot manuel du solde
    (memory/seo/serper-balance.json : {plan_total, balance, snapshot_at}) et on
    décrémente avec la conso locale loggée DEPUIS le snapshot.

    Conso locale = table god_mode_serper_calls (scraper) + entrées model=serper-search
    du costs-log (chemins distincts, pas de double comptage).
    """
    try:
        now = datetime.now(timezone.utc)
        month = now.strftime("%Y-%m")

        cfg_path = BASE_DIR / "memory" / "seo" / "serper-balance.json"
        cfg = {}
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text())
            except Exception:
                cfg = {}
        plan_total  = cfg.get("plan_total")
        balance     = cfg.get("balance")
        snapshot_at = cfg.get("snapshot_at")  # ISO UTC

        def _sum_credits(since_iso):
            """Somme des crédits Serper consommés. Si since_iso=None => mois courant."""
            total = 0
            # 1) Table god_mode_serper_calls
            try:
                import duckdb
                c = _duck(BASE_DIR / "data" / "god_mode.duckdb")
                if since_iso:
                    snap_naive = since_iso[:19].replace("T", " ")
                    r = c.execute(
                        "SELECT COALESCE(SUM(credits), 0) FROM god_mode_serper_calls "
                        "WHERE created_at >= ?::TIMESTAMP", [snap_naive]).fetchone()
                else:
                    r = c.execute(
                        "SELECT COALESCE(SUM(credits), 0) FROM god_mode_serper_calls "
                        "WHERE strftime(created_at, '%Y-%m') = ?", [month]).fetchone()
                total += int(r[0] or 0)
                c.close()
            except Exception:
                pass
            # 2) costs-log (appels serper_client standalone)
            try:
                if COSTS_FILE.exists():
                    data = json.loads(COSTS_FILE.read_text())
                    entries = data if isinstance(data, list) else data.get("entries", [])
                    for e in entries:
                        if str(e.get("model", "")) != "serper-search":
                            continue
                        if since_iso:
                            ts = str(e.get("timestamp", "") or e.get("date", ""))
                            if ts[:19] < since_iso[:19]:
                                continue
                        else:
                            if not str(e.get("date", "")).startswith(month):
                                continue
                        note = str(e.get("note", ""))
                        if "credits=" in note:
                            try:
                                total += int(note.split("credits=")[1].split()[0])
                                continue
                            except Exception:
                                pass
                        total += round((e.get("cost_usd", 0) or 0) / 0.001)
            except Exception:
                pass
            return total

        out = {
            "used_month": _sum_credits(None),
            "month": month,
            "fetched_at": now.isoformat(),
        }
        if plan_total is not None:
            out["plan_total"] = plan_total
        # Source de vérité = SOLDE LIVE serper.dev /account (l'endpoint existe, contrairement
        # à l'ancien commentaire ; c'est ce que la page Scrapper affiche déjà). On l'utilise
        # pour `available` ET on rafraîchit le snapshot pour qu'autoscrape.serper_available()
        # ne bloque plus sur une valeur figée.
        live = None
        try:
            sys.path.insert(0, str(BASE_DIR / "scripts"))
            from god_mode_agents import serper_balance as _sbal
            _b = _sbal()
            if _b.get("ok") and _b.get("balance") is not None:
                live = int(_b["balance"])
                # NB: _b["rateLimit"] = req/s (≈5), PAS le forfait crédits -> on garde
                # plan_total du snapshot.
        except Exception:
            live = None
        if live is not None:
            out["available"] = live
            out["balance_live"] = live
            # plan_total = plafond du forfait. Serper /account ne renvoie QUE le solde,
            # pas la taille du forfait => on prend le max(plafond connu, solde live) :
            # une recharge (ex. +50000) relève donc automatiquement le plafond au lieu
            # de rester collée à l'ancien forfait (bug "50 000 / 2500").
            plan_total = max(int(plan_total or 0), live)
            out["plan_total"] = plan_total
            try:
                cfg_path.write_text(json.dumps({
                    "plan_total": plan_total,
                    "balance": live,
                    "snapshot_at": now.isoformat(),
                    "note": "Auto-rafraichi depuis le solde live serper.dev /account. "
                            "plan_total = max(plafond connu, solde live) -> suit les recharges.",
                }, ensure_ascii=False, indent=2))
            except Exception:
                pass
        elif balance is not None and snapshot_at:
            consumed_since = _sum_credits(snapshot_at)
            out["consumed_since_snapshot"] = consumed_since
            out["available"] = max(0, int(balance) - consumed_since)
        return out
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/emelia/credits")
def get_emelia_credits():
    """Solde Emelia LIVE (crédits enrichissement). Lu via l'API GraphQL Emelia
    (me.subscription.enrich.creditsRemaining). Affiche l'arrondi (comme le dashboard Emelia)."""
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        import emelia_credits
        live = emelia_credits.fetch_live_balance()
        if not live.get("ok"):
            return {"error": live.get("error", "fetch"), "configured": False}
        return {
            "configured": True,
            "remaining": live.get("remaining"),          # arrondi (réf. dashboard)
            "remaining_raw": live.get("remaining_raw"),  # valeur brute
            "subscription_credits": live.get("subscription_credits"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"error": str(e), "configured": False}


@app.get("/api/sweego/stats")
def get_sweego_stats():
    """Emails envoyés via Sweego (total cumulé depuis /stats/msp + nombre de campagnes en base)."""
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        import sweego_backend as sw
        env_ok = bool(sw._env().get("SWEEGO_API_KEY"))
        if not env_ok:
            return {"configured": False}
        msp = sw.msp_stats()
        total_sent = sum(r.get("sent", 0) for r in (msp.get("result") or []))
        # Compter les campagnes en base toutes plateformes confondues
        campaigns = sw.list_campaigns("lcr") + sw.list_campaigns("mkd")
        return {
            "configured": True,
            "sent_total": total_sent,
            "campaigns_count": len(campaigns),
            "msps": msp.get("msps", []),
        }
    except Exception as e:
        return {"configured": False, "error": str(e)}


@app.get("/api/sweego/engagement")
def get_sweego_engagement(start: str | None = None, end: str | None = None):
    """Engagement Sweego (ouvertures/clics/bounces + taux) via /stats. Optionnel : start/end (YYYY-MM-DD).
    Câble sweego_backend.engagement_stats() — sert la vue masse des newsletters."""
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        import sweego_backend as sw
        if not sw._env().get("SWEEGO_API_KEY"):
            return {"configured": False}
        data = sw.engagement_stats(start, end)
        g = data.get("global", {})
        return {
            "configured": True,
            "sent": g.get("sent", 0),
            "accepted": g.get("accepted", 0),
            "bounced": g.get("bounced", 0),
            "openers": g.get("nb_human_openers", 0),
            "clickers": g.get("nb_clickers", 0),
            "unsubscribes": g.get("list_unsubscribe", 0),
            "open_rate": g.get("open_rate", 0),
            "click_rate": g.get("click_rate", 0),
            "by_day": data.get("by_day", []),
        }
    except Exception as e:
        return {"configured": False, "error": str(e)}


@app.get("/api/sites/{site}/marketing/overview")
def get_marketing_overview(site: str):
    """Stats harmonisées par canal : Cold email (Emelia) vs Masse (Sweego).
    Forme comparable : sent / opens / open_rate / clicks / click_rate / bounces / bounce_rate.
    - Emelia : agrège les campagnes dont le nom matche le site (préfixe LCR/MKD), dérive les
      compteurs absolus depuis mailsSent × pourcentages, puis recalcule les taux globaux.
    - Sweego : engagement_stats() (compte au niveau du compte Sweego, pas par site — libellé tel quel).
    """
    import os
    out = {"emelia": None, "sweego": None}
    pref = site.upper()

    # ── Emelia (cold email) ──
    try:
        EMELIA_KEY = os.environ.get("EMELIA_API_KEY", "")
        H = {"Authorization": EMELIA_KEY, "Content-Type": "application/json"}
        camps = requests.get("https://api.emelia.io/emails/campaigns", headers=H, timeout=15).json().get("campaigns", [])
        agg = {"sent": 0, "opens": 0.0, "clicks": 0.0, "replies": 0.0, "bounces": 0.0, "campaigns": 0}
        for c in camps:
            name = (c.get("name") or "").upper().replace(" ", "")
            # code site n'importe où dans le nom (workflow-lcr-x, test-...-lcr, LCR-...)
            if not (pref in name or (pref == "LCR" and "LECLIENTROI" in name)):
                continue
            cid = c.get("_id", "")
            try:
                st = requests.get(f"https://api.emelia.io/stats?campaignId={cid}", headers=H, timeout=8).json()
            except Exception:
                continue
            sent = st.get("mailsSent", 0) or 0
            if sent <= 0:
                continue
            agg["campaigns"] += 1
            agg["sent"] += sent
            agg["opens"]   += sent * (st.get("uniqueOpensPercent", 0) or 0) / 100.0
            agg["clicks"]  += sent * (st.get("linkClickedPercent", 0) or 0) / 100.0
            agg["replies"] += sent * (st.get("repliedPercent", 0) or 0) / 100.0
            agg["bounces"] += sent * (st.get("bouncedPercent", 0) or 0) / 100.0
        s = agg["sent"]
        out["emelia"] = {
            "configured": bool(EMELIA_KEY),
            "campaigns": agg["campaigns"],
            "sent": s,
            "opens": round(agg["opens"]), "clicks": round(agg["clicks"]),
            "replies": round(agg["replies"]), "bounces": round(agg["bounces"]),
            "open_rate": round(agg["opens"] / s * 100, 1) if s else 0,
            "click_rate": round(agg["clicks"] / s * 100, 1) if s else 0,
            "reply_rate": round(agg["replies"] / s * 100, 1) if s else 0,
            "bounce_rate": round(agg["bounces"] / s * 100, 1) if s else 0,
        }
    except Exception as e:
        out["emelia"] = {"configured": False, "error": str(e)}

    # ── Maildoso et Sweego : nos propres journaux ──
    # Ils partaient auparavant chacun de leur côté — `md.stats()` d'un côté, l'API Sweego de
    # l'autre. L'API Sweego compte TOUT le compte (les deux marques, plus les boîtes de
    # warmup) : elle ne pouvait pas s'aligner avec un tableau de bord par site. Les deux
    # canaux viennent maintenant de la même fonction que le tableau journalier, donc des
    # mêmes journaux — c'est la seule façon que deux écrans disent le même chiffre.
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        import dashboard_stats_backend as _stats
        out.update(_stats.performance_par_canal(site))
    except Exception as e:  # noqa: BLE001
        out.setdefault("maildoso", {"configured": False, "error": str(e)})
        out.setdefault("sweego", {"configured": False, "error": str(e)})

    return out


@app.get("/api/basile/usage")
def get_basile_usage():
    """Conso Basile du mois (contacts collectés via le connecteur Basile, source de vérité =
    pool contacts.duckdb primary_source='basile') vs forfait plan API (250 000/mois).
    Basile n'expose aucune API de solde/quota → décompte local, comme Serper."""
    try:
        import duckdb as _dd
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        used = 0
        try:
            c = _pool_conn()
            r = c.execute(
                "SELECT COUNT(*) FROM contacts WHERE primary_source = 'basile' "
                "AND strftime(created_at, '%Y-%m') = ?", [month]).fetchone()
            used = int(r[0] or 0)
            c.close()
        except Exception:
            used = 0
        plan_total = 250000  # plan API Basile (export/mois). Cf. docs/basile-api.md §10.
        configured = bool(os.environ.get("BASILE_KEY"))
        if not configured and ENV_FILE.exists():
            configured = any(l.strip().startswith("BASILE_KEY=") and l.split("=", 1)[1].strip(" '\"")
                             for l in ENV_FILE.read_text().splitlines())
        return {"configured": configured, "used_month": used, "plan_total": plan_total,
                "month": month, "fetched_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"error": str(e), "configured": False}


# ── Prospects scraping (Serper.dev) ───────────────────────────────────────────

@app.post("/api/sites/{site}/prospects/scrape")
async def api_prospects_scrape(site: str, request: Request):
    """Déclenche un scrape Serper + extraction emails pour un secteur/lieu donné."""
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    data = await request.json()
    sector = (data.get("sector") or "").strip()
    location = (data.get("location") or "").strip()
    max_results = int(data.get("max", 20))
    if not sector or not location:
        return {"error": "sector et location requis"}
    max_results = max(5, min(50, max_results))

    # Exécution synchrone (le scraping prend ~10-30s)
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        from scripts.prospect_scraper import find_prospects, save_run
        prospects = find_prospects(sector, location, max_results)
        out_path = save_run(site, sector, location, prospects)
        n_email = sum(1 for p in prospects if p.get("emails"))
        return {
            "ok": True,
            "count":     len(prospects),
            "with_email": n_email,
            "run_file":  str(out_path.relative_to(BASE_DIR)),
            "prospects": prospects,
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/sites/{site}/prospects/runs")
def api_prospects_list_runs(site: str):
    """OBSOLÈTE — remplacé par /api/sites/{site}/acquisition (state=cold_email)."""
    return {"runs": [], "deprecated": True}


@app.post("/api/sites/{site}/prospects/push-emelia")
async def api_prospects_push_emelia(site: str, request: Request):
    """Ajoute les prospects sélectionnés dans une campagne Emelia.

    Body: {campaign_id: str, emails: [{email, firstName?, lastName?, company?}]}
    """
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    data = await request.json()
    campaign_id = data.get("campaign_id", "")
    contacts = data.get("emails", [])
    if not campaign_id or not contacts:
        return {"error": "campaign_id et emails requis"}
    try:
        emelia_key = get_emelia_key_for_site(site)
        if not emelia_key:
            return {"error": f"Aucune clé Emelia pour {site} (ni EMELIA_API_KEY_{site.upper()} ni globale)"}
        added, skipped, errors = 0, 0, []
        for c in contacts:
            payload = {
                "email": c.get("email", ""),
                "firstName": c.get("firstName", ""),
                "lastName": c.get("lastName", ""),
                "company": c.get("company", ""),
            }
            try:
                r = requests.post(
                    f"https://api.emelia.io/campaigns/{campaign_id}/contacts",
                    headers={"Authorization": emelia_key, "Content-Type": "application/json"},
                    json=payload, timeout=10,
                )
                if r.status_code in (200, 201):
                    added += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append(str(e))
        return {"ok": True, "added": added, "skipped": skipped, "errors": errors[:5]}
    except Exception as e:
        return {"error": str(e)}


# ── Acquisition unifiée (cold_email → prm → lead → crm → blacklisted) ─────────

@app.get("/api/sites/{site}/acquisition")
def api_acq_list(
    site: str, request: Request, state: str = "", source: str = "", search: str = "",
    limit: int = 100, offset: int = 0,
):
    """Liste paginée avec filtres multi-valeurs séparées par virgule.
    state=cold_email,prm  →  contacts dans ces 2 états."""
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    # Lit le POOL et non plus `crm/{site}.duckdb`. Cette liste alimente « À rappeler » et
    # « Contacts récents » du tableau de bord : elle affichait des contacts issus d'une base
    # gelée de 1 653 lignes dont 1 506 blacklistés, pendant que le pool en compte 7 916.
    # Même correction que les compteurs, même cause.
    import contacts_pool_backend as pool
    import garde_lecture as gl
    role, qui = _qui(request)
    etat = gl.verifier(qui, role)
    if not etat["ok"]:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=429, content=gl.refus(etat))
    states  = [x for x in (state or "").split(",") if x]
    sources = [x for x in (source or "").split(",") if x]
    # Le plafond dépend du rôle : un écran montre cinquante lignes, personne n'a besoin
    # d'en demander cinq cents. Voir `garde_lecture`.
    lim = gl.plafonner(role, limit)
    try:
        contacts = _lecture_pool("list_contacts_for_site")(
            site, state=states or None, source=sources or None,
            search_email=search.strip() or None, limit=lim, offset=max(0, offset))
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": f"pool indisponible: {e}"[:200]})
    # `total` conservé pour ne pas casser les appelants ; sur une page pleine on ne connaît
    # pas le total exact sans un second comptage — on le signale plutôt que de mentir.
    gl.journaliser(qui, role, site, "acquisition", len(contacts))
    return {"contacts": contacts, "total": len(contacts),
            "total_exact": len(contacts) < lim}


@app.get("/api/sites/{site}/acquisition/stats")
def api_acq_stats(site: str):
    """Compteurs de contacts du tableau de bord.

    Lit le POOL (`contacts.duckdb`) et non plus `crm/{site}.duckdb`. Cette base CRM est un
    vestige de `acquisition_backend`, gelée depuis la migration vers le pool : elle contenait
    1 653 contacts pour LCR, dont **1 506 blacklistés**. Le tableau de bord annonçait donc
    « 1 653 contacts » et « 19 en cold email » alors que le pool en compte 7 916 et que les
    campagnes s'appuient dessus. Le chiffre le plus visible de la plateforme décrivait une
    base morte.

    On conserve la forme de la réponse (`total`, `by_state`, `by_source`) : le tableau de
    bord n'a rien à changer, et un futur appelant ne sera pas surpris.
    """
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    try:
        return _lecture_pool("stats_for_site")(site)
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": f"pool indisponible: {e}"[:200]})


@app.post("/api/sites/{site}/acquisition")
async def api_acq_create(site: str, request: Request):
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    data = await request.json()
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.acquisition_backend import create
    sess = getattr(request.state, "session", None)
    by = (sess or {}).get("username", "ui")
    return create(site, data, by=by)


@app.patch("/api/sites/{site}/acquisition/{contact_id}")
async def api_acq_update(site: str, contact_id: str, request: Request):
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    data = await request.json()
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.acquisition_backend import update
    return update(site, contact_id, data)


@app.patch("/api/sites/{site}/acquisition/{contact_id}/state")
async def api_acq_state(site: str, contact_id: str, request: Request):
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    data = await request.json()
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.acquisition_backend import change_state
    sess = getattr(request.state, "session", None)
    by = (sess or {}).get("username", "ui")
    return change_state(site, contact_id, data.get("state", ""), by=by, note=data.get("note", ""))


@app.delete("/api/sites/{site}/acquisition/{contact_id}")
def api_acq_delete(site: str, contact_id: str, hard: bool = False):
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.acquisition_backend import delete
    return delete(site, contact_id, hard=hard)


@app.post("/api/sites/{site}/acquisition/{contact_id}/blacklist")
async def api_acq_blacklist(site: str, contact_id: str, request: Request):
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    data = await request.json() if request.headers.get("content-length") else {}
    push_emelia = bool(data.get("push_emelia", False))
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.acquisition_backend import blacklist
    return blacklist(site, contact_id, push_emelia=push_emelia, emelia_api_key=get_emelia_key_for_site(site))


@app.post("/api/sites/{site}/acquisition/import-csv")
async def api_acq_import_csv(site: str, request: Request):
    """Body: {rows: [{email, nom, prenom, societe, tel, notes}, ...], default_state: 'cold_email'}"""
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    data = await request.json()
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.acquisition_backend import bulk_import
    return bulk_import(
        site, data.get("rows", []),
        source="import_csv", default_state=data.get("default_state", "cold_email"),
    )


# ── Images d'articles (upload + featured + insertion markdown) ────────────────

ARTICLES_IMG_DIR = BASE_DIR / "dashboard" / "assets" / "articles"
ARTICLES_IMG_DIR.mkdir(parents=True, exist_ok=True)


def _slugify_alt(text: str, maxlen: int = 60) -> str:
    """Convertit un alt en slug filename-safe."""
    import re, unicodedata
    s = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", s).strip("-").lower()
    return (s or "image")[:maxlen]


@app.post("/api/editorial/{article_id}/image")
async def api_article_image_upload(article_id: str, file: UploadFile = File(...),
                                   alt: str = "", position: str = "featured"):
    """Upload une image pour un article.
    position : 'featured' | 'p1' | 'p2' | 'p3'... (insère après le N-ème paragraphe)
    alt : texte alternatif SEO (obligatoire)
    """
    if not alt or not alt.strip():
        return {"error": "alt_required"}

    # Lookup l'article
    queue_file = BASE_DIR / "memory" / "editorial" / "articles-queue.json"
    if not queue_file.exists():
        return {"error": "no_queue"}
    queue = json.loads(queue_file.read_text())
    idx = next((i for i, a in enumerate(queue) if a.get("id") == article_id), -1)
    if idx == -1:
        return {"error": "article_not_found"}
    art = queue[idx]
    site = art.get("site", "lcr")

    # Détermine l'extension à partir du content-type
    ct = (file.content_type or "").lower()
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp", "image/gif": "gif"}.get(ct, "png")

    # Stockage : dashboard/assets/articles/{site}/{article_id}/{slug}-{timestamp}.{ext}
    art_dir = ARTICLES_IMG_DIR / site / article_id
    art_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify_alt(alt)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    filename = f"{slug}-{ts}.{ext}"
    out = art_dir / filename

    try:
        from PIL import Image
        import io as _io
        raw = await file.read()
        img = Image.open(_io.BytesIO(raw)).convert("RGBA" if ext == "png" else "RGB")
        # Cap la largeur à 1200px pour le web (préserve ratio)
        if img.width > 1200:
            ratio = 1200 / img.width
            img = img.resize((1200, int(img.height * ratio)), Image.LANCZOS)
        save_kwargs = {"optimize": True}
        if ext == "jpg": save_kwargs["quality"] = 85
        img.save(out, **save_kwargs)
    except Exception as e:
        return {"error": f"image_processing_failed: {e}"}

    image_url = f"/assets/articles/{site}/{article_id}/{filename}"
    image_id = f"img_{ts}_{slug[:20]}"

    # Mise à jour article : ajoute dans `article.images` + insère dans markdown
    article = art.setdefault("article", {})
    images = article.setdefault("images", [])
    new_img = {"id": image_id, "url": image_url, "alt": alt, "position": position, "added_at": datetime.now(timezone.utc).isoformat()}
    images.append(new_img)

    if position == "featured":
        article["featured_image"] = {"url": image_url, "alt": alt}
    else:
        # Insère ![alt](url) après le N-ème paragraphe
        try:
            n = int(position.lstrip("p")) if position.startswith("p") else 1
        except ValueError:
            n = 1
        md = article.get("markdown", "") or ""
        paragraphs = md.split("\n\n")
        # Le titre H1 est traditionnellement le 1er paragraphe ; on insère APRÈS la position demandée
        # Position p1 = après le 1er paragraphe non-H1, etc.
        insert_idx = min(n, len(paragraphs))
        image_md = f"![{alt}]({image_url})"
        paragraphs.insert(insert_idx, image_md)
        article["markdown"] = "\n\n".join(paragraphs)
        article["word_count"] = len(article["markdown"].split())

    art["updated_at"] = datetime.now(timezone.utc).isoformat()
    queue[idx] = art
    queue_file.write_text(json.dumps(queue, ensure_ascii=False, indent=2))

    return {"ok": True, "image": new_img, "url": image_url}


@app.get("/api/editorial/{article_id}/images")
def api_article_images_list(article_id: str):
    queue_file = BASE_DIR / "memory" / "editorial" / "articles-queue.json"
    if not queue_file.exists():
        return {"images": []}
    queue = json.loads(queue_file.read_text())
    art = next((a for a in queue if a.get("id") == article_id), None)
    if not art:
        return {"error": "not_found"}
    article = art.get("article", {})
    return {
        "images": article.get("images", []),
        "featured_image": article.get("featured_image"),
    }


@app.delete("/api/editorial/{article_id}/image/{image_id}")
def api_article_image_delete(article_id: str, image_id: str):
    queue_file = BASE_DIR / "memory" / "editorial" / "articles-queue.json"
    if not queue_file.exists():
        return {"error": "no_queue"}
    queue = json.loads(queue_file.read_text())
    idx = next((i for i, a in enumerate(queue) if a.get("id") == article_id), -1)
    if idx == -1:
        return {"error": "not_found"}
    art = queue[idx]
    article = art.setdefault("article", {})
    images = article.get("images", []) or []
    target = next((i for i in images if i.get("id") == image_id), None)
    if not target:
        return {"error": "image_not_found"}

    # Retire du markdown s'il y est
    md = article.get("markdown", "") or ""
    pattern = f"![{target.get('alt','')}]({target.get('url','')})"
    if pattern in md:
        article["markdown"] = md.replace("\n\n" + pattern, "").replace(pattern + "\n\n", "").replace(pattern, "")
        article["word_count"] = len(article["markdown"].split())

    # Featured ?
    if article.get("featured_image", {}).get("url") == target.get("url"):
        article.pop("featured_image", None)

    # Supprime du disque
    try:
        url = target.get("url", "")
        if url.startswith("/assets/articles/"):
            p = BASE_DIR / "dashboard" / url[len("/assets/"):].lstrip("/")
            if p.exists():
                p.unlink()
    except Exception:
        pass

    article["images"] = [i for i in images if i.get("id") != image_id]
    art["updated_at"] = datetime.now(timezone.utc).isoformat()
    queue[idx] = art
    queue_file.write_text(json.dumps(queue, ensure_ascii=False, indent=2))
    return {"ok": True}


# ── Logo de site (upload + serve depuis dashboard/assets/logos/) ──────────────

LOGOS_DIR = BASE_DIR / "dashboard" / "assets" / "logos"
LOGOS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/sites/{site}/logo")
def api_logo_status(site: str):
    """Retourne {has_logo: bool, url: str?}."""
    p = LOGOS_DIR / f"{site}.png"
    if p.exists():
        return {"has_logo": True, "url": f"/assets/logos/{site}.png", "size_bytes": p.stat().st_size}
    return {"has_logo": False, "url": None}


from fastapi import UploadFile, File

@app.post("/api/sites/{site}/logo")
async def api_logo_upload(site: str, file: UploadFile = File(...)):
    """Upload + resize 400x400 carré (crop centré si non carré) + sauvegarde PNG."""
    if site not in ("lcr", "mkd") and not site.replace("-", "").isalnum():
        return {"error": "invalid site"}
    try:
        from PIL import Image
        import io as _io
        raw = await file.read()
        img = Image.open(_io.BytesIO(raw)).convert("RGBA")

        # Crop centré pour obtenir un carré
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))

        # Resize 400x400 (LANCZOS = haute qualité)
        img = img.resize((400, 400), Image.LANCZOS)

        out = LOGOS_DIR / f"{site}.png"
        img.save(out, format="PNG", optimize=True)
        return {"ok": True, "url": f"/assets/logos/{site}.png", "size_bytes": out.stat().st_size}
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/sites/{site}/logo")
def api_logo_delete(site: str):
    p = LOGOS_DIR / f"{site}.png"
    if p.exists():
        p.unlink()
    return {"ok": True}


# ── Env vars par site (clé Tally, etc. — écrit atomiquement dans .env) ────────

def _write_env_var(key: str, value: str | None) -> bool:
    """Écrit/met à jour/supprime une variable dans .env. Idempotent."""
    if not key or not key.replace("_", "").isalnum():
        return False
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        env_path.touch()
    lines = env_path.read_text().splitlines()
    new_lines = []
    found = False
    for line in lines:
        s = line.strip()
        if s.startswith(f"{key}=") or s.startswith(f"#{key}="):
            if value is not None:
                new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found and value is not None:
        new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""))
    return True


# Connecteurs "par site" (variable env porte le suffixe _<SITE>)
SITE_ENV_CONNECTORS = {
    "tally":          "TALLY_API_KEY_{SITE}",
    "emelia":         "EMELIA_API_KEY_{SITE}",
    "unsplash_key":   "UNSPLASH_{SITE}_ACCESS_KEY",
}


def get_emelia_key_for_site(site: str) -> str:
    """Retourne la clé Emelia du site, avec fallback sur la clé globale legacy.

    Ordre de lookup :
      1. EMELIA_API_KEY_{SITE.UPPER()} (recommandé)
      2. EMELIA_API_KEY (clé globale legacy, compat)
    """
    env = load_env()
    if site:
        site_key = env.get(f"EMELIA_API_KEY_{site.upper()}", "").strip()
        if site_key:
            return site_key
    return env.get("EMELIA_API_KEY", "").strip()

@app.get("/api/sites/{site}/env-keys")
def api_env_keys_status(site: str):
    """Retourne le statut (configuré ou pas) des clés env par site, SANS exposer les valeurs."""
    env_path = BASE_DIR / ".env"
    env_text = env_path.read_text() if env_path.exists() else ""
    out = {}
    for k, tpl in SITE_ENV_CONNECTORS.items():
        var = tpl.format(SITE=site.upper())
        # Cherche `VAR=valeur_non_vide`
        configured = False
        for line in env_text.splitlines():
            line = line.strip()
            if line.startswith(f"{var}="):
                v = line.split("=", 1)[1].strip().strip("'\"")
                if v:
                    configured = True
                    break
        out[k] = {"env_var": var, "configured": configured}
    return out


@app.patch("/api/sites/{site}/env-keys")
async def api_env_keys_update(site: str, request: Request):
    """Met à jour les clés env du site. Body : {tally?: "tly-xxx", unsplash_key?: "..."}
    Valeur vide ou null = suppression de la ligne."""
    data = await request.json()
    updated = []
    for k, val in data.items():
        if k not in SITE_ENV_CONNECTORS:
            continue
        var = SITE_ENV_CONNECTORS[k].format(SITE=site.upper())
        value = (val or "").strip() or None
        if _write_env_var(var, value):
            updated.append({"key": k, "env_var": var, "set": value is not None})
    return {"ok": True, "updated": updated}


# ── Adresses d'envoi : le tableau de la page Configuration ───────────────────

@app.get("/api/sites/{site}/expediteurs")
def api_expediteurs(site: str):
    """Toutes les adresses d'envoi : usage, chauffe, volumes et engagement.

    Les volumes viennent du journal `email_events` — ce qui est réellement parti — et
    jamais de `mailboxes.sent_today`, qui vit dans DuckDB et se perd sous verrou.
    """
    _scripts_dans_le_chemin()
    import expediteur
    try:
        return expediteur.tableau(site)
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503,
                            content={"error": f"adresses indisponibles: {e}"[:200]})


@app.patch("/api/sites/{site}/expediteurs/{email}")
async def api_expediteur_maj(site: str, email: str, request: Request):
    """Ajuste une adresse : son usage, son plafond Maildoso, son activation.

    Le plafond est celui que MAILDOSO accepte : le relever ici sans le relever chez
    Maildoso ferait rejeter les envois. L'écran le dit.
    """
    _scripts_dans_le_chemin()
    import expediteur
    d = await request.json()
    champs, vals = [], []
    if "usage" in d:
        if d["usage"] not in ("adhoc", "mozart"):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=400,
                                content={"error": "usage doit valoir adhoc ou mozart"})
        champs.append("usage = %s"); vals.append(d["usage"])
    if "daily_cap" in d:
        champs.append("daily_cap = %s"); vals.append(max(0, int(d["daily_cap"])))
    if "status" in d:
        if d["status"] not in ("active", "inactive"):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=400,
                                content={"error": "status doit valoir active ou inactive"})
        champs.append("status = %s"); vals.append(d["status"])
    if not champs:
        return {"ok": True, "inchange": True}
    n = expediteur._ecrire(
        f"UPDATE mailboxes SET {', '.join(champs)} WHERE email = %s AND site_code = %s",
        tuple(vals) + (email, site))
    if not n:
        return _introuvable("adresse d'envoi")
    return {"ok": True, "tableau": expediteur.tableau(site)}


# ── Onoff Business — téléphonie ───────────────────────────────────────────────
# Le connecteur est en lecture seule côté Onoff (l'API n'expose ni la composition d'un
# appel, ni l'envoi de SMS, ni le solde — voir l'en-tête de scripts/onoff.py). Les journaux
# arrivent par WEBHOOK, qui fonctionne quel que soit l'abonnement, et l'API sert
# d'enrichissement quand le plan Max est actif.

def _onoff():
    _scripts_dans_le_chemin()
    import onoff
    return onoff


@app.get("/api/sites/{site}/onoff/etat")
def api_onoff_etat(site: str):
    """Ce que la page ON/OFF affiche en haut : configuration, sonde vivante, volumes."""
    o = _onoff()
    out = {"configure": o.configure(site), "resume": o.resume(site),
           "url_webhook": o.url_webhook(site),
           # Dit à l'écran ce qui est possible, pour qu'il n'affiche pas un bouton mort.
           "capacites": {"appeler": False, "envoyer_sms": False, "credit": False,
                         "lire_journaux": True, "messagerie": True}}
    out["verification"] = o.verifier(site) if out["configure"] else {"status": "missing_key"}
    return out


@app.get("/api/sites/{site}/onoff/membres")
def api_onoff_membres(site: str):
    return _onoff().membres(site)


@app.get("/api/sites/{site}/onoff/numeros")
def api_onoff_numeros(site: str):
    return _onoff().numeros(site)


@app.get("/api/sites/{site}/onoff/appels")
def api_onoff_appels(site: str, limite: int = 100, numero: str = ""):
    return _onoff().appels(site, limite=limite, numero=numero)


@app.get("/api/sites/{site}/onoff/messagerie")
def api_onoff_messagerie(site: str, non_lus: bool = False, limite: int = 100):
    return _onoff().messagerie(site, seulement_non_lus=non_lus, limite=limite)


@app.post("/api/sites/{site}/onoff/messagerie/{ident}/lu")
async def api_onoff_messagerie_lu(site: str, ident: str, request: Request):
    """Marque une messagerie écoutée — ou la remet en non lu (`{"lu": false}`)."""
    try:
        d = await request.json()
    except Exception:  # noqa: BLE001
        d = {}
    r = _onoff().marquer_lu(site, ident, lu=bool(d.get("lu", True)))
    if not r.get("ok"):
        return _introuvable("message vocal")
    return r


@app.get("/api/sites/{site}/onoff/messagerie/{ident}/audio")
def api_onoff_messagerie_audio(site: str, ident: str):
    """URL audio signée. Onoff ne sert pas le fichier directement, il faut la demander."""
    o = _onoff()
    # D'abord ce que le webhook a déjà livré : aucun appel réseau si l'URL est connue.
    for m in o.messagerie(site).get("messages", []):
        if m.get("id") == ident and m.get("url_audio"):
            return {"ok": True, "url": m["url_audio"], "source": "webhook"}
    r = o.url_messagerie(site, ident)
    r["source"] = "api"
    return r


@app.get("/api/sites/{site}/onoff/sms")
def api_onoff_sms(site: str, numero: str = "", limite: int = 200):
    return _onoff().fils_sms(site, numero=numero, limite=limite)


@app.post("/api/sites/{site}/onoff/sms")
async def api_onoff_sms_envoyer(site: str, request: Request):
    """Envoi d'un SMS 1 à 1.

    L'API Onoff n'ouvre pas encore cet endpoint (annoncé « à venir » par l'éditeur). La
    tentative est faite quand même : le jour où il ouvre, l'envoi marchera sans
    modification. En attendant on rend 501 avec la marche à suivre — pas 500, parce que
    ce n'est pas une panne.
    """
    d = await request.json()
    r = _onoff().envoyer_sms(site, d.get("depuis", ""), d.get("vers", ""), d.get("texte", ""))
    if r.get("ok"):
        return r
    from fastapi.responses import JSONResponse
    code = {"indisponible": 501, "vide": 400, "trop_long": 400, "numero": 400}.get(
        r.get("raison"), 502)
    return JSONResponse(status_code=code, content=r)


@app.get("/api/sites/{site}/onoff/statistiques")
def api_onoff_statistiques(site: str, depuis: str = "", jusqu_a: str = ""):
    return _onoff().statistiques(site, depuis=depuis, jusqu_a=jusqu_a)


@app.get("/api/sites/{site}/onoff/config")
def api_onoff_config(site: str):
    """État de la configuration, SANS jamais renvoyer la clé."""
    o = _onoff()
    return {"configure": o.configure(site),
            "variable": f"ONOFF_API_KEY_{site.upper()}",
            "url_webhook": o.url_webhook(site),
            "jeton_webhook_present": bool(o.jeton_webhook()),
            "console": "https://admin.onoffbusiness.com/integrations/api-keys",
            "verification": o.verifier(site) if o.configure(site) else {"status": "missing_key"}}


@app.patch("/api/sites/{site}/onoff/config")
async def api_onoff_config_maj(site: str, request: Request):
    """Enregistre (ou efface) la clé API du site. Valeur vide = suppression."""
    d = await request.json()
    valeur = (d.get("cle") or "").strip() or None
    _write_env_var(f"ONOFF_API_KEY_{site.upper()}", valeur)
    o = _onoff()
    return {"ok": True, "configure": o.configure(site),
            "verification": o.verifier(site) if valeur else {"status": "missing_key"}}


@app.post("/api/sites/{site}/onoff/appel")
async def api_onoff_appel(site: str, request: Request):
    """Prépare un appel depuis l'interface, et le consigne dans le suivi.

    L'API Onoff ne sait PAS composer un numéro : c'est l'application Onoff (ou son
    extension Chrome) qui le fait. Cette route rend donc l'URI `tel:` que l'écran ouvrira,
    et enregistre l'intention côté CRM. La preuve que l'appel a bien eu lieu viendra du
    journal Onoff par webhook — un fait, et non une case cochée à la main.
    """
    o = _onoff()
    d = await request.json()
    numero = o.e164(d.get("numero") or "")
    if not numero:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={"ok": False, "error": "numéro absent ou invalide"})

    role, user = _qui(request)
    consigne = {}
    email = (d.get("email") or "").strip()
    if email:
        _scripts_dans_le_chemin()
        import followup_backend as fb
        consigne = fb.enregistrer_appel(
            site, email, role, user,
            outcome=d.get("outcome") or "appel_lance",
            note=d.get("note") or f"Appel lancé depuis Cheffer vers {o.lisible(numero)}",
            statut=d.get("statut") or None,
            next_action_at=d.get("next_action_at"),
            est_un_appel=True,
        )
    return {"ok": True, "tel": f"tel:{numero}", "numero": numero,
            "numero_lisible": o.lisible(numero), "suivi": consigne}


@app.post("/api/webhook/onoff/{site}")
async def api_webhook_onoff(site: str, request: Request):
    """Réception des journaux Onoff (appels, SMS, messagerie).

    Le jeton passe en `?token=` — c'est le mécanisme déjà en place pour les autres
    webhooks, vérifié par le middleware avant d'arriver ici. On répond 200 même sur une
    charge inattendue : un fournisseur qui reçoit une erreur réessaie en boucle, et un log
    mal formé ne justifie pas de faire tomber le flux entier.
    """
    try:
        charge = await request.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "ignore": "corps illisible"}
    if site not in _known_site_codes():
        return {"ok": False, "ignore": "site inconnu"}

    o = _onoff()
    o.assurer_schema()
    lots = charge if isinstance(charge, list) else [charge]
    recus, erreurs = 0, []
    for c in lots:
        if not isinstance(c, dict):
            continue
        try:
            r = o.enregistrer_evenement(site, c)
            if r.get("ok"):
                recus += 1
            else:
                erreurs.append(r.get("error"))
        except Exception as e:  # noqa: BLE001
            erreurs.append(str(e)[:200])
    return {"ok": True, "recus": recus, "erreurs": erreurs[:5]}


# ── Modules toggle + mini-RAG par site ────────────────────────────────────────

@app.get("/api/sites/{site}/modules")
def api_modules_list(site: str):
    """Retourne la liste des modules + état (enabled/instructions) + statut connecteurs."""
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.modules_backend import get_modules
    return get_modules(site)


@app.patch("/api/sites/{site}/modules/{module_id}")
async def api_modules_patch(site: str, module_id: str, request: Request):
    """Active/désactive un module ou met à jour ses instructions IA.
    Body : {enabled?: bool, instructions?: str}"""
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    data = await request.json()
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.modules_backend import toggle, set_instructions
    out = {}
    if "enabled" in data:
        out.update(toggle(site, module_id, bool(data["enabled"])))
    if "instructions" in data:
        out.update(set_instructions(site, module_id, data["instructions"]))
    if not out:
        return {"error": "no_changes"}
    return out


# ── Mailnjoy Check API ────────────────────────────────────────────────────────

@app.get("/api/mailnjoy/credit")
def api_mailnjoy_credit():
    """Retourne le solde de crédit Mailnjoy. None si pas configuré."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from mailnjoy_check import get_credit, is_configured
    if not is_configured():
        return {"configured": False, "credit": None}
    credit = get_credit()
    return {"configured": True, "credit": credit, "checked_at": datetime.now(timezone.utc).isoformat()}


@app.get("/api/mailnjoy/status")
def api_mailnjoy_status():
    """Retourne l'état du module Mailnjoy : configuré ? crédit ? pending queue ?"""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from mailnjoy_check import get_credit, is_configured
    import duckdb
    out = {"configured": is_configured(), "credit": None, "pending_count": 0}
    if out["configured"]:
        out["credit"] = get_credit()
    try:
        c = _duck(BASE_DIR / "data" / "god_mode.duckdb")
        out["pending_count"] = c.execute("SELECT COUNT(*) FROM scrappe_pending").fetchone()[0]
        c.close()
    except Exception:
        pass
    return out


@app.post("/api/mailnjoy/test-credentials")
async def api_mailnjoy_test(request: Request):
    """Teste un couple ID/SECRET en appelant /v1/credit sans toucher au .env.
    Body: {id, secret}
    Returns: {ok, credit?, error?}"""
    body = await request.json()
    mid = (body.get("id") or "").strip()
    msec = (body.get("secret") or "").strip()
    if not mid or not msec:
        return {"ok": False, "error": "id et secret requis"}
    try:
        r = requests.get("https://api.mailnjoy.com/v1/credit",
                         headers={"mailnjoy-id": mid, "mailnjoy-secret": msec},
                         timeout=10)
        if r.status_code == 200:
            return {"ok": True, "credit": int(r.text.strip())}
        if r.status_code == 401:
            return {"ok": False, "error": "Identifiants invalides (401)"}
        return {"ok": False, "error": f"Erreur Mailnjoy {r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": f"Erreur réseau : {e}"}


@app.post("/api/mailnjoy/drain")
def api_mailnjoy_drain(site: str = None):
    """Déclenche un drain manuel de la queue Mailnjoy.
    Optionnel pour tester l'intégration sans attendre le cron."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from mailnjoy_check import check_pending_queue
    return check_pending_queue(site_code=site)


@app.get("/api/sites/{site}/workflow/counters")
def api_workflow_counters(site: str):
    """Compteurs workflow refondus pour la nouvelle state machine.
    Scrapés / Ajoutés / Nettoyés / Envoyés."""
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    import duckdb
    c = _duck(BASE_DIR / "data" / "god_mode.duckdb")
    try:
        # Scrapés = tout ce qui est passé par le scraper (en pending OU en scrappe)
        scraped_pending = c.execute("SELECT COUNT(*) FROM scrappe_pending WHERE site_code = ?", [site]).fetchone()[0]
        scraped_in_scrappe = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code = ?", [site]).fetchone()[0]
        scraped = scraped_pending + scraped_in_scrappe

        # Ajoutés = mailnjoy_valid + pushed_emelia (réellement utilisables)
        added = c.execute("""SELECT COUNT(*) FROM scrappe
                             WHERE site_code = ? AND status IN ('mailnjoy_valid', 'pushed_emelia', 'manual_review')""",
                          [site]).fetchone()[0]

        # Envoyés = pushed_emelia
        sent = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code = ? AND status = 'pushed_emelia'", [site]).fetchone()[0]

        # Nettoyés = rejetés validator (en DB) + supprimés Mailnjoy (lus depuis logs)
        rejected_validator = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code = ? AND status = 'rejected'", [site]).fetchone()[0]
        # Compte les lignes du log deletions
        mailnjoy_killed = 0
        log_f = BASE_DIR / "logs" / "mailnjoy_deletions.log"
        if log_f.exists():
            try:
                mailnjoy_killed = sum(1 for _ in log_f.read_text().splitlines() if _.strip())
            except Exception:
                pass

        cleaned = rejected_validator + mailnjoy_killed
    finally:
        c.close()

    return {
        "site":     site,
        "scraped":  scraped,
        "added":    added,
        "cleaned":  cleaned,
        "sent":     sent,
        "breakdown": {
            "pending_mailnjoy":    scraped_pending,
            "rejected_validator":  rejected_validator,
            "mailnjoy_killed":     mailnjoy_killed,
        }
    }


@app.post("/api/mailnjoy/save-credentials")
async def api_mailnjoy_save_credentials(request: Request):
    """Sauvegarde MAILNJOY_ID + MAILNJOY_SECRET dans le .env. Body: {id, secret}."""
    body = await request.json()
    mid = (body.get("id") or "").strip()
    msec = (body.get("secret") or "").strip()
    if not mid or not msec:
        return {"ok": False, "error": "id et secret requis"}
    # Test d'abord
    try:
        r = requests.get("https://api.mailnjoy.com/v1/credit",
                         headers={"mailnjoy-id": mid, "mailnjoy-secret": msec}, timeout=10)
        if r.status_code != 200:
            return {"ok": False, "error": f"Identifiants refusés ({r.status_code})"}
    except Exception as e:
        return {"ok": False, "error": f"Erreur réseau : {e}"}

    # Write to .env (replace existing lines)
    env_f = BASE_DIR / ".env"
    lines = env_f.read_text().splitlines() if env_f.exists() else []
    lines = [l for l in lines if not l.strip().startswith("MAILNJOY_ID=") and not l.strip().startswith("MAILNJOY_SECRET=")]
    lines.append(f"MAILNJOY_ID={mid}")
    lines.append(f"MAILNJOY_SECRET={msec}")
    env_f.write_text("\n".join(lines).rstrip() + "\n")
    return {"ok": True, "credit": int(r.text.strip())}


# ── Pool mutualisé contacts (2026-05-22) ──────────────────────────────────────

@app.get("/api/sites/{site}/vision")
def api_vision(site: str):
    """La base de contacts d'un site, vue de haut : étapes, enrichissement, engagement,
    secteurs. Un seul appel — la page Vision en faisait cinq et n'en tirait rien de lisible.

    L'enrichissement data.gouv y est intégré : il décrivait la même base depuis un encart
    de la page Acquisition, où il n'avait rien à faire.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import pool_pg
    import contacts_pool_backend as pool
    # Lu dans PostgreSQL depuis le 2026-08-20 : la page décrivait la base en interrogeant
    # le pool DuckDB, c'est-à-dire le fichier que le scraping verrouille. Équivalence des
    # deux sources vérifiée chiffre par chiffre avant la bascule — seul l'engagement
    # diffère, et à l'avantage de PostgreSQL : il compte le journal d'événements complet
    # là où le pool ne retient que le dernier signal par contact.
    # Repli sur DuckDB si PostgreSQL est injoignable : une page qui affiche est préférable
    # à une page qui explique pourquoi elle n'affiche pas.
    try:
        out = pool_pg.vision_contacts(site)
    except Exception:
        try:
            out = pool.vision_contacts(site)
            out["source"] = "duckdb (repli)"
        except Exception as e:  # noqa: BLE001
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=503, content={"error": f"base indisponible: {e}"[:200]})
    try:
        out["datagouv"] = pool_pg.enrichment_stats()
    except Exception:
        try:
            out["datagouv"] = pool.enrichment_stats()
        except Exception:
            out["datagouv"] = None
    try:
        out["enrichissement_suivi"] = _enrichissement_suivi()
    except Exception:
        out["enrichissement_suivi"] = None
    return out


def _lecture_pool(nom: str):
    """La fonction de lecture du pool, servie par PostgreSQL quand il répond.

    Étape 5 de la migration : les écrans lisent PostgreSQL, le pool DuckDB n'est plus que
    le repli. Ce repli n'est pas décoratif — c'est justement le fichier que le scraping
    verrouille, donc la raison d'être de la bascule ; mais une page qui affiche des chiffres
    d'il y a une heure vaut mieux qu'une page qui explique pourquoi elle n'affiche rien.

    Le choix se refait à CHAQUE appel, sans redémarrage : un PostgreSQL redevenu joignable
    est repris au premier rafraîchissement. L'échec est journalisé — un repli silencieux
    laisserait croire la bascule faite alors qu'elle ne l'est plus (leçon du 19/08).

    Équivalence des deux sources prouvée chiffre par chiffre : tests/test_pg_acquisition.py.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import pool_pg
    import contacts_pool_backend as _duck

    def appeler(*a, **k):
        try:
            return getattr(pool_pg, nom)(*a, **k)
        except Exception as e:  # noqa: BLE001
            print(f"[pool] {nom}: PostgreSQL indisponible ({type(e).__name__}: {e}) "
                  f"— repli sur DuckDB", flush=True)
            return getattr(_duck, nom)(*a, **k)
    return appeler


@app.get("/api/sites/{site}/pool/contacts")
def api_pool_contacts(site: str, request: Request, state: str = "", sectors_in: str = "",
                      source: str = "", search: str = "", engagement: str = "",
                      etape: str = "", limit: int = 500, offset: int = 0):
    """Liste les contacts du pool utilisés par ce site (avec filtres + recherche).
    `engagement` : openers | clickers (filtre comportemental)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from contacts_pool_backend import ETAPES
    list_contacts_for_site = _lecture_pool("list_contacts_for_site")
    count_contacts_for_site = _lecture_pool("count_contacts_for_site")
    compter_par_etape = _lecture_pool("compter_par_etape")
    import garde_lecture as gl
    role, qui = _qui(request)
    etat = gl.verifier(qui, role)
    if not etat["ok"]:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=429, content=gl.refus(etat))
    lim = gl.plafonner(role, limit)
    filtres = dict(
        state=state.split(",") if state else None,
        sectors_in=sectors_in.split(",") if sectors_in else None,
        source=source.split(",") if source else None,
        search_email=search or None,
        engagement=engagement or None,
        etape=etape.split(",") if etape else None,
    )
    # `total` est le nombre de contacts correspondant aux filtres, pas le nombre de lignes
    # rendues : sans lui l'interface ne peut pas paginer, et affichait « 25 contacts »
    # quelle que soit la taille réelle de la sélection.
    contacts = list_contacts_for_site(site_code=site, limit=lim, offset=offset, **filtres)
    gl.journaliser(qui, role, site, "pool/contacts", len(contacts))
    return {
        "contacts": contacts,
        "total": count_contacts_for_site(site_code=site, **filtres),
        # `limit` rendu = celui APPLIQUÉ, pas celui demandé : l'interface doit paginer sur
        # ce qu'elle a reçu, sinon elle croit avoir tout et saute des contacts.
        "limit": lim, "offset": offset,
        "plafonne": lim < limit,
        # Le vocabulaire des étapes vient du serveur : c'est lui qui les calcule.
        "etapes": ETAPES,
        # Compteurs par étape POUR LES AUTRES FILTRES en cours (l'étape elle-même est
        # exclue) : un onglet doit annoncer ce qu'il contient si on clique dessus.
        "etapes_counts": compter_par_etape(
            site_code=site, **{k: v for k, v in filtres.items() if k != "etape"}),
    }


@app.get("/api/sites/{site}/pool/filter-values")
def api_pool_filter_values(site: str):
    """Valeurs distinctes (secteur, source) + compteurs pour les filtres Acquisition."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    return _lecture_pool("filter_values_for_site")(site)


@app.get("/api/sites/{site}/pool/contacts/{contact_id}")
def api_pool_contact_detail(site: str, contact_id: str):
    """Detail d'un contact + historique cross-site."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from contacts_pool_backend import find_by_email_global, get_history_for_site, _conn
    import duckdb as _dd
    c = _pool_conn()
    try:
        cols = [r[1] for r in c.execute("PRAGMA table_info(contacts)").fetchall()]
        row = c.execute("SELECT * FROM contacts WHERE id = ?", [contact_id]).fetchone()
        if not row:
            return {"error": "not_found"}
        contact = dict(zip(cols, row))
        # parse JSON cols
        import json as _json
        for k in ("sectors", "email_validation_reasons", "mailnjoy_check"):
            v = contact.get(k)
            if isinstance(v, str):
                try: contact[k] = _json.loads(v)
                except: pass
        # historique tous sites
        hist_cols = [r[1] for r in c.execute("PRAGMA table_info(contact_site_history)").fetchall()]
        h_rows = c.execute("SELECT * FROM contact_site_history WHERE contact_id = ? ORDER BY added_to_site_at DESC", [contact_id]).fetchall()
        sites_history = []
        for hr in h_rows:
            d = dict(zip(hist_cols, hr))
            sh = d.get("state_history")
            if isinstance(sh, str):
                try: d["state_history"] = _json.loads(sh)
                except: pass
            # cast timestamps en str
            for ts_col in ("added_to_site_at", "last_action_at", "email_sent_at",
                           "emelia_opened_at", "emelia_clicked_at", "emelia_replied_at",
                           "emelia_bounced_at", "emelia_unsubscribed_at",
                           "last_contacted_by_site_at"):
                if d.get(ts_col): d[ts_col] = str(d[ts_col])
            sites_history.append(d)
        contact["sites_history"] = sites_history
        # timestamps contacts
        for ts_col in ("created_at", "updated_at", "blacklisted_at"):
            if contact.get(ts_col): contact[ts_col] = str(contact[ts_col])
        return contact
    finally:
        c.close()


@app.get("/api/sites/{site}/pool/stats")
def api_pool_stats(site: str):
    """Stats du pool pour ce site."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    return _lecture_pool("stats_for_site")(site)


# ── Enrichissement data.gouv (pool mutualisé, cf. scripts/datagouv_enrich.py) ──

def _datagouv_running() -> bool:
    try:
        return subprocess.run(["pgrep", "-f", "datagouv_enrich.py"],
                              capture_output=True).returncode == 0
    except Exception:
        return False


_ENRICH_LANCE_A = {"at": 0.0}


def _enrichissement_suivi(nb_runs: int = 20) -> dict:
    """État réel de l'enrichissement data.gouv : dernières EXÉCUTIONS et retard éventuel.

    L'écran affichait « pas tourné depuis plus de 24 h » en se fondant sur la date du
    dernier contact enrichi. Or le cron de 6 h 30 tourne tous les jours : quand il ne reste
    rien à enrichir, il ne écrit aucune ligne et cette date se fige. On lisait donc un
    retard là où le travail était simplement à jour.

    Le retard se mesure maintenant sur les EXÉCUTIONS, et il n'y a de retard que s'il reste
    effectivement des contacts à traiter.
    """
    import time as _t
    journal = BASE_DIR / "logs" / "datagouv_runs.jsonl"
    runs = []
    if journal.exists():
        for ligne in journal.read_text().splitlines()[-nb_runs:]:
            try:
                runs.append(json.loads(ligne))
            except Exception:
                pass
    runs.reverse()
    dernier = runs[0] if runs else None

    reste = 0
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        from contacts_pool_backend import enrichment_stats
        reste = int(enrichment_stats().get("remaining") or 0)
    except Exception:
        pass

    heures = None
    if dernier and dernier.get("fin"):
        try:
            fin = datetime.fromisoformat(dernier["fin"])
            if fin.tzinfo is None:
                fin = fin.replace(tzinfo=timezone.utc)
            heures = round((datetime.now(timezone.utc) - fin).total_seconds() / 3600, 1)
        except Exception:
            heures = None

    # 30 h : le cron passe toutes les 24 h, on laisse une marge avant de crier au loup.
    en_retard = reste > 0 and (heures is None or heures > 30)
    return {"runs": runs, "dernier": dernier, "heures_depuis": heures,
            "reste_a_traiter": reste, "en_retard": en_retard,
            "en_cours": _datagouv_running(),
            "log_path": "logs/datagouv_enrich.log"}


def _lancer_enrichissement(limite: int | None = None) -> dict:
    """Lance l'enrichissement en tâche de fond. Utilisé par la route ET par le rattrapage
    automatique : un seul endroit qui sait construire la commande."""
    import time as _t
    if _datagouv_running():
        return {"ok": False, "message": "Un enrichissement est déjà en cours."}
    cmd = ["python3", "scripts/datagouv_enrich.py"]
    if limite:
        cmd += ["--limit", str(int(limite))]
    log_f = open(str(BASE_DIR / "logs/datagouv_enrich.log"), "w")
    try:
        subprocess.Popen(cmd, cwd=str(BASE_DIR), stdout=log_f, stderr=subprocess.STDOUT)
    finally:
        log_f.close()
    _ENRICH_LANCE_A["at"] = _t.time()
    return {"ok": True, "message": "Enrichissement lancé en tâche de fond."}


@app.get("/api/admin/pression")
def api_pression_marketing(limite: int = 50):
    """Pression marketing : combien de communications chaque contact a reçues sur 30 jours.

    La règle (décision user du 2026-08-20) : un contact ne reçoit pas plus de N
    communications par mois glissant, tous canaux et tous sites confondus. Elle remplace la
    fenêtre de 120 jours POUR LES SEGMENTS — une action ciblée « relancer ceux qui ont
    ouvert » ne peut pas exclure ceux qui ont ouvert.

    Comptée sur `email_events`, seul journal qui garde chaque envoi.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import pool_pg
    maxi = pool_pg.pression_max()
    jours = pool_pg.PRESSION_JOURS
    try:
        repartition = [{"envois": int(r[0]), "contacts": int(r[1])} for r in pool_pg._q(f"""
            SELECT n, count(*) FROM (
                SELECT email, count(*) AS n FROM email_events
                WHERE event_type = 'sent' AND occurred_at > now() - interval '{jours} days'
                GROUP BY 1) x
            GROUP BY 1 ORDER BY 1""")]
        au_plafond = [{"email": r[0], "envois": int(r[1]),
                       "dernier": str(r[2])[:16], "libre_le": str(r[3])[:10]}
                      for r in pool_pg._q(f"""
            SELECT email, count(*) AS n, max(occurred_at),
                   min(occurred_at) + interval '{jours} days'
            FROM email_events
            WHERE event_type = 'sent' AND occurred_at > now() - interval '{jours} days'
            GROUP BY 1 HAVING count(*) >= %(maxi)s
            ORDER BY 2 DESC LIMIT %(limite)s""",
            {"maxi": maxi or 10 ** 6, "limite": min(500, max(1, limite))})]
        total = pool_pg._q(f"""
            SELECT count(DISTINCT email) FROM email_events
            WHERE event_type = 'sent' AND occurred_at > now() - interval '{jours} days'""")[0][0]
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": f"pression illisible: {e}"[:200]})

    return {"max": maxi, "jours": jours, "repartition": repartition,
            "au_plafond": au_plafond, "contactes_30j": int(total or 0),
            "reglage": "PRESSION_MAX_MOIS dans .env"}


@app.get("/api/sites/{site}/statistiques")
def api_statistiques(site: str, jours: int | None = None, limite: int = 10):
    """Le comportement des destinataires : par canal, par type d'adresse, par secteur, par zone.

    Ne lit QUE des campagnes réellement envoyées (`campaign_recipients`, une ligne par
    envoi journalisé). Les événements reçus sans envoi par destinataire — Sweego en masse
    — sont rendus à part dans `angles_morts`, jamais fondus dans les taux.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import stats_backend as st
    try:
        return st.tableau_de_bord(site, jours, limite)
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        msg = str(e)
        if "campaign_recipients" in msg and "exist" in msg:
            return JSONResponse(status_code=503, content={
                "error": "table des destinataires absente",
                "remede": "lancer une reconstruction (bouton « Recalculer »)"})
        return JSONResponse(status_code=503, content={"error": msg[:200]})


@app.post("/api/sites/{site}/statistiques/reconstruire")
def api_statistiques_reconstruire(site: str):
    """Rebâtit la table des destinataires depuis le journal d'événements.

    Reconstruction complète et idempotente : quelques milliers de lignes. Appelée par le
    cron horaire et par le bouton de la page — les deux peuvent se marcher dessus sans
    conséquence, la dernière écriture gagne et dit la même chose.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import stats_backend as st
    try:
        return st.reconstruire()
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/admin/roles")
def api_roles_etat(request: Request):
    """La matrice des droits : rôles, pages, et qui voit quoi. Superadmin uniquement."""
    sess = getattr(request.state, "session", None) or {}
    if sess.get("role") != "superadmin":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403,
                            content={"error": "réservé au superadmin"})
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import roles_backend as rbk
    try:
        return rbk.etat()
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.post("/api/admin/roles")
async def api_roles_enregistrer(request: Request):
    """Remplace les droits d'UN rôle. Superadmin uniquement, et jamais sur lui-même.

    Deux verrous plutôt qu'un : la route refuse tout autre rôle, et `roles_backend` refuse
    de restreindre `superadmin` même si l'appel arrive. Le second verrou protège du jour où
    quelqu'un appellera la fonction depuis un script.
    """
    sess = getattr(request.state, "session", None) or {}
    if sess.get("role") != "superadmin":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={"error": "réservé au superadmin"})
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import roles_backend as rbk
    body = await request.json()
    try:
        return rbk.enregistrer(body.get("role") or "", body.get("pages") or [],
                               par=sess.get("username") or "")
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/mes-pages")
def api_mes_pages(request: Request):
    """Les pages que MON rôle a le droit de voir — lu de la session, pas du navigateur.

    C'est cette route que la sidebar interroge. Elle ne prend aucun paramètre : impossible
    de demander « les pages du rôle superadmin » en changeant un argument.
    """
    sess = getattr(request.state, "session", None) or {}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import roles_backend as rbk
    # L'URL de chaque page voyage AVEC la clé. La sidebar tenait sa propre table clé → URL,
    # qu'il fallait penser à compléter en même temps que le catalogue serveur : une page
    # ajoutée d'un seul côté s'affichait au chargement puis DISPARAISSAIT dès la réponse,
    # faute de correspondance. C'est arrivé à Mozart le 2026-08-24. Une seule source de
    # vérité supprime la classe de bug entière.
    # Tout ce bloc est DANS le try : c'est la route qui alimente la sidebar entière, elle
    # doit répondre même si le catalogue des droits est en panne — sinon une erreur de
    # configuration vide le menu de tout le monde.
    urls: dict = {}
    beta: list = []
    beta_ok = False
    try:
        urls = {p["cle"]: p["url"] for p in rbk.PAGES}
        # Le catalogue complet, et pas seulement les URL. La sidebar s'en servait
        # uniquement pour FILTRER ses entrées écrites en dur : une page déclarée ici mais
        # absente de son code restait invisible pour toujours — c'est arrivé à Mozart le
        # 24/08, puis à Onoff et aux adresses d'envoi le 25/08. Avec le libellé et le
        # groupe, l'écran peut AJOUTER ce qu'il ne connaît pas.
        catalogue = [{"cle": p["cle"], "label": p["label"], "groupe": p.get("groupe") or "",
                      "url": p["url"]} for p in rbk.PAGES]
        beta = sorted(rbk.pages_beta())
        beta_ok = (sess.get("username") or "").strip().lower() in rbk.beta_testeurs()
    except Exception as e:  # noqa: BLE001
        print(f"[api] catalogue des pages illisible ({type(e).__name__}: {e})", flush=True)
    # La sidebar a besoin de savoir DEUX choses de plus : quelles pages sont en bêta, et
    # si ce compte y a droit. Elle les affiche grisées et étiquetées plutôt que de les
    # cacher — une fonctionnalité qui apparaît un jour sans prévenir surprend.
    try:
        return {"role": sess.get("role") or "",
                "pages": rbk.pages_autorisees(sess.get("role") or ""), "urls": urls,
                "catalogue": catalogue, "beta": beta, "beta_autorise": beta_ok}
    except Exception:  # noqa: BLE001
        return {"role": sess.get("role") or "",
                "pages": [p["cle"] for p in rbk.PAGES], "urls": urls,
                "catalogue": catalogue, "beta": beta, "beta_autorise": beta_ok}


@app.get("/api/admin/secteurs")
def api_secteurs(site: str = "lcr"):
    """La politique des secteurs : prioritaire / secondaire / interdit.

    Ce classement pilote l'ordre de la file de scraping et le ciblage Basile — il n'est
    pas déclaratif. `source` dit s'il s'agit du choix enregistré ou de la proposition par
    défaut, et `file` chiffre ce que le classement change concrètement dans la file.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import secteurs_backend as sb
    try:
        out = sb.politique(site)
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503,
                            content={"error": f"politique illisible: {e}"[:200]})
    try:
        out["file"] = sb.resume_file(site)
    except Exception:  # noqa: BLE001 — la file est un indicateur, pas le contenu de la page
        out["file"] = {}
    return out


@app.put("/api/admin/secteurs")
async def api_secteurs_put(request: Request):
    """Enregistre le classement. Réservé aux admins (cf. `_ADMIN_PREFIXES`).

    Sort dans la foulée de la file les cibles des secteurs devenus interdits : sans ça, le
    classement serait vrai à l'écran et faux dans la nuit qui suit.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import secteurs_backend as sb
    corps = await request.json()
    site = (corps.get("site") or "lcr").strip()
    _r, user = _qui(request)
    try:
        return sb.enregistrer(site, corps, par=user or "ui")
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503,
                            content={"error": f"enregistrement impossible: {e}"[:200]})


@app.get("/api/admin/etat-technique")
def api_etat_technique(historique: int = 0):
    """Relevé technique de la plateforme — le contrôle du matin.

    `historique=N` renvoie en plus les N derniers relevés quotidiens, pour voir si un
    compteur stagne. Lecture seule sur les bases métier.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import etat_technique as et
    try:
        out = et.releve()
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": f"relevé impossible: {e}"[:200]})
    if historique:
        try:
            out["historique"] = et.historique(min(60, max(1, historique)))
        except Exception:
            out["historique"] = []
    return out


@app.get("/api/enrichment/runs")
def api_enrichment_runs():
    """Historique des exécutions d'enrichissement + fin du log, pour la page dédiée."""
    suivi = _enrichissement_suivi(nb_runs=50)
    try:
        texte = (BASE_DIR / "logs" / "datagouv_enrich.log").read_text()
        suivi["log_tail"] = texte[-8000:]
    except Exception:
        suivi["log_tail"] = ""
    return suivi


@app.get("/api/enrichment/stats")
def api_enrichment_stats():
    """Stats globales d'enrichissement data.gouv (pool mutualisé, non par site)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from contacts_pool_backend import enrichment_stats
    import time as _t
    out = enrichment_stats()
    out["running"] = _datagouv_running()
    suivi = _enrichissement_suivi()
    out["suivi"] = suivi
    # « Arrête de me le demander, fais-le » : si l'enrichissement est réellement en retard
    # ET qu'il reste du travail, on le lance. Le garde-fou d'une heure évite qu'un écran
    # ouvert en boucle ne relance un job déjà parti.
    if (suivi["en_retard"] and not suivi["en_cours"]
            and (_t.time() - _ENRICH_LANCE_A["at"]) > 3600):
        out["relance_auto"] = _lancer_enrichissement()
    return out


@app.post("/api/enrichment/run")
async def api_enrichment_run(request: Request):
    """Lance l'enrichissement data.gouv en tâche de fond (incrémental : anti-join,
    ne traite que les contacts pas encore enrichis ; cache + rate-limit + backoff).
    Réservé au rôle admin (cf. _ADMIN_PREFIXES) — c'est un job système."""
    data = {}
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            data = await request.json()
        except Exception:
            data = {}
    # Cast défensif : un `limit` non numérique est ignoré (pas de 500).
    limite = None
    try:
        limite = int(data["limit"]) if data.get("limit") else None
    except (TypeError, ValueError, KeyError):
        limite = None
    return _lancer_enrichissement(limite)


@app.get("/api/sites/{site}/pool/depletion-alert")
def api_pool_depletion(site: str, threshold: int = 10):
    """Alerte secteur épuisé pour ce site."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from contacts_pool_backend import pool_sectors
    check_pool_depletion = _lecture_pool("check_pool_depletion")
    from god_mode_backend import SECTORS_GOD_MODE
    sectors = pool_sectors() or SECTORS_GOD_MODE  # secteurs RÉELS du pool, pas la liste scrapable figée
    return {"depleted": check_pool_depletion(site, sectors, threshold=threshold)}


@app.get("/api/sites/{site}/contacts/pool/count")
def api_pool_count_secteur(site: str, sector: str = ""):
    """Combien de contacts contactables pour UN secteur.

    Appelée par l'éditeur de newsletters pour annoncer la taille de la cible avant envoi.
    La route n'existait pas : l'appel renvoyait 404, la page l'avalait dans un `catch` et
    n'affichait aucun compteur. Personne ne pouvait le voir — le symptôme d'une route
    absente et celui d'un compteur à zéro sont identiques à l'écran.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    if not (sector or "").strip():
        return {"sector": "", "count": 0, "error": "secteur manquant"}
    import contacts_pool_backend as pool
    try:
        return {"sector": sector, "count": pool.count_available_for_sector(site, sector)}
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": f"pool indisponible: {e}"[:200]})


# ── Suivi commercial (mini-CRM) ───────────────────────────────────────────────
# Le rôle et l'identité viennent de la SESSION, jamais du corps de la requête : sinon
# n'importe qui pourrait s'annoncer administrateur pour voir les contacts d'un collègue.

def _qui(request: Request) -> tuple[str, str]:
    sess = getattr(request.state, "session", None) or {}
    return (sess.get("role") or ""), (sess.get("username") or "")


@app.get("/api/public/plaquette/{site}/{secteur}.pdf")
def api_plaquette_publique(site: str, secteur: str, societe: str = ""):
    """La plaquette du secteur, en accès libre — c'est un document commercial.

    Publique par nécessité : le lien vit dans un email envoyé à un prospect, qui n'a pas
    de compte. Sans donnée de la base : le PDF est engendré depuis `argumentaire.py`, il ne
    contient que notre discours et, éventuellement, le nom de la société destinataire passé
    en paramètre. Rien à fuiter.
    """
    from fastapi.responses import Response, JSONResponse
    if site not in ("lcr", "mkd", "tst"):
        return JSONResponse(status_code=404, content={"error": "site inconnu"})
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import plaquette as pl
    try:
        pdf = pl.construire(secteur, (societe or "")[:80])
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{pl.nom_fichier(secteur)}"',
        "Cache-Control": "public, max-age=3600",
    })


@app.post("/api/sites/{site}/opportunites")
async def api_opportunite_creer(site: str, request: Request):
    """« Le client dit oui » — le commercial transmet, il ne conclut pas seul."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import opportunites as op
    role, user = _qui(request)
    b = await request.json()
    try:
        return op.creer(site, b.get("email") or "", user or "inconnu", b.get("notes") or "")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


@app.get("/api/sites/{site}/opportunites")
def api_opportunites_lister(site: str, request: Request, statut: str = ""):
    """La file des opportunités. Un commercial ne voit que les siennes ; les
    administrateurs voient tout — c'est eux qui envoient les contrats."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import opportunites as op
    role, user = _qui(request)
    tout = role in ("admin", "superadmin")
    try:
        return {"opportunites": op.lister(site, statut, "" if tout else user),
                "vue_complete": tout, "etats": op.ETATS}
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/sites/{site}/opportunites/count")
def api_opportunites_compte(site: str, request: Request):
    """Le nombre d'affaires en attente de validation — la pastille du menu.

    Requête volontairement minuscule : elle est appelée à chaque affichage de la barre
    latérale. Un commercial compte les siennes, un administrateur compte tout, puisque
    c'est lui qui doit agir.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import opportunites as op
    role, user = _qui(request)
    try:
        opps = op.lister(site, "a_valider", "" if role in ("admin", "superadmin") else user)
        return {"a_valider": len(opps)}
    except Exception:  # noqa: BLE001 — une pastille absente vaut mieux qu'un menu en erreur
        return {"a_valider": 0}


@app.post("/api/sites/{site}/opportunites/{oid}")
async def api_opportunite_changer(site: str, oid: str, request: Request):
    """Fait avancer une opportunité. Réservé aux administrateurs : envoyer un contrat et
    déclarer une signature engagent l'entreprise, pas seulement le commercial."""
    sess = getattr(request.state, "session", None) or {}
    if sess.get("role") not in ("admin", "superadmin"):
        return {"ok": False, "error": "réservé aux administrateurs"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import opportunites as op
    b = await request.json()
    try:
        return op.changer(site, oid, b.get("statut") or "", sess.get("username") or "",
                          montant_mensuel=b.get("montant_mensuel"),
                          commission_pct=b.get("commission_pct"),
                          responsable=b.get("responsable"),
                          notes=b.get("notes"), perdu_motif=b.get("perdu_motif"))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


@app.get("/api/sites/{site}/ventes")
def api_ventes(site: str):
    """Le récapitulatif commercial : signés, en cours, MRR, commissions."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import opportunites as op
    try:
        return op.ventes(site)
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/sites/{site}/a-rappeler/script")
def api_script_appel(site: str, secteur: str = ""):
    """Le script d'appel du secteur : accroche, question, valeur, objections, sortie."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import argumentaire as ar
    return ar.script(secteur)


@app.get("/api/sites/{site}/a-rappeler/creneaux")
def api_creneaux(site: str, jour: str = ""):
    """Les créneaux libres — ceux du module de rendez-vous déjà en place, pas d'autres.

    Sans `jour` : les jours réservables. Avec : les créneaux de ce jour-là.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import booking_backend as bb
    try:
        if jour:
            return {"jour": jour, "creneaux": bb.available_slots(site, jour)}
        return {"jours": bb.available_days(site)}
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.post("/api/sites/{site}/a-rappeler/rdv")
async def api_prendre_rdv(site: str, request: Request):
    """Pose un rendez-vous pour ce prospect, depuis la fiche, sur un créneau libre.

    Deux choses que la route publique de prise de rendez-vous fait autrement, et qu'il
    fallait décider ici :

    - **La confirmation au client n'est PAS automatique.** Sur le lien public, le prospect
      s'inscrit lui-même et attend un accusé. Ici, c'est le commercial qui pose le créneau
      pendant l'appel : c'est LUI qui décide si le client reçoit un récapitulatif, parce
      que lui seul sait ce qui vient d'être dit. Un email qui part sans qu'il l'ait vu
      passer est exactement ce qu'on veut éviter.
    - **Le téléphone est vérifié et enregistré.** Un rendez-vous sans numéro est un
      rendez-vous qu'on ne pourra pas honorer : la réponse le signale, et si le commercial
      saisit le numéro manquant, on le range dans la fiche du contact.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import booking_backend as bb
    import followup_backend as fb
    role, user = _qui(request)
    b = await request.json()
    email = (b.get("email") or "").strip().lower()
    creneau = (b.get("slot_start") or "").strip()
    tel = (b.get("tel") or "").strip()
    envoyer = bool(b.get("envoyer_email", False))
    if not email or not creneau:
        return {"ok": False, "error": "email et créneau requis"}
    try:
        r = bb.create_booking(site, b.get("motif") or "demo", creneau,
                              b.get("nom") or email, email, tel, b.get("note") or "")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}
    if not r.get("ok", True):
        return r

    # Le numéro saisi à la volée rejoint la fiche : sans ça, il faudrait le ressaisir au
    # rendez-vous suivant, et il finirait sur un papier.
    tel_enregistre = False
    if tel:
        try:
            import contacts_pool_backend as pool
            tel_enregistre = bool(pool.create_in_pool({"email": email, "tel": tel},
                                                      primary_source="crm"))
        except Exception:  # noqa: BLE001
            pass

    # Par MAILDOSO, pas par Sweego (décision Camille, 2026-08-21) : un rendez-vous posé
    # pendant un appel prolonge une conversation, il doit partir de l'adresse qui a servi
    # aux échanges précédents — et c'est là que le prospect répondra.
    notif = None
    if envoyer:
        try:
            notif = bb.envoyer_confirmation_maildoso(r["booking"], r["config"], site)
        except Exception as e:  # noqa: BLE001
            notif = {"email": {"ok": False, "error": str(e)[:150]}}

    # Le rendez-vous est un ÉVÉNEMENT de la fiche : sans cette trace, le commercial suivant
    # ne saurait pas qu'un rendez-vous a été pris pendant l'appel.
    try:
        detail = f"Rendez-vous posé le {creneau}"
        detail += (" · récapitulatif envoyé au client" if (notif or {}).get("email", {}).get("ok")
                   else " · sans email au client" if not envoyer
                   else " · envoi du récapitulatif ÉCHOUÉ")
        fb.journaliser(site, email, user, "rdv", detail)
    except Exception:  # noqa: BLE001
        pass

    return {**r, "email_envoye": bool((notif or {}).get("email", {}).get("ok")),
            "email_erreur": (notif or {}).get("email", {}).get("error"),
            "expediteur": (notif or {}).get("email", {}).get("mailbox"),
            "tel_enregistre": tel_enregistre}


@app.post("/api/sites/{site}/a-rappeler/presentation")
async def api_envoyer_presentation(site: str, request: Request):
    """Envoie l'email de présentation du secteur, plaquette PDF jointe, depuis une boîte
    Maildoso. Un envoi nominatif, un seul destinataire — ce n'est pas une campagne."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import argumentaire as ar, plaquette as pl, maildoso_backend as md
    import followup_backend as fb
    role, user = _qui(request)
    b = await request.json()
    email = (b.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "destinataire invalide"}
    secteur = (b.get("secteur") or "").strip().lower()
    contact = {"prenom": b.get("prenom") or "", "societe": b.get("societe") or ""}
    # La plaquette est EN ATTENTE (décision Camille, 2026-08-21 : « les documents .pdf ne
    # sont pas bons pour le moment »). Elle ne part donc plus par défaut : il faut la
    # demander explicitement. Le jour où elle est validée, ce défaut repasse à True — et
    # d'ici là, aucun prospect ne reçoit un document qu'on ne veut pas montrer.
    joindre = bool(b.get("joindre_plaquette", False))
    lien = (f"https://api.cheffer.email/api/public/plaquette/{site}/{secteur}.pdf"
            if joindre and secteur else "")
    modele = ar.email_presentation(secteur, contact, user, site=site, lien_plaquette=lien)
    sujet = (b.get("sujet") or modele["sujet"]).strip()
    corps = (b.get("corps") or modele["corps"]).strip()
    try:
        pieces = []
        if joindre:
            pieces = [{"nom": pl.nom_fichier(secteur),
                       "contenu": pl.construire(secteur, contact["societe"]),
                       "type": "application/pdf"}]
        r = md.send_email(email, sujet, text=corps, html=modele.get("html"), site=site,
                          to_name=contact["societe"] or None, pieces_jointes=pieces)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}
    if r.get("ok"):
        try:
            fb.journaliser(site, email, user, "email",
                           f"Présentation {secteur or 'générique'} envoyée depuis "
                           f"{r.get('mailbox')}" + (" (plaquette jointe)" if joindre else ""))
        except Exception:  # noqa: BLE001
            pass
    return r


@app.post("/api/sites/{site}/a-rappeler/blacklist")
async def api_blacklister(site: str, request: Request):
    """Blackliste définitivement ce contact : plus aucun envoi, sur aucun site."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import contacts_pool_backend as pool
    import followup_backend as fb
    role, user = _qui(request)
    b = await request.json()
    email = (b.get("email") or "").strip().lower()
    if not email:
        return {"ok": False, "error": "email requis"}
    motif = (b.get("motif") or f"blacklisté depuis la fiche par {user}")[:200]
    try:
        ok = pool.set_global_blacklist(email, motif)
        try:
            fb.journaliser(site, email, user, "blacklist", motif)
        except Exception:  # noqa: BLE001
            pass
        return {"ok": bool(ok), "email": email, "motif": motif}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


@app.get("/api/sites/{site}/mon-activite")
def api_mon_activite(site: str, request: Request, qui: str = ""):
    """Le tableau de bord du rappelant : sa journée, sa série, où ça mord.

    `qui` n'est lu QUE pour un admin — il permet de regarder l'activité d'un commercial
    sans prendre son compte. Un non-admin ne voit que la sienne, quoi qu'il demande :
    le paramètre est ignoré, pas refusé, pour que l'interface reste simple.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import commercial_backend as cb
    role, user = _qui(request)
    cible = qui if (qui and role in ("admin", "superadmin")) else user
    try:
        return cb.tableau_de_bord(site, cible, role)
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/sites/{site}/a-rappeler")
def api_a_rappeler(site: str, request: Request, vue: str = "mes"):
    """Liste d'appels du commercial connecté.

    `vue` : mes | vivier | tous (administrateurs). Le filtrage est appliqué côté serveur
    par `followup_backend.lister` — l'interface ne fait que demander.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import followup_backend as fb
    import garde_lecture as gl
    role, user = _qui(request)
    etat = gl.verifier(user, role)
    if not etat["ok"]:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=429, content=gl.refus(etat))
    try:
        res = fb.lister(site, role, user, vue=vue if vue in ("mes", "vivier", "tous") else "mes")
        n = len(res.get("contacts") or res.get("a_rappeler") or []) if isinstance(res, dict) else 0
        gl.journaliser(user, role, site, "a-rappeler", n)
        return res
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": f"suivi indisponible: {e}"[:200]})


@app.get("/api/sites/{site}/a-rappeler/count")
def api_a_rappeler_count(site: str, request: Request):
    """Compteurs seuls, pour la pastille du menu — pas de fiches, pas de journal.

    Le menu est affiché sur TOUTES les pages et se rafraîchit en boucle : il n'a pas à
    télécharger 75 fiches pour écrire un nombre. La route renvoie aussi l'écart entre le
    chiffre du tableau de bord et ce que la liste sait montrer (`en_attente`).
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import followup_backend as fb
    role, user = _qui(request)
    try:
        return fb.compter(site, role, user)
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": f"suivi indisponible: {e}"[:200]})


@app.get("/api/sites/{site}/a-rappeler/commerciaux")
def api_a_rappeler_commerciaux(site: str, request: Request):
    """Comptes auxquels un contact peut être attribué, restreints à ce site.

    Renvoie aussi `par_defaut` : le commercial qui reçoit les rappels d'office. L'interface
    ne doit pas le deviner — un nom écrit en dur des deux côtés finit toujours par diverger.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import followup_backend as fb
    return {"commerciaux": [u for u in fb.commerciaux()
                            if not u["sites"] or site in u["sites"]],
            "par_defaut": fb.commercial_par_defaut(site)}


@app.get("/api/sites/{site}/a-rappeler/journal")
def api_a_rappeler_journal(site: str, request: Request, email: str = ""):
    """Historique des interactions d'un contact."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import followup_backend as fb
    if not email:
        return {"journal": []}
    return {"email": email, "journal": fb.journal(site, email)}


@app.post("/api/sites/{site}/a-rappeler/assigner")
async def api_a_rappeler_assigner(site: str, request: Request):
    """Attribue un contact à un commercial, ou le remet au vivier (`vers` absent/null)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import followup_backend as fb
    role, user = _qui(request)
    d = await request.json()
    vers = d.get("vers") or None
    # « __moi__ » : l'interface ne connaît pas le nom du compte connecté, et le lui faire
    # deviner l'obligerait à un appel supplémentaire. On résout ici, où la session fait foi —
    # un client ne peut donc pas s'attribuer un contact au nom d'un collègue.
    if vers == "__moi__":
        vers = user
    r = fb.assigner(site, d.get("email", ""), vers, role, user)
    if not r.get("ok"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content=r)
    return r


@app.post("/api/sites/{site}/a-rappeler/flash")
async def api_a_rappeler_flash(site: str, request: Request):
    """Épingle / dépingle un contact : il remonte en tête de la liste d'appels."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import followup_backend as fb
    role, user = _qui(request)
    d = await request.json()
    r = fb.basculer_flash(site, d.get("email", ""), role, user)
    if not r.get("ok"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content=r)
    return r


@app.post("/api/sites/{site}/a-rappeler/retirer")
async def api_a_rappeler_retirer(site: str, request: Request):
    """Retire un contact de la liste d'appels (ou l'y remet avec `annuler`).

    Retrait et non suppression : le contact reste au référentiel, son journal aussi, et
    `pg_reconcile` ne le fera pas réapparaître demain matin.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import followup_backend as fb
    role, user = _qui(request)
    d = await request.json()
    r = fb.retirer(site, d.get("email", ""), role, user, annuler=bool(d.get("annuler")))
    if not r.get("ok"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content=r)
    return r


@app.post("/api/sites/{site}/a-rappeler/appel")
async def api_a_rappeler_appel(site: str, request: Request):
    """Consigne une interaction : issue, statut, note, prochaine relance."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import followup_backend as fb
    role, user = _qui(request)
    d = await request.json()
    r = fb.enregistrer_appel(
        site, d.get("email", ""), role, user,
        statut=d.get("statut") or None,
        outcome=d.get("outcome") or "",
        note=d.get("note") or "",
        next_action_at=d.get("next_action_at"),
        est_un_appel=bool(d.get("est_un_appel", True)),
    )
    if not r.get("ok"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content=r)
    return r


@app.get("/api/sites/{site}/contacts/pool/count")
def api_pool_count_secteur(site: str, sector: str = ""):
    """Combien de contacts contactables pour UN secteur.

    Appelée par l'éditeur de newsletters pour annoncer la taille de la cible avant envoi.
    La route n'existait pas : l'appel renvoyait 404, la page l'avalait dans un `catch` et
    n'affichait aucun compteur. Personne ne pouvait le voir — le symptôme d'une route
    absente et celui d'un compteur à zéro sont identiques à l'écran.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    if not (sector or "").strip():
        return {"sector": "", "count": 0, "error": "secteur manquant"}
    import contacts_pool_backend as pool
    try:
        return {"sector": sector, "count": pool.count_available_for_sector(site, sector)}
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": f"pool indisponible: {e}"[:200]})


@app.get("/api/sites/{site}/pool/sector-availability")
def api_pool_sector_availability(site: str):
    """Dispo de pioche par secteur canonique (mêmes filtres que pick_for_campaign).
    Alimente la Vision : compteurs réels par secteur, triés décroissant."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from contacts_pool_backend import count_available_for_sector, pool_sectors
    from god_mode_backend import SECTORS_GOD_MODE
    sectors = pool_sectors() or SECTORS_GOD_MODE  # secteurs RÉELS du pool, pas la liste scrapable figée
    rows = [{"sector": s_, "available": count_available_for_sector(site, s_)} for s_ in sectors]
    rows.sort(key=lambda r: r["available"], reverse=True)
    return {"sectors": rows, "total_available": sum(r["available"] for r in rows)}


@app.get("/api/sites/{site}/pool/pick")
def api_pool_pick(site: str, sector: str, limit: int = 30):
    """Aperçu de la pioche pour une campagne (Step 3 du wizard Campagnes)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from contacts_pool_backend import pick_for_campaign, count_available_for_sector
    return {
        "available_total": count_available_for_sector(site, sector),
        "picked":          pick_for_campaign(site, sector, limit=limit),
    }


@app.post("/api/sites/{site}/pool/contacts/{contact_id}/change-state")
async def api_pool_change_state(site: str, contact_id: str, request: Request):
    """Change state d'un contact pour ce site (manuel via UI)."""
    body = await request.json()
    new_state = body.get("state")
    note = body.get("note", "")
    if not new_state:
        return {"ok": False, "error": "state required"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from contacts_pool_backend import change_state_for_site
    ok = change_state_for_site(contact_id, site, new_state, by="ui_manual", note=note)
    return {"ok": ok}


# ── Logo de contact (fiche client) : scrape du site web ou upload manuel ──────

CONTACT_LOGOS_DIR = LOGOS_DIR / "contacts"
CONTACT_LOGOS_DIR.mkdir(parents=True, exist_ok=True)


def _save_contact_logo(contact_id: str, raw: bytes) -> str:
    """Convertit l'image en PNG (max 400px, ratio conservé), la stocke et
    met à jour contacts.logo_url. Retourne l'URL servie."""
    from PIL import Image
    import io as _io
    img = Image.open(_io.BytesIO(raw))
    img = img.convert("RGBA")
    w, h = img.size
    if max(w, h) > 400:
        ratio = 400 / max(w, h)
        img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)
    out = CONTACT_LOGOS_DIR / f"{contact_id}.png"
    img.save(out, format="PNG", optimize=True)
    url = f"/assets/logos/contacts/{contact_id}.png"
    import duckdb as _dd
    c = _dd.connect(str(BASE_DIR / "data" / "contacts.duckdb"))
    try:
        c.execute("UPDATE contacts SET logo_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                  [url, contact_id])
    finally:
        c.close()
    return url


def _extract_logo_candidates(html: str, base_url: str) -> list[str]:
    """Extrait les URLs candidates de logo depuis le HTML (og:image, icônes, <img> logo)."""
    import re
    from urllib.parse import urljoin
    cands: list[str] = []
    # og:image / twitter:image (les 2 ordres d'attributs)
    for pat in (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
    ):
        cands += re.findall(pat, html, re.I)
    # <img> dont src/class/alt évoque un logo
    for m in re.finditer(r'<img[^>]+>', html, re.I):
        tag = m.group(0)
        if re.search(r'logo', tag, re.I):
            src = re.search(r'src=["\']([^"\']+)["\']', tag)
            if src:
                cands.append(src.group(1))
    # icônes (apple-touch-icon d'abord : plus grandes que favicon)
    for pat in (
        r'<link[^>]+rel=["\']apple-touch-icon[^"\']*["\'][^>]+href=["\']([^"\']+)["\']',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']apple-touch-icon[^"\']*["\']',
        r'<link[^>]+rel=["\'](?:shortcut )?icon["\'][^>]+href=["\']([^"\']+)["\']',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\'](?:shortcut )?icon["\']',
    ):
        cands += re.findall(pat, html, re.I)
    cands.append("/favicon.ico")
    # absolutise + dédoublonne en conservant l'ordre
    seen, out = set(), []
    for u in cands:
        if u.startswith("data:"):
            continue
        full = urljoin(base_url, u.strip())
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


@app.post("/api/sites/{site}/pool/contacts/{contact_id}/fetch-logo")
async def api_pool_contact_fetch_logo(site: str, contact_id: str, request: Request):
    """Tente de récupérer le logo depuis le site web du contact
    (og:image → <img> logo → apple-touch-icon → favicon)."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    website = (body.get("website") or "").strip()
    import duckdb as _dd
    if not website:
        c = _pool_conn()
        try:
            row = c.execute("SELECT website FROM contacts WHERE id = ?", [contact_id]).fetchone()
        finally:
            c.close()
        website = (row[0] or "").strip() if row else ""
    if not website:
        return {"ok": False, "error": "Aucune URL de site renseignée pour ce contact."}
    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    import requests as _rq
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ChefferBot/1.0)"}
    try:
        page = _rq.get(website, headers=headers, timeout=10, allow_redirects=True)
        html = page.text or ""
        base = page.url or website
    except Exception as e:
        return {"ok": False, "error": f"Site injoignable : {str(e)[:120]}"}

    for cand in _extract_logo_candidates(html, base)[:8]:
        try:
            r = _rq.get(cand, headers=headers, timeout=10)
            if r.status_code != 200 or not r.content or len(r.content) < 200:
                continue
            url = _save_contact_logo(contact_id, r.content)
            return {"ok": True, "url": url, "source": cand}
        except Exception:
            continue
    return {"ok": False, "error": "Aucun logo exploitable trouvé sur le site — importe une image PNG."}


@app.post("/api/sites/{site}/pool/contacts/{contact_id}/logo")
async def api_pool_contact_logo_upload(site: str, contact_id: str, file: UploadFile = File(...)):
    """Upload manuel d'une image (PNG/JPG/WebP) pour la fiche du contact."""
    try:
        raw = await file.read()
        url = _save_contact_logo(contact_id, raw)
        return {"ok": True, "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/sites/{site}/pool/contacts/{contact_id}/blacklist")
async def api_pool_blacklist(site: str, contact_id: str, request: Request):
    """Blacklist GLOBAL d'un contact (depuis l'UI Acquisition)."""
    body = await request.json()
    reason = body.get("reason", "manual blacklist via UI")
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from contacts_pool_backend import set_global_blacklist, find_by_email_global
    import duckdb as _dd
    c = _pool_conn()
    try:
        row = c.execute("SELECT email FROM contacts WHERE id = ?", [contact_id]).fetchone()
    finally:
        c.close()
    if not row:
        return {"ok": False, "error": "not_found"}
    set_global_blacklist(row[0], reason=reason)
    return {"ok": True}


# ============================================================================
# Templates cold email par secteur — propositions IA + édition + verrouillage
# (2026-05-25) Modèle 1-ligne-par-email. Store : email_templates (god_mode.duckdb).
# L'IA propose ; le user édite et verrouille chaque email. Pas d'envoi auto.
# Cf. context/lcr/sector-angles.md + scripts/email_generator.py.
# ============================================================================
@app.post("/api/sites/{site}/templates/generate")
async def api_templates_generate(site: str, request: Request):
    """Génère (DeepSeek) les 3 propositions d'un secteur, sans écraser un email verrouillé. Body: {sector}."""
    body = await request.json()
    sector = (body.get("sector") or "").strip()
    if not sector:
        return {"ok": False, "error": "sector required"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import email_templates_backend as etb
    try:
        return etb.generate(site, sector)
    except Exception as e:
        return {"ok": False, "error": f"generation failed: {e}"}


@app.get("/api/sites/{site}/templates")
async def api_templates_list(site: str):
    """Récap par secteur (nb d'emails + nb verrouillés) + secteurs supportés (pour l'UI)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import email_templates_backend as etb
    from email_generator import supported_sectors
    return {"ok": True, "sectors": etb.list_sectors(site), "available": supported_sectors()}


@app.get("/api/sites/{site}/templates/{sector}")
async def api_templates_get(site: str, sector: str):
    """Les emails d'un secteur (first / relance1 / relance2)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import email_templates_backend as etb
    return {"ok": True, "emails": etb.get_sector(site, sector)}


@app.put("/api/sites/{site}/templates/{sector}/{kind}")
async def api_templates_update(site: str, sector: str, kind: str, request: Request):
    """Édition manuelle d'un email. Body: {subject, body_html}. Re-valide, rouvre (unlock)."""
    body = await request.json()
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import email_templates_backend as etb
    return etb.update(site, sector, kind, body.get("subject", ""), body.get("body_html", ""))


@app.post("/api/sites/{site}/templates/{sector}/{kind}/lock")
async def api_templates_lock(site: str, sector: str, kind: str):
    """Verrouille (approuve) un email — refuse si non conforme."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import email_templates_backend as etb
    return etb.set_lock(site, sector, kind, True)


@app.post("/api/sites/{site}/templates/{sector}/{kind}/unlock")
async def api_templates_unlock(site: str, sector: str, kind: str):
    """Déverrouille un email (pour réédition)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import email_templates_backend as etb
    return etb.set_lock(site, sector, kind, False)


_HUMANIZE_SYS = ("Tu es Juliette, commerciale chez Le Client ROI. Tu RÉÉCRIS des cold emails B2B "
                 "pour qu'ils sonnent 100% humains et naturels — jamais 'écrit par une IA'. "
                 "Tu réponds UNIQUEMENT avec le corps HTML de l'email, sans aucun texte autour, "
                 "sans bloc markdown.")

_HUMANIZE_PROMPT = (
    "Réécris ce cold email pour qu'il sonne NATUREL et HUMAIN (comme écrit par une vraie "
    "commerciale), surtout PAS générique / template / IA.\n\n"
    "RÈGLES STRICTES (à respecter à la lettre) :\n"
    "- Le 1er paragraphe d'ouverture reste EXACTEMENT : <p>{{firstName}},</p> "
    "(la variable porte déjà la salutation).\n"
    "- Conserve TOUS les liens existants à l'identique (href inchangés), en particulier le "
    "lien de prise de RDV (tidycal/calendly) et {{UNSUBSCRIBE_LINK}}.\n"
    "- Conserve le bloc signature (la <table> avec les coordonnées) tel quel.\n"
    "- Garde la variable {{field1}} si elle est présente (= nom de l'entreprise).\n"
    "- Bannis les clichés : « c'est mission impossible », « Curieux de voir comment ? », "
    "« ROI x50 », « je me permets », « n'hésitez pas », « j'espère que vous allez bien ».\n"
    "- VOUVOIEMENT obligatoire (vous), jamais le tutoiement (B2B).\n"
    "- Phrases courtes, contractions, du concret et du spécifique. ~130 mots de prose max. UN seul CTA.\n"
    "- Réponds UNIQUEMENT le corps en HTML (<p>…</p>, <a>, <strong>, la table signature). Rien d'autre.\n\n"
    "EMAIL À RÉÉCRIRE :\n__BODY__"
)


@app.post("/api/sites/{site}/templates/{sector}/{kind}/humanize")
async def api_template_humanize(site: str, sector: str, kind: str, request: Request):
    """Réécrit le corps d'un email via DeepSeek pour le rendre plus humain. Ne sauvegarde
    PAS : renvoie {ok, subject, body_html} que le front met dans le brouillon."""
    body = await request.json()
    subject = (body.get("subject") or "").strip()
    body_html = (body.get("body_html") or "").strip()
    if not body_html:
        return {"ok": False, "error": "body_html requis"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from email_generator import validate_email
    from email_templates_backend import normalize_greeting
    from llm_call import call_llm
    prompt = _HUMANIZE_PROMPT.replace("__BODY__", body_html)
    try:
        out = call_llm(prompt, max_tokens=1500, temperature=0.85, system=_HUMANIZE_SYS,
                       module="cold_email", action=f"humanize-{sector}-{kind}", site=site)
    except Exception as e:
        return {"ok": False, "error": f"DeepSeek: {e}"}
    out = (out or "").strip()
    if out.startswith("```"):
        out = out.strip("`")
        if out[:4].lower() == "html":
            out = out[4:]
        out = out.strip()
    out = normalize_greeting(out)
    # Garde-fous : ne jamais perdre la désinscription ni casser le HTML.
    if "{{UNSUBSCRIBE_LINK}}" in body_html and "{{UNSUBSCRIBE_LINK}}" not in out:
        return {"ok": False, "error": "La réécriture a supprimé le lien de désinscription — annulé."}
    if "<p" not in out:
        return {"ok": False, "error": "Réécriture invalide (pas de HTML) — annulé."}
    errs = validate_email(subject, out)
    return {"ok": True, "subject": subject, "body_html": out, "validation_errors": errs}


# ============================================================================
# Newsletters HTML éditables (structure verrouillée, texte + images) — 2026-05-26
# Structures de base = structures/*.html ; versions = table html_templates.
# ============================================================================
@app.get("/api/sites/{site}/html/structures")
async def api_html_structures(site: str):
    """Liste les structures HTML de base disponibles."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import html_templates_backend as htb
    return {"ok": True, "structures": htb.list_structures()}


@app.get("/api/sites/{site}/html/structures/{name}")
async def api_html_structure_get(site: str, name: str):
    """HTML d'une structure de base (point de départ d'une édition)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import html_templates_backend as htb
    html = htb.get_structure(name)
    if html is None:
        return {"ok": False, "error": "structure introuvable"}
    return {"ok": True, "name": name, "html": html}


@app.get("/api/sites/{site}/html/templates")
async def api_html_templates_list(site: str):
    """Versions sauvegardées (newsletters éditées)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import html_templates_backend as htb
    return {"ok": True, "versions": htb.list_versions(site)}


@app.get("/api/sites/{site}/html/templates/{vid}")
async def api_html_template_get(site: str, vid: str):
    """HTML complet d'une version sauvegardée."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import html_templates_backend as htb
    v = htb.get_version(site, vid)
    return {"ok": bool(v), "version": v}


@app.post("/api/sites/{site}/html/templates")
async def api_html_template_save(site: str, request: Request):
    """Sauvegarde une version éditée. Body: {name, html, source}."""
    body = await request.json()
    name = (body.get("name") or "").strip()
    html = body.get("html") or ""
    if not name or not html:
        return {"ok": False, "error": "name et html requis"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import html_templates_backend as htb
    sess = getattr(request.state, "session", None)
    by = (sess or {}).get("username", "ui")
    return {"ok": True, "id": htb.save_version(site, name, html, source=body.get("source", ""), by=by)}


@app.patch("/api/sites/{site}/html/templates/{vid}")
async def api_html_template_rename(site: str, vid: str, request: Request):
    """Renomme un message validé. Body: {name}. Le nouveau nom remonte dans le wizard campagne."""
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "name requis"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import html_templates_backend as htb
    htb.rename_version(site, vid, name)
    return {"ok": True}


@app.delete("/api/sites/{site}/html/templates/{vid}")
async def api_html_template_delete(site: str, vid: str, request: Request):
    sess = getattr(request.state, "session", None)
    if not sess or sess.get("role") != "superadmin":
        return {"ok": False, "error": "Suppression réservée aux superadmin."}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import html_templates_backend as htb
    htb.delete_version(site, vid)
    return {"ok": True}


@app.post("/api/sites/{site}/html/lint")
async def api_html_lint(site: str, request: Request):
    """Lint email via emailens (lint + analyze), local. Body: {html, ref?, target_type?}. Persiste le resultat."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import email_lint_backend as elb
    body = await request.json()
    html = body.get("html") or ""
    target_type = (body.get("target_type") or "structure").strip()
    target_ref = (body.get("ref") or "").strip()
    res = elb.run_lint(html)
    if res.get("ok") and target_ref:
        sess = getattr(request.state, "session", None)
        by = (sess or {}).get("username", "ui")
        try:
            elb.save_result(site, target_type, target_ref, res, by=by)
        except Exception:
            pass
    return res


@app.get("/api/sites/{site}/html/lint")
def api_html_lint_results(site: str):
    """Derniers resultats de lint stockes (badges de la liste newsletters)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import email_lint_backend as elb
    return {"results": elb.get_all_results(site)}


@app.post("/api/sites/{site}/mass-campaigns/bat")
async def api_mass_campaign_bat(site: str, request: Request):
    """BAT Sweego : envoie le message validé à une seule adresse de test. Body: {message_id, subject, email}."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import sweego_backend as sw
    import html_templates_backend as htb
    body = await request.json()
    message_id = (body.get("message_id") or "").strip()
    subject = (body.get("subject") or "").strip()
    email = (body.get("email") or "").strip()
    if not message_id or not subject or not email or "@" not in email:
        return {"ok": False, "error": "message_id, subject et email requis"}
    msg = htb.resolve_campaign_message(site, message_id)
    if not msg or not msg.get("html"):
        return {"ok": False, "error": "message introuvable"}
    res = sw.send_campaign(f"{site}-bat-{message_id[:8]}", subject, msg["html"], [email], dry_run=False)
    return res


@app.post("/api/sites/{site}/mass-campaigns/create")
async def api_mass_campaign_create(site: str, request: Request):
    """Mass campaign via Sweego depuis un message valide. Body: {name, sector, message_id, subject, volume_target, dry_run?}."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import sweego_backend as sw, html_templates_backend as htb, email_lint_backend as elb
    from contacts_pool_backend import pick_for_campaign, count_available_for_sector
    body = await request.json()
    name = (body.get("name") or "").strip()
    sector = (body.get("sector") or "").strip()
    message_id = (body.get("message_id") or "").strip()
    subject = (body.get("subject") or "").strip()
    volume = int(body.get("volume_target") or 30)
    dry_run = bool(body.get("dry_run"))
    if not name or not sector or not message_id or not subject:
        return {"ok": False, "error": "name, sector, message_id, subject requis"}
    msg = htb.get_version(site, message_id)
    if not msg:
        return {"ok": False, "error": "message valide introuvable"}
    if not dry_run:
        stored = elb.get_all_results(site).get(f"version:{message_id}")
        if stored is None:
            return {"ok": False, "error": "Teste d'abord ce message (bouton Tester) avant l'envoi."}
        if stored.get("blocking"):
            return {"ok": False, "error": "Message bloquant au lint. Corrige-le avant l'envoi."}
    avail = count_available_for_sector(site, sector)
    if avail == 0:
        return {"ok": False, "error": f"aucun contact dispo secteur {sector}"}
    contacts = pick_for_campaign(site, sector, limit=min(volume, avail))
    emails = [c["email"] for c in contacts if c.get("email")]
    if not emails:
        return {"ok": False, "error": "aucun email exploitable"}
    campaign_id = f"{site}-{sector}-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    res = sw.send_campaign(campaign_id, subject, msg["html"], emails, dry_run=dry_run)
    if not res.get("ok"):
        return res
    if dry_run:
        return {"ok": True, "dry_run": True, "would_send": len(emails), "campaign_id": campaign_id}
    from contacts_pool_backend import mark_pushed_to_emelia
    for c in contacts:
        try:
            mark_pushed_to_emelia(c["id"], site, campaign_id, "")
        except Exception:
            pass
    sess = getattr(request.state, "session", None)
    by = (sess or {}).get("username", "ui")
    rid = sw.record_campaign(site, name, campaign_id, subject, sector, message_id,
                             len(emails), res.get("transaction_id"), by=by)
    return {"ok": True, "campaign_id": campaign_id, "sent": res.get("sent"), "record_id": rid}


@app.get("/api/sites/{site}/mass-campaigns")
def api_mass_campaigns_list(site: str):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import sweego_backend as sw
    return {"campaigns": sw.list_campaigns(site)}


@app.get("/api/sites/{site}/mass-campaigns/stats")
def api_mass_campaigns_stats(site: str, date_start: str = "", date_end: str = ""):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import sweego_backend as sw
    return {"engagement": sw.engagement_stats(date_start or None, date_end or None), "msp": sw.msp_stats()}


# ── Campagnes unifiées multi-canal (hub) ────────────────────────────────────────
@app.get("/api/sites/{site}/channels")
def api_campaign_channels(site: str):
    """Canaux d'envoi disponibles + cap/jour live."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import deliverability_agent as da
    import sweego_backend as sw
    emelia_caps = da.channel_caps(site, "emelia")
    sweego_ok = bool(sw._env().get("SWEEGO_API_KEY"))
    try:
        import maildoso_backend as md
        maildoso_boxes = [m for m in md.list_mailboxes(site) if m.get("status") == "active"]
        maildoso_cap = sum(m.get("daily_cap") or 0 for m in maildoso_boxes)
        maildoso_left = md.remaining_quota_today(site)
    except Exception:
        maildoso_boxes, maildoso_cap, maildoso_left = [], 0, 0
    _caps = sorted({m.get("daily_cap") or 0 for m in maildoso_boxes})
    _per_box = (f"{_caps[0]}" if len(_caps) == 1 else f"{_caps[0]}–{_caps[-1]}") if _caps else "0"
    return {"channels": [
        {"key": "emelia", "label": "Cold email", "sub": "Emelia",
         "enabled": (emelia_caps.get("plateau") or 0) > 0,
         "daily_cap": emelia_caps.get("plateau") or 0,
         "note": "Séquence à froid, plafonnée au warmup des expéditeurs."},
        {"key": "sweego", "label": "Masse", "sub": "Sweego",
         "enabled": sweego_ok, "daily_cap": da.channel_caps(site, "sweego").get("plateau"),
         "note": "Newsletters / annonces en volume."},
        {"key": "maildoso", "label": "Cold email maison", "sub": "Maildoso",
         "enabled": bool(maildoso_boxes) and maildoso_cap > 0, "daily_cap": maildoso_cap,
         "mailboxes": len(maildoso_boxes), "per_mailbox_cap": _per_box,
         "remaining_today": maildoso_left,
         "note": f"Envoi SMTP maison — {len(maildoso_boxes)} boîtes @leclient-roi.com en rotation, "
                 f"{_per_box}/jour par boîte (montée auto après chaque campagne propre)."},
    ]}


@app.post("/api/sites/{site}/campaigns/target-count")
async def api_campaign_target_count(site: str, request: Request):
    """Nb de contacts éligibles (Mailnjoy valid < 6 mois) pour des secteurs donnés.
    Body: {sectors:[...], regions?:[...], depts?:[...], cleaned_within_days?}."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import contacts_pool_backend as pool
    body = await request.json()
    sectors = body.get("sectors") or []
    regions = body.get("regions") or []
    depts = body.get("depts") or []
    engagement = (body.get("engagement") or "").strip() or None
    days = int(body.get("cleaned_within_days") or 180)
    # Ciblage par segment : ses règles priment sur les critères manuels.
    if (body.get("segment_id") or "").strip():
        import segments_backend as sb
        seg = sb.get_segment(body["segment_id"].strip())
        if not seg or seg.get("site_code") != site:
            return {"total": 0, "by_sector": {}, "error": "segment introuvable"}
        try:
            total = pool.count_for_segment(site, seg["rules"], cleaned_within_days=days)
        except Exception as e:  # noqa: BLE001
            return {"total": 0, "by_sector": {}, "error": f"pool indisponible : {str(e)[:100]}"}
        return {"total": total, "by_sector": {}, "segment": seg["name"],
                "summary": seg["summary"], "cleaned_within_days": days}
    per = {}
    seen_total = 0
    for sec in sectors:
        n = pool.count_available_for_sector(site, sec, cleaned_within_days=days,
                                            regions=regions, depts=depts,
                                            engagement=engagement)
        per[sec] = n
        seen_total += n
    return {"by_sector": per, "total": seen_total, "cleaned_within_days": days,
            "engagement": engagement}


# ── Mozart : scénarios d'automatisation ────────────────────────────────────────
# Le graphe est stocké et rendu TEL QUEL, dans la forme de l'éditeur (nodes/edges de
# React Flow). Aucune traduction entre l'écran et la base : c'est ce qui garantit que ce
# qu'on voit est ce qui s'exécute.

@app.get("/api/sites/{site}/mozart")
def api_mozart_liste(site: str):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import mozart
    scs = mozart.scenarios(site)
    # Les compteurs sont joints ici plutôt que demandés un par un : la liste en affiche
    # dix, ce serait dix allers-retours pour trois nombres.
    for sc in scs:
        try:
            st = mozart.stats(sc["id"])
            sc["inscrits"] = st["total_inscrits"]
            sc["par_statut"] = st["inscriptions"]
            sc["resume"] = mozart.resume(sc["id"], site)
        except Exception:  # noqa: BLE001
            # Forme CONSTANTE même en cas d'échec : une ligne sans `resume` obligerait
            # l'écran à distinguer « zéro » de « absent » à chaque champ.
            sc["inscrits"] = None
            sc["par_statut"] = {}
            sc["resume"] = None
    ouverte, pourquoi = mozart.fenetre_ouverte()
    return {"scenarios": scs,
            "fenetre": {"ouverte": ouverte, "motif": pourquoi,
                        "debut": mozart.FENETRE_DEBUT, "fin": mozart.FENETRE_FIN,
                        "fuseau": mozart.FUSEAU,
                        # ISO plutôt qu'un libellé : le serveur tourne en locale anglaise
                        # et rendrait « Monday 24 August ». La mise en forme française
                        # appartient à l'écran, qui connaît la langue de qui regarde.
                        "maintenant": mozart.maintenant_paris().isoformat(timespec="minutes")}}


@app.post("/api/sites/{site}/mozart")
async def api_mozart_creer(site: str, request: Request):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import mozart
    import pool_pg
    d = await request.json()
    role, qui = _qui(request)
    graphe = d.get("graphe") or {"nodes": [], "edges": []}
    c = pool_pg._conn()
    try:
        with c.cursor() as cur:
            cur.execute("""INSERT INTO mozart_scenarios (site_code, nom, description,
                                                         graphe, cree_par)
                           VALUES (%s, %s, %s, %s::jsonb, %s) RETURNING id""",
                        (site, (d.get("nom") or "Nouveau scénario")[:120],
                         d.get("description"), json.dumps(graphe), qui))
            sid = str(cur.fetchone()[0])
        c.commit()
    finally:
        pool_pg._rendre(c)
    return {"ok": True, "scenario": mozart.scenario(sid)}


def _scripts_dans_le_chemin() -> None:
    """Ajoute `scripts/` à `sys.path` — une seule fois.

    Les routes le faisaient sans garde : chaque requête allongeait `sys.path` d'une entrée
    pour toujours, et tout `import` ultérieur paie ce parcours.
    """
    chemin = str(BASE_DIR / "scripts")
    if chemin not in sys.path:
        sys.path.insert(0, chemin)


def _mozart_du_site(site: str, sid: str):
    """Le scénario, s'il existe ET s'il appartient à ce site. Sinon None.

    Ce contrôle était recopié dans huit routes — et OUBLIÉ dans la neuvième, celle qui
    écrit : un compte n'ayant accès qu'à `mkd` pouvait réécrire un scénario `lcr`. Un
    garde recopié à la main est un garde qu'on peut oublier ; celui-ci ne se recopie plus.
    """
    _scripts_dans_le_chemin()
    import mozart
    sc = mozart.scenario(sid)
    return sc if sc and sc["site_code"] == site else None


def _introuvable():
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=404, content={"error": "scénario introuvable"})


@app.get("/api/sites/{site}/mozart-expediteurs")
def api_mozart_expediteurs(site: str):
    """Les canaux d'envoi et leurs expéditeurs réels, pour le nœud « email ».

    Déclaré AVANT `/mozart/{sid}` serait inutile ici — le chemin ne peut pas être confondu
    avec un identifiant puisqu'il ne vit pas sous `/mozart/`. C'est délibéré : une route
    `/mozart/expediteurs` aurait été capturée par `{sid}` un jour ou l'autre.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import mozart
    return {"canaux": mozart.expediteurs(site)}


@app.get("/api/sites/{site}/mozart/{sid}")
def api_mozart_lire(site: str, sid: str):
    _scripts_dans_le_chemin()
    import mozart
    sc = _mozart_du_site(site, sid)
    if not sc:
        return _introuvable()
    sc["stats"] = mozart.stats(sid)
    sc["resume"] = mozart.resume(sid, site)
    sc["problemes"] = mozart.verifier(sc["graphe"] or {})
    ouverte, pourquoi = mozart.fenetre_ouverte()
    sc["fenetre"] = {"ouverte": ouverte, "motif": pourquoi,
                     "debut": mozart.FENETRE_DEBUT, "fin": mozart.FENETRE_FIN}
    return sc


@app.put("/api/sites/{site}/mozart/{sid}")
async def api_mozart_enregistrer(site: str, sid: str, request: Request):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import mozart
    d = await request.json()
    sc0 = _mozart_du_site(site, sid)
    # Le seul point d'écriture Mozart qui ne vérifiait NI l'existence NI le site. Le
    # middleware ne contrôle que le code de site présent dans le CHEMIN : un compte n'ayant
    # que `mkd` pouvait écrire `PUT /api/sites/mkd/mozart/<id-d-un-scénario-lcr>` et
    # réécrire le graphe d'un autre client. Et un identifiant inconnu faisait un UPDATE à
    # zéro ligne, puis un 500 sur `sc["graphe"]`.
    if not sc0:
        return _introuvable()
    if sc0.get("verrouille"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={
            "error": "scénario verrouillé",
            "detail": "C'est un modèle : on ne le modifie pas, on le duplique. "
                      "Le bouton « Dupliquer » en fait une copie modifiable.",
            "verrouille": True})
    champs, vals = [], []
    if "nom" in d:
        champs.append("nom = %s"); vals.append((d["nom"] or "")[:120])
    if "description" in d:
        champs.append("description = %s"); vals.append(d["description"])
    if "graphe" in d:
        champs.append("graphe = %s::jsonb"); vals.append(json.dumps(d["graphe"]))
    if "suivi_ouverture" in d:
        # Le pixel d'ouverture, scénario par scénario (guide de délivrabilité Maildoso).
        champs.append("suivi_ouverture = %s"); vals.append(bool(d["suivi_ouverture"]))
    if not champs:
        return {"ok": True, "inchange": True}
    champs.append("modifie_le = now()")
    mozart._ecrire(f"UPDATE mozart_scenarios SET {', '.join(champs)} WHERE id = %s",
                   tuple(vals) + (sid,))
    sc = mozart.scenario(sid)
    return {"ok": True, "scenario": sc, "problemes": mozart.verifier(sc["graphe"] or {})}


@app.post("/api/sites/{site}/mozart/{sid}/statut")
async def api_mozart_statut(site: str, sid: str, request: Request):
    """Activer, mettre en pause, archiver.

    L'ACTIVATION contrôle le graphe et refuse s'il est incomplet. Un scénario qui
    s'arrêterait au premier contact faute de message est découvert bien trop tard —
    quand les gens sont déjà dedans.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import mozart
    d = await request.json()
    statut = (d.get("statut") or "").strip()
    if statut not in ("brouillon", "actif", "pause", "archive"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={"error": f"statut inconnu: {statut}"})
    sc = _mozart_du_site(site, sid)
    if not sc:
        return _introuvable()
    if statut == "actif":
        pbs = mozart.verifier(sc["graphe"] or {})
        if pbs:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=400, content={
                "error": "scénario incomplet", "problemes": pbs})
    mozart._ecrire("UPDATE mozart_scenarios SET statut = %s, modifie_le = now() "
                   "WHERE id = %s", (statut, sid))
    return {"ok": True, "statut": statut}


@app.post("/api/sites/{site}/mozart/{sid}/dupliquer")
async def api_mozart_dupliquer(site: str, sid: str, request: Request):
    """Copie un scénario dans un nouveau brouillon. La seule porte de sortie d'un modèle."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import mozart
    role, qui = _qui(request)
    try:
        d = await request.json()
    except Exception:  # noqa: BLE001
        d = {}
    if not _mozart_du_site(site, sid):
        return _introuvable()
    neuf = mozart.dupliquer(sid, d.get("nom"), par=qui)
    return {"ok": True, "scenario": neuf}


@app.post("/api/sites/{site}/mozart/{sid}/verrou")
async def api_mozart_verrou(site: str, sid: str, request: Request):
    """Pose ou retire le cadenas. Marque aussi le scénario comme modèle quand on verrouille.

    Verrouiller ET marquer modèle vont ensemble : un scénario qu'on protège de la
    modification, c'est un point de départ qu'on veut retrouver intact. Les séparer
    obligerait à penser à deux réglages pour une seule intention.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import mozart
    d = await request.json()
    verrou = bool(d.get("verrouille"))
    sc = _mozart_du_site(site, sid)
    if not sc:
        return _introuvable()
    mozart._ecrire("UPDATE mozart_scenarios SET verrouille = %s, est_modele = %s, "
                   "modifie_le = now() WHERE id = %s", (verrou, verrou, sid))
    return {"ok": True, "verrouille": verrou, "est_modele": verrou}


@app.post("/api/sites/{site}/mozart/{sid}/simuler")
def api_mozart_simuler(site: str, sid: str):
    """Ce que le prochain passage ferait — sans écrire ni envoyer quoi que ce soit."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import mozart
    sc = _mozart_du_site(site, sid)
    if not sc:
        return _introuvable()
    return {"inscription": mozart.inscrire(sc, dry_run=True),
            "avancement": mozart.avancer(sc, dry_run=True),
            "problemes": mozart.verifier(sc["graphe"] or {})}


@app.delete("/api/sites/{site}/mozart/{sid}")
def api_mozart_supprimer(site: str, sid: str):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import mozart
    sc = _mozart_du_site(site, sid)
    if not sc:
        return _introuvable()
    if sc["statut"] == "actif":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={
            "error": "mettre le scénario en pause avant de le supprimer — "
                     "des contacts sont peut-être en cours de parcours"})
    if sc.get("verrouille"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={
            "error": "scénario verrouillé — retirer le cadenas avant de le supprimer"})
    mozart._ecrire("DELETE FROM mozart_scenarios WHERE id = %s", (sid,))
    return {"ok": True}


@app.get("/api/sites/{site}/campaigns/messages")
def api_campaign_messages(site: str):
    """Messages sélectionnables pour une campagne, groupés : Templates (newsletters),
    Messages validés, Cold emails (par secteur)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import html_templates_backend as htb
    return htb.campaign_message_options(site)


@app.get("/api/sites/{site}/campaigns/message-preview")
def api_campaign_message_preview(site: str, id: str = ""):
    """HTML d'un message (quelle que soit sa source) pour l'aperçu du wizard."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import html_templates_backend as htb
    msg = htb.resolve_campaign_message(site, id)
    if not msg or not msg.get("html"):
        return {"ok": False, "error": "message introuvable"}
    return {"ok": True, "html": msg["html"], "name": msg.get("name")}


@app.post("/api/sites/{site}/campaigns/plan")
async def api_campaign_plan(site: str, request: Request):
    """Planning de cadence + faisabilité + explication IA. Body: {channel, target_size, start_date}."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import deliverability_agent as da
    from datetime import date as _d
    body = await request.json()
    channel = (body.get("channel") or "").lower()
    target = int(body.get("target_size") or 0)
    try:
        start = _d.fromisoformat(body.get("start_date") or _d.today().isoformat())
    except Exception:
        start = _d.today()
    plan = da.plan_cadence(site, channel, target, start)
    plan["explanation"] = da.explain(plan, channel, target)
    return plan


@app.post("/api/sites/{site}/campaigns/suggest-subject")
async def api_campaign_suggest_subject(site: str, request: Request):
    """Propose un objet d'email accrocheur via DeepSeek à partir du contenu du message.
    Body: {message_id} ou {html}."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import html_templates_backend as htb, sweego_backend as sw
    body = await request.json()
    html = body.get("html")
    if not html and body.get("message_id"):
        msg = htb.resolve_campaign_message(site, body["message_id"])
        html = msg["html"] if msg else ""
    if not html:
        return {"ok": False, "error": "html ou message_id requis"}
    text = sw.html_to_text(html)[:1500]
    try:
        import llm_call
        prompt = (
            "Tu es expert emailing B2B en français. Propose UN SEUL objet d'email court (max 60 "
            "caractères), accrocheur, sans clickbait ni emoji, qui maximise le taux d'ouverture pour "
            "ce contenu. Réponds UNIQUEMENT par l'objet, sans guillemets ni préfixe.\n\n"
            f"Contenu de l'email :\n{text}"
        )
        subject = llm_call.call_llm(prompt, max_tokens=40, temperature=0.7,
                                    module="campaigns", action="suggest_subject", site=site)
        subject = (subject or "").strip().strip('"').splitlines()[0][:80]
        return {"ok": bool(subject), "subject": subject}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


@app.post("/api/sites/{site}/campaigns/preview-lint")
async def api_campaign_preview_lint(site: str, request: Request):
    """Lint HTML (liens cassés, rendu client, spam). Body: {html} ou {message_id}."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import email_lint_backend as elb, html_templates_backend as htb
    body = await request.json()
    html = body.get("html")
    if not html and body.get("message_id"):
        msg = htb.resolve_campaign_message(site, body["message_id"])
        html = msg["html"] if msg else ""
    if not html:
        return {"ok": False, "error": "html ou message_id requis"}
    return elb.run_lint(html)


@app.post("/api/sites/{site}/campaigns")
async def api_campaign_create(site: str, request: Request):
    """Crée + planifie une campagne unifiée. Refuse si cadence infaisable.
    Body: {name, channel, message_id, subject, sectors:[...], regions?:[...], depts?:[...],
    target_size, schedule_start}."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import campaign_engine as ce
    body = await request.json()
    sess = getattr(request.state, "session", None)
    by = (sess or {}).get("username", "ui")
    return ce.create_campaign(
        site, (body.get("name") or "").strip(), (body.get("channel") or "").lower(),
        (body.get("message_id") or "").strip(), (body.get("subject") or "").strip(),
        body.get("sectors") or [], int(body.get("target_size") or 0),
        (body.get("schedule_start") or "").strip(), by=by,
        regions=body.get("regions") or [], depts=body.get("depts") or [],
        engagement=(body.get("engagement") or "").strip() or None,
        segment_id=(body.get("segment_id") or "").strip() or None)


@app.get("/api/sites/{site}/campaigns")
def api_campaigns_list(site: str):
    """Liste les campagnes unifiées du site.

    L'échec est RENDU, pas levé : une exception donnait un 500 dont l'interface ne savait
    rien tirer, et le tableau affichait « la base est occupée » sans que ce soit vrai.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import campaign_engine as ce
    try:
        campagnes = ce.list_campaigns(site)
        # Ce qui est parti ne dit rien de ce que ça a donné : deux campagnes à 100 %
        # d'envoi n'ont rien à voir si l'une ouvre à 35 % et l'autre à 5 %. L'engagement
        # est greffé ici plutôt que réclamé par un second appel de l'interface.
        try:
            import stats_backend as st
            eng = st.engagement_par_campagne(site)
            for c in campagnes:
                c["engagement"] = eng.get(str(c.get("id")))
        except Exception:  # noqa: BLE001 — sans statistiques, la liste reste utilisable
            pass
        return {"campaigns": campagnes}
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503,
                            content={"error": f"campagnes illisibles : {e}"[:250]})


# ── Segments de ciblage réutilisables ─────────────────────────────────────────
@app.get("/api/sites/{site}/segments")
def api_segments_list(site: str):
    """Segments du site, avec le nombre de contacts que chacun vise aujourd'hui."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import segments_backend as sb
    import contacts_pool_backend as pool
    out = []
    for s in sb.list_segments(site):
        try:
            s["count"] = pool.count_for_segment(site, s["rules"])
            s["count_stale"] = False
            sb.save_count(s["id"], s["count"])
        except Exception:
            # Pool verrouillé (scrape ou nettoyage horaire en cours) : on ressert le
            # dernier comptage connu en le signalant, plutôt qu'un tiret sans explication.
            s["count"] = s.get("last_count")
            s["count_stale"] = True
        out.append(s)
    return {"segments": out}


@app.post("/api/sites/{site}/segments/preview")
async def api_segments_preview(site: str, request: Request):
    """Compteur live pendant l'édition : combien de contacts pour CES règles ?
    Déclaré avant /segments/{sid} — sur des chemins de même forme, la 1re route gagne."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import segments_backend as sb
    import contacts_pool_backend as pool
    body = await request.json()
    rules = body.get("rules") or {}
    ok, err = sb.validate_rules(rules)
    if not ok:
        return {"ok": False, "error": err, "summary": sb.describe_rules(rules)}
    try:
        out = {"ok": True, "count": pool.count_for_segment(site, rules),
               "summary": sb.describe_rules(rules)}
        # Pourquoi ce compteur vaut ce qu'il vaut. Un ciblage « a ouvert » renvoie
        # couramment 0 — non par erreur, mais parce qu'un contact qui a ouvert a REÇU, et
        # qu'il est donc en repos 120 jours. Sans cette explication, le zéro passe pour un bug.
        try:
            out["explication"] = pool.expliquer_segment(site, rules)
        except Exception:
            out["explication"] = None
        return out
    except Exception as e:  # noqa: BLE001
        # Verrou DuckDB : la base est en écriture (scrape / nettoyage). Ce n'est pas une
        # erreur de règles — `retryable` dit à l'UI de rester utilisable et de réessayer.
        locked = "lock" in str(e).lower()
        return {"ok": False, "retryable": locked,
                "summary": sb.describe_rules(rules),
                "error": ("Comptage indisponible : la base est en cours d'écriture "
                          "(scrape ou nettoyage). Les règles restent enregistrables.")
                         if locked else f"Comptage impossible : {str(e)[:120]}"}


@app.post("/api/sites/{site}/segments")
async def api_segment_create(site: str, request: Request):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import segments_backend as sb
    body = await request.json()
    sess = getattr(request.state, "session", None)
    return sb.create_segment(site, body.get("name") or "", body.get("rules") or {},
                             description=body.get("description") or "",
                             by=(sess or {}).get("username", "ui"))


@app.get("/api/sites/{site}/segments/{sid}")
def api_segment_detail(site: str, sid: str):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import segments_backend as sb
    import contacts_pool_backend as pool
    seg = sb.get_segment(sid)
    if not seg or seg["site_code"] != site:
        return {"ok": False, "error": "segment introuvable"}
    try:
        seg["count"] = pool.count_for_segment(site, seg["rules"])
    except Exception:
        seg["count"] = None
    return {"ok": True, "segment": seg}


@app.patch("/api/sites/{site}/segments/{sid}")
async def api_segment_update(site: str, sid: str, request: Request):
    """Renomme, réécrit les règles, verrouille ou déverrouille un segment."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import segments_backend as sb
    body = await request.json()
    sess = getattr(request.state, "session", None)
    return sb.update_segment(sid, site, body, by=(sess or {}).get("username", "ui"))


@app.post("/api/sites/{site}/segments/{sid}/duplicate")
def api_segment_duplicate(site: str, sid: str, request: Request):
    """Copie un segment sous un NOUVEL identifiant, déverrouillée.

    Le chemin porte un segment de plus que `/segments/{sid}` : aucune ambiguïté de route.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import segments_backend as sb
    sess = getattr(request.state, "session", None)
    return sb.duplicate_segment(sid, site, by=(sess or {}).get("username", "ui"))


@app.delete("/api/sites/{site}/segments/{sid}")
def api_segment_delete(site: str, sid: str):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import segments_backend as sb
    return sb.delete_segment(sid, site)


# Déclaré APRÈS /campaigns/messages et /campaigns/message-preview : sur des chemins de
# même forme, FastAPI retient la 1re route déclarée — l'ordre garde ces deux-là gagnantes.
@app.get("/api/sites/{site}/campaigns/{cid}")
def api_campaign_detail(site: str, cid: str):
    """Détail complet d'une campagne (fiche de contrôle/édition) : paramétrage, cadence,
    message rendu et nombre de contacts encore éligibles pour son ciblage."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import campaign_engine as ce
    import html_templates_backend as htb
    import contacts_pool_backend as pool
    camp = ce.get_campaign(cid)
    if not camp or camp.get("site_code") != site:
        return {"ok": False, "error": "campagne introuvable"}
    msg = htb.resolve_campaign_message(site, camp.get("message_id") or "") or {}
    p = camp.get("params") or {}
    try:
        available = sum(
            pool.count_available_for_sector(site, sec, regions=p.get("regions") or [],
                                            depts=p.get("depts") or [],
                                            engagement=p.get("engagement"))
            for sec in (camp.get("sectors") or [])
        )
    except Exception:
        available = None
    try:
        envois = ce.journal_envois(site, cid)
    except Exception:  # noqa: BLE001
        envois = []
    return {"ok": True, "campaign": camp, "available": available,
            "message_html": msg.get("html") or "", "message_name": msg.get("name") or "",
            "envois": envois}


@app.patch("/api/sites/{site}/campaigns/{cid}")
async def api_campaign_update(site: str, cid: str, request: Request):
    """Modifie une campagne : nom, objet, message, ciblage, volume, date de lancement."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import campaign_engine as ce
    body = await request.json()
    sess = getattr(request.state, "session", None)
    by = (sess or {}).get("username", "ui")
    return ce.update_campaign(site, cid, body, by=by)


def _send_bat(site: str, channel: str, message_id: str, subject: str, email: str,
              utm_campaign: str | None = None) -> dict:
    """BAT unifié : envoie le message à UNE adresse de test **par le canal qui fera
    l'envoi final**. Un BAT routé vers un autre canal ne prouve rien — ni l'expéditeur,
    ni la substitution des variables, ni le rendu, ni la délivrabilité.

    Chaque branche emprunte donc exactement la fonction utilisée par le dispatch
    (`campaign_engine._send_batch`), avec un contact fictif mappé comme un vrai
    contact du pool. Les défauts éventuels du template apparaissent donc dans le BAT :
    c'est le but.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import html_templates_backend as htb
    channel = (channel or "").lower()
    if not message_id or not subject or not email or "@" not in email:
        return {"ok": False, "error": "message, objet et email requis"}
    msg = htb.resolve_campaign_message(site, message_id)
    if not msg or not msg.get("html"):
        return {"ok": False, "error": "message introuvable"}

    utm = utm_campaign or f"{site}-bat"
    campaign_id = f"{site}-bat"
    # Contact fictif, mappé par chaque canal comme il mappe un contact du pool.
    sample = {"email": email, "prenom": "Camille", "nom": "Afchain",
              "societe": "Le Client ROI", "city": "Paris"}
    try:
        if channel == "maildoso":
            # Même appel que le dispatch : tag UTM + réécriture des liens + pixel.
            import maildoso_backend as md
            r = md.send_batch(campaign_id, subject, msg["html"], [sample],
                              site=site, utm_campaign=utm)
            if r.get("sent"):
                return {"ok": True, "note": f"BAT Maildoso envoyé à {email} (SMTP, boîte en rotation)"}
            err = (r.get("errors") or [{}])[0].get("error") or r.get("note") or "échec envoi Maildoso"
            return {"ok": False, "error": err}

        if channel == "emelia":
            # Emelia n'a pas d'envoi de test : le dispatch crée une campagne, pose le
            # HTML tagué en step unique, la démarre puis ajoute les contacts. Le BAT
            # fait pareil avec un seul contact — même expéditeur, mêmes variables.
            import emelia_campaign_manager as ecm
            html = msg["html"]
            try:
                from utm_tagging import tag_links
                html = tag_links(html, "coldemail", "email", utm)
            except Exception:
                pass
            contact = {"email": email, "firstName": sample["prenom"],
                       "lastName": sample["nom"], "field1": sample["societe"]}
            return ecm.send_test_email(html, subject, email, contact=contact,
                                       label=f"BAT {site.upper()}")

        # Sweego (masse) : même appel que le dispatch.
        import sweego_backend as sw
        r = sw.send_campaign(campaign_id, subject, msg["html"], [email], dry_run=False,
                             utm_campaign=utm, utm_source="sweego")
        if isinstance(r, dict):
            if r.get("ok"):
                return {**r, "note": f"BAT Sweego envoyé à {email}"}
            return r
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


@app.post("/api/sites/{site}/campaigns/bat")
async def api_campaign_bat(site: str, request: Request):
    """BAT avant création : envoie le message de test via le canal choisi.
    Body: {channel, message_id, subject, email}."""
    body = await request.json()
    return _send_bat(site, (body.get("channel") or "").lower(),
                     (body.get("message_id") or "").strip(),
                     (body.get("subject") or "").strip(),
                     (body.get("email") or "").strip())


@app.post("/api/sites/{site}/campaigns/{cid}/bat")
async def api_campaign_unified_bat(site: str, cid: str, request: Request):
    """BAT d'une campagne existante : envoie son message à une adresse de test, via son canal."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import campaign_engine as ce
    body = await request.json()
    email = (body.get("email") or "").strip()
    camp = ce.get_campaign(cid)
    if not camp:
        return {"ok": False, "error": "campagne introuvable"}
    return _send_bat(site, camp.get("channel"), camp["message_id"], camp["subject"], email,
                     utm_campaign=(camp.get("params") or {}).get("utm_campaign"))


@app.post("/api/sites/{site}/campaigns/{cid}/{action}")
async def api_campaign_action(site: str, cid: str, action: str):
    """Actions sur une campagne : pause | resume | cancel | send-now."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import campaign_engine as ce
    from datetime import date as _d
    camp = ce.get_campaign(cid)
    if not camp or camp["site_code"] != site:
        return {"ok": False, "error": "campagne introuvable"}
    if action == "pause":
        ce.set_status(cid, "paused"); return {"ok": True, "status": "paused"}
    if action == "resume":
        ce.set_status(cid, "running" if (camp["sent_count"] or 0) > 0 else "scheduled")
        return {"ok": True, "status": "resumed"}
    if action == "cancel":
        ce.set_status(cid, "cancelled"); return {"ok": True, "status": "cancelled"}
    if action == "send-now":
        # Envoi manuel lancé en tâche de fond : un lot maildoso s'étale sur des heures
        # (pause de 15-60 s entre emails) et gelait l'event loop — donc toute l'API —
        # tant qu'il tournait dans la requête. La vérification des crédits d'envoi part
        # avec lui. L'avancement se suit sur `sent_count`, persisté au fil de l'eau.
        return ce.dispatch_in_background(cid, _d.today())
    return {"ok": False, "error": f"action inconnue: {action}"}


# ── Prise de RDV publique (type Calendly/TidyCal) ───────────────────────────────
def _booking_site_ok(site: str) -> bool:
    return site in _known_site_codes()


@app.get("/api/book/{site}", response_class=HTMLResponse)
def book_page(site: str):
    """Page publique de prise de RDV (HTML autonome). Lien partageable."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    if not _booking_site_ok(site):
        return HTMLResponse("<h1>Site introuvable</h1>", status_code=404)
    import booking_backend as bb, booking_page as bp
    cfg = bb.get_settings(site)
    return HTMLResponse(bp.render_page(site, cfg))


@app.get("/api/book/{site}/config")
def book_config(site: str):
    """Motifs + jours réservables + meta (consommé par la page publique)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    if not _booking_site_ok(site):
        return {"reasons": [], "days": [], "error": "site introuvable"}
    import booking_backend as bb
    cfg = bb.get_settings(site)
    return {"reasons": cfg.get("reasons", []), "days": bb.available_days(site, cfg),
            "slot_minutes": cfg.get("slot_minutes"), "brand_color": cfg.get("brand_color"),
            "label": cfg.get("from_name"), "logo_url": cfg.get("logo_url"),
            "website_url": cfg.get("website_url"), "description": cfg.get("description")}


@app.get("/api/book/{site}/slots")
def book_slots(site: str, date: str):
    """Créneaux libres pour un jour donné (YYYY-MM-DD)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    if not _booking_site_ok(site):
        return {"slots": [], "error": "site introuvable"}
    import booking_backend as bb
    return {"slots": bb.available_slots(site, date)}


@app.post("/api/book/{site}/submit")
async def book_submit(site: str, request: Request):
    """Crée le RDV (valide motif + créneau) puis envoie email + SMS de confirmation."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    if not _booking_site_ok(site):
        return {"ok": False, "error": "site introuvable"}
    import booking_backend as bb
    body = await request.json()
    res = bb.create_booking(
        site, body.get("reason", ""), body.get("slot_start", ""),
        body.get("name", ""), body.get("email", ""), body.get("phone", ""), body.get("message", ""),
    )
    if not res.get("ok"):
        return res
    notif = bb.send_confirmations(res["booking"], res["config"])
    return {"ok": True, "id": res["booking"]["id"], "notif": notif}


# ── Back-office RDV (authentifié, isolé par site via middleware) ────────────────
@app.get("/api/sites/{site}/booking/settings")
def booking_settings_get(site: str):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import booking_backend as bb
    return bb.get_settings(site)


@app.put("/api/sites/{site}/booking/settings")
async def booking_settings_put(site: str, request: Request):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import booking_backend as bb
    patch = await request.json()
    return bb.update_settings(site, patch)


@app.get("/api/sites/{site}/booking/list")
def booking_list(site: str, limit: int = 25, offset: int = 0,
                 scope: str = "", search: str = ""):
    """RDV paginés. `scope` : active | archived | vide (tous). `search` : email."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import booking_backend as bb
    r = bb.list_bookings(site, limit=limit, offset=offset, scope=scope, search=search)
    # `bookings` conservé sous ce nom (clé historique lue par l'UI) + méta de pagination
    return {"bookings": r["items"], "total": r["total"], "limit": r["limit"],
            "offset": r["offset"], "counts": r["counts"]}


@app.get("/api/sites/{site}/booking/unread-count")
def booking_unread(site: str):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import booking_backend as bb
    return {"count": bb.unread_count(site)}


@app.post("/api/sites/{site}/booking/{bid}/status")
async def booking_set_status(site: str, bid: str, request: Request):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import booking_backend as bb
    body = await request.json()
    return bb.set_status(site, bid, body.get("status", "answered"))


@app.get("/api/sites/{site}/cleanup/counts")
def api_cleanup_counts(site: str):
    """Compteurs du POOL global (contacts.duckdb) : jamais vérifiés + vérifiés > 6 mois."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import cleanup_backend as cb
    return {
        "unverified": cb.count_unverified(),
        "stale": cb.count_stale(days=180),
        "stale_days": 180,
    }


@app.get("/api/sites/{site}/cleanup/history")
def api_cleanup_history(site: str, limit: int = 50):
    """Historique dédié des cycles de nettoyage : ne renvoie QUE les events cleanup_batch.
    Évite que les events cleanup_validated/cleanup_removed (très nombreux) ne poussent
    les batches hors de la fenêtre quand on regarde /logs?limit=N."""
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import god_mode_backend as gm
    try:
        rows = gm.list_logs(site, limit=min(limit, 200), action="cleanup_batch")
    except TypeError:
        # backward-compat si list_logs n'a pas encore le param action
        rows = [l for l in gm.list_logs(site, limit=1000) if l.get("action") == "cleanup_batch"][:limit]
    return {"logs": rows, "count": len(rows)}


@app.get("/api/sites/{site}/cleanup/contacts")
def api_cleanup_list(site: str, limit: int = 500):
    """Liste paginée du POOL pour la page Cleanup (table)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import cleanup_backend as cb
    return {"contacts": cb.list_pool(limit=limit)}


# État des nettoyages en cours (clé site:mode → dict progress) — évite les doubles lancements.
# Strictement séquentiel : un seul cycle ACTIF à la fois TOUS sites confondus.
import threading as _th
_active_cleanups: dict[str, dict] = {}
_cleanup_lock = _th.Lock()  # protège les writes sur _active_cleanups


def _is_any_cleanup_active() -> bool:
    """Vrai si AU MOINS un nettoyage tourne (séquentiel global)."""
    with _cleanup_lock:
        return len(_active_cleanups) > 0


def _set_cleanup_progress(key: str, **patch):
    """Merge patch dans l'état progress de ce cycle."""
    with _cleanup_lock:
        cur = _active_cleanups.get(key, {})
        cur.update(patch)
        _active_cleanups[key] = cur


def _launch_cleanup(site: str, mode: str, drain: bool = False, chunk_size: int = 100,
                    total_limit=None, source: str = "manual") -> dict:
    """Lance un cycle de nettoyage en ARRIÈRE-PLAN (thread daemon). Retourne immédiatement.
    SÉQUENTIEL STRICT : refuse si UN nettoyage est déjà en cours (tous sites/modes).
    Réutilisable : appelé par l'endpoint /cleanup/run (source='manual') ET par le hook de
    fin de scrape (source='auto-scrape'). `source` est tracé dans les logs cleanup_batch."""
    if site not in ("lcr", "mkd"):
        return {"ok": False, "error": "invalid site"}
    if mode not in ("unverified", "stale"):
        return {"ok": False, "error": "mode requis (unverified | stale)"}
    key = f"{site}:{mode}"

    # Verrou strict séquentiel : un seul cycle GLOBAL à la fois.
    with _cleanup_lock:
        if _active_cleanups:
            running_key = next(iter(_active_cleanups))
            return {
                "ok": False,
                "running": True,
                "error": f"Un nettoyage est déjà en cours ({running_key}). Mode séquentiel.",
                "active_key": running_key,
                "active": _active_cleanups[running_key],
            }
        # Pré-réservation : insertion atomique de l'état initial
        import time as _tm
        _active_cleanups[key] = {
            "site": site, "mode": mode, "source": source,
            "drain": drain, "chunk_size": chunk_size, "total_limit": total_limit,
            "processed": 0, "total": chunk_size,
            "valid": 0, "removed": 0, "skipped": 0, "errors": 0,
            "last_email": None,
            "started_at": _tm.time(),
            "status": "starting",
            "stop_requested": False,
            "cumulative": {"chunks_done": 0, "total": 0, "valid": 0, "removed": 0,
                           "skipped": 0, "errors": 0, "drained": False, "stopped": False},
        }

    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import cleanup_backend as cb

    def _should_stop() -> bool:
        st = _active_cleanups.get(key)
        return bool(st and st.get("stop_requested"))

    def _on_progress_single(stats, processed, email):
        _set_cleanup_progress(
            key, total=stats.get("total", chunk_size), processed=processed,
            valid=stats.get("valid", 0), removed=stats.get("removed", 0),
            skipped=stats.get("skipped", 0), errors=stats.get("errors", 0),
            last_email=email,
            status="running" if processed < stats.get("total", chunk_size) else "finishing",
        )

    def _on_progress_drain(cum, chunk_stats, chunk_processed, email):
        _set_cleanup_progress(
            key, total=chunk_stats.get("total", chunk_size), processed=chunk_processed,
            valid=chunk_stats.get("valid", 0), removed=chunk_stats.get("removed", 0),
            skipped=chunk_stats.get("skipped", 0), errors=chunk_stats.get("errors", 0),
            last_email=email, status="running", cumulative=dict(cum),
        )

    def _runner():
        try:
            if drain:
                cb.run_cleanup_drain(
                    mode=mode, site=site, chunk_size=chunk_size, total_limit=total_limit,
                    progress_cb=_on_progress_drain, should_stop=_should_stop, source=source,
                )
            else:
                cb.run_cleanup(
                    mode=mode, site=site, limit=chunk_size,
                    progress_cb=_on_progress_single, should_stop=_should_stop, source=source,
                )
        except Exception as e:
            print(f"  [cleanup_run] err: {e}")
        finally:
            with _cleanup_lock:
                _active_cleanups.pop(key, None)

    _th.Thread(target=_runner, daemon=True).start()
    return {
        "ok": True, "queued": True, "mode": mode, "drain": drain, "source": source,
        "chunk_size": chunk_size, "total_limit": total_limit, "key": key,
    }


@app.post("/api/sites/{site}/cleanup/run")
async def api_cleanup_run(site: str, request: Request):
    """Lance un cycle en ARRIÈRE-PLAN (thread daemon). Retourne immédiatement.
    SÉQUENTIEL STRICT : refuse si UN nettoyage est en cours (tous sites/modes confondus).

    Body :
      - mode: 'unverified' | 'stale' (requis)
      - drain: bool (default False) — si True, enchaîne des chunks jusqu'à épuisement
      - chunk_size: int (default 100) — taille d'un chunk (en mode drain comme single)
      - total_limit: int|null (default null) — en drain, plafond cumulé (null = drain complet)
      - limit: int — backward-compat ; en mode single = chunk_size, en mode drain ignoré
    """
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    body = await request.json()
    mode = (body.get("mode") or "").strip()
    drain = bool(body.get("drain", False))
    chunk_size = int(body.get("chunk_size") or body.get("limit") or 100)
    raw_total = body.get("total_limit")
    total_limit = int(raw_total) if raw_total else None
    return _launch_cleanup(site, mode, drain=drain, chunk_size=chunk_size,
                           total_limit=total_limit, source="manual")


@app.post("/api/sites/{site}/cleanup/stop")
def api_cleanup_stop(site: str):
    """Demande l'arrêt PROPRE du cycle en cours pour ce site.
    Le thread vérifie le flag entre chaque contact et entre chaque chunk."""
    with _cleanup_lock:
        for k in list(_active_cleanups.keys()):
            if k.startswith(site + ":"):
                _active_cleanups[k]["stop_requested"] = True
                _active_cleanups[k]["status"] = "stopping"
                return {"ok": True, "key": k, "stopping": True}
    return {"ok": False, "error": "Aucun cycle en cours pour ce site"}


# ── Autoscrape continu d'un département (cf. scripts/autoscrape_backend.py) ────
# Tourne en PROCESS DÉTACHÉ (pas un thread de l'API) : isole DuckDB (pas de conflit
# de connexions avec les requêtes), survit aux redémarrages de l'API, statut dans
# un fichier (memory/autoscrape/<site>-status.json). Stop via flag fichier.

@app.post("/api/sites/{site}/autoscrape/start")
async def api_autoscrape_start(site: str, request: Request):
    """Lance un autoscrape (dept + secteur(s)) en process détaché. Réservé admin."""
    sess = getattr(request.state, "session", None)
    if not sess or sess.get("role") not in ("admin", "superadmin"):
        return {"ok": False, "error": "Rôle admin requis."}
    if site not in ("lcr", "mkd"):
        return {"ok": False, "error": "invalid site"}
    body = await request.json()
    sectors = body.get("sectors") or ([body["sector"]] if body.get("sector") else [])
    sectors = [s.strip() for s in sectors if s and s.strip()]
    region = (body.get("region") or "").strip()
    dept = (body.get("dept") or "").strip()
    _tc = body.get("target_contacts")
    target_contacts = int(_tc) if _tc is not None else 0   # 0 = illimité (scrape tout)
    target_contacts = max(0, min(target_contacts, 100000))
    # Demande user 2026-06-16 : on choisit juste secteur(s) + RÉGION, et ça scrape en
    # continu tous les départements. `dept` reste accepté en legacy (mode mono-dept).
    all_regions = bool(body.get("all_regions"))
    if not sectors or not (region or dept or all_regions):
        return {"ok": False, "error": "secteur(s) et région (ou 'all_regions': true) requis"}

    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import autoscrape_backend as asb
    import time as _tm

    cur = asb.read_status(site)
    if cur.get("status") in ("running", "starting", "stopping", "cleaning") and (_tm.time() - cur.get("updated_at", 0) < 300):
        return {"ok": False, "running": True, "error": "Un autoscrape est déjà en cours.", "active": cur}

    region_name = "Toutes les régions" if all_regions else ""
    if region and not all_regions:
        try:
            region_name = asb._region_name(region)
        except Exception:
            region_name = region

    # Hors fenêtre nocturne : on ne lance pas, on PROGRAMME. Le scrape verrouillerait
    # contacts.duckdb et couperait les compteurs de l'interface toute la journée.
    in_window, why = asb.within_scrape_window()
    if not in_window:
        req = {"site": site, "sectors": sectors, "region": region or None,
               "dept": dept or None, "all_regions": all_regions,
               "target_contacts": target_contacts,
               "region_name": region_name or None}
        asb.write_pending(site, req)
        scope_txt = ("Toutes les régions" if all_regions
                     else (f"Région {region_name}" if region else f"Dept {dept}"))
        asb.write_status(site, {
            "site": site, "region": region or None, "region_name": region_name or None,
            "all_regions": all_regions, "dept": dept or None, "sectors": sectors,
            "status": "scheduled", "scope": scope_txt,
            "depts_total": 0, "depts_done": 0, "cities_total": 0, "cities_done": 0,
            "current_city": None, "examined": 0, "valid": 0, "rejected": 0, "errors": 0,
            "kept_total": 0, "valid_serper": 0, "valid_basile": 0,
            "target_contacts": target_contacts, "serper_available": None,
            "basile_active": True, "blocked": False, "stopped": False,
            "started_at": None, "message": f"{asb.PENDING_NOTE} · {why}",
        })
        return {"ok": True, "scheduled": True, "site": site,
                "starts_at": asb.SCRAPE_START, "reason": why,
                "message": f"{asb.PENDING_NOTE}. La journée reste libre pour travailler.",
                "sectors": sectors, "region": region or None, "dept": dept or None,
                "target_contacts": target_contacts}

    # Dans la fenêtre : lancement immédiat. Une demande en attente devient caduque.
    asb.clear_pending(site)
    scope = "Toutes les régions (France métropole)" if all_regions else (f"Région {region_name}" if region else f"Dept {dept}")
    asb.write_status(site, {
        "site": site, "region": region or None, "region_name": region_name or None,
        "all_regions": all_regions,
        "dept": dept or None, "sectors": sectors, "status": "starting",
        "scope": scope,
        "depts_total": 0, "depts_done": 0, "cities_total": 0, "cities_done": 0, "current_city": None,
        "examined": 0, "valid": 0, "rejected": 0, "errors": 0, "kept_total": 0,
        "valid_serper": 0, "valid_basile": 0, "target_contacts": target_contacts,
        "serper_available": None, "basile_active": True, "blocked": False, "stopped": False,
        "started_at": _tm.time(), "message": None,
    })
    try:
        if asb.stop_path(site).exists():
            asb.stop_path(site).unlink()
    except Exception:
        pass

    cmd = ["python3", "scripts/autoscrape_backend.py", "--site", site,
           "--sectors", ",".join(sectors), "--target-contacts", str(target_contacts)]
    if all_regions:
        cmd += ["--all-regions"]
    elif region:
        cmd += ["--region", region]
    elif dept:
        cmd += ["--dept", dept]
    log_f = open(str(BASE_DIR / "logs" / f"autoscrape-{site}.log"), "w")
    try:
        subprocess.Popen(cmd, cwd=str(BASE_DIR), start_new_session=True,
                         stdout=log_f, stderr=subprocess.STDOUT)
    finally:
        log_f.close()
    return {"ok": True, "started": True, "site": site, "all_regions": all_regions,
            "region": region or None, "region_name": region_name or None,
            "dept": dept or None, "sectors": sectors, "target_contacts": target_contacts}


@app.get("/api/scrape/active")
def api_scrape_active():
    """Scrapings en cours, tous sites confondus — pour la barre superadmin.

    La barre est globale : elle ne peut pas interroger une route par site sans savoir
    lesquels existent. Un run sans battement de cœur depuis 5 min est déclaré interrompu,
    comme le fait déjà la route par site — sinon un process tué net s'afficherait
    indéfiniment comme « en cours ».
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import autoscrape_backend as asb
    import time as _tm
    items = []
    for site in ("lcr", "mkd"):
        try:
            st = asb.read_status(site)
        except Exception:
            continue
        statut = st.get("status")
        if statut not in ("running", "starting", "stopping", "cleaning"):
            continue
        mort = (_tm.time() - st.get("updated_at", 0)) > 300
        items.append({
            "site": site,
            "status": "interrupted" if mort else statut,
            "region_name": st.get("region_name") or "",
            "current_dept": st.get("current_dept") or "",
            "current_city": st.get("current_city") or "",
            "valid": st.get("valid") or 0,
            "target": st.get("target_contacts") or 0,
            # Les mêmes compteurs que le tableau « Collectes en cours » de la page
            # Scraping : la barre et la page lisent la même source, elles doivent afficher
            # les mêmes chiffres. Deux écrans qui décrivent le même run avec des nombres
            # différents, c'est un écran de trop.
            "valid_basile": st.get("valid_basile") or 0,
            "valid_serper": st.get("valid_serper") or 0,
            "examined": st.get("examined") or 0,
            "duplicates": st.get("duplicates") or 0,
            "rejected": st.get("rejected") or 0,
            "cities_done": st.get("cities_done") or 0,
            "cities_total": st.get("cities_total") or 0,
            "sectors": st.get("sectors") or [],
            "updated_at": st.get("updated_at") or 0,
        })
    return {"count": len(items), "items": items}


@app.get("/api/sites/{site}/autoscrape/orchestrateur")
def api_autoscrape_orchestrateur(site: str):
    """L'état du mode AUTOMATIQUE : quota du jour, cible en cours, créneaux réservés.

    À ne pas confondre avec `/autoscrape/status`, qui décrit le run en train de tourner —
    celui-ci décrit l'orchestrateur qui décide QUOI lancer et QUAND. L'écran a besoin des
    deux : l'un dit « ça tourne », l'autre dit « voilà pourquoi, et ce qui vient après ».
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    try:
        import autoscrape_daily as ad
        return ad.status()
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/sites/{site}/scrape/conseil")
def api_scrape_conseil(site: str, combien: int = 10):
    """Les prochaines cibles selon Stéphane — note explicable, pas un oracle.

    Chaque point vient d'un chiffre de la base : rang du secteur, performance mesurée du
    couple secteur × zone (clic d'abord), terrain jamais collecté, rareté en base. Le
    conseil ne lance rien.
    """
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import stephane
    try:
        return stephane.conseiller(site, combien)
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/sites/{site}/stephane/memoire")
def api_stephane_memoire(site: str, limite: int = 20):
    """Ce que Stéphane a retenu : les couples secteur × zone qui répondent, et les autres."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import stephane
    try:
        return stephane.memoire(site, limite)
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/sites/{site}/stephane/config")
def api_stephane_config(site: str):
    """Le cadre posé à Stéphane : secteurs autorisés, départements, ce qui doit primer."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import stephane
    try:
        return stephane.config(site)
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.post("/api/sites/{site}/stephane/config")
async def api_stephane_config_set(site: str, request: Request):
    """Change le cadre. Réservé aux administrateurs : il pilote la dépense Serper."""
    sess = getattr(request.state, "session", None) or {}
    if sess.get("role") not in ("admin", "superadmin"):
        return {"ok": False, "error": "rôle admin requis"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import stephane
    body = await request.json()
    try:
        return stephane.enregistrer_config(
            site, body.get("secteurs") or [], body.get("depts") or [],
            body.get("priorite") or "equilibre", par=sess.get("username") or "")
    except Exception as e:  # noqa: BLE001
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


@app.get("/api/sites/{site}/autoscrape/status")
def api_autoscrape_status(site: str):
    """État de l'autoscrape (lu depuis le fichier de statut). Marque 'interrupted'
    si 'running' sans heartbeat depuis > 5 min (process mort)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import autoscrape_backend as asb
    import time as _tm
    st = asb.read_status(site)
    if st.get("status") in ("running", "starting", "stopping", "cleaning") and (_tm.time() - st.get("updated_at", 0) > 300):
        st = dict(st)
        st["status"] = "interrupted"
        st["message"] = "Process interrompu (plus de heartbeat depuis > 5 min)."
    # La fenêtre et le plafond viennent du SERVEUR : l'interface les écrivait en dur
    # (« 22h à 8h »), et continuait donc de les annoncer après leur levée.
    st = dict(st)
    fen = asb._fenetre()
    autorise, motif = asb.within_scrape_window()
    plafond_atteint, phrase = asb.quota_atteint(site)
    st["fenetre"] = {"continu": fen is None,
                     "debut": fen[0] if fen else None,
                     "fin": fen[1] if fen else None,
                     "autorise_maintenant": autorise,
                     "motif": motif}
    st["quota"] = {"plafond": asb.quota_jour(), "atteint": plafond_atteint, "phrase": phrase}
    return st


@app.post("/api/sites/{site}/autoscrape/resume")
async def api_autoscrape_resume(site: str, request: Request):
    """Relance un autoscrape arrêté là où il s'était arrêté (progression persistée :
    dépts finis sautés, villes finies du dept en cours sautées, reliquat de cible).
    Réservé admin, refuse si un run est déjà actif."""
    sess = getattr(request.state, "session", None)
    if not sess or sess.get("role") not in ("admin", "superadmin"):
        return {"ok": False, "error": "Rôle admin requis."}
    if site not in ("lcr", "mkd"):
        return {"ok": False, "error": "invalid site"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import autoscrape_backend as asb
    import time as _tm

    cur = asb.read_status(site)
    if cur.get("status") in ("running", "starting", "stopping", "cleaning") and (_tm.time() - cur.get("updated_at", 0) < 300):
        return {"ok": False, "running": True, "error": "Un autoscrape est déjà en cours.", "active": cur}

    # Validation AVANT de spawner : progression exploitable ?
    prog = asb.read_progress(site)
    if not prog:
        return {"ok": False, "error": "Aucune progression enregistrée — rien à reprendre."}
    if prog.get("status") not in asb.RESUMABLE_STATUSES:
        return {"ok": False, "error": f"Statut « {prog.get('status')} » — rien à reprendre."}
    region = prog.get("region")
    dept = prog.get("dept") or (None if region else prog.get("cities_dept"))
    if not region and not dept:
        return {"ok": False, "error": "Progression illisible (ni région ni département)."}

    scope = f"Région {prog.get('region_name') or region}" if region else f"Dept {dept}"
    asb.write_status(site, {
        "site": site, "region": region, "region_name": prog.get("region_name"),
        "dept": dept, "sectors": prog.get("sectors") or [], "status": "starting",
        "scope": f"{scope} (reprise)",
        "depts_total": prog.get("depts_total") or 0, "depts_done": len(prog.get("depts_done") or []),
        "cities_total": 0, "cities_done": 0, "current_city": None,
        "examined": 0, "valid": int(prog.get("valid") or 0), "rejected": 0, "errors": 0,
        "kept_total": 0, "valid_serper": 0, "valid_basile": 0,
        "target_contacts": int(prog.get("target_contacts") or 0),
        "serper_available": None, "basile_active": True, "blocked": False, "stopped": False,
        "started_at": _tm.time(), "message": "Reprise du run arrêté…",
    })
    log_f = open(str(BASE_DIR / "logs" / f"autoscrape-{site}.log"), "a")
    try:
        subprocess.Popen(["python3", "scripts/autoscrape_backend.py", "--site", site, "--resume"],
                         cwd=str(BASE_DIR), start_new_session=True,
                         stdout=log_f, stderr=subprocess.STDOUT)
    finally:
        log_f.close()
    return {"ok": True, "resumed": True, "site": site, "region": region, "dept": dept,
            "depts_done": len(prog.get("depts_done") or []),
            "valid_baseline": int(prog.get("valid") or 0),
            "target_contacts": int(prog.get("target_contacts") or 0)}


@app.post("/api/sites/{site}/autoscrape/stop")
def api_autoscrape_stop(site: str):
    """Demande l'arrêt propre : pose un flag fichier que le process détaché vérifie."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import autoscrape_backend as asb
    try:
        asb.stop_path(site).parent.mkdir(parents=True, exist_ok=True)
        asb.stop_path(site).write_text("stop")
        return {"ok": True, "stopping": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Campagnes cold-email AUTOMATISÉES (cf. scripts/auto_campaign_runner.py) ─────
def _ac_admin(request: Request):
    sess = getattr(request.state, "session", None)
    if not sess or sess.get("role") not in ("admin", "superadmin"):
        return None
    return sess


@app.post("/api/sites/{site}/auto-campaigns")
async def api_auto_campaign_create(site: str, request: Request):
    if not _ac_admin(request):
        return {"ok": False, "error": "Rôle admin requis."}
    if site not in ("lcr", "mkd"):
        return {"ok": False, "error": "invalid site"}
    body = await request.json()
    name = (body.get("name") or "").strip()
    sectors = [s for s in (body.get("sectors") or []) if s] or ([body["sector"]] if body.get("sector") else [])
    sender = (body.get("sender_email") or "").strip()
    source_mode = body.get("source_mode") or "pool"
    dept = (body.get("dept") or "").strip() or None
    daily_target = int(body.get("daily_target") or 30)
    if not name or not sectors or not sender:
        return {"ok": False, "error": "name, secteur(s) et expéditeur requis"}
    if source_mode == "autoscrape" and not dept:
        return {"ok": False, "error": "département requis en mode autoscrape"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import auto_campaign_backend as ab
    import workflow_emelia_push as wep
    try:
        emelia_cid = wep.ensure_campaign_for_auto(site, sectors[0])
    except Exception as e:
        return {"ok": False, "error": f"Création campagne Emelia: {e}"}
    sess = getattr(request.state, "session", None)
    cid = ab.create_auto_campaign(site, name, sectors, sender, source_mode=source_mode, dept=dept,
                                  daily_target=daily_target, emelia_campaign_id=emelia_cid,
                                  created_by=(sess.get("username") if sess else "system"))
    return {"ok": True, "id": cid, "emelia_campaign_id": emelia_cid, "campaign": ab.get_auto_campaign(cid)}


@app.get("/api/sites/{site}/auto-campaigns")
def api_auto_campaigns_list(site: str):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import auto_campaign_backend as ab
    return {"campaigns": ab.list_auto_campaigns(site)}


@app.get("/api/sites/{site}/auto-campaigns/status")
def api_auto_campaigns_status(site: str):
    """État du dernier/courant run d'auto-campagnes (fichier). 'interrupted' si stale >5min."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import auto_campaign_runner as r
    import time as _tm
    st = r.read_status(site)
    if st.get("status") == "running" and (_tm.time() - st.get("updated_at", 0) > 300):
        st = dict(st); st["status"] = "interrupted"
    return st


@app.get("/api/sites/{site}/auto-campaigns/{camp_id}")
def api_auto_campaign_get(site: str, camp_id: str):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import auto_campaign_backend as ab
    camp = ab.get_auto_campaign(camp_id)
    if not camp:
        return {"ok": False, "error": "not found"}
    camp["runs"] = ab.runs_for_campaign(camp_id, limit=30)
    return {"ok": True, "campaign": camp}


@app.patch("/api/sites/{site}/auto-campaigns/{camp_id}")
async def api_auto_campaign_update(site: str, camp_id: str, request: Request):
    if not _ac_admin(request):
        return {"ok": False, "error": "Rôle admin requis."}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import auto_campaign_backend as ab
    import auto_campaign_runner as r
    import time as _tm
    st = r.read_status(site)
    if st.get("status") == "running" and (_tm.time() - st.get("updated_at", 0) < 300):
        return {"ok": False, "running": True,
                "error": "Un run est en cours — mets la campagne en pause avant d'éditer."}
    body = await request.json()
    fields = {k: body[k] for k in ("name", "sectors", "source_mode", "dept", "sender_email",
                                    "daily_target", "message_mode") if k in body}
    ab.update_auto_campaign(camp_id, **fields)
    return {"ok": True, "campaign": ab.get_auto_campaign(camp_id)}


@app.post("/api/sites/{site}/auto-campaigns/{camp_id}/pause")
def api_auto_campaign_pause(site: str, camp_id: str, request: Request):
    if not _ac_admin(request):
        return {"ok": False, "error": "Rôle admin requis."}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import auto_campaign_backend as ab
    import auto_campaign_runner as r
    try:
        r.pause_path(camp_id).parent.mkdir(parents=True, exist_ok=True)
        r.pause_path(camp_id).write_text("pause")
    except Exception:
        pass
    ab.set_status(camp_id, "paused")
    return {"ok": True, "status": "paused"}


@app.post("/api/sites/{site}/auto-campaigns/{camp_id}/resume")
def api_auto_campaign_resume(site: str, camp_id: str, request: Request):
    if not _ac_admin(request):
        return {"ok": False, "error": "Rôle admin requis."}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import auto_campaign_backend as ab
    import auto_campaign_runner as r
    try:
        if r.pause_path(camp_id).exists():
            r.pause_path(camp_id).unlink()
    except Exception:
        pass
    ab.set_status(camp_id, "active")
    return {"ok": True, "status": "active"}


@app.post("/api/sites/{site}/auto-campaigns/{camp_id}/stop")
def api_auto_campaign_stop_one(site: str, camp_id: str, request: Request):
    if not _ac_admin(request):
        return {"ok": False, "error": "Rôle admin requis."}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import auto_campaign_backend as ab
    ab.set_status(camp_id, "stopped")
    return {"ok": True, "status": "stopped"}


@app.delete("/api/sites/{site}/auto-campaigns/{camp_id}")
def api_auto_campaign_delete(site: str, camp_id: str, request: Request):
    if not _ac_admin(request):
        return {"ok": False, "error": "Rôle admin requis."}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import auto_campaign_backend as ab
    ab.delete_auto_campaign(camp_id)
    return {"ok": True}


@app.post("/api/sites/{site}/auto-campaigns/{camp_id}/run")
def api_auto_campaign_run_now(site: str, camp_id: str, request: Request):
    """Trigger manuel : lance l'orchestrateur en process détaché pour cette campagne."""
    if not _ac_admin(request):
        return {"ok": False, "error": "Rôle admin requis."}
    cmd = ["python3", "scripts/auto_campaign_runner.py", "--site", site, "--campaign-id", camp_id]
    log_f = open(str(BASE_DIR / "logs" / f"auto_campaign-{site}.log"), "w")
    try:
        subprocess.Popen(cmd, cwd=str(BASE_DIR), start_new_session=True,
                         stdout=log_f, stderr=subprocess.STDOUT)
    finally:
        log_f.close()
    return {"ok": True, "started": True}


@app.get("/api/campaigns/{campaign_id}/stats-by-day")
def api_campaign_stats_by_day(campaign_id: str):
    """Stats par jour d'une campagne (agrège emelia_events) + totaux globaux."""
    import duckdb as _dd
    c = _duck(BASE_DIR / "data" / "god_mode.duckdb")
    try:
        rows = c.execute("""
            SELECT CAST(COALESCE(emelia_date, received_at) AS DATE) AS day, event_type, COUNT(*) AS n
            FROM emelia_events WHERE campaign_id = ?
            GROUP BY 1, 2 ORDER BY 1
        """, [campaign_id]).fetchall()
    finally:
        c.close()
    by_day: dict = {}
    totals: dict = {}
    for day, et, n in rows:
        d = str(day)
        by_day.setdefault(d, {"day": d})
        by_day[d][et] = int(n)
        totals[et] = totals.get(et, 0) + int(n)
    return {"ok": True, "campaign_id": campaign_id, "by_day": list(by_day.values()), "totals": totals}


@app.post("/api/sites/{site}/templates/{sector}/{kind}/send-test")
async def api_template_send_test(site: str, sector: str, kind: str, request: Request):
    """BAT : envoie l'email de test de la séquence du secteur à une adresse saisie.
    Réutilise la campagne Emelia du secteur (steps = templates verrouillés) + /emails/test."""
    body = await request.json()
    email = (body.get("email") or "").strip()
    if not email or "@" not in email:
        return {"ok": False, "error": "Adresse email destinataire invalide."}
    step = {"first": 0, "relance1": 1, "relance2": 2}.get(kind, 0)
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import workflow_emelia_push as wep
    try:
        cid = wep.ensure_campaign_for_auto(site, sector)
    except Exception as e:
        return {"ok": False, "error": f"Campagne Emelia: {e}"}
    if not cid:
        return {"ok": False, "error": "Campagne Emelia indisponible (clé manquante ?)."}
    key = wep._get_key(site)
    try:
        r = requests.post("https://api.emelia.io/emails/test",
                          json={"campaignId": cid, "email": email, "step": step},
                          headers={"Authorization": key, "Content-Type": "application/json"}, timeout=15)
        if r.status_code not in (200, 201):
            return {"ok": False, "error": f"Emelia HTTP {r.status_code}", "detail": r.text[:160]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "message": f"BAT envoyé à {email}"}


@app.get("/api/sites/{site}/cleanup/status")
def api_cleanup_status(site: str):
    """État détaillé des nettoyages actifs pour ce site (avec progress)."""
    with _cleanup_lock:
        items = [
            {"mode": k.split(":", 1)[1], **v}
            for k, v in _active_cleanups.items()
            if k.startswith(site + ":")
        ]
    # Compat ancien front : on garde aussi un champ "active" = liste des modes
    return {"active": [it["mode"] for it in items], "items": items}


@app.get("/api/cleanup/active")
def api_cleanup_active_global():
    """État GLOBAL (tous sites) pour la superadmin top bar."""
    with _cleanup_lock:
        items = [{"key": k, **v} for k, v in _active_cleanups.items()]
    return {"count": len(items), "items": items}


@app.get("/api/sites/{site}/cleanup/test-batch")
def api_cleanup_test_batch(site: str, limit: int = 5, mode: str = "unverified",
                           drain: bool = False, chunk_size: int = 3):
    """Test d'intégration LOOPBACK-ONLY : exécute synchrone (single ou drain) et compare counts."""
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    if mode not in ("unverified", "stale"):
        return {"ok": False, "error": "mode invalide"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import cleanup_backend as cb, time as _t
    before = {"unverified": cb.count_unverified(), "stale": cb.count_stale(days=180)}
    t0 = _t.time()
    if drain:
        res = cb.run_cleanup_drain(
            mode=mode, site=site,
            chunk_size=chunk_size,
            total_limit=limit,
        )
    else:
        res = cb.run_cleanup(mode=mode, site=site, limit=limit)
    after = {"unverified": cb.count_unverified(), "stale": cb.count_stale(days=180)}
    return {
        "ok": True, "mode": mode, "drain": drain,
        "limit": limit, "chunk_size": chunk_size,
        "elapsed_s": round(_t.time() - t0, 2),
        "counts_before": before, "counts_after": after,
        "diff_unverified": before["unverified"] - after["unverified"],
        "result": res,
    }


@app.get("/api/sites/{site}/cleanup/dryrun")
def api_cleanup_dryrun(site: str, email: str = ""):
    """Test unitaire NON-DESTRUCTIF : valide 1 contact et indique ce qui SERAIT fait, sans toucher la DB.
    Si email vide → prend le premier non vérifié du pool."""
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import cleanup_backend as cb
    from acquisition_backend import _validate_address
    import duckdb
    target = (email or "").strip()
    if not target:
        # Récup 1 candidat : on passe par la même config (read_only=False) pour éviter
        # le "different configuration than existing connections" de DuckDB.
        c = cb._pool(read_only=False)
        try:
            row = c.execute(
                "SELECT email FROM contacts "
                "WHERE (mailnjoy_check IS NULL OR LENGTH(mailnjoy_check)=0) "
                "AND (global_blacklisted IS NULL OR global_blacklisted = FALSE) "
                "ORDER BY created_at NULLS FIRST LIMIT 1"
            ).fetchone()
        finally:
            c.close()
        if not row:
            return {"ok": False, "error": "Aucun contact non vérifié dans le pool"}
        target = row[0]
    v = _validate_address(target)
    mn = v.get("mailnjoy_check")
    would = "skip"
    if not v.get("ok"):
        would = "delete"
    elif mn is not None:
        would = "update"
    return {
        "ok": True,
        "email": target,
        "validate_ok": v.get("ok"),
        "decision": v.get("decision"),
        "reason": v.get("reason"),
        "mailnjoy_check": mn,
        "would_action": would,
    }


@app.post("/api/sites/{site}/imagekit/upload")
async def api_imagekit_upload(site: str, file: UploadFile = File(...)):
    """Upload une image vers ImageKit (clé privée côté serveur, jamais exposée). Renvoie l'URL."""
    import os as _os, base64 as _b64
    key = _os.environ.get("IMAGEKIT_PRIVATE_KEY", "") or load_env().get("IMAGEKIT_PRIVATE_KEY", "")
    if not key:
        return {"ok": False, "error": "IMAGEKIT_PRIVATE_KEY manquante dans .env"}
    content = await file.read()
    auth = _b64.b64encode((key + ":").encode()).decode()
    try:
        r = requests.post(
            "https://upload.imagekit.io/api/v1/files/upload",
            headers={"Authorization": "Basic " + auth},
            files={"file": (file.filename or "upload.png", content)},
            data={"fileName": file.filename or "upload.png", "useUniqueFileName": "true", "folder": "/genesis-newsletters"},
            timeout=30,
        )
        if r.status_code not in (200, 201):
            return {"ok": False, "error": f"imagekit {r.status_code}: {r.text[:200]}"}
        return {"ok": True, "url": r.json().get("url", "")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/sites/{site}/pool/campaigns/create")
async def api_pool_campaigns_create(site: str, request: Request):
    """Crée une campagne Emelia depuis le pool : pick N contacts → create Emelia → push.

    Body: {name, sector, volume_target, volume_per_day}
    """
    body = await request.json()
    name = (body.get("name") or "").strip()
    sector = (body.get("sector") or "").strip()
    volume_target = int(body.get("volume_target") or 30)
    volume_per_day = int(body.get("volume_per_day") or 10)
    message_type = (body.get("message_type") or "cold_email").strip()
    message_id = (body.get("message_id") or "").strip()
    subject = (body.get("subject") or "").strip()

    if not name or not sector:
        return {"ok": False, "error": "name and sector required"}

    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from contacts_pool_backend import pick_for_campaign, mark_pushed_to_emelia, count_available_for_sector
    from emelia_campaign_manager import get_default_steps, build_newsletter_steps
    from workflow_emelia_push import _get_key

    # 0. Préparer le message (fail-fast AVANT toute création côté Emelia)
    if message_type == "newsletter":
        import html_templates_backend as htb, email_lint_backend as elb
        msg = htb.get_version(site, message_id)
        if not msg:
            return {"ok": False, "error": "Message validé introuvable."}
        if not subject:
            return {"ok": False, "error": "Sujet requis pour une newsletter."}
        stored = elb.get_all_results(site).get(f"version:{message_id}")
        if stored is None:
            return {"ok": False, "error": "Teste d'abord ce message (bouton Tester) avant de l'envoyer."}
        if stored.get("blocking"):
            return {"ok": False, "error": "Message bloquant au lint (lien cassé / variable inconnue). Corrige-le avant l'envoi."}
        steps = build_newsletter_steps(msg["html"], subject)
    else:
        steps = get_default_steps(sector, site=site)

    # 1. Pick contacts
    available = count_available_for_sector(site, sector)
    if available == 0:
        return {"ok": False, "error": f"Aucun contact dispo dans le secteur {sector}"}
    actual_volume = min(volume_target, available)
    contacts = pick_for_campaign(site, sector, limit=actual_volume)
    if not contacts:
        return {"ok": False, "error": "pick_for_campaign returned empty"}

    # 2. Get Emelia key for this site
    api_key = _get_key(site)
    if not api_key:
        return {"ok": False, "error": f"no emelia key for site={site}"}

    EMELIA_URL = "https://api.emelia.io"
    H = {"Authorization": api_key, "Content-Type": "application/json"}

    # 3. Create campaign
    r = requests.post(f"{EMELIA_URL}/emails/campaigns",
                      json={"name": name}, headers=H, timeout=20)
    if r.status_code not in (200, 201):
        return {"ok": False, "error": f"emelia create failed: {r.status_code} {r.text[:200]}"}
    camp = r.json().get("campaign", r.json())
    cid = camp.get("_id")
    if not cid:
        return {"ok": False, "error": "no campaign _id returned"}

    # 4. Configure steps (préparés à l'étape 0 : séquence cold email OU newsletter)
    try:
        requests.patch(f"{EMELIA_URL}/emails/campaigns/{cid}/steps",
                       json={"steps": steps}, headers=H, timeout=20)
    except Exception as e:
        print(f"  [campaigns/create] warn steps: {e}")

    # 5. Add contacts (batch)
    pushed = 0
    for c in contacts:
        contact_payload = {
            "email": c["email"],
            "firstName": c.get("prenom") or "",
            "lastName":  c.get("nom") or "",
            "field1":    c.get("societe") or "",
            "field2":    c.get("city") or "",
            "field3":    c.get("dept_code") or "",
            "field4":    c.get("website") or "",
        }
        try:
            r = requests.post(f"{EMELIA_URL}/emails/campaign/contacts",
                              json={"id": cid, "contact": contact_payload},
                              headers=H, timeout=15)
            if r.status_code in (200, 201):
                pushed += 1
                # Update pool side : mark pushed
                mark_pushed_to_emelia(c["id"], site, cid, "")
        except Exception as e:
            print(f"  [campaigns/create] add_contact failed: {e}")

    # 6. Start campaign
    try:
        requests.post(f"{EMELIA_URL}/emails/campaigns/{cid}/start",
                      headers=H, timeout=15)
    except Exception as e:
        print(f"  [campaigns/create] warn start: {e}")

    # 7. Register webhook (idempotent — déjà ALL_CAMPAIGNS mais on s'assure)
    try:
        import os as _os
        WEBHOOK_URL = "https://api.cheffer.email/api/emelia/webhook?token=" + _os.environ.get("WEBHOOK_TOKEN_1", "")
        if _os.environ.get("WEBHOOK_TOKEN_1"):
            requests.post(f"{EMELIA_URL}/webhook",
                json={"hookUrl": WEBHOOK_URL, "campaignId": cid,
                      "events": ["SENT","OPENED","CLICKED","REPLIED","BOUNCED","UNSUBSCRIBED"],
                      "type": "email"}, headers=H, timeout=15)
    except Exception as e:
        print(f"  [campaigns/create] warn webhook: {e}")

    return {
        "ok": True,
        "campaign_id": cid,
        "campaign_name": name,
        "pushed_count": pushed,
        "available_at_pick": available,
        "actual_volume": actual_volume,
    }


@app.post("/api/sites/{site}/pool/contacts/create")
async def api_pool_contact_create(site: str, request: Request):
    """Crée un nouveau contact dans le pool + l'attache à ce site."""
    body = await request.json()
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from contacts_pool_backend import create_in_pool, upsert_site_history
    cid = create_in_pool(body, primary_source=body.get("primary_source", "manual"))
    if not cid:
        return {"ok": False, "error": "invalid email"}
    upsert_site_history(cid, site,
                       state=body.get("state", "cold_email"),
                       source=body.get("source", "manual"),
                       by="ui_create")
    return {"ok": True, "contact_id": cid}


@app.patch("/api/sites/{site}/pool/contacts/{contact_id}")
async def api_pool_contact_update(site: str, contact_id: str, request: Request):
    """Update champs d'un contact dans le pool master (pas le history)."""
    body = await request.json()
    import duckdb as _dd
    c = _dd.connect(str(BASE_DIR / "data" / "contacts.duckdb"))
    try:
        # Champs autorisés à update
        ALLOWED = {"prenom", "nom", "societe", "tel", "website", "city",
                   "dept_code", "region_code", "postal_code",
                   "logo_url", "client_since"}
        updates, params = [], []
        for k, v in body.items():
            if k in ALLOWED:
                updates.append(f"{k} = ?")
                params.append(v)
        if not updates:
            return {"ok": False, "error": "no updatable fields"}
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(contact_id)
        c.execute(f"UPDATE contacts SET {', '.join(updates)} WHERE id = ?", params)
    finally:
        c.close()
    return {"ok": True}


@app.delete("/api/sites/{site}/pool/contacts/{contact_id}")
async def api_pool_contact_delete(site: str, contact_id: str, hard: bool = False):
    """Supprime la row contact_site_history pour ce site (ou hard delete tout)."""
    import duckdb as _dd
    c = _dd.connect(str(BASE_DIR / "data" / "contacts.duckdb"))
    try:
        if hard:
            c.execute("DELETE FROM contact_site_history WHERE contact_id = ?", [contact_id])
            c.execute("DELETE FROM contacts WHERE id = ?", [contact_id])
        else:
            c.execute(
                "DELETE FROM contact_site_history WHERE contact_id = ? AND site_code = ?",
                [contact_id, site]
            )
    finally:
        c.close()
    return {"ok": True, "hard": hard}


@app.post("/api/sites/{site}/pool/contacts/import-csv")
async def api_pool_csv_import(site: str, request: Request):
    """Import CSV : crée les contacts dans le pool + attache au site."""
    body = await request.json()
    rows = body.get("rows", [])
    default_state = body.get("default_state", "cold_email")
    sectors_for_all = body.get("sectors", [])

    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from contacts_pool_backend import create_in_pool, upsert_site_history

    added, skipped, errors = 0, 0, 0
    for r in rows:
        email = (r.get("email") or "").strip().lower()
        if not email or "@" not in email:
            skipped += 1
            continue
        try:
            data = {
                "email": email,
                "prenom":  r.get("prenom") or r.get("firstName") or "",
                "nom":     r.get("nom") or r.get("lastName") or "",
                "societe": r.get("societe") or r.get("company") or "",
                "tel":     r.get("tel") or r.get("phone") or "",
                "website": r.get("website") or "",
                "city":    r.get("city") or "",
                "dept_code": r.get("dept_code") or "",
                "sectors": sectors_for_all or ([r.get("sector")] if r.get("sector") else None),
            }
            cid = create_in_pool(data, primary_source="csv")
            if cid:
                upsert_site_history(cid, site, state=default_state, source="import_csv", by="csv_import")
                added += 1
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            print(f"  [csv import] err: {e}")
    return {"ok": True, "added": added, "skipped": skipped, "errors": errors}


# ── Import CSV intelligent (analyze → commit SSE) ────────────────────────────--
@app.post("/api/sites/{site}/pool/import/analyze")
async def api_pool_import_analyze(site: str, file: UploadFile = File(...)):
    """Phase 1 : upload + détection séparateur/charset + mapping + matching secteur
    DeepSeek (1 call, cap 30) + pré-analyse dédup. Renvoie un récap (import_id)."""
    name = (file.filename or "import.csv")
    if not name.lower().endswith(".csv"):
        return {"error": "format invalide — fichier .csv attendu"}
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        return {"error": "fichier trop volumineux (max 50 Mo)"}

    import re
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:80]
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_dir = BASE_DIR / "data" / "imports" / site
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{ts}_{safe}"
    dest.write_bytes(raw)
    try:
        dest.chmod(0o600)
    except Exception:
        pass

    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from csv_import_backend import analyze
    try:
        return analyze(str(dest), site, filename=name)
    except Exception as e:
        import traceback; traceback.print_exc()
        return {"error": f"analyse échouée: {e}"}


@app.post("/api/sites/{site}/pool/import/{import_id}/commit")
async def api_pool_import_commit(site: str, import_id: str):
    """Phase 2 : import batché. Stream SSE des events de progression {step, pct, …}."""
    from fastapi.responses import StreamingResponse
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from csv_import_backend import commit_import

    def _gen():
        try:
            for ev in commit_import(import_id, site):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:
            import traceback; traceback.print_exc()
            yield f"data: {json.dumps({'step': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/sectors")
def api_list_sectors():
    """Liste dynamique des secteurs (seed 16 + autre + secteurs importés). Cap 30."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from god_mode_backend import list_sectors, MAX_SECTORS
    sectors = list_sectors()
    return {"sectors": sectors, "total": len(sectors), "max": MAX_SECTORS}


@app.post("/api/sites/{site}/onboarding/send-test-email")
async def api_onboarding_send_test(site: str, request: Request):
    """Step 16 du wizard — envoie 1 email test à l'email du propriétaire pour valider la chaîne.

    Body : {test_email: str, sector: str (optionnel, défaut 'restaurant')}
    """
    body = await request.json()
    test_email = (body.get("test_email") or "").strip().lower()
    sector = body.get("sector", "restaurant")
    if not test_email or "@" not in test_email:
        return {"ok": False, "error": "test_email invalide"}

    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from workflow_emelia_push import _get_key
    from emelia_campaign_manager import get_default_steps
    api_key = _get_key(site)
    if not api_key:
        return {"ok": False, "error": f"no emelia key for site={site} (configure step 9 first)"}

    EMELIA_URL = "https://api.emelia.io"
    H = {"Authorization": api_key, "Content-Type": "application/json"}

    # 1. Cherche ou crée une campagne onboarding-test
    camp_name = f"onboarding-test-{site}"
    r = requests.get(f"{EMELIA_URL}/emails/campaigns", headers=H, timeout=15)
    cid = None
    if r.status_code == 200:
        for c in (r.json().get("campaigns") or []):
            if c.get("name") == camp_name:
                cid = c.get("_id")
                break

    if not cid:
        # Create
        r = requests.post(f"{EMELIA_URL}/emails/campaigns",
                          json={"name": camp_name}, headers=H, timeout=20)
        if r.status_code not in (200, 201):
            return {"ok": False, "error": f"create campaign failed: {r.status_code}"}
        camp = r.json().get("campaign", r.json())
        cid = camp.get("_id")
        if not cid:
            return {"ok": False, "error": "no campaign _id returned"}
        # Configure steps avec template du secteur
        try:
            steps = get_default_steps(sector, site=site)
            requests.patch(f"{EMELIA_URL}/emails/campaigns/{cid}/steps",
                           json={"steps": steps}, headers=H, timeout=20)
        except Exception as e:
            print(f"  [onboarding test] warn steps: {e}")

    # 2. POST /emails/test (envoi instantané sans respecter cadence)
    try:
        r = requests.post(f"{EMELIA_URL}/emails/test",
                          json={"campaignId": cid, "email": test_email, "step": 0},
                          headers=H, timeout=20)
        if r.status_code in (200, 201):
            return {"ok": True, "campaign_id": cid, "sent_to": test_email}
        return {"ok": False, "error": f"emelia test failed: {r.status_code} {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/sites/{site}/onboarding/confirm-activation")
async def api_onboarding_confirm(site: str, request: Request):
    """User a reçu le mail test → on active le site (god_mode_state.enabled=TRUE)."""
    body = await request.json()
    received = bool(body.get("received", False))
    if not received:
        return {"ok": False, "error": "received must be true to activate"}
    import duckdb as _dd
    c = _dd.connect(str(BASE_DIR / "data" / "god_mode.duckdb"))
    try:
        c.execute("""
            INSERT OR REPLACE INTO god_mode_state
            (site_code, enabled, enabled_by, enabled_at, updated_at)
            VALUES (?, TRUE, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, [site, "onboarding_mail_test_confirmed"])
    finally:
        c.close()
    return {"ok": True, "site": site, "enabled": True}


@app.get("/api/sites/{site}/geo/regions")
def api_geo_regions(site: str):
    # Métropole uniquement : Corse + DOM-TOM exclus du scrapper (demande user 2026-06-16).
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from workflow_geo import metropole_regions
    return {"regions": metropole_regions()}


@app.get("/api/sites/{site}/geo/departments")
def api_geo_departments(site: str, region: str = ""):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from workflow_geo import metropole_departments
    return {"departments": metropole_departments(region or None)}


@app.get("/api/sites/{site}/geo/cities")
def api_geo_cities(site: str, dept: str = "", region: str = "", min_pop: int = 10000):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from workflow_geo import metropole_cities
    return {"cities": metropole_cities(dept or None, region or None, min_pop=min_pop)}


@app.get("/api/sites/{site}/scrape/cron-config")
def api_scrape_cron_get(site: str):
    import duckdb as _dd, json as _json
    c = _duck(BASE_DIR / "data" / "god_mode.duckdb")
    try:
        row = c.execute("""
            SELECT scrape_cron_days, scrape_cron_hour, scrape_cron_minute, scrape_cron_enabled
            FROM god_mode_settings WHERE site_code = ?
        """, [site]).fetchone()
    finally:
        c.close()
    if not row:
        return {"days": [1,2,3,4,5], "hour": 6, "minute": 30, "enabled": True, "cron_expr": "30 6 * * 1-5"}
    days_raw, hour, minute, enabled = row
    try:
        days = _json.loads(days_raw) if isinstance(days_raw, str) else (days_raw or [1,2,3,4,5])
    except Exception:
        days = [1,2,3,4,5]
    cron_expr = _build_cron(minute, hour, days)
    return {"days": days, "hour": hour, "minute": minute, "enabled": bool(enabled), "cron_expr": cron_expr}


@app.post("/api/sites/{site}/scrape/cron-config")
async def api_scrape_cron_set(site: str, request: Request):
    body = await request.json()
    days = body.get("days", [1,2,3,4,5])
    hour = int(body.get("hour", 6))
    minute = int(body.get("minute", 30))
    enabled = bool(body.get("enabled", True))
    import duckdb as _dd, json as _json
    c = _dd.connect(str(BASE_DIR / "data" / "god_mode.duckdb"))
    try:
        existing = c.execute("SELECT site_code FROM god_mode_settings WHERE site_code = ?", [site]).fetchone()
        if existing:
            c.execute("""
                UPDATE god_mode_settings
                SET scrape_cron_days = ?, scrape_cron_hour = ?, scrape_cron_minute = ?, scrape_cron_enabled = ?
                WHERE site_code = ?
            """, [_json.dumps(days), hour, minute, enabled, site])
        else:
            c.execute("""
                INSERT INTO god_mode_settings
                (site_code, scrape_cron_days, scrape_cron_hour, scrape_cron_minute, scrape_cron_enabled)
                VALUES (?, ?, ?, ?, ?)
            """, [site, _json.dumps(days), hour, minute, enabled])
    finally:
        c.close()
    return {"ok": True, "cron_expr": _build_cron(minute, hour, days), "enabled": enabled}


def _build_cron(minute: int, hour: int, days: list) -> str:
    """Génère expression crontab depuis (minute, heure, jours[1..7]).
    1=lundi ... 7=dimanche → cron 0=dimanche, 1=lundi ... 6=samedi
    """
    if not days:
        return f"{minute} {hour} * * *"
    cron_days_map = {1:1, 2:2, 3:3, 4:4, 5:5, 6:6, 7:0}
    cron_days = sorted(set(cron_days_map[d] for d in days if d in cron_days_map))
    if cron_days == [1,2,3,4,5]:
        return f"{minute} {hour} * * 1-5"
    if cron_days == [0,1,2,3,4,5,6]:
        return f"{minute} {hour} * * *"
    return f"{minute} {hour} * * {','.join(str(d) for d in cron_days)}"


# Au-dela de ce delai, un scrape sans log de fin est considere mort (thread tue par un
# restart process, ou hang). Un scrape reel se termine en minutes -> 2h = marge tres large.
SCRAPE_STALE_TIMEOUT_MIN = 120


@app.get("/api/sites/{site}/scrape/live-activity")
def api_scrape_live_activity(site: str, limit: int = 20):
    """Live-activity feed des scrapes : matche start_scrape + scrape + crédits Serper consommés."""
    import duckdb as _dd, json as _json
    c = _duck(BASE_DIR / "data" / "god_mode.duckdb")
    try:
        starts = c.execute("""
            SELECT id, created_at, resource_id, username, payload
            FROM god_mode_logs
            WHERE site_code = ? AND action = 'start_scrape'
            ORDER BY created_at DESC LIMIT ?
        """, [site, limit]).fetchall()

        out = []
        for s in starts:
            sid, start_at, sector, username, payload_raw = s
            try:
                start_payload = _json.loads(payload_raw) if isinstance(payload_raw, str) else (payload_raw or {})
            except Exception:
                start_payload = {}
            cities = start_payload.get("cities") or []
            max_results = start_payload.get("max_results", 0)
            # Runs antérieurs au 2026-08-21 : la marque n'existait pas. On la déduit — un
            # run lancé par un compte nommé est manuel, le reste vient de l'orchestrateur.
            declencheur = start_payload.get("declencheur") or (
                "manuel" if (username and username not in ("cron", "system", "autoscrape"))
                else "automatique")

            # Libellé périmètre (région) issu du start_scrape — autoscrape région agrégé.
            scope = start_payload.get("scope") or start_payload.get("region_name")
            run_message = None
            # Match avec le scrape end (même sector, postérieur). Fenêtre large (12 h) car
            # un autoscrape région tourne longtemps — 1 seul run à la fois ⇒ pas de collision.
            # NB : le scraper logge AUSSI une ligne action='scrape' PAR VILLE (payload sans
            # 'scope'). Sans le filtre json, la 1re ville (quelques secondes après le start,
            # souvent 0 partout) était prise pour la fin du run → « Région finie · 7s · 0 ».
            # Borne haute du run = prochain start du même secteur (un seul run à la fois),
            # à défaut maintenant. Remplace une fenêtre fixe de 12 h qui classait à tort
            # « timeout » tout autoscrape régional plus long qu'elle : celui du 30/07 a
            # tourné 12 h 58 et s'est terminé « done » (713 valides), mais sa fin tombait
            # 58 min hors fenêtre — donc jamais appariée, donc affichée en échec.
            _nxt = c.execute(
                "SELECT min(created_at) FROM god_mode_logs WHERE site_code = ? "
                "AND action = 'start_scrape' AND resource_id = ? AND created_at > ?",
                [site, sector, start_at]).fetchone()[0]
            _upper = _nxt or _dt_now()
            end_row = c.execute("""
                SELECT created_at, payload, success
                FROM god_mode_logs
                WHERE site_code = ? AND action = 'scrape' AND resource_id = ?
                  AND created_at > ? AND created_at < ?
                  AND json_extract_string(payload, '$.scope') IS NOT NULL
                ORDER BY created_at ASC LIMIT 1
            """, [site, sector, start_at, _upper]).fetchone()

            end_at = None; scraped = 0; valid = 0; rejected = 0; errors = 0; status = "running"
            duplicates = 0; net = None; cleanup = None; skipped_seen = 0
            valid_serper = None; valid_basile = None
            if end_row:
                end_at, end_payload_raw, success = end_row
                try:
                    ep = _json.loads(end_payload_raw) if isinstance(end_payload_raw, str) else (end_payload_raw or {})
                except Exception:
                    ep = {}
                scraped  = ep.get("scraped", 0)
                valid    = ep.get("valid", 0)
                rejected = ep.get("rejected", 0)
                errors   = ep.get("errors", 0)
                duplicates = ep.get("duplicates", 0)
                skipped_seen = ep.get("skipped_seen", 0)
                valid_serper = ep.get("valid_serper")
                valid_basile = ep.get("valid_basile")
                cleanup  = ep.get("cleanup")
                # net = contacts gardés après Mailnjoy. Si pas de champ net (runs anciens),
                # on dérive valid − supprimés ; sinon net = valid (pas de cleanup loggé).
                if ep.get("net") is not None:
                    net = ep.get("net")
                elif cleanup and cleanup.get("removed") is not None:
                    net = max(0, (valid or 0) - int(cleanup.get("removed") or 0))
                scope    = ep.get("scope") or scope
                run_message = ep.get("message")
                # Statut métier précis (région finie, bloquée Serper…) plutôt que done/failed.
                _st = ep.get("status")
                status = _st if _st in ("done", "blocked_serper", "stopped", "timeout", "stalled") else ("done" if success else "failed")
            else:
                # Pas de log de fin (run interrompu / timeout ou en cours) : le recap chiffre du log
                # final manque. On recupere le VRAI nombre de contacts SAUVES (insertion au fil de
                # l'eau, AVANT la fin), borne a la fenetre de ce run (_upper, calcule plus haut).
                try:
                    valid = c.execute(
                        "SELECT (SELECT count(*) FROM scrappe_pending WHERE site_code = ? AND sector = ? "
                        "AND created_at >= ? AND created_at < ?) + (SELECT count(*) FROM scrappe "
                        "WHERE site_code = ? AND sector = ? AND created_at >= ? AND created_at < ?)",
                        [site, sector, start_at, _upper, site, sector, start_at, _upper]).fetchone()[0] or 0
                except Exception:
                    valid = 0

            # Calc credits consommés entre start_at et end_at (ou now si running)
            until_clause = "AND created_at <= ?" if end_at else ""
            params = [site, sector.split()[0] if sector else "", start_at]
            if end_at: params.append(end_at)
            credits_used = c.execute(f"""
                SELECT COALESCE(SUM(credits), 0)
                FROM god_mode_serper_calls
                WHERE site_code = ? AND query LIKE '%' || ? || '%'
                  AND created_at >= ? {until_clause}
            """, params).fetchone()[0]

            # Duration
            duration_s = None
            if end_at:
                try: duration_s = int((end_at - start_at).total_seconds())
                except Exception: pass

            # Progression (% de complétion)
            # En running : on estime progress depuis le temps écoulé / 60s par ville (très approximatif)
            if status == "running":
                elapsed = (_dt_now() - start_at).total_seconds() if start_at else 0
                if elapsed > SCRAPE_STALE_TIMEOUT_MIN * 60:
                    # Plus de fin loggee apres 2h -> run mort (thread tue par un restart). On le clot.
                    status = "timeout"
                    progress_pct = 100
                else:
                    est_total = max(60, 30 * (len(cities) or 1))  # 30s par ville env
                    progress_pct = min(95, int(elapsed / est_total * 100))
            else:
                progress_pct = 100

            out.append({
                "id":            sid,
                "start_at":      str(start_at) if start_at else None,
                "end_at":        str(end_at) if end_at else None,
                "duration_s":    duration_s,
                "sector":        sector,
                "cities":        cities,
                "scope":         scope,
                "message":       run_message,
                "max_results":   max_results,
                "username":      username or "cron",
                "declencheur":   declencheur,
                "status":        status,
                "scraped":       scraped,
                "valid":         valid,
                "valid_serper":  valid_serper,
                "valid_basile":  valid_basile,
                "rejected":      rejected,
                "duplicates":    duplicates,
                "skipped_seen":  skipped_seen,
                "errors":        errors,
                "net":           net,
                "cleanup":       cleanup,
                "credits_used":  int(credits_used or 0),
                "progress_pct":  progress_pct,
            })
        return {"activity": out}
    finally:
        c.close()


def _dt_now():
    from datetime import datetime
    return datetime.now()


@app.get("/api/sites/{site}/warmup-status")
def api_warmup_status(site: str):
    """Retourne le statut warmup du/des senders d'un site."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from workflow_emelia_push import daily_warmup_quota, emelia_sent_today_by_sender
    import duckdb as _dd
    c = _duck(BASE_DIR / "data" / "god_mode.duckdb")
    try:
        rows = c.execute("SELECT sender_email, sender_name, warmup_start_date, status, daily_max_override FROM email_senders WHERE site_code = ?", [site]).fetchall()
    finally:
        c.close()
    out = []
    from datetime import date as _date
    today = _date.today()
    for sender_email, sender_name, start_date, status, override in rows:
        days_since = (today - start_date).days + 1 if start_date else 0
        quota = daily_warmup_quota(sender_email) or 0
        sent = emelia_sent_today_by_sender(sender_email) or 0
        out.append({
            "sender_email": sender_email,
            "sender_name":  sender_name,
            "status":       status,
            "warmup_day":   days_since,
            "daily_quota":  quota,
            "sent_today":   sent,
            "remaining":    max(0, quota - sent),
            "is_override":  override is not None,
        })
    return {"senders": out}


@app.get("/api/versions/log/{log_name}")
def api_version_log(log_name: str):
    """Retourne le contenu d'un changelog .log de version."""
    from fastapi.responses import PlainTextResponse
    # Sécu : nom doit matcher pattern strict (anti path traversal)
    import re as _re
    if not _re.match(r"^genesis-\d{4}-\d{2}-\d{2}-v\d{4}\.log$", log_name):
        return PlainTextResponse("invalid log name", status_code=400)
    p = BASE_DIR / "backups" / log_name
    if not p.exists():
        return PlainTextResponse("log not found", status_code=404)
    return PlainTextResponse(p.read_text(errors="replace"), media_type="text/plain; charset=utf-8")


@app.get("/api/versions/zip/{zip_name}")
def api_version_zip(zip_name: str):
    """Téléchargement d'un ZIP version."""
    from fastapi.responses import FileResponse, PlainTextResponse
    import re as _re
    if not _re.match(r"^genesis-\d{4}-\d{2}-\d{2}-v\d{4}\.zip$", zip_name):
        return PlainTextResponse("invalid zip name", status_code=400)
    p = BASE_DIR / "backups" / zip_name
    if not p.exists():
        return PlainTextResponse("zip not found", status_code=404)
    return FileResponse(p, media_type="application/zip", filename=zip_name)

