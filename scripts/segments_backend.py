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


# ── Stockage : PostgreSQL ─────────────────────────────────────────────────────
# Migré depuis DuckDB le 2026-08-19. Motif : `god_mode.duckdb` n'admet qu'un écrivain, et
# les segments sont lus à chaque ouverture de la page Campagnes comme de l'éditeur de
# campagne. Tant qu'ils vivaient dans ce fichier, un scrape ou un nettoyage rendait ces
# écrans indisponibles — sans compter les conflits de configuration dans le process de
# l'API. La table DuckDB reste en place, intacte, comme filet de retour arrière.
#
# L'identifiant public reste l'UUID historique, porté par `legacy_id` : les campagnes le
# stockent dans `params.segment_id`, les URL de l'interface le portent. La clé technique
# PostgreSQL (`id`) ne sort jamais du module.

def _dsn() -> str:
    for ligne in (BASE_DIR / ".env").read_text().splitlines():
        if ligne.startswith("PG_DSN="):
            return ligne.split("=", 1)[1].strip()
    raise RuntimeError("PG_DSN absent de .env")


_POOL_PG = None


def _conn():
    """Connexion PostgreSQL, prise dans un pool (les segments sont lus très souvent)."""
    global _POOL_PG
    import psycopg2.pool
    if _POOL_PG is None:
        _POOL_PG = psycopg2.pool.ThreadedConnectionPool(1, 6, _dsn())
    return _POOL_PG.getconn()


def _rendre(c):
    if _POOL_PG is not None:
        _POOL_PG.putconn(c)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_table() -> None:
    """Ne crée plus rien : le schéma PostgreSQL est appliqué une fois par `pg_schema.sql`.
    La fonction reste pour ne pas casser ses appelants."""
    return None


def save_count(sid: str, count: int) -> None:
    """Mémorise le dernier comptage réussi d'un segment (cache d'affichage)."""
    try:
        c = _conn()
        try:
            with c:
                with c.cursor() as cur:
                    cur.execute("UPDATE segments SET last_count=%s, last_count_at=now() "
                                "WHERE legacy_id=%s", [int(count), sid])
        finally:
            _rendre(c)
    except Exception:
        pass  # le cache d'affichage n'est jamais bloquant


# ── Règles ───────────────────────────────────────────────────────────────────
def empty_rules() -> dict:
    return {"match": "AND", "exclude_match": "AND",
            "include": {"sectors": [], "regions": [], "depts": [], "engagement": None},
            "exclude": {"sectors": [], "regions": [], "depts": [], "engagement": None}}


def normalize_rules(rules: dict | None) -> dict:
    """Complète et nettoie des règles partielles — l'UI peut n'envoyer que ce qu'elle utilise."""
    r = rules or {}
    out = empty_rules()
    out["match"] = "OR" if str(r.get("match", "AND")).upper() == "OR" else "AND"
    # Mode de combinaison de l'EXCLUSION, ajouté le 2026-08-20. Il était figé à « OU » :
    # ajouter « secteur immobilier » à une exclusion « a ouvert » retirait TOUT
    # l'immobilier, alors que l'intention évidente est « retirer les immobiliers QUI ont
    # ouvert ». Défaut « ET » : on décrit une sous-population à retirer. Les valeurs d'une
    # MÊME famille restent en OU (« exclure banque ou assurance »), comme à l'inclusion.
    out["exclude_match"] = "OR" if str(r.get("exclude_match", "AND")).upper() == "OR" else "AND"
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


