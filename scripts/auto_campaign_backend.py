#!/usr/bin/env python3
"""
auto_campaign_backend.py — Modèle + CRUD des campagnes cold-email AUTOMATISÉES.

Une "campagne auto" tourne toute seule chaque jour : elle pousse jusqu'à `daily_target`
contacts (plafonné par le warmup de l'expéditeur) ; si le pool est sec et source_mode
= 'autoscrape', elle déclenche un scrape du département pour réapprovisionner.

Tables dans god_mode.duckdb (là où vivent email_senders + emelia_events) :
  - auto_campaigns     : config persistante
  - auto_campaign_runs : 1 ligne par run quotidien (audit, idempotence, reprise crash)

DuckDB = 1 seul writer → connexions courtes + retry sur lock.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone, date
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"
WRITE_RETRY = 5

_DDL = [
    """
    CREATE TABLE IF NOT EXISTS auto_campaigns (
        id                 VARCHAR PRIMARY KEY,
        site_code          VARCHAR NOT NULL,
        name               VARCHAR NOT NULL,
        sectors            JSON    NOT NULL,
        source_mode        VARCHAR NOT NULL DEFAULT 'pool',   -- 'pool' | 'autoscrape'
        dept               VARCHAR,
        sender_email       VARCHAR NOT NULL,
        message_mode       VARCHAR NOT NULL DEFAULT 'templates_sector',
        daily_target       INTEGER NOT NULL DEFAULT 30,
        status             VARCHAR NOT NULL DEFAULT 'active',  -- active | paused | stopped
        emelia_campaign_id VARCHAR,
        created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_by         VARCHAR,
        last_run_at        TIMESTAMP,
        last_run_date      DATE,
        last_pushed_count  INTEGER DEFAULT 0,
        last_error         VARCHAR,
        updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auto_campaign_runs (
        id               VARCHAR PRIMARY KEY,
        auto_campaign_id VARCHAR NOT NULL,
        site_code        VARCHAR NOT NULL,
        run_date         DATE NOT NULL,
        started_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        finished_at      TIMESTAMP,
        target           INTEGER,
        pushed           INTEGER DEFAULT 0,
        sent_observed    INTEGER DEFAULT 0,
        end_reason       VARCHAR,
        scrape_invoked   BOOLEAN DEFAULT FALSE,
        error            VARCHAR
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_acr_camp_date ON auto_campaign_runs(auto_campaign_id, run_date)",
]

_CAMP_COLS = [
    "id", "site_code", "name", "sectors", "source_mode", "dept", "sender_email",
    "message_mode", "daily_target", "status", "emelia_campaign_id", "created_at",
    "created_by", "last_run_at", "last_run_date", "last_pushed_count", "last_error", "updated_at",
]


def _conn(read_only: bool = False):
    last = None
    for attempt in range(WRITE_RETRY):
        try:
            return duckdb.connect(str(GOD_DB), read_only=read_only)
        except Exception as e:  # lock / config conflict
            last = e
            time.sleep(1.0 + attempt * 0.5)
    raise last


_MIGRATED = False


def _ensure_schema() -> None:
    global _MIGRATED
    if _MIGRATED:
        return
    c = _conn()
    try:
        for stmt in _DDL:
            c.execute(stmt)
    finally:
        c.close()
    _MIGRATED = True


def _row_to_camp(row) -> dict:
    d = dict(zip(_CAMP_COLS, row))
    try:
        d["sectors"] = json.loads(d["sectors"]) if isinstance(d.get("sectors"), str) else (d.get("sectors") or [])
    except Exception:
        d["sectors"] = []
    for k in ("created_at", "last_run_at", "last_run_date", "updated_at"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    return d


# ── CRUD ──────────────────────────────────────────────────────────────────────
def create_auto_campaign(site_code: str, name: str, sectors: list[str], sender_email: str,
                         source_mode: str = "pool", dept: str | None = None,
                         message_mode: str = "templates_sector", daily_target: int = 30,
                         emelia_campaign_id: str | None = None, created_by: str = "system") -> str:
    _ensure_schema()
    cid = str(uuid.uuid4())
    c = _conn()
    try:
        c.execute("""
            INSERT INTO auto_campaigns
              (id, site_code, name, sectors, source_mode, dept, sender_email, message_mode,
               daily_target, status, emelia_campaign_id, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """, [cid, site_code, name, json.dumps(sectors), source_mode, dept, sender_email,
              message_mode, int(daily_target), emelia_campaign_id, created_by])
    finally:
        c.close()
    return cid


def list_auto_campaigns(site_code: str) -> list[dict]:
    _ensure_schema()
    c = _conn(read_only=True)
    try:
        rows = c.execute(
            f"SELECT {', '.join(_CAMP_COLS)} FROM auto_campaigns WHERE site_code = ? "
            "ORDER BY created_at DESC", [site_code]).fetchall()
    finally:
        c.close()
    return [_row_to_camp(r) for r in rows]


def list_active(site_code: str) -> list[dict]:
    return [c for c in list_auto_campaigns(site_code) if c.get("status") == "active"]


def get_auto_campaign(camp_id: str) -> dict | None:
    _ensure_schema()
    c = _conn(read_only=True)
    try:
        row = c.execute(
            f"SELECT {', '.join(_CAMP_COLS)} FROM auto_campaigns WHERE id = ?", [camp_id]).fetchone()
    finally:
        c.close()
    return _row_to_camp(row) if row else None


_UPDATABLE = {"name", "sectors", "source_mode", "dept", "sender_email", "message_mode",
              "daily_target", "status", "emelia_campaign_id"}


def update_auto_campaign(camp_id: str, **fields) -> bool:
    _ensure_schema()
    sets, params = [], []
    for k, v in fields.items():
        if k not in _UPDATABLE:
            continue
        if k == "sectors":
            v = json.dumps(v)
        sets.append(f"{k} = ?")
        params.append(v)
    if not sets:
        return False
    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(camp_id)
    c = _conn()
    try:
        c.execute(f"UPDATE auto_campaigns SET {', '.join(sets)} WHERE id = ?", params)
    finally:
        c.close()
    return True


def set_status(camp_id: str, status: str) -> bool:
    return update_auto_campaign(camp_id, status=status)


def delete_auto_campaign(camp_id: str) -> bool:
    _ensure_schema()
    c = _conn()
    try:
        c.execute("DELETE FROM auto_campaigns WHERE id = ?", [camp_id])
    finally:
        c.close()
    return True


# ── Runs (idempotence 1/jour, audit, reprise) ──────────────────────────────────
def sender_has_completed_run_today(sender_email: str, run_date: date | None = None) -> bool:
    """True si un run AVEC end_reason (= terminé) existe aujourd'hui pour ce sender.
    Garde la contrainte '1 campagne auto/jour par expéditeur' + idempotence relance PM2."""
    _ensure_schema()
    rd = (run_date or date.today()).isoformat()
    c = _conn(read_only=True)
    try:
        n = c.execute("""
            SELECT COUNT(*) FROM auto_campaign_runs r
            JOIN auto_campaigns ac ON ac.id = r.auto_campaign_id
            WHERE ac.sender_email = ? AND r.run_date = ? AND r.end_reason IS NOT NULL
        """, [sender_email, rd]).fetchone()[0]
    finally:
        c.close()
    return int(n or 0) > 0


def start_run(auto_campaign_id: str, site_code: str, target: int,
              run_date: date | None = None) -> str:
    _ensure_schema()
    rid = str(uuid.uuid4())
    rd = (run_date or date.today()).isoformat()
    c = _conn()
    try:
        c.execute("""
            INSERT INTO auto_campaign_runs (id, auto_campaign_id, site_code, run_date, target)
            VALUES (?, ?, ?, ?, ?)
        """, [rid, auto_campaign_id, site_code, rd, int(target)])
    finally:
        c.close()
    return rid


def finish_run(run_id: str, pushed: int, sent_observed: int, end_reason: str,
               scrape_invoked: bool = False, error: str | None = None) -> None:
    _ensure_schema()
    c = _conn()
    try:
        c.execute("""
            UPDATE auto_campaign_runs
            SET finished_at = CURRENT_TIMESTAMP, pushed = ?, sent_observed = ?,
                end_reason = ?, scrape_invoked = ?, error = ?
            WHERE id = ?
        """, [int(pushed), int(sent_observed), end_reason, bool(scrape_invoked), error, run_id])
    finally:
        c.close()


def record_campaign_result(camp_id: str, pushed: int, error: str | None,
                           run_date: date | None = None) -> None:
    _ensure_schema()
    rd = (run_date or date.today()).isoformat()
    c = _conn()
    try:
        c.execute("""
            UPDATE auto_campaigns
            SET last_run_at = CURRENT_TIMESTAMP, last_run_date = ?, last_pushed_count = ?,
                last_error = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, [rd, int(pushed), error, camp_id])
    finally:
        c.close()


def runs_for_campaign(auto_campaign_id: str, limit: int = 30) -> list[dict]:
    _ensure_schema()
    cols = ["id", "run_date", "started_at", "finished_at", "target", "pushed",
            "sent_observed", "end_reason", "scrape_invoked", "error"]
    c = _conn(read_only=True)
    try:
        rows = c.execute(
            f"SELECT {', '.join(cols)} FROM auto_campaign_runs WHERE auto_campaign_id = ? "
            "ORDER BY started_at DESC LIMIT ?", [auto_campaign_id, int(limit)]).fetchall()
    finally:
        c.close()
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        for k in ("run_date", "started_at", "finished_at"):
            if d.get(k) is not None:
                d[k] = str(d[k])
        out.append(d)
    return out
