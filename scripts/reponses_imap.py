#!/usr/bin/env python3
"""scripts/reponses_imap.py — les RÉPONSES des prospects remontent dans Cheffer (22/10/2026).

Jusqu'ici aucun programme ne lisait les boîtes Maildoso : le 21/10, 34 messages de prospects
dormaient dans les 4 boîtes (dont 2 oppositions RGPD) et Cheffer affichait « 0 réponse ».

Toutes les 15 min (fenêtre d'envoi), pour chaque boîte Maildoso du site :
  - lecture SEULE (BODY.PEEK : rien n'est marqué lu, rien n'est déplacé) de INBOX et Junk ;
  - on ne garde que les messages d'une adresse à qui Cheffer a écrit (journal `email_events`) ;
  - chaque message est journalisé UNE fois (`email_events`, type `reply`, provider_msg_id = Message-ID) ;
  - classement : `auto` (absence, accusé de réception), `opposition` (désinscription, RGPD),
    `humain` (tout le reste) ;
  - une opposition exclut le contact DÉFINITIVEMENT (`contacts.etat = 'exclu'`) : la base
    repoussoir de 120 jours ne suffit pas pour une opposition (article 21 du RGPD).

    python3 reponses_imap.py            relève et journalise
    python3 reponses_imap.py --essai    affiche sans rien écrire
"""
from __future__ import annotations

import email
import imaplib
import re
import sys
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

IMAP_HOTE, IMAP_PORT = "imap.horus.maildoso.com", 993
DOSSIERS = ("INBOX", "Junk")
JOURS = 21

AUTO = re.compile(r"absen|cong[ée]s|auto(matique|-?reply|matic)|out of office|accus[ée] de r[ée]ception|"
                  r"bien re[çc]u votre|fermeture|changement d'adresse|n'est plus consult|request .* received|"
                  r"ticket|demande .* (prise en compte|enregistr)|delivery status|undeliver|non remis", re.I)
OPPOSITION = re.compile(r"d[ée]sinscri|d[ée]sabonn|unsubscribe|ne (plus|pas) (me )?(recevoir|contacter|solliciter)|"
                        r"supprim\w* (moi|mes|mon|de vos)|retir\w* (moi|mon adresse)|opposition|rgpd|"
                        r"article 21|cnil|stop\b|pas int[ée]ress", re.I)


def _texte(m) -> str:
    for type_ in ("text/plain", "text/html"):
        for p in m.walk():
            if p.get_content_type() == type_:
                t = (p.get_payload(decode=True) or b"").decode(p.get_content_charset() or "utf-8", "ignore")
                if type_ == "text/html":
                    t = re.sub(r"<[^>]+>", " ", t)
                # On coupe la citation de notre message : seule la réponse compte.
                t = re.split(r"\n\s*(Le .{5,120}a écrit|On .{5,120}wrote|De ?:|From:|-{4,}|_{4,})", t)[0]
                return re.sub(r"\s+", " ", t).strip()
    return ""


def classer(sujet: str, corps: str, entetes: dict) -> str:
    """Fonction PURE : 'auto' | 'opposition' | 'humain'."""
    if re.search(r"auto-(replied|generated)", entetes.get("auto-submitted", ""), re.I) or entetes.get("x-autoreply"):
        return "auto"
    if OPPOSITION.search(sujet + " " + corps[:600]):
        return "opposition"
    if AUTO.search(sujet) or AUTO.search(corps[:300]):
        return "auto"
    return "humain"


def _destinataires_connus() -> set[str]:
    import pool_pg
    return {r[0] for r in pool_pg._q("SELECT DISTINCT email::text FROM email_events WHERE event_type = 'sent'")}


def _deja_vus() -> set[str]:
    import pool_pg
    return {r[0] for r in pool_pg._q("""SELECT provider_msg_id FROM email_events
                                         WHERE event_type = 'reply' AND provider_msg_id IS NOT NULL""")}


def relever(site: str = "lcr", essai: bool = False) -> dict:
    import os
    import expediteur
    import pg_sync
    import pool_pg
    env = dict(l.strip().split("=", 1) for l in open(Path(__file__).resolve().parent.parent / ".env")
               if "=" in l and not l.lstrip().startswith("#"))
    connus, vus = _destinataires_connus(), _deja_vus()
    depuis = (datetime.now(timezone.utc) - timedelta(days=JOURS)).strftime("%d-%b-%Y")
    out = {"boites": 0, "nouvelles": 0, "humain": 0, "auto": 0, "opposition": 0, "erreurs": []}
    for b in expediteur.boites(site):
        mdp = (env.get(b.get("password_ref") or "MAILDOSO_SMTP_PASSWORD") or os.environ.get("MAILDOSO_SMTP_PASSWORD", "")).strip().strip('"\'')
        try:
            imap = imaplib.IMAP4_SSL(IMAP_HOTE, IMAP_PORT, timeout=30)
            imap.login(b["email"], mdp)
        except Exception as e:  # noqa: BLE001
            out["erreurs"].append(f"{b['email']} : {type(e).__name__}")
            continue
        out["boites"] += 1
        for dossier in DOSSIERS:
            try:
                if imap.select(dossier, readonly=True)[0] != "OK":
                    continue
                ids = imap.search(None, f'(SINCE "{depuis}")')[1][0].split()
            except Exception:  # noqa: BLE001
                continue
            for i in ids:
                m = email.message_from_bytes(imap.fetch(i, "(BODY.PEEK[])")[1][0][1])
                de = parseaddr(m.get("From", ""))[1].strip().lower()
                mid = (m.get("Message-ID") or "").strip()[:250]
                if de not in connus or not mid or mid in vus:
                    continue
                sujet = str(make_header(decode_header(m.get("Subject", ""))))
                corps = _texte(m)
                genre = classer(sujet, corps, {k.lower(): v for k, v in m.items()})
                try:
                    quand = parsedate_to_datetime(m.get("Date"))
                except Exception:  # noqa: BLE001
                    quand = None
                out["nouvelles"] += 1
                out[genre] += 1
                vus.add(mid)
                print(f"[reponses] {b['email'].split('@')[0]:10} {dossier:5} {genre:10} {de.split('@')[1]:28} {sujet[:60]}", flush=True)
                if essai:
                    continue
                pg_sync.record_event(de, "reply", site, "maildoso", mailbox=b["email"], provider_msg_id=mid,
                                     at=quand, meta={"genre": genre, "sujet": sujet[:200], "dossier": dossier,
                                                     "extrait": corps[:500]})
                if genre == "opposition":
                    pool_pg._ecrire("""UPDATE contacts SET etat = 'exclu', etat_at = now(),
                                              etat_motif = 'opposition reçue par réponse email (relevé IMAP)',
                                              blacklist_reason = 'opposition'
                                        WHERE email = %(e)s AND etat <> 'exclu'""", {"e": de})
        imap.logout()
    return out


if __name__ == "__main__":
    r = relever(essai="--essai" in sys.argv)
    print(f"[reponses] {r['boites']} boîte(s) · {r['nouvelles']} nouvelle(s) : {r['humain']} humaine(s), "
          f"{r['auto']} automatique(s), {r['opposition']} opposition(s)"
          + (f" · erreurs : {r['erreurs']}" if r["erreurs"] else ""), flush=True)
