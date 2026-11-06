"""Compteur d'envois du superadmin (21/10/2026) : jour, semaine (lundi) et mois comptés À PARIS."""
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra.compteur_envois import bornes  # noqa: E402

UTC = ZoneInfo("UTC")


class Bornes(unittest.TestCase):
    def test_mercredi_midi(self):
        b = bornes(datetime(2026, 10, 21, 10, 0, tzinfo=UTC))
        self.assertEqual((b["jour"].day, b["semaine"].day, b["mois"].day), (21, 19, 1))

    def test_minuit_paris_change_de_jour_avant_utc(self):
        # 22/10 à 0 h 30 à Paris = 21/10 22 h 30 UTC : c'est déjà le 22.
        b = bornes(datetime(2026, 10, 21, 22, 30, tzinfo=UTC))
        self.assertEqual(b["jour"].day, 22)

    def test_dimanche_reste_dans_la_semaine(self):
        b = bornes(datetime(2026, 10, 25, 12, 0, tzinfo=UTC))
        self.assertEqual(b["semaine"].day, 19)


if __name__ == "__main__":
    unittest.main()
