#!/usr/bin/env python3
"""
segments_backend.py — Segments de ciblage réutilisables.

Un segment = un nom + des RÈGLES enregistrées, identifié par un UUID unique et stable.
On le crée une fois, on le réutilise dans les campagnes, on le verrouille quand il est
validé pour qu'il ne bouge plus sous les campagnes qui s'en servent.

Modèle de règles — volontairement minimal, lisible par un humain :

    {
      "match": "AND",                 # comment combiner les FAMILLES d'inclusion
      "include": {
        "sectors":    ["immobilier"], # valeurs d'une même famille = toujours OU
        "regions":    ["93"],
        "depts":      ["13", "06"],
        "engagement": "open_30"       # null | open_30 | open_180 | open_any | click_any
      },
      "exclude": {                    # tout contact qui matche UNE exclusion est retiré
        "sectors": [], "regions": [], "depts": [], "engagement": null
      }
    }

Trois règles à retenir :
  1. À l'intérieur d'une famille, les valeurs sont en OU (secteur A **ou** B).
  2. Entre familles d'inclusion, c'est `match` qui décide : ET (toutes) ou OU (au moins une).
  3. L'exclusion est toujours soustraite, quel que soit `match`.

Les filtres d'éligibilité du pool (email nettoyé Mailnjoy, non blacklisté, hors cooldown)
s'appliquent EN PLUS et ne sont jamais négociables — un segment ne peut pas les contourner.

Stockage : table `segments` dans data/god_mode.duckdb (comme les campagnes), pour ne pas
ajouter d'écritures sur contacts.duckdb qui est déjà très sollicité en lecture.
"""
from __future__ import annotations

import json
import sys
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"

MATCH_MODES = ("AND", "OR")
ENGAGEMENTS = ("open_30", "open_180", "open_any", "click_any")
FAMILIES = ("sectors", "regions", "depts")

ENGAGEMENT_LABELS = {
    "open_30": "a ouvert (30 j)",
    "open_180": "a ouvert (180 j)",
    "open_any": "a déjà ouvert",
    "click_any": "a déjà cliqué",
}


def _conn():
    return duckdb.connect(str(GOD_DB))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_table() -> None:
    c = _conn()
    try:
        c.execute(
            """CREATE TABLE IF NOT EXISTS segments (
                id          VARCHAR,      -- UUID v4 unique et stable
                site_code   VARCHAR,
                name        VARCHAR,
                description VARCHAR,
                rules       VARCHAR,      -- JSON du modèle décrit en tête de fichier
                locked      BOOLEAN,      -- verrouillé = non modifiable, non supprimable
                created_by  VARCHAR,
                created_at  TIMESTAMP,
                updated_at  TIMESTAMP,
                PRIMARY KEY (id)
            )"""
        )
        # Dernier comptage connu : le pool est verrouillé dès qu'un scrape ou le nettoyage
        # horaire écrit (DuckDB = 1 écrivain OU des lecteurs, jamais les deux). Plutôt que
        # d'afficher un tiret, on ressert la dernière valeur en la datant.
        cols = {r[1] for r in c.execute("PRAGMA table_info(segments)").fetchall()}
        for col, typ in (("last_count", "INTEGER"), ("last_count_at", "TIMESTAMP")):
            if col not in cols:
                c.execute(f"ALTER TABLE segments ADD COLUMN {col} {typ}")
    finally:
        c.close()


def save_count(sid: str, count: int) -> None:
    """Mémorise le dernier comptage réussi d'un segment (cache d'affichage)."""
    try:
        c = _conn()
        try:
            c.execute("UPDATE segments SET last_count=?, last_count_at=? WHERE id=?",
                      [int(count), _now(), sid])
        finally:
            c.close()
    except Exception:
        pass  # le cache d'affichage n'est jamais bloquant


# ── Règles ───────────────────────────────────────────────────────────────────
def empty_rules() -> dict:
    return {"match": "AND",
            "include": {"sectors": [], "regions": [], "depts": [], "engagement": None},
            "exclude": {"sectors": [], "regions": [], "depts": [], "engagement": None}}


def normalize_rules(rules: dict | None) -> dict:
    """Complète et nettoie des règles partielles — l'UI peut n'envoyer que ce qu'elle utilise."""
    r = rules or {}
    out = empty_rules()
    out["match"] = "OR" if str(r.get("match", "AND")).upper() == "OR" else "AND"
    for side in ("include", "exclude"):
        src = r.get(side) or {}
        for fam in FAMILIES:
            vals = src.get(fam) or []
            if isinstance(vals, str):
                vals = [vals]
            # dédoublonnage en conservant l'ordre de saisie
            seen, clean = set(), []
            for v in vals:
                v = str(v).strip()
                if v and v not in seen:
                    seen.add(v); clean.append(v)
            out[side][fam] = clean
        eng = (src.get("engagement") or "").strip() or None
        out[side]["engagement"] = eng
    return out


def validate_rules(rules: dict) -> tuple[bool, str]:
    """Un segment sans aucun critère d'inclusion viserait tout le pool : on le refuse."""
    r = normalize_rules(rules)
    if r["match"] not in MATCH_MODES:
        return False, "mode de combinaison invalide (AND ou OR)"
    for side in ("include", "exclude"):
        eng = r[side]["engagement"]
        if eng and eng not in ENGAGEMENTS:
            return False, f"critère d'engagement inconnu : {eng}"
    inc = r["include"]
    if not any(inc[f] for f in FAMILIES) and not inc["engagement"]:
        return False, "au moins un critère d'inclusion est requis"
    return True, ""


