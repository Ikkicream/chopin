"""Balayage d'antispam multi-destinataires (27/09/2026, vague 1 Omoda : 3 destinataires La Poste
cliqués en 10 s depuis des IP OVH, 10 min après l'envoi). Lancer : python3 -m unittest tests.test_balayage -v"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.score_clics import DEFAUT, balayages, scorer  # noqa: E402

T = datetime(2026, 9, 27, 14, 21, 5, tzinfo=timezone.utc)
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"


def k(i, rid, dom, s, depuis=640):
    return {"id": i, "recipient_id": rid, "domaine": dom, "at": T + timedelta(seconds=s), "secondes_depuis_envoi": depuis}


class Balayage(unittest.TestCase):
    def test_cas_reel_la_poste(self):
        cl = [k(33, 5355, "laposte.net", 0), k(34, 5355, "laposte.net", 1), k(35, 4422, "laposte.net", 2),
              k(36, 4777, "laposte.net", 10)]
        self.assertEqual(balayages(cl, DEFAUT), {33, 34, 35, 36})

    def test_deux_destinataires_ne_suffisent_pas(self):
        self.assertEqual(balayages([k(1, 1, "laposte.net", 0), k(2, 2, "laposte.net", 5)], DEFAUT), set())

    def test_messageries_differentes_pas_un_balayage(self):
        cl = [k(1, 1, "laposte.net", 0), k(2, 2, "orange.fr", 3), k(3, 3, "gmail.com", 6)]
        self.assertEqual(balayages(cl, DEFAUT), set())

    def test_trop_espaces(self):
        cl = [k(1, 1, "laposte.net", 0), k(2, 2, "laposte.net", 40), k(3, 3, "laposte.net", 80)]
        self.assertEqual(balayages(cl, DEFAUT), set())

    def test_clics_tardifs_ignores(self):
        cl = [k(i, i, "orange.fr", i, depuis=8000) for i in range(1, 5)]
        self.assertEqual(balayages(cl, DEFAUT), set())

    def test_score_plus_humain_probable(self):
        e = [{"source": "S", "at": T, "url": "https://x/rappel", "type": "contenu", "ip": "54.38.153.182",
              "ua": CHROME, "proxy": False}]
        self.assertEqual(scorer(e, None, DEFAUT)["statut"], "human_likely")
        s = scorer(e, None, DEFAUT, balayage=True)
        self.assertIn(s["statut"], ("bot_suspected", "security_scan"))


if __name__ == "__main__":
    unittest.main()