def conflits_rules(rules: dict) -> list[str]:
    """Critères présents des DEUX CÔTÉS — inclus et exclus à la fois.

    Les deux cartes de l'éditeur se ressemblent, et on remplit volontiers la seconde comme
    la première « pour dire sur quelle population exclure ». Le résultat est un segment qui
    s'annule lui-même : tout ce qui entre par l'inclusion ressort par l'exclusion, et le
    compteur affiche 0 sans que rien n'explique pourquoi (cas remonté le 2026-08-20 :
    « secteur immobilier ET dépt 75 — SAUF secteur immobilier ou dépt 75 »).

    On rend la liste en clair, pour que l'interface puisse le dire avant d'enregistrer.
    """
    r = normalize_rules(rules)
    # En mode « ET », répéter un critère de l'inclusion dans l'exclusion est LÉGITIME :
    # « immobilier » + « a ouvert » côté exclusion veut dire « retire les immobiliers qui
    # ont ouvert ». Ce n'est un piège qu'en mode « OU », où le critère répété suffit à
    # tout faire sortir.
    if r.get("exclude_match", "AND") != "OR":
        return []
    inc, exc = r["include"], r["exclude"]
    conflits: list[str] = []
    for famille, etiquette in (("sectors", "secteur"), ("regions", "région"), ("depts", "dépt")):
        communs = sorted(set(inc.get(famille) or []) & set(exc.get(famille) or []))
        conflits += [f"{etiquette} {c}" for c in communs]
    if inc.get("engagement") and inc["engagement"] == exc.get("engagement"):
        conflits.append(ENGAGEMENT_LABELS.get(inc["engagement"], inc["engagement"]))
    return conflits


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
        colle = " et " if r.get("exclude_match", "AND") == "AND" else " ou "
        txt += " — SAUF " + colle.join(exc)
    return txt


# ── CRUD (PostgreSQL) ────────────────────────────────────────────────────────
# `legacy_id` porte l'UUID public — celui que les campagnes enregistrent et que l'URL de
# l'interface affiche. La clé technique de PostgreSQL ne sort jamais d'ici.
_COLS = ["legacy_id", "site_code", "name", "description", "rules", "locked",
         "created_by", "created_at", "updated_at", "last_count", "last_count_at"]
_SELECT = f"SELECT {', '.join(_COLS)} FROM segments"
_NOMS = ["id", "site_code", "name", "description", "rules", "locked",
         "created_by", "created_at", "updated_at", "last_count", "last_count_at"]


