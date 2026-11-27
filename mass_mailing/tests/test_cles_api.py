"""Clé DeepSeek saisie par le superadmin (20/10/2026) : testée avant d'être gardée, chiffrée,
jamais renvoyée à l'écran.

Rien ne part sur le réseau ni en base : requests.get et pg sont remplacés, le fichier de
chiffrement est temporaire."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import cles_api  # noqa: E402

CLE = "sk-0123456789abcdef0123456789ab9e09"


class Rep:
    def __init__(self, code, corps=None):
        self.status_code, self._corps = code, corps or {}

    def json(self):
        return self._corps


SOLDE = {"balance_infos": [{"currency": "USD", "total_balance": "32.56"}]}


class TestCles(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        for cible, val in (("FICHIER_CHIFFREMENT", Path(d.name) / "cle"),):
            p = mock.patch.object(cles_api, cible, val)
            p.start()
            self.addCleanup(p.stop)
        self.base = {}

        def ecrire(sql, params=None):
            if sql.lstrip().startswith("INSERT"):
                self.base[params["n"]] = {"chiffree": params["c"], "fin": params["f"], "maj_at": None, "maj_par": params["p"]}
            elif sql.lstrip().startswith("DELETE"):
                return 1 if self.base.pop(params["n"], None) else 0
            return 1

        def ligne(sql, params=None):
            return self.base.get(params["n"])

        for cible, f in (("ecrire", ecrire), ("ligne", ligne)):
            p = mock.patch.object(cles_api.pg, cible, side_effect=f)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(cles_api, "_depuis_env", return_value="")
        p.start()
        self.addCleanup(p.stop)

    def test_cle_masquee_refusee_sans_appel(self):
        with mock.patch.object(cles_api.requests, "get") as get:
            with self.assertRaises(ValueError):
                cles_api.enregistrer("deepseek", "sk-****************************", "camille")
        get.assert_not_called()
        self.assertEqual(self.base, {})

    def test_cle_refusee_par_deepseek_n_ecrase_rien(self):
        with mock.patch.object(cles_api.requests, "get", return_value=Rep(401)):
            with self.assertRaises(ValueError):
                cles_api.enregistrer("deepseek", CLE, "camille")
        self.assertEqual(self.base, {})

    def test_cle_valide_chiffree_et_relue(self):
        with mock.patch.object(cles_api.requests, "get", return_value=Rep(200, SOLDE)):
            t = cles_api.enregistrer("deepseek", CLE, "camille")
        self.assertEqual(t["solde"], "32.56 USD")
        self.assertNotIn(CLE, self.base["deepseek"]["chiffree"])
        self.assertEqual(cles_api.lire("deepseek"), CLE)

    def test_etat_ne_montre_jamais_la_cle(self):
        with mock.patch.object(cles_api.requests, "get", return_value=Rep(200, SOLDE)):
            cles_api.enregistrer("deepseek", CLE, "camille")
        e = cles_api.etat("deepseek")
        self.assertEqual((e["configuree"], e["source"], e["fin"]), (True, "superadmin", "9e09"))
        self.assertNotIn(CLE, repr(e))


if __name__ == "__main__":
    unittest.main()
