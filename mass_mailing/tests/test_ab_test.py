"""Tests du scoring de l'A/B test (jobs/ab_test.py) — fonction pure, aucune écriture en base.

Lancer depuis genesis/mass_mailing :  python3 -m unittest tests.test_ab_test -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.ab_test import repartir, scorer  # noqa: E402


def m(livres, ouverts=0, cliques=0, desinscrits=0, plaintes=0, rebonds=0):
    return {"echantillon": livres, "envoyes": livres, "en_file": 0, "livres": livres, "ouverts": ouverts,
            "cliques": cliques, "desinscrits": desinscrits, "plaintes": plaintes, "rebonds": rebonds}


class ScoringAB(unittest.TestCase):
    def test_meilleur_taux_ouverture_gagne(self):
        s = scorer({"A": m(150, ouverts=45), "B": m(150, ouverts=60)}, "ouverture")
        self.assertEqual(s["gagnant"], "B")
        self.assertEqual(s["variantes"]["B"]["taux_ouverture"], 40.0)

    def test_critere_clic(self):
        s = scorer({"A": m(150, ouverts=80, cliques=2), "B": m(150, ouverts=50, cliques=9)}, "clic")
        self.assertEqual(s["gagnant"], "B")

    def test_plaintes_penalisent(self):
        # B ouvre un peu plus mais déclenche 2 plaintes : ×5 chacune → A l'emporte.
        s = scorer({"A": m(150, ouverts=60), "B": m(150, ouverts=64, plaintes=2)}, "ouverture")
        self.assertEqual(s["gagnant"], "A")

    def test_egalite_departagee_par_autre_critere(self):
        # B passe en tête grâce aux clics, mais sur le critère les taux sont égaux : pas de
        # gagnant net au seuil de 90 %, on garde A.
        s = scorer({"A": m(100, ouverts=30, cliques=1), "B": m(100, ouverts=30, cliques=4)}, "ouverture")
        self.assertEqual(s["en_tete"], "B")
        self.assertEqual(s["gagnant"], "A")
        self.assertFalse(s["net"])

    def test_egalite_parfaite_garde_A(self):
        s = scorer({"A": m(100, ouverts=30), "B": m(100, ouverts=30)}, "ouverture")
        self.assertEqual(s["gagnant"], "A")

    def test_confiance(self):
        fort = scorer({"A": m(150, ouverts=30), "B": m(150, ouverts=75)}, "ouverture")
        faible = scorer({"A": m(150, ouverts=45), "B": m(150, ouverts=48)}, "ouverture")
        self.assertTrue(fort["significatif"])
        self.assertFalse(faible["significatif"])

    def test_seuil_90_pas_de_gagnant_net(self):
        s = scorer({"A": m(150, ouverts=10), "B": m(150, ouverts=13)}, "ouverture")
        self.assertEqual(s["en_tete"], "B")
        self.assertEqual(s["gagnant"], "A")
        self.assertFalse(s["net"])
        self.assertIn("pas de gagnant net", s["departage"])

    def test_seuil_90_gagnant_net(self):
        s = scorer({"A": m(150, ouverts=10), "B": m(150, ouverts=25)}, "ouverture")
        self.assertGreaterEqual(s["confiance"], 90)
        self.assertEqual(s["gagnant"], "B")
        self.assertTrue(s["net"])

    def test_rien_parti(self):
        s = scorer({"A": m(0), "B": m(0)}, "clic")
        self.assertEqual(s["gagnant"], "A")



class SuiteAB(unittest.TestCase):
    """21/10/2026 : pendant le test, le reste de la file part aussi, moitié A, moitié B."""

    def test_rattrape_la_version_en_retard(self):
        # Zylio : A 149, B 158 déjà dans le test → les 9 premiers vont à A, puis alternance.
        v = repartir(13, {"A": 149, "B": 158})
        self.assertEqual(v[:9], ["A"] * 9)
        self.assertEqual(sorted(v[9:]), ["A", "A", "B", "B"])

    def test_parts_egales(self):
        v = repartir(3133, {"A": 0, "B": 0})
        self.assertEqual(abs(v.count("A") - v.count("B")), 1)


if __name__ == "__main__":
    unittest.main()
