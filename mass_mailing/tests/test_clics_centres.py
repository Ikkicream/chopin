"""Clics d'antivirus (21/10/2026) : une IP Microsoft, Google, Proofpoint… n'est jamais un humain."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.clics import _CENTRES  # noqa: E402


class Centres(unittest.TestCase):
    def test_antivirus_reconnus(self):
        for org in ("MSFT Microsoft Corporation", "Google LLC", "Amazon Technologies Inc.", "Proofpoint, Inc."):
            self.assertTrue(_CENTRES.search(org), org)

    def test_fai_francais_restent_humains(self):
        for org in ("Orange S.A. FR-ORANGE", "Free SAS PROXAD", "SFR SA", "Bouygues Telecom"):
            self.assertFalse(_CENTRES.search(org), org)


if __name__ == "__main__":
    unittest.main()
