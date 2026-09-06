#!/usr/bin/env python3
"""
rgpd_purge.py — Purge RGPD : anonymise les prospects froids inactifs depuis > 3 ans
(recommandation CNIL B2B). Cf. politiques de confidentialité (legal/).

Règle :
- On cible les contacts dont le DERNIER contact (toutes interactions) date de > 3 ans
  (ou la date de création si jamais contactés).
- On ÉPARGNE : les leads/clients (state prm/lead/crm sur un site) et les blacklistés
  (qui doivent rester connus pour respecter leur opposition).
- Action = ANONYMISATION en place (on garde la ligne pour les stats secteur/ville,
  on efface les données identifiantes). Réversibilité nulle = c'est le but RGPD.

Usage :
    python3 scripts/rgpd_purge.py            # dry-run (compte, ne modifie rien)
    python3 scripts/rgpd_purge.py --apply    # anonymise réellement
"""
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "contacts.duckdb"
RETENTION_DAYS = 3 * 365  # ~3 ans

_DATE_COLS = ["email_sent_at", "last_contacted_by_site_at", "last_action_at",
              "emelia_opened_at", "emelia_clicked_at", "emelia_replied_at"]


def _naive(dt):
    """Normalise un datetime en naïf (sans tz) pour comparaison robuste."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if getattr(dt, "tzinfo", None) else dt


def find_purgeable(c):
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    # Contacts protégés : au moins un état lead/prm/crm sur un site
    protected = {r[0] for r in c.execute(
        "SELECT DISTINCT contact_id FROM contact_site_history WHERE lower(state) IN ('prm','lead','crm')"
    ).fetchall()}
    # Dernier contact par contact_id (max des colonnes de date du history)
    greatest = "GREATEST(" + ", ".join(f"COALESCE({col}, TIMESTAMP '1970-01-01')" for col in _DATE_COLS) + ")"
    last_touch = {cid: _naive(lt) for cid, lt in c.execute(
        f"SELECT contact_id, MAX({greatest}) AS lt FROM contact_site_history GROUP BY contact_id"
    ).fetchall()}

    purge = []
    for cid, email, created, bl in c.execute(
        "SELECT id, email, created_at, COALESCE(global_blacklisted, FALSE) FROM contacts"
    ).fetchall():
        if bl or cid in protected:
            continue
        lt = last_touch.get(cid)
        ref = lt if (lt and lt.year > 1970) else _naive(created)
        if ref and ref < cutoff:
            purge.append(cid)
    return purge, cutoff


def main(apply=False):
    c = duckdb.connect(str(DB), read_only=not apply)
    try:
        total = c.execute("SELECT count(*) FROM contacts").fetchone()[0]
        purge, cutoff = find_purgeable(c)
        print(f"Rétention {RETENTION_DAYS // 365} ans · cutoff {cutoff.date()} · "
              f"contacts={total} · à anonymiser={len(purge)}")
        if not purge:
            print("Rien à purger.")
            return
        if not apply:
            print("(dry-run — rien modifié ; relancer avec --apply pour anonymiser)")
            return
        now = datetime.now()
        c.executemany(
            "UPDATE contacts SET prenom='', nom='', tel='', website='', societe='', "
            "job_title='', civility='', job_function='', "
            "email='purged-' || id || '@anonymized.local', updated_at=? WHERE id=?",
            [[now, cid] for cid in purge],
        )
        print(f"Anonymisés : {len(purge)} contact(s).")
    finally:
        c.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="anonymise réellement (sinon dry-run)")
    main(apply=ap.parse_args().apply)
