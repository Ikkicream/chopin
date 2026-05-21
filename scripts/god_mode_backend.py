#!/usr/bin/env python3
"""
god_mode_backend.py — Helpers DB pour la feature GOD MODE.

Tables (data/god_mode.duckdb):
  god_mode_state, god_mode_settings, god_mode_logs,
  scrappe, god_mode_campaigns, god_mode_templates
"""

import json
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"
AUTH_DB = BASE_DIR / "data" / "auth.duckdb"
TEMPLATES_DIR = BASE_DIR / "memory" / "templates"
SKILLS_DIR = BASE_DIR / "skills"

VALID_SITES = {"lcr", "mkd"}
SECTORS_GOD_MODE = ["immobilier", "restaurant", "garagiste", "coiffeur", "retail", "artisan"]

# Top 50 INSEE communes par population (2025)
TOP_50_INSEE = [
    "Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Nantes", "Montpellier",
    "Strasbourg", "Bordeaux", "Lille", "Rennes", "Reims", "Le Havre", "Saint-Étienne",
    "Toulon", "Grenoble", "Dijon", "Angers", "Nîmes", "Villeurbanne", "Saint-Denis",
    "Aix-en-Provence", "Clermont-Ferrand", "Le Mans", "Brest", "Tours", "Amiens",
    "Limoges", "Annecy", "Boulogne-Billancourt", "Perpignan", "Metz", "Besançon",
    "Orléans", "Rouen", "Argenteuil", "Mulhouse", "Montreuil", "Caen", "Nancy",
    "Saint-Paul", "Tourcoing", "Roubaix", "Nanterre", "Vitry-sur-Seine", "Avignon",
    "Créteil", "Dunkerque", "Poitiers", "Asnières-sur-Seine"
]


# ── Connexions ────────────────────────────────────────────────────────────────
def _conn():
    return duckdb.connect(str(GOD_DB))


def _auth():
    return duckdb.connect(str(AUTH_DB), read_only=True)


# ── Auth admin ────────────────────────────────────────────────────────────────
def verify_admin(token: str | None):
    """Retourne dict user si role=admin, sinon None."""
    if not token:
        return None
    c = _auth()
    try:
        row = c.execute("""
            SELECT s.user_id, u.username, u.role, u.nom, u.prenom
            FROM sessions s JOIN users u ON s.user_id = u.id
            WHERE s.token = ? AND s.expires_at > ?
        """, [token, datetime.now(timezone.utc).isoformat()]).fetchone()
    finally:
        c.close()
    if not row:
        return None
    if row[2] not in ("admin", "superadmin"):
        return None
    return {"user_id": row[0], "username": row[1], "role": row[2], "nom": row[3], "prenom": row[4]}


# ── State ─────────────────────────────────────────────────────────────────────
def get_state(site_code: str):
    c = _conn()
    try:
        row = c.execute("SELECT site_code, enabled, enabled_by, enabled_at, disabled_at, updated_at FROM god_mode_state WHERE site_code=?", [site_code]).fetchone()
    finally:
        c.close()
    if not row:
        return None
    return {"site_code": row[0], "enabled": row[1], "enabled_by": row[2], "enabled_at": str(row[3]) if row[3] else None, "disabled_at": str(row[4]) if row[4] else None, "updated_at": str(row[5]) if row[5] else None}


def set_state(site_code: str, enabled: bool, username: str):
    now = datetime.now(timezone.utc)
    c = _conn()
    try:
        if enabled:
            c.execute("UPDATE god_mode_state SET enabled=TRUE, enabled_by=?, enabled_at=?, updated_at=? WHERE site_code=?", [username, now, now, site_code])
        else:
            c.execute("UPDATE god_mode_state SET enabled=FALSE, disabled_at=?, updated_at=? WHERE site_code=?", [now, now, site_code])
    finally:
        c.close()


# ── Settings ──────────────────────────────────────────────────────────────────
def get_settings(site_code: str):
    c = _conn()
    try:
        row = c.execute("SELECT site_code, daily_quota, scrape_quota, serper_provider, last_modified_by, last_modified_at FROM god_mode_settings WHERE site_code=?", [site_code]).fetchone()
    finally:
        c.close()
    if not row:
        return None
    return {"site_code": row[0], "daily_quota": row[1], "scrape_quota": row[2], "provider": row[3], "last_modified_by": row[4], "last_modified_at": str(row[5]) if row[5] else None}


