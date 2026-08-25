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


def _toutes_pleines(site: str) -> bool:
    """Plus aucune boîte n'a de place aujourd'hui ? Alors seulement le lot s'arrête."""
    try:
        import expediteur
        return not any(b["active"] and b["reste"] > 0 for b in expediteur.boites(site))
    except Exception:  # noqa: BLE001
        return False


def _boite_du_contact(site: str, email_contact: str, today: _date,
                      usage: str | None = None) -> dict | None:
    """La boîte d'envoi de CE contact — la même à chaque fois (décision du 2026-08-23).

    L'ancienne rotation « la moins chargée, au hasard » changeait d'expéditeur d'un envoi
    à l'autre. Or un prospect qui a ouvert a fait gagner à cette adresse-là un signal
    positif dans son client de messagerie : lui réécrire depuis une autre, c'est repartir
    de zéro auprès de lui. Voir `expediteur`.

    Rend None quand la boîte du contact est pleine : il attend demain plutôt que de
    changer d'adresse. L'appelant doit le traiter comme un REPORT, pas comme un échec.
    Repli sur l'ancienne rotation si PostgreSQL ne répond pas — mieux vaut un expéditeur
    imparfait qu'un lot bloqué.
    """
    try:
        import expediteur
        return expediteur.choisir(email_contact, site, usage=usage)
    except Exception as e:  # noqa: BLE001
        print(f"[maildoso] affinité expéditeur indisponible ({type(e).__name__}: {e}) "
              f"— rotation par défaut", flush=True)
        return _pick_mailbox(site, today)


def _increment_sent(email: str):
    c = _conn()
    try:
        c.execute("UPDATE mailboxes SET sent_today=sent_today+1 WHERE email=?", [email])
    finally:
        c.close()


def stats(site: str = SITE_DEFAULT) -> dict:
    """Compteurs d'envoi Maildoso pour un site (table maildoso_sent).
    Maildoso = SMTP : pas de tracking d'ouverture/clic natif → seuls sent/errors sont connus."""
    # Journal servi par PostgreSQL (fin du Lot 1) : `maildoso_sent` vit dans
    # `god_mode.duckdb`, le fichier que le dispatch et le scraping se disputent — et dont
    # le verrou a produit 156 lignes de journal en double le 2026-08-22. Repli DuckDB si
    # PostgreSQL ne répond pas.
    try:
        import journal_pg
        return journal_pg.stats_canal(site, "maildoso")
    except Exception as e:  # noqa: BLE001
        print(f"[maildoso] stats: PostgreSQL indisponible ({type(e).__name__}: {e}) "
              f"— repli DuckDB", flush=True)
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


def _comptabiliser(site, campaign_id, mailbox, to_email, subject, rfc_msgid,
                   status, error=None):
    """Écrit la trace DuckDB d'un envoi — sans jamais pouvoir faire échouer l'envoi.

    Un email déjà transmis ne se rattrape pas ; l'échec d'une écriture qui le CONSTATE ne
    doit donc rien interrompre. Chaque écriture est isolée : un verrou sur `god_mode` ne
    doit pas non plus empêcher la seconde de réussir.

    L'échec est CRIÉ, jamais avalé : un lot où la comptabilité DuckDB tombe silencieusement
    laisserait `maildoso_sent` incomplet sans que personne ne s'en aperçoive.
    """
    try:
        _record_sent(site, campaign_id, mailbox, to_email, subject, rfc_msgid, status, error)
    except Exception as e:  # noqa: BLE001
        print(f"[maildoso] journal DuckDB indisponible pour {to_email} "
              f"({type(e).__name__}: {str(e)[:120]}) — l'email est parti, "
              f"le journal PostgreSQL fait foi", flush=True)
    if status == "sent":
        try:
            _increment_sent(mailbox)
        except Exception as e:  # noqa: BLE001
            print(f"[maildoso] compteur de {mailbox} non incrémenté "
                  f"({type(e).__name__}: {str(e)[:120]}) — sans conséquence, le quota du "
                  f"jour se compte dans le journal", flush=True)


