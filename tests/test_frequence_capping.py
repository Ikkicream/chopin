#!/usr/bin/env python3
"""Tests de la règle de fréquence : 1 email reçu -> plus rien pendant 120 jours.

Vérifie sur une base temporaire (jamais sur data/contacts.duckdb) que :
  - un envoi inscrit l'adresse en base repoussoir avec le flag à 0 et la date d'envoi ;
  - la pioche exclut toute adresse repoussée, même si son cooldown de pool a été perdu ;
  - la pioche donne la priorité aux contacts jamais sollicités ;
  - l'adresse redevient éligible au-delà des 120 jours, pas avant ;
  - un contact sans ligne contact_site_history est bien créé au marquage (bug d'août 2026 :
    UPDATE à zéro ligne muet -> jusqu'à 17 renvois de la même adresse).
"""
import json
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import contacts_pool_backend as pool  # noqa: E402

ECHECS = []


def verifie(nom, condition, detail=""):
    if condition:
        print(f"  OK   {nom}")
    else:
        print(f"  ÉCHEC {nom} {detail}")
        ECHECS.append(nom)


def _base_temporaire(tmp: Path):
    """Redirige le module vers une base neuve et crée le schéma minimal."""
    # Ce fichier teste l'implémentation DuckDB de la règle des 120 jours sur une base
    # jetable. Deux garde-fous sont indispensables :
    #
    # 1. `_PG_READS = False` — sinon les lectures partiraient vers PostgreSQL et le test
    #    interrogerait la production au lieu de sa base jetable.
    # 2. `pg_sync._ACTIF = False` — sinon `mark_pushed_to_emelia` écrirait ses envois dans
    #    le journal de PRODUCTION. C'est arrivé le 19/08/2026 : trois adresses fictives
    #    (neuf@, orphelin@, perdu@exemple.fr) se sont retrouvées dans `email_events` et
    #    dans la fenêtre de 120 jours. Un test ne doit rien laisser derrière lui.
    #
    # L'implémentation PostgreSQL de la même règle est couverte par test_pg_equivalence.py.
    pool._PG_READS = False
    try:
        import pg_sync
        pg_sync._ACTIF = False
    except ImportError:
        pass
    pool.POOL_DB = tmp
    pool._MIGRATED = False
    c = pool._connect_with_retry(read_only=False)
    c.execute("""CREATE TABLE contacts (
        id VARCHAR, email VARCHAR, prenom VARCHAR, nom VARCHAR, societe VARCHAR,
        tel VARCHAR, website VARCHAR, city VARCHAR, dept_code VARCHAR,
        region_code VARCHAR, postal_code VARCHAR, sectors VARCHAR,
        primary_source VARCHAR, email_score INTEGER, email_validation_reasons VARCHAR,
        mailnjoy_check VARCHAR, global_blacklisted BOOLEAN, blacklist_reason VARCHAR,
        blacklisted_at TIMESTAMP, created_at TIMESTAMP, updated_at TIMESTAMP)""")
    c.execute("""CREATE TABLE contact_site_history (
        id VARCHAR, contact_id VARCHAR, site_code VARCHAR, account_id VARCHAR,
        state VARCHAR, source VARCHAR, added_to_site_at TIMESTAMP,
        state_history VARCHAR, last_action_at TIMESTAMP,
        emelia_campaign_id VARCHAR, emelia_contact_id VARCHAR, email_sent_at TIMESTAMP,
        emelia_opened_at TIMESTAMP, emelia_clicked_at TIMESTAMP,
        emelia_replied_at TIMESTAMP, emelia_bounced_at TIMESTAMP,
        emelia_unsubscribed_at TIMESTAMP, last_contacted_by_site_at TIMESTAMP,
        notes VARCHAR, last_opened_at TIMESTAMP, last_clicked_at TIMESTAMP,
        last_open_channel VARCHAR, last_click_channel VARCHAR)""")
    c.execute(pool._ENRICHMENT_DDL)
    c.execute(pool.SUPPRESSION_DDL)
    c.close()
    pool._MIGRATED = True


