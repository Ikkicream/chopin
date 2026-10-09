#!/usr/bin/env python3
"""duck_pg.py — god_mode.duckdb servi par PostgreSQL (lot 3 de la sortie de DuckDB, 08/10).

`god_mode.duckdb` porte ~35 tables lues et écrites par une trentaine de fichiers, avec leur
propre SQL. Les réécrire un par un aurait pris des jours et autant d'occasions d'erreur.
On garde donc leur SQL, et on change ce qu'il y a SOUS la connexion :

  - les tables vivent dans le schéma PostgreSQL `godmode`, même structure, même ordre de
    colonnes (les INSERT positionnels continuent de marcher) ;
  - `scrappe*` n'y sont PAS : elles résolvent vers `public` (lot 1, déjà dans PostgreSQL) ;
  - `ConnexionDuckPG` se présente comme une connexion DuckDB (`execute(...).fetchone()`,
    `fetchall`, `executemany`, `description`, `close`) et traduit au passage les tournures
    propres à DuckDB (voir `traduire`).

Bascule : `GODMODE_PG=1` dans .env. Les ouvertures passent par `connecter(chemin)` — qui
rend une connexion DuckDB ordinaire pour toute autre base, ou si la bascule est éteinte.

Usage : python3 scripts/duck_pg.py schema | copier | etat | test "<sql>"
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"
SCHEMA = "godmode"
# Déjà dans PostgreSQL (public) depuis le lot 1 : ne pas les dupliquer dans `godmode`.
TABLES_PUBLIQUES = {"scrappe", "scrappe_pending", "scrappe_rejected"}


def actif() -> bool:
    try:
        for ligne in (BASE_DIR / ".env").read_text().splitlines():
            if ligne.startswith("GODMODE_PG="):
                return ligne.split("=", 1)[1].strip() == "1"
    except Exception:  # noqa: BLE001
        pass
    return False


def _est_god(chemin) -> bool:
    try:
        return Path(str(chemin)).name == "god_mode.duckdb"
    except Exception:  # noqa: BLE001
        return False


def connecter(chemin=GOD_DB, read_only: bool = False, **_):
    """Remplace `duckdb.connect(GOD_DB, ...)` : PostgreSQL si la bascule est active."""
    if _est_god(chemin) and actif():
        return ConnexionDuckPG()
    import duckdb
    return duckdb.connect(str(chemin), read_only=read_only)


# ── Traduction DuckDB → PostgreSQL ────────────────────────────────────────────
_FMT = {"%Y": "YYYY", "%m": "MM", "%d": "DD", "%H": "HH24", "%M": "MI", "%S": "SS",
        "%y": "YY", "%j": "DDD"}


def _placeholders(sql: str) -> str:
    """`?` → `%s` et `%` → `%%`, HORS chaînes littérales, identifiants et commentaires."""
    out, i, n = [], 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'" and j + 1 < n and sql[j + 1] == "'":
                    j += 2
                    continue
                if sql[j] == "'":
                    break
                j += 1
            out.append(sql[i:j + 1].replace("%", "%%"))
            i = j + 1
        elif ch == '"':
            j = sql.find('"', i + 1)
            j = n - 1 if j < 0 else j
            out.append(sql[i:j + 1])
            i = j + 1
        elif sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j < 0 else j
            i = j
        elif ch == "?":
            out.append("%s")
            i += 1
        elif ch == "%":
            out.append("%%")
            i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _json_chemin(chemin: str) -> str:
    parts = [p for p in chemin.lstrip("$").lstrip(".").split(".") if p]
    return "{" + ",".join(parts) + "}"


def traduire(sql: str) -> str:
    s = sql
    # json_extract_string(x, '$.a.b') → (x)::jsonb #>> '{a,b}'
    s = re.sub(r"json_extract_string\(\s*([^,()]+(?:\([^()]*\))?)\s*,\s*'([^']+)'\s*\)",
               lambda m: f"(({m.group(1)})::jsonb #>> '{_json_chemin(m.group(2))}')", s,
               flags=re.I)
    s = re.sub(r"json_extract\(\s*([^,()]+(?:\([^()]*\))?)\s*,\s*'([^']+)'\s*\)",
               lambda m: f"(({m.group(1)})::jsonb #> '{_json_chemin(m.group(2))}')", s,
               flags=re.I)
    # strftime(col, '%Y-%m') → to_char(col, 'YYYY-MM')
    def _strf(m):
        fmt = m.group(2)
        for k, v in _FMT.items():
            fmt = fmt.replace(k, v)
        return f"to_char({m.group(1)}, '{fmt}')"
    s = re.sub(r"strftime\(\s*([^,]+?)\s*,\s*'([^']+)'\s*\)", _strf, s, flags=re.I)
    # INTERVAL 7 DAY / INTERVAL (n) DAY → INTERVAL '7 day'
    s = re.sub(r"INTERVAL\s+\(?\s*(\d+)\s*\)?\s+(DAY|HOUR|MINUTE|SECOND|MONTH|YEAR)S?\b",
               lambda m: f"INTERVAL '{m.group(1)} {m.group(2).lower()}'", s, flags=re.I)
    # epoch(x) → extract(epoch from x)
    s = re.sub(r"\bepoch\(\s*([^()]+)\)", r"extract(epoch from \1)", s, flags=re.I)
    # today() → current_date
    s = re.sub(r"\btoday\(\)", "current_date", s, flags=re.I)
    # Types des DDL (les tables existent déjà ; la commande doit seulement rester valide)
    if re.match(r"\s*(CREATE|ALTER)\s", s, flags=re.I):
        s = re.sub(r"\bDOUBLE\b(?!\s+PRECISION)", "double precision", s, flags=re.I)
        s = re.sub(r"\bJSON\b", "text", s)
        s = re.sub(r"\bUBIGINT\b", "bigint", s, flags=re.I)
        s = re.sub(r"\bHUGEINT\b", "numeric", s, flags=re.I)
    return s


# ── La connexion ──────────────────────────────────────────────────────────────
class ConnexionDuckPG:
    def __init__(self):
        import pool_pg
        self._pool = pool_pg
        self._c = pool_pg._conn()
        with self._c.cursor() as cur:
            cur.execute(f"SET search_path TO {SCHEMA}, public")
        self._c.commit()
        self._cur = None
        self.description = None

    # Réécritures qui demandent le catalogue (clé primaire, colonnes).
    def _colonnes(self, table: str) -> list[str]:
        with self._c.cursor() as cur:
            cur.execute("""SELECT column_name FROM information_schema.columns
                           WHERE table_name = %s AND table_schema IN (%s, 'public')
                           ORDER BY (table_schema = %s) DESC, ordinal_position""",
                        (table, SCHEMA, SCHEMA))
            vus, out = set(), []
            for (c,) in cur.fetchall():
                if c not in vus:
                    vus.add(c)
                    out.append(c)
            return out

    def _cle(self, table: str) -> list[str]:
        with self._c.cursor() as cur:
            cur.execute("""SELECT a.attname FROM pg_index i
                           JOIN pg_class t ON t.oid = i.indrelid
                           JOIN pg_namespace n ON n.oid = t.relnamespace
                           JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey)
                           WHERE t.relname = %s AND n.nspname IN (%s, 'public')
                             AND (i.indisprimary OR i.indisunique)
                           ORDER BY i.indisprimary DESC""", (table, SCHEMA))
            return [r[0] for r in cur.fetchall()]

    def _reecrire(self, sql: str) -> str | tuple:
        st = sql.strip()
        m = re.match(r"(?is)(PRAGMA\s+table_info\(\s*'?\"?(\w+)\"?'?\s*\)|DESCRIBE\s+(\w+))\s*;?$", st)
        if m:
            table = m.group(2) or m.group(3)
            pragma = st.upper().startswith("PRAGMA")
            with self._c.cursor() as cur:
                cur.execute("""SELECT ordinal_position - 1, column_name, data_type,
                                      is_nullable = 'NO', column_default
                               FROM information_schema.columns
                               WHERE table_name = %s AND table_schema IN (%s, 'public')
                               ORDER BY ordinal_position""", (table, SCHEMA))
                rows = cur.fetchall()
            if pragma:
                return ("rows", [(r[0], r[1], r[2], r[3], r[4], False) for r in rows])
            return ("rows", [(r[1], r[2], "NO" if r[3] else "YES", None, r[4], None) for r in rows])
        m = re.match(r"(?is)INSERT\s+OR\s+(REPLACE|IGNORE)\s+INTO\s+(\w+)\s*(\([^)]*\))?\s*(VALUES.*|SELECT.*)$", st)
        if m:
            mode, table, cols, reste = m.group(1).upper(), m.group(2), m.group(3), m.group(4)
            colonnes = ([c.strip() for c in cols[1:-1].split(",")] if cols
                        else self._colonnes(table))
            base = f"INSERT INTO {table} ({', '.join(colonnes)}) {reste.rstrip(';')}"
            cle = self._cle(table)
            if mode == "IGNORE" or not cle:
                return base + " ON CONFLICT DO NOTHING"
            maj = ", ".join(f"{c} = EXCLUDED.{c}" for c in colonnes if c not in cle)
            return base + (f" ON CONFLICT ({', '.join(cle)}) DO UPDATE SET {maj}" if maj
                           else f" ON CONFLICT ({', '.join(cle)}) DO NOTHING")
        return sql

    def execute(self, sql: str, params=None):
        r = self._reecrire(sql)
        if isinstance(r, tuple):
            self._lignes, self.description = r[1], [("c",)] * 6
            self._cur = None
            return self
        self._lignes = None
        sql_pg = traduire(r)
        sql_pg = _placeholders(sql_pg) if params else sql_pg
        if isinstance(params, dict):
            params = list(params.values())
        self._cur = self._c.cursor()
        try:
            self._cur.execute(sql_pg, list(params) if params else None)
            self._c.commit()
        except Exception:
            self._c.rollback()
            with self._c.cursor() as cur:
                cur.execute(f"SET search_path TO {SCHEMA}, public")
            self._c.commit()
            raise
        self.description = self._cur.description
        return self

    def executemany(self, sql: str, rows):
        for r in rows:
            self.execute(sql, r)
        return self

    @staticmethod
    def _texte(row):
        import uuid as _u
        return tuple(str(v) if isinstance(v, _u.UUID) else v for v in row) if row else row

    def fetchone(self):
        if self._lignes is not None:
            return self._lignes.pop(0) if self._lignes else None
        return self._texte(self._cur.fetchone()) if self._cur and self._cur.description else None

    def fetchall(self):
        if self._lignes is not None:
            out, self._lignes = self._lignes, []
            return out
        return ([self._texte(r) for r in self._cur.fetchall()]
                if self._cur and self._cur.description else [])

    def fetchmany(self, n=1000):
        if self._lignes is not None:
            out, self._lignes = self._lignes[:n], self._lignes[n:]
            return out
        return ([self._texte(r) for r in self._cur.fetchmany(n)]
                if self._cur and self._cur.description else [])

    def commit(self):
        self._c.commit()

    def rollback(self):
        self._c.rollback()

    def close(self):
        try:
            self._c.rollback()
            with self._c.cursor() as cur:
                cur.execute("SET search_path TO public")
            self._c.commit()
        finally:
            self._pool._rendre(self._c)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


# ── Schéma et reprise ─────────────────────────────────────────────────────────
_TYPES = {"VARCHAR": "text", "TIMESTAMP": "timestamp", "TIMESTAMP WITH TIME ZONE": "timestamptz",
          "DOUBLE": "double precision", "FLOAT": "real", "JSON": "text", "BOOLEAN": "boolean",
          "INTEGER": "integer", "BIGINT": "bigint", "SMALLINT": "smallint", "DATE": "date",
          "UBIGINT": "bigint", "HUGEINT": "numeric", "TINYINT": "smallint", "UUID": "uuid",
          "BLOB": "bytea", "TIME": "time", "DECIMAL": "numeric", "INTERVAL": "interval"}


def _type_pg(t: str) -> str:
    t = (t or "").upper()
    if t.endswith("[]"):
        return "text"   # tableaux DuckDB : sérialisés en texte, comme JSON
    if t.startswith("DECIMAL"):
        return "numeric"
    return _TYPES.get(t, "text")


def _defaut_pg(d) -> str:
    if d is None:
        return ""
    d = str(d)
    if "nextval" in d:
        return f" DEFAULT {d}"
    if d.upper() in ("CURRENT_TIMESTAMP", "NOW()", "CURRENT_DATE"):
        return f" DEFAULT {d}"
    if re.fullmatch(r"-?\d+(\.\d+)?|true|false|'[^']*'", d, flags=re.I):
        return f" DEFAULT {d}"
    if d.upper().startswith("CAST("):
        m = re.match(r"CAST\('?(.*?)'? AS (\w+)\)", d, flags=re.I)
        if m:
            return f" DEFAULT '{m.group(1)}'"
    return ""


def _duck():
    """Source de la copie. `DUCK_PG_SOURCE` permet de partir d'une copie du fichier quand
    un scrape tient le verrou (création du schéma) ; la reprise des données, elle, se fait
    sur le vrai fichier, bases à l'arrêt."""
    import os
    import duckdb
    return duckdb.connect(os.environ.get("DUCK_PG_SOURCE") or str(GOD_DB), read_only=True)