def update_settings(site_code: str, daily_quota: int, scrape_quota: int, username: str):
    c = _conn()
    try:
        c.execute("UPDATE god_mode_settings SET daily_quota=?, scrape_quota=?, last_modified_by=?, last_modified_at=? WHERE site_code=?",
                  [daily_quota, scrape_quota, username, datetime.now(timezone.utc), site_code])
    finally:
        c.close()


# ── Logs ──────────────────────────────────────────────────────────────────────
def log_action(site_code: str, username: str, user_id: str, action: str, resource: str = None,
               resource_id: str = None, ip: str = None, payload: dict = None,
               success: bool = True, error: str = None):
    log_id = str(uuid.uuid4())
    c = _conn()
    try:
        c.execute("""INSERT INTO god_mode_logs (id, site_code, user_id, username, action, resource, resource_id, ip, payload, success, error_message)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  [log_id, site_code, user_id, username, action, resource, resource_id, ip,
                   json.dumps(payload) if payload else None, success, error])
    finally:
        c.close()
    return log_id


def list_logs(site_code: str = None, limit: int = 200):
    c = _conn()
    try:
        if site_code:
            rows = c.execute("SELECT id, site_code, username, action, resource, resource_id, ip, payload, success, error_message, created_at FROM god_mode_logs WHERE site_code=? ORDER BY created_at DESC LIMIT ?", [site_code, limit]).fetchall()
        else:
            rows = c.execute("SELECT id, site_code, username, action, resource, resource_id, ip, payload, success, error_message, created_at FROM god_mode_logs ORDER BY created_at DESC LIMIT ?", [limit]).fetchall()
    finally:
        c.close()
    return [{"id": r[0], "site_code": r[1], "username": r[2], "action": r[3], "resource": r[4], "resource_id": r[5], "ip": r[6], "payload": json.loads(r[7]) if r[7] else None, "success": r[8], "error": r[9], "created_at": str(r[10])} for r in rows]


# ── Validation contact ────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
PHONE_FR_RE = re.compile(r"^0[67](?:[ .-]?\d{2}){4}$")


def validate_email(email: str) -> bool:
    if not email:
        return False
    return bool(EMAIL_RE.match(email.strip()))


def validate_phone_fr(phone: str) -> bool:
    if not phone:
        return False
    return bool(PHONE_FR_RE.match(phone.strip()))


# ── Prospects (table scrappe) ─────────────────────────────────────────────────
def add_prospect(site_code: str, data: dict) -> str:
    pid = str(uuid.uuid4())
    c = _conn()
    try:
        c.execute("""INSERT INTO scrappe (id, site_code, company_name, contact_name, email, phone, sector, city, postal_code, website, source, search_query, score, status, raw_data)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  [pid, site_code, data.get("company_name"), data.get("contact_name"), data.get("email"),
                   data.get("phone"), data.get("sector"), data.get("city"), data.get("postal_code"),
                   data.get("website"), data.get("source"), data.get("search_query"),
                   data.get("score", 0), data.get("status", "new"),
                   json.dumps(data.get("raw_data", {}))])
    finally:
        c.close()
    return pid


def list_prospects(site_code: str, status: str = None, sector: str = None, limit: int = 500):
    c = _conn()
    try:
        q = "SELECT id, site_code, company_name, contact_name, email, phone, sector, city, postal_code, website, source, score, status, created_at, contacted_at, rejection_reason FROM scrappe WHERE site_code=?"
        params = [site_code]
        if status:
            q += " AND status=?"; params.append(status)
        if sector:
            q += " AND sector=?"; params.append(sector)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        rows = c.execute(q, params).fetchall()
    finally:
        c.close()
    return [{"id": r[0], "site_code": r[1], "company_name": r[2], "contact_name": r[3], "email": r[4], "phone": r[5], "sector": r[6], "city": r[7], "postal_code": r[8], "website": r[9], "source": r[10], "score": r[11], "status": r[12], "created_at": str(r[13]), "contacted_at": str(r[14]) if r[14] else None, "rejection_reason": r[15]} for r in rows]


def update_prospect_status(prospect_id: str, status: str, reason: str = None):
    c = _conn()
    try:
        if status == "contacted":
            c.execute("UPDATE scrappe SET status=?, contacted_at=? WHERE id=?", [status, datetime.now(timezone.utc), prospect_id])
        elif status == "validated":
            c.execute("UPDATE scrappe SET status=?, validated_at=? WHERE id=?", [status, datetime.now(timezone.utc), prospect_id])
        else:
            c.execute("UPDATE scrappe SET status=?, rejection_reason=? WHERE id=?", [status, reason, prospect_id])
    finally:
        c.close()


