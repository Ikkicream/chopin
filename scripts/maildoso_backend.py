"""
Cold email maison via Maildoso — canal `maildoso` (3e connecteur, avec Emelia et Sweego).

- ⚠️ L'API REST Maildoso (https://api.maildoso.com, header `Authorization: Bearer <PAT>`)
  ne fait PAS d'envoi : elle gère l'infra (domaines, boîtes, warmup, stats).
  L'ENVOI se fait en SMTP direct : smtp.maildoso.com:587 (STARTTLS), login = email complet.
- Secrets dans .env : MAILDOSO_API_TOKEN, MAILDOSO_SMTP_PASSWORD (commun aux 4 boîtes).
- Boîtes : table `mailboxes` (god_mode.duckdb), rotation + cap journalier par boîte.
  Domaine d'envoi : leclient-roi.com (avec tiret — distinct de leclientroi.com Emelia/Sweego).
  Réponses agrégées sur leclientroi@maildoso.email (forwarding) + IMAP imap.horus.maildoso.com:993.
- Doc complète : .claude/skills/maildoso/SKILL.md + routeur_doc/cold-email-engine.md.

CLI : python3 scripts/maildoso_backend.py verify|sync|mailboxes|test <email>
"""
from __future__ import annotations

import os
import random
import smtplib
import time
import uuid as _uuid
from collections.abc import Callable
from datetime import date as _date, datetime, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

import duckdb
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"
API_URL = "https://api.maildoso.com"
SMTP_HOST = "smtp.maildoso.com"
SMTP_PORT = 587
IMAP_HOST = "imap.horus.maildoso.com"
IMAP_PORT = 993
SITE_DEFAULT = "lcr"
DAILY_CAP_PER_MAILBOX = 25   # prudent : domaine warmé 2 semaines seulement (ramp-up cf. cold-email-engine.md)


def _env() -> dict:
    e = {}
    f = BASE_DIR / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MAILDOSO_") and "=" in line:
                k, v = line.split("=", 1)
                e[k.strip()] = v.strip()
    return e


def _headers() -> dict:
    return {"Authorization": "Bearer " + _env().get("MAILDOSO_API_TOKEN", ""),
            "Accept": "application/json"}


