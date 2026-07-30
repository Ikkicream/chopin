#!/usr/bin/env python3
"""booking_backend.py — Prise de RDV publique par site (type Calendly/TidyCal).

Flux :
  - Page publique `/api/book/{site}` : le prospect choisit un MOTIF (démo, question,
    partenariat…), un JOUR puis un CRÉNEAU parmi ceux ouverts dans le back-office,
    saisit nom/email/téléphone → confirmation email + SMS (Sweego).
  - Back-office (authentifié) : configure les motifs, la disponibilité hebdo, la durée
    de créneau, l'expéditeur. Liste les RDV pris.

Tables (data/god_mode.duckdb) :
  booking_settings(site_code PK, config JSON, updated_at)
  bookings(id, site_code, reason_key, reason_label, slot_start, slot_minutes,
           name, email, phone, message, status, created_at)
"""
from __future__ import annotations

import html
import json
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"

_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Validation email stricte (RFC-friendly, sans être permissif). Bornée à 254 car (RFC 5321).
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _valid_email(e: str) -> bool:
    e = (e or "").strip()
    return bool(e) and len(e) <= 254 and _EMAIL_RE.match(e) is not None


def _conn(retries: int = 8, delay: float = 0.4):
    import time as _t
    for attempt in range(retries):
        try:
            return duckdb.connect(str(GOD_DB))
        except Exception as e:  # noqa: BLE001
            if "Conflicting lock" in str(e) and attempt < retries - 1:
                _t.sleep(delay)
                continue
            raise


_INIT = False


