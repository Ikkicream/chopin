#!/usr/bin/env python3
"""
api.py — Backend FastAPI pour le dashboard Genesis.
Agrège les données de Emdash, Emelia, CRM interne (DuckDB), pm2, orchestrateur.

Lancer: uvicorn scripts.api:app --host 0.0.0.0 --port 8080 --reload
Ou:     python3 scripts/api.py
"""

import json
import sys
import subprocess
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from god_mode_api import router as god_mode_router
from auth_backend import login as auth_login, reset_password as auth_reset, send_password_telegram as auth_send_telegram, log_login as auth_log_login, get_login_logs as auth_get_logs, verify_session as auth_verify, logout as auth_logout, list_users as auth_list_users, create_user as auth_create_user, delete_user as auth_delete_user, update_user as auth_update_user
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
from fastapi import FastAPI, Request
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
}
_ADMIN_PREFIXES = ("/api/auth/users", "/api/auth/logs")


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
    if path in _AUTH_OPEN_PATHS:
        return await call_next(request)

    # Sinon : Bearer session token obligatoire
    bearer = request.headers.get("authorization", "")
    token = bearer[7:] if bearer.startswith("Bearer ") else ""
    sess = auth_verify(token) if token else None
    if not sess:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"error": "Bearer token required"})

    # Endpoints admin-only
    if any(path.startswith(p) for p in _ADMIN_PREFIXES) and sess.get("role") != "admin":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={"error": "admin role required"})

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
def get_campaigns():
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
        return {"campaigns": enriched}
    except Exception as e:
        return {"campaigns": [], "error": str(e)}


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
def get_budget(site: str = ""):
    import sys
    sys.path.insert(0, str(BASE_DIR))
    from scripts.cost_tracker import get_summary, PRICING

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
def get_connectors():
    """Vérifie la disponibilité de chaque connecteur (clé API + connexion réseau)."""
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

    # Resend (newsletter)
    resend_key = env.get("RESEND_API_KEY", "")
    results["resend"] = {"ok": bool(resend_key), "label": "Resend (newsletter)", "key_set": bool(resend_key), "env_var": "RESEND_API_KEY"}

    # Anthropic Claude
    claude_key = env.get("ANTHROPIC_API_KEY", "")
    results["claude"] = {"ok": bool(claude_key), "label": "Claude / Anthropic", "key_set": bool(claude_key), "env_var": "ANTHROPIC_API_KEY"}

    return {"connectors": results, "checkedAt": datetime.now(timezone.utc).isoformat()}


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
    uvicorn.run("scripts.api:app", host="0.0.0.0", port=8080, reload=False)


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
async def api_health_check():
    """Check health of all configured sites: HTTP, SSL, sitemap, robots.txt."""
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

    results = check_all_sites(sites)
    return {"sites": results, "checked_at": datetime.now(timezone.utc).isoformat()}


# ── Versions & Backups ────────────────────────────────────────────────────────

