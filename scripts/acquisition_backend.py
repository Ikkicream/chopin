#!/usr/bin/env python3
"""
acquisition_backend.py — Storage unifié des contacts d'acquisition (cold_email → PRM → lead → CRM).

Remplace les 3 stockages historiques :
  - data/crm/{site}.duckdb table `contacts` (= CRM)
  - data/crm/prm_{site}.duckdb table `prm_contacts` (= PRM/leads)
  - data/prospects/{site}/leads.csv (= cold emails)

Modèle :
  acquisition_contacts (
    id              VARCHAR PRIMARY KEY,
    state           VARCHAR,   -- 'cold_email' | 'prm' | 'lead' | 'crm' | 'blacklisted'
    source          VARCHAR,   -- 'scraping_serper' | 'import_csv' | 'emelia_click' | 'tally:<form>' | 'manual'
    email           VARCHAR UNIQUE,
    nom             VARCHAR,
    prenom          VARCHAR,
    societe         VARCHAR,
    tel             VARCHAR,
    notes           VARCHAR,
    state_history   VARCHAR,   -- JSON: [{state, date, by, note}]
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_action_at  TIMESTAMP  -- dernière interaction (click, fill, sign…)
  )

Transitions automatiques (côté agents) :
  - Scraping/CSV    →  cold_email
  - Emelia click    →  prm  (si cold_email)
  - Emelia reply    →  lead (si cold_email/prm)
  - Tally form      →  lead (si vide ou plus bas)
  - Manuel         →  crm  ou  blacklisted
  - Bounce/opt-out  →  blacklisted

Hiérarchie de progression (utilisée pour ne PAS régresser involontairement) :
  cold_email (1) < prm (2) < lead (3) < crm (4)    blacklisted = état terminal
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).parent.parent

VALID_STATES = ["cold_email", "prm", "lead", "crm", "blacklisted"]
STATE_RANK = {"cold_email": 1, "prm": 2, "lead": 3, "crm": 4, "blacklisted": 5}

_SCHEMA_INIT: dict[str, bool] = {}


def db_path(site: str) -> Path:
    return BASE_DIR / "data" / "crm" / f"{site}.duckdb"


def _ensure_schema(site: str) -> None:
    """Crée la table si absente, idempotent. Appelé au 1er get_db() par site."""
    if _SCHEMA_INIT.get(site):
        return
    p = db_path(site)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(p))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS acquisition_contacts (
                id              VARCHAR PRIMARY KEY,
                state           VARCHAR DEFAULT 'cold_email',
                source          VARCHAR DEFAULT 'manual',
                email           VARCHAR UNIQUE,
                nom             VARCHAR DEFAULT '',
                prenom          VARCHAR DEFAULT '',
                societe         VARCHAR DEFAULT '',
                tel             VARCHAR DEFAULT '',
                notes           VARCHAR DEFAULT '',
                state_history   VARCHAR DEFAULT '[]',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_action_at  TIMESTAMP
            )
        """)
        # Indices (DuckDB n'a pas de DROP INDEX IF NOT EXISTS, on swallow)
        for sql in [
            "CREATE INDEX IF NOT EXISTS idx_acq_state ON acquisition_contacts(state)",
            "CREATE INDEX IF NOT EXISTS idx_acq_source ON acquisition_contacts(source)",
        ]:
            try:
                conn.execute(sql)
            except Exception:
                pass
    finally:
        conn.close()
    _SCHEMA_INIT[site] = True


def _conn(site: str) -> duckdb.DuckDBPyConnection:
    _ensure_schema(site)
    return duckdb.connect(str(db_path(site)))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())[:8]


def _append_history(history_json: str, state: str, by: str, note: str = "") -> str:
    try:
        h = json.loads(history_json) if history_json else []
        if not isinstance(h, list):
            h = []
    except Exception:
        h = []
    h.append({"state": state, "date": _now(), "by": by, "note": note})
    return json.dumps(h, ensure_ascii=False)


# ── CRUD ──────────────────────────────────────────────────────────────────────

def find_by_email(site: str, email: str) -> dict | None:
    if not email:
        return None
    email = email.strip().lower()
    conn = _conn(site)
    try:
        row = conn.execute(
            "SELECT id, state, source, email, nom, prenom, societe, tel, notes, "
            "state_history, created_at, updated_at, last_action_at "
            "FROM acquisition_contacts WHERE email = ?",
            [email],
        ).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row) if row else None