def tables_duck(d) -> list[str]:
    return [r[0] for r in d.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' "
        "AND table_type = 'BASE TABLE' ORDER BY 1").fetchall() if r[0] not in TABLES_PUBLIQUES]


def creer_schema() -> dict:
    import pool_pg
    d = _duck()
    faites = []
    try:
        pool_pg._ecrire(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        for (seq,) in d.execute("SELECT sequence_name FROM duckdb_sequences()").fetchall():
            pool_pg._ecrire(f"CREATE SEQUENCE IF NOT EXISTS {SCHEMA}.{seq}")
        for t in tables_duck(d):
            cols = d.execute("""SELECT column_name, data_type, column_default, is_nullable
                                FROM information_schema.columns WHERE table_name = ?
                                ORDER BY ordinal_position""", [t]).fetchall()
            pk = [r[0] for r in d.execute(
                "SELECT unnest(constraint_column_names) FROM duckdb_constraints() "
                "WHERE table_name = ? AND constraint_type = 'PRIMARY KEY'", [t]).fetchall()]
            uniq = [r[0] for r in d.execute(
                "SELECT constraint_column_names FROM duckdb_constraints() "
                "WHERE table_name = ? AND constraint_type = 'UNIQUE'", [t]).fetchall()]
            defs = [f'"{c}" {_type_pg(ty)}{_defaut_pg(df).replace("nextval(" + chr(39), "nextval(" + chr(39) + SCHEMA + ".")}'
                    for c, ty, df, nul in cols]
            if pk:
                defs.append(f"PRIMARY KEY ({', '.join(chr(34) + c + chr(34) for c in pk)})")
            for u in uniq:
                if list(u) != pk:
                    defs.append(f"UNIQUE ({', '.join(chr(34) + c + chr(34) for c in u)})")
            pool_pg._ecrire(f"CREATE TABLE IF NOT EXISTS {SCHEMA}.{t} ({', '.join(defs)})")
            faites.append(t)
    finally:
        d.close()
    return {"tables": len(faites)}


def copier() -> dict:
    """Recopie chaque table (TRUNCATE puis COPY) — à lancer bases à l'arrêt."""
    import io
    import csv
    import pool_pg
    d = _duck()
    bilan = {}
    try:
        c = pool_pg._conn()
        try:
            for t in tables_duck(d):
                cur_d = d.execute(f'SELECT * FROM "{t}"')
                cols = [x[0] for x in cur_d.description]
                buf = io.StringIO()
                w = csv.writer(buf)
                n = 0
                while True:
                    paquet = cur_d.fetchmany(5000)
                    if not paquet:
                        break
                    for r in paquet:
                        w.writerow([("\\N" if v is None else
                                     json.dumps(v, default=str) if isinstance(v, (dict, list)) else
                                     ("true" if v else "false") if isinstance(v, bool) else v)
                                    for v in r])
                        n += 1
                buf.seek(0)
                with c.cursor() as cur:
                    cur.execute(f"TRUNCATE {SCHEMA}.{t}")
                    cur.copy_expert(f"COPY {SCHEMA}.{t} ({', '.join(chr(34) + x + chr(34) for x in cols)}) "
                                    f"FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
                c.commit()
                bilan[t] = n
            for (seq, val) in d.execute(
                    "SELECT sequence_name, last_value FROM duckdb_sequences()").fetchall():
                with c.cursor() as cur:
                    cur.execute(f"SELECT setval('{SCHEMA}.{seq}', %s)", (max(1, int(val or 1)),))
                c.commit()
        finally:
            pool_pg._rendre(c)
    finally:
        d.close()
    return bilan


def etat() -> dict:
    import pool_pg
    r = pool_pg._q("""SELECT relname, n_live_tup FROM pg_stat_user_tables
                      WHERE schemaname = %(s)s ORDER BY relname""", {"s": SCHEMA})
    return {"actif": actif(), "tables": {k: int(v) for k, v in r}}


if __name__ == "__main__":
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    cmd = sys.argv[1] if len(sys.argv) > 1 else "etat"
    if cmd == "schema":
        print(json.dumps(creer_schema()))
    elif cmd == "copier":
        print(json.dumps(copier(), default=str))
    elif cmd == "test":
        c = ConnexionDuckPG()
        try:
            print(c.execute(sys.argv[2]).fetchall()[:10])
        finally:
            c.close()
    else:
        print(json.dumps(etat(), default=str))
