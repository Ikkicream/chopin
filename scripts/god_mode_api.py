#!/usr/bin/env python3
"""
god_mode_api.py — Router FastAPI pour la feature GOD MODE.
Tous les endpoints sont admin-only (header x-session-token requis).
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import date

import god_mode_backend as gm

router = APIRouter(prefix="/api/god-mode", tags=["god-mode"])


# ── Dependency admin ──────────────────────────────────────────────────────────
def require_admin(
    x_session_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    token = x_session_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    user = gm.verify_admin(token)
    if not user:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def _check_site(site: str):
    if site not in gm.VALID_SITES:
        raise HTTPException(status_code=400, detail=f"Site invalide: {site}")


def _ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()


# ── State + Toggle ────────────────────────────────────────────────────────────
@router.get("/{site}/state")
def state(site: str, user=Depends(require_admin)):
    _check_site(site)
    s = gm.get_state(site)
    if not s:
        raise HTTPException(status_code=404, detail="State introuvable")
    return s


@router.post("/{site}/toggle")
async def toggle(site: str, request: Request, user=Depends(require_admin)):
    _check_site(site)
    body = await request.json()
    enabled = bool(body.get("enabled", False))
    gm.set_state(site, enabled, user["username"])
    gm.log_action(site, user["username"], user["user_id"], "toggle",
                  resource="state", payload={"enabled": enabled}, ip=_ip(request))
    return gm.get_state(site)


# ── Settings ──────────────────────────────────────────────────────────────────
@router.get("/{site}/settings")
def settings_get(site: str, user=Depends(require_admin)):
    _check_site(site)
    return gm.get_settings(site)


@router.put("/{site}/settings")
async def settings_put(site: str, request: Request, user=Depends(require_admin)):
    _check_site(site)
    body = await request.json()
    daily_quota = int(body.get("daily_quota", 35))
    scrape_quota = int(body.get("scrape_quota", 100))
    if daily_quota < 1 or daily_quota > 36:
        raise HTTPException(status_code=400, detail="daily_quota doit être entre 1 et 36 (lissage Emelia 1/20min sur 8h-20h)")
    if scrape_quota < 1 or scrape_quota > 1000:
        raise HTTPException(status_code=400, detail="scrape_quota doit être entre 1 et 1000")
    gm.update_settings(site, daily_quota, scrape_quota, user["username"])
    gm.log_action(site, user["username"], user["user_id"], "update_settings",
                  resource="settings", payload={"daily_quota": daily_quota, "scrape_quota": scrape_quota}, ip=_ip(request))
    return gm.get_settings(site)


# ── Context check ─────────────────────────────────────────────────────────────
@router.get("/{site}/context-check")
def context_check(site: str, user=Depends(require_admin)):
    _check_site(site)
    return gm.context_check(site)


# ── Logs ──────────────────────────────────────────────────────────────────────
@router.get("/{site}/logs")
def logs(site: str, limit: int = 200, user=Depends(require_admin)):
    _check_site(site)
    return {"logs": gm.list_logs(site, limit=min(limit, 1000))}


# ── Prospects ─────────────────────────────────────────────────────────────────
@router.get("/{site}/prospects")
def prospects_list(site: str, status: Optional[str] = None, sector: Optional[str] = None,
                   limit: int = 500, user=Depends(require_admin)):
    _check_site(site)
    return {"prospects": gm.list_prospects(site, status=status, sector=sector, limit=min(limit, 2000))}


@router.post("/{site}/prospects/{prospect_id}/status")
async def prospect_set_status(site: str, prospect_id: str, request: Request, user=Depends(require_admin)):
    _check_site(site)
    body = await request.json()
    status = body.get("status")
    reason = body.get("reason")
    if status not in ("validated", "sent"):
        raise HTTPException(status_code=400, detail="status invalide (validated|sent)")
    gm.update_prospect_status(prospect_id, status, reason)
    gm.log_action(site, user["username"], user["user_id"], "update_prospect_status",
                  resource="prospect", resource_id=prospect_id, payload={"status": status, "reason": reason}, ip=_ip(request))
    return {"ok": True}


# ── Templates ─────────────────────────────────────────────────────────────────
@router.get("/{site}/templates")
def templates_list(site: str, user=Depends(require_admin)):
    _check_site(site)
    state = gm.get_state(site)
    settings = gm.get_settings(site)
    return {
        "site": site,
        "sectors": gm.SECTORS_GOD_MODE,
        "templates": gm.list_templates(site),
        "state": state,
        "settings": settings,
    }


@router.get("/{site}/templates/{sector}")
def template_get(site: str, sector: str, user=Depends(require_admin)):
    _check_site(site)
    if sector not in gm.SECTORS_GOD_MODE:
        raise HTTPException(status_code=400, detail=f"Secteur invalide: {sector}")
    t = gm.get_template(site, sector)
    if not t:
        return {"site_code": site, "sector": sector, "raw_content": None, "html_content": None, "locked": False, "exists": False}
    return {**t, "exists": True}


@router.post("/{site}/templates/{sector}/generate")
async def template_generate(site: str, sector: str, request: Request, user=Depends(require_admin)):
    _check_site(site)
    if sector not in gm.SECTORS_GOD_MODE:
        raise HTTPException(status_code=400, detail=f"Secteur invalide: {sector}")
    import god_mode_templates as gm_tpl
    try:
        t = gm_tpl.generate_template(site, sector, user["username"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DeepSeek error: {e}")
    gm.log_action(site, user["username"], user["user_id"], "generate_template",
                  resource="template", resource_id=f"{site}/{sector}", ip=_ip(request))
    return t


@router.put("/{site}/templates/{sector}/html")
async def template_update_html(site: str, sector: str, request: Request, user=Depends(require_admin)):
    _check_site(site)
    if sector not in gm.SECTORS_GOD_MODE:
        raise HTTPException(status_code=400, detail=f"Secteur invalide: {sector}")
    body = await request.json()
    html = body.get("html_content", "")
    try:
        gm.update_template_html(site, sector, html, user["username"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    gm.log_action(site, user["username"], user["user_id"], "update_template_html",
                  resource="template", resource_id=f"{site}/{sector}",
                  payload={"chars": len(html)}, ip=_ip(request))
    return gm.get_template(site, sector)


@router.put("/{site}/templates/{sector}/subject")
async def template_update_subject(site: str, sector: str, request: Request, user=Depends(require_admin)):
    _check_site(site)
    if sector not in gm.SECTORS_GOD_MODE:
        raise HTTPException(status_code=400, detail=f"Secteur invalide: {sector}")
    body = await request.json()
    subject = (body.get("subject") or "").strip()
    if not subject:
        raise HTTPException(status_code=400, detail="subject vide")
    try:
        gm.update_template_subject(site, sector, subject, user["username"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    gm.log_action(site, user["username"], user["user_id"], "update_template_subject",
                  resource="template", resource_id=f"{site}/{sector}",
                  payload={"subject": subject}, ip=_ip(request))
    return gm.get_template(site, sector)


@router.post("/{site}/templates/{sector}/lock")
async def template_lock(site: str, sector: str, request: Request, user=Depends(require_admin)):
    _check_site(site)
    if sector not in gm.SECTORS_GOD_MODE:
        raise HTTPException(status_code=400, detail=f"Secteur invalide: {sector}")
    t = gm.get_template(site, sector)
    if not t:
        raise HTTPException(status_code=404, detail="Template inexistant — générer avant de verrouiller")
    gm.lock_template(site, sector, user["username"])
    gm.log_action(site, user["username"], user["user_id"], "lock_template",
                  resource="template", resource_id=f"{site}/{sector}", ip=_ip(request))
    return gm.get_template(site, sector)


@router.post("/{site}/templates/{sector}/unlock")
async def template_unlock(site: str, sector: str, request: Request, user=Depends(require_admin)):
    _check_site(site)
    if sector not in gm.SECTORS_GOD_MODE:
        raise HTTPException(status_code=400, detail=f"Secteur invalide: {sector}")
    gm.unlock_template(site, sector, user["username"])
    gm.log_action(site, user["username"], user["user_id"], "unlock_template",
                  resource="template", resource_id=f"{site}/{sector}", ip=_ip(request))
    return gm.get_template(site, sector)


# ── Stats ─────────────────────────────────────────────────────────────────────
@router.get("/{site}/serper/credits")
def serper_credits(site: str, user=Depends(require_admin)):
    _check_site(site)
    import god_mode_agents as gm_agents
    bal = gm_agents.serper_balance()
    usage_site = gm.serper_usage(site_code=site)
    usage_global = gm.serper_usage()
    return {"balance": bal, "usage_site": usage_site, "usage_global": usage_global}


@router.get("/{site}/stats/timeseries")
def stats_timeseries(site: str, date_from: Optional[str] = None, date_to: Optional[str] = None, user=Depends(require_admin)):
    _check_site(site)
    from datetime import date as d, timedelta
    today = d.today()
    df = d.fromisoformat(date_from) if date_from else (today - timedelta(days=30))
    dt = d.fromisoformat(date_to) if date_to else today
    if df > dt:
        df, dt = dt, df
    return {"site": site, "from": str(df), "to": str(dt), "series": gm.stats_timeseries(site, df, dt)}


@router.get("/{site}/stats")
def stats(site: str, user=Depends(require_admin)):
    _check_site(site)
    return gm.stats(site)


# ── Scraping ──────────────────────────────────────────────────────────────────
import threading
import god_mode_agents as gm_agents


@router.post("/{site}/scrape")
async def scrape(site: str, request: Request, user=Depends(require_admin)):
    _check_site(site)
    state = gm.get_state(site)
    if not state or not state.get("enabled"):
        raise HTTPException(status_code=400, detail="GOD MODE désactivé pour ce site")
    settings = gm.get_settings(site)
    body = await request.json()
    sector = body.get("sector")
    cities = body.get("cities")
    if sector not in gm.SECTORS_GOD_MODE:
        raise HTTPException(status_code=400, detail=f"Secteur invalide: {sector}")
    max_results = min(int(body.get("max_results", settings["scrape_quota"])), settings["scrape_quota"])

    gm.log_action(site, user["username"], user["user_id"], "start_scrape",
                  resource="sector", resource_id=sector,
                  payload={"sector": sector, "cities": cities, "max_results": max_results}, ip=_ip(request))

    captured_user = {"username": user["username"], "user_id": user["user_id"]}

    def run():
        try:
            gm_agents.scrape_sector(site, sector, cities=cities, max_results=max_results, username=captured_user["username"])
        except Exception as e:
            gm.log_action(site, captured_user["username"], captured_user["user_id"], "scrape_error",
                          resource="sector", resource_id=sector, payload={"error": str(e)}, success=False, error=str(e))

    threading.Thread(target=run, daemon=True).start()
    return {"started": True, "site": site, "sector": sector, "max_results": max_results}


# ── Campaigns ─────────────────────────────────────────────────────────────────
import god_mode_scheduler as gm_sched


@router.post("/{site}/campaigns/validate")
async def campaign_validate(site: str, request: Request, user=Depends(require_admin)):
    _check_site(site)
    body = await request.json()
    sector = body.get("sector")
    date_str = body.get("date")
    if not sector or not date_str:
        raise HTTPException(status_code=400, detail="sector et date requis")
    from datetime import date as d
    return gm_sched.validate_schedule(site, sector, d.fromisoformat(date_str), body.get("prospect_count"))


@router.post("/{site}/campaigns/schedule")
async def campaign_schedule(site: str, request: Request, user=Depends(require_admin)):
    _check_site(site)
    body = await request.json()
    sector = body.get("sector")
    date_str = body.get("date")
    if not sector or not date_str:
        raise HTTPException(status_code=400, detail="sector et date requis")
    from datetime import date as d
    try:
        result = gm_sched.schedule_campaign(site, sector, d.fromisoformat(date_str), user["username"], body.get("prospect_count"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    gm.log_action(site, user["username"], user["user_id"], "schedule_campaign",
                  resource="campaign", resource_id=result["campaign_id"],
                  payload={"sector": sector, "date": date_str, "prospect_count": result["prospect_count"]}, ip=_ip(request))
    return result


@router.get("/{site}/campaigns")
def campaigns_list(site: str, user=Depends(require_admin)):
    _check_site(site)
    return {"campaigns": gm.list_campaigns(site)}


# ── Géographie (régions / départements / villes) ─────────────────────────────
import workflow_geo


@router.get("/geo/regions")
def geo_regions(user=Depends(require_admin)):
    return {"regions": workflow_geo.list_regions()}


@router.get("/geo/departments")
def geo_departments(region: Optional[str] = None, user=Depends(require_admin)):
    return {"departments": workflow_geo.list_departments(region_code=region)}


@router.get("/geo/cities")
def geo_cities(
    dept: Optional[str] = None,
    region: Optional[str] = None,
    min_pop: int = 10000,
    user=Depends(require_admin),
):
    cities = workflow_geo.list_cities(dept_code=dept, region_code=region, min_pop=min_pop)
    return {"cities": cities, "count": len(cities)}


# ── Performance Workflow (chaîne complète par secteur et par ville) ───────────
from pathlib import Path
import duckdb as _duckdb
import requests as _req
import os as _os
from datetime import date as _date

_GOD_DB = Path(__file__).parent.parent / "data" / "god_mode.duckdb"
_CRM_DIR = Path(__file__).parent.parent / "data" / "crm"


def _emelia_key(site: str) -> str | None:
    k = _os.environ.get(f"EMELIA_API_KEY_{site.upper()}", "").strip()
    if k:
        return k
    return (_os.environ.get("EMELIA_API_KEY", "").strip()) or None


@router.get("/{site}/performance")
def performance(
    site: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user=Depends(require_admin),
):
    """Agrégats Workflow par secteur et par ville.

    Source de vérité : `acquisition_contacts` (table principale du pipeline).
    Pour les volumes scrape/qualifier en amont, on enrichit via la table `scrappe`.

    Funnel par secteur : scraped → qualified → sent → opened → clicked → replied → leads
                         + bounced + unsubscribed (déchets sortants du pipeline).
    """
    _check_site(site)

    # ───── 1) Côté scrappe (volumes amont : scraped, qualified) ─────
    s_where = ["site_code = ?"]
    s_params: list = [site]
    if date_from:
        s_where.append("created_at >= ?")
        s_params.append(date_from)
    if date_to:
        s_where.append("created_at < ?")
        s_params.append(date_to + " 23:59:59")
    s_wsql = " AND ".join(s_where)

    c = _duckdb.connect(str(_GOD_DB), read_only=True)
    try:
        scrape_by_sector = {
            row[0]: {"scraped": row[1], "qualified": row[2]}
            for row in c.execute(f"""
                SELECT sector,
                       count(*) AS scraped,
                       count(*) FILTER (WHERE qualifier_buyer = TRUE) AS qualified
                FROM scrappe WHERE {s_wsql} AND sector IS NOT NULL
                GROUP BY sector
            """, s_params).fetchall()
        }
        scrape_by_city = {
            (row[0], row[1] or ""): {"scraped": row[2], "qualified": row[3]}
            for row in c.execute(f"""
                SELECT city, dept_code,
                       count(*) AS scraped,
                       count(*) FILTER (WHERE qualifier_buyer = TRUE) AS qualified
                FROM scrappe WHERE {s_wsql} AND city IS NOT NULL
                GROUP BY city, dept_code
            """, s_params).fetchall()
        }
    finally:
        c.close()

    # ───── 2) Côté acquisition_contacts (vraies stats de delivery email) ─────
    acq_db = _CRM_DIR / f"{site}.duckdb"
    by_sector_acq: dict[str, dict] = {}
    by_city_acq: dict[tuple, dict] = {}
    if acq_db.exists():
        a_where = ["sector IS NOT NULL"]
        a_params: list = []
        if date_from:
            a_where.append("created_at >= ?")
            a_params.append(date_from)
        if date_to:
            a_where.append("created_at < ?")
            a_params.append(date_to + " 23:59:59")
        a_wsql = " AND ".join(a_where)

        ac = _duckdb.connect(str(acq_db), read_only=True)
        try:
            for row in ac.execute(f"""
                SELECT
                  sector,
                  count(*) FILTER (WHERE email_sent_at IS NOT NULL)           AS sent,
                  count(*) FILTER (WHERE emelia_opened_at IS NOT NULL)        AS opened,
                  count(*) FILTER (WHERE emelia_clicked_at IS NOT NULL)       AS clicked,
                  count(*) FILTER (WHERE emelia_replied_at IS NOT NULL)       AS replied,
                  count(*) FILTER (WHERE emelia_bounced_at IS NOT NULL)       AS bounced,
                  count(*) FILTER (WHERE emelia_unsubscribed_at IS NOT NULL)  AS unsubscribed,
                  count(*) FILTER (WHERE state = 'prm')                       AS prm,
                  count(*) FILTER (WHERE state = 'lead')                      AS lead,
                  count(*) FILTER (WHERE state = 'crm')                       AS crm,
                  count(*) FILTER (WHERE state = 'blacklisted')               AS blacklisted
                FROM acquisition_contacts WHERE {a_wsql}
                GROUP BY sector
            """, a_params).fetchall():
                (sec, sent, opened, clicked, replied, bounced, unsubscribed,
                 prm, lead, crm_, black) = row
                by_sector_acq[sec] = {
                    "sent": sent, "opened": opened, "clicked": clicked,
                    "replied": replied, "bounced": bounced, "unsubscribed": unsubscribed,
                    "prm": prm, "lead": lead, "crm": crm_, "blacklisted": black,
                }
            # Par ville depuis acquisition (besoin notes city — on stocke pas la city dans acq table direct)
            # → on déduit la city via scrappe en joignant sur email
            for row in ac.execute("""
                SELECT
                  s.city, s.dept_code,
                  count(*) FILTER (WHERE a.email_sent_at IS NOT NULL)         AS sent,
                  count(*) FILTER (WHERE a.emelia_clicked_at IS NOT NULL)     AS clicked,
                  count(*) FILTER (WHERE a.emelia_replied_at IS NOT NULL)     AS replied,
                  count(*) FILTER (WHERE a.state = 'lead')                    AS lead
                FROM acquisition_contacts a
                JOIN read_parquet('') p ON 1=0  -- placeholder, on remplace ci-dessous
                GROUP BY s.city, s.dept_code
            """ if False else "SELECT 1", []).fetchall():
                pass  # On laisse vide ici ; le join cross-DB est fait juste après plus simplement
        finally:
            ac.close()

        # Join cross-DB simplifié : on récupère les emails sent par ville depuis scrappe (qui a city),
        # puis on hydrate via acquisition_contacts par email pour les statuts.
        scs = _duckdb.connect(str(_GOD_DB), read_only=True)
        try:
            rows = scs.execute(f"""
                SELECT city, dept_code, email FROM scrappe
                WHERE {s_wsql} AND city IS NOT NULL AND email IS NOT NULL
            """, s_params).fetchall()
        finally:
            scs.close()
        by_email_city: dict[str, tuple] = {}
        for city, dept, email in rows:
            by_email_city[email.lower()] = (city, dept or "")

        ac = _duckdb.connect(str(acq_db), read_only=True)
        try:
            for row in ac.execute(f"""
                SELECT email, email_sent_at, emelia_clicked_at, emelia_replied_at, state
                FROM acquisition_contacts WHERE {a_wsql}
            """, a_params).fetchall():
                em, sent_at, clk_at, rep_at, state = row
                key = by_email_city.get((em or "").lower())
                if not key:
                    continue
                d = by_city_acq.setdefault(key, {"sent": 0, "clicked": 0, "replied": 0, "lead": 0})
                if sent_at: d["sent"] += 1
                if clk_at:  d["clicked"] += 1
                if rep_at:  d["replied"] += 1
                if state == "lead": d["lead"] += 1
        finally:
            ac.close()

    # ───── 3) Merge by_sector ─────
    sectors = set(scrape_by_sector.keys()) | set(by_sector_acq.keys())
    by_sector = []
    for sec in sorted(sectors, key=lambda s: -scrape_by_sector.get(s, {}).get("scraped", 0)):
        s_data = scrape_by_sector.get(sec, {})
        a_data = by_sector_acq.get(sec, {})
        by_sector.append({
            "sector":       sec,
            "scraped":      s_data.get("scraped", 0),
            "qualified":    s_data.get("qualified", 0),
            "sent":         a_data.get("sent", 0),
            "opened":       a_data.get("opened", 0),
            "clicked":      a_data.get("clicked", 0),
            "replied":      a_data.get("replied", 0),
            "leads":        a_data.get("lead", 0),
            "prm":          a_data.get("prm", 0),
            "bounced":      a_data.get("bounced", 0),
            "unsubscribed": a_data.get("unsubscribed", 0),
        })

    # ───── 4) Merge by_city (top 10) ─────
    cities = set(scrape_by_city.keys()) | set(by_city_acq.keys())
    by_city_list = []
    for (city, dept) in cities:
        s_data = scrape_by_city.get((city, dept), {})
        a_data = by_city_acq.get((city, dept), {})
        by_city_list.append({
            "city":      city,
            "dept":      dept,
            "scraped":   s_data.get("scraped", 0),
            "qualified": s_data.get("qualified", 0),
            "sent":      a_data.get("sent", 0),
            "clicked":   a_data.get("clicked", 0),
            "replied":   a_data.get("replied", 0),
            "leads":     a_data.get("lead", 0),
        })
    by_city_list.sort(key=lambda r: -r["scraped"])
    by_city_list = by_city_list[:10]

    # ───── 5) Totaux ─────
    keys_sec = ("scraped","qualified","sent","opened","clicked","replied","leads","prm","bounced","unsubscribed")
    totals = {k: sum(r[k] for r in by_sector) for k in keys_sec}

    return {
        "site": site,
        "date_from": date_from,
        "date_to": date_to,
        "totals": totals,
        "by_sector": by_sector,
        "by_city": by_city_list,
    }


# ── Run manuel du workflow_runner sur un département ─────────────────────────
@router.post("/{site}/workflow-run")
async def workflow_run(site: str, request: Request, user=Depends(require_admin)):
    """Lance workflow_runner en background sur un département choisi.
    Body: {"dept": "75", "scrape_quota": 12, "dry_run": false}
    """
    _check_site(site)
    state = gm.get_state(site)
    if not state or not state.get("enabled"):
        raise HTTPException(status_code=400, detail="Workflow désactivé pour ce site")
    body = await request.json()
    dept_code = body.get("dept")
    scrape_quota = int(body.get("scrape_quota", 30))
    daily_limit = int(body.get("daily_limit", 50))
    dry_run = bool(body.get("dry_run", False))

    gm.log_action(site, user["username"], user["user_id"], "workflow_run_manual",
                  resource="dept", resource_id=dept_code,
                  payload={"dept": dept_code, "scrape_quota": scrape_quota, "dry_run": dry_run},
                  ip=_ip(request))

    import threading
    import workflow_runner

    def _run():
        try:
            workflow_runner.run_site(site, forced_dept=dept_code,
                                     scrape_quota=scrape_quota,
                                     daily_emelia_limit=daily_limit,
                                     dry_run=dry_run)
        except Exception as e:
            gm.log_action(site, user["username"], user["user_id"], "workflow_run_error",
                          payload={"dept": dept_code, "error": str(e)}, success=False, error=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True, "site": site, "dept": dept_code,
            "scrape_quota": scrape_quota, "dry_run": dry_run}


# ── Sectors meta ──────────────────────────────────────────────────────────────
@router.get("/meta/sectors")
def meta_sectors(user=Depends(require_admin)):
    return {"sectors": gm.SECTORS_GOD_MODE, "cities_top50": gm.TOP_50_INSEE}
