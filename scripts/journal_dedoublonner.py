#!/usr/bin/env python3
"""journal_dedoublonner.py — retire les rejournalisations d'un même envoi dans `email_events`.

`mark_pushed_to_emelia` écrit le journal PostgreSQL **avant** d'ouvrir DuckDB (règle du
2026-08-20 : ce qui porte une règle métier s'écrit d'abord dans PostgreSQL). Si l'écriture
DuckDB qui suit échoue — verrou de `god_mode.duckdb` pendant un dispatch — l'appelant
recommence le marquage : PostgreSQL reçoit alors une SECONDE ligne d'envoi pour un email
qui n'est parti qu'une fois.

Constaté le 2026-08-22 : 316 lignes `sent` pour 160 envois SMTP réels (vérifié un par un
contre `maildoso_sent`, une seule ligne par destinataire). **Personne n'a reçu deux fois
le message** — c'est le journal qui compte double.

Sans conséquence sur la fenêtre de 120 jours (`v_suppression` prend `max(occurred_at)`),
mais tout volume lu dans PostgreSQL est faux — et c'est précisément ce qu'il faut lire
pour sortir les journaux d'envoi de `god_mode.duckdb`.

On garde la ligne la PLUS ANCIENNE de chaque (adresse, campagne, jour UTC) : c'est celle
qui correspond à l'envoi réel, les suivantes sont des reprises. Une table de sauvegarde
est écrite avant toute suppression.

Usage :
    python3 scripts/journal_dedoublonner.py            # état des lieux, n'écrit rien
    python3 scripts/journal_dedoublonner.py --apply     # dédoublonne + pose le garde-fou
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_CLE = ("email, COALESCE(campaign_id, '00000000-0000-0000-0000-000000000000'::uuid), "
        "timezone('UTC', occurred_at)::date")


def _dsn() -> str:
    for ligne in (BASE_DIR / ".env").read_text().splitlines():
        if ligne.startswith("PG_DSN="):
            return ligne.split("=", 1)[1].strip()
    raise SystemExit("PG_DSN absent de .env")


def executer(apply: bool = False) -> dict:
    import psycopg2
    cx = psycopg2.connect(_dsn())
    cx.autocommit = False
    cu = cx.cursor()
    bilan: dict = {"apply": apply}
    try:
        cu.execute("SELECT count(*) FROM email_events WHERE event_type = 'sent'")
        bilan["lignes_sent_avant"] = int(cu.fetchone()[0])
        cu.execute(f"""
            SELECT count(*) FROM (
              SELECT 1 FROM email_events WHERE event_type = 'sent'
              GROUP BY {_CLE} HAVING count(*) > 1) t""")
        bilan["cles_en_double"] = int(cu.fetchone()[0])
        cu.execute(f"""
            SELECT coalesce(sum(n - 1), 0) FROM (
              SELECT count(*) n FROM email_events WHERE event_type = 'sent'
              GROUP BY {_CLE} HAVING count(*) > 1) t""")
        bilan["lignes_a_supprimer"] = int(cu.fetchone()[0])
        cu.execute(f"""
            SELECT timezone('UTC', occurred_at)::date AS j, count(*) - count(DISTINCT ({_CLE}))
            FROM email_events WHERE event_type = 'sent'
            GROUP BY 1 HAVING count(*) > count(DISTINCT ({_CLE})) ORDER BY 1 DESC""")
        bilan["par_jour"] = {str(r[0]): int(r[1]) for r in cu.fetchall()}

        if not apply:
            cx.rollback()
            return bilan

        cu.execute("""
            CREATE TABLE IF NOT EXISTS email_events_avant_dedoublonnage AS
            SELECT * FROM email_events WHERE event_type = 'sent'""")
        cu.execute(f"""
            WITH doublons AS (
              SELECT id, row_number() OVER (PARTITION BY {_CLE}
                                            ORDER BY occurred_at, id) AS rang
              FROM email_events WHERE event_type = 'sent')
            DELETE FROM email_events WHERE id IN (SELECT id FROM doublons WHERE rang > 1)""")
        bilan["lignes_supprimees"] = cu.rowcount

        # Le garde-fou, pour que la reprise d'un marquage ne puisse plus produire de
        # doublon : une campagne n'écrit jamais deux fois à la même personne le même jour.
        cu.execute(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_events_sent_unique
            ON email_events ({_CLE}) WHERE event_type = 'sent'""")
        cu.execute("SELECT count(*) FROM email_events WHERE event_type = 'sent'")
        bilan["lignes_sent_apres"] = int(cu.fetchone()[0])
        cx.commit()
    except Exception:
        cx.rollback()
        raise
    finally:
        cu.close()
        cx.close()
    return bilan


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    print(json.dumps(executer(apply=ap.parse_args().apply), indent=2, ensure_ascii=False))
