#!/usr/bin/env python3
"""pg_gate.py — La porte d'entrée de PostgreSQL.

**Le modèle a changé le 2026-08-20 (décision user).** PostgreSQL accueille désormais TOUS
les contacts, chacun portant son ÉTAT (`a_verifier`, `ok`, `ko`, `exclu`, `spam`). La porte
n'est plus un filtre à l'entrée mais un drapeau : on n'écarte plus personne de la base, on
sait seulement à qui on a le droit d'écrire.

Deux raisons : l'entonnoir laissait 1 776 contacts sur 7 970 hors de PostgreSQL, invisibles
à tout écran qui le lit ; et il interdisait au scraping d'écrire directement dans
PostgreSQL, donc de sortir de la fenêtre 22 h-8 h imposée par le verrou DuckDB.

`ELIGIBILITE_SQL` reste la définition du CONTACTABLE — c'est elle qui décide de l'état
`ok` et qui filtrera la pioche des campagnes. Ce qui change, c'est ce qu'on en fait :
un drapeau, pas une porte.

Modèle historique (conservé pour mémoire) — ENTONNOIR : DuckDB fait le sale boulot —
scraping, nettoyage, vérification Mailnjoy, enrichissement — et un contact n'entrait dans
PostgreSQL QUE lorsqu'il était bon.

**Critère retenu — option C, la plus stricte.** Un contact franchit la porte si :
  1. Mailnjoy a rendu `valid` ;
  2. la vérification date de moins de 180 jours ;
  3. il n'est pas blacklisté globalement ;
  4. l'enrichissement data.gouv A ÉTÉ EFFECTUÉ et ne l'exclut pas
     (ni diffusion partielle, ni administration, ni entreprise fermée).

Le point 4 est ce qui distingue l'option C : un contact non encore enrichi ATTEND. Cela
suppose que l'enrichissement tourne régulièrement — un cron quotidien a été ajouté le
2026-08-19, sans quoi les contacts s'accumuleraient indéfiniment en salle d'attente.

**Sortie.** Un contact qui se salit après coup (désabonnement, plainte, rebond dur, exclusion
par un ré-enrichissement) est RETIRÉ de PostgreSQL. Son journal `email_events` reste : il est
indexé sur l'ADRESSE et non sur le contact, donc l'historique et surtout le blocage de
120 jours lui survivent. C'est précisément ce qui manquait quand un contact purgé puis
re-scrapé repartait vierge — la boucle de renvois d'août 2026.
"""
from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
POOL_DB = BASE_DIR / "data" / "contacts.duckdb"

CLEANED_WITHIN_DAYS = 180

# Le critère, écrit UNE fois. Il sert au balayage complet comme à la décision unitaire :
# deux formulations divergeraient tôt ou tard, et la divergence serait invisible.
ELIGIBILITE_SQL = f"""
    COALESCE(ct.global_blacklisted, FALSE) = FALSE
    AND json_extract_string(ct.mailnjoy_check, '$.decision') = 'valid'
    AND json_extract_string(ct.mailnjoy_check, '$.checked_at') >=
        (CURRENT_TIMESTAMP - INTERVAL '{CLEANED_WITHIN_DAYS}' DAY)::VARCHAR
    AND e.contact_id IS NOT NULL
    AND COALESCE(e.excluded, FALSE) = FALSE
"""

# L'ÉTAT d'un contact, en cascade : la première condition bloquante l'emporte. Écrit ici,
# à côté du critère d'éligibilité, pour que les deux ne puissent pas diverger — `ok` est
# exactement « ce qui satisfait ELIGIBILITE_SQL ».
#
# On ne stocke que des VERDICTS. « En repos » (120 jours) et « prêt » (SIRET trouvé) restent
# calculés à la lecture : ils dépendent de la date, pas d'une décision.
ETAT_SQL = f"""
    CASE
        WHEN COALESCE(ct.global_blacklisted, FALSE) THEN 'spam'
        WHEN json_extract_string(ct.mailnjoy_check, '$.decision') IS NOT NULL
         AND json_extract_string(ct.mailnjoy_check, '$.decision') <> 'valid' THEN 'ko'
        WHEN COALESCE(e.excluded, FALSE) THEN 'exclu'
        WHEN json_extract_string(ct.mailnjoy_check, '$.decision') IS NULL THEN 'a_verifier'
        WHEN json_extract_string(ct.mailnjoy_check, '$.checked_at') <
             (CURRENT_TIMESTAMP - INTERVAL '{CLEANED_WITHIN_DAYS}' DAY)::VARCHAR THEN 'a_verifier'
        ELSE 'ok'
    END
"""
# Note : l'ÉTAT décrit l'ADRESSE, pas l'éligibilité complète à un envoi. Il exigeait
# auparavant que l'enrichissement data.gouv ait eu lieu (`e.contact_id IS NOT NULL`) —
# héritage de la porte d'entrée « option C ». Conséquence : 73 contacts validés par
# Mailnjoy mais pas encore enrichis s'affichaient « À vérifier » dans PostgreSQL et
# « Vérifié » dans le pool, deux écrans se contredisant sur les mêmes personnes.
# L'exigence d'enrichissement appartient à la PIOCHE D'ENVOI (`ELIGIBILITE_SQL` ici,
# `_ELIGIBLE` dans pool_pg), pas au verdict sur l'adresse. Elle y est restée intacte.

