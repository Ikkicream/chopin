#!/usr/bin/env python3
"""pg_sync_enrichment.py — recopie l'enrichissement data.gouv du pool vers PostgreSQL.

Le miroir existait, mais amputé : `contact_enrichment` n'y portait que (contact_id,
excluded, raw, enriched_at). Le SIRET était enfoui dans le JSON, les motifs d'exclusion et
les signaux (RGE, Qualiopi, ESS) nulle part — donc inexploitables par les écrans. Et il
manquait 964 lignes sur 7 158, l'ancienne porte d'entrée n'ayant jamais laissé passer les
contacts non éligibles.

Idempotent : rejouable autant de fois qu'on veut, il met à jour ce qui a changé.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

COLONNES = ("contact_id", "siret", "siren", "denomination", "code_naf",
            "categorie_entreprise", "tranche_effectif_libelle", "commune", "dept_code",
            "region_code", "match_quality", "excluded", "exclusion_reason",
            "est_rge", "est_qualiopi", "est_ess", "enriched_at")


def _dsn() -> str:
    for ligne in (BASE_DIR / ".env").read_text().splitlines():
        if ligne.startswith("PG_DSN="):
            return ligne.split("=", 1)[1].strip()
    raise RuntimeError("PG_DSN absent de .env")


def synchroniser() -> dict:
    import psycopg2
    import psycopg2.extras
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from duck_ouverture import ouvrir

    d = ouvrir(BASE_DIR / "data" / "contacts.duckdb")
    try:
        # Les contacts connus de PostgreSQL font foi : on ne recopie pas l'enrichissement
        # d'un contact qui n'y est pas (la clé étrangère le refuserait de toute façon).
        lignes = d.execute(f"SELECT {', '.join(COLONNES)} FROM contact_enrichment").fetchall()
    finally:
        d.close()

    pg = psycopg2.connect(_dsn())
    try:
        with pg:
            with pg.cursor() as cur:
                cur.execute("SELECT id::text FROM contacts")
                connus = {r[0] for r in cur.fetchall()}
                lot = [tuple(r) for r in lignes if str(r[0]) in connus]
                psycopg2.extras.execute_batch(cur, f"""
                    INSERT INTO contact_enrichment ({', '.join(COLONNES)})
                    VALUES ({', '.join(['%s'] * len(COLONNES))})
                    ON CONFLICT (contact_id) DO UPDATE SET
                        siret = EXCLUDED.siret,
                        siren = EXCLUDED.siren,
                        denomination = EXCLUDED.denomination,
                        code_naf = EXCLUDED.code_naf,
                        categorie_entreprise = EXCLUDED.categorie_entreprise,
                        tranche_effectif_libelle = EXCLUDED.tranche_effectif_libelle,
                        commune = EXCLUDED.commune,
                        dept_code = EXCLUDED.dept_code,
                        region_code = EXCLUDED.region_code,
                        match_quality = EXCLUDED.match_quality,
                        excluded = EXCLUDED.excluded,
                        exclusion_reason = EXCLUDED.exclusion_reason,
                        est_rge = EXCLUDED.est_rge,
                        est_qualiopi = EXCLUDED.est_qualiopi,
                        est_ess = EXCLUDED.est_ess,
                        enriched_at = EXCLUDED.enriched_at
                """, lot, page_size=500)
            with pg.cursor() as cur:
                cur.execute("SELECT count(*), count(*) FILTER (WHERE siret IS NOT NULL), "
                            "count(*) FILTER (WHERE excluded) FROM contact_enrichment")
                total, avec_siret, exclus = cur.fetchone()
    finally:
        pg.close()

    return {"pool": len(lignes), "copiees": len(lot), "postgresql": int(total),
            "avec_siret": int(avec_siret), "exclus": int(exclus),
            "ignorees_contact_absent": len(lignes) - len(lot)}


if __name__ == "__main__":
    print(json.dumps(synchroniser(), indent=1, ensure_ascii=False))
