#!/usr/bin/env python3
"""pg_gate.py — La porte d'entrée de PostgreSQL.

Modèle en ENTONNOIR (décision user du 2026-08-19) : DuckDB fait le sale boulot — scraping,
nettoyage, vérification Mailnjoy, enrichissement — et un contact n'entre dans PostgreSQL
QUE lorsqu'il est bon. PostgreSQL ne doit contenir que du contactable.

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

_FROM = """
    FROM contacts ct
    LEFT JOIN contact_enrichment e ON e.contact_id = ct.id
"""


def _duck():
    import duckdb
    try:
        return duckdb.connect(str(POOL_DB))
    except Exception:
        return duckdb.connect(str(POOL_DB), read_only=True)


def _colonnes() -> str:
    return """ct.id, ct.email, ct.prenom, ct.nom, ct.societe, ct.tel, ct.website, ct.city,
              ct.dept_code, ct.region_code, ct.postal_code, ct.sectors, ct.primary_source,
              ct.email_score, ct.mailnjoy_check, ct.global_blacklisted"""


def _ligne(r) -> dict:
    cles = ["id", "email", "prenom", "nom", "societe", "tel", "website", "city",
            "dept_code", "region_code", "postal_code", "sectors", "primary_source",
            "email_score", "mailnjoy_check", "global_blacklisted"]
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
