"""Plusieurs accès par compte client : retirer un accès (20/10/2026).

Rien n'est écrit en base : clients.par_slug et pg.ecrire sont remplacés."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi import HTTPException  # noqa: E402

from api import saas  # noqa: E402

ZYLIO = {"id": 3, "slug": "zylio", "schema_pg": "mmc_zylio"}


def requete(role):
    return SimpleNamespace(state=SimpleNamespace(session={"role": role}))


class TestRetirerAcces(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(saas.clients, "par_slug", side_effect=lambda s: ZYLIO if s == "zylio" else None)
        p.start()
        self.addCleanup(p.stop)

    def test_retire_seulement_un_utilisateur_du_client(self):
        with mock.patch.object(saas.pg, "ecrire", return_value=1) as ecrire:
            self.assertEqual(saas.retirer_acces("zylio", 8, requete("superadmin")), {"ok": True})
        sql, params = ecrire.call_args.args
        self.assertIn("client_id = %(c)s", sql)
        self.assertIn("role = 'client'", sql)
        self.assertEqual(params, {"u": 8, "c": 3})

    def test_utilisateur_d_un_autre_client_404(self):
        with mock.patch.object(saas.pg, "ecrire", return_value=0):
            with self.assertRaises(HTTPException) as e:
                saas.retirer_acces("zylio", 1, requete("superadmin"))
        self.assertEqual(e.exception.status_code, 404)

    def test_client_inconnu_404(self):
        with mock.patch.object(saas.pg, "ecrire") as ecrire:
            with self.assertRaises(HTTPException) as e:
                saas.retirer_acces("inconnu", 8, requete("superadmin"))
        self.assertEqual(e.exception.status_code, 404)
        ecrire.assert_not_called()

    def test_compte_client_refuse(self):
        with mock.patch.object(saas.pg, "ecrire") as ecrire:
            with self.assertRaises(HTTPException) as e:
                saas.retirer_acces("zylio", 8, requete("client"))
        self.assertEqual(e.exception.status_code, 403)
        ecrire.assert_not_called()


if __name__ == "__main__":
    unittest.main()
