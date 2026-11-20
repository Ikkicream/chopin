"""Agent d'apprentissage du message (13/10/2026) : même clé de problème des deux côtés."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import controle_html  # noqa: E402
from jobs.apprentissage import cle_probleme, expressions  # noqa: E402


class TestApprentissage(unittest.TestCase):
    def test_cle_identique_note(self):
        controle_html._APPRIS.update(t=10**12, poids={}, mots=[])   # pas de base : poids par défaut
        html = "<html><body><p>Bonjour {{Prenom}}, 3 offres !!!</p></body></html>"
        a = controle_html.analyser(html, objet="Test", preheader="", expediteur={"adresse_postale": "x"}, tester_liens=False)
        bloquant = next(p for p in a["problemes"] if p["niveau"] == "bloquant")
        cle = cle_probleme(bloquant)
        # Un poids appris pour CETTE clé doit changer la note : preuve que les clés concordent.
        controle_html._APPRIS.update(t=10**12, poids={cle: 15.0}, mots=[])
        b = controle_html.analyser(html, objet="Test", preheader="", expediteur={"adresse_postale": "x"}, tester_liens=False)
        self.assertEqual(b["score"], a["score"] + 10)

    def test_cle_sans_nombres(self):
        self.assertEqual(cle_probleme({"categorie": "Liens", "message": "3 lien(s) mort(s)."}),
                         cle_probleme({"categorie": "Liens", "message": "12 lien(s) mort(s)."}))

    def test_expressions(self):
        e = expressions("Offre SANS engagement, résiliable à tout moment")
        self.assertIn("sans engagement", e)
        self.assertIn("resiliable", e)
        self.assertNotIn("a", e)

    def test_mot_appris_signale(self):
        controle_html._APPRIS.update(t=10**12, poids={}, mots=["devis gratuit"])
        a = controle_html.analyser("<p>Votre devis gratuit en 2 minutes</p>", objet="x", preheader="",
                                   expediteur={"adresse_postale": "x"}, tester_liens=False)
        self.assertTrue(any(p["categorie"] == "Apprentissage" for p in a["problemes"]))


if __name__ == "__main__":
    unittest.main()