def _ajoute_contact(email, *, contacte_il_y_a_jours=None):
    """Crée un contact valide Mailnjoy, éventuellement déjà contacté."""
    cid = str(uuid.uuid4())
    check = json.dumps({"decision": "valid",
                        "checked_at": datetime.now(timezone.utc).isoformat()})
    c = pool._conn()
    try:
        c.execute("""INSERT INTO contacts (id, email, sectors, primary_source, email_score,
                     mailnjoy_check, global_blacklisted, created_at, updated_at)
                     VALUES (?, ?, ?, 'serper', 90, ?, FALSE,
                             CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                  [cid, email, json.dumps(["immobilier"]), check])
        if contacte_il_y_a_jours is not None:
            at = datetime.now(timezone.utc) - timedelta(days=contacte_il_y_a_jours)
            c.execute("""INSERT INTO contact_site_history
                         (id, contact_id, site_code, state, source, added_to_site_at,
                          last_action_at, email_sent_at, last_contacted_by_site_at)
                         VALUES (?, ?, 'lcr', 'cold_email', 'test', CURRENT_TIMESTAMP,
                                 CURRENT_TIMESTAMP, ?, ?)""",
                      [str(uuid.uuid4()), cid, at, at])
            pool._suppress_conn(c, email, 'lcr', 'camp-test', at,
                                at + timedelta(days=pool.SUPPRESSION_DAYS), 'test')
    finally:
        c.close()
    return cid


def lance():
    with tempfile.TemporaryDirectory() as d:
        _base_temporaire(Path(d) / "pool_test.duckdb")

        print("\n1. Règle : 120 jours")
        verifie("SUPPRESSION_DAYS vaut 120", pool.SUPPRESSION_DAYS == 120,
                f"(vaut {pool.SUPPRESSION_DAYS})")
        verifie("cooldown même site aligné",
                pool.COOLDOWN_SAME_SITE_DAYS == pool.SUPPRESSION_DAYS)
        verifie("cooldown inter-sites aligné",
                pool.COOLDOWN_GLOBAL_DAYS == pool.SUPPRESSION_DAYS)

        print("\n2. Un envoi inscrit l'adresse en base repoussoir")
        neuf = _ajoute_contact("neuf@exemple.fr")
        verifie("avant envoi : contactable", not pool.is_suppressed("neuf@exemple.fr"))
        verifie("avant envoi : dans la pioche",
                "neuf@exemple.fr" in [x["email"] for x in
                                      pool.pick_for_campaign("lcr", "immobilier", limit=50)])
        pool.upsert_site_history(neuf, "lcr", state="cold_email")
        pool.mark_pushed_to_emelia(neuf, "lcr", "camp-1")
        verifie("après envoi : flag à 0", pool.is_suppressed("neuf@exemple.fr"))
        c = pool._conn(read_only=True)
        row = c.execute("SELECT contactable, last_sent_at, release_at FROM email_suppression "
                        "WHERE email = 'neuf@exemple.fr'").fetchone()
        c.close()
        verifie("flag stocké à 0", row is not None and row[0] == 0)
        verifie("date d'envoi stockée", row is not None and row[1] is not None)
        verifie("libération à +120 jours",
                row is not None and 119 <= (row[2] - row[1]).days <= 120)
        verifie("après envoi : hors pioche",
                "neuf@exemple.fr" not in [x["email"] for x in
                                          pool.pick_for_campaign("lcr", "immobilier", limit=50)])

        print("\n3. Le contact sans historique est créé au marquage (bug d'août 2026)")
        orphelin = _ajoute_contact("orphelin@exemple.fr")
        pool.mark_pushed_to_emelia(orphelin, "lcr", "camp-2")
        c = pool._conn(read_only=True)
        h = c.execute("SELECT last_contacted_by_site_at FROM contact_site_history "
                      "WHERE contact_id = ?", [orphelin]).fetchone()
        c.close()
        verifie("ligne d'historique créée", h is not None)
        verifie("cooldown posé", h is not None and h[0] is not None)
        verifie("inscrit en base repoussoir", pool.is_suppressed("orphelin@exemple.fr"))
        verifie("hors pioche",
                "orphelin@exemple.fr" not in [x["email"] for x in
                                              pool.pick_for_campaign("lcr", "immobilier", limit=50)])

        print("\n4. Fenêtre de 120 jours : bornes")
        _ajoute_contact("recent@exemple.fr", contacte_il_y_a_jours=119)
        _ajoute_contact("ancien@exemple.fr", contacte_il_y_a_jours=121)
        pris = [x["email"] for x in pool.pick_for_campaign("lcr", "immobilier", limit=50)]
        verifie("119 jours -> toujours bloqué", "recent@exemple.fr" not in pris)
        verifie("121 jours -> de nouveau éligible", "ancien@exemple.fr" in pris)

        print("\n5. Priorité aux jamais contactés")
        for i in range(5):
            _ajoute_contact(f"frais{i}@exemple.fr")
        pris = pool.pick_for_campaign("lcr", "immobilier", limit=3)
        verifie("le lot ne contient que des jamais contactés",
                all(not x.get("last_contacted_by_site_at") for x in pris),
                f"({[x['email'] for x in pris]})")

        print("\n6. La base repoussoir prime même si le pool a perdu le cooldown")
        perdu = _ajoute_contact("perdu@exemple.fr")
        pool.upsert_site_history(perdu, "lcr", state="cold_email")
        pool.mark_pushed_to_emelia(perdu, "lcr", "camp-3")
        c = pool._conn()  # on efface le cooldown côté pool, la repoussoir reste
        c.execute("UPDATE contact_site_history SET last_contacted_by_site_at = NULL, "
                  "email_sent_at = NULL WHERE contact_id = ?", [perdu])
        c.close()
        pris = [x["email"] for x in pool.pick_for_campaign("lcr", "immobilier", limit=50)]
        verifie("adresse repoussée reste hors pioche", "perdu@exemple.fr" not in pris)

        print("\n7. release_expired() ne libère que le hors-fenêtre")
        avant = pool.suppression_stats()["bloques"]
        liberes = pool.release_expired()
        apres = pool.suppression_stats()["bloques"]
        verifie("seul le contact à 121 jours est libéré", liberes == 1, f"(libérés={liberes})")
        verifie("les autres restent bloqués", apres == avant)

    print("\n" + "=" * 60)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS)}")
        return 1
    print("Tous les tests passent.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
