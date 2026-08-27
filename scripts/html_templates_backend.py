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
    # `duck_ouverture.ouvrir` et non `duckdb.connect` : ce module est dans le CHEMIN DU
    # DISPATCH — résoudre le message, le contrôler, lire les modèles. Une ouverture directe
    # échoue au premier verrou tenu par un scrape, et le lot entier est refusé : c'est ce
    # qui a fait échouer la campagne du 2026-08-27 à 10h30, « Could not set lock on file
    # god_mode.duckdb ». Ces lectures ne sont pas des écritures de garantie — elles peuvent
    # attendre une seconde et demie, et se contenter d'un accès en lecture seule.
    import duck_ouverture
    return duck_ouverture.ouvrir(GOD_DB)


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


# ── Message unifié pour une campagne (3 sources) ─────────────────────────────────
# Le wizard campagne peut piocher dans : Templates (structures/newsletters),
# Messages validés (versions), ou Cold emails (email_templates, par secteur).
# On encode la source dans le message_id : "struct:<name>" | "cold:<sector>:<kind>" | "ver:<id>".
def campaign_message_options(site: str, auto: bool = False) -> dict:
    """Liste groupée des messages sélectionnables pour une campagne.

    `auto=True` ajoute « le cold email du secteur du contact » — réservé aux SCÉNARIOS.
    Une campagne vise un ciblage qu'on a choisi et porte un seul message : lui proposer un
    message variable n'aurait pas de sens, et rendrait son aperçu impossible à afficher.
    """
    groups = []
    if auto:
        import email_templates_backend as _etb
        groups.append({
            "key": "auto",
            "label": "Selon le secteur du contact (scénarios)",
            "items": [{"id": f"auto:{k}",
                       "name": {"first": "Premier message du secteur",
                                "relance1": "Relance 1 du secteur",
                                "relance2": "Relance 2 du secteur"}.get(k, k),
                       "sub": "le message est choisi à l'envoi, d'après la fiche du contact"}
                      for k in _etb.KINDS],
        })
    structs = [{"id": f"struct:{s['name']}",
                "name": s["name"].replace("leclientroi-newsletter-", "")}
               for s in list_structures()]
    if structs:
        groups.append({"key": "template", "label": "Templates (newsletters, avec images)", "items": structs})
    versions = [{"id": f"ver:{v['id']}", "name": v["name"], "sub": v.get("source") or ""}
                for v in list_versions(site)]
    if versions:
        groups.append({"key": "version", "label": "Messages validés", "items": versions})
    try:
        import email_templates_backend as etb
        cold = []
        for s in etb.list_sectors(site):
            emails = etb.get_sector(site, s["sector"])
            first = next((e for e in emails if e["kind"] == "first"), None)
            if first:
                cold.append({"id": f"cold:{s['sector']}:first",
                             "name": s["sector"], "sub": first.get("subject") or ""})
        if cold:
            groups.append({"key": "cold", "label": "Cold emails (texte, par secteur)", "items": cold})
    except Exception:
        pass
    return {"groups": groups}


def resolve_campaign_message(site: str, mid: str) -> dict | None:
    """Résout un message_id (quelle que soit sa source) en {html, name}."""
    if not mid:
        return None
    if mid.startswith("struct:"):
        html = get_structure(mid[len("struct:"):])
        return {"html": html, "name": mid[len("struct:"):]} if html else None
    if mid.startswith("cold:"):
        try:
            _, sector, kind = mid.split(":", 2)
        except ValueError:
            return None
        import email_templates_backend as etb
        t = etb._get_one(site, sector, kind)
        if not t:
            return None
        # Emballage conforme (lang/charset/title/préheader + footer désinscription) —
        # utilisé pour l'aperçu, le lint ET l'envoi, donc cohérent partout.
        return {"html": etb.wrap_cold_email(t["body_html"], t.get("subject")),
                "name": f"Cold — {sector}"}
    vid = mid[len("ver:"):] if mid.startswith("ver:") else mid
    return get_version(site, vid)


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
