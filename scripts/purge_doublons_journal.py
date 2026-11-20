#!/usr/bin/env python3
"""purge_doublons_journal.py — Retire du journal les envois rejoués par la migration.

Le fait. La bascule vers PostgreSQL a rejoué les envois depuis `contact_site_history`
(DuckDB) pour les canaux réputés « sans journal par destinataire ». 405 envois maildoso
d'août y figuraient DÉJÀ : le journal porte donc deux lignes `sent` pour la même adresse
le même jour — la vraie (canal `maildoso`, campagne et boîte renseignées) et celle de la
reprise (canal `inconnu`, ni campagne ni boîte, `meta.source = contact_site_history`).

Pourquoi ça n'est pas cosmétique. Deux envois le même jour ferment la fenêtre
d'attribution du premier sur le second : l'ouverture, qui arrive après les deux, est
portée au crédit de la ligne fantôme. Mesuré le 2026-08-21 : maildoso affichait 20,3 %
d'ouverture, le fantôme 27,5 %. `stats_backend` dédoublonne à la lecture, mais tout
nouvel outil qui lira `email_events` sans le savoir retombera dans le piège.

Ce qui est supprimé, et rien d'autre — les trois conditions sont cumulatives :
  1. `event_type = 'sent'` et `channel = 'inconnu'` ;
  2. `meta.source = 'contact_site_history'` (donc issue de la reprise, pas d'un envoi réel) ;
  3. il existe, le MÊME jour et pour la MÊME adresse, un envoi sur un canal connu.

La troisième est le garde-fou qui compte : une ligne n'est retirée que si l'envoi qu'elle
décrit est déjà journalisé ailleurs. Aucune adresse ne peut donc perdre son dernier envoi,
et la fenêtre des 120 jours (`v_suppression`) ne bouge pas — c'est vérifié dans la
transaction, avant validation, et la suppression est abandonnée si le compte change.

Usage :
    python3 scripts/purge_doublons_journal.py            # compte et sauvegarde, n'écrit pas
    python3 scripts/purge_doublons_journal.py --apply    # supprime
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

CIBLE = """
  FROM email_events e
  WHERE e.event_type = 'sent' AND e.channel = 'inconnu'
    AND e.meta->>'source' = 'contact_site_history'
    AND EXISTS (SELECT 1 FROM email_events m
                WHERE m.event_type = 'sent' AND m.channel <> 'inconnu'
                  AND m.email = e.email AND m.site_code = e.site_code
                  AND m.occurred_at::date = e.occurred_at::date)
"""

COLONNES = ["id", "occurred_at", "email", "contact_id", "site_code", "campaign_id",
            "channel", "event_type", "url", "mailbox", "provider_msg_id", "meta"]


def executer(apply: bool = False) -> dict:
    import pool_pg as p

    lignes = p._q(
        "SELECT e.id, e.occurred_at, e.email::text, e.contact_id, e.site_code, "
        "e.campaign_id, e.channel, e.event_type, e.url, e.mailbox, "
        "e.provider_msg_id, e.meta " + CIBLE)

    dossier = BASE_DIR / "backups" / "journal"
    dossier.mkdir(parents=True, exist_ok=True)
    horodatage = p._q("SELECT to_char(now(), 'YYYY-MM-DD_HH24MISS')")[0][0]
    sauvegarde = dossier / f"email_events_doublons_migration_{horodatage}.json"
    sauvegarde.write_text(json.dumps(
        [{c: (v.isoformat() if isinstance(v, datetime.datetime) else v)
          for c, v in zip(COLONNES, r)} for r in lignes],
        ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    bilan = {"lignes_visees": len(lignes), "sauvegarde": str(sauvegarde),
             "suppression_avant": p._q("SELECT count(*) FROM v_suppression")[0][0],
             "sent_avant": p._q(
                 "SELECT count(*) FROM email_events WHERE event_type='sent'")[0][0],
             "applique": False}

    if not apply:
        bilan["note"] = "essai à blanc — rien n'a été supprimé (relancer avec --apply)"
        return bilan

    c = p._conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute("DELETE" + CIBLE)
                bilan["supprimees"] = cur.rowcount
                cur.execute("SELECT count(*) FROM v_suppression")
                apres = cur.fetchone()[0]
                # Le contrôle est DANS la transaction : si la fenêtre des 120 jours bouge
                # d'une seule ligne, on lève et PostgreSQL annule tout.
                if apres != bilan["suppression_avant"]:
                    raise RuntimeError(
                        f"ABANDON : v_suppression {bilan['suppression_avant']} -> {apres}")
                bilan["suppression_apres"] = apres
    finally:
        p._rendre(c)

    bilan["applique"] = True
    bilan["sent_apres"] = p._q(
        "SELECT count(*) FROM email_events WHERE event_type='sent'")[0][0]
    bilan["restant_canal_inconnu"] = p._q(
        "SELECT count(*) FROM email_events "
        "WHERE event_type='sent' AND channel='inconnu'")[0][0]
    return bilan


if __name__ == "__main__":
    print(json.dumps(executer("--apply" in sys.argv), ensure_ascii=False, indent=2))
