#!/usr/bin/env python3
"""pool_rattrapage.py — remet dans le pool les contacts que le verrou DuckDB a fait tomber.

Le scraper écrit deux fois : d'abord dans `god_mode.duckdb` (`scrappe_pending`, puis
`scrappe` une fois Mailnjoy passé), ensuite dans le pool `contacts.duckdb` — et cette
seconde écriture ouvre sa propre connexion, contact par contact. Quand un autre processus
tient le verrou du pool (nettoyage nocturne, enrichissement, autre passe de collecte),
elle échoue ; l'erreur est imprimée et la boucle continue. Le contact reste alors dans
`scrappe`, vérifié et payé, mais **invisible d'Acquisition et de toute campagne**.

Constat du 2026-08-23 : 4 136 adresses de `scrappe` absentes du pool, dont 3 151 portent
une pierre tombale (`scrappe_rejected` : rejetées à dessein par le nettoyage, il ne faut
surtout pas les ressusciter) — et **985 récupérables**, jamais sollicitées, jamais rejetées.

Ce script est le filet, pas le correctif : il rattrape ce qui est tombé, à chaque passage.
Le rendre quotidien vaut mieux que fiabiliser la double écriture, parce qu'il rattrape
aussi tout ce qui tombera pour une raison qu'on n'a pas prévue.

Trois garde-fous, dans cet ordre :
  - une adresse présente dans `scrappe_rejected` n'est JAMAIS réinjectée ;
  - les règles de collecte D'AUJOURD'HUI sont réappliquées : ces contacts ont été collectés
    avant la liste noire des adresses de rôle du 2026-08-21, et rattraper `contact@`,
    `rgpd@` ou une boîte d'ingestion Sentry reviendrait à défaire cette décision ;
  - le verdict Mailnjoy stocké est recopié tel quel, donc aucun crédit n'est redépensé.

Usage :
    python3 scripts/pool_rattrapage.py --dry-run   # compte, n'écrit rien
    python3 scripts/pool_rattrapage.py             # applique
    python3 scripts/pool_rattrapage.py --depuis 2026-08-01
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"


def _god(read_only: bool = True):
    import duckdb
    return duckdb.connect(str(GOD_DB), read_only=read_only)


def _refuse_aujourdhui(email: str) -> str | None:
    """Le motif de rejet selon les règles de collecte actuelles, ou None si l'adresse passe.

    On rejoue les rejets DURS de `email_validator` — pas le pipeline complet : le contrôle
    MX y coûte un aller-retour DNS par adresse, et il n'apprendrait rien de plus qu'un
    verdict Mailnjoy déjà payé, qui est strictement plus fort.
    """
    import email_validator as ev

    if not ev.is_syntax_valid(email):
        return "syntaxe"
    for controle in (ev.has_forbidden_patterns, ev.is_honeypot, ev.is_forbidden_tld,
                     ev.is_role_based, ev.is_placeholder, ev.is_disposable):
        rejete, motif = controle(email)
        if rejete:
            return motif
    if ev.is_trash_tld(email):
        return "trash_tld"
    return None


def _geo_depuis_ville(ville: str | None, dept: str | None, region: str | None):
    """Complète le département et la région à partir de la ville quand ils manquent.

    `god_mode.scrappe` ne stocke le département que sur la voie Basile : 17 lignes sur
    7 971 côté Serper. La double écriture du scraper, elle, le résout au vol via
    `resolve_city_geo` — mais elle ne laisse rien dans `scrappe`. Un rattrapage qui recopie
    la colonne telle quelle réinjecte donc des contacts sans département, **invisibles au
    ciblage géographique** alors que la ville est là. On refait le même travail que le
    scraper plutôt que de propager son trou.
    """
    if (dept or "").strip():
        return dept, region
    if not (ville or "").strip():
        return dept, region
    try:
        from workflow_geo import resolve_city_geo
        g = resolve_city_geo(ville) or {}
        return (g.get("dept") or dept), (g.get("region") or region)
    except Exception:  # noqa: BLE001
        return dept, region


def _maybe(v):
    if v is None or isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return None


def analyser(depuis: str | None = None) -> dict:
    """Ce qui manque au pool, et pourquoi — sans rien écrire."""
    import contacts_pool_backend as pool

    g = _god()
    try:
        rejetes = {r[0].strip().lower() for r in
                   g.execute("SELECT email FROM scrappe_rejected WHERE email IS NOT NULL").fetchall()}
        req = ("SELECT id, lower(trim(email)), site_code, company_name, phone, website, "
               "       sector, city, postal_code, dept_code, region_code, email_score, "
               "       email_validation_reasons, mailnjoy_check, source, created_at "
               "FROM scrappe WHERE email IS NOT NULL AND trim(email) <> ''")
        params = []
        if depuis:
            req += " AND created_at >= ?"
            params.append(depuis)
        lignes = g.execute(req, params).fetchall()
    finally:
        g.close()

    c = pool._conn(read_only=True)
    try:
        presents = {r[0].strip().lower() for r in c.execute("SELECT email FROM contacts").fetchall()}
    finally:
        c.close()

    manquants, tombstones, vus = [], 0, set()
    refuses: dict[str, int] = {}
    for r in lignes:
        em = r[1]
        if not em or em in presents or em in vus:
            continue
        vus.add(em)
        if em in rejetes:
            tombstones += 1
            continue
        motif = _refuse_aujourdhui(em)
        if motif:
            cle = motif.split(":", 1)[0]
            refuses[cle] = refuses.get(cle, 0) + 1
            continue
        manquants.append(r)
    return {"scrappe": len(lignes),
            "absents_du_pool": len(manquants) + tombstones + sum(refuses.values()),
            "tombstones_respectes": tombstones,
            "refuses_par_les_regles_actuelles": sum(refuses.values()),
            "motifs_de_refus": dict(sorted(refuses.items(), key=lambda x: -x[1])),
            "recuperables": len(manquants),
            "_lignes": manquants}


def rattraper(depuis: str | None = None, dry_run: bool = False, limite: int = 0) -> dict:
    import contacts_pool_backend as pool

    bilan = analyser(depuis)
    lignes = bilan.pop("_lignes")
    if limite:
        lignes = lignes[:limite]
    bilan["dry_run"] = dry_run
    if dry_run:
        bilan["exemples"] = [r[1] for r in lignes[:5]]
        return bilan

    # UNE seule connexion pour tout le lot : c'est précisément la connexion-par-contact
    # qui rendait la double écriture fragile.
    c = pool._conn()
    crees, echecs = 0, []
    try:
        for r in lignes:
            (_sid, em, site, societe, tel, site_web, secteur, ville, cp,
             dept, region, score, raisons, mn, source, _cree) = r
            dept, region = _geo_depuis_ville(ville, dept, region)
            try:
                cid = pool.create_in_pool({
                    "email": em,
                    "societe": societe,
                    "tel": tel,
                    "website": site_web,
                    "city": ville,
                    "postal_code": cp,
                    "dept_code": dept,
                    "region_code": region,
                    "sectors": [secteur] if secteur else None,
                    "email_score": score,
                    "email_validation_reasons": _maybe(raisons),
                    # Le verdict voyage avec le contact : sans lui il repartirait en
                    # « à vérifier » et le nettoyage nocturne rachèterait un crédit.
                    "mailnjoy_check": _maybe(mn),
                }, primary_source=(source or "serper"), conn=c)
                if cid:
                    pool.upsert_site_history(cid, site or "lcr", state="cold_email",
                                             source=(source or "serper"),
                                             by="pool_rattrapage", conn=c)
                    crees += 1
            except Exception as e:  # noqa: BLE001
                echecs.append(f"{em}: {type(e).__name__}: {e}"[:160])
    finally:
        c.close()

    bilan["crees"] = crees
    bilan["echecs"] = len(echecs)
    if echecs:
        bilan["exemples_echecs"] = echecs[:5]

    # Les nouveaux entrants doivent rejoindre PostgreSQL tout de suite : `upsert_site_history`
    # déclenche déjà `promote_contact`, mais il est best-effort. Le balayage complet de
    # `pg_reconcile` est le seul à garantir qu'aucun n'est resté en route.
    if crees:
        try:
            import pg_reconcile
            bilan["postgresql"] = pg_reconcile.reconcilier()
        except Exception as e:  # noqa: BLE001
            bilan["postgresql"] = f"échec: {type(e).__name__}: {e}"[:200]
    return bilan


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--depuis", default=None, help="date ISO, ex. 2026-08-01")
    ap.add_argument("--limite", type=int, default=0)
    a = ap.parse_args()
    print(json.dumps(rattraper(depuis=a.depuis, dry_run=a.dry_run, limite=a.limite),
                     indent=2, ensure_ascii=False, default=str))
