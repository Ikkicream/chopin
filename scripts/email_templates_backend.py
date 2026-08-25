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


_FN = "{{firstName}}"


def _preheader(body_html: str) -> str:
    """~90 premiers caractères de texte du corps (préheader ≥ 30 car. recommandé)."""
    import re as _re
    txt = _re.sub(r"<[^>]+>", " ", body_html or "")
    txt = _re.sub(r"\{\{[^}]*\}\}", "", txt)  # retire les variables du préheader
    txt = " ".join(txt.split())
    return txt[:90]


# Signature/footer conforme (CAN-SPAM / CNIL) ajouté aux cold emails.
# NB : pas d'adresse postale en dur (à compléter par Camille) — on met société, contact,
# téléphone et un lien de désinscription réel et détectable par le lint.
_COLD_FOOTER = (
    '<hr style="border:none;border-top:1px solid #eee;margin:22px 0 10px" />'
    '<p style="font-size:12px;line-height:18px;color:#666666;margin:0">'
    'Le Client ROI · <a href="https://leclientroi.com" style="color:#666666">leclientroi.com</a> · '
    'contact@leclientroi.com · +33&nbsp;7&nbsp;44&nbsp;30&nbsp;66&nbsp;03<br />'
    'Email professionnel envoyé par Le Client ROI. '
    # href contient « unsubscribe » pour être détecté comme lien de désinscription (lint EN)
    '<a href="mailto:contact@leclientroi.com?subject=unsubscribe" style="color:#666666">Me désinscrire</a>.'
    '</p>'
)


def wrap_cold_email(body_html: str, subject: str = "") -> str:
    """Emballe un corps de cold email (fragment) dans un document HTML conforme :
    lang, charset, title, viewport, préheader caché, et footer désinscription/contact.
    Rend le message valide au lint ET conforme à l'envoi. Idempotent (ne réemballe pas)."""
    body = body_html or ""
    if "<html" in body.lower():
        return body  # déjà un document complet
    pre = _preheader(body)
    subj = (subject or "Le Client ROI").replace("<", "").replace(">", "")
    return (
        '<!doctype html>\n<html lang="fr">\n<head>\n'
        '<meta charset="utf-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        f'<title>{subj}</title>\n</head>\n'
        '<body style="margin:0;padding:0;background:#ffffff;font-family:Arial,Helvetica,sans-serif;color:#222222">\n'
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#ffffff;font-size:1px">{pre}</div>\n'
        '<div style="max-width:600px;margin:0 auto;padding:18px;font-size:15px;line-height:1.6">\n'
        f'{body}\n{_COLD_FOOTER}\n</div>\n</body>\n</html>'
    )


def normalize_greeting(body_html: str) -> str:
    """Force la salutation au format `{{firstName}},` SANS « Bonjour » littéral devant :
    c'est la valeur poussée (greeting_first_name) qui porte la salutation complète
    (« Bonjour Philippe » / « Bonjour »), car Emelia trim les espaces de bord du champ
    firstName (donc impossible d'y cacher l'espace). Rendu : « Bonjour Philippe, » avec
    prénom, « Bonjour, » sans — jamais « Bonjour , », « , … » ni « Bonjour Bonjour ».
    Idempotent. Appelé à la génération IA ET à l'édition manuelle. Sans {{firstName}},
    ne touche à rien."""
    if not body_html or _FN not in body_html:
        return body_html
    out = body_html.replace("Bonjour " + _FN, _FN)  # « Bonjour {{firstName}} » -> « {{firstName}} »
    out = out.replace("Bonjour" + _FN, _FN)         # « Bonjour{{firstName}} »  -> « {{firstName}} »
    return out


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
        _upsert(site, sector, kind, em.get("subject", ""), normalize_greeting(em.get("body_html", "")),
                not errs, errs, by="ai", locked=False)
    return {"ok": True, "sector": sector, "skipped_locked": skipped, "emails": get_sector(site, sector)}


def update(site: str, sector: str, kind: str, subject: str, body_html: str, by: str = "ui") -> dict:
    """Édition manuelle d'un email. Re-valide ; l'édition rouvre (locked=False)."""
    from email_generator import validate_email
    if kind not in KINDS:
        return {"ok": False, "error": f"kind invalide ({kind})"}
    body_html = normalize_greeting(body_html or "")
    errs = validate_email(subject or "", body_html)
    _upsert(site, sector, kind, subject or "", body_html, not errs, errs, by=by, locked=False)
    return {"ok": True, "valid": not errs, "validation_errors": errs, "email": _get_one(site, sector, kind)}


def dupliquer(site: str, source: str, cible: str, by: str = "ui") -> dict:
    """Recopie les trois emails d'un secteur vers un autre, en brouillon déverrouillé.

    Sert au cas le plus fréquent : un secteur proche existe déjà et fonctionne, on part de
    lui plutôt que de la page blanche. La copie est RE-VALIDÉE — un email conforme pour un
    secteur peut ne plus l'être ailleurs (le lint exige un lien de prise de rendez-vous, et
    le corps peut nommer le métier d'origine).

    Un email VERROUILLÉ de la cible n'est jamais écrasé : le verrou vaut approbation, et
    une duplication ne doit pas défaire une validation.
    """
    from email_generator import validate_email
    source, cible = (source or "").strip(), (cible or "").strip()
    if not source or not cible:
        return {"ok": False, "error": "secteur source et cible requis"}
    if source == cible:
        return {"ok": False, "error": "la source et la cible sont le même secteur"}

    copies, ignores = [], []
    for kind in KINDS:
        origine = _get_one(site, source, kind)
        if not origine or not (origine.get("body_html") or "").strip():
            continue
        existant = _get_one(site, cible, kind)
        if existant and existant.get("locked"):
            ignores.append(kind)
            continue
        corps = normalize_greeting(origine.get("body_html") or "")
        errs = validate_email(origine.get("subject") or "", corps)
        _upsert(site, cible, kind, origine.get("subject") or "", corps,
                not errs, errs, by=by, locked=False)
        copies.append({"kind": kind, "valid": not errs, "validation_errors": errs})

    if not copies and not ignores:
        return {"ok": False, "error": f"aucun email à copier depuis « {source} »"}
    return {"ok": True, "source": source, "cible": cible,
            "copies": copies, "ignores_car_verrouilles": ignores,
            "emails": get_sector(site, cible)}


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
