"""Import d'un fichier DÉJÀ vérifié par Mailnjoy (13/10/2026) : verdicts repris, 0 crédit."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.analyze_csv import analyser  # noqa: E402
from jobs.validation import decision_fichier  # noqa: E402


class TestFichierVerifie(unittest.TestCase):
    def test_export_avec_colonnes(self):
        csv = "Nom;Email;Status;Category\nA;a@x.fr;VALID;SAFE\nB;b@x.fr;INVALID;UNSAFE\nC;c@x.fr;VALID;RISKY\n".encode()
        a = analyser(csv)
        self.assertEqual(a["colonnes_verdict"], {"email": 1, "statut": 2, "categorie": 3})
        v = {d["email"]: d["verdict"] for d in a["destinataires"]}
        self.assertEqual(v["a@x.fr"], ("VALID", "SAFE"))
        self.assertEqual(v["b@x.fr"], ("INVALID", "UNSAFE"))

    def test_emails_seuls(self):
        a = analyser("email\na@x.fr\nb@x.fr\n".encode())
        self.assertEqual(a["compteurs"]["uniques"], 2)
        self.assertEqual(a["destinataires"][0]["verdict"], ("", ""))

    def test_sans_en_tete_inchange(self):
        a = analyser("a@x.fr\nb@x.fr\n".encode())
        self.assertEqual(a["compteurs"]["uniques"], 2)

    def test_decisions(self):
        self.assertEqual(decision_fichier("VALID", "SAFE")[0], "valid")
        self.assertEqual(decision_fichier("VALID", "VERY_SAFE")[0], "valid")
        self.assertEqual(decision_fichier("Valide", "")[0], "valid")
        self.assertEqual(decision_fichier("VALID", "RISKY")[0], "risky")
        self.assertEqual(decision_fichier("INVALID", "UNSAFE")[0], "invalid")
        self.assertEqual(decision_fichier("Invalide", "")[0], "invalid")
        self.assertEqual(decision_fichier("catch-all", "")[0], "risky")
        self.assertEqual(decision_fichier("unknown", "")[0], "unknown")
        self.assertEqual(decision_fichier("disposable", "")[0], "disposable")
        self.assertEqual(decision_fichier("", "")[0], "valid")          # liste déjà nettoyée
        self.assertEqual(decision_fichier("blabla", "")[0], "unknown")  # prudence


if __name__ == "__main__":
    unittest.main()