def _record_sent(site, campaign_id, mailbox, to_email, subject, rfc_msgid, status, error=None):
    c = _conn()
    try:
        c.execute("INSERT INTO maildoso_sent VALUES (?,?,?,?,?,?,?,?,?,?)",
                  [str(_uuid.uuid4())[:8], site, campaign_id or "", mailbox, to_email,
                   subject, rfc_msgid or "", status, error, datetime.now(timezone.utc)])
    finally:
        c.close()
    _journaliser_hors_campagne(site, campaign_id, mailbox, to_email, rfc_msgid, status)


def _journaliser_hors_campagne(site, campaign_id, mailbox, to_email, rfc_msgid, status):
    """Journalise dans PostgreSQL les envois qu'aucun autre chemin ne journalise.

    Un envoi de campagne est déjà porté au journal par `mark_pushed_to_emelia`, qui écrit
    PostgreSQL avant DuckDB. Les BAT et les tests, eux, ne passent pas par ce chemin : ils
    partaient réellement, consommaient le quota de la boîte, et n'apparaissaient nulle part
    dans PostgreSQL. Quatre d'entre eux le 2026-08-21 suffisaient à décaler de 4 envois le
    calcul de montée en charge une fois celui-ci lu dans PostgreSQL.

    La distinction se lit dans l'identifiant : un lot de campagne vaut
    « {site}-{campagne}-{AAAA}-{MM}-{JJ} », donc six segments. Tout le reste — chaîne vide,
    « lcr-bat », un nom de gabarit — est un envoi hors campagne.

    Best-effort et volontairement muet en cas d'échec de la campagne : re-journaliser un
    envoi déjà journalisé créerait le doublon que tout le reste s'emploie à supprimer.
    """
    if status != "sent" or not to_email:
        return
    if len((campaign_id or "").split("-")) >= 6:
        return          # lot de campagne : déjà journalisé, ne pas écrire deux fois
    try:
        import pg_sync
        pg_sync.record_event(to_email, "sent", site, "maildoso", mailbox=mailbox,
                             provider_msg_id=rfc_msgid or None,
                             meta={"source": "maildoso_bat", "campagne": campaign_id or ""})
    except Exception as e:  # noqa: BLE001
        print(f"[maildoso] journal PostgreSQL indisponible pour un envoi hors campagne : "
              f"{type(e).__name__}: {e}", flush=True)


def already_sent_emails(campaign_id: str) -> set[str]:
    """Destinataires déjà servis pour ce campaign_id (ligne 'sent' dans maildoso_sent).

    Sert de garde de reprise : `maildoso_sent` est écrit juste après chaque SMTP réussi,
    c'est donc la seule trace fiable quand le process meurt au milieu d'un lot — les
    compteurs de campagne et le marquage des contacts, eux, n'étaient historiquement
    posés qu'à la toute fin du lot. Sans cette garde, un redémarrage en cours d'envoi
    repioche les contacts déjà contactés et leur renvoie le même email."""
    if not campaign_id:
        return set()
    # Lue dans PostgreSQL depuis la fin du Lot 1. Cette garde protège du scénario
    # « le process meurt au milieu d'un lot » — or ce qui le tuait le plus souvent était
    # précisément le verrou du fichier qu'elle interrogeait. Elle ne pouvait pas être la
    # dernière à rester dessus. En cas d'indisponibilité PostgreSQL on retombe sur DuckDB :
    # une garde dégradée vaut mieux qu'aucune garde.
    try:
        import journal_pg
        return journal_pg.deja_servis(campaign_id)
    except Exception as e:  # noqa: BLE001
        print(f"[maildoso] garde de reprise: PostgreSQL indisponible "
              f"({type(e).__name__}: {e}) — repli DuckDB", flush=True)
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


