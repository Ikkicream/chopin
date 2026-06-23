"""
Mass campaigns via Sweego (https://api.sweego.io) — canal séparé d'Emelia (cold email).

- Auth : header `Api-Key` (clé dans .env : SWEEGO_API_KEY, domaine SWEEGO_DOMAIN).
- Envoi : POST /send, provider="email", campaign-type="market"|"transac".
  Pour une newsletter sans perso on retire les {{tokens}} (clean_html_for_sweego).
  Pour un envoi personnalisé, passer les champs extra dans chaque recipient object.
- Domaines autorisés (vérifiés) : leclientroi.com, news.leclientroi.email.
- Désinscription : gérée nativement par Sweego (header List-Unsubscribe 1-clic).
- Stats : POST /stats/msp {channel:"email"} → délivrabilité par MSP (gmail/microsoft/yahoo_eu…).
"""
from __future__ import annotations

import html as _html
import re
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"
SWEEGO_URL = "https://api.sweego.io"


def _env() -> dict:
    e = {}
    f = BASE_DIR / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("SWEEGO_") and "=" in line:
                k, v = line.split("=", 1)
                e[k.strip()] = v.strip()
    return e


def _headers() -> dict:
    return {"Api-Key": _env().get("SWEEGO_API_KEY", ""),
            "Content-Type": "application/json", "Accept": "application/json"}


def _from() -> dict:
    dom = _env().get("SWEEGO_DOMAIN", "news.leclientroi.email")
    return {"email": "news@" + dom, "name": "Le Client ROI"}


# ── Préparation du HTML ─────────────────────────────────────────────────────────
def clean_html_for_sweego(html_str: str) -> str:
    """Retire les liens/variables {{...}} non substituables (désinscription gérée par le header Sweego)."""
    s = html_str or ""
    s = re.sub(r"<a\b[^>]*\{\{[^}]*\}\}[^>]*>.*?</a>", "", s, flags=re.I | re.S)  # ancre avec token
    s = re.sub(r"\{\{[^}]*\}\}", "", s)  # tokens résiduels
    return s


def html_to_text(html_str: str) -> str:
    s = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", html_str or "", flags=re.I | re.S)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p\s*>", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = _html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s or "(voir version HTML)"


