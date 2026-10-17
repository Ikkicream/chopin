#!/usr/bin/env python3
"""pool_ecriture_pg.py — le pool de contacts ÉCRIT dans PostgreSQL (lot 2, 07/10).

Lot 1 : la chaîne d'acquisition (scrappe*) est passée dans PostgreSQL.
Lot 2 : le pool lui-même. PostgreSQL devient la SEULE référence des contacts, de leur état
par site, de leur engagement et de leur enrichissement ; `contacts.duckdb` n'est plus écrit.

Ce module porte les versions PostgreSQL des fonctions d'écriture de
`contacts_pool_backend` (mêmes signatures, mêmes règles : remplissage des seuls champs
vides, montée d'état sans jamais redescendre sauf « blacklisted », cooldown vérifié après
marquage d'un envoi). Les lectures existent déjà dans `pool_pg`.

Activé par `POOL_PG=1` dans .env (`actif()`), relu à chaque appel.

La fenêtre de 120 jours n'a pas de table ici : elle se DÉDUIT du journal des envois
(`v_suppression` sur `email_events`). `suppress()` n'a donc rien à écrire — c'est
`pg_sync.record_send`, appelé à chaque envoi, qui la porte.

Usage : python3 scripts/pool_ecriture_pg.py schema | copier | etat
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))


def actif() -> bool:
    try:
        for ligne in (BASE_DIR / ".env").read_text().splitlines():
            if ligne.startswith("POOL_PG="):
                return ligne.split("=", 1)[1].strip() == "1"
    except Exception:  # noqa: BLE001
        pass
    return False


def _q(sql, params=None):
    import pool_pg
    return pool_pg._q(sql, params or {})


def _ecrire(sql, params=None) -> int:
    import pool_pg
    return pool_pg._ecrire(sql, params or {})


def _ecrire_rendre(sql, params=None):
    import acq_pg
    return acq_pg._ecrire_rendre(sql, params or {})


def _norm(email: str) -> str:
    return (email or "").strip().lower()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Schéma : ce que DuckDB portait et que PostgreSQL n'avait pas ─────────────
SCHEMA = """
ALTER TABLE contact_sites ADD COLUMN IF NOT EXISTS emelia_campaign_id text;
ALTER TABLE contact_sites ADD COLUMN IF NOT EXISTS emelia_contact_id text;
ALTER TABLE contact_sites ADD COLUMN IF NOT EXISTS email_sent_at timestamptz;
ALTER TABLE contact_sites ADD COLUMN IF NOT EXISTS emelia_opened_at timestamptz;
ALTER TABLE contact_sites ADD COLUMN IF NOT EXISTS emelia_clicked_at timestamptz;
ALTER TABLE contact_sites ADD COLUMN IF NOT EXISTS emelia_replied_at timestamptz;
ALTER TABLE contact_sites ADD COLUMN IF NOT EXISTS emelia_bounced_at timestamptz;
ALTER TABLE contact_sites ADD COLUMN IF NOT EXISTS emelia_unsubscribed_at timestamptz;
ALTER TABLE contact_sites ADD COLUMN IF NOT EXISTS last_contacted_by_site_at timestamptz;
ALTER TABLE contact_sites ADD COLUMN IF NOT EXISTS last_opened_at timestamptz;
ALTER TABLE contact_sites ADD COLUMN IF NOT EXISTS last_clicked_at timestamptz;
ALTER TABLE contact_sites ADD COLUMN IF NOT EXISTS last_open_channel text;
ALTER TABLE contact_sites ADD COLUMN IF NOT EXISTS last_click_channel text;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS nom_commercial text;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS sigle text;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS section_naf text;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS tranche_effectif_code text;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS code_postal text;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS code_insee text;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS latitude double precision;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS longitude double precision;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS etat_administratif text;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS date_creation text;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS date_fermeture text;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS statut_diffusion text;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS est_bio boolean;
ALTER TABLE contact_enrichment ADD COLUMN IF NOT EXISTS est_societe_mission boolean
"""


def creer_schema() -> None:
    for stmt in [s.strip() for s in SCHEMA.split(";") if s.strip()]:
        _ecrire(stmt)


def _etat(email: str) -> None:
    import acq_pg
    acq_pg.recalculer_etat(email)


# ── Contacts ─────────────────────────────────────────────────────────────────
_COLS_CONTACT = None


def _cols_contact() -> list[str]:
    global _COLS_CONTACT
    if _COLS_CONTACT is None:
        _COLS_CONTACT = [r[0] for r in _q(
            "SELECT column_name FROM information_schema.columns WHERE table_name='contacts' "
            "ORDER BY ordinal_position")]
    return _COLS_CONTACT


def _contact_dict(row) -> dict:
    d = dict(zip(_cols_contact(), row))
    d["id"] = str(d["id"]) if d.get("id") else None
    d["email"] = str(d["email"]) if d.get("email") else None
    return d


def find_by_email_global(email: str) -> dict | None:
    em = _norm(email)
    if not em:
        return None
    r = _q(f"SELECT {', '.join(_cols_contact())} FROM contacts WHERE email = %(e)s", {"e": em})
    return _contact_dict(r[0]) if r else None


_SCALAIRES = ("prenom", "nom", "societe", "tel", "website", "city", "dept_code",
              "region_code", "postal_code", "email_score", "primary_source", "job_title",
              "civility", "job_function", "prenom_source")


def create_in_pool(data: dict, primary_source: str | None = None) -> str | None:
    """Insère ou complète (champs VIDES seulement) — même contrat que la version DuckDB."""
    import acq_pg
    em = _norm(data.get("email", ""))
    if not em or "@" not in em:
        return None
    secteurs = data.get("sectors")
    if isinstance(secteurs, str):
        try:
            secteurs = json.loads(secteurs)
        except Exception:  # noqa: BLE001
            secteurs = [secteurs]
    secteurs = [s for s in (secteurs or []) if s]
    mn = data.get("mailnjoy_check")
    if isinstance(mn, str):
        try:
            mn = json.loads(mn)
        except Exception:  # noqa: BLE001
            mn = None
    p = {c: (data.get(c) if data.get(c) not in ("",) else None) for c in _SCALAIRES}
    p["primary_source"] = primary_source or data.get("primary_source") or "manual"
    p.update({"em": em, "sec": secteurs, "evr": acq_pg._j(data.get("email_validation_reasons")),
              "mn": acq_pg._j(mn) if mn else None,
              "mnd": (mn or {}).get("decision") if mn else None,
              "mna": (mn or {}).get("checked_at") if mn else None})
    sets = ",\n            ".join(f"{c} = COALESCE(NULLIF(contacts.{c}::text, ''), EXCLUDED.{c}::text)::{t}"
                                   for c, t in (("prenom", "text"), ("nom", "text"),
                                                ("societe", "text"), ("tel", "text"),
                                                ("website", "text"), ("city", "text"),
                                                ("dept_code", "text"), ("region_code", "text"),
                                                ("postal_code", "text"),
                                                ("job_title", "text"), ("civility", "text"),
                                                ("job_function", "text"),
                                                ("prenom_source", "text")))
    r = _ecrire_rendre(f"""
        INSERT INTO contacts (id, email, prenom, nom, societe, tel, website, city, dept_code,
                              region_code, postal_code, sectors, primary_source, email_score,
                              email_validation_reasons, mailnjoy_check, mailnjoy_decision,
                              mailnjoy_checked_at, job_title, civility, job_function,
                              prenom_source, entre_par_pg)
        VALUES (gen_random_uuid(), %(em)s, %(prenom)s, %(nom)s, %(societe)s, %(tel)s,
                %(website)s, %(city)s, %(dept_code)s, %(region_code)s, %(postal_code)s,
                %(sec)s::text[], %(primary_source)s, %(email_score)s, %(evr)s::jsonb,
                %(mn)s::jsonb, %(mnd)s, %(mna)s::timestamptz, %(job_title)s, %(civility)s,
                %(job_function)s, %(prenom_source)s, true)
        ON CONFLICT (email) DO UPDATE SET
            {sets},
            email_score = COALESCE(contacts.email_score, EXCLUDED.email_score),
            email_validation_reasons = COALESCE(contacts.email_validation_reasons,
                                                EXCLUDED.email_validation_reasons),
            mailnjoy_check = COALESCE(contacts.mailnjoy_check, EXCLUDED.mailnjoy_check),
            mailnjoy_decision = COALESCE(contacts.mailnjoy_decision, EXCLUDED.mailnjoy_decision),
            mailnjoy_checked_at = COALESCE(contacts.mailnjoy_checked_at,
                                           EXCLUDED.mailnjoy_checked_at),
            sectors = CASE WHEN cardinality(contacts.sectors) = 0 THEN EXCLUDED.sectors
                           ELSE contacts.sectors END
        RETURNING id::text""", p)
    cid = r[0][0] if r else None
    if cid:
        _etat(em)
    return cid


def set_global_blacklist(email: str, reason: str = "") -> bool:
    em = _norm(email)
    if not em:
        return False
    _ecrire("""UPDATE contacts SET global_blacklisted = true, blacklist_reason = %(r)s,
                      blacklisted_at = now(), etat = 'spam', etat_motif = %(r)s, etat_at = now()
               WHERE email = %(e)s AND NOT est_test""", {"r": (reason or "")[:200], "e": em})
    _ecrire("""UPDATE contact_sites SET state = 'blacklisted', last_action_at = now()
               WHERE contact_id = (SELECT id FROM contacts WHERE email = %(e)s)""", {"e": em})
    return True


# ── État par site (contact_sites) ─────────────────────────────────────────────
_COLS_SITE = None


def _cols_site() -> list[str]:
    global _COLS_SITE
    if _COLS_SITE is None:
        _COLS_SITE = [r[0] for r in _q(
            "SELECT column_name FROM information_schema.columns WHERE table_name='contact_sites' "
            "ORDER BY ordinal_position")]
    return _COLS_SITE


def get_history_for_site(contact_id: str, site_code: str) -> dict | None:
    r = _q(f"SELECT {', '.join(_cols_site())} FROM contact_sites "
           f"WHERE contact_id = %(c)s::uuid AND site_code = %(s)s",
           {"c": contact_id, "s": site_code})
    if not r:
        return None
    d = dict(zip(_cols_site(), r[0]))
    d["id"] = str(d["id"])
    d["contact_id"] = str(d["contact_id"])
    d["added_to_site_at"] = d.get("added_at")      # nom historique DuckDB
    return d


def upsert_site_history(contact_id: str, site_code: str, state: str = "cold_email",
                        source: str = "manual", account_id: str | None = None,
                        by: str = "system", note: str = "") -> str:
    from contacts_pool_backend import STATE_RANK
    ex = get_history_for_site(contact_id, site_code)
    entree = {"state": state, "date": _now_iso(), "by": by, "note": note}
    if ex:
        if STATE_RANK.get(state, 0) > STATE_RANK.get(ex.get("state"), 0) or state == "blacklisted":
            hist = list(ex.get("state_history") or []) + [entree]
            _ecrire("""UPDATE contact_sites SET state = %(st)s, state_history = %(h)s::jsonb,
                              last_action_at = now() WHERE id = %(id)s::uuid""",
                    {"st": state, "h": json.dumps(hist), "id": ex["id"]})
            _apres_changement(contact_id, site_code, state)
        return ex["id"]
    r = _ecrire_rendre("""
        INSERT INTO contact_sites (id, contact_id, site_code, account_id, state, source,
                                   added_at, state_history, last_action_at)
        VALUES (gen_random_uuid(), %(c)s::uuid, %(s)s, %(a)s, %(st)s, %(src)s, now(),
                %(h)s::jsonb, now())
        ON CONFLICT (contact_id, site_code) DO NOTHING
        RETURNING id::text""",
        {"c": contact_id, "s": site_code, "a": account_id, "st": state, "src": source,
         "h": json.dumps([entree])})
    _apres_changement(contact_id, site_code, state)
    if r:
        return r[0][0]
    ex = get_history_for_site(contact_id, site_code)
    return ex["id"] if ex else ""


def _apres_changement(contact_id: str, site_code: str, state: str) -> None:
    """Un contact qui devient lead / PRM entre dans la liste d'appels (cf. pg_sync)."""
    if state in ("lead", "prm"):
        try:
            import pg_sync
            pg_sync._attribuer_rappel(contact_id, site_code)
        except Exception as e:  # noqa: BLE001
            print(f"[pool_pg] attribution du rappel : {type(e).__name__}: {e}", flush=True)


