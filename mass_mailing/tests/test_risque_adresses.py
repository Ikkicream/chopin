"""Agent « adresses à risque » (jobs/risque_adresses.py) — fonctions pures.
Lancer : python3 -m unittest tests.test_risque_adresses -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.risque_adresses import auc, entrainer, facteurs, niveau, probabilite  # noqa: E402


def donnees():
    d = []
    for i in range(300):
        d.append((facteurs(f"a{i}@gmail.com", "VALID/SAFE"), 0))
        d.append((facteurs(f"b{i}@laposte.net", None), 1 if i % 3 == 0 else 0))
    for i in range(50):
        d.append((facteurs(f"c{i}@yahoo.fr", "VALID/SAFE"), 1 if i % 10 == 0 else 0))
    return d


class Risque(unittest.TestCase):
    def test_angle_mort_yahoo(self):
        self.assertEqual(facteurs("x@yahoo.fr", "VALID/SAFE")["mailnjoy"], "VALID/SAFE·yahoo")
        self.assertEqual(facteurs("x@aol.com", "VALID/SAFE")["mailnjoy"], "VALID/SAFE·yahoo")
        self.assertEqual(facteurs("x@gmail.com", "VALID/SAFE")["mailnjoy"], "VALID/SAFE")
        self.assertEqual(facteurs("x@gmail.com", None)["mailnjoy"], "non_verifie")

    def test_ordre_des_risques(self):
        m = entrainer(donnees())
        p = lambda e, v: probabilite(m, facteurs(e, v))[0]  # noqa: E731
        self.assertLess(p("z@gmail.com", "VALID/SAFE"), p("z@yahoo.fr", "VALID/SAFE"))
        self.assertLess(p("z@yahoo.fr", "VALID/SAFE"), p("z@laposte.net", None))

    def test_niveaux(self):
        self.assertEqual([niveau(x) for x in (0.01, 0.1, 0.2, 0.5)], ["faible", "moyen", "eleve", "tres_eleve"])

    def test_auc(self):
        self.assertEqual(auc([(0.1, 0), (0.2, 0), (0.8, 1), (0.9, 1)]), 1.0)
        self.assertEqual(auc([(0.9, 0), (0.1, 1)]), 0.0)
        self.assertEqual(auc([(0.5, 0), (0.5, 1)]), 0.5)          # ex æquo (revue du 30/09)

    def test_multiplicateur_minuscule_ne_plante_pas(self):
        m = {"a_priori": 0.0, "poids": {"domaine": {"gmail.com": -9.0}, "messagerie": {}, "mailnjoy": {}}}
        p, eff = probabilite(m, facteurs("x@gmail.com", None))
        self.assertLess(p, 0.001)
        self.assertEqual(eff[0][0], "domaine = gmail.com")


if __name__ == "__main__":
    unittest.main()