# ── API infra (pas d'envoi ici) ─────────────────────────────────────────────────
def verify_connection() -> dict:
    """GET /v1/user/me — teste le token. {ok, user|error}."""
    try:
        r = requests.get(API_URL + "/v1/user/me", headers=_headers(), timeout=20)
        if r.status_code == 200:
            return {"ok": True, "user": r.json()}
        return {"ok": False, "error": f"maildoso {r.status_code}: {r.text[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def api_accounts() -> list[dict]:
    """GET /v1/user/accounts-lookup — boîtes du compte (avec creds)."""
    r = requests.get(API_URL + "/v1/user/accounts-lookup", headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json().get("items", [])


def api_stats() -> dict:
    r = requests.get(API_URL + "/v1/user/stats", headers=_headers(), timeout=20)
    return r.json() if r.status_code == 200 else {}


# ── Table mailboxes ──────────────────────────────────────────────────────────────
def _conn():
    return duckdb.connect(str(GOD_DB))


def _ensure_tables():
    c = _conn()
    try:
        c.execute(
            """CREATE TABLE IF NOT EXISTS mailboxes (
                email        VARCHAR,
                site_code    VARCHAR,
                sender_name  VARCHAR,
                provider     VARCHAR,     -- 'maildoso'
                provider_id  VARCHAR,     -- account_id API Maildoso
                domain       VARCHAR,
                smtp_host    VARCHAR,
                smtp_port    INTEGER,
                imap_host    VARCHAR,
                imap_port    INTEGER,
                username     VARCHAR,
                password_ref VARCHAR,     -- clé .env, jamais le mdp en clair
                status       VARCHAR,     -- warming|active|paused
                daily_cap    INTEGER,
                sent_today   INTEGER,
                last_reset   DATE,
                created_at   TIMESTAMP,
                PRIMARY KEY (email)
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS maildoso_sent (
                id          VARCHAR,
                site_code   VARCHAR,
                campaign_id VARCHAR,
                mailbox     VARCHAR,
                to_email    VARCHAR,
                subject     VARCHAR,
                rfc_msgid   VARCHAR,
                status      VARCHAR,      -- sent|error
                error       VARCHAR,
                created_at  TIMESTAMP,
                PRIMARY KEY (id)
            )"""
        )
    finally:
        c.close()


def sync_mailboxes(site: str = SITE_DEFAULT) -> dict:
    """Upsert les boîtes depuis l'API Maildoso (statut API active → status local 'active')."""
    _ensure_tables()
    items = api_accounts()
    c = _conn()
    n = 0
    try:
        for a in items:
            email = a.get("email_account", "")
            if not email:
                continue
            name = f"{a.get('first_name', '')} {a.get('last_name', '')}".strip() or email
            status = "active" if a.get("is_active") and a.get("status") == "active" else "paused"
            exists = c.execute("SELECT status FROM mailboxes WHERE email=?", [email]).fetchone()
            if exists:
                c.execute("UPDATE mailboxes SET sender_name=?, provider_id=?, status=? WHERE email=?",
                          [name, str(a.get("id", "")), status, email])
            else:
                c.execute("INSERT INTO mailboxes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          [email, site, name, "maildoso", str(a.get("id", "")),
                           email.split("@", 1)[-1], SMTP_HOST, SMTP_PORT,
                           a.get("imap", {}).get("imap_host", IMAP_HOST),
                           a.get("imap", {}).get("port", IMAP_PORT),
                           email, "MAILDOSO_SMTP_PASSWORD", status,
                           DAILY_CAP_PER_MAILBOX, 0, None, datetime.now(timezone.utc)])
            n += 1
    finally:
        c.close()
    return {"ok": True, "synced": n}


def list_mailboxes(site: str = SITE_DEFAULT) -> list[dict]:
    _ensure_tables()
    c = _conn()
    try:
        rows = c.execute(
            "SELECT email, sender_name, status, daily_cap, sent_today, last_reset "
            "FROM mailboxes WHERE site_code=? AND provider='maildoso' ORDER BY email", [site]).fetchall()
    finally:
        c.close()
    return [{"email": r[0], "sender_name": r[1], "status": r[2], "daily_cap": r[3],
             "sent_today": r[4], "last_reset": str(r[5]) if r[5] else None} for r in rows]


def _reset_counters_if_new_day(c, today: _date):
    c.execute("UPDATE mailboxes SET sent_today=0, last_reset=? "
              "WHERE provider='maildoso' AND (last_reset IS NULL OR last_reset < ?)", [today, today])


def _pick_mailbox(site: str, today: _date) -> dict | None:
    """Boîte active la moins sollicitée aujourd'hui, sous son cap. None si tout est plein."""
    c = _conn()
    try:
        _reset_counters_if_new_day(c, today)
        r = c.execute(
            "SELECT email, sender_name, smtp_host, smtp_port, username, password_ref "
            "FROM mailboxes WHERE site_code=? AND provider='maildoso' AND status='active' "
            "AND sent_today < daily_cap ORDER BY sent_today ASC, random() LIMIT 1", [site]).fetchone()
    finally:
        c.close()
    if not r:
        return None
    return {"email": r[0], "sender_name": r[1], "smtp_host": r[2], "smtp_port": r[3],
            "username": r[4], "password_ref": r[5]}


def _increment_sent(email: str):
    c = _conn()
    try:
        c.execute("UPDATE mailboxes SET sent_today=sent_today+1 WHERE email=?", [email])
    finally:
        c.close()


def stats(site: str = SITE_DEFAULT) -> dict:
    """Compteurs d'envoi Maildoso pour un site (table maildoso_sent).
    Maildoso = SMTP : pas de tracking d'ouverture/clic natif → seuls sent/errors sont connus."""
    _ensure_tables()
    c = _conn()
    try:
        row = c.execute(
            "SELECT COUNT(*) FILTER (WHERE status='sent'), COUNT(*) FILTER (WHERE status='error') "
            "FROM maildoso_sent WHERE site_code=?", [site]).fetchone()
    finally:
        c.close()
    return {"sent": int(row[0] or 0), "errors": int(row[1] or 0)}


def remaining_quota_today(site: str = SITE_DEFAULT) -> int:
    _ensure_tables()
    c = _conn()
    try:
        _reset_counters_if_new_day(c, _date.today())
        r = c.execute("SELECT COALESCE(SUM(daily_cap - sent_today), 0) FROM mailboxes "
                      "WHERE site_code=? AND provider='maildoso' AND status='active'", [site]).fetchone()
    finally:
        c.close()
    return int(r[0] or 0)


def _record_sent(site, campaign_id, mailbox, to_email, subject, rfc_msgid, status, error=None):
    c = _conn()
    try:
        c.execute("INSERT INTO maildoso_sent VALUES (?,?,?,?,?,?,?,?,?,?)",
                  [str(_uuid.uuid4())[:8], site, campaign_id or "", mailbox, to_email,
                   subject, rfc_msgid or "", status, error, datetime.now(timezone.utc)])
    finally:
        c.close()


def already_sent_emails(campaign_id: str) -> set[str]:
    """Destinataires déjà servis pour ce campaign_id (ligne 'sent' dans maildoso_sent).

    Sert de garde de reprise : `maildoso_sent` est écrit juste après chaque SMTP réussi,
    c'est donc la seule trace fiable quand le process meurt au milieu d'un lot — les
    compteurs de campagne et le marquage des contacts, eux, n'étaient historiquement
    posés qu'à la toute fin du lot. Sans cette garde, un redémarrage en cours d'envoi
    repioche les contacts déjà contactés et leur renvoie le même email."""
    if not campaign_id:
        return set()
    c = _conn()
    try:
        rows = c.execute("SELECT DISTINCT to_email FROM maildoso_sent "
                         "WHERE campaign_id = ? AND status = 'sent'", [campaign_id]).fetchall()
    finally:
        c.close()
    return {r[0] for r in rows if r[0]}


# ── Envoi SMTP ───────────────────────────────────────────────────────────────────
def _split_name(full: str) -> tuple[str, str]:
    parts = (full or "").split()
    return (parts[0] if parts else "", " ".join(parts[1:]) if len(parts) > 1 else "")


def _apply_tokens(s: str, contact: dict | None, mb: dict) -> str:
    """Remplace les variables {{...}} des templates par les données du contact / de la boîte.
    Nettoie les salutations vides (« Bonjour , » → « Bonjour, ») quand le prénom manque."""
    if not s:
        return s
    c = contact or {}
    exp_first, exp_last = _split_name(mb.get("sender_name", ""))
    repl = {
        "prenom": c.get("prenom") or "", "firstname": c.get("prenom") or "", "firstName": c.get("prenom") or "",
        "nom": c.get("nom") or "", "lastname": c.get("nom") or "", "lastName": c.get("nom") or "",
        "entreprise": c.get("societe") or c.get("entreprise") or "", "societe": c.get("societe") or "",
        "company": c.get("societe") or "",
        "ville": c.get("city") or c.get("ville") or "", "city": c.get("city") or "",
        "expediteur_prenom": exp_first, "expediteur_nom": exp_last,
    }
    import re as _re
    unsub = f"mailto:{mb['email']}?subject=desinscription"
    s = s.replace("{{UNSUBSCRIBE_LINK}}", unsub).replace("{{unsubscribe}}", unsub)
    s = _re.sub(r"\{\{\s*([A-Za-z_]+)\s*\}\}", lambda m: repl.get(m.group(1), m.group(0)), s)
    # Salutation sans prénom : « Bonjour , » / « Bonjour  , » → « Bonjour, »
    s = _re.sub(r"Bonjour\s+,", "Bonjour,", s)
    return s


# Base publique des endpoints de tracking (redirection clic + pixel d'ouverture)
TRACK_BASE = os.environ.get("GENESIS_PUBLIC_URL", "https://api.cheffer.email").rstrip("/")


def _add_tracking(html_str: str, site: str, email: str, campaign_id: str) -> str:
    """Réécrit les liens http(s) vers /api/sweego/click (token par destinataire) et
    ajoute un pixel /api/track/open. Ignore désinscription, mailto, ancres et
    variables non résolues. En cas d'échec de création d'un token, le lien
    d'origine est conservé (le tracking est best-effort, jamais bloquant)."""
    import re as _re
    from sweego_backend import make_click_token

    def _rw(m):
        url = m.group(2)
        if "{{" in url or "unsubscribe" in url.lower():
            return m.group(0)
        try:
            tok = make_click_token(site, email, campaign_id, url, channel="maildoso")
            return f'{m.group(1)}"{TRACK_BASE}/api/sweego/click?t={tok}"'
        except Exception:
            return m.group(0)

    out = _re.sub(r'(href=)"(https?://[^"]+)"', _rw, html_str)
    try:
        tok_open = make_click_token(site, email, campaign_id, "pixel:open", channel="maildoso")
        pixel = (f'<img src="{TRACK_BASE}/api/track/open?t={tok_open}" '
                 f'width="1" height="1" alt="" style="display:none">')
        out = out.replace("</body>", pixel + "</body>", 1) if "</body>" in out else out + pixel
    except Exception:
        pass
    return out


def send_email(to_email: str, subject: str, text: str | None = None, html: str | None = None,
               site: str = SITE_DEFAULT, campaign_id: str | None = None,
               to_name: str | None = None, mailbox: dict | None = None,
               in_reply_to: str | None = None, contact: dict | None = None,
               pieces_jointes: list | None = None) -> dict:
    """Envoie UN email via une boîte Maildoso (rotation auto si `mailbox` non fourni).

    text/html : au moins un des deux. Cold email → préférer text seul.
    {ok, mailbox, rfc_msgid | error}."""
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "destinataire invalide"}
    if not subject or not subject.strip():
        return {"ok": False, "error": "sujet requis"}
    if not text and not html:
        return {"ok": False, "error": "text ou html requis"}
    _ensure_tables()
    today = _date.today()
    mb = mailbox or _pick_mailbox(site, today)
    if not mb:
        return {"ok": False, "error": "aucune boîte active sous son cap journalier"}
    password = _env().get(mb.get("password_ref") or "MAILDOSO_SMTP_PASSWORD", "")
    if not password:
        return {"ok": False, "error": f"secret {mb.get('password_ref')} absent du .env"}

    if not text and html:
        from sweego_backend import html_to_text
        text = html_to_text(html)

    # Personnalisation par destinataire ({{prenom}}, {{entreprise}}, {{expediteur_*}}, désinscription…)
    subject = _apply_tokens(subject, contact, mb)
    text = _apply_tokens(text, contact, mb)
    html = _apply_tokens(html, contact, mb) if html else html

    # Tracking comportemental par destinataire (ouvertures via pixel, clics via
    # redirection) — SMTP n'offre rien nativement, on utilise l'infra de tokens Genesis.
    if html and campaign_id:
        try:
            html = _add_tracking(html, site, to_email, campaign_id)
        except Exception:
            pass

    msg = EmailMessage()
    msg["From"] = f"{mb['sender_name']} <{mb['email']}>"
    msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email
    msg["Subject"] = subject
    rfc_msgid = make_msgid(domain=mb["email"].split("@", 1)[-1])
    msg["Message-ID"] = rfc_msgid
    msg["List-Unsubscribe"] = f"<mailto:{mb['email']}?subject=unsubscribe>"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(text)
    # Pièces jointes : [{"nom", "contenu" (bytes), "type" ("application/pdf")}]. Ajoutées
    # APRÈS le corps — `add_attachment` bascule le message en multipart, et l'ordre décide
    # de ce que les clients mail affichent en premier.
    # L'HTML AVANT les pièces jointes : `add_alternative` sur un message déjà passé en
    # multipart/mixed range la version HTML à côté du PDF au lieu de l'attacher au texte.
    # Résultat constaté le 2026-08-21 : le destinataire recevait le corps, jamais la pièce.
    if html:
        msg.add_alternative(html, subtype="html")
    for pj in (pieces_jointes or []):
        # Un échec de pièce jointe n'était pas rendu : l'envoi partait sans elle, et
        # personne ne le savait avant que le destinataire ne le signale. On le REMONTE.
        grand, petit = (pj.get("type") or "application/octet-stream").split("/", 1)
        contenu = pj.get("contenu")
        if not isinstance(contenu, (bytes, bytearray)):
            return {"ok": False, "mailbox": mb["email"],
                    "error": f"pièce jointe « {pj.get('nom')} » : contenu non binaire"}
        try:
            msg.add_attachment(bytes(contenu), maintype=grand, subtype=petit,
                               filename=pj.get("nom") or "piece-jointe")
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "mailbox": mb["email"],
                    "error": f"pièce jointe « {pj.get('nom')} » refusée : {e}"}

    try:
        with smtplib.SMTP(mb.get("smtp_host", SMTP_HOST), int(mb.get("smtp_port", SMTP_PORT)),
                          timeout=45) as s:
            s.starttls()
            s.login(mb.get("username", mb["email"]), password)
            s.send_message(msg)
    except Exception as e:  # noqa: BLE001
        _record_sent(site, campaign_id, mb["email"], to_email, subject, rfc_msgid, "error", str(e))
        return {"ok": False, "error": f"smtp: {e}", "mailbox": mb["email"]}

    _increment_sent(mb["email"])
    _record_sent(site, campaign_id, mb["email"], to_email, subject, rfc_msgid, "sent")
    # Ce qui a RÉELLEMENT été transmis. Une pièce jointe qui n'arrive pas est invisible
    # côté serveur : sans cette liste, on en est réduit à croire le destinataire sur parole.
    parties = [f"{p.get_content_type()}"
               + (f" ({p.get_filename()})" if p.get_filename() else "")
               for p in msg.walk() if not p.get_content_type().startswith("multipart")]
    return {"ok": True, "mailbox": mb["email"], "rfc_msgid": rfc_msgid, "parties": parties}


