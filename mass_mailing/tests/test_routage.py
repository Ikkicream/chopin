"""Tests de l'agent de routage (jobs/routage.py) — fonction pure planifier().
Lancer depuis genesis/mass_mailing :  python3 -m unittest tests.test_routage -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.routage import exclusions_auto, planifier, taux_lisse  # noqa: E402

CAP = {"orange": {"debit_heure": 44, "restant_jour": 110, "etat": "warming"},
       "laposte": {"debit_heure": 40, "restant_jour": 100, "etat": "warming"},
       "gmail": {"debit_heure": 115, "restant_jour": 345, "etat": "warming"},
       "microsoft": {"debit_heure": 55, "restant_jour": 165, "etat": "warming"},
       "yahoo": {"debit_heure": 35, "restant_jour": 100, "etat": "paused"}}
TAUX = {"orange": taux_lisse(8, 36), "laposte": taux_lisse(2, 10), "gmail": taux_lisse(0, 97), "microsoft": taux_lisse(1, 108), "yahoo": 0.0}


class Plan(unittest.TestCase):
    def test_priorite_aux_ouvreurs(self):
        p = {x["groupe"]: x for x in planifier({"orange": 216, "laposte": 64, "gmail": 644, "microsoft": 814, "yahoo": 195}, TAUX, CAP, 0.3)}
        self.assertEqual(p["orange"]["priorite"], 1)
        self.assertEqual(p["orange"]["volume"], 44)          # débit plein
        self.assertEqual(p["laposte"]["volume"], 40)
        self.assertEqual(p["gmail"]["priorite"], 2)
        self.assertEqual(p["gmail"]["volume"], 34)           # 30 % de 115
        self.assertEqual(p["microsoft"]["volume"], 16)       # 30 % de 55
        self.assertEqual(p["yahoo"]["volume"], 0)            # en pause

    def test_reste_du_jour_borne(self):
        cap = {**CAP, "orange": {"debit_heure": 44, "restant_jour": 10, "etat": "warming"}}
        p = {x["groupe"]: x for x in planifier({"orange": 216}, TAUX, cap, 0.3)}
        self.assertEqual(p["orange"]["volume"], 10)

    def test_plus_de_priorite_1_les_non_ouvreurs_restent_a_part_basse(self):
        # D (27/09) : Gmail et Outlook n'ouvrent pas → toujours 30 %, même priorité 1 épuisée.
        p = {x["groupe"]: x for x in planifier({"gmail": 644, "microsoft": 814}, TAUX, CAP, 0.3)}
        self.assertEqual((p["gmail"]["volume"], p["microsoft"]["volume"]), (34, 16))

    def test_plus_de_priorite_1_ouvreur_moyen_a_plein(self):
        taux = {**TAUX, "gmail": 0.04}
        p = {x["groupe"]: x for x in planifier({"gmail": 644, "microsoft": 814}, taux, CAP, 0.3)}
        self.assertEqual((p["gmail"]["volume"], p["microsoft"]["volume"]), (115, 16))

    def test_messagerie_exclue(self):
        cap = {**CAP, "yahoo": {"debit_heure": 35, "restant_jour": 100, "etat": "cautious"}}
        p = {x["groupe"]: x for x in planifier({"orange": 10, "yahoo": 185}, TAUX, cap, 0.3, {"yahoo": "revalidation"})}
        self.assertEqual((p["yahoo"]["volume"], p["yahoo"]["priorite"]), (0, 0))
        self.assertIn("revalidation", p["yahoo"]["raison"])

    def test_jamais_plus_que_restant(self):
        p = {x["groupe"]: x for x in planifier({"laposte": 7}, TAUX, CAP, 0.3)}
        self.assertEqual(p["laposte"]["volume"], 7)


class Exclusion(unittest.TestCase):
    def test_yahoo_cas_reel(self):
        self.assertIn("yahoo", exclusions_auto({"yahoo": (10, 2), "orange": (110, 0)}, {}))

    def test_petit_echantillon_ou_deja_exclu(self):
        self.assertEqual(exclusions_auto({"gmx": (2, 1), "yahoo": (10, 2)}, {"yahoo": "manuel"}), {})

    def test_sous_le_seuil(self):
        self.assertEqual(exclusions_auto({"gmail": (136, 1)}, {}), {})


if __name__ == "__main__":
    unittest.main()