def _add_tracking(html_str: str, site: str, email: str, campaign_id: str,
                  suivi_ouverture: bool = True) -> str:
    """Réécrit les liens http(s) vers /api/sweego/click (token par destinataire) et
    ajoute un pixel /api/track/open. Ignore désinscription, mailto, ancres et
    variables non résolues. En cas d'échec de création d'un token, le lien
    d'origine est conservé (le tracking est best-effort, jamais bloquant).

    `suivi_ouverture=False` retire le PIXEL sans toucher aux liens : le guide de
    délivrabilité de Maildoso déconseille le pixel d'ouverture, que Gmail note. Les clics,
    eux, restent mesurés — c'est une redirection, pas une image invisible. L'option est
    posée au cas par cas : couper le pixel partout priverait les commerciaux de la liste
    des ouvreurs, et le taux d'ouverture est aussi ce qui déclenche l'alerte sur la pente.
    """
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
    if not suivi_ouverture:
        return out
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
               pieces_jointes: list | None = None, suivi_ouverture: bool = True,
               usage: str | None = None) -> dict:
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
    # `usage` sépare les pools d'adresses ('adhoc' pour les campagnes, 'mozart' pour les
    # scénarios). L'affinité d'un contact déjà servi prime : voir `expediteur.choisir`.
    mb = mailbox or _boite_du_contact(site, (contact or {}).get("email") or to_email,
                                      today, usage=usage)
    if not mb:
        return {"ok": False, "reporte": True,
                "error": "aucune boîte disponible pour ce contact aujourd'hui"}
    # ── La fenêtre de 120 jours, au point de passage ────────────────────────────
    # Elle était appliquée par chaque APPELANT : `campaign_engine._drop_recently_emailed`
    # croisait deux sources (base repoussoir + journal), `mozart._envoyer` n'en consultait
    # qu'une. Deux copies d'une même règle divergent toujours, et c'est la plus coûteuse de
    # la plateforme — un renvoi trop tôt se paie en réputation. Elle vit donc ici, dans le
    # seul endroit par lequel TOUT envoi passe. Les appelants gardent leur filtre en amont :
    # il évite de composer un message pour quelqu'un qui sera refusé, mais il n'est plus la
    # garantie.
    #
    # Les BAT et les tests en sont exemptés : ils partent vers nos propres adresses, à
    # notre demande. La distinction est celle qui sert déjà au journal — un lot de campagne
    # porte six segments (« {site}-{campagne}-{AAAA}-{MM}-{JJ} »), tout le reste n'en est pas.
    if len((campaign_id or "").split("-")) >= 6:
        try:
            import journal_pg
            if journal_pg.recemment_servis([to_email], SUPPRESSION_JOURS):
                return {"ok": False, "refuse": True,
                        "error": f"contacté il y a moins de {SUPPRESSION_JOURS} jours"}
        except Exception as e:  # noqa: BLE001
            # Une barrière illisible ne doit pas laisser passer en silence : on le crie,
            # et on s'en remet au filtre amont de l'appelant.
            print(f"[maildoso] fenêtre des {SUPPRESSION_JOURS} jours illisible "
                  f"({type(e).__name__}: {e}) — envoi laissé au filtre de l'appelant",
                  flush=True)

    # Écart minimum depuis le DERNIER envoi de CETTE boîte. Contrôlé ici, avant toute
    # écriture SMTP, parce que c'est le seul endroit qui connaît la boîte retenue. Le
    # refus est un REPORT : l'appelant passe au contact suivant, qui partira d'une autre
    # adresse — c'est ainsi que la rotation et la cadence se renforcent au lieu de se gêner.
    dernier = _DERNIER_ENVOI.get(mb["email"])
    if dernier is not None:
        reste = ECART_MIN_BOITE - (time.time() - dernier)
        if reste > 0:
            return {"ok": False, "reporte": True,
                    "error": f"cadence — {mb['email'].split('@')[0]} a écrit il y a "
                             f"{int(ECART_MIN_BOITE - reste)} s, minimum {ECART_MIN_BOITE} s",
                    "mailbox": mb["email"]}

    password = _env().get(mb.get("password_ref") or "MAILDOSO_SMTP_PASSWORD", "")
    if not password:
        return {"ok": False, "error": f"secret {mb.get('password_ref')} absent du .env"}

    if not text and html:
        from sweego_backend import html_to_text
        text = html_to_text(html)

    # Spintax AVANT la personnalisation : une variante peut contenir {{prenom}}, et le
    # tirage doit être fait quand les accolades doubles sont encore intactes. Le tirage est
    # déterministe par destinataire — sinon une relance serait rédigée autrement que le
    # premier message reçu par la même personne.
    try:
        import qualite_message as qm
        subject = qm.spintax(subject, to_email)
        text = qm.spintax(text, to_email)
        html = qm.spintax(html, to_email) if html else html
    except ImportError:
        pass

    # Personnalisation par destinataire ({{prenom}}, {{entreprise}}, {{expediteur_*}}, désinscription…)
    gabarits = [x for x in (subject, text, html) if x]
    subject = _apply_tokens(subject, contact, mb)
    text = _apply_tokens(text, contact, mb)
    html = _apply_tokens(html, contact, mb) if html else html

    # Dernier rideau AVANT le SMTP : un email troué ne se rattrape pas, il se lit.
    # Le contrôle porte sur le texte RENDU, donc il voit ce que le destinataire verrait —
    # y compris une variable qu'aucun moteur ne connaît, que `_apply_tokens` laissait
    # passer telle quelle, et les accolades simples ou crochets qu'il ne regardait même pas.
    # Le refus est INDIVIDUEL : il écarte ce destinataire, jamais le lot.
    try:
        import garde_variables as gvar
        subject = gvar.nettoyer_ponctuation(subject)
        text = gvar.nettoyer_ponctuation(text)
        verdict = gvar.verifier_avant_envoi(subject, text, html, contact, gabarits)
        if not verdict["ok"]:
            print(f"[maildoso] envoi REFUSÉ à {to_email} : {'; '.join(verdict['motifs'][:3])}",
                  flush=True)
            return {"ok": False, "refuse": True, "error": "message incomplet: "
                    + "; ".join(verdict["motifs"][:3])}
    except ImportError:
        # Le garde-fou absent ne doit pas empêcher d'envoyer, mais il doit s'entendre.
        print("[maildoso] garde_variables introuvable — envoi SANS contrôle des variables",
              flush=True)

    # Tracking comportemental par destinataire (ouvertures via pixel, clics via
    # redirection) — SMTP n'offre rien nativement, on utilise l'infra de tokens Genesis.
    if html and campaign_id:
        try:
            html = _add_tracking(html, site, to_email, campaign_id,
                                 suivi_ouverture=suivi_ouverture)
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
        _comptabiliser(site, campaign_id, mb["email"], to_email, subject, rfc_msgid,
                       "error", str(e))
        return {"ok": False, "error": f"smtp: {e}", "mailbox": mb["email"]}

    # ── Comptabilité : APRÈS l'envoi, donc jamais bloquante ──────────────────────
    # L'email est PARTI. Ce qui suit ne fait que l'écrire quelque part, et ce quelque part
    # est `god_mode.duckdb` — un fichier à écrivain unique que le scraping et le dispatch
    # se disputent. Le 2026-08-24, un verrou sur ce fichier a levé ici, l'exception est
    # remontée jusqu'à `send_batch`, et le lot du matin s'est arrêté à 29 emails sur 80.
    # Les 29 étaient partis ; les 51 autres ne sont jamais partis, pour une écriture de
    # comptabilité.
    #
    # Ces deux écritures sont en outre REDONDANTES depuis la fin du Lot 1 : le journal
    # `email_events` porte l'envoi, et le compteur du jour se lit dans ce journal
    # (`expediteur.envoyes_aujourdhui`), plus dans `mailboxes.sent_today`. Elles ne
    # méritaient donc en aucun cas de coûter un lot.
    _DERNIER_ENVOI[mb["email"]] = time.time()
    _comptabiliser(site, campaign_id, mb["email"], to_email, subject, rfc_msgid, "sent")
    # Ce qui a RÉELLEMENT été transmis. Une pièce jointe qui n'arrive pas est invisible
    # côté serveur : sans cette liste, on en est réduit à croire le destinataire sur parole.
    parties = [f"{p.get_content_type()}"
               + (f" ({p.get_filename()})" if p.get_filename() else "")
               for p in msg.walk() if not p.get_content_type().startswith("multipart")]
    return {"ok": True, "mailbox": mb["email"], "rfc_msgid": rfc_msgid, "parties": parties}


