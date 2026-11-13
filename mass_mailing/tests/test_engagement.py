"""Classement humain / robot / ? des ouvertures et alternance A/B par vague (15/10/2026)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.engagement import classer_evenement  # noqa: E402
from jobs.routage import _alterner  # noqa: E402

CHROME109 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"


class Engagement(unittest.TestCase):
    def test_scanner_microsoft(self):
        assert classer_evenement(CHROME109, "4.251.36.105", 16)[0] == "robot"


    def test_scanner_google(self):
        assert classer_evenement(CHROME109, "74.125.218.36", 900)[0] == "robot"


    def test_ouverture_immediate(self):
        assert classer_evenement(CHROME109, "90.115.120.36", 20)[0] == "robot"


    def test_headless(self):
        assert classer_evenement("Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/148.0", "1.2.3.4", 900)[0] == "robot"


    def test_gmail_proxy_humain(self):
        ua = "Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 (via ggpht.com GoogleImageProxy)"
        assert classer_evenement(ua, "142.250.32.71", 504)[0] == "humain"


    def test_outlook_humain(self):
        assert classer_evenement("Mozilla/4.0 (compatible; ms-office; MSOffice 16)", "93.3.254.216", 582)[0] == "humain"


    def test_apple_mpp_inconnu(self):
        assert classer_evenement("Mozilla/5.0", "2a09:bac3:33ca:14e6::215:68", 1645)[0] == "?"


    def test_passerelle_plusieurs_ip(self):
        assert classer_evenement(CHROME109.replace("109", "148"), "147.185.226.14", 2249, nb_ip_heure=5)[0] == "robot"


    def test_navigateur_particulier_humain(self):
        assert classer_evenement(CHROME109.replace("109", "141"), "2a01:cb1c:312::1", 1460)[0] == "humain"


    def test_alterner_equilibre(self):
        v = {i: "A" for i in range(10)} | {i: "B" for i in range(10, 14)}
        out = _alterner(list(range(14)), v)
        assert [v[i] for i in out[:8]] == ["A", "B"] * 4
        assert sorted(out) == list(range(14))
        pris = out[:6]
        assert abs(sum(v[i] == "A" for i in pris) - sum(v[i] == "B" for i in pris)) <= 1


class AlternanceCumulee(unittest.TestCase):
    def test_plusieurs_groupes_impairs_restent_equilibres(self):
        # 5 groupes servis 1 par 1 : sans report de la version en retard, A partirait 5 fois.
        v = {}
        groupes = []
        for g in range(5):
            ids = [g * 10 + k for k in range(4)]
            for k, i in enumerate(ids):
                v[i] = "A" if k % 2 == 0 else "B"
            groupes.append(ids)
        reste = {"A": 10, "B": 10}
        partis = []
        for ids in groupes:
            pris = _alterner(ids, v, "A" if reste["A"] >= reste["B"] else "B")[:1]
            for i in pris:
                reste[v[i]] -= 1
            partis += pris
        n_a = sum(v[i] == "A" for i in partis)
        self.assertLessEqual(abs(n_a - (len(partis) - n_a)), 1)


class PlafondApresAlternance(unittest.TestCase):
    def test_troncature_du_plafond_rattrape_l_ecart(self):
        # 15/10 : lot de 19 (9 A aux petits ids, 10 B), plafond 13 : trié par id, A prenait 7 places
        # à chaque vague (cumul 21 A / 18 B). Ordonné par rattrapage, l'écart revient à ≤ 1.
        from jobs.envoi import ordre_rattrapage
        dest = [{"id": i, "variante": "A" if i < 9 else "B"} for i in range(19)]
        partis = {"A": 21, "B": 18}
        for d in ordre_rattrapage(dest, partis)[:13]:
            partis[d["variante"]] += 1
        self.assertLessEqual(abs(partis["A"] - partis["B"]), 1)
        self.assertEqual(len(ordre_rattrapage(dest, {})), 19)

    def test_rien_n_est_perdu_quand_la_seconde_liste_est_plus_longue(self):
        v = {0: "A", 1: "B", 2: "B", 3: "B"}
        self.assertEqual(sorted(_alterner([0, 1, 2, 3], v, "A")), [0, 1, 2, 3])


class ProxyGmail(unittest.TestCase):
    def test_proxy_gmail_est_indetermine(self):
        from jobs.engagement import classer_evenement
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/42.0.2311.135 Safari/537.36 Edge/12.246 Mozilla/5.0")
        self.assertEqual(classer_evenement(ua, "66.249.89.10", 900)[0], "?")
        # Une autre IP Google (hors proxy d'images) reste un scanner.
        self.assertEqual(classer_evenement(ua, "74.125.10.10", 900)[0], "robot")


if __name__ == "__main__":
    unittest.main()
