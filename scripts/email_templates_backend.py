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
    """Le texte d'aperçu, affiché juste après l'objet dans la boîte de réception.

    Il ne recopie PLUS le début du corps. Constaté le 2026-08-26 : les variables y étaient
    retirées, ce qui donnait « Bonjour, Je suis , de LeClientROI » — un aperçu troué,
    montré à côté de l'objet avant même l'ouverture. Un aperçu abîmé coûte l'ouverture que
    l'objet vient de gagner.

    On saute donc la salutation et la présentation (qui portent toutes les variables) et
    on prend la première phrase qui APPREND quelque chose : la loi, le chiffre, la question.
    À défaut, une phrase neutre vaut mieux qu'un texte troué.
    """
    import re as _re
    txt = _re.sub(r"<[^>]+>", " ", body_html or "")
    txt = " ".join(txt.split())
    # On découpe en phrases et on garde la première qui ne contient aucune variable et qui
    # dit quelque chose (une salutation fait moins de 25 caractères).
    for phrase in _re.split(r"(?<=[.?!])\s+", txt):
        if "{{" in phrase or "{" in phrase:
            continue
        phrase = phrase.strip()
        if len(phrase) >= 25:
            return phrase[:110]
    return "Prospection locale par SMS, RCS et email — LeClientROI."


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


def _colonne_favori(c) -> None:
    """Ajoute `favori` si elle manque. Idempotent, appelé avant toute lecture du tableau."""
    try:
        c.execute("ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS favori BOOLEAN DEFAULT FALSE")
    except Exception:  # noqa: BLE001
        pass


def set_favori(site: str, sector: str, kind: str, favori: bool) -> dict:
    c = _conn()
    try:
        _colonne_favori(c)
        c.execute("UPDATE email_templates SET favori=? WHERE site_code=? AND sector=? AND kind=?",
                  [bool(favori), site, sector, kind])
    finally:
        c.close()
    return {"ok": True, "favori": bool(favori)}


