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

import contextvars
import os
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import psycopg2.pool

BASE_DIR = Path(__file__).resolve().parent.parent.parent   # …/genesis
ENV_FILE = BASE_DIR / ".env"
SCHEMA = "mass_mailing"

# ── Multi-clients (SaaS, 13/10/2026) ─────────────────────────────────────────
# Chaque client vit dans SON schéma PostgreSQL (`mmc_<slug>`) : campagnes, destinataires,
# suppressions, événements, file de jobs — tout est physiquement séparé. `mass_mailing`
# reste l'espace interne de Camille ET porte les tables de la plateforme (clients,
# utilisateurs, sessions), que seul ce module touche, toujours en nom qualifié.
# Le schéma courant est porté par une variable de contexte : posé par le middleware
# pour une requête, par le worker pour un tour de client. Défaut : `mass_mailing`.
_SCHEMA_VALIDE = re.compile(r"^(mass_mailing|mmc_[a-z][a-z0-9_]{1,40})$")
_SCHEMA_COURANT: contextvars.ContextVar[str] = contextvars.ContextVar("mm_schema", default=SCHEMA)


def schema_courant() -> str:
    return _SCHEMA_COURANT.get()


def verifier_schema(nom: str) -> str:
    if not _SCHEMA_VALIDE.match(nom or ""):
        raise ValueError(f"schéma refusé : {nom!r}")
    return nom


def poser_schema(nom: str) -> contextvars.Token:
    """Pose le schéma pour la suite du contexte (requête HTTP). Rend le jeton de remise."""
    return _SCHEMA_COURANT.set(verifier_schema(nom))


@contextmanager
def espace(nom: str):
    """`with pg.espace("mmc_zylio"):` — toutes les requêtes du bloc visent ce client."""
    jeton = _SCHEMA_COURANT.set(verifier_schema(nom))
    try:
        yield nom
    finally:
        _SCHEMA_COURANT.reset(jeton)

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
        # `public` reste en fin de chemin pour les types et fonctions (citext, pgcrypto) ; les
        # tables du client portant les mêmes noms, elles masquent toujours celles de Cheffer.
        self._cur.execute(f"SET search_path TO {verifier_schema(schema_courant())}, public")
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


def appliquer_schema(chemin: Path | None = None, schema: str | None = None) -> dict:
    """Rejoue `schema.sql` dans `schema` (défaut : le schéma courant). Idempotent."""
    cible = verifier_schema(schema or schema_courant())
    fichier = chemin or (BASE_DIR / "mass_mailing" / "schema.sql")
    sql = fichier.read_text()
    if cible != SCHEMA:
        # Seules ces deux lignes nomment le schéma : tout le reste est en nom relatif.
        sql = (sql.replace("CREATE SCHEMA IF NOT EXISTS mass_mailing;", f"CREATE SCHEMA IF NOT EXISTS {cible};")
                  .replace("SET search_path TO mass_mailing, public;", f"SET search_path TO {cible}, public;"))
        assert "mass_mailing" not in "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")), \
            "schema.sql nomme mass_mailing hors des deux lignes prévues"
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
        "WHERE table_schema = %(s)s ORDER BY table_name", {"s": cible})
    return {"ok": True, "schema": cible, "tables": [t["table_name"] for t in tables]}


def sante() -> dict:
    """Le module peut-il parler à sa base, et son schéma est-il en place ?"""
    try:
        s = schema_courant()
        n = valeur("SELECT count(*) FROM information_schema.tables "
                   "WHERE table_schema = %(s)s", {"s": s})
        return {"ok": True, "schema": s, "tables": int(n or 0)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erreur": str(e)[:200]}


if __name__ == "__main__":
    import json
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sante"
    print(json.dumps(appliquer_schema() if cmd == "migrer" else sante(),
                     ensure_ascii=False, indent=1))


# Liste de suppression : une raison plus forte remplace toujours une plus faible, jamais l'inverse
# (revue du 30/09 : une désinscription ou une plainte arrivée après un soft/hard bounce était perdue
# par ON CONFLICT DO NOTHING). Rang : plainte > désinscription = manuel > hard > fournisseur = import > soft.
_RANG = ("CASE {t}.reason WHEN 'complaint' THEN 5 WHEN 'unsubscribe' THEN 4 WHEN 'manual' THEN 4 "
         "WHEN 'hard_bounce' THEN 3 WHEN 'provider' THEN 2 WHEN 'import' THEN 2 ELSE 1 END")
SUPPRESSION_SUR_CONFLIT = (
    "ON CONFLICT (email_hash, scope, COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid)) "
    "DO UPDATE SET reason = EXCLUDED.reason, source = EXCLUDED.source, occurred_at = EXCLUDED.occurred_at, "
    "metadata = COALESCE(suppressions.metadata, '{}'::jsonb) || COALESCE(EXCLUDED.metadata, '{}'::jsonb) "
    f"WHERE {_RANG.format(t='suppressions')} < {_RANG.format(t='EXCLUDED')}")
# Un soft bounce (boîte pleine, inactive) est une quarantaine, pas un bannissement : ignoré après 60 jours.
SUPPRESSION_ACTIVE = "NOT ({t}.reason = 'soft_bounce' AND {t}.occurred_at < now() - interval '60 days')"


def meme_espace(fn):
    """Enveloppe `fn` pour qu'elle s'exécute dans le schéma COURANT, même depuis un autre
    fil (ThreadPoolExecutor ne transmet pas les variables de contexte). Sans elle, un lot
    d'un client écrirait ses statuts dans l'espace interne."""
    schema = schema_courant()

    def enveloppe(*a, **k):
        with espace(schema):
            return fn(*a, **k)
    return enveloppe
