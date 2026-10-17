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


def _env(cle: str) -> str:
    try:
        for ligne in (BASE_DIR / ".env").read_text().splitlines():
            if ligne.startswith(cle + "="):
                return ligne.split("=", 1)[1].strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def main_pg(apply=False):
    """Même règle, sur le pool PostgreSQL (lot 2, 07/10 : contacts.duckdb n'est plus la
    référence — anonymiser là-bas laisserait les vraies données intactes).

    Le dernier contact se lit dans `contact_sites` ET dans le journal `email_events`, qui
    voit tous les canaux. L'anonymisation s'étend aux lignes du journal de ces contacts :
    le journal porte l'adresse en clair, et à plus de 3 ans il ne sert plus à la fenêtre
    de 120 jours.

    Garde-fou : tant que `RGPD_PG_VALIDE=1` n'est pas dans .env, `--apply` reste un test à
    blanc. C'est le seul script qui détruit définitivement ; sa première passe sur
    PostgreSQL se valide sur la liste qu'il annonce, pas sur la foi du code.
    """
    import sys as _s
    _s.path.insert(0, str(BASE_DIR / "scripts"))
    import pool_pg
    garde = """
        WITH dernier AS (
            SELECT ct.id, ct.email::text AS email,
                   GREATEST(ct.created_at,
                            (SELECT max(GREATEST(cs.email_sent_at, cs.last_contacted_by_site_at,
                                                 cs.last_action_at, cs.emelia_opened_at,
                                                 cs.emelia_clicked_at, cs.emelia_replied_at,
                                                 cs.last_opened_at, cs.last_clicked_at))
                               FROM contact_sites cs WHERE cs.contact_id = ct.id),
                            (SELECT max(ev.occurred_at) FROM email_events ev
                              WHERE ev.email = ct.email)) AS dernier
              FROM contacts ct
             WHERE NOT COALESCE(ct.global_blacklisted, false)
               AND NOT ct.est_test
               AND ct.email::text NOT LIKE 'purged-%%'
               AND NOT EXISTS (SELECT 1 FROM contact_sites cs WHERE cs.contact_id = ct.id
                                 AND lower(cs.state) IN ('prm', 'lead', 'crm')))
        SELECT id::text, email, dernier FROM dernier
         WHERE dernier < now() - make_interval(days => %(j)s)"""
    cibles = pool_pg._q(garde, {"j": RETENTION_DAYS})
    total = pool_pg._q("SELECT count(*) FROM contacts")[0][0]
    print(f"[PostgreSQL] Rétention {RETENTION_DAYS // 365} ans · contacts={total} · "
          f"à anonymiser={len(cibles)}")
    for cid, em, der in cibles[:20]:
        print(f"   {em} — dernier contact {str(der)[:10]}")
    if not cibles:
        print("Rien à purger.")
        return
    if not apply or _env("RGPD_PG_VALIDE") != "1":
        print("(test à blanc — rien modifié. Passage réel : --apply ET RGPD_PG_VALIDE=1 dans .env)")
        return
    for cid, em, _ in cibles:
        anonyme = f"purged-{cid}@anonymized.local"
        pool_pg._ecrire("UPDATE email_events SET email = %(a)s WHERE email = %(e)s",
                        {"a": anonyme, "e": em})
        pool_pg._ecrire("""UPDATE contacts SET prenom = '', nom = '', tel = '', website = '',
                                  societe = '', job_title = '', civility = '', job_function = '',
                                  email = %(a)s, updated_at = now() WHERE id::text = %(c)s""",
                        {"a": anonyme, "c": cid})
    print(f"Anonymisés : {len(cibles)} contact(s).")


def main(apply=False):
    if _env("POOL_PG") == "1":
        return main_pg(apply)
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
