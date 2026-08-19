#!/usr/bin/env python3
"""pg_migrate.py — Reprise DuckDB → PostgreSQL du référentiel Cheffer.

Idempotent : rejouable sans doublon (ON CONFLICT partout, journal vidé et reconstruit).
Ne MODIFIE rien côté DuckDB — lecture seule sur les sources.

Ordre imposé par les clés étrangères : contacts → contact_sites/enrichment → campaigns
→ email_events.

Sur le journal d'événements, deux décisions de source méritent d'être explicites :

  - Les `sent` viennent de `maildoso_sent` (une ligne par destinataire, avec la boîte
    expéditrice et la campagne). Les campagnes de masse Sweego ne journalisent pas par
    destinataire : elles sont donc absentes du journal, et c'est signalé en fin de reprise
    plutôt que comblé par une approximation.
  - Les `open`/`click` viennent de `contact_site_history` (pixel `/api/track/open`, tous
    canaux) et NON de `sweego_events`. Ce dernier ne couvre pas maildoso et il est dominé
    par le trafic des boîtes de test/warmup et les ouvertures par proxy anti-spam : l'utiliser
    donnait des taux d'ouverture à 15 000 %. Seuls ses rebonds et plaintes sont repris, et
    uniquement pour des adresses réellement prospectées.
"""
from __future__ import annotations

import json
import sys
import uuid as _uuid
from datetime import timezone
from pathlib import Path

import duckdb
import psycopg2
import psycopg2.extras

BASE_DIR = Path(__file__).resolve().parent.parent
POOL_DB = BASE_DIR / "data" / "contacts.duckdb"
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"