# ── Context check ────────────────────────────────────────────────────────────
def context_check(site_code: str) -> dict:
    """Vérifie présence fichiers contexte pour un site (skills/{site}/)."""
    site_dir = SKILLS_DIR / site_code
    expected = ["competitive-intel.md", "content-writer.md", "editorial-manager.md", "seo-strategist.md"]
    if not site_dir.exists():
        return {"site": site_code, "exists": False, "missing": expected, "files": []}
    files = sorted([f.name for f in site_dir.glob("*.md")])
    missing = [f for f in expected if f not in files]
    return {"site": site_code, "exists": True, "files": files, "missing": missing, "ready": len(missing) == 0}


# ── Templates ─────────────────────────────────────────────────────────────────
def get_template(site_code: str, sector: str):
    c = _conn()
    try:
        row = c.execute("SELECT id, site_code, sector, subject, raw_content, html_content, locked, locked_by, locked_at, generated_by, generated_at FROM god_mode_templates WHERE site_code=? AND sector=?", [site_code, sector]).fetchone()
    finally:
        c.close()
    if not row:
        return None
    return {"id": row[0], "site_code": row[1], "sector": row[2], "subject": row[3], "raw_content": row[4], "html_content": row[5], "locked": row[6], "locked_by": row[7], "locked_at": str(row[8]) if row[8] else None, "generated_by": row[9], "generated_at": str(row[10]) if row[10] else None}


def list_templates(site_code: str):
    return [t for t in (get_template(site_code, s) for s in SECTORS_GOD_MODE) if t]


def save_template(site_code: str, sector: str, subject: str, raw_content: str, html_content: str, username: str):
    """Crée ou écrase un template. Bloque si locked=True."""
    existing = get_template(site_code, sector)
    if existing and existing["locked"]:
        raise ValueError(f"Template {site_code}/{sector} verrouillé — déverrouiller avant de régénérer")
    tid = existing["id"] if existing else str(uuid.uuid4())
    c = _conn()
    try:
        if existing:
            c.execute("UPDATE god_mode_templates SET subject=?, raw_content=?, html_content=?, generated_by=?, generated_at=? WHERE id=?",
                      [subject, raw_content, html_content, username, datetime.now(timezone.utc), tid])
        else:
            c.execute("""INSERT INTO god_mode_templates (id, site_code, sector, subject, raw_content, html_content, locked, generated_by)
                         VALUES (?, ?, ?, ?, ?, ?, FALSE, ?)""",
                      [tid, site_code, sector, subject, raw_content, html_content, username])
    finally:
        c.close()
    # Écrit aussi sur disque
    out_dir = TEMPLATES_DIR / site_code
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{sector}.html").write_text(html_content, encoding="utf-8")
    (out_dir / f"{sector}.txt").write_text(raw_content, encoding="utf-8")
    return tid


def _html_to_text(html: str) -> str:
    """Convertit HTML en texte brut (retire signature, normalise br/p)."""
    if not html:
        return ""
    cleaned = re.sub(r"<p>\s*<img[^>]*emelia-public-files[^>]*>\s*</p>", "", html, flags=re.I)
    cleaned = re.sub(r"<p>\s*<a[^>]*UNSUBSCRIBE_LINK[^>]*>.*?</a>\s*</p>", "", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"</p>\s*<p>", "\n\n", cleaned, flags=re.I)
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.I)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def update_template_html(site_code: str, sector: str, html_content: str, username: str):
    """Met à jour le html_content + régénère raw_content depuis le HTML. Bloque si locked."""
    existing = get_template(site_code, sector)
    if not existing:
        raise ValueError(f"Template {site_code}/{sector} introuvable")
    if existing["locked"]:
        raise ValueError(f"Template {site_code}/{sector} verrouillé")
    body_text = _html_to_text(html_content)
    subject = existing.get("subject") or ""
    raw_full = f"SUBJECT: {subject}\n\n{body_text}"
    c = _conn()
    try:
        c.execute("UPDATE god_mode_templates SET html_content=?, raw_content=? WHERE site_code=? AND sector=?",
                  [html_content, raw_full, site_code, sector])
    finally:
        c.close()
    out_dir = TEMPLATES_DIR / site_code
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{sector}.html").write_text(html_content, encoding="utf-8")
    (out_dir / f"{sector}.txt").write_text(raw_full, encoding="utf-8")


