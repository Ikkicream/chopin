"""Resend : 429 de débit rejoué (pas de report au lendemain) et clics rangés via l'anti-robots (20/10/2026).

Rien ne part sur le réseau ni en base : requests.post, pg et clics.classer sont remplacés."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import resend  # noqa: E402
from jobs import clics, resend_webhook  # noqa: E402


class Rep:
    def __init__(self, code, texte="", entetes=None):
        self.status_code, self.text, self.headers = code, texte, entetes or {}
        self.content = texte.encode()

    def json(self):
        import json
        return json.loads(self.text)


DEBIT = '{"name":"rate_limit_exceeded","statusCode":429,"message":"Too many requests"}'
QUOTA = '{"name":"daily_quota_exceeded","statusCode":429,"message":"quota"}'


def envoyer():
    return resend.envoyer_un(destinataire="jean@example.fr", subject="Objet", html_str="<p>x</p>", texte="x",
                             expediteur={"from_name": "Zylio", "from_email": "hello@news.zylio.email",
                                         "tenant": "zylio", "campaign_type": "market"},
                             campagne="mm-test", url_desinscription="https://exemple.fr/u")


class TestDebit(unittest.TestCase):
    def setUp(self):
        for cible, val in (("configure", True), ("valider_corps", [])):
            p = mock.patch.object(resend, cible, return_value=val)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(resend.time, "sleep")
        self.dodo = p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(resend, "_headers", return_value={})
        p.start()
        self.addCleanup(p.stop)

    def test_429_debit_rejoue_puis_ok(self):
        with mock.patch.object(resend.requests, "post",
                               side_effect=[Rep(429, DEBIT, {"retry-after": "1"}), Rep(200, '{"id":"abc"}')]) as post:
            r = envoyer()
        self.assertTrue(r["ok"])
        self.assertEqual(post.call_count, 2)

    def test_429_debit_persistant_signale_debit(self):
        with mock.patch.object(resend.requests, "post", return_value=Rep(429, DEBIT)) as post:
            r = envoyer()
        self.assertEqual(post.call_count, resend.ESSAIS_429)
        self.assertTrue(r["debit"])
        self.assertFalse(r["quota"])

    def test_429_quota_pas_rejoue(self):
        with mock.patch.object(resend.requests, "post", return_value=Rep(429, QUOTA)) as post:
            r = envoyer()
        self.assertEqual(post.call_count, 1)
        self.assertTrue(r["quota"])
        self.assertFalse(r["debit"])


class TestClicResend(unittest.TestCase):
    def test_clic_va_dans_clicks_puis_classer(self):
        envoye = datetime(2026, 10, 21, 7, 2, tzinfo=timezone.utc)
        ecrits = []
        with mock.patch.object(resend_webhook.pg, "ligne",
                               return_value={"id": 7, "campaign_id": "c-1", "submitted_at": envoye}), \
             mock.patch.object(resend_webhook.pg, "ecrire", side_effect=lambda sql, p=None: ecrits.append((sql, p)) or 1), \
             mock.patch.object(clics, "classer", return_value={"humain": 1, "robot": 0, "suspect": 0}) as classer:
            effet = resend_webhook._ranger_clic(
                {"click": {"ipAddress": "1.2.3.4", "link": "https://zylio.email/essai",
                           "timestamp": "2026-10-21T07:12:00.000Z", "userAgent": "Mozilla/5.0"}}, "abc", "msg_1")
        sql, p = ecrits[0]
        self.assertIn("INSERT INTO clicks", sql)
        self.assertNotIn("clicked_at = COALESCE", sql)          # jamais de clic posé en direct
        self.assertEqual((p["ev"], p["r"], p["ip"], p["t"], p["d"]), ("resend:msg_1", 7, "1.2.3.4", "contenu", 600))
        classer.assert_called_once_with("c-1")
        self.assertIn("1 humain", effet)

    def test_lien_piege_reconnu(self):
        self.assertEqual(clics._type_lien("https://mail.cheffer.email" + clics.CHEMIN_PIEGE + "?x=1"), "piege")


if __name__ == "__main__":
    unittest.main()