def change_state_for_site(contact_id: str, site_code: str, new_state: str,
                          by: str = "system", note: str = "") -> bool:
    from contacts_pool_backend import STATE_RANK
    if not contact_id or not site_code:
        return False
    ex = get_history_for_site(contact_id, site_code)
    if not ex:
        upsert_site_history(contact_id, site_code, state=new_state, by=by, note=note)
        return True
    cur = ex.get("state")
    if cur == "blacklisted":
        return False
    if STATE_RANK.get(new_state, 0) <= STATE_RANK.get(cur, 0) and new_state != "blacklisted":
        return False
    hist = list(ex.get("state_history") or []) + [
        {"state": new_state, "date": _now_iso(), "by": by, "note": note}]
    _ecrire("""UPDATE contact_sites SET state = %(st)s, state_history = %(h)s::jsonb,
                      last_action_at = now() WHERE id = %(id)s::uuid""",
            {"st": new_state, "h": json.dumps(hist), "id": ex["id"]})
    _apres_changement(contact_id, site_code, new_state)
    return True


# ── Envois et événements ──────────────────────────────────────────────────────
def mark_pushed_to_emelia(contact_id: str, site_code: str, campaign_id: str,
                          emelia_contact_id: str = "", email: str | None = None,
                          mailbox: str | None = None, modele: str | None = None) -> None:
    """Marque un envoi. Le journal (`record_send`) PORTE la fenêtre de 120 jours : il est
    écrit d'abord, et le marquage est VÉRIFIÉ ensuite — un marquage muet se paie en renvois."""
    import pg_sync
    em = _norm(email) if email else None
    if not em:
        r = _q("SELECT email::text FROM contacts WHERE id = %(c)s::uuid", {"c": contact_id})
        em = r[0][0] if r else None
    if em:
        pg_sync.record_send(em, site_code, contact_id=contact_id, campaign_id=campaign_id,
                            mailbox=mailbox, modele=modele)
    if not get_history_for_site(contact_id, site_code):
        upsert_site_history(contact_id, site_code, state="cold_email", source="campaign",
                            by="campaign_engine",
                            note=f"ligne créée au marquage d'envoi ({campaign_id})")
    _ecrire("""UPDATE contact_sites SET emelia_campaign_id = %(cp)s, emelia_contact_id = %(ec)s,
                      email_sent_at = now(), last_contacted_by_site_at = now(),
                      last_action_at = now()
               WHERE contact_id = %(c)s::uuid AND site_code = %(s)s""",
            {"cp": campaign_id, "ec": emelia_contact_id or "pushed", "c": contact_id,
             "s": site_code})
    ok = _q("""SELECT count(*) FROM contact_sites WHERE contact_id = %(c)s::uuid
               AND site_code = %(s)s AND last_contacted_by_site_at IS NOT NULL""",
            {"c": contact_id, "s": site_code})
    if not ok or not ok[0][0]:
        raise RuntimeError(f"cooldown non posé pour {contact_id}/{site_code} — risque de renvoi")


