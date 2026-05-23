#!/usr/bin/env python3
"""
workflow_emelia_push.py — Push d'un prospect qualifié vers une campagne Emelia.

Stratégie :
- 1 campagne Emelia par {site}-{sector} (donc 6 campagnes max par site, 12 au total).
- Le département est poussé en custom_field (`dept`) du contact pour permettre la segmentation
  côté Emelia via filtres natifs ou statistiques par dept.
- Création lazy : la campagne n'est créée la première fois qu'un prospect du secteur arrive.
- Anti-doublon strict : si `emelia_contact_id` non null sur le prospect, on ne pousse pas.
- Quota strict : 50 contacts/site/jour (table god_mode_settings.daily_quota, défaut 50).

API Emelia : https://api.emelia.io
"""

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

import duckdb

sys.path.insert(0, str(Path(__file__).parent))
from acquisition_backend import (
    find_by_email as acq_find,
    create as acq_create,
)

BASE_DIR = Path(__file__).parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"
EMELIA_URL = "https://api.emelia.io"

# Load .env
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip("\x27\""))


def _get_key(site: str) -> str | None:
    """Clé Emelia par site (LCR/MKD).

    Ordre de priorité (2026-05-22) :
      1. Table site_credentials (chiffrée AES) — source de vérité post-onboarding
      2. Env var EMELIA_API_KEY_<SITE> — legacy
      3. Env var EMELIA_API_KEY globale — fallback ultime
    """
    try:
        from site_credentials_backend import get_credential
        v = get_credential(site, "EMELIA_API_KEY")
        if v:
            return v.strip() or None
    except Exception:
        pass
    k = os.environ.get(f"EMELIA_API_KEY_{site.upper()}", "").strip()
    if k:
        return k
    k = os.environ.get("EMELIA_API_KEY", "").strip()
    return k or None


def _headers(api_key: str) -> dict:
    # Emelia REST utilise `Authorization: <key>` sans préfixe Bearer
    return {"Authorization": api_key, "Content-Type": "application/json"}


def _campaign_name(site: str, sector: str) -> str:
    return f"workflow-{site}-{sector}"


def list_campaigns(api_key: str) -> list[dict]:
    """Liste les campagnes Emelia du compte."""
    r = requests.get(f"{EMELIA_URL}/emails/campaigns", headers=_headers(api_key), timeout=15)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        return data.get("campaigns") or data.get("data") or []
    return data


def _camp_id(camp: dict) -> str | None:
    """Extrait l'id d'une campagne, gère plusieurs formats de réponse Emelia."""
    if not isinstance(camp, dict):
        return None
    return camp.get("_id") or camp.get("id") or (camp.get("campaign") or {}).get("_id")


def find_campaign_by_name(api_key: str, name: str) -> dict | None:
    for c in list_campaigns(api_key):
        if (c.get("name") or "").lower() == name.lower():
            return c
    return None




# ── Warmup ramp-up (cf. specs/warmup-plan.md) ─────────────────────────────────
def daily_warmup_quota(sender_email: str, today=None) -> int:
    """Retourne le quota journalier autorisé pour un sender, selon son plan de chauffe.
    Lit la table email_senders. Si daily_max_override est set, le retourne.
    Sinon applique le Plan A (conservateur Emelia) :
      J1-J3=10, J4-J7=20, J8-J14=35, J15-J21=50, J22-J28=75, J29+=100.
    """
    from datetime import date as _date
    today = today or _date.today()
    c = duckdb.connect(str(GOD_DB), read_only=True)
    try:
        row = c.execute(
            "SELECT warmup_start_date, daily_max_override, status FROM email_senders WHERE sender_email = ?",
            [sender_email],
        ).fetchone()
    finally:
        c.close()
    if not row:
        return 0  # sender inconnu = pas d'envoi
    start, override, status = row
    if status != "active":
        return 0
    if override is not None:
        return int(override)
    if not start:
        return 0
    days = (today - start).days + 1  # J1 = jour de début
    if days <= 3:   return 10
    if days <= 7:   return 20
    if days <= 14:  return 35
    if days <= 21:  return 50
    if days <= 28:  return 75
    return 100


