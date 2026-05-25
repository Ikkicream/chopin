#!/usr/bin/env python3
"""
email_templates_backend.py — Templates cold email par secteur, modèle 1-ligne-par-email.

Remplace sector_templates_backend (qui stockait une séquence figée). Ici chaque email
(first / relance1 / relance2) est une ligne indépendante : éditable et verrouillable seule.
- L'IA (email_generator) PROPOSE les 3 emails ; le user édite et programme/verrouille chacun.
- « locked » = approuvé/figé par le user (l'édition le rouvre ; régénérer ne l'écrase pas).
- Aucune séquence auto, aucun push pipeline : c'est un assistant de rédaction.

Table email_templates (god_mode.duckdb). PK (site_code, sector, kind).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"
sys.path.insert(0, str(BASE_DIR / "scripts"))

KINDS = ["first", "relance1", "relance2"]
KIND_LABEL = {"first": "1er email", "relance1": "Relance 1", "relance2": "Relance 2"}


def _conn():
    return duckdb.connect(str(GOD_DB))


def _ensure_table() -> None:
    c = _conn()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS email_templates (
                site_code         VARCHAR,
                sector            VARCHAR,
                kind              VARCHAR,
                subject           VARCHAR,
                body_html         VARCHAR,
                valid             BOOLEAN,
                validation_errors VARCHAR,
                locked            BOOLEAN DEFAULT FALSE,
                locked_at         TIMESTAMP,
                updated_by        VARCHAR,
                updated_at        TIMESTAMP,
                PRIMARY KEY (site_code, sector, kind)
            )
        """)
    finally:
        c.close()


def _row(r) -> dict:
    cols = ["site_code", "sector", "kind", "subject", "body_html", "valid",
            "validation_errors", "locked", "locked_at", "updated_by", "updated_at"]
    d = dict(zip(cols, r))
    d["label"] = KIND_LABEL.get(d["kind"], d["kind"])
    try:
        d["validation_errors"] = json.loads(d["validation_errors"]) if d["validation_errors"] else []
    except Exception:
        d["validation_errors"] = []
    for k in ("locked_at", "updated_at"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    return d


_SELECT = ("SELECT site_code, sector, kind, subject, body_html, valid, validation_errors, "
           "locked, locked_at, updated_by, updated_at FROM email_templates")


def _get_one(site: str, sector: str, kind: str) -> dict | None:
    _ensure_table()
    c = _conn()
    try:
        r = c.execute(_SELECT + " WHERE site_code=? AND sector=? AND kind=?",
                      [site, sector, kind]).fetchone()
    finally:
        c.close()
    return _row(r) if r else None


def _upsert(site: str, sector: str, kind: str, subject: str, body_html: str,
            valid: bool, errors: list, by: str = "ai", locked: bool = False) -> None:
    _ensure_table()
    c = _conn()
    try:
        now = datetime.now(timezone.utc)
        c.execute("DELETE FROM email_templates WHERE site_code=? AND sector=? AND kind=?",
                  [site, sector, kind])
        c.execute(
            "INSERT INTO email_templates "
            "(site_code, sector, kind, subject, body_html, valid, validation_errors, locked, updated_by, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            [site, sector, kind, subject, body_html, valid,
             json.dumps(errors, ensure_ascii=False), locked, by, now],
        )
    finally:
        c.close()


def get_sector(site: str, sector: str) -> list[dict]:
    """Les emails d'un secteur, ordonnés first → relance1 → relance2."""
    _ensure_table()
    c = _conn()
    try:
        rows = c.execute(_SELECT + " WHERE site_code=? AND sector=?", [site, sector]).fetchall()
    finally:
        c.close()
    by_kind = {r[2]: _row(r) for r in rows}
    return [by_kind[k] for k in KINDS if k in by_kind]


def list_sectors(site: str) -> list[dict]:
    """Récap par secteur : nb d'emails + nb verrouillés."""
    _ensure_table()
    c = _conn()
    try:
        rows = c.execute(
            "SELECT sector, count(*), sum(CASE WHEN locked THEN 1 ELSE 0 END) "
            "FROM email_templates WHERE site_code=? GROUP BY sector ORDER BY sector", [site]
        ).fetchall()
    finally:
        c.close()
    return [{"sector": s, "emails": int(n), "locked": int(lk or 0)} for s, n, lk in rows]


def generate(site: str, sector: str) -> dict:
    """Génère (DeepSeek) les 3 propositions et upsert SANS écraser un email verrouillé."""
    from email_generator import generate_sequence
    res = generate_sequence(site, sector)
    if res.get("excluded"):
        return {"ok": False, "excluded": True, "reason": res.get("reason")}
    emails = res.get("emails", [])
    verrors = res.get("validation_errors", {})
    skipped = []
    for i, kind in enumerate(KINDS):
        if i >= len(emails):
            break
        existing = _get_one(site, sector, kind)
        if existing and existing.get("locked"):
            skipped.append(kind)
            continue
        em = emails[i]
        errs = verrors.get(i + 1, [])
        _upsert(site, sector, kind, em.get("subject", ""), em.get("body_html", ""),
                not errs, errs, by="ai", locked=False)
    return {"ok": True, "sector": sector, "skipped_locked": skipped, "emails": get_sector(site, sector)}


def update(site: str, sector: str, kind: str, subject: str, body_html: str, by: str = "ui") -> dict:
    """Édition manuelle d'un email. Re-valide ; l'édition rouvre (locked=False)."""
    from email_generator import validate_email
    if kind not in KINDS:
        return {"ok": False, "error": f"kind invalide ({kind})"}
    errs = validate_email(subject or "", body_html or "")
    _upsert(site, sector, kind, subject or "", body_html or "", not errs, errs, by=by, locked=False)
    return {"ok": True, "valid": not errs, "validation_errors": errs, "email": _get_one(site, sector, kind)}


def set_lock(site: str, sector: str, kind: str, locked: bool, by: str = "ui") -> dict:
    """Verrouille (= approuve) ou déverrouille un email. Verrouiller refuse si non conforme."""
    t = _get_one(site, sector, kind)
    if not t:
        return {"ok": False, "error": "email introuvable (générer d'abord)"}
    if locked and not t.get("valid"):
        return {"ok": False, "error": "email non conforme — corriger avant de verrouiller",
                "validation_errors": t.get("validation_errors")}
    c = _conn()
    try:
        c.execute(
            "UPDATE email_templates SET locked=?, locked_at=? WHERE site_code=? AND sector=? AND kind=?",
            [locked, datetime.now(timezone.utc) if locked else None, site, sector, kind],
        )
    finally:
        c.close()
    return {"ok": True, "locked": locked, "email": _get_one(site, sector, kind)}


if __name__ == "__main__":
    import pprint
    pprint.pprint(list_sectors(sys.argv[1] if len(sys.argv) > 1 else "lcr"))