def _ensure_tables() -> None:
    global _INIT
    if _INIT:
        return
    c = _conn()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS booking_settings (
                site_code  VARCHAR PRIMARY KEY,
                config     VARCHAR,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id           VARCHAR PRIMARY KEY,
                site_code    VARCHAR,
                reason_key   VARCHAR,
                reason_label VARCHAR,
                slot_start   VARCHAR,   -- ISO local 'YYYY-MM-DDTHH:MM' (Europe/Paris)
                slot_minutes INTEGER,
                name         VARCHAR,
                email        VARCHAR,
                phone        VARCHAR,
                message      VARCHAR,
                status       VARCHAR DEFAULT 'confirmed',
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _INIT = True
    finally:
        c.close()


# ── Config par défaut ──────────────────────────────────────────────────────────
def _site_meta(site: str) -> dict:
    """Métadonnées du site (label, url, description, couleur) depuis sites_config."""
    try:
        import sites_config
        s = sites_config.get_site(site) or {}
        core = s.get("core") or {}
        desc = ((s.get("rag_context") or {}).get("business_description") or "").strip()
        return {
            "label": core.get("label") or site.upper(),
            "url": core.get("url") or "",
            "color": core.get("primary_color") or "#4f46e5",
            "description": desc,
        }
    except Exception:  # noqa: BLE001
        return {"label": site.upper(), "url": "", "color": "#4f46e5", "description": ""}


def _site_label(site: str) -> str:
    return _site_meta(site)["label"]


def _default_config(site: str) -> dict:
    meta = _site_meta(site)
    return {
        "timezone": "Europe/Paris",
        "slot_minutes": 30,
        "lead_days": 14,            # fenêtre de réservation (jours à l'avance)
        "brand_color": meta["color"],
        "from_name": meta["label"],
        "from_email": "info@leclientroi.com",   # domaine Sweego vérifié
        "logo_url": "",                          # logo affiché sur la page publique
        "hero_image_url": "",                    # image de fond derrière l'en-tête
        "website_url": meta["url"],              # lien + favicon « icône du site »
        "description": meta["description"],      # texte d'intro sur la page publique
        "sms_enabled": True,
        "reasons": [
            {"key": "demo",        "label": "Démo de l'outil",        "emoji": "🎬"},
            {"key": "question",    "label": "Question / Information",  "emoji": "💬"},
            {"key": "partenariat", "label": "Partenariat",            "emoji": "🤝"},
        ],
        # Disponibilité hebdo : listes de plages [début, fin] en HH:MM (heure locale).
        "availability": {
            "mon": [["09:00", "12:00"], ["14:00", "18:00"]],
            "tue": [["09:00", "12:00"], ["14:00", "18:00"]],
            "wed": [["09:00", "12:00"], ["14:00", "18:00"]],
            "thu": [["09:00", "12:00"], ["14:00", "18:00"]],
            "fri": [["09:00", "12:00"], ["14:00", "17:00"]],
            "sat": [],
            "sun": [],
        },
    }


def get_settings(site: str) -> dict:
    """Config du site (seed défaut + persistée si elle existe)."""
    _ensure_tables()
    c = _conn()
    try:
        row = c.execute("SELECT config FROM booking_settings WHERE site_code=?", [site]).fetchone()
    finally:
        c.close()
    cfg = _default_config(site)
    if row and row[0]:
        try:
            cfg.update(json.loads(row[0]))
        except Exception:  # noqa: BLE001
            pass
    return cfg


def update_settings(site: str, patch: dict) -> dict:
    """Merge + persiste la config. Retourne la config résultante."""
    _ensure_tables()
    cfg = get_settings(site)
    # Champs modifiables uniquement
    allowed = {"slot_minutes", "lead_days", "brand_color", "from_name", "from_email",
               "sms_enabled", "reasons", "availability", "timezone",
               "logo_url", "hero_image_url", "website_url", "description"}
    for k, v in (patch or {}).items():
        if k in allowed:
            cfg[k] = v
    payload = json.dumps(cfg, ensure_ascii=False)
    c = _conn()
    try:
        exists = c.execute("SELECT 1 FROM booking_settings WHERE site_code=?", [site]).fetchone()
        if exists:
            c.execute("UPDATE booking_settings SET config=?, updated_at=CURRENT_TIMESTAMP WHERE site_code=?",
                      [payload, site])
        else:
            c.execute("INSERT INTO booking_settings (site_code, config) VALUES (?, ?)", [site, payload])
    finally:
        c.close()
    return cfg


# ── Calcul des créneaux ──────────────────────────────────────────────────────────
def _tz(cfg: dict) -> ZoneInfo:
    try:
        return ZoneInfo(cfg.get("timezone") or "Europe/Paris")
    except Exception:  # noqa: BLE001
        return ZoneInfo("Europe/Paris")


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _booked_starts(site: str, day_iso: str) -> set[str]:
    _ensure_tables()
    c = _conn()
    try:
        rows = c.execute(
            "SELECT slot_start FROM bookings WHERE site_code=? AND slot_start LIKE ? AND status<>'cancelled'",
            [site, f"{day_iso}T%"],
        ).fetchall()
    finally:
        c.close()
    return {r[0] for r in rows}


def available_slots(site: str, day_iso: str, cfg: dict | None = None) -> list[dict]:
    """Créneaux libres pour un jour donné. Retourne [{start (ISO local), label 'HH:MM'}]."""
    cfg = cfg or get_settings(site)
    try:
        d = date.fromisoformat(day_iso)
    except Exception:  # noqa: BLE001
        return []
    wd = _WEEKDAYS[d.weekday()]
    ranges = (cfg.get("availability") or {}).get(wd) or []
    minutes = int(cfg.get("slot_minutes") or 30)
    tz = _tz(cfg)
    now = datetime.now(tz)
    booked = _booked_starts(site, day_iso)
    out: list[dict] = []
    for rng in ranges:
        try:
            start_t, end_t = _parse_hhmm(rng[0]), _parse_hhmm(rng[1])
        except Exception:  # noqa: BLE001
            continue
        cur = datetime.combine(d, start_t, tzinfo=tz)
        end_dt = datetime.combine(d, end_t, tzinfo=tz)
        step = timedelta(minutes=minutes)
        while cur + step <= end_dt + timedelta(seconds=1):
            iso = cur.strftime("%Y-%m-%dT%H:%M")
            if cur > now + timedelta(minutes=5) and iso not in booked:
                out.append({"start": iso, "label": cur.strftime("%H:%M")})
            cur += step
    return out


def available_days(site: str, cfg: dict | None = None) -> list[dict]:
    """Jours réservables sur la fenêtre lead_days (uniquement ceux avec >=1 créneau libre)."""
    cfg = cfg or get_settings(site)
    tz = _tz(cfg)
    today = datetime.now(tz).date()
    lead = int(cfg.get("lead_days") or 14)
    days = []
    for i in range(lead + 1):
        d = today + timedelta(days=i)
        slots = available_slots(site, d.isoformat(), cfg)
        if slots:
            days.append({"date": d.isoformat(), "slots_count": len(slots),
                         "weekday": _WEEKDAYS[d.weekday()]})
    return days


# ── Création d'un RDV ──────────────────────────────────────────────────────────
def create_booking(site: str, reason_key: str, slot_start: str, name: str,
                   email: str, phone: str = "", message: str = "") -> dict:
    """Valide motif + créneau (offert & libre) puis enregistre. {ok, booking|error}."""
    cfg = get_settings(site)
    reasons = {r["key"]: r for r in (cfg.get("reasons") or [])}
    if reason_key not in reasons:
        return {"ok": False, "error": "motif invalide"}
    # Bornage des entrées (anti-payload géant) avant toute validation/stockage.
    name = (name or "").strip()[:120]
    email = (email or "").strip().lower()[:254]
    # Téléphone : on ne garde que les caractères légitimes d'un numéro (anti-injection SMS).
    phone = re.sub(r"[^0-9+ ().\-]", "", (phone or "").strip())[:30]
    message = (message or "").strip()[:2000]
    if not name:
        return {"ok": False, "error": "nom requis"}
    if not _valid_email(email):
        return {"ok": False, "error": "email invalide"}
    day_iso = (slot_start or "")[:10]
    valid = {s["start"] for s in available_slots(site, day_iso, cfg)}
    if slot_start not in valid:
        return {"ok": False, "error": "créneau indisponible"}
    bid = str(uuid.uuid4())[:8]
    reason = reasons[reason_key]
    _ensure_tables()
    c = _conn()
    try:
        c.execute(
            "INSERT INTO bookings (id, site_code, reason_key, reason_label, slot_start, "
            "slot_minutes, name, email, phone, message, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?, 'confirmed')",
            [bid, site, reason_key, reason["label"], slot_start, int(cfg.get("slot_minutes") or 30),
             name, email, phone, message],
        )
    finally:
        c.close()
    return {"ok": True, "booking": {
        "id": bid, "site_code": site, "reason_key": reason_key, "reason_label": reason["label"],
        "slot_start": slot_start, "slot_minutes": int(cfg.get("slot_minutes") or 30),
        "name": name, "email": email, "phone": phone,
    }, "config": cfg}


def unread_count(site: str) -> int:
    """Nombre de RDV pas encore marqués 'répondu' (= la pastille)."""
    _ensure_tables()
    c = _conn()
    try:
        row = c.execute(
            "SELECT COUNT(*) FROM bookings WHERE site_code=? AND status NOT IN ('answered','cancelled')",
            [site],
        ).fetchone()
    finally:
        c.close()
    return int(row[0]) if row else 0


def set_status(site: str, bid: str, status: str) -> dict:
    """Change le statut d'un RDV. 'answered' = répondu au demandeur → retire la pastille."""
    if status not in ("confirmed", "answered", "cancelled"):
        return {"ok": False, "error": "statut invalide"}
    _ensure_tables()
    c = _conn()
    try:
        c.execute("UPDATE bookings SET status=? WHERE id=? AND site_code=?", [status, bid, site])
    finally:
        c.close()
    return {"ok": True, "id": bid, "status": status}


ARCHIVED_SQL = "status IN ('answered','cancelled')"
ACTIVE_SQL = "status NOT IN ('answered','cancelled')"


def list_bookings(site: str, limit: int = 25, offset: int = 0,
                  scope: str = "", search: str = "") -> dict:
    """Liste paginée des RDV d'un site.

    `scope`  : 'active' (à traiter) | 'archived' (répondus / annulés) | '' (tous).
    `search` : sous-chaîne sur l'email, insensible à la casse.

    Retourne {items, total, limit, offset, counts}. `total` porte sur le filtre courant
    (pas sur la page) et `counts` donne le volume par onglet — les deux honorent `search`,
    pour que la recherche montre aussi combien de résultats dorment dans l'autre onglet.
    """
    _ensure_tables()
    limit = max(1, min(int(limit or 25), 200))
    offset = max(0, int(offset or 0))

    where = ["site_code = ?"]
    params: list = [site]
    if search and search.strip():
        where.append("lower(email) LIKE ?")
        params.append(f"%{search.strip().lower()}%")
    base_sql = " AND ".join(where)

    scope_sql = {"active": ACTIVE_SQL, "archived": ARCHIVED_SQL}.get(scope, "")
    full_sql = f"{base_sql} AND {scope_sql}" if scope_sql else base_sql

    c = _conn()
    try:
        n_active = c.execute(
            f"SELECT COUNT(*) FROM bookings WHERE {base_sql} AND {ACTIVE_SQL}", params).fetchone()[0]
        n_archived = c.execute(
            f"SELECT COUNT(*) FROM bookings WHERE {base_sql} AND {ARCHIVED_SQL}", params).fetchone()[0]
        total = c.execute(
            f"SELECT COUNT(*) FROM bookings WHERE {full_sql}", params).fetchone()[0]
        rows = c.execute(
            "SELECT id, reason_label, slot_start, slot_minutes, name, email, phone, message, "
            f"status, created_at FROM bookings WHERE {full_sql} "
            "ORDER BY slot_start DESC LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
    finally:
        c.close()
    return {
        "items": [{"id": r[0], "reason_label": r[1], "slot_start": r[2], "slot_minutes": r[3],
                   "name": r[4], "email": r[5], "phone": r[6], "message": r[7],
                   "status": r[8], "created_at": str(r[9])} for r in rows],
        "total": int(total), "limit": limit, "offset": offset,
        "counts": {"active": int(n_active), "archived": int(n_archived)},
    }


# ── Confirmation (email + SMS) ─────────────────────────────────────────────────
def _fmt_slot_fr(slot_start: str, minutes: int) -> str:
    """'lundi 30 juin 2026 à 14:00 (30 min)' — formaté en français, sans dépendance locale."""
    try:
        dt = datetime.fromisoformat(slot_start)
    except Exception:  # noqa: BLE001
        return slot_start
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre"]
    return f"{jours[dt.weekday()]} {dt.day} {mois[dt.month]} {dt.year} à {dt.strftime('%H:%M')} ({minutes} min)"


def _safe_color(c: str) -> str:
    """N'autorise qu'une couleur hex (#rgb/#rrggbb/#rrggbbaa) — sinon fallback (anti-injection CSS)."""
    c = (c or "").strip()
    return c if re.match(r"^#[0-9A-Fa-f]{3,8}$", c) else "#4f46e5"


def _confirmation_html(booking: dict, cfg: dict) -> str:
    # Échappement HTML systématique des valeurs interpolées : `name` est une saisie
    # utilisateur (XSS/HTML-injection) ; `label`/`reason_label` viennent de la config.
    label = html.escape(cfg.get("from_name") or booking["site_code"].upper())
    name = html.escape(booking.get("name") or "")
    reason = html.escape(booking.get("reason_label") or "")
    color = _safe_color(cfg.get("brand_color"))
    when = html.escape(_fmt_slot_fr(booking["slot_start"], booking["slot_minutes"]))
    return f"""<!DOCTYPE html><html lang="fr"><body style="margin:0;background:#f3f4f6;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111827;">
<div style="max-width:520px;margin:0 auto;padding:24px;">
  <div style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.06);">
    <div style="background:{color};padding:28px 32px;color:#fff;">
      <div style="font-size:13px;opacity:.85;text-transform:uppercase;letter-spacing:.5px;">{label}</div>
      <div style="font-size:22px;font-weight:700;margin-top:6px;">Rendez-vous confirmé ✅</div>
    </div>
    <div style="padding:28px 32px;">
      <p style="margin:0 0 16px;font-size:15px;">Bonjour {name},</p>
      <p style="margin:0 0 20px;font-size:15px;line-height:1.5;">Votre rendez-vous (<strong>{reason}</strong>) est bien enregistré. Voici le récapitulatif :</p>
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;padding:18px 20px;font-size:15px;">
        <div style="margin-bottom:8px;">📅 <strong>{when}</strong></div>
        <div style="margin-bottom:8px;">🎯 {reason}</div>
        <div>🤝 Notre Directeur Commercial <strong>Roméo.C</strong> sera à ce rendez-vous et vous attend.</div>
      </div>
      <p style="margin:20px 0 0;font-size:14px;line-height:1.5;">Des questions avant le rendez-vous ? Vous pouvez contacter Roméo directement à <a href="mailto:romeo@leclientroi.com" style="color:{color};">romeo@leclientroi.com</a>.</p>
      <p style="margin:16px 0 0;font-size:13px;color:#6b7280;line-height:1.5;">Un imprévu ? Répondez simplement à cet email pour replanifier. À très vite !</p>
    </div>
  </div>
  <div style="text-align:center;color:#9ca3af;font-size:12px;margin-top:16px;">{label}</div>
</div></body></html>"""


def _confirmation_sms(booking: dict, cfg: dict) -> str:
    label = cfg.get("from_name") or booking["site_code"].upper()
    when = _fmt_slot_fr(booking["slot_start"], booking["slot_minutes"])
    return (f"{label} : votre RDV ({booking['reason_label']}) est confirme le {when}. "
            f"Romeo.C, notre Directeur Commercial, vous y attend. "
            f"Questions : romeo@leclientroi.com")


def send_confirmations(booking: dict, cfg: dict) -> dict:
    """Envoie email (Sweego transac) + SMS (best-effort). Retourne {email, sms}."""
    out = {"email": {"ok": False}, "sms": {"skipped": True}}
    try:
        import sweego_backend as sw
        subject = f"Confirmation de votre rendez-vous — {cfg.get('from_name') or booking['site_code'].upper()}"
        out["email"] = sw.send_transactional_email(
            subject=subject,
            html_str=_confirmation_html(booking, cfg),
            to_email=booking["email"],
            to_name=booking.get("name"),
            from_email=cfg.get("from_email"),
            from_name=cfg.get("from_name"),
            campaign_id=f"booking-{booking['site_code']}",
        )
    except Exception as e:  # noqa: BLE001
        out["email"] = {"ok": False, "error": str(e)}
    if cfg.get("sms_enabled") and (booking.get("phone") or "").strip():
        try:
            import sweego_backend as sw
            out["sms"] = sw.send_sms(
                to_phone=booking["phone"],
                text=_confirmation_sms(booking, cfg),
                from_name=cfg.get("from_name"),
                campaign_id=f"booking-{booking['site_code']}",
            )
        except Exception as e:  # noqa: BLE001
            out["sms"] = {"ok": False, "error": str(e)}
    return out
