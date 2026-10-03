"""Réputation d'envoi : les listes de réseau entier (UCEPROTECT 2/3) ne bloquent pas (30/09/2026).
Lancer : python3 -m unittest tests.test_reputation -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra.hetrix import etat_moniteur  # noqa: E402


class Etat(unittest.TestCase):
    def test_uceprotect_3_seul_non_bloquant(self):
        m = {"listee": True, "listes": [{"rbl": "dnsbl-3.uceprotect.net"}]}
        self.assertEqual(etat_moniteur(m), "reseau")

    def test_uceprotect_1_bloquant(self):
        self.assertEqual(etat_moniteur({"listee": True, "listes": [{"rbl": "dnsbl-1.uceprotect.net"}]}), "listee")

    def test_spamhaus_avec_uceprotect_3_bloquant(self):
        m = {"listee": True, "listes": [{"rbl": "dnsbl-3.uceprotect.net"}, {"rbl": "zen.spamhaus.org"}]}
        self.assertEqual(etat_moniteur(m), "listee")

    def test_propre_et_absent(self):
        self.assertEqual(etat_moniteur({"listee": False, "listes": []}), "propre")
        self.assertEqual(etat_moniteur(None), "non_surveille")


if __name__ == "__main__":
    unittest.main()