@app.get("/api/versions")
async def api_versions():
    """Git log + ZIP backup listing."""
    import glob

    # Git log (last 20 commits)
    git_log = []
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--format=%H|%ai|%s", "-20"],
            capture_output=True, text=True, cwd=str(BASE_DIR)
        )
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                parts = line.split("|", 2)
                git_log.append({
                    "hash": parts[0][:7],
                    "date": parts[1][:16],
                    "message": parts[2] if len(parts) > 2 else ""
                })
    except Exception:
        pass

    # ZIP backups
    backups = []
    backup_dir = BASE_DIR / "backups"
    if backup_dir.exists():
        zips = sorted(backup_dir.glob("genesis-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        for z in zips[:30]:
            stat = z.stat()
            size_mb = stat.st_size / (1024 * 1024)
            backups.append({
                "name": z.name,
                "size": f"{size_mb:.1f} MB",
                "date": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
            })

    return {"git_log": git_log, "backups": backups}


# ── SEO Ahrefs Data ───────────────────────────────────────────────────────────

@app.get("/api/seo-ahrefs/{site}")
async def api_seo_ahrefs(site: str):
    """Return cached Ahrefs data for a site."""
    cache_file = BASE_DIR / "memory" / "seo" / f"{site}-ahrefs-latest.json"
    if not cache_file.exists():
        return {"error": "no data", "site": site}
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


# ── Agents Registry ───────────────────────────────────────────────────────────

AGENTS_REGISTRY = [
    {"id": "editorial-manager", "name": "Editorial Manager", "model": "Haiku", "role": "Orchestre le pipeline éditorial complet", "cost_avg": "~0.002€", "status": "actif", "site": "both"},
    {"id": "seo-strategist", "name": "SEO Strategist", "model": "Haiku + Ahrefs", "role": "Brief SEO : H1/H2/H3, keywords, internal links", "cost_avg": "~0.01€ + 20 crédits", "status": "actif", "site": "both"},
    {"id": "content-writer", "name": "Content Writer", "model": "DeepSeek", "role": "Rédige les articles selon le brief", "cost_avg": "~0.25€", "status": "actif", "site": "both"},
    {"id": "internal-linking", "name": "Internal Linking", "model": "Haiku", "role": "Maillage interne entre articles", "cost_avg": "~0.005€", "status": "a_activer", "site": "both"},
    {"id": "quality-editor", "name": "Quality Editor", "model": "Haiku", "role": "Score /100 sur 5 dimensions", "cost_avg": "~0.005€", "status": "actif", "site": "both"},
    {"id": "visual-agent", "name": "Visual Agent", "model": "Unsplash API", "role": "Featured image + LinkedIn image", "cost_avg": "0€", "status": "a_activer", "site": "both"},
    {"id": "linkedin-specialist", "name": "LinkedIn Specialist", "model": "Haiku", "role": "Post LinkedIn J+3 apr\u00e8s publication", "cost_avg": "~0.01\u20ac", "status": "actif", "site": "both"},
    {"id": "competitive-intel", "name": "Competitive Intelligence", "model": "Haiku", "role": "Veille RSS concurrents + content gaps", "cost_avg": "~0.01€", "status": "actif", "site": "both"},
    {"id": "seo-strategy", "name": "SEO Strategy", "model": "Haiku + Ahrefs", "role": "Recommandations stratégiques hebdo", "cost_avg": "~0.02€", "status": "actif", "site": "both"},
    {"id": "briefing", "name": "Daily Briefing", "model": "Haiku", "role": "Rapport quotidien Telegram", "cost_avg": "~0.003€", "status": "actif", "site": "both"},
]

@app.get("/api/agents")
async def api_agents():
    """List all agents with their config."""
    return {"agents": AGENTS_REGISTRY}

@app.get("/api/agents/{agent_id}/instructions")
async def api_agent_instructions(agent_id: str):
    """Get the full instructions (.md) for an agent."""
    skills_dir = BASE_DIR / "skills"
    # Try multiple filenames
    candidates = [f"{agent_id}.md", f"{agent_id}.md"]
    for name in candidates:
        f = skills_dir / name
        if f.exists():
            return {"id": agent_id, "instructions": f.read_text()}
    return {"id": agent_id, "instructions": "Instructions non trouv\u00e9es.", "error": True}


# ── Agents Per-Site (upgraded) ────────────────────────────────────────────────

AGENT_CRONS_FILE = BASE_DIR / "memory" / "agent-crons.json"

def _load_agent_crons():
    if AGENT_CRONS_FILE.exists():
        return json.loads(AGENT_CRONS_FILE.read_text())
    # Defaults
    return {
        "lcr": {
            "editorial-manager": {"freq": "weekly", "day": "mon", "hour": 6},
            "seo-strategist": {"freq": "weekly", "day": "mon", "hour": 7},
            "content-writer": {"freq": "weekly", "day": "wed", "hour": 10},
            "internal-linking": {"freq": "weekly", "day": "wed", "hour": 11},
            "quality-editor": {"freq": "per_article", "day": None, "hour": None},
            "visual-agent": {"freq": "per_article", "day": None, "hour": None},
            "linkedin-specialist": {"freq": "daily", "day": None, "hour": 10},
            "competitive-intel": {"freq": "weekly", "day": "mon", "hour": 5},
        },
        "mkd": {
            "editorial-manager": {"freq": "weekly", "day": "mon", "hour": 6},
            "seo-strategist": {"freq": "weekly", "day": "thu", "hour": 7},
            "content-writer": {"freq": "weekly", "day": "thu", "hour": 10},
            "internal-linking": {"freq": "weekly", "day": "thu", "hour": 11},
            "quality-editor": {"freq": "per_article", "day": None, "hour": None},
            "visual-agent": {"freq": "per_article", "day": None, "hour": None},
            "linkedin-specialist": {"freq": "daily", "day": None, "hour": 10},
            "competitive-intel": {"freq": "weekly", "day": "mon", "hour": 5},
        },
    }

def _save_agent_crons(data):
    AGENT_CRONS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

AGENT_COSTS = {
    "editorial-manager": 0.002,
    "seo-strategist": 0.01,
    "content-writer": 0.25,
    "internal-linking": 0.005,
    "quality-editor": 0.005,
    "visual-agent": 0.0,
    "linkedin-specialist": 0.01,
    "competitive-intel": 0.01,
}

FREQ_MULTIPLIERS = {"daily": 30, "weekly": 4.3, "biweekly": 2.15, "monthly": 1, "per_article": 4.3}

@app.get("/api/agents/{site}")
async def api_agents_site(site: str):
    """Get agents config for a specific site with cron + cost."""
    crons = _load_agent_crons()
    site_crons = crons.get(site, {})

    agents = []
    for a in AGENTS_REGISTRY:
        if a["site"] not in ("both", site):
            continue
        cron = site_crons.get(a["id"], {"freq": "weekly"})
        cost_unit = AGENT_COSTS.get(a["id"], 0)
        freq = cron.get("freq", "weekly")
        cost_month = cost_unit * FREQ_MULTIPLIERS.get(freq, 4.3)

        agents.append({
            **a,
            "cron": cron,
            "cost_unit_eur": round(cost_unit * 0.92, 4),
            "cost_month_eur": round(cost_month * 0.92, 3),
        })

    return {"site": site, "agents": agents}

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

@app.post("/api/agents/{site}/{agent_id}/cron")
async def api_agent_update_cron(site: str, agent_id: str, request: Request):
    """Update cron schedule for an agent."""
    data = await request.json()
    crons = _load_agent_crons()
    if site not in crons:
        crons[site] = {}
    crons[site][agent_id] = {
        "freq": data.get("freq", "weekly"),
        "day": data.get("day"),
        "hour": data.get("hour"),
    }
    _save_agent_crons(crons)
    return {"ok": True, "cron": crons[site][agent_id]}

@app.get("/api/agents/{site}/planner")
async def api_agents_planner(site: str):
    """Return a weekly execution plan in logical order."""
    crons = _load_agent_crons()
    site_crons = crons.get(site, {})

    DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    DAY_LABELS = {"mon": "Lundi", "tue": "Mardi", "wed": "Mercredi", "thu": "Jeudi", "fri": "Vendredi", "sat": "Samedi", "sun": "Dimanche"}

    plan = {d: [] for d in DAYS}
    for agent_id, cron in site_crons.items():
        agent = next((a for a in AGENTS_REGISTRY if a["id"] == agent_id), None)
        if not agent:
            continue
        freq = cron.get("freq", "weekly")
        if freq == "daily":
            for d in DAYS:
                plan[d].append({"agent": agent["name"], "id": agent_id, "hour": cron.get("hour", 10), "model": agent["model"]})
        elif freq == "weekly" and cron.get("day"):
            day = cron["day"]
            if day in plan:
                plan[day].append({"agent": agent["name"], "id": agent_id, "hour": cron.get("hour", 10), "model": agent["model"]})
        elif freq == "per_article":
            pass  # triggered by pipeline, not scheduled

    # Sort each day by hour
    for d in plan:
        plan[d] = sorted(plan[d], key=lambda x: x.get("hour", 0))

    return {"site": site, "plan": {DAY_LABELS.get(d, d): plan[d] for d in DAYS if plan[d]}}


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

@app.post("/api/sites/{site}/acquisition/{contact_id}/email")
async def api_acq_send_email(site: str, contact_id: str, request: Request):
    """Envoie un email \u00e0 un contact d'acquisition (via Resend)."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.acquisition_backend import _conn
    data = await request.json()
    conn = _conn(site)
    try:
        row = conn.execute("SELECT email FROM acquisition_contacts WHERE id = ?", [contact_id]).fetchone()
    finally:
        conn.close()
    if not row:
        return {"error": "contact not found"}

    import os
    resend_key = os.environ.get("RESEND_API_KEY", "")
    if resend_key:
        try:
            r = requests.post("https://api.resend.com/emails", json={
                "from": data.get("from", f"contact@{site}.com"),
                "to": [row[0]],
                "subject": data.get("subject", ""),
                "text": data.get("body", ""),
            }, headers={"Authorization": f"Bearer {resend_key}"}, timeout=10)
            if r.status_code in (200, 201):
                return {"ok": True, "method": "resend", "status": r.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return {"ok": True, "method": "logged_only", "message": "Email log\u00e9 (Resend non configur\u00e9)"}


# ── Auth System ───────────────────────────────────────────────────────────────

def _real_ip(request: Request) -> str:
    """X-Forwarded-For first (Nginx proxy), fallback to socket peer."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


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
    """Create a user (admin only)."""
    data = await request.json()
    uid = auth_create_user(
        data.get("username", ""), data.get("password", ""),
        role=data.get("role", "viewer"),
        nom=data.get("nom", ""), prenom=data.get("prenom", ""),
        email=data.get("email", "")
    )
    if not uid:
        return {"error": "username already exists"}
    return {"ok": True, "id": uid}

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
    signature = '<p><img src="https://emelia-public-files.s3.eu-west-3.amazonaws.com/69821e307d7c504e0e847ac1-1778073002600-signature.png"></p><p><a href="{{UNSUBSCRIBE_LINK}}" rel="noopener noreferrer" target="_blank">Si vous ne souhaitez pas recevoir d\u2019email de ma part, n\u2019h\u00e9sitez pas \u00e0 cliquer sur ce lien \U0001f642</a></p>'

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


@app.post("/api/emelia/webhook")
async def api_emelia_webhook(request: Request):
    """Receive Emelia webhook events: opened, clicked, replied, bounced.
    Injects contacts into PRM for lcr site."""
    data = await request.json()

    # Emelia sends events like: {event: "opened", contact: {email, firstName, ...}, campaign: {name, ...}}
    event_type = data.get("event", data.get("type", ""))
    contact = data.get("contact", data.get("data", {}).get("contact", {}))
    campaign = data.get("campaign", data.get("data", {}).get("campaign", {}))

    email = contact.get("email", "")
    if not email:
        return {"ok": False, "error": "no email"}

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
        env = load_env()
        emelia_key = env.get("EMELIA_API_KEY", "")
        if not emelia_key:
            return {"error": "EMELIA_API_KEY introuvable"}
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
    site: str, state: str = "", source: str = "", search: str = "",
    limit: int = 100, offset: int = 0,
):
    """Liste paginée avec filtres multi-valeurs séparées par virgule.
    state=cold_email,prm  →  contacts dans ces 2 états."""
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.acquisition_backend import list_contacts
    states  = [s for s in (state or "").split(",") if s]
    sources = [s for s in (source or "").split(",") if s]
    return list_contacts(site, state=states or None, source=sources or None, search=search.strip(),
                         limit=min(500, max(1, limit)), offset=max(0, offset))


@app.get("/api/sites/{site}/acquisition/stats")
def api_acq_stats(site: str):
    if site not in ("lcr", "mkd"):
        return {"error": "invalid site"}
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from scripts.acquisition_backend import stats
    return stats(site)


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
    env = load_env()
    return blacklist(site, contact_id, push_emelia=push_emelia, emelia_api_key=env.get("EMELIA_API_KEY", ""))


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
