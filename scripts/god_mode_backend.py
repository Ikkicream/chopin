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

import time

import duckdb

BASE_DIR = Path(__file__).parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"
AUTH_DB = BASE_DIR / "data" / "auth.duckdb"
TEMPLATES_DIR = BASE_DIR / "memory" / "templates"
SKILLS_DIR = BASE_DIR / "skills"

VALID_SITES = {"lcr", "mkd"}
SECTORS_GOD_MODE = ["immobilier", "restaurant", "garagiste", "coiffeur", "retail", "artisan", "fleuriste", "boulanger", "plombier", "electricien", "menuisier", "avocat", "comptable", "agence-marketing", "agence-web", "consultant"]

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
def _conn(retries: int = 8, delay: float = 0.4):
    """Ouvre une connexion write en retrying sur lock conflict (API concurrente)."""
    for attempt in range(retries):
        try:
            return duckdb.connect(str(GOD_DB))
        except Exception as e:
            if "Conflicting lock" in str(e) and attempt < retries - 1:
                time.sleep(delay)
                continue
            raise


def _auth():
    return duckdb.connect(str(AUTH_DB), read_only=True)


# ── Secteurs (source de vérité dynamique, plafond 30) ──────────────────────────
# SECTORS_GOD_MODE reste la liste SCRAPABLE (Serper). La table `sectors` est la
# source de vérité globale : elle contient les 16 scrapables + autre + tout secteur
# créé à l'import CSV (non scrapable). Plafond strict : 30 secteurs au total.
MAX_SECTORS = 30

# Seed aligné avec genesis-ui/src/lib/sectors.ts
SECTOR_SEED = [
    {"code": "immobilier",       "label": "Immobilier",       "emoji": "🏠", "kind": "b2c"},
    {"code": "restaurant",       "label": "Restaurant",       "emoji": "🍕", "kind": "b2c"},
    {"code": "garagiste",        "label": "Garagiste",        "emoji": "🚗", "kind": "b2c"},
    {"code": "coiffeur",         "label": "Coiffeur",         "emoji": "💇", "kind": "b2c"},
    {"code": "retail",           "label": "Retail",           "emoji": "🛍️", "kind": "b2c"},
    {"code": "artisan",          "label": "Artisan",          "emoji": "🔧", "kind": "b2c"},
    {"code": "fleuriste",        "label": "Fleuriste",        "emoji": "💐", "kind": "b2c"},
    {"code": "boulanger",        "label": "Boulanger",        "emoji": "🥖", "kind": "b2c"},
    {"code": "plombier",         "label": "Plombier",         "emoji": "🔧", "kind": "b2c"},
    {"code": "electricien",      "label": "Électricien",      "emoji": "⚡", "kind": "b2c"},
    {"code": "menuisier",        "label": "Menuisier",        "emoji": "🪵", "kind": "b2c"},
    {"code": "avocat",           "label": "Avocat",           "emoji": "⚖️", "kind": "b2b"},
    {"code": "comptable",        "label": "Comptable",        "emoji": "📊", "kind": "b2b"},
    {"code": "agence-marketing", "label": "Agence Marketing", "emoji": "📣", "kind": "b2b"},
    {"code": "agence-web",       "label": "Agence Web",       "emoji": "💻", "kind": "b2b"},
    {"code": "consultant",       "label": "Consultant",       "emoji": "🧑‍💼", "kind": "b2b"},
    {"code": "autre",            "label": "Autre",            "emoji": "📦", "kind": "mixed"},
]
_SECTORS_INIT = False


