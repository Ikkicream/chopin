"""Tests du pilotage adaptatif (jobs/capacite.py) — fonctions pures, aucune écriture en base.
Lancer depuis genesis/mass_mailing :  python3 -m unittest tests.test_capacite -v"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.capacite import analyser_evenement, classer_reponse, decider, groupe_de  # noqa: E402

M0 = {"tentes": 0, "acceptes": 0, "differes": 0, "rebonds": 0, "limites": 0, "critiques": 0, "plaintes": 0}
AUJ = date(2026, 9, 28)


def m(**k):
    return {**M0, **k}


class Taxonomie(unittest.TestCase):
    def test_classes(self):
        cas = [
            ("accepted", 250, "250 2.0.0 OK", "accepted"),
            ("deferred", 421, "421 4.7.28 Our system has detected an unusual rate", "transient_rate_limit"),
            ("deferred", 451, "451 4.7.650 The mail server has been temporarily rate limited", "transient_rate_limit"),
            ("deferred", 421, "421 4.7.0 [TS04] Messages from x temporarily deferred", "transient_rate_limit"),
            ("deferred", 452, "452 4.2.2 The email account is over quota", "transient_mailbox_full"),
            ("deferred", 450, "450 greylisted, try again in 5 minutes", "transient_greylisting"),
            ("deferred", 421, "421 Service not available", "transient_server_busy"),
            ("hard_bounce", 550, "550 5.1.1 The email account does not exist", "permanent_invalid_recipient"),
            ("hard_bounce", 550, "550 5.7.26 Unauthenticated email is not accepted (DMARC)", "permanent_authentication"),
            ("hard_bounce", 550, "550 5.7.1 Message rejected as spam", "permanent_policy_or_spam"),
            ("hard_bounce", 550, "550 5.7.515 Access denied", "permanent_policy_or_spam"),
            ("hard_bounce", 550, "550 OFR_506 [506] Mail refused", "permanent_policy_or_spam"),
            ("hard_bounce", 554, "554 something odd", "permanent_unknown"),
            # Cas réels du 26/09 : Sweego étiquette « hard_bounce » un 451 de Microsoft (S3115).
            ("hard_bounce", 451, "451 4.7.652 The mail server [185.255.28.17] has exceeded the maximum number of connections. (S3115)", "transient_rate_limit"),
            ("hard_bounce", 554, "554 30 Sorry, your message cannot be delivered. This mailbox is disabled (554.30).", "permanent_invalid_recipient"),
        ]
        for etat, code, texte, attendu in cas:
            self.assertEqual(classer_reponse(etat, code, texte), attendu, texte)

    def test_groupes(self):
        self.assertEqual(groupe_de("wanadoo.fr"), "orange")
        self.assertEqual(groupe_de("live.fr"), "microsoft")
        self.assertEqual(groupe_de("aol.com"), "yahoo")
        self.assertEqual(groupe_de("bnpparibas.com"), "autres")

    def test_evenement_sweego_reel(self):
        p = {"event_id": "e1", "timestamp": "2026-09-26T14:48:37+00:00", "domain_from": "news.leclientroi.email",
             "campaign_type": "market", "recipient": "x@wanadoo.fr",
             "details": "Sep 26 14:48:37 prod-mta-12 zone-mta: info Sender/orange/2036567[1] id=a ACCEPTED from=b@swg.news.leclientroi.email "
                        "to=x@wanadoo.fr src=185.255.28.17 mx=smtp-in2.orange.fr[80.12.24.83] id=<c> (250 2.0.0 OK queued)"}
        r = analyser_evenement("delivered", p)
        self.assertEqual((r["sending_ip"], r["zone_sweego"], r["mx"], r["etat"], r["categorie"]),
                         ("185.255.28.17", "orange", "smtp-in2.orange.fr", "accepted", "accepted"))
        self.assertIsNone(analyser_evenement("email_opened", p))


class Decisions(unittest.TestCase):
    E = {"debit_heure": 40, "plafond_jour": 100, "derniere_hausse": None, "jour_chauffe": 2, "groupe": "laposte", "etat": "warming"}

    def test_echantillon_insuffisant(self):
        d = decider(self.E, m(), m(tentes=5, acceptes=5), AUJ)
        self.assertEqual(d["decision"], "maintenir")

    def test_sain_augmente_une_fois_par_jour(self):
        d = decider(self.E, m(tentes=5, acceptes=5), m(tentes=40, acceptes=40), AUJ)
        self.assertEqual((d["decision"], round(d["debit"])), ("augmenter", 44))
        d2 = decider({**self.E, "derniere_hausse": AUJ}, m(tentes=5, acceptes=5), m(tentes=40, acceptes=40), AUJ)
        self.assertEqual(d2["decision"], "maintenir")

    def test_limitation_divise_par_deux(self):
        d = decider(self.E, m(tentes=20, acceptes=18, differes=2, limites=1), m(tentes=40, acceptes=38), AUJ)
        self.assertEqual((d["decision"], d["etat"], d["debit"]), ("reduire", "throttled", 20.0))

    def test_rebonds_durs_prudence(self):
        d = decider(self.E, m(), m(tentes=50, acceptes=47, rebonds=3), AUJ)
        self.assertEqual((d["decision"], d["etat"]), ("reduire", "cautious"))

    def test_periode_observation_apres_baisse(self):
        from datetime import datetime, timedelta, timezone
        t = datetime(2026, 9, 28, 10, tzinfo=timezone.utc)
        e = {**self.E, "dernier_reduit": t - timedelta(hours=2)}
        d = decider(e, m(), m(tentes=50, acceptes=47, rebonds=3), AUJ, t)
        self.assertEqual((d["decision"], d["debit"]), ("maintenir", 40.0))   # rebonds : 1 baisse / 24 h
        d = decider(e, m(tentes=20, limites=1), m(tentes=40), AUJ, t)
        self.assertEqual(d["decision"], "reduire")                            # freinage : 1 baisse / h
        d = decider({**self.E, "dernier_reduit": t - timedelta(minutes=20)}, m(tentes=20, limites=1), m(tentes=40), AUJ, t)
        self.assertEqual(d["decision"], "maintenir")

    def test_politique_suspend(self):
        d = decider(self.E, m(), m(tentes=50, acceptes=48, rebonds=2, critiques=2), AUJ)
        self.assertEqual((d["decision"], d["etat"]), ("suspendre", "paused"))

    def test_plaintes_suspend(self):
        d = decider(self.E, m(), m(tentes=500, acceptes=500, plaintes=2), AUJ)
        self.assertEqual(d["etat"], "paused")


class Reprise(unittest.TestCase):
    """30/09 : une file en pause sans envoi restait en pause pour toujours (« échantillon insuffisant »)."""
    from datetime import datetime, timedelta, timezone
    T = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
    E = {"debit_heure": 48, "plafond_jour": 121, "derniere_hausse": None, "jour_chauffe": 3, "groupe": "orange", "etat": "paused"}

    def test_reste_en_pause_avant_48h(self):
        d = decider({**self.E, "derniere_suspension": self.T - self.timedelta(hours=29)}, m(), m(), AUJ, self.T)
        self.assertEqual((d["decision"], d["etat"]), ("maintenir", "paused"))

    def test_reprise_apres_48h_debit_divise_par_deux(self):
        d = decider({**self.E, "derniere_suspension": self.T - self.timedelta(hours=49)}, m(), m(), AUJ, self.T)
        self.assertEqual((d["decision"], d["etat"], d["debit"]), ("reprendre", "recovery", 24.0))

    def test_nouvelle_plainte_repasse_en_pause(self):
        d = decider({**self.E, "derniere_suspension": self.T - self.timedelta(hours=49)}, m(), m(tentes=10, acceptes=10, plaintes=1), AUJ, self.T)
        self.assertEqual(d["decision"], "suspendre")


if __name__ == "__main__":
    unittest.main()
