"""Classement des rebonds Sweego (jobs/rebonds.py) — cas réels du 30/09/2026.
Lancer : python3 -m unittest tests.test_rebonds -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.rebonds import classer, origine_de  # noqa: E402

CAS = [
    ("(451 too many errors from your ip (185.255.28.17), please visit http://postmaster.free.fr/)", "451", "hard", ("expediteur", "trop_d_erreurs_ip")),
    ("(451 4.7.652 The mail server [185.255.28.17] has exceeded the maximum number of connections.)", "451 4.7.652", "hard", ("expediteur", "limite_debit")),
    ("(421 4.1.1 BXpE Service refuse. Veuillez essayer plus tard. OFR005_411 [411])", "421", "hard", ("expediteur", "service_refuse")),
    ("(550 5.1.1 <x@free.fr>: Recipient address rejected: User unknown)", "550 5.1.1", "hard", ("hard", "inconnue")),
    ("(550 5.5.0 Requested action not taken: mailbox unavailable (S2017062302))", "550 5.5.0", "hard", ("hard", "inconnue")),
    ("(554 30 Sorry, your message to a@yahoo.fr cannot be delivered. This mailbox is disabled (554.30).)", "554 30", "hard", ("hard", "desactivee")),
    ("(550 5.2.1 This mailbox has been blocked due to inactivity (UserSearch))", "550 5.2.1", "soft", ("hard", "bloquee_inactivite")),
    ("(552 5.2.2 <a@icloud.com>: user is over quota)", "552 5.2.2", "soft", ("soft", "boite_pleine")),
    ("(452-4.2.2 The recipient's inbox is out of storage space.)", "452 4.2.2", "soft", ("soft", "boite_pleine")),
    ("(450 4.2.1 <a@b.fr>: Recipient address rejected: this mailbox is inactive)", "450 4.2.1", "hard", ("soft", "boite_inactive")),
    ("info Queue 1a0e.001 DROP[suppressed] Recipient a@aol.com was found from suppression list", "-1", "hard", ("hard", "deja_supprimee")),
    ("(DNS Error: Failed to resolve any IP addresses for the Mail Exchange (MX) server associated with gmail.fr)", "", "hard", ("hard", "domaine_invalide")),
    ("Header x-campaign-tags : wrong tag value : ''", "550", None, ("technique", "erreur_technique")),
]


class Classement(unittest.TestCase):
    def test_cas_reels(self):
        for texte, code, ts, attendu in CAS:
            with self.subTest(texte=texte[:50]):
                self.assertEqual(classer(texte, code, ts), attendu)

    def test_revue_30_09(self):
        # Panne réseau vers un MX valide (citroen.fr, lyreco.fr…) : jamais une adresse morte.
        self.assertEqual(classer("REJECTED[network] Network error when connecting to MX server x for lyreco.fr: Connection timed out", "-1", "hard")[0], "technique")
        self.assertEqual(classer("(421 4.4.2 connection timed out)", "421", "hard")[0], "technique")
        # Une IP du journal ne doit pas passer pour le code 5.1.1.
        self.assertEqual(classer("mx=x[91.195.1.10] (550 5.7.1 message rejected due to local policy)", "550", "hard")[0], "expediteur")

    def test_4xx_jamais_adresse_morte(self):
        self.assertNotEqual(classer("(451 4.7.1 try again later)", "451", "hard")[0], "hard")

    def test_origine(self):
        self.assertEqual(origine_de("188.245.184.71", "default"), "plateforme_lcr")
        self.assertEqual(origine_de("0.0.0.0", "mm-902675d5"), "mass_email")


if __name__ == "__main__":
    unittest.main()
