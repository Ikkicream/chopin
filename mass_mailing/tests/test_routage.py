"""Tests de l'agent de routage (jobs/routage.py) — fonction pure planifier().
Lancer depuis genesis/mass_mailing :  python3 -m unittest tests.test_routage -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.routage import choisir, domaines_a_bloquer, exclusions_auto, plafond_domaine, plafonds_equilibre, planifier, taux_lisse  # noqa: E402

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


class PlafondDomaine(unittest.TestCase):
    """21/10/2026 : 456 mails Gmail en un après-midi. Jamais plus de 10 % d'une vague par domaine."""

    def test_plafond(self):
        self.assertEqual(plafond_domaine(88), 8)
        self.assertEqual(plafond_domaine(5), 1)

    def test_gmail_un_seul_domaine_borne_le_reste_va_aux_autres(self):
        cand = {"gmail": [(i, "gmail.com") for i in range(100)],
                "autres": [(1000 + i, f"agence{i}.fr") for i in range(200)]}
        pris = choisir(cand, {"gmail": 88, "autres": 0}, {"gmail": 100, "autres": 100}, ["gmail", "autres"])
        self.assertEqual(len(pris["gmail"]), 8)
        self.assertEqual(len(pris["gmail"]) + len(pris["autres"]), 88)

    def test_aucun_domaine_au_dela(self):
        cand = {"autres": [(i, "orpi.com" if i % 2 else f"d{i}.fr") for i in range(300)]}
        pris = choisir(cand, {"autres": 80}, {"autres": 100}, ["autres"])["autres"]
        self.assertEqual(sum(1 for i in pris if i % 2), 8)
        self.assertEqual(len(pris), 80)

    def test_jamais_au_dela_de_la_capacite(self):
        cand = {"gmail": [(i, "gmail.com") for i in range(50)], "orange": [(100 + i, "orange.fr") for i in range(50)]}
        pris = choisir(cand, {"gmail": 40, "orange": 40}, {"gmail": 40, "orange": 40}, ["gmail", "orange"])
        # Deux domaines seulement : aucune vague ne peut tenir 10 % par domaine au-delà d'1 mail
        # chacun (règle de Camille, appliquée sur la vague RÉELLE depuis le 22/10/2026).
        self.assertEqual((len(pris["gmail"]), len(pris["orange"])), (1, 1))



class MoteurComplet(unittest.TestCase):
    """21/10/2026 : spam probable → sonde, équilibre entre files, domaines coupés."""

    def test_spam_probable_en_sonde(self):
        pl = {"gmail": {"etat": "spam_probable", "motif": "0,4 % contre 5,8 %"}}
        taux = {"gmail": 0.18, "orange": 0.10}
        p = {x["groupe"]: x for x in planifier({"gmail": 500, "orange": 100}, taux, CAP, 0.3, None, pl)}
        self.assertEqual(p["gmail"]["volume"], 2)
        self.assertEqual(p["gmail"]["priorite"], 2)
        self.assertIn("SONDE", p["gmail"]["raison"])
        self.assertTrue(p["gmail"]["sonde"])
        self.assertEqual(p["orange"]["priorite"], 1)

    def test_equilibre(self):
        pl = plafonds_equilibre({"autres": 2000, "orange": 150, "gmail": 50}, 88)
        self.assertEqual(pl["orange"], 12)      # 2 × 6,8 % de 88, arrondi au-dessus
        self.assertEqual(pl["gmail"], 4)
        cand = {"orange": [(i, f"o{i}.fr") for i in range(50)], "autres": [(100 + i, f"d{i}.fr") for i in range(200)]}
        pris = choisir(cand, {"orange": 40, "autres": 48}, {"orange": 40, "autres": 100}, ["orange", "autres"], pl)
        self.assertEqual(len(pris["orange"]), 12)

    def test_plafond_sur_la_vague_reelle(self):
        # Vague prévue à 120 mais seulement 30 candidats dont 20 du même domaine : 10 % de la vague RÉELLE.
        cand = {"autres": [(i, "wanadoo.fr") for i in range(20)] + [(100 + i, f"d{i}.fr") for i in range(10)]}
        pris = choisir(cand, {"autres": 120}, {"autres": 120}, ["autres"])["autres"]
        n_wanadoo = sum(1 for i in pris if i < 100)
        self.assertLessEqual(n_wanadoo, max(1, int(len(pris) * 0.10)), f"{n_wanadoo} sur {len(pris)}")

    def test_domaines_bloques(self):
        st = {"orpi.com": {"envoyes": 20, "rebonds": 3, "plaintes": 0}, "foncia.fr": {"envoyes": 80, "rebonds": 3, "plaintes": 0},
              "x.fr": {"envoyes": 2, "rebonds": 0, "plaintes": 1}}
        b = domaines_a_bloquer(st, {})
        self.assertEqual(set(b), {"orpi.com", "x.fr"})
        self.assertEqual(domaines_a_bloquer(st, b), {})
        cand = {"autres": [(1, "orpi.com"), (2, "a.fr"), (3, "b.fr")]}
        self.assertEqual(choisir(cand, {"autres": 3}, {"autres": 3}, ["autres"], None, {"orpi.com"})["autres"], [2, 3])


if __name__ == "__main__":
    unittest.main()
