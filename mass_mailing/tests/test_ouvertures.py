"""Qui ouvre vraiment (20/10/2026) : cas relevés sur Kick off Zylio. Fonctions pures, sans base ni réseau."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import ouvertures as o  # noqa: E402
from jobs import bilan_campagnes as b  # noqa: E402

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
EDGE12 = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 "
          "Safari/537.36 Edge/12.246 Mozilla/5.0")


class TestClasser(unittest.TestCase):
    def test_antivirus_microsoft(self):
        self.assertEqual(o.classer("MSFT Microsoft Corporation (MSFT)", CHROME)[0], o.MACHINE)

    def test_scanner_google(self):
        self.assertEqual(o.classer("GOOGLE Google LLC (GOGL)", EDGE12)[0], o.MACHINE)

    def test_proxy_images_gmail_humain(self):
        self.assertEqual(o.classer("GOOGLE Google LLC (GOGL)", "Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 (via ggpht.com GoogleImageProxy)")[0], o.HUMAIN)

    def test_outlook_bureau_humain(self):
        self.assertEqual(o.classer("", "Mozilla/4.0 (compatible; ms-office; MSOffice 16)")[0], o.HUMAIN)

    def test_box_orange_humain(self):
        self.assertEqual(o.classer("FR-TELECOM-20051230 Orange S.A.", CHROME)[0], o.HUMAIN)

    def test_apple_mail(self):
        self.assertEqual(o.classer("CLOUDFLAREWARP", "Mozilla/5.0")[0], o.APPLE)

    def test_destinataire_humain_si_une_ouverture_humaine(self):
        self.assertEqual(o.verdict_destinataire([o.MACHINE, o.HUMAIN]), o.HUMAIN)
        self.assertEqual(o.verdict_destinataire([o.MACHINE, o.APPLE]), o.APPLE)


class TestAlertes(unittest.TestCase):
    def test_taux_brut_qui_ment(self):
        z = {"envoyes": 472, "livres": 471, "hard": 0, "plaintes": 0, "desinscrits": 0, "ouverts_brut": 138, "ouverts_rapides": 89}
        self.assertEqual(len(b.alertes(z)), 1)

    def test_campagne_saine(self):
        z = {"envoyes": 100, "livres": 100, "hard": 1, "plaintes": 0, "desinscrits": 0, "ouverts_brut": 10, "ouverts_rapides": 1}
        self.assertEqual(b.alertes(z), [])


if __name__ == "__main__":
    unittest.main()
