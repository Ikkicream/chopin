#!/usr/bin/env python3
"""scripts/unibox.py — « Mes réponses » : les réponses des prospects relevées dans le Gmail
de chaque commercial (lot 1 de l'unibox, 28/10/2026).

Demande de Camille : « tu dois relever des boîtes Gmail que des comptes à qui on a envoyé
un email, pas le reste : je ne veux pas recevoir mes relevés bancaires dedans ».

D'où le relevé en DEUX TEMPS, pour qu'aucun message privé ne soit jamais lu :
  1. on ne demande à Gmail que l'en-tête `From` des messages récents (rien d'autre) ;
  2. on ne télécharge le message entier QUE si l'expéditeur est quelqu'un à qui CETTE boîte
     a écrit via Cheffer (`email_events`, `sent`, `mailbox` = la boîte). Tout le reste est
     ignoré sur la seule adresse, sans être ouvert ni stocké.

Lecture SEULE : `select(readonly=True)` et `BODY.PEEK` — rien n'est marqué lu, déplacé ni
supprimé dans Gmail. Dossiers relevés : la boîte de réception et les spams.

Une réponse est enregistrée UNE fois (`message_id` unique) dans `unibox_messages`, et
journalisée dans `email_events` (`reply`, canal `gmail`) pour les statistiques. Le classement
(personne / automatique / opposition) est celui des boîtes Maildoso (`reponses_imap.classer`).
Une opposition exclut le contact définitivement, comme pour Maildoso.

    python3 unibox.py            relève toutes les boîtes connectées
    python3 unibox.py --essai    affiche sans rien écrire
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

IMAP_HOTE = "imap.gmail.com"
DOSSIERS = ("INBOX", "[Gmail]/Spam")
JOURS = 30                 # fenêtre de relevé (et jamais avant la connexion de la boîte)
LOT_ENTETES = 200          # FETCH des en-têtes par paquets

_DDL = """
CREATE TABLE IF NOT EXISTS unibox_messages (
    id            bigserial PRIMARY KEY,
    utilisateur   text NOT NULL,
    site          text NOT NULL DEFAULT 'lcr',
    boite         text NOT NULL,
    email_contact text NOT NULL,
    message_id    text NOT NULL UNIQUE,
    in_reply_to   text,
    sujet         text,
    extrait       text,
    genre         text NOT NULL,          -- humain | auto | opposition
    dossier       text,
    campagne_id   text,
    recu_le       timestamptz,
    lu            boolean NOT NULL DEFAULT false,
    cree_le       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS unibox_messages_user ON unibox_messages (utilisateur, recu_le DESC);
CREATE TABLE IF NOT EXISTS unibox_releves (
    utilisateur text PRIMARY KEY,
    releve_le   timestamptz,
    erreur      text,
    ignores     integer,
    retenus     integer
);
-- Lot 2 (03/11) : les réponses écrites depuis Cheffer, parties de la boîte du commercial.
CREATE TABLE IF NOT EXISTS unibox_reponses (
    id          bigserial PRIMARY KEY,
    message     bigint NOT NULL REFERENCES unibox_messages (id),
    utilisateur text NOT NULL,
    texte       text NOT NULL,
    rfc_msgid   text,
    envoye_le   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS unibox_reponses_message ON unibox_reponses (message);
ALTER TABLE unibox_reponses ADD COLUMN IF NOT EXISTS html text;   -- mise en forme (03/11)
"""


def _pg():
    import pool_pg
    return pool_pg


def _assurer_tables() -> None:
    _pg()._ecrire(_DDL)


def _dec(v: str) -> str:
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:  # noqa: BLE001
        return v or ""


def destinataires(boite: str) -> dict[str, str | None]:
    """{adresse: campagne} des personnes à qui CETTE boîte a écrit via Cheffer."""
    lignes = _pg()._q("""
        SELECT lower(email::text), max(meta->>'campagne')
          FROM email_events
         WHERE event_type = 'sent' AND lower(mailbox) = lower(%(b)s)
         GROUP BY 1""", {"b": boite})
    return {e: c for e, c in lignes}


def _deja_vus() -> set[str]:
    return {r[0] for r in _pg()._q("SELECT message_id FROM unibox_messages")}


def _expediteurs(imap, ids: list[bytes]) -> dict[bytes, str]:
    """{id: adresse From} en ne demandant QUE l'en-tête From (jamais le corps)."""
    out: dict[bytes, str] = {}
    for k in range(0, len(ids), LOT_ENTETES):
        paquet = b",".join(ids[k:k + LOT_ENTETES]).decode()
        typ, data = imap.fetch(paquet, "(BODY.PEEK[HEADER.FIELDS (FROM)])")
        if typ != "OK":
            continue
        for item in data:
            if not isinstance(item, tuple):
                continue
            m = re.match(rb"(\d+) ", item[0])
            if m:
                de = email.message_from_bytes(item[1]).get("From", "")
                out[m.group(1)] = parseaddr(_dec(de))[1].strip().lower()
    return out


def relever_boite(b: dict, essai: bool = False) -> dict:
    import pg_sync
    import pool_pg
    import site_credentials_backend as scb
    import boite_commercial as bc
    from reponses_imap import _texte, classer

    res = {"utilisateur": b["utilisateur"], "boite": b["email"], "retenus": 0, "ignores": 0, "erreur": None}
    connus = destinataires(b["email"])
    if not connus:
        return res                         # personne n'a encore reçu d'email de cette boîte
    vus = _deja_vus()
    debut = max(datetime.now(timezone.utc) - timedelta(days=JOURS), b["connectee_le"] or datetime.min.replace(tzinfo=timezone.utc))
    depuis = debut.strftime("%d-%b-%Y")
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOTE, 993, timeout=30)
        bc.login_imap(imap, b["email"], scb.decrypt_value(b["mdp_chiffre"]))
    except Exception as e:  # noqa: BLE001
        res["erreur"] = f"connexion IMAP refusée ({type(e).__name__})"
        return res
    try:
        for dossier in DOSSIERS:
            try:
                if imap.select(f'"{dossier}"', readonly=True)[0] != "OK":
                    continue
                ids = imap.search(None, f'(SINCE "{depuis}")')[1][0].split()
            except Exception:  # noqa: BLE001
                continue
            for i, de in _expediteurs(imap, ids).items():
                if de not in connus:
                    res["ignores"] += 1      # message privé : jamais ouvert, jamais stocké
                    continue
                m = email.message_from_bytes(imap.fetch(i, "(BODY.PEEK[])")[1][0][1])
                mid = (m.get("Message-ID") or "").strip()[:250]
                if not mid or mid in vus:
                    continue
                sujet, corps = _dec(m.get("Subject", "")), _texte(m)
                genre = classer(sujet, corps, {k.lower(): v for k, v in m.items()})
                try:
                    quand = parsedate_to_datetime(m.get("Date"))
                except Exception:  # noqa: BLE001
                    quand = datetime.now(timezone.utc)
                vus.add(mid)
                res["retenus"] += 1
                print(f"[unibox] {b['utilisateur']:8} {dossier:12} {genre:10} {de:36} {sujet[:50]}", flush=True)
                if essai:
                    continue
                _pg()._ecrire("""
                    INSERT INTO unibox_messages (utilisateur, site, boite, email_contact, message_id, in_reply_to,
                                                 sujet, extrait, genre, dossier, campagne_id, recu_le)
                    VALUES (%(u)s, %(s)s, %(b)s, %(e)s, %(mid)s, %(irt)s, %(suj)s, %(ext)s, %(g)s, %(d)s, %(c)s, %(q)s)
                    ON CONFLICT (message_id) DO NOTHING""",
                    {"u": b["utilisateur"], "s": b.get("site") or "lcr", "b": b["email"], "e": de, "mid": mid,
                     "irt": (m.get("In-Reply-To") or "").strip()[:250] or None, "suj": sujet[:300],
                     "ext": corps[:4000], "g": genre, "d": "spam" if "Spam" in dossier else "reception",
                     "c": connus.get(de), "q": quand})
                pg_sync.record_event(de, "reply", b.get("site") or "lcr", "gmail", mailbox=b["email"],
                                     provider_msg_id=mid, at=quand,
                                     meta={"genre": genre, "sujet": sujet[:200], "source": "unibox",
                                           "commercial": b["utilisateur"], "campagne": connus.get(de)})
                if genre == "opposition":
                    pool_pg._ecrire("""UPDATE contacts SET etat = 'exclu', etat_at = now(),
                                              etat_motif = 'opposition reçue par réponse email (unibox)',
                                              blacklist_reason = 'opposition'
                                        WHERE email = %(e)s AND etat <> 'exclu'""", {"e": de})
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass
    return res


def relever_tous(essai: bool = False) -> list[dict]:
    _assurer_tables()
    boites = _pg()._q("""SELECT utilisateur, site, email, mdp_chiffre, connectee_le
                           FROM boites_commerciales WHERE mdp_chiffre IS NOT NULL""")
    out = []
    for u, site, adr, mdp, cle in boites:
        r = relever_boite({"utilisateur": u, "site": site, "email": adr, "mdp_chiffre": mdp, "connectee_le": cle}, essai)
        out.append(r)
        if not essai:
            _pg()._ecrire("""
                INSERT INTO unibox_releves (utilisateur, releve_le, erreur, ignores, retenus)
                VALUES (%(u)s, now(), %(e)s, %(i)s, %(r)s)
                ON CONFLICT (utilisateur) DO UPDATE SET releve_le = now(), erreur = EXCLUDED.erreur,
                    ignores = EXCLUDED.ignores, retenus = EXCLUDED.retenus""",
                {"u": u, "e": r["erreur"], "i": r["ignores"], "r": r["retenus"]})
    return out


# ── Lecture pour la page « Mes réponses » ────────────────────────────────────
def lister(utilisateur: str, site: str, tous: bool = False) -> dict:
    """Les réponses du commercial (ou de tous, pour un admin), avec la fiche du contact."""
    _assurer_tables()
    filtre = "" if tous else "AND m.utilisateur = %(u)s"
    lignes = _pg()._q(f"""
        SELECT m.id, m.message_id, m.utilisateur, m.boite, m.email_contact, m.sujet, m.extrait, m.genre, m.dossier,
               m.campagne_id, cc.nom, m.recu_le, m.lu, c.prenom, c.nom, c.societe, c.tel
          FROM unibox_messages m
          LEFT JOIN contacts c ON lower(c.email::text) = m.email_contact
          LEFT JOIN campagnes_commerciales cc ON cc.id::text = m.campagne_id
         WHERE m.site = %(s)s {filtre}
         ORDER BY m.recu_le DESC NULLS LAST
         LIMIT 500""", {"u": utilisateur, "s": site})
    cles = ("id", "message_id", "utilisateur", "boite", "email", "sujet", "extrait", "genre", "dossier", "campagne_id",
            "campagne", "recu_le", "lu", "prenom", "nom", "societe", "tel")
    messages = [dict(zip(cles, l)) for l in lignes]
    envoyees: dict[int, list] = {}
    if messages:
        for mid, texte, le, html_ in _pg()._q("""
                SELECT message, texte, envoye_le, html FROM unibox_reponses
                 WHERE message = ANY(%(ids)s) ORDER BY envoye_le""",
                {"ids": [m["id"] for m in messages]}):
            envoyees.setdefault(mid, []).append({"texte": texte, "envoye_le": le.isoformat(),
                                                 "html": html_ or None})
    for m in messages:
        m["recu_le"] = m["recu_le"].isoformat() if m["recu_le"] else None
        m["reponses"] = envoyees.get(m["id"], [])
    rel = _pg()._q("SELECT releve_le, erreur, ignores, retenus FROM unibox_releves WHERE utilisateur = %(u)s",
                   {"u": utilisateur})
    boite = _pg()._q("SELECT email FROM boites_commerciales WHERE utilisateur = %(u)s", {"u": utilisateur})
    return {
        "messages": messages,
        "boite": boite[0][0] if boite else None,
        "releve": ({"le": rel[0][0].isoformat() if rel[0][0] else None, "erreur": rel[0][1],
                    "ignores": rel[0][2], "retenus": rel[0][3]} if rel else None),
        "destinataires": len(destinataires(boite[0][0])) if boite else 0,
    }


def marquer_lu(utilisateur: str, ident: int, lu: bool = True, tous: bool = False) -> bool:
    filtre = "" if tous else "AND utilisateur = %(u)s"
    _pg()._ecrire(f"UPDATE unibox_messages SET lu = %(l)s WHERE id = %(i)s {filtre}",
                  {"l": lu, "i": ident, "u": utilisateur})
    return True


# Mise en forme de la réponse (03/11, « même pas un éditeur léger pour mettre du gras »).
# L'éditeur de l'écran produit du HTML ; on n'en garde QUE ces balises, sans aucun
# attribut sauf le href des liens (http, https, mailto). Pas de bleach sur le serveur :
# une liste blanche courte, écrite ici, se relit d'un coup d'œil.
_BALISES = {"b", "strong", "i", "em", "u", "a", "ul", "ol", "li", "br", "p", "div"}
_VIDES = {"br"}


def _html_sur(brut: str) -> str:
    import html as _h
    from html.parser import HTMLParser

    class _Filtre(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.out: list[str] = []
            self.ouvertes: list[str] = []
            self.cache = 0                      # dans un <script> ou un <style> : on jette

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self.cache += 1
            if tag not in _BALISES:
                return
            if tag == "a":
                href = (dict(attrs).get("href") or "").strip()
                if not re.match(r"(?i)^(https?://|mailto:)", href):
                    return
                self.out.append(f'<a href="{_h.escape(href, quote=True)}">')
            else:
                self.out.append(f"<{tag}>")
            if tag not in _VIDES:
                self.ouvertes.append(tag)

        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self.cache = max(0, self.cache - 1)
            if tag in self.ouvertes:
                while self.ouvertes:
                    t_ = self.ouvertes.pop()
                    self.out.append(f"</{t_}>")
                    if t_ == tag:
                        break

        def handle_data(self, data):
            if not self.cache:
                self.out.append(_h.escape(data))

    f = _Filtre()
    f.feed(brut or "")
    f.close()
    return "".join(f.out) + "".join(f"</{t_}>" for t_ in reversed(f.ouvertes))


def repondre(utilisateur: str, ident: int, texte: str, html: str | None = None) -> dict:
    """Répondre depuis Cheffer (lot 2, 03/11) : part de la boîte du commercial, dans le fil.

    Demandé par Camille quand Sylvie n'a pas pu se connecter à Gmail sur son poste : avec
    la boîte connectée par Google, elle n'a plus besoin d'ouvrir Gmail du tout. On ne répond
    QUE depuis sa propre boîte, même un admin : l'expéditeur, c'est la session."""
    corps_html = _html_sur(html) if html else ""
    if corps_html and not (texte or "").strip():
        from sweego_backend import html_to_text
        texte = html_to_text(corps_html)
    texte = (texte or "").strip()
    if not texte:
        return {"ok": False, "error": "Écris ta réponse avant d'envoyer."}
    r = _pg()._q("""SELECT email_contact, message_id, sujet, genre, site, boite FROM unibox_messages
                     WHERE id = %(i)s AND utilisateur = %(u)s""", {"i": ident, "u": utilisateur})
    if not r:
        return {"ok": False, "error": "Message introuvable dans ta boîte."}
    contact, msgid, sujet, genre, site, adresse = r[0]
    if genre == "opposition":
        return {"ok": False, "error": "Ce contact a demandé à ne plus être contacté : on ne lui écrit plus."}

    import boite_commercial as bc
    import maildoso_backend as md
    import site_credentials_backend as scb
    b = bc._ligne(utilisateur)
    if not b or not b.get("mdp_chiffre") or (b.get("email") or "").lower() != (adresse or "").lower():
        return {"ok": False, "error": "Ta boîte n'est plus connectée : reconnecte-la dans « Ma boîte d'envoi »."}
    mb = {"email": b["email"], "username": b["email"], "sender_name": b.get("nom_affiche") or utilisateur,
          "smtp_host": bc.SMTP_HOTE, "smtp_port": bc.SMTP_PORT,
          "password": scb.decrypt_value(b["mdp_chiffre"]), "canal": "gmail", "utilisateur": utilisateur}
    sujet = (sujet or "").strip()
    if not re.match(r"(?i)^(re|tr|fwd?)\s*:", sujet):
        sujet = f"Re: {sujet}" if sujet else "Re:"
    # Pas de suivi d'ouverture ni de format campagne : c'est une conversation, et un
    # identifiant sans six segments n'entre ni dans la fenêtre d'envoi ni dans les 120 jours.
    page = ('<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#222">'
            + corps_html + "</body></html>") if corps_html else None
    res = md.send_email(contact, sujet, text=texte, html=page, site=site, campaign_id=f"reponse-{ident}",
                        mailbox=mb, in_reply_to=msgid, suivi_ouverture=False, usage="reponse")
    if not res.get("ok"):
        if res.get("reporte"):
            return {"ok": False, "error": res.get("error") or "Envoi reporté : réessaie dans quelques minutes."}
        return {"ok": False, "error": res.get("error") or "Gmail a refusé l'envoi."}
    _assurer_tables()
    _pg()._ecrire("""INSERT INTO unibox_reponses (message, utilisateur, texte, rfc_msgid, html)
                     VALUES (%(m)s, %(u)s, %(t)s, %(r)s, %(h)s)""",
                  {"m": ident, "u": utilisateur, "t": texte, "r": res.get("rfc_msgid"),
                   "h": corps_html or None})
    marquer_lu(utilisateur, ident, True)
    return {"ok": True}


if __name__ == "__main__":
    for r in relever_tous(essai="--essai" in sys.argv):
        print(f"[unibox] {r['utilisateur']} ({r['boite']}) : {r['retenus']} réponse(s) retenue(s), "
              f"{r['ignores']} message(s) privé(s) ignoré(s) sans lecture"
              + (f" · {r['erreur']}" if r["erreur"] else ""), flush=True)