def tableau(site: str) -> dict:
    """Tous les cold emails du site, avec ce qu'ils ont produit.

    **Les chiffres sont désormais PAR MODÈLE** (Lot B, 2026-08-26). Le journal porte
    `meta.modele` depuis cette date, et l'historique a été repris : un envoi rattaché à une
    campagne connaît son message avec certitude, puisqu'une campagne n'en porte qu'un.

    **Un modèle jamais envoyé affiche zéro, et c'est voulu.** Auparavant les trois emails
    d'un secteur partageaient les chiffres du secteur, ce qui prêtait à chacun le mérite du
    seul qui était réellement parti. `secteur_*` conserve le volume du secteur, comme
    contexte — mais il ne doit jamais être présenté comme la performance du modèle.
    """
    import json as _json
    c = _conn()
    try:
        _colonne_favori(c)
        lignes = c.execute(
            "SELECT sector, kind, subject, body_html, valid, validation_errors, locked, "
            "locked_at, updated_by, updated_at, COALESCE(favori, FALSE) "
            "FROM email_templates WHERE site_code = ? ORDER BY sector, kind", [site]
        ).fetchall()
    finally:
        c.close()

    # Les volumes, par secteur, lus dans le journal PostgreSQL — jamais dans un compteur
    # local qui dérive.
    volumes: dict = {}
    try:
        import pool_pg
        for sec, envoyes, aujourdhui, ouvreurs, cliqueurs, premier in pool_pg._q("""
            WITH envois AS (
                SELECT DISTINCT ev.email, ct.sectors[1] AS secteur, ev.occurred_at
                  FROM email_events ev
                  JOIN contacts ct ON lower(ct.email::text) = lower(ev.email::text)
                 WHERE ev.site_code = %(s)s AND ev.event_type = 'sent'
                   AND ct.sectors IS NOT NULL
            )
            SELECT e.secteur,
                   count(DISTINCT e.email)                                        AS envoyes,
                   count(DISTINCT e.email) FILTER (
                     WHERE (e.occurred_at AT TIME ZONE 'Europe/Paris')::date
                           = (now() AT TIME ZONE 'Europe/Paris')::date)           AS aujourdhui,
                   count(DISTINCT e.email) FILTER (WHERE EXISTS (
                     SELECT 1 FROM email_events o WHERE o.email = e.email
                        AND o.site_code = %(s)s AND o.event_type = 'open'))       AS ouvreurs,
                   count(DISTINCT e.email) FILTER (WHERE EXISTS (
                     SELECT 1 FROM email_events k WHERE k.email = e.email
                        AND k.site_code = %(s)s AND k.event_type = 'click'))      AS cliqueurs,
                   min(e.occurred_at)                                             AS premier
              FROM envois e GROUP BY 1""", {"s": site}):
            volumes[sec] = {"envoyes": int(envoyes or 0), "aujourdhui": int(aujourdhui or 0),
                            "ouvreurs": int(ouvreurs or 0), "cliqueurs": int(cliqueurs or 0),
                            "premier_envoi": str(premier) if premier else None}
    except Exception as e:  # noqa: BLE001
        print(f"[templates] volumes indisponibles ({type(e).__name__}: {e})", flush=True)

    # Les volumes PAR MODÈLE. Même journal, mais groupés sur `meta.modele` au lieu du
    # secteur du contact — c'est toute la différence entre « l'immobilier a produit 46 %
    # d'ouverture » et « CET email-là a produit 46 % d'ouverture ». Un modèle absent de
    # cette table n'est jamais parti : il doit afficher zéro, pas les chiffres du voisin.
    par_modele: dict = {}
    try:
        import pool_pg
        for modele, envoyes, aujourdhui, ouvreurs, cliqueurs, premier in pool_pg._q("""
            WITH envois AS (
                SELECT DISTINCT ev.email, ev.meta->>'modele' AS modele, ev.occurred_at
                  FROM email_events ev
                 WHERE ev.site_code = %(s)s AND ev.event_type = 'sent'
                   AND ev.meta ? 'modele'
            )
            SELECT e.modele,
                   count(DISTINCT e.email)                                        AS envoyes,
                   count(DISTINCT e.email) FILTER (
                     WHERE (e.occurred_at AT TIME ZONE 'Europe/Paris')::date
                           = (now() AT TIME ZONE 'Europe/Paris')::date)           AS aujourdhui,
                   count(DISTINCT e.email) FILTER (WHERE EXISTS (
                     SELECT 1 FROM email_events o WHERE o.email = e.email
                        AND o.site_code = %(s)s AND o.event_type = 'open'
                        AND o.meta->>'modele' = e.modele))                        AS ouvreurs,
                   count(DISTINCT e.email) FILTER (WHERE EXISTS (
                     SELECT 1 FROM email_events k WHERE k.email = e.email
                        AND k.site_code = %(s)s AND k.event_type = 'click'
                        AND k.meta->>'modele' = e.modele))                        AS cliqueurs,
                   min(e.occurred_at)                                             AS premier
              FROM envois e GROUP BY 1""", {"s": site}):
            par_modele[modele] = {
                "envoyes": int(envoyes or 0), "aujourdhui": int(aujourdhui or 0),
                "ouvreurs": int(ouvreurs or 0), "cliqueurs": int(cliqueurs or 0),
                "premier_envoi": str(premier) if premier else None}
    except Exception as e:  # noqa: BLE001
        print(f"[templates] volumes par modèle indisponibles ({type(e).__name__}: {e})",
              flush=True)

    # L'icône et le libellé du secteur, à la source. La galerie les affichait déjà dans
    # l'assistant en allant les chercher sur une AUTRE route : deux appels pour une donnée
    # qui appartient à la ligne. On les pose ici.
    meta_secteur: dict = {}
    try:
        from email_generator import sector_display
        meta_secteur = {s["code"]: s for s in sector_display()}
    except Exception as e:  # noqa: BLE001
        print(f"[templates] métadonnées secteur indisponibles ({type(e).__name__}: {e})",
              flush=True)

    import qualite_message as qm
    out = []
    for (sec, kind, subj, body, valid, errs, locked, locked_at, by, maj, favori) in lignes:
        v = qm.controler(subj or "", body or "", premier_contact=(kind == "first"))
        vol_sec = volumes.get(sec) or {}
        # La clé du modèle est celle que porte la campagne : `cold:<secteur>:<kind>`.
        vol = par_modele.get(f"cold:{sec}:{kind}") or {}
        m = meta_secteur.get(sec) or {}
        out.append({
            "type": "cold", "modele_id": f"cold:{sec}:{kind}",
            "emoji": m.get("emoji") or "✉️", "secteur_label": m.get("label") or sec,
            "sector": sec, "kind": kind, "subject": subj or "",
            "extrait": qm._texte(body or "")[:150],
            "valid": bool(valid), "locked": bool(locked), "favori": bool(favori),
            "validation_errors": (_json.loads(errs) if isinstance(errs, str) and errs else (errs or [])),
            "updated_by": by, "updated_at": str(maj) if maj else None,
            "locked_at": str(locked_at) if locked_at else None,
            "liens": v["liens"], "images": v["images"], "variantes": v["variantes"],
            "mots": len(qm._texte(body or "").split()),
            "avertissements": v["avertissements"][:3],
            "conditionnel": "{{si " in (body or ""),
            # Par MODÈLE. Zéro = ce message-là n'est jamais parti.
            "envoyes": vol.get("envoyes", 0), "envoyes_aujourdhui": vol.get("aujourdhui", 0),
            "ouvreurs": vol.get("ouvreurs", 0), "cliqueurs": vol.get("cliqueurs", 0),
            "premier_envoi": vol.get("premier_envoi"),
            "attribue": bool(vol),
            # Le secteur, pour situer — jamais à présenter comme la performance du modèle.
            "secteur_envoyes": vol_sec.get("envoyes", 0),
            "secteur_ouvreurs": vol_sec.get("ouvreurs", 0),
        })
    out += _lignes_emailing(site, par_modele, meta_secteur)

    jamais = [e for e in out if not e["attribue"]]
    return {"emails": out,
            "note_attribution": (
                "Les volumes sont comptés PAR MODÈLE depuis le 2026-08-26 : le journal "
                "retient le message utilisé à chaque envoi, et l'historique a été repris "
                "depuis les campagnes. Un modèle à zéro n'a jamais été envoyé — ce n'est "
                "pas une donnée manquante."),
            "totaux": {"emails": len(out),
                       "cold": sum(1 for e in out if e["type"] == "cold"),
                       "emailing": sum(1 for e in out if e["type"] == "emailing"),
                       "favoris": sum(1 for e in out if e["favori"]),
                       "verrouilles": sum(1 for e in out if e["locked"]),
                       "jamais_envoyes": len(jamais),
                       "non_conformes": sum(1 for e in out if not e["valid"])}}