# Le motif, pour qu'un « ko » soit explicable sans rouvrir la base.
MOTIF_SQL = """
    CASE
        WHEN COALESCE(ct.global_blacklisted, FALSE) THEN COALESCE(ct.blacklist_reason, 'blacklisté')
        WHEN json_extract_string(ct.mailnjoy_check, '$.decision') IS NOT NULL
         AND json_extract_string(ct.mailnjoy_check, '$.decision') <> 'valid'
            THEN 'mailnjoy: ' || json_extract_string(ct.mailnjoy_check, '$.decision')
        WHEN COALESCE(e.excluded, FALSE) THEN COALESCE(e.exclusion_reason, 'exclu data.gouv')
        ELSE NULL
    END
"""

_FROM = """
    FROM contacts ct
    LEFT JOIN contact_enrichment e ON e.contact_id = ct.id
"""


def _duck(tentatives: int = 30, pause_s: float = 20.0):
    """Ouvre le pool, patiemment.

    Depuis le passage du scraping en 24 h/24 (2026-08-20), un scrape peut tenir
    `contacts.duckdb` à n'importe quelle heure — y compris pendant l'enrichissement de
    6h30 et la réconciliation qui le suit. Deux essais consécutifs ne suffisaient plus :
    la réconciliation mourait sur le verrou et PostgreSQL restait en retard, ce qui est
    précisément la panne qu'elle est censée réparer. On attend donc jusqu'à dix minutes,
    ce qui couvre le nettoyage Mailnjoy entre deux villes, avant d'abandonner.
    """
    import time
    import duckdb
    derniere = None
    for i in range(tentatives):
        for read_only in (False, True):
            try:
                return duckdb.connect(str(POOL_DB), read_only=read_only)
            except Exception as e:  # noqa: BLE001
                derniere = e
        if i < tentatives - 1:
            time.sleep(pause_s)
    raise derniere


def _colonnes() -> str:
    return """ct.id, ct.email, ct.prenom, ct.nom, ct.societe, ct.tel, ct.website, ct.city,
              ct.dept_code, ct.region_code, ct.postal_code, ct.sectors, ct.primary_source,
              ct.email_score, ct.mailnjoy_check, ct.global_blacklisted,
              ct.blacklist_reason"""


def _ligne(r) -> dict:
    cles = ["id", "email", "prenom", "nom", "societe", "tel", "website", "city",
            "dept_code", "region_code", "postal_code", "sectors", "primary_source",
            "email_score", "mailnjoy_check", "global_blacklisted", "blacklist_reason"]
    return dict(zip(cles, r))


def est_eligible(contact_id: str, conn=None) -> bool:
    """Ce contact a-t-il le droit d'être dans PostgreSQL ?"""
    c = conn or _duck()
    try:
        r = c.execute(f"SELECT 1 {_FROM} WHERE ct.id = ? AND {ELIGIBILITE_SQL}",
                      [contact_id]).fetchone()
        return r is not None
    finally:
        if conn is None:
            c.close()


def contact_eligible(contact_id: str, conn=None) -> dict | None:
    """La ligne du contact s'il est éligible, None sinon."""
    c = conn or _duck()
    try:
        r = c.execute(f"SELECT {_colonnes()} {_FROM} WHERE ct.id = ? AND {ELIGIBILITE_SQL}",
                      [contact_id]).fetchone()
        return _ligne(r) if r else None
    finally:
        if conn is None:
            c.close()


def tous_eligibles(conn=None) -> list[dict]:
    """Tous les contacts qui devraient être dans PostgreSQL."""
    c = conn or _duck()
    try:
        rows = c.execute(f"SELECT {_colonnes()} {_FROM} WHERE {ELIGIBILITE_SQL}").fetchall()
        return [_ligne(r) for r in rows]
    finally:
        if conn is None:
            c.close()