# ── Envoi ───────────────────────────────────────────────────────────────────────
def send_campaign(campaign_id: str, subject: str, html_str: str,
                  recipients: list[str], dry_run: bool = False) -> dict:
    """Envoie une mass campaign. `recipients` = liste d'emails. dry_run=True -> validation sans envoi."""
    recipients = [e for e in (recipients or []) if e and "@" in e]
    if not recipients:
        return {"ok": False, "error": "aucun destinataire valide"}
    if not subject or not subject.strip():
        return {"ok": False, "error": "sujet requis"}
    try:
        from utm_tagging import tag_links
        html_str = tag_links(html_str, "sweego", "email", campaign_id or "lcr-mass")
    except Exception:
        pass
    body = {
        "provider": "email",
        "campaign-type": "market",
        "campaign-id": campaign_id or "lcr-mass",
        "subject": subject,
        "from": _from(),
        "recipients": [{"email": e} for e in recipients],
        "message-html": clean_html_for_sweego(html_str),
        "message-txt": html_to_text(html_str),
        "dry-run": bool(dry_run),
    }
    try:
        r = requests.post(SWEEGO_URL + "/send", headers=_headers(), json=body, timeout=45)
        if r.status_code == 200:
            d = r.json()
            return {"ok": True, "transaction_id": d.get("transaction_id"),
                    "sent": len(recipients), "dry_run": dry_run}
        return {"ok": False, "error": f"sweego {r.status_code}: {r.text[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# ── Stats ─────────────────────────────────────────────────────────────────────
_ENGAGE_FIELDS = ["sent", "accepted", "bounced", "hardbounce", "softbounce", "complaints",
                  "rejected", "undelivered", "list_unsubscribe", "nb_openers", "nb_openings",
                  "nb_human_openers", "nb_human_openings", "nb_clickers", "nb_clicks"]


def engagement_stats(date_start: str | None = None, date_end: str | None = None) -> dict:
    """POST /stats {channel:email} -> ouvertures/clics agrégés (+ détail par jour/domaine)."""
    payload = {"channel": "email"}
    if date_start:
        payload["start_date"] = date_start
    if date_end:
        payload["end_date"] = date_end
    try:
        r = requests.post(SWEEGO_URL + "/stats", headers=_headers(), json=payload, timeout=25)
        rows = r.json().get("result", []) if r.status_code == 200 else []
    except Exception:
        rows = []
    agg = {k: sum(x.get(k, 0) for x in rows) for k in _ENGAGE_FIELDS}
    # taux dérivés
    sent = agg["sent"] or 0
    agg["open_rate"] = round(agg["nb_human_openers"] / sent * 100, 1) if sent else 0
    agg["click_rate"] = round(agg["nb_clickers"] / sent * 100, 1) if sent else 0
    return {"global": agg, "by_day": rows}


def msp_stats() -> dict:
    """POST /stats/msp -> délivrabilité par MSP (gmail/microsoft/yahoo_eu/default…)."""
    try:
        r = requests.post(SWEEGO_URL + "/stats/msp", headers=_headers(), json={}, timeout=25)
        d = r.json() if r.status_code == 200 else {}
    except Exception:
        d = {}
    return {"msps": d.get("msps", []), "result": d.get("result", [])}


# ── Suivi local des campagnes Sweego ────────────────────────────────────────────
def _conn():
    return duckdb.connect(str(GOD_DB))


def _ensure_table():
    c = _conn()
    try:
        c.execute(
            """CREATE TABLE IF NOT EXISTS mass_campaigns (
                id               VARCHAR,
                site_code        VARCHAR,
                name             VARCHAR,
                campaign_id      VARCHAR,
                subject          VARCHAR,
                sector           VARCHAR,
                message_id       VARCHAR,
                recipients_count INTEGER,
                transaction_id   VARCHAR,
                status           VARCHAR,
                created_at       TIMESTAMP,
                created_by       VARCHAR,
                PRIMARY KEY (id)
            )"""
        )
    finally:
        c.close()


def record_campaign(site, name, campaign_id, subject, sector, message_id,
                    count, transaction_id, by="ui") -> str:
    _ensure_table()
    rid = str(_uuid.uuid4())[:8]
    c = _conn()
    try:
        c.execute("INSERT INTO mass_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  [rid, site, name, campaign_id, subject, sector, message_id,
                   count, transaction_id, "sent", datetime.now(timezone.utc), by])
    finally:
        c.close()
    return rid


def list_campaigns(site) -> list[dict]:
    _ensure_table()
    c = _conn()
    try:
        rows = c.execute(
            "SELECT id, name, campaign_id, subject, sector, recipients_count, transaction_id, status, created_at "
            "FROM mass_campaigns WHERE site_code=? ORDER BY created_at DESC", [site]
        ).fetchall()
    finally:
        c.close()
    return [{"id": r[0], "name": r[1], "campaign_id": r[2], "subject": r[3], "sector": r[4],
             "recipients_count": r[5], "transaction_id": r[6], "status": r[7],
             "created_at": str(r[8]), "provider": "sweego"} for r in rows]


if __name__ == "__main__":
    # dry-run de validation (aucun envoi)
    res = send_campaign("dryrun-test", "Dry run", "<p>Bonjour <a href='{{UNSUBSCRIBE_LINK}}'>désinscription</a> {{firstName}}</p><p>Visite <a href='https://leclientroi.com'>le site</a></p>",
                        ["afchain.camille@gmail.com"], dry_run=True)
    print("dry-run:", res)
    print("clean:", clean_html_for_sweego("<p>x <a href='{{UNSUBSCRIBE_LINK}}'>désinscription</a> {{firstName}}</p>"))
