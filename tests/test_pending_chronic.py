#!/usr/bin/env python3
"""Tests de la sortie de file des pending chroniques.

Vérifie sur une base temporaire que :
  - le drain ignore les lignes à bout de tentatives (elles monopoliseraient chaque passe) ;
  - mais qu'elles sont COMPTÉES (`count_chronic_pending`) — c'est ce qui manquait : 397
    lignes s'étaient accumulées entre mai et août 2026 sans qu'aucun compteur ne le dise ;
  - qu'elles partent au tombstone une fois le délai de grâce écoulé, et pas avant ;
  - qu'elles ne peuvent plus revenir (tombstone = motif 'unverifiable').
"""
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import duckdb  # noqa: E402
import god_mode_backend as gm  # noqa: E402

ECHECS = []


def verifie(nom, condition, detail=""):
    if condition:
        print(f"  OK   {nom}")
    else:
        print(f"  ÉCHEC {nom} {detail}")
        ECHECS.append(nom)


def _base(tmp: Path):
    gm.GOD_DB = tmp
    c = duckdb.connect(str(tmp))
    c.execute("""CREATE TABLE scrappe_pending (
        id VARCHAR, site_code VARCHAR, company_name VARCHAR, contact_name VARCHAR,
        email VARCHAR, phone VARCHAR, sector VARCHAR, city VARCHAR, postal_code VARCHAR,
        website VARCHAR, source VARCHAR, search_query VARCHAR, score INTEGER,
        status VARCHAR, raw_data VARCHAR, email_score INTEGER,
        email_validation_reasons VARCHAR, region_code VARCHAR, dept_code VARCHAR,
        created_at TIMESTAMP, mailnjoy_attempts INTEGER, mailnjoy_last_error VARCHAR)""")
    c.close()


def _pending(email, attempts, age_jours):
    # DuckDB n'accepte pas de paramètre dans un littéral INTERVAL : on calcule la date côté
    # Python et on l'insère telle quelle.
    c = duckdb.connect(str(gm.GOD_DB))
    pid = str(uuid.uuid4())
    cree = datetime.now(timezone.utc) - timedelta(days=age_jours)
    c.execute("""INSERT INTO scrappe_pending (id, site_code, email, created_at,
                 mailnjoy_attempts, mailnjoy_last_error)
                 VALUES (?, 'lcr', ?, ?, ?, 'http_500')""",
              [pid, email, cree, attempts])
    c.close()
    return pid


def lance():
    with tempfile.TemporaryDirectory() as d:
        _base(Path(d) / "god_test.duckdb")

        _pending("frais@ex.fr", 0, 0)            # normal, doit être drainé
        _pending("presque@ex.fr", 4, 30)         # dernière tentative permise
        _pending("chronique-vieux@ex.fr", 5, 30)  # à bout ET ancien -> tombstone
        _pending("chronique-recent@ex.fr", 6, 2)  # à bout mais récent -> grâce

        print("\n1. La file du drain")
        file_drain = [r["email"] for r in gm.list_pending(site_code="lcr")]
        verifie("le contact frais est dans la file", "frais@ex.fr" in file_drain)
        verifie("4 tentatives : encore dans la file", "presque@ex.fr" in file_drain)
        verifie("5 tentatives : hors file", "chronique-vieux@ex.fr" not in file_drain)
        verifie("6 tentatives : hors file", "chronique-recent@ex.fr" not in file_drain)

        print("\n2. Les lignes hors file sont comptées (ce qui manquait)")
        verifie("count_chronic_pending = 2", gm.count_chronic_pending("lcr") == 2,
                f"(vaut {gm.count_chronic_pending('lcr')})")

        print("\n3. Sortie de file après le délai de grâce")
        res = gm.retire_chronic_pending(site_code="lcr", age_days=7)
        verifie("1 seule ligne retirée (l'ancienne)", res["retired"] == 1,
                f"(vaut {res['retired']})")
        restants = [r[0] for r in duckdb.connect(str(gm.GOD_DB)).execute(
            "SELECT email FROM scrappe_pending").fetchall()]
        verifie("l'ancienne a quitté scrappe_pending",
                "chronique-vieux@ex.fr" not in restants)
        verifie("la récente reste (délai de grâce)",
                "chronique-recent@ex.fr" in restants)
        verifie("le contact frais est intact", "frais@ex.fr" in restants)

        print("\n4. Tombstone : elle ne peut plus revenir")
        verifie("email_rejected() la connaît", gm.email_rejected("chronique-vieux@ex.fr"))
        row = duckdb.connect(str(gm.GOD_DB)).execute(
            "SELECT decision, reason FROM scrappe_rejected WHERE email = ?",
            ["chronique-vieux@ex.fr"]).fetchone()
        verifie("decision = 'unverifiable'", row is not None and row[0] == "unverifiable")
        verifie("motif tracé", row is not None and "mailnjoy_500" in (row[1] or ""))
        verifie("la récente n'est PAS au tombstone",
                not gm.email_rejected("chronique-recent@ex.fr"))

        print("\n5. Idempotence")
        r2 = gm.retire_chronic_pending(site_code="lcr", age_days=7)
        verifie("2e passage : rien à retirer", r2["retired"] == 0, f"(vaut {r2['retired']})")

    print("\n" + "=" * 60)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS)}")
        return 1
    print("Tous les tests passent.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