# Un fichier de structure s'appelle `leclientroi-newsletter-immobilier.html`. Le secteur
# est le dernier segment : c'est lui qui permet au filtre par secteur de valoir pour les
# DEUX types à la fois, ce qui est tout l'intérêt de la fusion.
#
# Les newsletters ont été nommées au pluriel et en langage courant, les secteurs en
# singulier et en code. Sans ces équivalences, trois newsletters sur huit restent
# orphelines de secteur et échappent au filtre — ce qui vide la fusion de son intérêt.
_ALIAS_SECTEUR = {
    "agences": "agence-marketing", "agence": "agence-marketing", "marketing": "agence-marketing",
    "boutique": "retail", "boutiques": "retail", "commerce": "retail",
}


def _secteur_du_fichier(nom: str, secteurs_connus) -> str:
    for m in reversed((nom or "").replace("_", "-").split("-")):
        if m in secteurs_connus:
            return m
        alias = _ALIAS_SECTEUR.get(m)
        if alias in secteurs_connus:
            return alias
        # Pluriel simple : « artisans » → « artisan ».
        if m.endswith("s") and m[:-1] in secteurs_connus:
            return m[:-1]
    return ""


def _lignes_emailing(site: str, par_modele: dict, meta_secteur: dict) -> list[dict]:
    """Les newsletters, dans la même table que les cold emails.

    Décision de Camille (2026-08-26) : « cold email et newsletters sont la même chose ».
    Deux LECTEURS distincts, une seule vue — fondre les deux backends casserait l'éditeur
    de newsletters, qui n'a rien demandé.

    Les deux sources ne se ressemblent pas. Les structures sont des FICHIERS
    (`structures/*.html`), les versions enregistrées sont des lignes de `html_templates`.
    Cette table est vide aujourd'hui : sans les huit structures du disque, l'onglet
    « Emailing » s'afficherait désespérément vide alors que le matériel existe.
    """
    import qualite_message as qm
    lignes: list[dict] = []
    try:
        import html_templates_backend as htb
        structures = htb.list_structures()
        versions = htb.list_versions(site)
    except Exception as e:  # noqa: BLE001
        print(f"[templates] newsletters indisponibles ({type(e).__name__}: {e})", flush=True)
        return []

    connus = set(meta_secteur)

    def _ligne(modele_id: str, nom: str, html: str, maj: str | None, par: str | None) -> dict:
        sec = _secteur_du_fichier(nom, connus)
        m = meta_secteur.get(sec) or {}
        # `premier_contact=False` : une newsletter part à des contacts qui connaissent déjà
        # l'expéditeur. La règle des deux liens ne la concerne pas.
        v = qm.controler("", html or "", premier_contact=False)
        vol = par_modele.get(modele_id) or {}
        texte = qm._texte(html or "")
        return {
            "type": "emailing", "modele_id": modele_id,
            "emoji": m.get("emoji") or "📰", "secteur_label": m.get("label") or (sec or "tous secteurs"),
            "sector": sec, "kind": "emailing", "subject": nom,
            "extrait": texte[:150],
            # Une newsletter n'a ni recette de cold email ni verrou : les colonnes existent
            # pour que la table reste homogène, elles ne prétendent pas à un état.
            "valid": True, "locked": False, "favori": False,
            "validation_errors": [], "avertissements": v["avertissements"][:3],
            "updated_by": par, "updated_at": maj, "locked_at": None,
            "liens": v["liens"], "images": v["images"], "variantes": v["variantes"],
            "mots": len(texte.split()), "conditionnel": "{{si " in (html or ""),
            "envoyes": vol.get("envoyes", 0), "envoyes_aujourdhui": vol.get("aujourdhui", 0),
            "ouvreurs": vol.get("ouvreurs", 0), "cliqueurs": vol.get("cliqueurs", 0),
            "premier_envoi": vol.get("premier_envoi"), "attribue": bool(vol),
            "secteur_envoyes": 0, "secteur_ouvreurs": 0,
        }

    for s in structures:
        html = ""
        try:
            html = htb.get_structure(s["name"]) or ""
        except Exception:  # noqa: BLE001
            pass
        # `struct:<stem>` et NON `struct:<fichier>` : c'est l'identifiant que porte une
        # campagne (`campaign_message_options`). Une autre forme ici et l'aperçu ne
        # résoudrait rien, tandis que l'attribution du lot B ne se raccrocherait à rien.
        lignes.append(_ligne(f"struct:{s['name']}", s["name"], html, None, None))

    for v in versions:
        html = ""
        try:
            html = (htb.get_version(site, v["id"]) or {}).get("html") or ""
        except Exception:  # noqa: BLE001
            pass
        lignes.append(_ligne(f"ver:{v['id']}", v["name"], html,
                             v.get("created_at"), v.get("created_by")))

    return lignes


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