_COL_EVT = {"SENT": "email_sent_at", "OPENED": "emelia_opened_at",
            "CLICKED": "emelia_clicked_at", "REPLIED": "emelia_replied_at",
            "BOUNCED": "emelia_bounced_at", "UNSUBSCRIBED": "emelia_unsubscribed_at"}


def record_emelia_event(contact_id: str, site_code: str, event_type: str,
                        event_date=None) -> None:
    col = _COL_EVT.get((event_type or "").upper())
    if not col:
        return
    _ecrire(f"""UPDATE contact_sites SET {col} = COALESCE(%(t)s::timestamptz, now()),
                       last_action_at = now()
                WHERE contact_id = %(c)s::uuid AND site_code = %(s)s""",
            {"t": event_date, "c": contact_id, "s": site_code})


def record_engagement(site_code: str, email: str, kind: str, channel: str,
                      at: str | None = None, only_if_null: bool = False,
                      proxy: bool = False) -> bool:
    if kind not in ("open", "click") or not email or "@" not in email:
        return False
    at = str(at or _now_iso())
    cols = [("last_opened_at", "last_open_channel")]
    if kind == "click":
        cols = [("last_clicked_at", "last_click_channel")] + cols
    for col, ch in cols:
        garde = f"cs.{col} IS NULL" if only_if_null else f"(cs.{col} IS NULL OR cs.{col} < %(at)s::timestamptz)"
        _ecrire(f"""UPDATE contact_sites cs SET {col} = %(at)s::timestamptz, {ch} = %(ch)s
                    FROM contacts c2
                    WHERE cs.contact_id = c2.id AND cs.site_code = %(s)s
                      AND c2.email = %(e)s AND {garde}""",
                {"at": at, "ch": channel, "s": site_code, "e": _norm(email)})
    try:
        import pg_sync
        pg_sync.record_event(_norm(email), kind, site_code, channel, at=at)
    except Exception as e:  # noqa: BLE001
        print(f"[pool_pg] journal d'engagement : {type(e).__name__}: {e}", flush=True)
    if kind == "click" or not proxy:
        try:
            import expediteur
            expediteur.confirmer(email)
        except Exception as e:  # noqa: BLE001
            print(f"[pool_pg] affinité expéditeur : {type(e).__name__}: {e}", flush=True)
    return True


