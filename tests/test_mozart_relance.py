"""Exception à la règle des 120 jours pour les relances Mozart (Camille, 05/10/2026).
Lancer : python3 tests/test_mozart_relance.py — sans base : _q est simulé."""
import sys, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import mozart

def sc(data):
    return {"id": str(uuid.uuid4()), "site_code": "lcr",
            "graphe": {"nodes": [{"id": "declencheur", "type": "declencheur", "data": data}], "edges": []}}

def avec(propres, total, premier_il_y_a_j, dernier_il_y_a_j=None):
    maint = datetime.now(timezone.utc)
    def faux_q(sql, params=None):
        if "mozart_passages" in sql: return [(propres,)]
        if "min(occurred_at)" in sql: return [(total, maint - timedelta(days=premier_il_y_a_j) if total else None)]
        if "max(occurred_at)" in sql: return [(maint - timedelta(days=dernier_il_y_a_j) if dernier_il_y_a_j is not None else None,)]
        raise AssertionError(sql)
    mozart._q = faux_q

CAS = [
    ("sans exception déclarée → refus", {}, (0, 1, 30), False),
    ("premier envoi : 1 email il y a 30 j → oui", {"relance_premier_envoi": True}, (0, 1, 30), True),
    ("premier envoi : 1 email il y a 5 j → non (< 14 j)", {"relance_premier_envoi": True}, (0, 1, 5), False),
    ("premier envoi : 2 emails hors scénario → non", {"relance_premier_envoi": True}, (0, 2, 30), False),
    ("premier envoi : déjà 2 relances → non", {"relance_premier_envoi": True}, (2, 3, 30), False),
    ("premier envoi : 1 relance faite → oui (2e)", {"relance_premier_envoi": True}, (1, 2, 40), True),
    ("séquence : E1 du scénario seul → relance oui", {"relance_mode": "sequence"}, (1, 1, 5), True),
    ("séquence : un email hors scénario → non", {"relance_mode": "sequence"}, (1, 2, 5), False),
    ("séquence : 3 emails déjà → non", {"relance_mode": "sequence"}, (3, 3, 20), False),
    ("engagés : dernier envoi il y a 10 j → oui", {"relance_mode": "engages"}, (0, 3, 60, 10), True),
    ("engagés : dernier envoi il y a 3 j → non", {"relance_mode": "engages"}, (0, 3, 60, 3), False),
    ("engagés : 2 emails du scénario → non", {"relance_mode": "engages"}, (2, 5, 60, 10), False),
]
ok = True
for nom, data, args, attendu in CAS:
    avec(*args)
    r = mozart._relance_autorisee(sc(data), "x@exemple.fr")
    ok &= (r == attendu)
    print(("  OK    " if r == attendu else "  ÉCHEC ") + nom)
print("=" * 62)
print("L'exception aux 120 jours tient dans ses limites." if ok else "ÉCHEC")
sys.exit(0 if ok else 1)
