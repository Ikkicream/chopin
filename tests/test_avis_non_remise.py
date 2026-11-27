"""tests/test_avis_non_remise.py — lecture des avis de non-remise Maildoso (23/11/2026).

Avant ce correctif, `reponses_imap.py` jetait tout avis de non-remise (il ne venait pas d'un
destinataire connu) : 0 rebond enregistré sur 3 469 envois Maildoso. Ces tests figent la
RÈGLE : un échec définitif devient un rebond, un retard n'en est pas un.
"""
import email
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import avis_non_remise as anr  # noqa: E402
import reponses_imap  # noqa: E402

DSN_RFC3464 = """From: Mail Delivery System <MAILER-DAEMON@smtp.maildoso.com>
To: j.durand@leclient-roi.com
Subject: Undelivered Mail Returned to Sender
Message-ID: <dsn-1@smtp.maildoso.com>
Date: Mon, 23 Nov 2026 10:00:00 +0000
MIME-Version: 1.0
Content-Type: multipart/report; report-type=delivery-status; boundary="B"

--B
Content-Type: text/plain

This is the mail system. Your message could not be delivered.

--B
Content-Type: message/delivery-status

Reporting-MTA: dns; smtp.maildoso.com

Final-Recipient: rfc822; Absent@Exemple-Inexistant.fr
Original-Recipient: rfc822;absent@exemple-inexistant.fr
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown

--B--
"""

DSN_RETARD = DSN_RFC3464.replace("Action: failed", "Action: delayed").replace(
    "Status: 5.1.1", "Status: 4.4.1").replace("<dsn-1@", "<dsn-2@")

DSN_TEXTE = """From: Mail Delivery Subsystem <mailer-daemon@googlemail.com>
Subject: Delivery Status Notification (Failure)
Message-ID: <dsn-3@google.com>
X-Failed-Recipients: inconnu@exemple.fr
Content-Type: text/plain

Address not found. 550 5.1.1 The email account that you tried to reach does not exist.
"""

REPONSE = """From: Client <client@exemple.fr>
Subject: Re: votre offre
Message-ID: <r-1@exemple.fr>
Content-Type: text/plain

Bonjour, merci.
"""


def m(s):
    return email.message_from_string(s)


def test_echec_definitif_lu():
    a = anr.analyser(m(DSN_RFC3464))
    assert anr.est_avis(m(DSN_RFC3464))
    assert a["action"] == "failed"
    assert a["adresses"] == {"absent@exemple-inexistant.fr": "5.1.1"}
    assert anr.nature("5.1.1") == "hard"


def test_retard_pas_un_rebond():
    assert anr.analyser(m(DSN_RETARD))["action"] == "delayed"
    assert anr.nature("4.4.1") == "soft"


def test_avis_texte_gmail():
    a = anr.analyser(m(DSN_TEXTE))
    assert a["action"] == "failed" and "inconnu@exemple.fr" in a["adresses"]


def test_reponse_humaine_pas_un_avis():
    assert not anr.est_avis(m(REPONSE))


def test_traiter_avis_ne_garde_que_les_destinataires_connus():
    out = {"rebonds": 0}
    vus = set()
    boite = {"email": "j.durand@leclient-roi.com"}
    # inconnu de Cheffer → ignoré
    reponses_imap._traiter_avis(m(DSN_RFC3464), "<dsn-1@x>", boite, "INBOX", "lcr", set(), vus, True, out)
    assert out["rebonds"] == 0
    # connu → compté une fois, puis dédoublonné
    connus = {"absent@exemple-inexistant.fr"}
    reponses_imap._traiter_avis(m(DSN_RFC3464), "<dsn-1@x>", boite, "INBOX", "lcr", connus, vus, True, out)
    reponses_imap._traiter_avis(m(DSN_RFC3464), "<dsn-1@x>", boite, "INBOX", "lcr", connus, vus, True, out)
    assert out["rebonds"] == 1
    # un retard ne compte jamais
    reponses_imap._traiter_avis(m(DSN_RETARD), "<dsn-2@x>", boite, "INBOX", "lcr", connus, vus, True, out)
    assert out["rebonds"] == 1


if __name__ == "__main__":
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
            print("ok", nom)
