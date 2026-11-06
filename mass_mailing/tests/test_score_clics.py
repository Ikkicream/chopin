"""Tests du score anti-robot (jobs/score_clics.py) — fonction pure, aucune écriture en base.

Lancer depuis genesis/mass_mailing :  python3 -m unittest tests.test_score_clics -v
Jeu de référence : tests/fixtures/cas_reels.json (26/09/2026, sans adresse email) :
- « bnp » : la passerelle de sécurité de BNP Paribas (16 clics Sweego, 8 visites de rappel) ;
- « humain_oui » : une vraie visite suivie d'un « Oui, rappelez-moi » 11 s plus tard.
"""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.score_clics import DEFAUT, reseau, scorer, statut_de, ua_robot  # noqa: E402

FIX = json.loads((Path(__file__).parent / "fixtures" / "cas_reels.json").read_text())
T0 = datetime(2026, 9, 26, 14, 0, tzinfo=timezone.utc)
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"


def dt(s):
    return datetime.fromisoformat(s)


def cas(nom):
    c = FIX[nom]
    ev = [{"source": "S", "at": dt(x["at"]), "url": x["url"], "type": x["type"], "ip": x["ip"], "ua": x["ua"],
           "proxy": x.get("proxy")} for x in c["S"]]
    ev += [{"source": "R", "at": dt(x["at"]), "url": x["url"], "type": x["type"], "ip": x["ip"], "ua": x["ua"],
            "proxy": False} for x in c["R"]]
    return ev, (dt(c["soumis_a"]) if c["soumis_a"] else None)


def clic(s, url="https://exemple.fr/a", type_="contenu", ip="90.1.2.3", ua=CHROME, source="S", proxy=False):
    return {"source": source, "at": T0 + timedelta(seconds=s), "url": url, "type": type_, "ip": ip, "ua": ua, "proxy": proxy}


class CasReels(unittest.TestCase):
    def test_bnp_est_un_scan(self):
        ev, soumis = cas("bnp")
        r = scorer(ev, soumis, DEFAUT)
        self.assertEqual(r["statut"], "security_scan", r)
        self.assertTrue(any("rafale" in x for x in r["raisons"]), r)

    def test_bnp_sans_le_lien_piege_reste_un_scan(self):
        ev, soumis = cas("bnp")
        ev = [e for e in ev if e["type"] != "piege"]
        self.assertEqual(scorer(ev, soumis, DEFAUT)["statut"], "security_scan")

    def test_vrai_oui_est_humain_confirme(self):
        ev, soumis = cas("humain_oui")
        r = scorer(ev, soumis, DEFAUT)
        self.assertEqual(r["statut"], "human_confirmed", r)


class Regles(unittest.TestCase):
    def test_clic_isole_humain_probable(self):
        r = scorer([clic(3600)], T0, DEFAUT)
        self.assertEqual(r["statut"], "human_likely", r)

    def test_rafale_3_liens_en_10s(self):
        ev = [clic(0, "https://e.fr/1"), clic(2, "https://e.fr/2"), clic(4, "https://e.fr/3")]
        r = scorer(ev, T0, DEFAUT)
        self.assertEqual(r["statut"], "security_scan", r)

    def test_deux_liens_espaces_reste_humain(self):
        ev = [clic(0, "https://e.fr/1"), clic(90, "https://e.fr/2")]
        self.assertEqual(scorer(ev, T0, DEFAUT)["statut"], "human_likely")

    def test_paire_desinscription_autre_lien(self):
        ev = [clic(0, "https://e.fr/offre"), clic(30, "https://mail.cheffer.email/api/public/mass-mailing/desinscription?t=x", "desinscription")]
        r = scorer(ev, T0, DEFAUT)
        self.assertLessEqual(r["score"], -50, r)

    def test_trois_reseaux_en_deux_minutes(self):
        ev = [clic(0, ip="1.1.1.1"), clic(40, "https://e.fr/b", ip="2.2.2.2"), clic(80, "https://e.fr/c", ip="3.3.3.3")]
        self.assertTrue(any("réseaux" in x for x in scorer(ev, T0, DEFAUT)["raisons"]))

    def test_navigateur_de_robot_et_mot_entier(self):
        self.assertEqual(ua_robot("python-requests/2.31", DEFAUT["user_agents_robots"]), "python-requests")
        self.assertEqual(ua_robot("Mozilla/5.0 (compatible; Googlebot/2.1)", ["bot"]), None)  # « googlebot » : un seul mot
        self.assertEqual(ua_robot("Some Bot 1.0", ["bot"]), "bot")
        self.assertIsNone(ua_robot("Mozilla/5.0 (Linux; Android 12; Cubot KingKong)", ["bot"]))

    def test_navigateur_vide(self):
        r = scorer([clic(3600, ua="")], T0, DEFAUT)
        self.assertEqual(r["statut"], "security_scan")

    def test_proxy_sweego_seul_ne_suffit_pas_a_scanner(self):
        r = scorer([clic(3600, proxy=True)], T0, DEFAUT)
        self.assertEqual(r["statut"], "bot_suspected", r)

    def test_delai_serveur_uniquement(self):
        # Clic Sweego 5 s après l'envoi : pas de pénalité (horloge Sweego décalée).
        self.assertEqual(scorer([clic(5)], T0, DEFAUT)["statut"], "human_likely")
        # Visite de rappel 5 s après l'envoi (heure serveur) : pénalité.
        r = scorer([clic(5, source="R", type_="visite")], T0, DEFAUT)
        self.assertTrue(any("après l'envoi" in x for x in r["raisons"]), r)

    def test_ip_multi_destinataires(self):
        r = scorer([clic(3600, ip="9.9.9.9")], T0, DEFAUT, ips_multi={"9.9.9.9"})
        self.assertTrue(any("même IP" in x for x in r["raisons"]))

    def test_reseau(self):
        self.assertEqual(reseau("185.152.39.39"), "185.152.39.0/24")
        self.assertEqual(reseau("2001:db8::1"), "2001:db8::/48")
        self.assertIsNone(reseau("pas une ip"))

    def test_seuils(self):
        s = DEFAUT["seuils"]
        self.assertEqual([statut_de(x, s) for x in (-60, -59, -25, -24, 14, 15, 39, 40)],
                         ["security_scan", "bot_suspected", "bot_suspected", "unknown", "unknown",
                          "human_likely", "human_likely", "human_confirmed"])


