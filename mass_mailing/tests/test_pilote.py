"""Tests du pilote de chauffe (jobs/pilote.py) et de son branchement dans le plan de vague.
Lancer depuis genesis/mass_mailing :  python3 -m unittest tests.test_pilote -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs import placement  # noqa: E402
from jobs.pilote import (DEPART, EN_SONDE, ORANGE, PALIER_SANS_PREUVE, ROUGE, SONDE, SONDE_JOUR, SONDE_MAX, STOP,  # noqa: E402
                         VERT, juger, palier_suivant, sonde_par_vague)
from jobs.routage import choisir, planifier, plafonds_equilibre, restants_equilibre, taux_lisse  # noqa: E402

CAP = {"orange": {"debit_heure": 44, "restant_jour": 400, "etat": "warming"},
       "gmail": {"debit_heure": 186, "restant_jour": 798, "etat": "warming"},
       "laposte": {"debit_heure": 64, "restant_jour": 160, "etat": "warming"}}
TAUX = {"orange": taux_lisse(8, 36), "gmail": taux_lisse(0, 97), "laposte": taux_lisse(2, 10)}


class Controleur(unittest.TestCase):
    def test_sain(self):
        self.assertEqual(juger(placement.BOITE, 120, 1, 0, False)[0], VERT)

    def test_placement_inconnu_reste_vert(self):
        self.assertEqual(juger(placement.INCONNU, 30, 0, 0, False)[0], VERT)

    def test_plainte_nouvelle_recule(self):
        self.assertEqual(juger(placement.BOITE, 120, 0, 1, False)[0], ROUGE)

    def test_rebonds_forts_reculent(self):
        self.assertEqual(juger(placement.BOITE, 100, 4, 0, False)[0], ROUGE)

    def test_rebonds_sur_petit_echantillon_ignores(self):
        # 1 rebond sur 5 mails = 20 %, mais ça ne veut rien dire.
        self.assertEqual(juger(placement.INCONNU, 5, 1, 0, False)[0], VERT)

    def test_frein_du_fournisseur_on_tient(self):
        self.assertEqual(juger(placement.BOITE, 100, 0, 0, True)[0], ORANGE)

    def test_rebonds_moyens_on_tient(self):
        self.assertEqual(juger(placement.BOITE, 100, 3, 0, False)[0], ORANGE)

    def test_spam_probable_sonde(self):
        self.assertEqual(juger(placement.SPAM, 100, 0, 0, False, 20, 0)[0], EN_SONDE)

    def test_spam_persistant_reste_en_sonde_jamais_stop(self):
        # Camille, 27/11 : « minimum 20 emails par jour », jamais d'arrêt.
        v, motif = juger(placement.SPAM, 100, 0, 0, False, SONDE_MAX * 3, 0)
        self.assertEqual(v, EN_SONDE)
        self.assertIn("persistant", motif)

    def test_un_seul_signal_ne_suffit_pas(self):
        self.assertEqual(juger(placement.SPAM, 100, 0, 0, False, 30, 1)[0], EN_SONDE)

    def test_reprise_quand_la_sonde_montre_des_lecteurs(self):
        # Outlook sur Hall U Need A, 27/11 : 9 signaux sur 93 livrés en sonde.
        v, motif = juger(placement.SPAM, 100, 0, 0, False, 93, 9)
        self.assertEqual(v, VERT)
        self.assertIn("reprise", motif)

    def test_signaux_trop_dilues_restent_en_sonde(self):
        self.assertEqual(juger(placement.SPAM, 100, 0, 0, False, 200, 2)[0], EN_SONDE)

    def test_plainte_prime_sur_tout(self):
        self.assertEqual(juger(placement.SPAM, 100, 0, 1, True, SONDE_MAX, 0)[0], ROUGE)


class PlacementIcloud(unittest.TestCase):
    def test_un_prechargement_sur_96_c_est_du_spam(self):
        # Hall U Need A, 26/11 : 1 préchargement Apple sur 96 livrés.
        self.assertEqual(placement.verdict_placement("icloud", 96, 0, 1, 0.03)[0], placement.SPAM)

    def test_icloud_en_boite(self):
        self.assertEqual(placement.verdict_placement("icloud", 96, 2, 40, 0.03)[0], placement.BOITE)


class Producteur(unittest.TestCase):
    def test_premiere_vague(self):
        self.assertEqual(palier_suivant(None, None, VERT, None, False), DEPART)

    def test_croissance_exponentielle_quand_la_boite_est_prouvee(self):
        p, suite = DEPART, []
        for _ in range(8):
            p = palier_suivant(p, p, VERT, VERT, True)
            suite.append(p)
        self.assertEqual(suite, [8, 12, 18, 27, 41, 62, 93, 140])

    def test_sans_preuve_plafonne(self):
        p = DEPART
        for _ in range(20):
            p = palier_suivant(p, p, VERT, VERT, False)
        self.assertEqual(p, PALIER_SANS_PREUVE)

    def test_croit_depuis_ce_qui_est_parti(self):
        # Palier 40 mais seulement 10 partis (réserve, capacité) : on ne gonfle pas un palier fictif.
        self.assertEqual(palier_suivant(40, 10, VERT, VERT, True), 15)

    def test_orange_tient(self):
        self.assertEqual(palier_suivant(27, 27, ORANGE, VERT, True), 27)

    def test_rouge_divise(self):
        self.assertEqual(palier_suivant(40, 40, ROUGE, VERT, True), 20)
        self.assertEqual(palier_suivant(3, 3, ROUGE, VERT, True), SONDE)

    def test_sonde_puis_sortie_repart_petit(self):
        self.assertEqual(palier_suivant(60, 60, EN_SONDE, VERT, False, 0, 14), SONDE)
        self.assertEqual(palier_suivant(SONDE, SONDE, VERT, EN_SONDE, True), DEPART)

    def test_ancien_stop_redevient_sonde(self):
        self.assertEqual(palier_suivant(0, 0, EN_SONDE, STOP, False, 0, 10), SONDE)
        self.assertEqual(palier_suivant(0, 0, VERT, STOP, False), DEPART)

    def test_sonde_atteint_20_par_jour(self):
        # 14 vagues de 8 h à 21 h : la somme des sondes atteint exactement le quota.
        deja = 0
        for restantes in range(14, 0, -1):
            deja += sonde_par_vague(deja, restantes)
        self.assertEqual(deja, SONDE_JOUR)

    def test_sonde_rattrape_si_la_journee_commence_tard(self):
        self.assertEqual(sonde_par_vague(0, 4), 5)
        self.assertEqual(sonde_par_vague(18, 3), 1)
        self.assertEqual(sonde_par_vague(SONDE_JOUR, 3), 0)


class Branchement(unittest.TestCase):
    def test_palier_borne_le_plan(self):
        pil = {"gmail": {"palier": 8, "verdict": VERT, "motif": "sain"}, "orange": {"palier": 12, "verdict": VERT, "motif": "sain"}}
        p = {x["groupe"]: x for x in planifier({"gmail": 2000, "orange": 85}, TAUX, CAP, 0.3, None, None, pil)}
        self.assertEqual(p["gmail"]["volume"], 8)
        self.assertEqual(p["orange"]["volume"], 12)
        self.assertIn("pilote VERT", p["gmail"]["raison"])

    def test_sonde_garde_la_main(self):
        pil = {"gmail": {"palier": SONDE, "verdict": EN_SONDE, "motif": "spam"}}
        pl = {"gmail": {"etat": placement.SPAM, "motif": "0 vraie ouverture"}}
        p = {x["groupe"]: x for x in planifier({"gmail": 2000}, TAUX, CAP, 0.3, None, pl, pil)}
        self.assertEqual(p["gmail"]["volume"], SONDE)

    def test_reprise_du_pilote_leve_la_sonde_du_placement(self):
        pil = {"microsoft": {"palier": DEPART, "verdict": VERT, "motif": "reprise : 9 vrais signaux"}}
        pl = {"microsoft": {"etat": placement.SPAM, "motif": "0,9 % contre 2,9 %"}}
        cap = {**CAP, "microsoft": {"debit_heure": 117, "restant_jour": 389, "etat": "warming"}}
        p = {x["groupe"]: x for x in planifier({"microsoft": 1298}, {"microsoft": 0.01}, cap, 0.3, None, pl, pil)}
        self.assertFalse(p["microsoft"]["sonde"])
        self.assertEqual(p["microsoft"]["volume"], DEPART)

    def test_sonde_du_pilote_suit_le_quota(self):
        pil = {"gmail": {"palier": 4, "verdict": EN_SONDE, "motif": "spam persistant"}}
        pl = {"gmail": {"etat": placement.SPAM, "motif": "0 vraie ouverture"}}
        p = {x["groupe"]: x for x in planifier({"gmail": 2000}, TAUX, CAP, 0.3, None, pl, pil)}
        self.assertEqual(p["gmail"]["volume"], 4)
        self.assertIn("20/jour", p["gmail"]["raison"])

    def test_sonde_exemptee_de_la_part_par_domaine(self):
        cand = {"gmail": [(i, "gmail.com") for i in range(50)], "orange": [(100 + i, "orange.fr") for i in range(50)]}
        # Vague de 12 : 10 % = 1 par domaine ; la sonde Gmail doit quand même partir à 2.
        pris = choisir(cand, {"gmail": 2, "orange": 10}, {"gmail": 2, "orange": 10}, ["orange", "gmail"], None, None, 0.10, {"gmail"})
        self.assertEqual(len(pris["gmail"]), 2)
        self.assertEqual(len(pris["orange"]), 1)

    def test_sans_pilote_rien_ne_change(self):
        a = planifier({"gmail": 2000, "orange": 85}, TAUX, CAP, 0.3)
        b = planifier({"gmail": 2000, "orange": 85}, TAUX, CAP, 0.3, None, None, None)
        self.assertEqual(a, b)

    def test_equilibre_sans_les_messageries_en_sonde(self):
        # Cas Hall U Need A du 25/11 : Gmail 2 479 en sonde, La Poste 6 saine → La Poste ne doit plus être bornée à 1.
        restants = {"gmail": 2479, "microsoft": 1298, "laposte": 6, "orange": 85}
        plan = [{"groupe": "gmail", "volume": 2, "sonde": True}, {"groupe": "microsoft", "volume": 2, "sonde": True},
                {"groupe": "laposte", "volume": 6}, {"groupe": "orange", "volume": 12}]
        r = restants_equilibre(restants, {}, plan)
        self.assertEqual(set(r), {"laposte", "orange"})
        cap = plafonds_equilibre(r, 22)
        self.assertGreaterEqual(cap["laposte"], 3)
        self.assertGreaterEqual(cap["orange"], 12)

    def test_equilibre_sans_les_exclus(self):
        r = restants_equilibre({"yahoo": 338, "orange": 85}, {"yahoo": "retirée"}, [{"groupe": "orange", "volume": 5}])
        self.assertEqual(r, {"orange": 85})


if __name__ == "__main__":
    unittest.main()