def sender_email_for_site(site: str) -> str:
    """Renvoie l'email du sender actif pour le site (lecture DB)."""
    c = duckdb.connect(str(GOD_DB), read_only=True)
    try:
        row = c.execute(
            "SELECT sender_email FROM email_senders WHERE site_code = ? AND status = 'active' LIMIT 1",
            [site],
        ).fetchone()
    finally:
        c.close()
    return row[0] if row else ""


def emelia_sent_today_by_sender(sender_email: str) -> int:
    """Compte les events SENT du jour pour un sender (lit emelia_events).
    Note: site_code dans emelia_events est dérivé via name → on filtre via campaign_name préfixe.
    Pour faire plus simple : on filtre par site_code de la row email_senders."""
    c = duckdb.connect(str(GOD_DB), read_only=True)
    try:
        sender_row = c.execute("SELECT site_code FROM email_senders WHERE sender_email = ?", [sender_email]).fetchone()
        if not sender_row:
            return 0
        site_code = sender_row[0]
        from datetime import date as _date
        today = _date.today().isoformat()
        cnt = c.execute("""
            SELECT COUNT(*) FROM emelia_events
            WHERE event_type = 'SENT'
              AND site_code = ?
              AND CAST(received_at AS DATE) = ?
        """, [site_code, today]).fetchone()[0]
    finally:
        c.close()
    return int(cnt or 0)


def get_or_create_campaign(api_key: str, site: str, sector: str) -> dict:
    """Renvoie la campagne existante ou la crée. Renvoie {id, name, …}."""
    name = _campaign_name(site, sector)
    existing = find_campaign_by_name(api_key, name)
    if existing:
        return existing

    # Création
    r = requests.post(f"{EMELIA_URL}/emails/campaigns",
                      json={"name": name},
                      headers=_headers(api_key), timeout=20)
    r.raise_for_status()
    created = r.json()
    # Si l'API renvoie {"success": ..., "campaign": {...}}, on déballe
    if isinstance(created, dict) and "campaign" in created and isinstance(created["campaign"], dict):
        created = created["campaign"]

    # Settings par défaut : lun-ven 8h-18h Europe/Paris
    cid = _camp_id(created)
    if cid:
        try:
            requests.patch(
                f"{EMELIA_URL}/emails/campaigns/{cid}/settings",
                json={
                    "sendingDays": {
                        "monday": True, "tuesday": True, "wednesday": True,
                        "thursday": True, "friday": True,
                        "saturday": False, "sunday": False,
                    },
                    "sendingHours": {"start": "08:00", "end": "18:00"},
                    "timezone": "Europe/Paris",
                },
                headers=_headers(api_key), timeout=15,
            )
        except Exception as e:
            print(f"  [emelia] warn settings: {e}")

        # === Configurer steps (template du secteur) + START + register webhook ===
        try:
            from emelia_campaign_manager import get_default_steps
            steps = get_default_steps(sector)
            requests.patch(
                f"{EMELIA_URL}/emails/campaigns/{cid}/steps",
                json={"steps": steps},
                headers=_headers(api_key), timeout=20,
            )
        except Exception as e:
            print(f"  [emelia] warn steps: {e}")

        try:
            requests.post(
                f"{EMELIA_URL}/emails/campaigns/{cid}/start",
                headers=_headers(api_key), timeout=15,
            )
        except Exception as e:
            print(f"  [emelia] warn start: {e}")

        # Register webhook pour cette campagne précise (idempotent — Emelia gère le dedup)
        try:
            import os as _os
            WEBHOOK_URL = "https://api.cheffer.email/api/emelia/webhook?token=" + _os.environ.get("WEBHOOK_TOKEN_1", "")
            if _os.environ.get("WEBHOOK_TOKEN_1"):
                requests.post(f"{EMELIA_URL}/webhook",
                    json={
                        "hookUrl":    WEBHOOK_URL,
                        "campaignId": cid,
                        "events":     ["SENT", "OPENED", "CLICKED", "REPLIED", "BOUNCED", "UNSUBSCRIBED"],
                        "type":       "email",
                    },
                    headers=_headers(api_key), timeout=15)
        except Exception as e:
            print(f"  [emelia] warn webhook register: {e}")

    return created