if __name__ == "__main__":
    unittest.main()


class BadgeEtPreferences(unittest.TestCase):
    """Badge visible « Email envoyé par la technologie Cheffer » + page de préférences (27/09)."""

    def test_badge_seul_nest_pas_un_robot(self):
        ev = [clic(3600, "https://mail.cheffer.email/api/public/mass-mailing/p?t=x", "piege"),
              clic(3601, "/p", "visite", source="R")]
        self.assertNotIn(scorer(ev, T0, DEFAUT)["statut"], ("security_scan", "bot_suspected"))

    def test_badge_puis_formulaire_humain(self):
        ev = [clic(3600, "https://mail.cheffer.email/api/public/mass-mailing/p?t=x", "piege"),
              clic(3601, "/p", "visite", source="R"), clic(3620, "/p", "pause", source="R")]
        self.assertEqual(scorer(ev, T0, DEFAUT)["statut"], "human_confirmed")

    def test_formulaire_robot(self):
        ev = [clic(3601, "/p", "visite", source="R"),
              {**clic(3601.5, "/p", "robot_perdu", source="R"), "motif": "aucun geste humain"}]
        r = scorer(ev, T0, DEFAUT)
        self.assertEqual(r["statut"], "security_scan", r)
        self.assertTrue(any("robot" in x for x in r["raisons"]))


class PiegesDuFormulaire(unittest.TestCase):
    def setUp(self):
        from infra import preferences as P
        self.P = P
        self.t = "123.abc"
        self.emis = 1_790_000_000
        self.sig = P._signe(self.t, self.emis)
        self.ok = {"t": self.t, "emis": str(self.emis), "sig": self.sig, "geste": self.sig[::-1],
                   "site_web": "", "choix": "mensuel"}

    def test_humain_accepte(self):
        self.assertIsNone(self.P.verifier_humain(self.ok, self.t, self.emis + 12))

    def test_champ_piege(self):
        self.assertEqual(self.P.verifier_humain({**self.ok, "site_web": "http://x"}, self.t, self.emis + 12), "champ piège rempli")

    def test_sans_geste(self):
        self.assertIn("geste", self.P.verifier_humain({**self.ok, "geste": ""}, self.t, self.emis + 12))

    def test_trop_rapide(self):
        self.assertIn("trop rapide", self.P.verifier_humain(self.ok, self.t, self.emis + 1))

    def test_signature_falsifiee(self):
        self.assertEqual(self.P.verifier_humain({**self.ok, "sig": "0" * 32}, self.t, self.emis + 12), "signature invalide")

    def test_jeton_dun_autre_destinataire(self):
        self.assertEqual(self.P.verifier_humain(self.ok, "999.zzz", self.emis + 12), "signature invalide")

    def test_choix_inconnu(self):
        self.assertEqual(self.P.verifier_humain({**self.ok, "choix": "tout"}, self.t, self.emis + 12), "choix inconnu")
