#!/usr/bin/env python3
"""
html_templates_backend.py — Newsletters HTML éditables (structure verrouillée, texte + images).

- Structures de base = fichiers `structures/*.html` (point de départ d'une édition).
- Versions sauvegardées = table `html_templates` (god_mode.duckdb), nommées + datées.
La structure HTML n'est jamais modifiée par le code ; seul le contenu (texte/img) édité par
l'utilisateur est resauvegardé comme nouvelle version.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"
STRUCTURES_DIR = BASE_DIR / "structures"


def _conn():
    return duckdb.connect(str(GOD_DB))


def _ensure_table():
    c = _conn()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS html_templates (
                id         VARCHAR PRIMARY KEY,
                site_code  VARCHAR,
                name       VARCHAR,
                html       VARCHAR,
                source     VARCHAR,
                created_by VARCHAR,
                created_at TIMESTAMP
            )
        """)
    finally:
        c.close()


def list_structures() -> list[dict]:
    """Structures HTML de base disponibles (fichiers structures/*.html)."""
    if not STRUCTURES_DIR.exists():
        return []
    return [{"name": f.stem, "file": f.name} for f in sorted(STRUCTURES_DIR.glob("*.html"))]


def get_structure(name: str) -> str | None:
    """HTML d'une structure de base. `name` = stem du fichier (sans .html). Anti path-traversal."""
    safe = Path(name).name  # retire tout chemin
    f = (STRUCTURES_DIR / f"{safe}.html").resolve()
    if STRUCTURES_DIR.resolve() not in f.parents or not f.exists():
        return None
    return f.read_text(encoding="utf-8")


def save_version(site: str, name: str, html: str, source: str = "", by: str = "ui") -> str:
    """Sauvegarde une version éditée (nommée + datée). Renvoie l'id."""
    _ensure_table()
    vid = str(uuid.uuid4())[:8]
    c = _conn()
    try:
        c.execute(
            "INSERT INTO html_templates (id, site_code, name, html, source, created_by, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            [vid, site, name, html, source, by, datetime.now(timezone.utc)],
        )
    finally:
        c.close()
    return vid


def list_versions(site: str) -> list[dict]:
    _ensure_table()
    c = _conn()
    try:
        rows = c.execute(
            "SELECT id, name, source, created_by, created_at FROM html_templates "
            "WHERE site_code=? ORDER BY created_at DESC", [site]
        ).fetchall()
    finally:
        c.close()
    return [{"id": r[0], "name": r[1], "source": r[2], "created_by": r[3], "created_at": str(r[4])}
            for r in rows]


def get_version(site: str, vid: str) -> dict | None:
    _ensure_table()
    c = _conn()
    try:
        r = c.execute(
            "SELECT id, name, html, source, created_at FROM html_templates WHERE site_code=? AND id=?",
            [site, vid]
        ).fetchone()
    finally:
        c.close()
    return {"id": r[0], "name": r[1], "html": r[2], "source": r[3], "created_at": str(r[4])} if r else None


def delete_version(site: str, vid: str) -> None:
    _ensure_table()
    c = _conn()
    try:
        c.execute("DELETE FROM html_templates WHERE site_code=? AND id=?", [site, vid])
    finally:
        c.close()


if __name__ == "__main__":
    print("structures:", list_structures())


def rename_version(site: str, vid: str, name: str) -> bool:
    """Renomme une version (message validé). Le nom est ce que lit le wizard campagne."""
    _ensure_table()
    c = _conn()
    try:
        c.execute("UPDATE html_templates SET name=? WHERE site_code=? AND id=?", [name, site, vid])
    finally:
        c.close()
    return True