def contact_tel_quel(contact_id: str, conn=None) -> dict | None:
    """Le contact avec son état, éligible ou non. None seulement s'il n'existe plus.

    Remplace `contact_eligible` dans le chemin d'écriture : PostgreSQL accueille tout le
    monde, la sélection se fait sur `etat` au moment de piocher, pas à l'entrée.
    """
    c = conn or _duck()
    try:
        r = c.execute(
            f"SELECT {_colonnes()}, {ETAT_SQL} AS etat, {MOTIF_SQL} AS motif {_FROM} "
            f"WHERE ct.id = ?", [contact_id]).fetchone()
        if not r:
            return None
        d = _ligne(r[:-2])
        d["etat"] = r[-2]
        d["etat_motif"] = r[-1]
        return d
    finally:
        if conn is None:
            c.close()


def tous_contacts(conn=None) -> list[dict]:
    """TOUS les contacts du pool, chacun avec son état et son motif.

    Remplace `tous_eligibles` pour la réconciliation : PostgreSQL accueille tout le monde,
    et c'est l'état qui dit à qui on peut écrire.
    """
    c = conn or _duck()
    try:
        rows = c.execute(
            f"SELECT {_colonnes()}, {ETAT_SQL} AS etat, {MOTIF_SQL} AS motif {_FROM}"
        ).fetchall()
        out = []
        for r in rows:
            d = _ligne(r[:-2])
            d["etat"] = r[-2]
            d["etat_motif"] = r[-1]
            out.append(d)
        return out
    finally:
        if conn is None:
            c.close()


def etat_contact(contact_id: str, conn=None) -> tuple[str, str | None] | None:
    """L'état d'UN contact, calculé par la même cascade que le balayage."""
    c = conn or _duck()
    try:
        r = c.execute(f"SELECT {ETAT_SQL}, {MOTIF_SQL} {_FROM} WHERE ct.id = ?",
                      [contact_id]).fetchone()
        return (r[0], r[1]) if r else None
    finally:
        if conn is None:
            c.close()


def compter_eligibles(conn=None) -> dict:
    """Compteurs de la salle d'attente, pour voir ce qui bloque et où."""
    c = conn or _duck()
    try:
        def n(cond: str) -> int:
            return int(c.execute(f"SELECT count(*) {_FROM} WHERE {cond}").fetchone()[0] or 0)
        total = n("TRUE")
        valid = n("json_extract_string(ct.mailnjoy_check, '$.decision') = 'valid'")
        non_bl = n("json_extract_string(ct.mailnjoy_check, '$.decision') = 'valid' "
                   "AND COALESCE(ct.global_blacklisted, FALSE) = FALSE")
        non_exclu = n("json_extract_string(ct.mailnjoy_check, '$.decision') = 'valid' "
                      "AND COALESCE(ct.global_blacklisted, FALSE) = FALSE "
                      "AND COALESCE(e.excluded, FALSE) = FALSE")
        eligibles = n(ELIGIBILITE_SQL)
        return {
            "contacts_pool": total,
            "mailnjoy_valid": valid,
            "et_non_blacklistes": non_bl,
            "et_non_exclus": non_exclu,
            "eligibles": eligibles,
            "en_attente_enrichissement": non_exclu - eligibles,
        }
    finally:
        if conn is None:
            c.close()


def etat_site(contact_id: str, site_code: str, conn=None) -> dict | None:
    """État contact × site à recopier avec le contact promu."""
    c = conn or _duck()
    try:
        r = c.execute("""SELECT state, source, state_history FROM contact_site_history
                         WHERE contact_id = ? AND site_code = ?""",
                      [contact_id, site_code]).fetchone()
        if not r:
            return None
        hist = r[2]
        if isinstance(hist, str):
            try:
                hist = json.loads(hist)
            except Exception:
                hist = []
        return {"state": r[0] or "cold_email", "source": r[1], "history": hist or []}
    finally:
        if conn is None:
            c.close()


def sites_du_contact(contact_id: str, conn=None) -> list[str]:
    c = conn or _duck()
    try:
        return [r[0] for r in c.execute(
            "SELECT site_code FROM contact_site_history WHERE contact_id = ?",
            [contact_id]).fetchall()]
    finally:
        if conn is None:
            c.close()


if __name__ == "__main__":
    print(json.dumps(compter_eligibles(), indent=2, ensure_ascii=False))