# ── La cadence d'envoi ────────────────────────────────────────────────────────
# Un fournisseur ne regarde pas seulement COMBIEN on envoie, mais À QUEL RYTHME. Une
# adresse jeune qui crache trente messages en vingt minutes se signale toute seule : c'est
# la signature d'un robot, pas d'une personne qui écrit.
#
# Le 2026-08-24 au matin, la rotation entre boîtes était cassée (le compteur par boîte
# rendait zéro pour tout le monde) : les 29 emails du lot sont partis de la MÊME adresse
# en 18 minutes, soit ~97 par heure. La pause de 15-60 s était respectée — elle s'applique
# au LOT, pas à la boîte. Une pause par lot ne protège rien dès qu'une seule boîte encaisse
# tout.
#
# D'où deux règles, et la plus contraignante des deux gagne :
#   1. **par BOÎTE** : jamais moins de `ECART_MIN_BOITE` entre deux envois d'une même
#      adresse. C'est celle qui protège la réputation.
#   2. **étalement** : le lot se répartit sur ce qui reste de la fenêtre d'envoi, plutôt
#      que de se vider d'un coup au début. Un envoi régulier toute la journée ressemble à
#      quelqu'un qui travaille ; une rafale à 8h30 ressemble à une machine.
#
# Maildoso n'a AUCUNE file d'attente de son côté : c'est du SMTP direct (`smtplib`), le
# message part à la seconde où on le remet. La régulation nous appartient entièrement —
# vérifié le 2026-08-24 à la demande de Camille.
# La fenêtre de non-recontact. Lue depuis `contacts_pool_backend`, qui la porte pour toute
# la plateforme : trois constantes valant 120 dans trois modules finiraient par diverger.
try:
    from contacts_pool_backend import SUPPRESSION_DAYS as SUPPRESSION_JOURS