# ── Enrichissement data.gouv ──────────────────────────────────────────────────
_COLS_ENR = ("contact_id", "siret", "siren", "denomination", "nom_commercial", "sigle",
             "code_naf", "section_naf", "categorie_entreprise", "tranche_effectif_code",
             "tranche_effectif_libelle", "code_postal", "code_insee", "commune", "dept_code",
             "region_code", "latitude", "longitude", "etat_administratif", "date_creation",
             "date_fermeture", "statut_diffusion", "est_rge", "est_qualiopi", "est_ess",
             "est_bio", "est_societe_mission", "match_quality", "excluded",
             "exclusion_reason", "raw", "enriched_at")


def upsert_enrichment(d: dict) -> None:
    """Équivalent de l'`INSERT OR REPLACE INTO contact_enrichment` de datagouv_enrich."""
    import acq_pg
    vals = {c: d.get(c) for c in _COLS_ENR}
    vals["raw"] = acq_pg._j(vals.get("raw"))
    vals["excluded"] = bool(vals.get("excluded"))
    vals["enriched_at"] = vals.get("enriched_at") or _now_iso()
    cols = ", ".join(_COLS_ENR)
    ph = ", ".join(f"%({c})s" + ("::uuid" if c == "contact_id" else "::jsonb" if c == "raw"
                                 else "::timestamptz" if c == "enriched_at" else "")
                   for c in _COLS_ENR)
    maj = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLS_ENR if c != "contact_id")
    _ecrire(f"""INSERT INTO contact_enrichment ({cols}) VALUES ({ph})
                ON CONFLICT (contact_id) DO UPDATE SET {maj}""", vals)
    r = _q("SELECT email::text FROM contacts WHERE id = %(c)s::uuid", {"c": d.get("contact_id")})
    if r:
        _etat(r[0][0])