def lock_template(site_code: str, sector: str, username: str):
    c = _conn()
    try:
        c.execute("UPDATE god_mode_templates SET locked=TRUE, locked_by=?, locked_at=? WHERE site_code=? AND sector=?",
                  [username, datetime.now(timezone.utc), site_code, sector])
    finally:
        c.close()


def unlock_template(site_code: str, sector: str, username: str):
    c = _conn()
    try:
        c.execute("UPDATE god_mode_templates SET locked=FALSE WHERE site_code=? AND sector=?", [site_code, sector])
    finally:
        c.close()


# ── Campagnes ─────────────────────────────────────────────────────────────────
def get_today_campaign(site_code: str, day: date = None) -> dict | None:
    day = day or date.today()
    c = _conn()
    try:
        row = c.execute("SELECT id, site_code, sector, scheduled_date, status, prospect_count, sent_count FROM god_mode_campaigns WHERE site_code=? AND scheduled_date=? LIMIT 1", [site_code, day]).fetchone()
    finally:
        c.close()
    if not row:
        return None
    return {"id": row[0], "site_code": row[1], "sector": row[2], "scheduled_date": str(row[3]), "status": row[4], "prospect_count": row[5], "sent_count": row[6]}


def create_campaign(site_code: str, sector: str, scheduled_date: date, prospect_count: int, template_id: str, emelia_campaign_id: str, username: str) -> str:
    cid = str(uuid.uuid4())
    c = _conn()
    try:
        c.execute("""INSERT INTO god_mode_campaigns (id, site_code, sector, scheduled_date, emelia_campaign_id, status, prospect_count, template_id, created_by)
                     VALUES (?, ?, ?, ?, ?, 'scheduled', ?, ?, ?)""",
                  [cid, site_code, sector, scheduled_date, emelia_campaign_id, prospect_count, template_id, username])
    finally:
        c.close()
    return cid


def list_campaigns(site_code: str, limit: int = 100):
    c = _conn()
    try:
        rows = c.execute("SELECT id, site_code, sector, scheduled_date, emelia_campaign_id, status, prospect_count, sent_count, created_by, created_at FROM god_mode_campaigns WHERE site_code=? ORDER BY scheduled_date DESC LIMIT ?", [site_code, limit]).fetchall()
    finally:
        c.close()
    return [{"id": r[0], "site_code": r[1], "sector": r[2], "scheduled_date": str(r[3]), "emelia_campaign_id": r[4], "status": r[5], "prospect_count": r[6], "sent_count": r[7], "created_by": r[8], "created_at": str(r[9])} for r in rows]


# ── Serper credits tracking ───────────────────────────────────────────────────
def log_serper_call(site_code: str, endpoint: str, query: str, credits: int = 1, success: bool = True):
    cid = str(uuid.uuid4())
    c = _conn()
    try:
        c.execute("INSERT INTO god_mode_serper_calls (id, site_code, endpoint, query, credits, success) VALUES (?, ?, ?, ?, ?, ?)",
                  [cid, site_code, endpoint, query[:200] if query else None, credits, success])
    finally:
        c.close()


def serper_usage(site_code: str = None) -> dict:
    """Retourne credits used today/month/year/total. Filtre site_code si fourni."""
    today = date.today()
    first_of_month = today.replace(day=1)
    first_of_year = today.replace(month=1, day=1)
    c = _conn()
    try:
        site_clause = "WHERE site_code=?" if site_code else ""
        params = [site_code] if site_code else []
        used_today = c.execute(f"SELECT COALESCE(SUM(credits),0) FROM god_mode_serper_calls {site_clause} {'AND' if site_clause else 'WHERE'} CAST(created_at AS DATE)=?", params + [today]).fetchone()[0]
        used_month = c.execute(f"SELECT COALESCE(SUM(credits),0) FROM god_mode_serper_calls {site_clause} {'AND' if site_clause else 'WHERE'} CAST(created_at AS DATE)>=?", params + [first_of_month]).fetchone()[0]
        used_year = c.execute(f"SELECT COALESCE(SUM(credits),0) FROM god_mode_serper_calls {site_clause} {'AND' if site_clause else 'WHERE'} CAST(created_at AS DATE)>=?", params + [first_of_year]).fetchone()[0]
        used_total = c.execute(f"SELECT COALESCE(SUM(credits),0) FROM god_mode_serper_calls {site_clause}", params).fetchone()[0]
        calls_total = c.execute(f"SELECT COUNT(*) FROM god_mode_serper_calls {site_clause}", params).fetchone()[0]
    finally:
        c.close()
    return {"used_today": int(used_today), "used_month": int(used_month), "used_year": int(used_year), "used_total": int(used_total), "calls_total": int(calls_total)}


