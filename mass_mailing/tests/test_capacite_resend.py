"""Apprentissage de capacité à partir des événements Resend (13/10/2026)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.capacite import analyser_evenement_resend, groupe_de  # noqa: E402


def ev(typ, to="jean@gmail.com", bounce=None):
    return {"type": typ, "data": {"to": [to], "from": '"Zylio" <hello@news.zylio.email>', "created_at": "2026-10-14T09:10:00Z",
                                  **({"bounce": bounce} if bounce else {})}}


class TestResend(unittest.TestCase):
    def test_livre(self):
        r = analyser_evenement_resend("email.delivered", ev("email.delivered"), "svix1")
        self.assertEqual((r["etat"], r["identite"], r["sending_ip"], groupe_de(r["domaine_dest"])),
                         ("accepted", "news.zylio.email", "resend", "gmail"))

    def test_retard_et_rebond_temporaire(self):
        self.assertEqual(analyser_evenement_resend("email.delivery_delayed", ev("email.delivery_delayed"), "s")["etat"], "deferred")
        r = analyser_evenement_resend("email.bounced", ev("email.bounced", bounce={"type": "Temporary", "subType": "MailboxFull", "message": "mailbox full"}), "s")
        self.assertEqual(r["etat"], "deferred")

    def test_rebond_definitif(self):
        r = analyser_evenement_resend("email.bounced", ev("email.bounced", to="x@orange.fr",
                                      bounce={"type": "Permanent", "subType": "General", "message": "550 5.1.1 user unknown"}), "s")
        self.assertEqual((r["etat"], groupe_de(r["domaine_dest"])), ("hard_bounce", "orange"))
        self.assertTrue(r["categorie"].startswith("permanent"))

    def test_ignore(self):
        self.assertIsNone(analyser_evenement_resend("email.opened", ev("email.opened"), "s"))


if __name__ == "__main__":
    unittest.main()
