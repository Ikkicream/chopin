#!/usr/bin/env python3
"""pg_reconcile.py — Met PostgreSQL en conformité avec la porte d'entrée.

Balayage complet dans les deux sens :
  - RETIRE de PostgreSQL tout contact qui ne satisfait plus `pg_gate.ELIGIBILITE_SQL` ;
  - PROMEUT tout contact éligible qui n'y est pas encore.

À lancer après l'enrichissement quotidien : c'est lui qui fait franchir la porte aux contacts
qui attendaient leur vérification data.gouv, et qui en sort ceux que l'enrichissement vient
d'exclure (entreprise fermée, administration, diffusion partielle).

Le journal `email_events` n'est JAMAIS touché. Un contact retiré y garde ses lignes — elles
sont indexées sur l'adresse — donc la fenêtre de 120 jours continue de le protéger même
lorsqu'il n'est plus dans le référentiel. C'est le mécanisme qui manquait en août 2026,
quand un contact purgé puis re-scrapé repartait vierge et se faisait renvoyer un email.

Usage :
    python3 scripts/pg_reconcile.py            # applique
    python3 scripts/pg_reconcile.py --dry-run  # montre sans écrire
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))


def _dsn() -> str:
    for ligne in (BASE_DIR / ".env").read_text().splitlines():
        if ligne.startswith("PG_DSN="):
            return ligne.split("=", 1)[1].strip()
    raise SystemExit("PG_DSN absent de .env")


def reconcilier(dry_run: bool = False) -> dict:
    """Met PostgreSQL en conformité avec le pool — TOUS les contacts, avec leur état.

    **Changement du 2026-08-20.** Avant, cette fonction appliquait une porte : elle
    insérait les contacts éligibles et SUPPRIMAIT ceux qui ne l'étaient plus. Résultat,
    1 776 contacts sur 7 970 n'existaient pas dans PostgreSQL — invisibles à tout écran qui
    le lit, et impossible d'y faire écrire le scraping.

    Désormais : tout le monde entre, chacun avec son `etat` (`a_verifier`, `ok`, `ko`,
    `exclu`, `spam`). Un contact n'est supprimé que s'il a DISPARU du pool — plus jamais
    parce qu'il est devenu mauvais. Un mauvais contact reste, marqué, ce qui vaut infiniment
    mieux : on se souvient de l'avoir écarté au lieu de le re-scraper trois semaines plus tard.
    """
    import psycopg2
    import psycopg2.extras
    import pg_gate
    import pg_sync

    duck = pg_gate._duck()
    try:
        contacts = {d["email"].strip().lower(): d
                    for d in pg_gate.tous_contacts(conn=duck) if d.get("email")}
    finally:
        duck.close()

    pg = psycopg2.connect(_dsn())
    pg.autocommit = False
    cur = pg.cursor()
    try:
        cur.execute("SELECT lower(email::text) FROM contacts")
        presents = {r[0] for r in cur.fetchall()}

        a_retirer = sorted(presents - set(contacts))     # disparus du pool, et eux seuls
        a_creer = sorted(set(contacts) - presents)

        bilan = {"pool": len(contacts), "presents_avant": len(presents),
                 "a_retirer": len(a_retirer), "a_creer": len(a_creer),
                 "dry_run": dry_run}

        if dry_run:
            bilan["exemples_retires"] = a_retirer[:5]
            bilan["exemples_crees"] = a_creer[:5]
            pg.rollback()
            return bilan

        if a_retirer:
            # Les événements survivent : `email_events.contact_id` est en ON DELETE SET NULL
            # et la colonne `email` porte l'identité. On le vérifie juste après.
            avant = _compter_evenements(cur, a_retirer)
            psycopg2.extras.execute_batch(
                cur, "DELETE FROM contacts WHERE lower(email::text) = %s",
                [(e,) for e in a_retirer], page_size=500)
            apres = _compter_evenements(cur, a_retirer)
            bilan["evenements_conserves"] = apres
            if apres != avant:
                pg.rollback()
                raise RuntimeError(
                    f"Le retrait a détruit des événements ({avant} -> {apres}) — "
                    f"annulé. La fenêtre de 120 jours en dépend.")

        for em in a_creer:
            _inserer(cur, contacts[em])

        # L'état de TOUT LE MONDE est réaligné à chaque passage : c'est lui qui pilotera la
        # pioche des campagnes, il ne doit jamais dater.
        maj = [(d["etat"], d.get("etat_motif"), bool(d.get("global_blacklisted")),
                d.get("blacklist_reason"), em) for em, d in contacts.items()]
        psycopg2.extras.execute_batch(cur, """
            UPDATE contacts SET etat = %s, etat_motif = %s, etat_at = now(),
                                global_blacklisted = %s, blacklist_reason = %s
            WHERE lower(email::text) = %s
              AND (etat IS DISTINCT FROM %s OR global_blacklisted IS DISTINCT FROM %s)
        """, [(e, m, bl, br, em, e, bl) for e, m, bl, br, em in maj], page_size=500)

        pg.commit()

        cur.execute("SELECT count(*) FROM contacts")
        bilan["presents_apres"] = int(cur.fetchone()[0])
        cur.execute("SELECT etat, count(*) FROM contacts GROUP BY 1 ORDER BY 2 DESC")
        bilan["par_etat"] = {r[0]: int(r[1]) for r in cur.fetchall()}
    except Exception:
        pg.rollback()
        raise
    finally:
        cur.close()
        pg.close()

    # Les états par site des nouveaux entrants, via le chemin normal.
    if not dry_run and a_creer:
        duck = pg_gate._duck()
        try:
            for em in a_creer:
                cid = contacts[em]["id"]
                for site in pg_gate.sites_du_contact(cid, conn=duck):
                    st = pg_gate.etat_site(cid, site, conn=duck)
                    if st:
                        pg_sync.sync_contact_site(cid, site, st["state"],
                                                  st.get("source") or "", st.get("history"))
        finally:
            duck.close()

    # Filet de l'attribution automatique : `sync_contact_site` attribue déjà chaque contact
    # au moment où il devient lead / PRM, mais un contact entré par un autre chemin — ou
    # promu pendant que PostgreSQL était injoignable — resterait sans propriétaire, donc
    # sans appel. Ce balayage ne touche que ceux qui n'appartiennent à personne.
    if not dry_run:
        try:
            import followup_backend as fb
            bilan["attributions_auto"] = {
                s: fb.attribuer_auto(s).get("attribues", 0) for s in ("lcr", "mkd")
            }
        except Exception as e:  # noqa: BLE001
            bilan["attributions_auto"] = f"échec: {type(e).__name__}: {e}"[:200]
    return bilan


def _compter_evenements(cur, emails: list[str]) -> int:
    cur.execute("SELECT count(*) FROM email_events WHERE lower(email::text) = ANY(%s)",
                (emails,))
    return int(cur.fetchone()[0] or 0)


def _inserer(cur, d: dict) -> None:
    mn = d.get("mailnjoy_check") or {}
    if isinstance(mn, str):
        try:
            mn = json.loads(mn)
        except Exception:
            mn = {}
    secteurs = d.get("sectors") or []
    if isinstance(secteurs, str):
        try:
            secteurs = json.loads(secteurs)
        except Exception:
            secteurs = []
    cur.execute("""
        INSERT INTO contacts (id, email, prenom, nom, societe, tel, website, city,
            dept_code, region_code, postal_code, sectors, primary_source, email_score,
            mailnjoy_decision, mailnjoy_checked_at, mailnjoy_check, global_blacklisted,
            blacklist_reason, created_at, updated_at, etat, etat_motif, etat_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), now(),
                %s,%s,now())
        ON CONFLICT (email) DO NOTHING
    """, (d.get("id"), d["email"].strip().lower(), d.get("prenom"), d.get("nom"),
          d.get("societe"), d.get("tel"), d.get("website"), d.get("city"),
          d.get("dept_code"), d.get("region_code"), d.get("postal_code"), secteurs,
          d.get("primary_source"), d.get("email_score"), mn.get("decision"),
          mn.get("checked_at"), json.dumps(mn) if mn else None,
          # Écrit en dur à `false` jusqu'au 2026-08-20 : les 1 482 contacts blacklistés
          # entraient dans PostgreSQL comme s'ils ne l'étaient pas. L'état (`spam`) était
          # juste, mais la colonne brute mentait — et c'est elle que lit la clause
          # d'éligibilité des envois.
          bool(d.get("global_blacklisted")), d.get("blacklist_reason"),
          d.get("etat") or "a_verifier", d.get("etat_motif")))


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    b = reconcilier(dry_run=dry)
    print(json.dumps(b, indent=2, ensure_ascii=False))