def already_pushed_today(site: str, conn: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Compte de contacts poussés vers Emelia aujourd'hui pour ce site.
    Réutilise la connexion fournie si possible (évite l'erreur DuckDB
    "Can't open with different configuration"), sinon en ouvre une r/w."""
    close = conn is None
    if close:
        conn = duckdb.connect(str(GOD_DB))
    try:
        row = conn.execute("""
            SELECT count(*) FROM scrappe
            WHERE site_code = ?
              AND emelia_contact_id IS NOT NULL
              AND CAST(contacted_at AS DATE) = CAST(? AS DATE)
        """, [site, date.today().isoformat()]).fetchone()
    finally:
        if close:
            conn.close()
    return row[0] if row else 0


def push_prospect(site: str, prospect_id: str, daily_limit: int = 50) -> dict:
    """Pousse un prospect vers Emelia. Renvoie {pushed, reason, campaign_id, contact_id}.

    Refuse si :
      - prospect déjà poussé (emelia_contact_id non null)
      - quota jour atteint (daily_limit, défaut 50)
      - clé Emelia manquante
      - email invalide
    """
    api_key = _get_key(site)
    if not api_key:
        return {"pushed": False, "reason": f"no_emelia_key_{site}"}

    c = duckdb.connect(str(GOD_DB))
    try:
        row = c.execute("""
            SELECT id, company_name, contact_name, email, sector, city, dept_code, region_code,
                   website, emelia_contact_id, phone
            FROM scrappe WHERE id=? AND site_code=?
        """, [prospect_id, site]).fetchone()
        if not row:
            return {"pushed": False, "reason": "prospect_not_found"}
        (pid, company, contact_name, email, sector, city, dept, region, website, already_id, phone) = row
        if already_id:
            return {"pushed": False, "reason": "already_pushed", "contact_id": already_id}
        if not email or "@" not in email:
            return {"pushed": False, "reason": "invalid_email"}

        # Anti-doublon : refuser de pusher si le contact est blacklisté dans acquisition_contacts
        existing_acq = acq_find(site, email)
        if existing_acq and existing_acq.get("state") == "blacklisted":
            return {"pushed": False, "reason": "blacklisted"}

        # Quota check (réutilise la connexion ouverte pour éviter conflit DuckDB)
        if already_pushed_today(site, conn=c) >= daily_limit:
            return {"pushed": False, "reason": f"daily_limit_{daily_limit}_reached"}

        # === Warmup ramp-up check (cf. specs/warmup-plan.md) ===
        # Bloque le push si on dépasse le quota journalier de chauffe du sender.
        sender = sender_email_for_site(site)
        if sender:
            warmup_quota = daily_warmup_quota(sender)
            sent_today = emelia_sent_today_by_sender(sender)
            if warmup_quota > 0 and sent_today >= warmup_quota:
                return {"pushed": False,
                        "reason": f"warmup_quota_reached_{sent_today}/{warmup_quota}_sender={sender}"}

        # Get or create campaign
        try:
            camp = get_or_create_campaign(api_key, site, sector)
        except Exception as e:
            return {"pushed": False, "reason": f"campaign_error: {e}"}

        cid = _camp_id(camp)
        if not cid:
            return {"pushed": False, "reason": "no_campaign_id"}

        # Build contact
        first_name, last_name = "", ""
        if contact_name:
            parts = contact_name.split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""
        contact = {
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "field1": company or "",
            "field2": city or "",
            "field3": dept or "",
            "field4": website or "",
        }
        r = requests.post(f"{EMELIA_URL}/emails/campaign/contacts",
                          json={"id": cid, "contact": contact},
                          headers=_headers(api_key), timeout=15)
        if r.status_code not in (200, 201):
            return {"pushed": False, "reason": f"emelia_http_{r.status_code}: {r.text[:120]}"}

        contact_id = ""
        try:
            data = r.json()
            contact_id = data.get("_id") or data.get("id") or data.get("contactId") or ""
        except Exception:
            pass

        # Mark in scrappe
        now = datetime.now(timezone.utc)
        c.execute("""
            UPDATE scrappe
            SET emelia_segment_id = ?, emelia_contact_id = ?, contacted_at = ?, status = 'pushed_emelia'
            WHERE id=? AND site_code=?
        """, [cid, contact_id or "pushed", now, pid, site])

        # Crée (ou enrichit) le contact dans acquisition_contacts en state=cold_email
        prenom, nom = "", ""
        if contact_name:
            parts = contact_name.split(" ", 1)
            prenom = parts[0]
            nom = parts[1] if len(parts) > 1 else ""

        acq_payload = {
            "email":              email,
            "prenom":             prenom,
            "nom":                nom,
            "societe":            company or "",
            "tel":                phone or "",
            "notes":              f"workflow scrape city={city} dept={dept} website={website or ''}",
            "state":              "cold_email",
            "source":             f"workflow:{sector}",
            "sector":             sector,
            "dept_code":          dept,
            "region_code":        region,
            "email_sent_at":      now.isoformat(),
            "emelia_campaign_id": cid,
            "emelia_contact_id":  contact_id or "pushed",
        }
        acq_id = ""
        try:
            existing = acq_find(site, email)
            if existing:
                # Le contact existait déjà : on enrichit avec les infos Emelia + secteur/géo
                acq_id = existing["id"]
                acq_c = duckdb.connect(str(BASE_DIR / "data" / "crm" / f"{site}.duckdb"))
                try:
                    acq_c.execute("""
                        UPDATE acquisition_contacts
                        SET sector = COALESCE(?, sector),
                            dept_code = COALESCE(?, dept_code),
                            region_code = COALESCE(?, region_code),
                            email_sent_at = COALESCE(email_sent_at, ?),
                            emelia_campaign_id = COALESCE(emelia_campaign_id, ?),
                            emelia_contact_id = COALESCE(emelia_contact_id, ?),
                            updated_at = ?,
                            last_action_at = ?
                        WHERE id = ?
                    """, [sector, dept, region, now.isoformat(), cid, contact_id or "pushed",
                          now.isoformat(), now.isoformat(), acq_id])
                finally:
                    acq_c.close()
            else:
                res = acq_create(site, acq_payload, by="workflow_runner")

            # DUAL-WRITE pool 2026-05-22 : pousser dans contacts.duckdb
            try:
                import contacts_pool_backend as _cpb
                _pool_cid = _cpb.create_in_pool({
                    "email":      email,
                    "prenom":     prenom,
                    "nom":        nom,
                    "societe":    company,
                    "tel":        phone,
                    "website":    website,
                    "city":       city,
                    "dept_code":  dept,
                    "sectors":    [sector] if sector else None,
                }, primary_source="serper")
                if _pool_cid:
                    _cpb.upsert_site_history(_pool_cid, site,
                        state="cold_email",
                        source="serper",
                        by="workflow_runner")
                    _cpb.mark_pushed_to_emelia(_pool_cid, site, cid, contact_id or "pushed")
            except Exception as _pool_err:
                print(f"  [emelia push][pool dual-write] {_pool_err}")
                acq_id = res.get("id", "")
        except Exception as e:
            print(f"  [acquisition_contacts] warn upsert: {e}")

        return {
            "pushed": True,
            "campaign_id": cid,
            "campaign_name": _campaign_name(site, sector),
            "contact_id": contact_id or "pushed",
            "acquisition_id": acq_id,
        }
    finally:
        c.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: workflow_emelia_push.py <site> <prospect_id>")
        sys.exit(1)
    print(push_prospect(sys.argv[1], sys.argv[2]))