except Exception:  # noqa: BLE001
    SUPPRESSION_JOURS = 120

ECART_MIN_BOITE = 240        # secondes entre deux envois d'une même boîte (4 min)
ECART_MIN_LOT = 20           # plancher absolu entre deux envois, toutes boîtes confondues
ECART_MAX_LOT = 900          # au-delà, un lot ne finirait jamais (15 min)

# Quand chaque boîte a envoyé pour la dernière fois, dans CE process. Volontairement en
# mémoire : la contrainte protège d'une rafale à l'intérieur d'un lot, pas d'un envoi
# légitime après un redémarrage.
_DERNIER_ENVOI: dict[str, float] = {}


def _cadence(restants: int) -> tuple[int, int]:
    """L'écart à observer entre deux envois, en secondes : (min, max) pour le tirage.

    On étale ce qui reste sur le temps qui reste. À 14h avec 36 emails et une fenêtre qui
    ferme à 17h59, cela donne un envoi toutes les 6-7 minutes — un rythme d'humain.

    La borne de fin est demandée à `deliverability_agent`, qui la porte pour toute la
    plateforme : la reparser ici avec un repli numérique en dur en faisait une TROISIÈME
    écriture, qui aurait cessé de suivre au premier changement d'horaire.
    """
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    import deliverability_agent as da

    maintenant = _dt.now(ZoneInfo(da.SEND_TZ))
    h, m = (int(x) for x in da.SEND_END.split(":"))
    fin_fenetre = maintenant.replace(hour=h, minute=m, second=0, microsecond=0)
    secondes = max(0, (fin_fenetre - maintenant).total_seconds())
    if restants <= 1 or secondes <= 0:
        return (ECART_MIN_LOT, ECART_MIN_LOT * 2)
    ideal = int(secondes / restants)
    base = max(ECART_MIN_LOT, min(ECART_MAX_LOT, ideal))
    # Un intervalle tiré au hasard autour de la cible : un envoi TOUTES LES 380 secondes,
    # à la seconde près, est aussi reconnaissable qu'une rafale.
    return (max(ECART_MIN_LOT, int(base * 0.7)), int(base * 1.3))