def _row_to_dict(row) -> dict:
    if not row:
        return {}
    return {
        "id":              row[0],
        "state":           row[1],
        "source":          row[2],
        "email":           row[3],
        "nom":             row[4],
        "prenom":          row[5],
        "societe":         row[6],
        "tel":             row[7],
        "notes":           row[8],
        "state_history":   _safe_json(row[9]),
        "created_at":      str(row[10]) if row[10] else "",
        "updated_at":      str(row[11]) if row[11] else "",
        "last_action_at":  str(row[12]) if row[12] else "",
    }


def _safe_json(s: str | None):
    if not s:
        return []
    try:
        return json.loads(s)
    except Exception:
        return []


def create(site: str, data: dict, by: str = "manual") -> dict:
    """Crée un contact. Si email existe déjà : retourne l'existant sans erreur.
    Promu seulement si le nouveau state est supérieur (et pas blacklisted)."""
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return {"error": "email_required"}

    existing = find_by_email(site, email)
    if existing:
        new_state = data.get("state")
        if new_state and STATE_RANK.get(new_state, 0) > STATE_RANK.get(existing["state"], 0) and existing["state"] != "blacklisted":
            return change_state(site, existing["id"], new_state, by=by, note=data.get("notes", ""))
        return {"existing": True, **existing}

    new_id = _new_id()
    state = data.get("state", "cold_email")
    if state not in VALID_STATES:
        state = "cold_email"
    source = data.get("source", "manual")
    history = _append_history("[]", state, by, "création")

    conn = _conn(site)
    try:
        conn.execute(
            """INSERT INTO acquisition_contacts
               (id, state, source, email, nom, prenom, societe, tel, notes, state_history,
                created_at, updated_at, last_action_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                new_id, state, source, email,
                data.get("nom", ""), data.get("prenom", ""), data.get("societe", ""),
                data.get("tel", ""), data.get("notes", ""), history,
                _now(), _now(), _now() if state != "cold_email" else None,
            ],
        )
    finally:
        conn.close()
    return {"created": True, "id": new_id, "state": state, "source": source, "email": email}


def update(site: str, contact_id: str, data: dict) -> dict:
    """Met à jour les champs simples (pas le state — utiliser change_state)."""
    fields, values = [], []
    for k in ("nom", "prenom", "societe", "tel", "notes", "source"):
        if k in data:
            fields.append(f"{k} = ?")
            values.append(data[k])
    if not fields:
        return {"updated": False, "reason": "no_changes"}
    fields.append("updated_at = ?")
    values.append(_now())
    values.append(contact_id)
    conn = _conn(site)
    try:
        conn.execute(f"UPDATE acquisition_contacts SET {', '.join(fields)} WHERE id = ?", values)
    finally:
        conn.close()
    return {"updated": True, "id": contact_id}


def change_state(site: str, contact_id: str, new_state: str, by: str = "manual", note: str = "") -> dict:
    """Change l'état avec trace dans state_history. Refuse si state invalide."""
    if new_state not in VALID_STATES:
        return {"error": "invalid_state", "valid": VALID_STATES}
    conn = _conn(site)
    try:
        row = conn.execute("SELECT state_history FROM acquisition_contacts WHERE id = ?", [contact_id]).fetchone()
        if not row:
            return {"error": "not_found"}
        new_history = _append_history(row[0], new_state, by, note)
        conn.execute(
            "UPDATE acquisition_contacts SET state = ?, state_history = ?, updated_at = ?, last_action_at = ? WHERE id = ?",
            [new_state, new_history, _now(), _now(), contact_id],
        )
    finally:
        conn.close()
    return {"changed": True, "id": contact_id, "state": new_state}


def list_contacts(site: str, state: list[str] | None = None, source: list[str] | None = None,
                  search: str = "", limit: int = 100, offset: int = 0) -> dict:
    """Liste paginée avec filtres."""
    where, params = [], []
    if state:
        placeholders = ",".join(["?"] * len(state))
        where.append(f"state IN ({placeholders})")
        params.extend(state)
    if source:
        placeholders = ",".join(["?"] * len(source))
        where.append(f"source IN ({placeholders})")
        params.extend(source)
    if search:
        where.append("(LOWER(email) LIKE ? OR LOWER(nom) LIKE ? OR LOWER(prenom) LIKE ? OR LOWER(societe) LIKE ?)")
        pat = f"%{search.lower()}%"
        params.extend([pat, pat, pat, pat])

    where_sql = " WHERE " + " AND ".join(where) if where else ""

    conn = _conn(site)
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM acquisition_contacts{where_sql}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT id, state, source, email, nom, prenom, societe, tel, notes,
                       state_history, created_at, updated_at, last_action_at
                FROM acquisition_contacts{where_sql}
                ORDER BY COALESCE(last_action_at, updated_at) DESC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
    finally:
        conn.close()

    return {
        "total":    total,
        "limit":    limit,
        "offset":   offset,
        "contacts": [_row_to_dict(r) for r in rows],
    }


def delete(site: str, contact_id: str, hard: bool = False) -> dict:
    """Soft delete (state=blacklisted) ou hard delete RGPD."""
    if hard:
        conn = _conn(site)
        try:
            conn.execute("DELETE FROM acquisition_contacts WHERE id = ?", [contact_id])
        finally:
            conn.close()
        return {"hard_deleted": True, "id": contact_id}
    return change_state(site, contact_id, "blacklisted", by="manual", note="deleted (soft)")


def blacklist(site: str, contact_id: str, push_emelia: bool = False, emelia_api_key: str = "") -> dict:
    """Passe le contact en blacklisted + optionnellement push Emelia unsubscribe."""
    result = change_state(site, contact_id, "blacklisted", by="manual", note="blacklisted")
    if result.get("error"):
        return result

    emelia_pushed = False
    if push_emelia and emelia_api_key:
        conn = _conn(site)
        try:
            row = conn.execute("SELECT email FROM acquisition_contacts WHERE id = ?", [contact_id]).fetchone()
        finally:
            conn.close()
        if row:
            try:
                import requests as _req
                r = _req.post(
                    "https://api.emelia.io/unsubscribe",
                    headers={"Authorization": emelia_api_key, "Content-Type": "application/json"},
                    json={"email": row[0]}, timeout=10,
                )
                emelia_pushed = r.status_code < 400
            except Exception:
                emelia_pushed = False
    return {**result, "emelia_pushed": emelia_pushed}


def bulk_import(site: str, rows: list[dict], source: str = "import_csv", default_state: str = "cold_email") -> dict:
    """Import en masse. Dédup par email. Retourne stats."""
    added, skipped, errors = 0, 0, 0
    for r in rows:
        email = (r.get("email") or "").strip().lower()
        if not email or "@" not in email:
            errors += 1
            continue
        existing = find_by_email(site, email)
        if existing:
            skipped += 1
            continue
        payload = {
            "email":   email,
            "nom":     r.get("nom") or r.get("lastName") or "",
            "prenom":  r.get("prenom") or r.get("firstName") or "",
            "societe": r.get("societe") or r.get("company") or "",
            "tel":     r.get("tel") or r.get("phone") or "",
            "notes":   r.get("notes", ""),
            "state":   default_state,
            "source":  source,
        }
        res = create(site, payload, by="bulk_import")
        if res.get("created"):
            added += 1
        else:
            skipped += 1
    return {"added": added, "skipped": skipped, "errors": errors, "total_seen": len(rows)}


def stats(site: str) -> dict:
    """Compteurs par état + par source (pour les onglets / dashboards)."""
    conn = _conn(site)
    try:
        by_state = dict(conn.execute(
            "SELECT state, COUNT(*) FROM acquisition_contacts GROUP BY state"
        ).fetchall())
        by_source = dict(conn.execute(
            "SELECT source, COUNT(*) FROM acquisition_contacts GROUP BY source"
        ).fetchall())
        total = sum(by_state.values())
    finally:
        conn.close()
    return {
        "total":  total,
        "by_state":  {s: by_state.get(s, 0) for s in VALID_STATES + list(set(by_state) - set(VALID_STATES))},
        "by_source": by_source,
    }


if __name__ == "__main__":
    # Smoke-test
    import sys
    site = sys.argv[1] if len(sys.argv) > 1 else "lcr"
    print(f"=== Stats {site} ===")
    print(json.dumps(stats(site), ensure_ascii=False, indent=2))