def _ensure_sectors_table() -> None:
    """Crée + seed la table `sectors` (idempotent, 1×/process)."""
    global _SECTORS_INIT
    if _SECTORS_INIT:
        return
    c = _conn()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS sectors (
                code        VARCHAR PRIMARY KEY,
                label       VARCHAR,
                emoji       VARCHAR,
                kind        VARCHAR DEFAULT 'mixed',   -- b2b | b2c | mixed
                scrapable   BOOLEAN DEFAULT FALSE,
                source      VARCHAR DEFAULT 'seed',    -- seed | import
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for s in SECTOR_SEED:
            scrapable = s["code"] in SECTORS_GOD_MODE
            c.execute(
                "INSERT INTO sectors (code, label, emoji, kind, scrapable, source) "
                "VALUES (?, ?, ?, ?, ?, 'seed') ON CONFLICT (code) DO NOTHING",
                [s["code"], s["label"], s["emoji"], s["kind"], scrapable],
            )
        _SECTORS_INIT = True
    finally:
        c.close()


def list_sectors() -> list[dict]:
    """Tous les secteurs (seed + importés), triés scrapables d'abord."""
    _ensure_sectors_table()
    c = _conn()
    try:
        rows = c.execute(
            "SELECT code, label, emoji, kind, scrapable, source FROM sectors "
            "ORDER BY scrapable DESC, code"
        ).fetchall()
    finally:
        c.close()
    out = [
        {"code": r[0], "label": r[1], "emoji": r[2], "kind": r[3],
         "scrapable": bool(r[4]), "source": r[5]}
        for r in rows
    ]
    return out or [
        {**s, "scrapable": s["code"] in SECTORS_GOD_MODE, "source": "seed"}
        for s in SECTOR_SEED
    ]


def add_sector(code: str, label: str = "", emoji: str = "🏷️", kind: str = "mixed") -> dict:
    """Crée un secteur importé (scrapable=FALSE). Refuse si plafond 30 atteint.

    Retourne {created|exists|rejected, code, total}. En cas de rejet, l'appelant
    doit basculer la catégorie concernée vers 'autre'."""
    _ensure_sectors_table()
    code = (code or "").strip().lower().replace(" ", "-")
    if not code:
        return {"rejected": True, "reason": "empty_code"}
    c = _conn()
    try:
        existing = c.execute("SELECT code FROM sectors WHERE code = ?", [code]).fetchone()
        total = c.execute("SELECT COUNT(*) FROM sectors").fetchone()[0]
        if existing:
            return {"exists": True, "code": code, "total": total}
        if total >= MAX_SECTORS:
            return {"rejected": True, "reason": "cap_reached", "code": code, "total": total}
        c.execute(
            "INSERT INTO sectors (code, label, emoji, kind, scrapable, source) "
            "VALUES (?, ?, ?, ?, FALSE, 'import')",
            [code, label or code.replace("-", " ").title(), emoji or "🏷️", kind or "mixed"],
        )
        return {"created": True, "code": code, "total": total + 1}
    finally:
        c.close()


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


def list_logs(site_code: str = None, limit: int = 200, action: str = None):
    """Liste les logs ; si `action` est fourni, filtre exactement par cette action (ex: 'cleanup_batch')."""
    c = _conn()
    try:
        sql = "SELECT id, site_code, username, action, resource, resource_id, ip, payload, success, error_message, created_at FROM god_mode_logs"
        clauses = []
        args = []
        if site_code:
            clauses.append("site_code=?"); args.append(site_code)
        if action:
            clauses.append("action=?"); args.append(action)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        rows = c.execute(sql, args).fetchall()
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
        c.execute("""INSERT INTO scrappe (id, site_code, company_name, contact_name, email, phone, sector, city, postal_code, website, source, search_query, score, status, raw_data, email_score, email_validation_reasons)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  [pid, site_code, data.get("company_name"), data.get("contact_name"), data.get("email"),
                   data.get("phone"), data.get("sector"), data.get("city"), data.get("postal_code"),
                   data.get("website"), data.get("source"), data.get("search_query"),
                   data.get("score", 0), data.get("status", "new"),
                   json.dumps(data.get("raw_data", {})),
                   data.get("email_score"),
                   json.dumps(data.get("email_validation_reasons")) if data.get("email_validation_reasons") is not None else None])
    finally:
        c.close()
    return pid




# ── Pending (scrappe_pending) — Mailnjoy queue ────────────────────────────────
def add_prospect_pending(site_code: str, data: dict) -> str:
    """Insère un prospect dans la table temporaire scrappe_pending en attendant
    la vérification Mailnjoy. Voir specs/mailnjoy-integration-prompt.md."""
    pid = str(uuid.uuid4())
    c = _conn()
    try:
        c.execute("""INSERT INTO scrappe_pending
            (id, site_code, company_name, contact_name, email, phone, sector, city, postal_code,
             website, source, search_query, score, status, raw_data, email_score,
             email_validation_reasons, region_code, dept_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [pid, site_code, data.get("company_name"), data.get("contact_name"), data.get("email"),
             data.get("phone"), data.get("sector"), data.get("city"), data.get("postal_code"),
             data.get("website"), data.get("source"), data.get("search_query"),
             data.get("score", 0), data.get("status", "pending_mailnjoy"),
             json.dumps(data.get("raw_data", {})),
             data.get("email_score"),
             json.dumps(data.get("email_validation_reasons")) if data.get("email_validation_reasons") is not None else None,
             data.get("region_code"), data.get("dept_code")])
    finally:
        c.close()
    return pid


def list_pending(site_code: str = None, limit: int = 500) -> list[dict]:
    c = _conn()
    try:
        q = """SELECT id, site_code, company_name, contact_name, email, phone, sector, city,
                      postal_code, website, source, search_query, score, status, raw_data,
                      email_score, email_validation_reasons, region_code, dept_code,
                      created_at, mailnjoy_attempts, mailnjoy_last_error
               FROM scrappe_pending WHERE mailnjoy_attempts < 5"""
        params = []
        if site_code:
            q += " AND site_code = ?"; params.append(site_code)
        q += " ORDER BY created_at ASC LIMIT ?"; params.append(limit)
        rows = c.execute(q, params).fetchall()
    finally:
        c.close()
    cols = ["id", "site_code", "company_name", "contact_name", "email", "phone", "sector",
            "city", "postal_code", "website", "source", "search_query", "score", "status",
            "raw_data", "email_score", "email_validation_reasons", "region_code", "dept_code",
            "created_at", "mailnjoy_attempts", "mailnjoy_last_error"]
    return [dict(zip(cols, r)) for r in rows]


def move_pending_to_scrappe(pending_id: str, mn_check: dict) -> str | None:
    """Déplace une ligne de scrappe_pending → scrappe (status='validated').
    La ligne pending est ENSUITE supprimée. Retourne l'id scrappe créé."""
    c = _conn()
    try:
        row = c.execute("SELECT * FROM scrappe_pending WHERE id = ?", [pending_id]).fetchone()
        if not row:
            return None
        cols = [d[0] for d in c.description]
        d = dict(zip(cols, row))

        new_id = str(uuid.uuid4())
        c.execute("""INSERT INTO scrappe
            (id, site_code, company_name, contact_name, email, phone, sector, city, postal_code,
             website, source, search_query, score, status, raw_data, email_score,
             email_validation_reasons, region_code, dept_code, mailnjoy_check)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [new_id, d["site_code"], d["company_name"], d["contact_name"], d["email"],
             d["phone"], d["sector"], d["city"], d["postal_code"], d["website"],
             d["source"], d["search_query"], d["score"], "mailnjoy_valid",
             d["raw_data"] if isinstance(d["raw_data"], str) else json.dumps(d["raw_data"] or {}),
             d["email_score"],
             d["email_validation_reasons"] if isinstance(d["email_validation_reasons"], str)
                else (json.dumps(d["email_validation_reasons"]) if d["email_validation_reasons"] else None),
             d["region_code"], d["dept_code"], json.dumps(mn_check)])
        c.execute("DELETE FROM scrappe_pending WHERE id = ?", [pending_id])
    finally:
        c.close()
    return new_id


def delete_pending(pending_id: str) -> None:
    """Supprime définitivement une ligne pending (mailnjoy invalid ou risky)."""
    c = _conn()
    try:
        c.execute("DELETE FROM scrappe_pending WHERE id = ?", [pending_id])
    finally:
        c.close()


def bump_pending_error(pending_id: str, err: str) -> None:
    """Incrémente mailnjoy_attempts + stocke la dernière erreur."""
    c = _conn()
    try:
        c.execute("""UPDATE scrappe_pending
                       SET mailnjoy_attempts = mailnjoy_attempts + 1,
                           mailnjoy_last_error = ?
                       WHERE id = ?""", [err[:500], pending_id])
    finally:
        c.close()




def _conn_ro():
    """Connexion lecture seule — ne prend pas le write-lock DuckDB."""
    return duckdb.connect(str(GOD_DB), read_only=True)


def email_recently_validated(email: str, days: int = 30) -> bool:
    """True si l'email a déjà été validé par Mailnjoy il y a moins de N jours.
    Empêche de re-checker un email récemment confirmé."""
    if not email:
        return False
    c = _conn_ro()
    try:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        row = c.execute("""
            SELECT 1 FROM scrappe
            WHERE email = ? AND mailnjoy_check IS NOT NULL
              AND CAST(json_extract_string(mailnjoy_check, '$.checked_at') AS VARCHAR) > ?
            LIMIT 1
        """, [email, cutoff]).fetchone()
    finally:
        c.close()
    return row is not None


def email_in_pending(email: str) -> bool:
    """True si l'email est déjà dans scrappe_pending (évite doublons de queue)."""
    if not email:
        return False
    c = _conn_ro()
    try:
        row = c.execute('SELECT 1 FROM scrappe_pending WHERE email = ? LIMIT 1', [email]).fetchone()
    finally:
        c.close()
    return row is not None


def list_prospects(site_code: str, status: str = None, sector: str = None, limit: int = 500):
    c = _conn()
    try:
        q = """SELECT id, site_code, company_name, contact_name, email, phone, sector, city,
                       postal_code, website, source, score, status, created_at, contacted_at,
                       rejection_reason, email_score, email_validation_reasons, mailnjoy_check,
                       qualifier_buyer, qualifier_reason, emelia_contact_id
                FROM scrappe WHERE site_code=?"""
        params = [site_code]
        if status:
            q += " AND status=?"; params.append(status)
        if sector:
            q += " AND sector=?"; params.append(sector)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        rows = c.execute(q, params).fetchall()
    finally:
        c.close()
    import json as _json
    def _maybe_parse(v):
        if v is None: return None
        if isinstance(v, (dict, list)): return v
        try: return _json.loads(v) if isinstance(v, str) else v
        except Exception: return v
    return [{
        "id": r[0], "site_code": r[1], "company_name": r[2], "contact_name": r[3],
        "email": r[4], "phone": r[5], "sector": r[6], "city": r[7],
        "postal_code": r[8], "website": r[9], "source": r[10], "score": r[11],
        "status": r[12], "created_at": str(r[13]),
        "contacted_at": str(r[14]) if r[14] else None,
        "rejection_reason": r[15],
        "email_score": r[16],
        "email_validation_reasons": _maybe_parse(r[17]),
        "mailnjoy_check":           _maybe_parse(r[18]),
        "qualifier_buyer": r[19],
        "qualifier_reason": r[20],
        "emelia_contact_id": r[21],
    } for r in rows]


def update_prospect_status(prospect_id: str, status: str, reason: str = None):
    c = _conn()
    try:
        if status == "contacted":
            c.execute("UPDATE scrappe SET status=?, contacted_at=? WHERE id=?", [status, datetime.now(timezone.utc), prospect_id])
        elif status in ("validated", "mailnjoy_valid"):
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


# ── Quota de scrape mensuel par user ──────────────────────────────────────────
# Garde-fou produit (2026-06-26) : un user métier (commercial) est plafonné à
# SCRAPE_MONTHLY_CAP contacts GARDÉS (scrapés + insérés dans le pool) par mois
# calendaire, tous sites confondus. Le superadmin (Camille) n'est pas concerné.
SCRAPE_MONTHLY_CAP = 5000
_SCRAPE_QUOTA_INIT = False


def _ensure_scrape_quota_table() -> None:
    global _SCRAPE_QUOTA_INIT
    if _SCRAPE_QUOTA_INIT:
        return
    c = _conn()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS scrape_quota_usage (
                user_id    VARCHAR NOT NULL,
                year_month VARCHAR NOT NULL,   -- 'YYYY-MM'
                used       INTEGER DEFAULT 0,  -- contacts gardés ce mois
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, year_month)
            )
        """)
        _SCRAPE_QUOTA_INIT = True
    finally:
        c.close()


def scrape_quota_status(user_id: str, cap: int = SCRAPE_MONTHLY_CAP) -> dict:
    """Usage de scrape du mois courant pour un user. {used, limit, remaining, year_month}."""
    _ensure_scrape_quota_table()
    ym = date.today().strftime("%Y-%m")
    c = _conn()
    try:
        row = c.execute(
            "SELECT used FROM scrape_quota_usage WHERE user_id=? AND year_month=?",
            [user_id, ym],
        ).fetchone()
    finally:
        c.close()
    used = int(row[0]) if row else 0
    return {"used": used, "limit": cap, "remaining": max(0, cap - used), "year_month": ym}


def record_scrape_usage(user_id: str, n: int) -> None:
    """Incrémente le compteur mensuel de `n` contacts gardés (best-effort, read-modify-write)."""
    if not user_id or not n or n <= 0:
        return
    _ensure_scrape_quota_table()
    ym = date.today().strftime("%Y-%m")
    try:
        c = _conn()
        try:
            row = c.execute(
                "SELECT used FROM scrape_quota_usage WHERE user_id=? AND year_month=?",
                [user_id, ym],
            ).fetchone()
            if row:
                c.execute(
                    "UPDATE scrape_quota_usage SET used = used + ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE user_id=? AND year_month=?",
                    [int(n), user_id, ym],
                )
            else:
                c.execute(
                    "INSERT INTO scrape_quota_usage (user_id, year_month, used) VALUES (?, ?, ?)",
                    [user_id, ym, int(n)],
                )
        finally:
            c.close()
    except Exception:
        pass


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
        # Sent (status='pushed_emelia' = email envoyé via Emelia)
        sent_today = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND status='pushed_emelia' AND CAST(contacted_at AS DATE)=?", [site_code, today]).fetchone()[0]
        sent_month = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND status='pushed_emelia' AND CAST(contacted_at AS DATE)>=?", [site_code, first_of_month]).fetchone()[0]
        sent_year = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND status='pushed_emelia' AND CAST(contacted_at AS DATE)>=?", [site_code, first_of_year]).fetchone()[0]
        sent_total = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND status='pushed_emelia'", [site_code]).fetchone()[0]
        camp_today = c.execute("SELECT COUNT(*) FROM god_mode_campaigns WHERE site_code=? AND scheduled_date=?", [site_code, today]).fetchone()[0]

        # Cleaned (nettoyés) = rejetés par le validator + supprimés par Mailnjoy.
        # Validator drops -> insérés en scrappe avec status='rejected'
        # Mailnjoy drops  -> jamais en scrappe, lus depuis logs/mailnjoy_deletions.log
        cleaned_validator_today = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND status='rejected' AND CAST(created_at AS DATE)=?", [site_code, today]).fetchone()[0]
        cleaned_validator_month = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND status='rejected' AND CAST(created_at AS DATE)>=?", [site_code, first_of_month]).fetchone()[0]
        cleaned_validator_year  = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND status='rejected' AND CAST(created_at AS DATE)>=?", [site_code, first_of_year]).fetchone()[0]
        cleaned_validator_total = c.execute("SELECT COUNT(*) FROM scrappe WHERE site_code=? AND status='rejected'", [site_code]).fetchone()[0]
    finally:
        c.close()

    # Lecture log Mailnjoy (parsé par date — note: log non par-site, mais ~tous sites confondus)
    import json as _json
    from pathlib import Path as _Path
    log_f = _Path(__file__).parent.parent / "logs" / "mailnjoy_deletions.log"
    cleaned_mailnjoy_today = cleaned_mailnjoy_month = cleaned_mailnjoy_year = cleaned_mailnjoy_total = 0
    if log_f.exists():
        try:
            for line in log_f.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    e = _json.loads(line)
                    ts = e.get("ts", "")[:10]
                    if not ts:
                        continue
                    cleaned_mailnjoy_total += 1
                    if ts == today.isoformat():       cleaned_mailnjoy_today += 1
                    if ts >= first_of_month.isoformat(): cleaned_mailnjoy_month += 1
                    if ts >= first_of_year.isoformat():  cleaned_mailnjoy_year  += 1
                except Exception:
                    pass
        except Exception:
            pass
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
        # Nettoyés = validator rejections + mailnjoy deletions
        "cleaned_today": cleaned_validator_today + cleaned_mailnjoy_today,
        "cleaned_month": cleaned_validator_month + cleaned_mailnjoy_month,
        "cleaned_year":  cleaned_validator_year  + cleaned_mailnjoy_year,
        "cleaned_total": cleaned_validator_total + cleaned_mailnjoy_total,
        "cleaned_breakdown": {
            "validator_total": cleaned_validator_total,
            "mailnjoy_total":  cleaned_mailnjoy_total,
        },
    }


def stats_timeseries(site_code: str, date_from: date, date_to: date) -> list[dict]:
    """Pour chaque jour entre from et to, retourne {date, scraped, sent, ratio}."""
    c = _conn()
    try:
        rows = c.execute("""
            SELECT
                CAST(created_at AS DATE) AS d,
                COUNT(*) AS scraped,
                SUM(CASE WHEN status='pushed_emelia' THEN 1 ELSE 0 END) AS sent
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
