#!/usr/bin/env python3
"""mass_mailing/infra/pg.py — accès PostgreSQL du module Mass Mailing.

COPIE AUTONOME, volontairement. Ce module n'importe rien de `scripts/` : c'est la
condition posée par Camille (2026-09-25) pour que Mass Mailing ne tombe pas quand
le reste de Genesis bouge — et le précédent est frais, `sweego_backend.py` faisant
redémarrer le dashboard vingt fois par jour depuis un `duckdb.connect()` en dur.

Tout passe par le schéma `mass_mailing`. Le `search_path` est posé à l'ouverture de
chaque connexion : aucune requête de ce module ne doit pouvoir toucher `public` par
inadvertance, où vivent les tables Cheffer.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import psycopg2.pool

BASE_DIR = Path(__file__).resolve().parent.parent.parent   # …/genesis
ENV_FILE = BASE_DIR / ".env"
SCHEMA = "mass_mailing"

_POOL: psycopg2.pool.ThreadedConnectionPool | None = None
_VERROU = threading.Lock()


def _dsn() -> str:
    """DSN lu dans l'environnement, puis dans `.env`. Jamais écrit dans un log."""
    dsn = os.environ.get("PG_DSN", "")
    if dsn:
        return dsn
    if ENV_FILE.exists():
        for ligne in ENV_FILE.read_text().splitlines():
            ligne = ligne.strip()
            if ligne.startswith("PG_DSN="):
                return ligne.split("=", 1)[1].strip().strip("'\"")
    raise RuntimeError("PG_DSN introuvable (ni environnement, ni .env)")


def _pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _POOL
    if _POOL is None:
        with _VERROU:
            if _POOL is None:
                _POOL = psycopg2.pool.ThreadedConnectionPool(1, 8, _dsn())
    return _POOL


class connexion:
    """Connexion du pool, `search_path` posé, rendue en sortie de bloc.

        with connexion() as c:
            c.execute("SELECT 1")

    Le commit est automatique en sortie normale, le rollback en cas d'exception :
    une campagne à moitié écrite est pire qu'une campagne pas écrite du tout.
    """

    def __init__(self, curseur_dict: bool = True):
        self._curseur_dict = curseur_dict
        self._conn = None
        self._cur = None

    def __enter__(self):
        self._conn = _pool().getconn()
        fabrique = psycopg2.extras.RealDictCursor if self._curseur_dict else None
        self._cur = self._conn.cursor(cursor_factory=fabrique)
        self._cur.execute(f"SET search_path TO {SCHEMA}, public")
        return self._cur

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            try:
                self._cur.close()
            finally:
                _pool().putconn(self._conn)
        return False


def lignes(sql: str, params: dict | tuple | None = None) -> list[dict]:
    with connexion() as c:
        c.execute(sql, params)
        return [dict(r) for r in c.fetchall()]


def ligne(sql: str, params: dict | tuple | None = None) -> dict | None:
    r = lignes(sql, params)
    return r[0] if r else None


def ecrire(sql: str, params: dict | tuple | None = None) -> int:
    with connexion(curseur_dict=False) as c:
        c.execute(sql, params)
        return c.rowcount


def valeur(sql: str, params: dict | tuple | None = None) -> Any:
    with connexion(curseur_dict=False) as c:
        c.execute(sql, params)
        r = c.fetchone()
        return r[0] if r else None


def appliquer_schema(chemin: Path | None = None) -> dict:
    """Rejoue `schema.sql`. Idempotent : conçu pour être lancé à chaque déploiement."""
    fichier = chemin or (BASE_DIR / "mass_mailing" / "schema.sql")
    sql = fichier.read_text()
    conn = _pool().getconn()
    try:
        with conn.cursor() as c:
            c.execute(sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool().putconn(conn)
    tables = lignes(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %(s)s ORDER BY table_name", {"s": SCHEMA})
    return {"ok": True, "schema": SCHEMA, "tables": [t["table_name"] for t in tables]}


def sante() -> dict:
    """Le module peut-il parler à sa base, et son schéma est-il en place ?"""
    try:
        n = valeur("SELECT count(*) FROM information_schema.tables "
                   "WHERE table_schema = %(s)s", {"s": SCHEMA})
        return {"ok": True, "schema": SCHEMA, "tables": int(n or 0)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erreur": str(e)[:200]}


if __name__ == "__main__":
    import json
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sante"
    print(json.dumps(appliquer_schema() if cmd == "migrer" else sante(),
                     ensure_ascii=False, indent=1))