def dsn() -> str:
    for line in (BASE_DIR / ".env").read_text().splitlines():
        if line.startswith("PG_DSN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("PG_DSN absent de .env")


def _duck(path):
    """DuckDB met l'instance en cache par process : on ouvre en lecture-écriture d'abord,
    comme le reste du code, pour ne pas créer de conflit de configuration."""
    try:
        return duckdb.connect(str(path))
    except Exception:
        return duckdb.connect(str(path), read_only=True)


def _jarr(v) -> list:
    """Colonne JSON DuckDB → liste Python."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    try:
        out = json.loads(v)
        return out if isinstance(out, list) else [out]
    except Exception:
        return []


def _jobj(v) -> dict:
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    try:
        out = json.loads(v)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def _aware(ts):
    """Les horodatages DuckDB sont naïfs et en UTC ; PostgreSQL veut du timestamptz."""
    if ts is None:
        return None
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts


def migrer() -> dict:
    pool = _duck(POOL_DB)
    god = _duck(GOD_DB)
    pg = psycopg2.connect(dsn())
    pg.autocommit = False
    cur = pg.cursor()
    bilan: dict[str, int] = {}

    try:
        # ── contacts ────────────────────────────────────────────────────────
        rows = pool.execute("""
            SELECT id, email, prenom, nom, societe, tel, website, city, dept_code,
                   region_code, postal_code, sectors, primary_source, email_score,
                   email_validation_reasons, mailnjoy_check, global_blacklisted,
                   blacklist_reason, blacklisted_at, created_at, updated_at,
                   job_title, civility, job_function, logo_url, client_since
            FROM contacts WHERE email IS NOT NULL AND trim(email) <> ''
        """).fetchall()
        lot = []
        for r in rows:
            mn = _jobj(r[15])
            lot.append((
                r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10],
                _jarr(r[11]), r[12], r[13],
                json.dumps(_jarr(r[14])) if r[14] is not None else None,
                mn.get("decision"), mn.get("checked_at"),
                json.dumps(mn) if mn else None,
                bool(r[16]), r[17], _aware(r[18]), _aware(r[19]), _aware(r[20]),
                r[21], r[22], r[23], r[24], _aware(r[25]),
            ))
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO contacts (id, email, prenom, nom, societe, tel, website, city,
                dept_code, region_code, postal_code, sectors, primary_source, email_score,
                email_validation_reasons, mailnjoy_decision, mailnjoy_checked_at,
                mailnjoy_check, global_blacklisted, blacklist_reason, blacklisted_at,
                created_at, updated_at, job_title, civility, job_function, logo_url,
                client_since)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        """, lot, page_size=500)
        bilan["contacts"] = len(lot)

        # ── contact_sites (l'ÉTAT seul) ─────────────────────────────────────
        rows = pool.execute("""
            SELECT h.id, h.contact_id, h.site_code, h.account_id, h.state, h.source,
                   h.added_to_site_at, h.last_action_at, h.state_history, h.notes
            FROM contact_site_history h
            JOIN contacts c ON c.id = h.contact_id
            WHERE c.email IS NOT NULL AND trim(c.email) <> ''
        """).fetchall()
        lot = [(r[0], r[1], r[2], r[3], r[4] or "cold_email", r[5],
                _aware(r[6]), _aware(r[7]), json.dumps(_jarr(r[8])), r[9]) for r in rows]
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO contact_sites (id, contact_id, site_code, account_id, state,
                source, added_at, last_action_at, state_history, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (contact_id, site_code) DO NOTHING
        """, lot, page_size=500)
        bilan["contact_sites"] = len(lot)

        # ── enrichissement ──────────────────────────────────────────────────
        try:
            rows = pool.execute("""
                SELECT e.contact_id, e.excluded, e.raw FROM contact_enrichment e
                JOIN contacts c ON c.id = e.contact_id
            """).fetchall()
            lot = [(r[0], bool(r[1]), json.dumps(_jobj(r[2]))) for r in rows]
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO contact_enrichment (contact_id, excluded, raw)
                VALUES (%s,%s,%s) ON CONFLICT (contact_id) DO NOTHING
            """, lot, page_size=500)
            bilan["contact_enrichment"] = len(lot)
        except Exception as e:  # noqa: BLE001
            bilan["contact_enrichment"] = -1
            print(f"  enrichissement ignoré : {e}")

        # ── campagnes (id court DuckDB -> uuid, ancien id conservé) ─────────
        rows = god.execute("""
            SELECT id, site_code, name, channel, message_id, subject, sectors, target_size,
                   schedule_start, cadence, status, sent_count, last_dispatch_at,
                   last_dispatch_day, last_error, params, created_by, created_at
            FROM campaigns_unified
        """).fetchall()
        camp_ids: dict[str, str] = {}
        lot = []
        for r in rows:
            new_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"cheffer:campaign:{r[0]}"))
            camp_ids[r[0]] = new_id
            lot.append((new_id, r[1], r[2], r[3], r[4], r[5], _jarr(r[6]), r[7] or 0,
                        r[8], json.dumps(_jarr(r[9])), r[10], r[11] or 0,
                        _aware(r[12]), r[13], r[14], json.dumps(_jobj(r[15])),
                        r[16], _aware(r[17]), r[0]))
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO campaigns (id, site_code, name, channel, message_id, subject,
                sectors, target_size, schedule_start, cadence, status, sent_count,
                last_dispatch_at, last_dispatch_day, last_error, params, created_by,
                created_at, legacy_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (legacy_id) DO NOTHING
        """, lot, page_size=200)
        bilan["campaigns"] = len(lot)

        # ── boîtes d'envoi + warmup ─────────────────────────────────────────
        rows = god.execute("""SELECT email, site_code, sender_name, provider, provider_id,
                   domain, smtp_host, smtp_port, imap_host, imap_port, username,
                   password_ref, status, daily_cap, sent_today, last_reset, created_at
                   FROM mailboxes""").fetchall()
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO mailboxes (email, site_code, sender_name, provider, provider_id,
                domain, smtp_host, smtp_port, imap_host, imap_port, username, password_ref,
                status, daily_cap, sent_today, last_reset, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (email) DO NOTHING
        """, [tuple(r[:16]) + (_aware(r[16]),) for r in rows], page_size=100)
        bilan["mailboxes"] = len(rows)

        rows = god.execute("""SELECT mailbox, day, old_cap, new_cap, reason, sent_window,
                   err_window, created_at FROM maildoso_ramp_log""").fetchall()
        cur.execute("DELETE FROM mailbox_ramp_log")
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO mailbox_ramp_log (mailbox, day, old_cap, new_cap, reason,
                sent_window, err_window, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, [tuple(r[:7]) + (_aware(r[7]),) for r in rows], page_size=200)
        bilan["mailbox_ramp_log"] = len(rows)

        # ── segments ────────────────────────────────────────────────────────
        try:
            rows = god.execute("SELECT * FROM segments").fetchall()
            cols = [d[0] for d in god.description]
            lot = []
            for r in rows:
                d = dict(zip(cols, r))
                lot.append((str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"cheffer:segment:{d['id']}")),
                            d.get("site_code"), d.get("name"),
                            json.dumps(_jobj(d.get("rules"))), d.get("last_count"),
                            _aware(d.get("counted_at")), d.get("created_by"),
                            _aware(d.get("created_at")), _aware(d.get("updated_at")),
                            str(d["id"])))
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO segments (id, site_code, name, rules, last_count, counted_at,
                    created_by, created_at, updated_at, legacy_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (legacy_id) DO NOTHING
            """, lot, page_size=100)
            bilan["segments"] = len(lot)
        except Exception as e:  # noqa: BLE001
            bilan["segments"] = -1
            print(f"  segments ignorés : {e}")

        # ── LE JOURNAL — reconstruit intégralement à chaque passage ─────────
        cur.execute("DELETE FROM email_events")
        cur.execute("SELECT id, lower(email) FROM contacts")
        par_email = {e: i for i, e in cur.fetchall()}
        evenements = []

        # 1. Les envois : maildoso, une ligne par destinataire.
        for camp_str, site, mailbox, to_email, created, rfc in god.execute("""
                SELECT campaign_id, site_code, mailbox, lower(to_email), created_at, rfc_msgid
                FROM maildoso_sent WHERE status = 'sent'""").fetchall():
            court = None
            if camp_str:
                parts = camp_str.split("-")
                if len(parts) >= 3:
                    court = f"{parts[1]}-{parts[2]}"
            evenements.append((_aware(created), to_email, par_email.get(to_email),
                               site or "lcr", camp_ids.get(court), "maildoso", "sent",
                               None, mailbox, rfc, json.dumps({"source": "maildoso_sent"})))

        # 1 bis. Les envois que maildoso ne journalise PAS : Sweego et Emelia en masse ne
        #        fournissent qu'un compteur de campagne. Leur trace par destinataire n'existe
        #        que dans `last_contacted_by_site_at`. Sans cette reprise, deux adresses
        #        sortaient de la fenêtre de 120 jours et redevenaient contactables — un
        #        renvoi, exactement ce que la règle interdit. On n'ajoute l'événement que
        #        s'il n'est pas déjà couvert par un envoi maildoso, pour ne pas doublonner.
        dernier_maildoso: dict[str, object] = {}
        for e, t in god.execute("""SELECT lower(to_email), max(created_at) FROM maildoso_sent
                                   WHERE status='sent' GROUP BY 1""").fetchall():
            dernier_maildoso[e] = _aware(t)
        for email, site, contacte in pool.execute("""
                SELECT lower(c.email), h.site_code, h.last_contacted_by_site_at
                FROM contact_site_history h JOIN contacts c ON c.id = h.contact_id
                WHERE h.last_contacted_by_site_at IS NOT NULL""").fetchall():
            contacte = _aware(contacte)
            connu = dernier_maildoso.get(email)
            if connu is not None and abs((connu - contacte).total_seconds()) < 60:
                continue  # déjà couvert par le journal maildoso
            if connu is not None and connu >= contacte:
                continue
            evenements.append((contacte, email, par_email.get(email), site or "lcr",
                               None, "inconnu", "sent", None, None, None,
                               json.dumps({"source": "contact_site_history",
                                           "note": "canal sans journal par destinataire"})))

        # 2. Ouvertures et clics : le pool, alimenté par le pixel /api/track/open.
        for email, site, opened, clicked, ch_o, ch_c in pool.execute("""
                SELECT lower(c.email), h.site_code, h.last_opened_at, h.last_clicked_at,
                       h.last_open_channel, h.last_click_channel
                FROM contact_site_history h JOIN contacts c ON c.id = h.contact_id
                WHERE h.last_opened_at IS NOT NULL OR h.last_clicked_at IS NOT NULL
                """).fetchall():
            if opened:
                evenements.append((_aware(opened), email, par_email.get(email), site or "lcr",
                                   None, ch_o or "maildoso", "open", None, None, None,
                                   json.dumps({"source": "contact_site_history"})))
            if clicked:
                evenements.append((_aware(clicked), email, par_email.get(email), site or "lcr",
                                   None, ch_c or "maildoso", "click", None, None, None,
                                   json.dumps({"source": "contact_site_history"})))

        # 3. Rebonds, plaintes, désabonnements : Sweego, restreint aux adresses réellement
        #    prospectées — sinon les boîtes de test et de warmup polluent le journal.
        map_evt = {"hard_bounce": "bounce", "complaint": "complaint", "list_unsub": "unsub"}
        for evt, email, site, recu, camp_str in god.execute("""
                SELECT event_type, lower(email), site_code, received_at, campaign_id
                FROM sweego_events
                WHERE event_type IN ('hard_bounce','complaint','list_unsub')""").fetchall():
            if email not in par_email:
                continue
            evenements.append((_aware(recu), email, par_email.get(email), site or "lcr",
                               None, "sweego", map_evt[evt], None, None, None,
                               json.dumps({"source": "sweego_events"})))

        # 4. Emelia (volume marginal, mais le canal existe).
        map_em = {"SENT": "sent", "OPENED": "open", "CLICKED": "click",
                  "BOUNCED": "bounce", "UNSUBSCRIBED": "unsub", "REPLIED": "reply"}
        for evt, email, site, recu in god.execute("""
                SELECT event_type, lower(email), site_code, received_at
                FROM emelia_events WHERE email IS NOT NULL""").fetchall():
            t = map_em.get((evt or "").upper())
            if not t:
                continue
            evenements.append((_aware(recu), email, par_email.get(email), site or "lcr",
                               None, "emelia", t, None, None, None,
                               json.dumps({"source": "emelia_events"})))

        evenements = [e for e in evenements if e[0] is not None and e[1]]
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO email_events (occurred_at, email, contact_id, site_code, campaign_id,
                channel, event_type, url, mailbox, provider_msg_id, meta)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, evenements, page_size=1000)
        bilan["email_events"] = len(evenements)

        pg.commit()
    except Exception:
        pg.rollback()
        raise
    finally:
        cur.close()
        pg.close()
        pool.close()
        god.close()
    return bilan


if __name__ == "__main__":
    print("Reprise DuckDB -> PostgreSQL\n")
    b = migrer()
    for k, v in b.items():
        print(f"  {k:22s} {v if v >= 0 else 'ignoré'}")
    print("\nOK")