# ── Stats ─────────────────────────────────────────────────────────────────────
def stats(site_code: str) -> dict:
    today = date.today()
    first_of_month = today.replace(day=1)
    first_of_year = today.replace(month=1, day=1)
    c = _conn()
    try:
        # Scraped (= total prospects en table, statut validated ou sent)
        scraped_today = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND CAST(created_at AS DATE)=?", [site_code, today]).fetchone()[0]
        scraped_month = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND CAST(created_at AS DATE)>=?", [site_code, first_of_month]).fetchone()[0]
        scraped_year = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND CAST(created_at AS DATE)>=?", [site_code, first_of_year]).fetchone()[0]
        scraped_total = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=?", [site_code]).fetchone()[0]
        # Sent (status='sent' = email envoyé via Emelia)
        sent_today = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND status='sent' AND CAST(contacted_at AS DATE)=?", [site_code, today]).fetchone()[0]
        sent_month = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND status='sent' AND CAST(contacted_at AS DATE)>=?", [site_code, first_of_month]).fetchone()[0]
        sent_year = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND status='sent' AND CAST(contacted_at AS DATE)>=?", [site_code, first_of_year]).fetchone()[0]
        sent_total = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND status='sent'", [site_code]).fetchone()[0]
        camp_today = c.execute("SELECT COUNT(*) FROM god_mode_campaigns WHERE site_code=? AND scheduled_date=?", [site_code, today]).fetchone()[0]
    finally:
        c.close()
    def ratio(num, den):
        return round(num / den * 100, 1) if den else 0.0
    return {
        "scraped_today": scraped_today, "scraped_month": scraped_month, "scraped_year": scraped_year, "scraped_total": scraped_total,
        "sent_today": sent_today, "sent_month": sent_month, "sent_year": sent_year, "sent_total": sent_total,
        "ratio_today": ratio(sent_today, scraped_today),
        "ratio_month": ratio(sent_month, scraped_month),
        "ratio_year": ratio(sent_year, scraped_year),
        "ratio_total": ratio(sent_total, scraped_total),
        "campaigns_today": camp_today,
    }


def stats_timeseries(site_code: str, date_from: date, date_to: date) -> list[dict]:
    """Pour chaque jour entre from et to, retourne {date, scraped, sent, ratio}."""
    c = _conn()
    try:
        rows = c.execute("""
            SELECT
                CAST(created_at AS DATE) AS d,
                COUNT(*) AS scraped,
                SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) AS sent
            FROM scrappe
            WHERE site_code=? AND CAST(created_at AS DATE) BETWEEN ? AND ?
            GROUP BY 1 ORDER BY 1
        """, [site_code, date_from, date_to]).fetchall()
    finally:
        c.close()
    by_date = {str(r[0]): {"scraped": r[1], "sent": r[2] or 0} for r in rows}
    series = []
    cur = date_from
    from datetime import timedelta
    while cur <= date_to:
        ds = str(cur)
        d = by_date.get(ds, {"scraped": 0, "sent": 0})
        ratio = round(d["sent"] / d["scraped"] * 100, 1) if d["scraped"] else 0.0
        series.append({"date": ds, "scraped": d["scraped"], "sent": d["sent"], "ratio": ratio})
        cur += timedelta(days=1)
    return series


def update_template_subject(site_code: str, sector: str, subject: str, username: str):
    """Met à jour uniquement le subject. Bloque si locked."""
    existing = get_template(site_code, sector)
    if not existing:
        raise ValueError(f"Template {site_code}/{sector} introuvable")
    if existing["locked"]:
        raise ValueError(f"Template {site_code}/{sector} verrouillé")
    body_text = _html_to_text(existing.get("html_content") or "")
    raw_full = f"SUBJECT: {subject}\n\n{body_text}"
    c = _conn()
    try:
        c.execute("UPDATE god_mode_templates SET subject=?, raw_content=? WHERE site_code=? AND sector=?",
                  [subject, raw_full, site_code, sector])
    finally:
        c.close()


if __name__ == "__main__":
    print("god_mode_backend module — VALID_SITES:", VALID_SITES)
    print("Sectors:", SECTORS_GOD_MODE)
    print("Top 50 cities:", len(TOP_50_INSEE))
