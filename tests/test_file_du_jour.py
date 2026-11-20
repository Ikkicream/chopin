#!/usr/bin/env python3
"""La file du jour (21/10/2026) : un contact dont la boîte attitrée est en pause de 4 minutes
repart DANS LA JOURNÉE, il n'attend plus le lendemain.

Avant : `send_batch` reportait au lendemain tout contact tombant sur sa boîte en pause, sauf si
TOUTES les boîtes l'étaient. Avec 4 boîtes, 3 sont en pause à tout instant : 116 garagistes sur
159 reportés le 21/10, la plateforme plafonnait à ~77 envois/jour pour ~125 autorisés.

Simulation sans réseau ni base : horloge fictive, 4 boîtes, affinité fixe par contact.
"""
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import maildoso_backend as md  # noqa: E402

ECHECS: list[str] = []


def verifie(nom, condition, detail=""):
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def simuler(n_contacts: int, plafond: int, fin_minutes: int | None = None, campagne: str = "lcr-99d75608-a98-2026-10-22", ecart: int = 60):
    horloge = {"t": 0.0}
    boites = [f"b{i}@x.fr" for i in range(4)]
    envoyes = {b: 0 for b in boites}
    dernier = {b: None for b in boites}
    affinite = {f"c{i}@client.fr": boites[i % 4] for i in range(n_contacts)}
    journal = []

    def boites_fn(site, usage=None):
        return [{"email": b, "active": True, "reste": max(0, plafond - envoyes[b]), "usage": "adhoc"} for b in boites]

    fake_exp = types.SimpleNamespace(boites=boites_fn, affinite=lambda e: {"boite": affinite[e]} if e in affinite else None)
    sys.modules["expediteur"] = fake_exp

    def send_email(to, subject, **kw):
        b = affinite[to]
        if envoyes[b] >= plafond:
            return {"ok": False, "reporte": True, "error": "aucune boîte disponible pour ce contact aujourd'hui"}
        if dernier[b] is not None and horloge["t"] - dernier[b] < md.ECART_MIN_BOITE:
            return {"ok": False, "reporte": True, "error": "cadence — pause"}
        envoyes[b] += 1
        dernier[b] = horloge["t"]
        journal.append((horloge["t"], b, to))
        return {"ok": True, "mailbox": b}

    debut = datetime(2026, 10, 22, 9, 0, tzinfo=ZoneInfo("Europe/Paris"))
    orig = (md.send_email, md._secondes_depuis_dernier_envoi, md.time.sleep, md._cadence,
            md.already_sent_emails, md._echeance_passee)
    md.send_email = send_email
    md._secondes_depuis_dernier_envoi = lambda b: None if dernier[b] is None else horloge["t"] - dernier[b]
    md.time.sleep = lambda s: horloge.__setitem__("t", horloge["t"] + s)
    md._cadence = lambda restants, fin=None: (ecart, ecart)
    md.already_sent_emails = lambda cid: set()
    md._echeance_passee = (lambda f: False) if fin_minutes is None else (lambda f: horloge["t"] >= fin_minutes * 60)
    try:
        res = md.send_batch(campagne, "Objet", "<p>x</p>", list(affinite),
                            site="lcr", usage="adhoc", fin_lot=debut + timedelta(hours=9))
    finally:
        (md.send_email, md._secondes_depuis_dernier_envoi, md.time.sleep, md._cadence,
         md.already_sent_emails, md._echeance_passee) = orig
        sys.modules.pop("expediteur", None)
    return res, journal, envoyes


print("\n1. Les contacts dont la boîte est en pause repartent dans la journée")
res, journal, envoyes = simuler(n_contacts=80, plafond=30)
verifie("les 80 contacts partent (4 boîtes × 30 de plafond = 120 possibles)", res["sent"] == 80, f"({res['sent']} envoyés, {res['reportes']} reportés)")
verifie("aucun report au lendemain", res["reportes"] == 0)
ecarts_ok = all(
    t2 - t1 >= md.ECART_MIN_BOITE
    for b in envoyes
    for (t1, _, _), (t2, _, _) in zip([j for j in journal if j[1] == b], [j for j in journal if j[1] == b][1:]))
verifie("la pause de 4 minutes par boîte est toujours respectée", ecarts_ok)

print("\n2. Une boîte pleine fait attendre ses contacts jusqu'à demain, pas les autres")
res, journal, envoyes = simuler(n_contacts=160, plafond=30)
verifie("120 envois (plafond atteint partout)", res["sent"] == 120, f"({res['sent']})")
verifie("40 reportés à demain (boîtes pleines)", res["reportes"] == 40, f"({res['reportes']})")
verifie("chaque boîte s'arrête à son plafond", all(v == 30 for v in envoyes.values()), str(envoyes))

print("\n3. La tranche de journée d'une campagne est respectée")
res, journal, envoyes = simuler(n_contacts=80, plafond=30, fin_minutes=30)
verifie("le lot rend la main à l'échéance", max(t for t, _, _ in journal) <= 30 * 60, f"(dernier envoi à {max(t for t, _, _ in journal) / 60:.0f} min)")
verifie("les non-servis repartent au prochain lot", res["sent"] + res["reportes"] == 80, f"({res['sent']} + {res['reportes']})")

print("\n4. Un BAT (hors lot de campagne) n'attend jamais : il ne doit pas geler l'API")
res, journal, envoyes = simuler(n_contacts=8, plafond=30, campagne="lcr-bat", ecart=1)
verifie("aucune attente : les contacts dont la boîte est en pause sont reportés", res["sent"] == 4 and res["reportes"] == 4,
        f"({res['sent']} envoyés, {res['reportes']} reportés)")

print("\n" + "=" * 62)
print(f"{len(ECHECS)} ÉCHEC(S) : " + ", ".join(ECHECS) if ECHECS else "Tout est vert.")
sys.exit(1 if ECHECS else 0)
