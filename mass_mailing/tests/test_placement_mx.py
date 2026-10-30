"""Tests du placement probable (jobs/placement.py) et des familles de serveurs (infra/mx.py), 21/10/2026.
Lancer depuis genesis/mass_mailing :  python3 -m unittest tests.test_placement_mx -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra.mx import famille_de_mx  # noqa: E402
from jobs.placement import BOITE, INCONNU, SPAM, verdict_placement  # noqa: E402


class Placement(unittest.TestCase):
    def test_gmail_cas_reel(self):
        # 21/10 : 501 livrés, 2 vraies ouvertures, 5,8 % ailleurs.
        self.assertEqual(verdict_placement("gmail", 501, 2, 1, 0.058)[0], SPAM)

    def test_zero_humain(self):
        self.assertEqual(verdict_placement("google_pro", 60, 0, 0, None)[0], SPAM)

    def test_trop_peu(self):
        self.assertEqual(verdict_placement("yahoo", 28, 0, 0, 0.05)[0], INCONNU)

    def test_boite(self):
        self.assertEqual(verdict_placement("orange", 146, 17, 5, 0.023)[0], BOITE)

    def test_icloud_compte_apple(self):
        self.assertEqual(verdict_placement("icloud", 80, 0, 9, 0.05)[0], BOITE)


class DelaiOuverture(unittest.TestCase):
    """22/10/2026 : une « box » 17 s après la livraison = passerelle d'entreprise, pas une lectrice."""

    def test_delai(self):
        from infra.ouvertures import classer
        self.assertEqual(classer("FR-ORANGE France Telecom", "Mozilla/5.0 (Windows NT 10.0)", 17)[0], "machine")
        self.assertEqual(classer("FR-ORANGE France Telecom", "Mozilla/5.0 (Windows NT 10.0)", 2400)[0], "humain")
        self.assertEqual(classer("FR-ORANGE France Telecom", "Mozilla/5.0 (Windows NT 10.0)")[0], "humain")


class FamillesMx(unittest.TestCase):
    def test_familles(self):
        self.assertEqual(famille_de_mx("aspmx.l.google.com alt1.aspmx.l.google.com"), "google_pro")
        self.assertEqual(famille_de_mx("century21-fr.mail.protection.outlook.com"), "microsoft_pro")
        self.assertEqual(famille_de_mx("mx0a-00123.pphosted.com"), "passerelle")
        self.assertEqual(famille_de_mx("eu-smtp-inbound-1.mimecast.com"), "passerelle")
        self.assertEqual(famille_de_mx("mx1.mail.ovh.net"), "ovh")
        self.assertEqual(famille_de_mx("mx.agence.fr"), "autres")
        self.assertEqual(famille_de_mx(""), "autres")


if __name__ == "__main__":
    unittest.main()