# ── Reprise de l'existant DuckDB ──────────────────────────────────────────────
def _uuid_valide(v) -> bool:
    import uuid as _u
    try:
        _u.UUID(str(v))
        return True
    except Exception:  # noqa: BLE001
        return False


def copier_depuis_duckdb() -> dict:
    """Aligne PostgreSQL sur le pool DuckDB, une dernière fois. Idempotent.

    - contacts absents de PG → insérés (via create_in_pool, mêmes règles) ;
    - contact_sites : colonnes d'envoi / d'engagement reprises ; lignes manquantes créées ;
    - contact_enrichment : lignes et colonnes manquantes reprises ;
    - base repoussoir : toute adresse bloquée dans DuckDB et inconnue du journal y entre
      comme envoi de reprise (`meta.attribution = 'reprise-suppression-duckdb'`), pour que
      la fenêtre de 120 jours ne s'ouvre pour personne à la bascule.
    """
    import psycopg2
    import psycopg2.extras
    import contacts_pool_backend as cpb
    import acq_pg
    def _duck_frais():
        # Une connexion NEUVE par étape, mémoire élargie, un seul fil : le 07/10 la lecture
        # de l'historique par site a saturé les 1,8 Go alloués après celle des contacts.
        d = cpb._conn(read_only=True)
        for reglage in ("SET memory_limit = '3GB'", "SET threads = 1",
                        "SET preserve_insertion_order = false"):
            try:
                d.execute(reglage)
            except Exception:  # noqa: BLE001
                pass
        return d

    duck = _duck_frais()
    bilan = {}
    try:
        dsn = [l.split("=", 1)[1].strip() for l in (BASE_DIR / ".env").read_text().splitlines()
               if l.startswith("PG_DSN=")][0]
        pg = psycopg2.connect(dsn)
        cur = pg.cursor()

        # 1. Contacts manquants
        cur.execute("SELECT id::text FROM contacts")
        ids_pg = {r[0] for r in cur.fetchall()}
        cols = [d[0] for d in duck.execute("SELECT * FROM contacts LIMIT 0").description]
        manquants = [dict(zip(cols, r)) for r in duck.execute("SELECT * FROM contacts").fetchall()
                     if str(r[0]) not in ids_pg]
        n = 0
        for d in manquants:
            em = _norm(d.get("email"))
            if not em:
                continue
            cur.execute("SELECT 1 FROM contacts WHERE email = %s", (em,))
            if cur.fetchone():
                continue
            mn = d.get("mailnjoy_check")
            if isinstance(mn, str):
                try:
                    mn = json.loads(mn)
                except Exception:  # noqa: BLE001
                    mn = None
            sec = d.get("sectors")
            if isinstance(sec, str):
                try:
                    sec = json.loads(sec)
                except Exception:  # noqa: BLE001
                    sec = []
            cur.execute("""
                INSERT INTO contacts (id, email, prenom, nom, societe, tel, website, city,
                    dept_code, region_code, postal_code, sectors, primary_source, email_score,
                    email_validation_reasons, mailnjoy_check, mailnjoy_decision,
                    mailnjoy_checked_at, global_blacklisted, blacklist_reason, blacklisted_at,
                    job_title, civility, job_function, prenom_source, created_at, updated_at)
                VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::text[],%s,%s,%s::jsonb,%s::jsonb,
                        %s,%s::timestamptz,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,now()),COALESCE(%s,now()))
                ON CONFLICT DO NOTHING""",
                (str(d["id"]), em, d.get("prenom"), d.get("nom"), d.get("societe"), d.get("tel"),
                 d.get("website"), d.get("city"), d.get("dept_code"), d.get("region_code"),
                 d.get("postal_code"), [s for s in (sec or []) if s], d.get("primary_source"),
                 d.get("email_score"), acq_pg._j(d.get("email_validation_reasons")),
                 acq_pg._j(mn) if mn else None, (mn or {}).get("decision") if mn else None,
                 (mn or {}).get("checked_at") if mn else None,
                 bool(d.get("global_blacklisted")), d.get("blacklist_reason"),
                 d.get("blacklisted_at"), d.get("job_title"), d.get("civility"),
                 d.get("job_function"), d.get("prenom_source"), d.get("created_at"),
                 d.get("updated_at")))
            n += cur.rowcount
        pg.commit()
        bilan["contacts_ajoutes"] = n

        # 2. contact_sites
        duck.close()
        duck = _duck_frais()
        csh_cols = ("contact_id", "site_code", "account_id", "state", "source",
                    "added_to_site_at", "state_history", "last_action_at", "emelia_campaign_id",
                    "emelia_contact_id", "email_sent_at", "emelia_opened_at", "emelia_clicked_at",
                    "emelia_replied_at", "emelia_bounced_at", "emelia_unsubscribed_at",
                    "last_contacted_by_site_at", "notes", "last_opened_at", "last_clicked_at",
                    "last_open_channel", "last_click_channel")
        cur_d = duck.execute(f"SELECT {', '.join(csh_cols)} FROM contact_site_history")
        rows = []
        while True:
            paquet = cur_d.fetchmany(2000)
            if not paquet:
                break
            rows.extend(paquet)
        data = []
        ecartes = 0
        for r in rows:
            d = dict(zip(csh_cols, r))
            if not _uuid_valide(d.get("contact_id")):
                ecartes += 1          # lignes de test (« id-inexistant ») : sans objet
                continue
            d["state_history"] = acq_pg._j(d.get("state_history")) or "[]"
            data.append(tuple(d[c] for c in csh_cols))
        cur.execute("CREATE TEMP TABLE _csh (LIKE contact_sites INCLUDING DEFAULTS) ON COMMIT DROP")
        psycopg2.extras.execute_values(cur, """
            INSERT INTO _csh (id, contact_id, site_code, account_id, state, source, added_at,
                state_history, last_action_at, emelia_campaign_id, emelia_contact_id,
                email_sent_at, emelia_opened_at, emelia_clicked_at, emelia_replied_at,
                emelia_bounced_at, emelia_unsubscribed_at, last_contacted_by_site_at, notes,
                last_opened_at, last_clicked_at, last_open_channel, last_click_channel)
            VALUES %s""", data,
            template="(gen_random_uuid(), %s::uuid, %s, %s, COALESCE(%s,'cold_email'), %s, "
                     "COALESCE(%s, now()), %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                     "%s, %s, %s, %s, %s)", page_size=1000)
        cur.execute("""
            INSERT INTO contact_sites (id, contact_id, site_code, account_id, state, source,
                added_at, state_history, last_action_at)
            SELECT gen_random_uuid(), t.contact_id, t.site_code, t.account_id, t.state, t.source,
                   t.added_at, t.state_history, t.last_action_at
              FROM _csh t JOIN contacts c ON c.id = t.contact_id
            ON CONFLICT (contact_id, site_code) DO NOTHING""")
        bilan["sites_ajoutes"] = cur.rowcount
        cur.execute("""
            UPDATE contact_sites cs SET
                emelia_campaign_id = COALESCE(cs.emelia_campaign_id, t.emelia_campaign_id),
                emelia_contact_id = COALESCE(cs.emelia_contact_id, t.emelia_contact_id),
                email_sent_at = GREATEST(cs.email_sent_at, t.email_sent_at),
                emelia_opened_at = COALESCE(cs.emelia_opened_at, t.emelia_opened_at),
                emelia_clicked_at = COALESCE(cs.emelia_clicked_at, t.emelia_clicked_at),
                emelia_replied_at = COALESCE(cs.emelia_replied_at, t.emelia_replied_at),
                emelia_bounced_at = COALESCE(cs.emelia_bounced_at, t.emelia_bounced_at),
                emelia_unsubscribed_at = COALESCE(cs.emelia_unsubscribed_at, t.emelia_unsubscribed_at),
                last_contacted_by_site_at = GREATEST(cs.last_contacted_by_site_at,
                                                     t.last_contacted_by_site_at),
                last_opened_at = GREATEST(cs.last_opened_at, t.last_opened_at),
                last_clicked_at = GREATEST(cs.last_clicked_at, t.last_clicked_at),
                last_open_channel = COALESCE(t.last_open_channel, cs.last_open_channel),
                last_click_channel = COALESCE(t.last_click_channel, cs.last_click_channel),
                notes = COALESCE(cs.notes, t.notes)
              FROM _csh t
             WHERE cs.contact_id = t.contact_id AND cs.site_code = t.site_code""")
        bilan["sites_completes"] = cur.rowcount
        pg.commit()

        # 3. contact_enrichment
        duck.close()
        duck = _duck_frais()
        ecols = [d[0] for d in duck.execute("SELECT * FROM contact_enrichment LIMIT 0").description]
        garde = [c for c in _COLS_ENR if c in ecols]
        rows = duck.execute(f"SELECT {', '.join(garde)} FROM contact_enrichment").fetchall()
        data = []
        for r in rows:
            d = dict(zip(garde, r))
            if not _uuid_valide(d.get("contact_id")):
                continue
            if "raw" in d:
                d["raw"] = acq_pg._j(d["raw"])
            data.append(tuple(d[c] for c in garde))
        maj = ", ".join(f"{c} = COALESCE(contact_enrichment.{c}, EXCLUDED.{c})"
                        for c in garde if c != "contact_id")
        psycopg2.extras.execute_values(cur, f"""
            INSERT INTO contact_enrichment ({', '.join(garde)})
            SELECT v.* FROM (VALUES %s) AS v({', '.join(garde)})
            WHERE EXISTS (SELECT 1 FROM contacts c WHERE c.id = v.contact_id::uuid)
            ON CONFLICT (contact_id) DO UPDATE SET {maj}""", data,
            template="(" + ", ".join("%s::uuid" if c == "contact_id" else
                                     "%s::jsonb" if c == "raw" else
                                     "%s::timestamptz" if c == "enriched_at" else
                                     "%s::boolean" if c.startswith("est_") or c == "excluded" else
                                     "%s::double precision" if c in ("latitude", "longitude") else
                                     "%s::text" for c in garde) + ")",
            page_size=1000)
        bilan["enrichissements"] = len(data)
        pg.commit()

        # 4. Base repoussoir
        duck.close()
        duck = _duck_frais()
        sup = duck.execute("""SELECT email, last_sent_at, site_code FROM email_suppression
                              WHERE contactable = 0""").fetchall()
        cur.execute("SELECT email::text FROM v_suppression")
        connus = {r[0].lower() for r in cur.fetchall()}
        repris = [(s[0].lower(), s[1], s[2] or "lcr") for s in sup
                  if s[0] and s[0].lower() not in connus]
        for em, at, site in repris:
            cur.execute("""INSERT INTO email_events (occurred_at, email, contact_id, site_code,
                               channel, event_type, meta)
                           VALUES (%s, %s, (SELECT id FROM contacts WHERE email = %s), %s,
                                   'reprise', 'sent', %s)""",
                        (at, em, em, site,
                         json.dumps({"attribution": "reprise-suppression-duckdb"})))
        pg.commit()
        bilan["repoussoir_repris"] = len(repris)
        pg.close()
    finally:
        duck.close()

    # 5. États recalculés pour tout le monde, avec la règle PostgreSQL.
    _ecrire(f"""UPDATE contacts ct SET etat = {_etat_sql()}, etat_at = now()
                WHERE NOT ct.est_test AND ct.etat IS DISTINCT FROM {_etat_sql()}""")
    return bilan


def _etat_sql() -> str:
    import acq_pg
    return acq_pg.ETAT_PG


def etat() -> dict:
    return {"actif": actif(),
            "contacts": int(_q("SELECT count(*) FROM contacts")[0][0]),
            "contact_sites": int(_q("SELECT count(*) FROM contact_sites")[0][0]),
            "contact_enrichment": int(_q("SELECT count(*) FROM contact_enrichment")[0][0]),
            "par_etat": dict(_q("SELECT etat, count(*) FROM contacts GROUP BY 1"))}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "etat"
    if cmd == "schema":
        creer_schema(); print(json.dumps(etat(), default=str))
    elif cmd == "etats":
        # Réapplique la règle d'état (acq_pg.ETAT_PG) à toutes les fiches.
        _ecrire(f"""UPDATE contacts ct SET etat = {_etat_sql()}, etat_at = now()
                    WHERE NOT ct.est_test AND ct.etat IS DISTINCT FROM {_etat_sql()}""")
        print(json.dumps(etat(), default=str))
    elif cmd == "copier":
        print(json.dumps(copier_depuis_duckdb(), default=str))
        print(json.dumps(etat(), default=str))
    else:
        print(json.dumps(etat(), default=str))
