"""Fenêtre d'envoi et étalement (13/10/2026)."""
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.envoi import dans_fenetre, part_de_la_journee, prochaine_ouverture  # noqa: E402

P = ZoneInfo("Europe/Paris")
F = {"debut": 9, "fin": 18, "jours": [1, 2, 3, 4, 5], "etale": True}


class TestFenetre(unittest.TestCase):
    def test_dans_fenetre(self):
        self.assertTrue(dans_fenetre(F, datetime(2026, 10, 14, 9, 0, tzinfo=P)))        # mercredi 9h
        self.assertFalse(dans_fenetre(F, datetime(2026, 10, 14, 18, 0, tzinfo=P)))      # 18h : fini
        self.assertFalse(dans_fenetre(F, datetime(2026, 10, 17, 10, 0, tzinfo=P)))      # samedi

    def test_prochaine_ouverture(self):
        self.assertEqual(prochaine_ouverture(F, datetime(2026, 10, 13, 20, 30, tzinfo=P)),
                         datetime(2026, 10, 14, 9, 2, tzinfo=P))                         # mardi soir → mercredi 9h02
        self.assertEqual(prochaine_ouverture(F, datetime(2026, 10, 16, 19, 0, tzinfo=P)),
                         datetime(2026, 10, 19, 9, 2, tzinfo=P))                         # vendredi soir → lundi
        self.assertEqual(prochaine_ouverture(F, datetime(2026, 10, 14, 7, 0, tzinfo=P)),
                         datetime(2026, 10, 14, 9, 2, tzinfo=P))                         # tôt → même jour 9h02

    def test_etalement(self):
        self.assertAlmostEqual(part_de_la_journee(F, datetime(2026, 10, 14, 9, 10, tzinfo=P)), 1 / 9)
        self.assertEqual(part_de_la_journee(F, datetime(2026, 10, 14, 17, 30, tzinfo=P)), 1.0)
        self.assertEqual(part_de_la_journee({**F, "etale": False}, datetime(2026, 10, 14, 9, 10, tzinfo=P)), 1.0)


if __name__ == "__main__":
    unittest.main()