def describe_rules(rules: dict) -> str:
    """Résumé lisible d'un segment, affiché sur sa carte et dans le récap de campagne."""
    r = normalize_rules(rules)
    lib = {"sectors": "secteur", "regions": "région", "depts": "dépt"}

    def side_txt(side: str) -> list[str]:
        bits = []
        for fam in FAMILIES:
            vals = r[side][fam]
            if vals:
                bits.append(f"{lib[fam]} {' ou '.join(vals)}")
        if r[side]["engagement"]:
            bits.append(ENGAGEMENT_LABELS.get(r[side]["engagement"], r[side]["engagement"]))
        return bits

    inc = side_txt("include")
    txt = (f" {'ET' if r['match'] == 'AND' else 'OU'} ").join(inc) if inc else "tout le pool"
    exc = side_txt("exclude")
    if exc:
        txt += " — SAUF " + " ou ".join(exc)
    return txt


# ── CRUD ─────────────────────────────────────────────────────────────────────
_COLS = ["id", "site_code", "name", "description", "rules", "locked",
         "created_by", "created_at", "updated_at", "last_count", "last_count_at"]
_SELECT = f"SELECT {', '.join(_COLS)} FROM segments"


def _row(r) -> dict:
    d = dict(zip(_COLS, r))
    try:
        d["rules"] = normalize_rules(json.loads(d["rules"]) if d.get("rules") else None)
    except Exception:
        d["rules"] = empty_rules()
    d["locked"] = bool(d.get("locked"))
    for k in ("created_at", "updated_at", "last_count_at"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    d["summary"] = describe_rules(d["rules"])
    return d


def list_segments(site: str) -> list[dict]:
    _ensure_table()
    c = _conn()
    try:
        rows = c.execute(_SELECT + " WHERE site_code=? ORDER BY created_at DESC", [site]).fetchall()
    finally:
        c.close()
    return [_row(r) for r in rows]


def get_segment(sid: str) -> dict | None:
    _ensure_table()
    c = _conn()
    try:
        r = c.execute(_SELECT + " WHERE id=?", [sid]).fetchone()
    finally:
        c.close()
    return _row(r) if r else None


def create_segment(site: str, name: str, rules: dict, description: str = "",
                   by: str = "ui") -> dict:
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "nom requis"}
    ok, err = validate_rules(rules)
    if not ok:
        return {"ok": False, "error": err}
    # UUID v4 complet : identifiant unique et stable, jamais réutilisé même après suppression.
    sid = str(_uuid.uuid4())
    _ensure_table()
    c = _conn()
    try:
        c.execute("INSERT INTO segments (id, site_code, name, description, rules, locked, "
                  "created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                  [sid, site, name, (description or "").strip(),
                   json.dumps(normalize_rules(rules), ensure_ascii=False),
                   False, by, _now(), _now()])
    finally:
        c.close()
    return {"ok": True, "id": sid, "segment": get_segment(sid)}


def update_segment(sid: str, site: str, patch: dict, by: str = "ui") -> dict:
    """Modifie un segment. Un segment VERROUILLÉ est refusé : des campagnes s'appuient
    peut-être dessus, on ne change pas leur cible dans leur dos."""
    seg = get_segment(sid)
    if not seg or seg["site_code"] != site:
        return {"ok": False, "error": "segment introuvable"}
    if seg["locked"] and "locked" not in patch:
        return {"ok": False, "error": "segment verrouillé — déverrouille-le pour le modifier"}

    sets, vals = [], []
    if "name" in patch:
        nm = (patch.get("name") or "").strip()
        if not nm:
            return {"ok": False, "error": "nom requis"}
        sets.append("name=?"); vals.append(nm)
    if "description" in patch:
        sets.append("description=?"); vals.append((patch.get("description") or "").strip())
    if "rules" in patch:
        ok, err = validate_rules(patch["rules"])
        if not ok:
            return {"ok": False, "error": err}
        sets.append("rules=?"); vals.append(json.dumps(normalize_rules(patch["rules"]), ensure_ascii=False))
    if "locked" in patch:
        sets.append("locked=?"); vals.append(bool(patch["locked"]))
    if not sets:
        return {"ok": False, "error": "aucun champ à modifier"}
    sets.append("updated_at=?"); vals.append(_now())

    c = _conn()
    try:
        c.execute(f"UPDATE segments SET {', '.join(sets)} WHERE id=?", vals + [sid])
    finally:
        c.close()
    return {"ok": True, "segment": get_segment(sid)}


def delete_segment(sid: str, site: str) -> dict:
    seg = get_segment(sid)
    if not seg or seg["site_code"] != site:
        return {"ok": False, "error": "segment introuvable"}
    if seg["locked"]:
        return {"ok": False, "error": "segment verrouillé — déverrouille-le avant de le supprimer"}
    c = _conn()
    try:
        c.execute("DELETE FROM segments WHERE id=?", [sid])
    finally:
        c.close()
    return {"ok": True, "id": sid}


if __name__ == "__main__":
    site = sys.argv[1] if len(sys.argv) > 1 else "lcr"
    for s in list_segments(site):
        lock = "🔒" if s["locked"] else "  "
        print(f"{lock} {s['id']}  {s['name']:28} {s['summary']}")
