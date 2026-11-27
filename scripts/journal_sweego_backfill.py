#!/usr/bin/env python3
"""journal_sweego_backfill.py — verse `sweego_events` dans le journal `email_events`.

Dernier volet du Lot 1 : sortir les journaux d'envoi de `god_mode.duckdb`. Les rebonds,
plaintes et désinscriptions Sweego y étaient déjà (importés lors de la mise en place du
journal) ; **les ouvertures et les clics, non** — 1 738 ouvertures et 998 clics ne
figuraient nulle part dans PostgreSQL. Basculer les écrans sans ce versement aurait fait
disparaître tout l'engagement Sweego des statistiques.

Le drapeau `proxy` est CONSERVÉ dans `meta`, pas filtré à l'entrée. 993 des 1 738
ouvertures Sweego viennent d'un pré-chargement antispam et non d'un humain (57 %) : les
jeter ici reviendrait à décider une fois pour toutes à la place des écrans, alors que la
question « une ouverture proxy compte-t-elle ? » se pose différemment selon qu'on mesure
la délivrabilité ou l'intérêt d'un prospect. Le journal enregistre le fait ; la lecture
tranche.

Idempotent : chaque ligne porte son `sweego_event_id` dans `meta`, un second passage
n'insère rien.

Usage :
    python3 scripts/journal_sweego_backfill.py            # état des lieux
    python3 scripts/journal_sweego_backfill.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# `email_events.event_type` est contraint en base : on ne verse que ce qui a un équivalent.
TYPES = {
    "email_opened": "open",
    "email_clicked": "click",
    "hard_bounce":   "bounce",
    "complaint":     "complaint",
    "list_unsub":    "unsub",
}


def _dsn() -> str:
    for ligne in (BASE_DIR / ".env").read_text().splitlines():
        if ligne.startswith("PG_DSN="):
            return ligne.split("=", 1)[1].strip()
    raise SystemExit("PG_DSN absent de .env")


def executer(apply: bool = False) -> dict:
    import duckdb
    import psycopg2
    import psycopg2.extras

    g = duckdb.connect(str(BASE_DIR / "data" / "god_mode.duckdb"), read_only=True)
    try:
        lignes = g.execute(
            "SELECT id, event_type, lower(trim(email)), campaign_id, site_code, url, "
            "       COALESCE(proxy, FALSE), transaction_id, received_at "
            "FROM sweego_events WHERE email IS NOT NULL AND trim(email) <> ''").fetchall()
    finally:
        g.close()

    cx = psycopg2.connect(_dsn())
    cx.autocommit = False
    cu = cx.cursor()
    bilan: dict = {"apply": apply, "sweego_events": len(lignes)}
    try:
        # Deux clés d'unicité, parce qu'il y a deux populations à ne pas doubler :
        # l'identifiant Sweego pour ce que CE script a déjà versé, et le triplet
        # (adresse, type, instant) pour les rebonds et plaintes importés AVANT lui — ils
        # portent la même horodate à la microseconde près, sans identifiant d'événement.
        cu.execute("SELECT meta->>'sweego_event_id' FROM email_events "
                   "WHERE meta ? 'sweego_event_id'")
        deja_id = {r[0] for r in cu.fetchall()}
        cu.execute("SELECT lower(email::text), event_type, occurred_at FROM email_events "
                   "WHERE channel = 'sweego'")
        deja_cle = {(r[0], r[1], r[2].replace(tzinfo=None)) for r in cu.fetchall()}
        bilan["deja_verses"] = len(deja_id)
        bilan["deja_presents_sans_identifiant"] = len(deja_cle) - len(deja_id)

        a_verser, ignores = [], {"type_inconnu": 0, "deja_verse": 0, "deja_present": 0}
        for (sid, etype, email, camp, site, url, proxy, tid, at) in lignes:
            if sid in deja_id:
                ignores["deja_verse"] += 1
                continue
            cible = TYPES.get(etype)
            if not cible:
                ignores["type_inconnu"] += 1
                continue
            if (email, cible, at) in deja_cle:
                ignores["deja_present"] += 1
                continue
            a_verser.append((at, email, email, site or "lcr", "sweego", cible,
                             url or None, tid or None,
                             json.dumps({"source": "sweego_events", "sweego_event_id": sid,
                                         "proxy": bool(proxy), "campagne_sweego": camp})))

        bilan["a_verser"] = len(a_verser)
        bilan["ignores"] = ignores
        par_type: dict[str, int] = {}
        for x in a_verser:
            par_type[x[5]] = par_type.get(x[5], 0) + 1
        bilan["par_type"] = par_type

        if not apply or not a_verser:
            cx.rollback()
            return bilan

        psycopg2.extras.execute_batch(cu, """
            INSERT INTO email_events (occurred_at, email, contact_id, site_code, channel,
                                      event_type, url, provider_msg_id, meta)
            VALUES (%s, %s, (SELECT id FROM contacts WHERE email = %s), %s, %s, %s, %s, %s, %s)
        """, a_verser, page_size=500)
        cx.commit()
        cu.execute("SELECT event_type, channel, count(*) FROM email_events "
                   "WHERE channel = 'sweego' GROUP BY 1, 2 ORDER BY 3 DESC")
        bilan["sweego_dans_le_journal"] = {f"{r[0]}": int(r[2]) for r in cu.fetchall()}
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
    print(json.dumps(executer(apply=ap.parse_args().apply), indent=2, ensure_ascii=False,
                     default=str))