def send_batch(campaign_id: str, subject: str, html_str: str, recipients: list[dict | str],
               site: str = SITE_DEFAULT, utm_campaign: str | None = None,
               pace: tuple[int, int] | None = None,
               on_sent: Callable[[dict], None] | None = None,
               suivi_ouverture: bool = True, usage: str | None = None) -> dict:
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
    # Trois issues qui ne sont PAS des erreurs, et qu'il faut compter à part sous peine
    # de les confondre avec une panne :
    #   - reportés : la boîte attitrée du contact est pleine, il attend demain ;
    #   - refusés  : le message aurait comporté un trou, on ne l'envoie pas ;
    #   - ignorés  : déjà servis par ce lot (reprise).
    reportes: list[str] = []
    refuses: list[dict] = []
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
        # Second rideau : un destinataire ne doit JAMAIS emporter le lot. `send_email` rend
        # normalement un dictionnaire, mais une panne imprévue (verrou, réseau, gabarit
        # tordu) y lèverait — et le 2026-08-24 c'est exactement ce qui a arrêté l'envoi du
        # matin à 29 emails sur 80. On isole donc chaque contact.
        # L'écart par boîte se vérifie AVANT d'écrire, jamais après. Posé après l'envoi,
        # il ne retardait que le SUIVANT : deux messages pouvaient partir de la même
        # adresse à vingt secondes d'intervalle, puis attendre — exactement la rafale
        # qu'il devait interdire. C'est `send_email` qui applique la règle maintenant,
        # parce que c'est lui qui sait quelle boîte va servir.
        try:
            res = send_email(it["email"], subject, text=text, html=html_str, site=site,
                             suivi_ouverture=suivi_ouverture, usage=usage,
                             campaign_id=campaign_id, contact=it,
                             to_name=f"{it.get('prenom', '')} {it.get('nom', '')}".strip() or None)
        except Exception as e:  # noqa: BLE001
            print(f"[maildoso] {it['email']} : envoi interrompu "
                  f"({type(e).__name__}: {str(e)[:140]}) — on passe au suivant", flush=True)
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
        if res.get("ok"):
            sent += 1
            sent_emails.append(it["email"])
            # La boîte qui a RÉELLEMENT écrit, transmise au callback par le contact.
            # Sans elle, le journal PostgreSQL enregistre l'envoi sans expéditeur — et
            # `expediteur.envoyes_aujourdhui`, qui compte par boîte, rend 0 pour tout le
            # monde. Conséquence vécue le 2026-08-24 : le plafond de 40/jour/boîte n'était
            # PAS appliqué, et les 29 envois du matin sont tous partis de la même adresse
            # au lieu d'être répartis sur quatre.
            it["_mailbox"] = res.get("mailbox")
            if on_sent:
                try:
                    on_sent(it)
                except Exception as e:  # noqa: BLE001
                    print(f"[maildoso] on_sent({it['email']}) a échoué : {e}")
        elif res.get("reporte"):
            # La boîte attitrée de ce contact est pleine. On ne change PAS d'expéditeur
            # (c'est tout l'intérêt de l'affinité), on passe au suivant. Le lot ne
            # s'arrête que si plus AUCUNE boîte n'a de place — sinon la première boîte
            # remplie stopperait l'envoi des trois autres.
            reportes.append(it["email"])
            if _toutes_pleines(site):
                exhausted = True
                break
            continue          # rien n'est parti : pas de pause à observer
        elif res.get("refuse"):
            refuses.append({"email": it["email"], "motif": res.get("error")})
            continue          # rien n'est parti : pas de pause à observer
        else:
            errors.append({"email": it["email"], "error": res.get("error")})
            if "aucune boîte active" in (res.get("error") or ""):
                exhausted = True
                break
        if i < len(items) - 1:
            # L'écart est recalculé à CHAQUE tour : la fenêtre se referme pendant le lot,
            # et un intervalle figé au départ finirait par déborder l'heure de fermeture.
            bas, haut = pace or _cadence(len(items) - i - 1)
            time.sleep(max(1, random.randint(bas, max(bas, haut))))
    if refuses:
        print(f"[maildoso] {campaign_id} : {len(refuses)} destinataire(s) REFUSÉ(S) — "
              f"message incomplet. Premier : {refuses[0]}", flush=True)
    if reportes:
        print(f"[maildoso] {campaign_id} : {len(reportes)} destinataire(s) reporté(s) — "
              f"boîte attitrée pleine", flush=True)
    out = {"ok": sent > 0 or not errors, "sent": sent, "sent_emails": sent_emails,
           "reportes": len(reportes), "refuses": refuses[:20], "nb_refuses": len(refuses),
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
