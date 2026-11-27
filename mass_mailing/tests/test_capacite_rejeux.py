"""Rejeux Sweego (24/11/2026) : un rebond ou un différé compte UNE fois par message.

Cas réel du 23/11 : Sweego a renvoyé chaque rebond Yahoo/AOL 21 fois (nouvel event_id, `details`
sans IP) → 66 lignes pour 3 adresses, une file fantôme « inconnue|…|yahoo » à « 100 % de rebonds »
qui écrasait la vraie file dans le routage. Aucune écriture en base : `pg` est remplacé par une
fausse base en mémoire.
Lancer depuis genesis/mass_mailing :  python3 -m unittest tests.test_capacite_rejeux -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs import capacite  # noqa: E402

CAMP = "d4cdc47a-e4ac-41fd-b497-9252009fecac"
ORIGINE = ("Nov 23 17:16:20 prod-mta-12 zone-mta: info Sender/yahoo_us/1471548[17] id=x REJECTED[capacity] "
           "from=<a@news.leclientroi.email> to=<mort@aol.com> src=185.255.28.68 mx=mta7.am0.yahoodns.net[98.136.96.77] "
           "(552 1 Requested mail action aborted, mailbox not found)")
REJEU = "552 1 Requested mail action aborted, mailbox not found"


def evt(i, typ, details, ts, h="h-mort", code=552, dest="mort@aol.com"):
    return {"id": i, "event_type": typ, "campaign_id": CAMP, "email_hash": h, "received_at": ts,
            "raw_payload": {"event_id": f"ev-{i}", "swg_uid": f"uid-{h}", "details": details, "timestamp": ts,
                            "recipient": dest, "domain_from": "news.leclientroi.email", "campaign_type": "market",
                            "response_code": code}}


class FausseBase:
    SCHEMA = "mass_mailing"

    def __init__(self, evenements, lignes=None):
        self.evenements, self.lignes_ = evenements, list(lignes or [])

    def schema_courant(self):
        return self.SCHEMA

    def valeur(self, sql, prm=None):
        if "max(webhook_id)" in sql:
            return max((x["webhook_id"] for x in self.lignes_), default=0)
        if sql.lstrip().startswith("SELECT 1 FROM smtp_reponses"):
            return 1 if any(x["email_hash"] == prm["h"] and x["campaign_id"] == prm["c"] and x["etat"] == prm["e"]
                            and (x["etat"] == "hard_bounce" or x["at"] == prm["at"]) for x in self.lignes_) else None
        if sql.lstrip().startswith("SELECT sending_ip FROM smtp_reponses"):
            vus = [x for x in self.lignes_ if x["email_hash"] == prm["h"] and x["campaign_id"] == prm["c"]
                   and x["sending_ip"] != "inconnue"]
            return vus[-1]["sending_ip"] if vus else None
        raise AssertionError(sql)

    def lignes(self, sql, prm=None):
        assert "FROM webhook_events" in sql
        return [e for e in self.evenements if e["id"] > prm["d"]][: prm["l"]]

    def ecrire(self, sql, prm=None):
        assert "INSERT INTO smtp_reponses" in sql
        if any(x["event_id"] == prm["ev"] for x in self.lignes_):
            return 0
        self.lignes_.append({"event_id": prm["ev"], "webhook_id": prm["w"], "at": prm["at"], "campaign_id": prm["c"],
                             "email_hash": prm["h"], "sending_ip": prm["ip"], "etat": prm["et"], "categorie": prm["ca"]})
        return 1


class Rejeux(unittest.TestCase):
    def setUp(self):
        self._pg, self._mx = capacite.pg, capacite.charger_mx
        capacite.charger_mx = lambda: None

    def tearDown(self):
        capacite.pg, capacite.charger_mx = self._pg, self._mx

    def ingerer(self, evenements, lignes=None):
        capacite.pg = FausseBase(evenements, lignes)
        capacite.ingerer()
        return capacite.pg.lignes_

    def test_rebond_rejoue_21_fois_compte_une_fois(self):
        evts = [evt(1, "hard_bounce", ORIGINE, "2026-11-23T17:16:20+00:00")]
        evts += [evt(2 + k, "hard_bounce", REJEU, "2026-11-23T17:16:33.600200") for k in range(21)]
        lignes = self.ingerer(evts)
        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes[0]["sending_ip"], "185.255.28.68")

    def test_rejeu_seul_herite_de_l_ip_du_message(self):
        # Boîte pleine Microsoft du 23/11 : accepté par .17, puis 17 rejeux sans IP du même différé.
        dest = "plein@hotmail.com"
        acc = evt(1, "delivered", "250 OK src=185.255.28.17", "2026-11-23T13:14:21+00:00", h="h-plein", code=250, dest=dest)
        evts = [acc] + [evt(2 + k, "soft_bounce", "452 4.2.2 mailbox full (over quota)", "2026-11-23T22:01:03.509930",
                            h="h-plein", code=452, dest=dest) for k in range(17)]
        lignes = self.ingerer(evts)
        self.assertEqual([x["etat"] for x in lignes], ["accepted", "deferred"])
        self.assertEqual({x["sending_ip"] for x in lignes}, {"185.255.28.17"})

    def test_vrai_nouvel_essai_differe_garde(self):
        # Deux différés à des heures DIFFÉRENTES = deux vrais essais du serveur : on garde les deux.
        evts = [evt(1, "soft_bounce", "452 4.2.2 over quota src=185.255.28.17", "2026-11-23T10:00:00+00:00", code=452),
                evt(2, "soft_bounce", "452 4.2.2 over quota src=185.255.28.17", "2026-11-23T11:00:00+00:00", code=452)]
        self.assertEqual(len(self.ingerer(evts)), 2)

    def test_deux_adresses_deux_rebonds(self):
        evts = [evt(1, "hard_bounce", ORIGINE, "2026-11-23T17:16:20+00:00", h="a"),
                evt(2, "hard_bounce", ORIGINE, "2026-11-23T17:16:21+00:00", h="b")]
        self.assertEqual(len(self.ingerer(evts)), 2)


if __name__ == "__main__":
    unittest.main()