def send_batch(campaign_id: str, subject: str, html_str: str, recipients: list[dict | str],
               site: str = SITE_DEFAULT, utm_campaign: str | None = None,
               pace: tuple[int, int] = (15, 60),
               on_sent: Callable[[dict], None] | None = None) -> dict:
    """Lot de cold emails avec rotation des boîtes + pause aléatoire entre envois.

    `recipients` : emails (str) ou dicts contacts ({email, prenom?, nom?}).
    `on_sent` : appelé avec le contact juste après chaque envoi réussi. Permet à
    l'appelant de persister sa progression au fil de l'eau plutôt qu'à la fin du lot —
    avec un pacing de 15-60 s, un lot de 200 dure ~2 h, et tout ce qui n'est écrit
    qu'à la fin est perdu si le process meurt entre-temps. Une exception du callback
    n'interrompt pas le lot (l'email, lui, est déjà parti).
    Les destinataires déjà servis sous ce `campaign_id` sont ignorés : reprise sûre.
    S'arrête proprement quand toutes les boîtes ont atteint leur cap.
    {ok, sent, sent_emails[], skipped, errors[], exhausted?}."""
    try:
        from utm_tagging import tag_links
        html_str = tag_links(html_str, "maildoso", "email", utm_campaign or campaign_id or "lcr-cold")
    except Exception:
        pass
    from sweego_backend import html_to_text
    text = html_to_text(html_str)

    sent, sent_emails, errors, exhausted = 0, [], [], False
    items = [{"email": r} if isinstance(r, str) else r for r in (recipients or [])]
    items = [it for it in items if it.get("email") and "@" in it["email"]]
    # Garde de reprise : on ne réexpédie jamais à quelqu'un que ce campaign_id a déjà servi.
    done = already_sent_emails(campaign_id)
    if done:
        before = len(items)
        items = [it for it in items if it["email"] not in done]
        skipped = before - len(items)
        if skipped:
            print(f"[maildoso] reprise {campaign_id} : {skipped} destinataire(s) déjà servi(s), ignoré(s)")
    else:
        skipped = 0
    for i, it in enumerate(items):
        res = send_email(it["email"], subject, text=text, html=html_str, site=site,
                         campaign_id=campaign_id, contact=it,
                         to_name=f"{it.get('prenom', '')} {it.get('nom', '')}".strip() or None)
        if res.get("ok"):
            sent += 1
            sent_emails.append(it["email"])
            if on_sent:
                try:
                    on_sent(it)
                except Exception as e:  # noqa: BLE001
                    print(f"[maildoso] on_sent({it['email']}) a échoué : {e}")
        else:
            errors.append({"email": it["email"], "error": res.get("error")})
            if "aucune boîte active" in (res.get("error") or ""):
                exhausted = True
                break
        if i < len(items) - 1:
            time.sleep(random.randint(*pace))
    out = {"ok": sent > 0 or not errors, "sent": sent, "sent_emails": sent_emails,
           "skipped": skipped, "errors": errors[:10]}
    if exhausted:
        out["exhausted"] = True
        out["note"] = f"cap journalier atteint après {sent} envois"
    return out


if __name__ == "__main__":
    import json
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if cmd == "verify":
        print(json.dumps({"api": verify_connection(), "stats": api_stats()},
                         ensure_ascii=False, default=str))
    elif cmd == "sync":
        print(json.dumps(sync_mailboxes(), ensure_ascii=False))
        print(json.dumps(list_mailboxes(), ensure_ascii=False, indent=2))
    elif cmd == "mailboxes":
        print(json.dumps(list_mailboxes(), ensure_ascii=False, indent=2))
    elif cmd == "test" and len(sys.argv) > 2:
        r = send_email(sys.argv[2], "Test connecteur Maildoso — Cheffer",
                       text="Bonjour,\n\nCeci est un email de test du connecteur Maildoso "
                            "fraîchement branché sur Cheffer (canal cold email maison).\n\n"
                            "Si tu lis ceci, le SMTP fonctionne. ✅\n\n— Juliette (via BigMatch)")
        print(json.dumps(r, ensure_ascii=False))
    else:
        print(f"usage: {sys.argv[0]} verify|sync|mailboxes|test <email>")