def _row(r) -> dict:
    d = dict(zip(_NOMS, r))
    # `rules` est du jsonb : psycopg2 le rend déjà décodé. On accepte les deux formes,
    # le temps que d'anciennes lignes en texte disparaissent.
    brut = d.get("rules")
    try:
        d["rules"] = normalize_rules(json.loads(brut) if isinstance(brut, str) else brut)
    except Exception:
        d["rules"] = empty_rules()
    d["locked"] = bool(d.get("locked"))
    for k in ("created_at", "updated_at", "last_count_at"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    d["summary"] = describe_rules(d["rules"])
    d["reference"] = reference(d.get("id") or "")
    return d


def _lire(sql: str, params: list) -> list:
    c = _conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        c.rollback()
        _rendre(c)


def list_segments(site: str) -> list[dict]:
    rows = _lire(_SELECT + " WHERE site_code=%s ORDER BY created_at DESC", [site])
    usages = _usages()
    out = []
    for r in rows:
        d = _row(r)
        d["used_by"] = usages.get(d["id"], [])
        out.append(d)
    return out


def get_segment(sid: str) -> dict | None:
    rows = _lire(_SELECT + " WHERE legacy_id=%s", [sid])
    return _row(rows[0]) if rows else None


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
    c = _conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(
                    "INSERT INTO segments (id, legacy_id, site_code, name, description, "
                    "rules, locked, created_by, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), %s, %s, %s, %s, %s::jsonb, false, %s, now(), now())",
                    [sid, site, name, (description or "").strip(),
                     json.dumps(normalize_rules(rules), ensure_ascii=False), by])
    finally:
        _rendre(c)
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
        sets.append("name=%s"); vals.append(nm)
    if "description" in patch:
        sets.append("description=%s"); vals.append((patch.get("description") or "").strip())
    if "rules" in patch:
        ok, err = validate_rules(patch["rules"])
        if not ok:
            return {"ok": False, "error": err}
        sets.append("rules=%s::jsonb")
        vals.append(json.dumps(normalize_rules(patch["rules"]), ensure_ascii=False))
    if "locked" in patch:
        sets.append("locked=%s"); vals.append(bool(patch["locked"]))
    if not sets:
        return {"ok": False, "error": "aucun champ à modifier"}
    sets.append("updated_at=now()")

    c = _conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(f"UPDATE segments SET {', '.join(sets)} WHERE legacy_id=%s",
                            vals + [sid])
    finally:
        _rendre(c)
    return {"ok": True, "segment": get_segment(sid)}


# ── Identité technique et usage ──────────────────────────────────────────────
# L'identifiant d'un segment est son UUID, et lui seul : c'est ce que les campagnes
# enregistrent dans `params.segment_id`, et c'est sur lui que `campaign_engine` retrouve
# les règles au moment du dispatch. Deux conséquences, appliquées ici :
#
#   1. La référence lisible (« SEG-3F9A21 ») est DÉRIVÉE de l'UUID, jamais stockée. Un
#      second identifiant rangé dans une colonne finit toujours par diverger du premier.
#   2. Une duplication crée un NOUVEL UUID. Copier un segment sans changer d'identifiant
#      ferait pointer deux objets modifiables sur la même clé de campagne.
#
# Et surtout : on ne supprime pas un segment qu'une campagne utilise. Le moteur refuse de
# dispatcher quand la cible a disparu (« segment introuvable — campagne bloquée ») ; le
# problème se découvrait alors le matin de l'envoi. Il se découvre maintenant au clic.

def reference(sid: str) -> str:
    """Référence courte affichable, dérivée de l'UUID. Jamais utilisée comme clé."""
    return "SEG-" + (sid or "").replace("-", "")[:6].upper()


def _usages(sids: list[str] | None = None) -> dict[str, list[dict]]:
    """Campagnes pointant sur chaque segment, en une requête."""
    try:
        rows = _lire("""
            SELECT params->>'segment_id' AS sid, COALESCE(legacy_id, id::text), name, status
            FROM campaigns
            WHERE params->>'segment_id' IS NOT NULL
        """, [])
    except Exception:
        return {}
    out: dict[str, list[dict]] = {}
    for sid, cid, nom, statut in rows:
        if sids is not None and sid not in sids:
            continue
        out.setdefault(sid, []).append({"id": cid, "name": nom, "status": statut})
    return out


def usage(sid: str) -> list[dict]:
    """Les campagnes qui s'appuient sur ce segment (vide si aucune)."""
    return _usages([sid]).get(sid, [])


def duplicate_segment(sid: str, site: str, by: str = "ui") -> dict:
    """Copie un segment sous un nouvel identifiant.

    La copie arrive TOUJOURS déverrouillée : on duplique précisément pour modifier. Le
    nom reçoit un suffixe numéroté, parce que trois « (copie) » dans une liste ne se
    distinguent plus les uns des autres.
    """
    seg = get_segment(sid)
    if not seg or seg["site_code"] != site:
        return {"ok": False, "error": "segment introuvable"}

    existants = {s["name"] for s in list_segments(site)}
    base = f"{seg['name']} (copie)"
    nom, n = base, 2
    while nom in existants:
        nom, n = f"{base} {n}", n + 1

    return create_segment(site, nom, seg["rules"],
                          description=seg.get("description") or "", by=by)


def delete_segment(sid: str, site: str) -> dict:
    seg = get_segment(sid)
    if not seg or seg["site_code"] != site:
        return {"ok": False, "error": "segment introuvable"}
    if seg["locked"]:
        return {"ok": False, "error": "segment verrouillé — déverrouille-le avant de le supprimer"}
    # Une campagne dont la cible a disparu ne bascule pas sur un autre ciblage : elle
    # s'arrête au dispatch suivant. On refuse donc ici, pendant qu'on peut encore choisir.
    utilise = usage(sid)
    if utilise:
        noms = ", ".join(u["name"] for u in utilise[:3])
        return {"ok": False, "error": f"utilisé par {len(utilise)} campagne(s) : {noms}"
                                      " — duplique-le ou retire-le de ces campagnes d'abord",
                "used_by": utilise}
    c = _conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute("DELETE FROM segments WHERE legacy_id=%s", [sid])
    finally:
        _rendre(c)
    return {"ok": True, "id": sid}


if __name__ == "__main__":
    site = sys.argv[1] if len(sys.argv) > 1 else "lcr"
    for s in list_segments(site):
        lock = "🔒" if s["locked"] else "  "
        print(f"{lock} {s['id']}  {s['name']:28} {s['summary']}")
