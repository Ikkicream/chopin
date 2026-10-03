#!/usr/bin/env python3
"""Une seule fenêtre d'envoi, et elle est contrôlée au point de passage (Lot F, 2026-08-26).

Trois écritures de la même mécanique : `deliverability_agent.within_send_window` pour les
campagnes (08:01–17:59), `mozart.fenetre_ouverte` pour les scénarios (09:01–18:30), et le
rythme intra-lot de `maildoso_backend._cadence`. Elles différaient d'une heure de chaque
côté, sans raison retrouvée. Camille a tranché le 26/08 : les scénarios s'alignent.

**Mais la duplication n'était pas le vrai danger.** Ni `send_email` ni `send_batch` ne
regardaient l'heure : ce sont les APPELANTS qui le faisaient. Un nouveau chemin d'appel —
script de rattrapage, bouton d'écran, cron ajouté un soir — envoyait donc à 3 h du matin
sans que rien ne s'y oppose. C'est ce trou-là que ce fichier protège.

Second volet : la cadence par boîte vivait dans un dictionnaire EN RAM. L'écart de quatre
minutes tenait à l'intérieur d'un lot, jamais entre le dispatch (cron 8h30) et le tick
Mozart (cron horaire) — deux process, deux dictionnaires vides.
"""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

PARIS = ZoneInfo("Europe/Paris")
ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


import fenetre_envoi as fen
import deliverability_agent as da
import mozart as mz

print("\nLes deux fenêtres n'en font plus qu'une")
verifie("campagnes et scénarios ont les mêmes bornes",
        (fen.PROFILS["campagne"]["debut"], fen.PROFILS["campagne"]["fin"])
        == (fen.PROFILS["scenario"]["debut"], fen.PROFILS["scenario"]["fin"]),
        f"({fen.PROFILS['campagne']['debut']}–{fen.PROFILS['campagne']['fin']})")
verifie("et les mêmes jours",
        fen.PROFILS["campagne"]["jours"] == fen.PROFILS["scenario"]["jours"])
verifie("la règle du projet est respectée (lun-sam, 08:01–17:59)",
        fen.PROFILS["campagne"]["debut"] == "08:01"
        and fen.PROFILS["campagne"]["fin"] == "17:59"
        and 6 not in fen.PROFILS["campagne"]["jours"])
verifie("Mozart ne garde pas sa propre copie des bornes",
        (mz.FENETRE_DEBUT, mz.FENETRE_FIN)
        == (fen.PROFILS["scenario"]["debut"], fen.PROFILS["scenario"]["fin"]),
        f"({mz.FENETRE_DEBUT}–{mz.FENETRE_FIN})")

print("\nMême verdict, à la minute près")
heures = [(7, 30), (8, 0), (8, 1), (8, 2), (12, 0), (17, 59), (18, 0), (18, 15), (23, 0)]
ecarts = []
for h, m in heures:
    q = datetime(2026, 8, 26, h, m, tzinfo=PARIS)     # un mercredi
    if da.within_send_window(q)[0] != mz.fenetre_ouverte(q)[0]:
        ecarts.append(f"{h:02d}:{m:02d}")
verifie("campagnes et scénarios répondent pareil", not ecarts, f"({ecarts})")

q = datetime(2026, 8, 26, 8, 0, tzinfo=PARIS)
verifie("08:00 est encore trop tôt", not fen.ouverte("campagne", q)[0])
q = datetime(2026, 8, 26, 8, 1, tzinfo=PARIS)
verifie("08:01 ouvre", fen.ouverte("campagne", q)[0])
q = datetime(2026, 8, 26, 17, 59, tzinfo=PARIS)
verifie("17:59 est encore ouvert", fen.ouverte("campagne", q)[0])
q = datetime(2026, 8, 26, 18, 0, tzinfo=PARIS)
verifie("18:00 est fermé", not fen.ouverte("campagne", q)[0])
q = datetime(2026, 8, 30, 12, 0, tzinfo=PARIS)       # un dimanche
verifie("le dimanche est fermé toute la journée", not fen.ouverte("campagne", q)[0])

print("\nLe report vise la prochaine ouverture, pas l'heure suivante")
p = fen.prochaine_ouverture("campagne", datetime(2026, 8, 26, 18, 31, tzinfo=PARIS))
verifie("un refus de 18h31 renvoie au lendemain 08:01",
        (p.day, p.hour, p.minute) == (27, 8, 1), f"({p})")
p = fen.prochaine_ouverture("campagne", datetime(2026, 8, 29, 19, 0, tzinfo=PARIS))
verifie("un refus du samedi soir saute le dimanche",
        p.weekday() != 6 and (p.day, p.hour) == (31, 8), f"({p:%a %d %H:%M})")

print("\nQuelle fenêtre pour quel envoi — et surtout : laquelle pour AUCUN")
verifie("un lot de campagne suit la fenêtre des campagnes",
        fen.profil_pour("lcr-fd0dc221-b44-2026-08-26", None) == "campagne")
verifie("un pas de scénario suit celle des scénarios",
        fen.profil_pour("lcr-mozart-abcd1234-2026-08-26", "mozart") == "scenario")
verifie("un BAT ne suit AUCUNE fenêtre (il répond à un geste immédiat)",
        fen.profil_pour("lcr-bat", None) is None)
verifie("un envoi sans campagne non plus", fen.profil_pour("", None) is None)
verifie("un transactionnel non plus", fen.profil_pour(None, None) is None)

print("\nLe contrôle est DANS send_email, pas chez ses appelants")
src = (RACINE / "scripts" / "maildoso_backend.py").read_text()
i_def = src.index("def send_email(")
i_smtp = src.index("msg[\"From\"]")
corps = src[i_def:i_smtp]
verifie("send_email consulte la fenêtre", "fenetre_envoi.ouverte(" in corps)
verifie("il choisit le profil d'après l'envoi", "profil_pour(campaign_id, usage)" in corps)
verifie("un refus est un REPORT, pas un échec",
        '"reporte": True' in corps and "hors fenêtre d'envoi" in corps)
verifie("le contrôle précède l'écriture SMTP",
        corps.index("fenetre_envoi.ouverte(") < len(corps))

print("\nLa cadence par boîte survit à un changement de process")
verifie("l'écart minimum ne se lit plus dans la mémoire seule",
        "_secondes_depuis_dernier_envoi" in src)
i_fn = src.index("def _secondes_depuis_dernier_envoi")
fn = src[i_fn:i_fn + 1400]
verifie("elle interroge le journal", "email_events" in fn and "mailbox = %(m)s" in fn)
verifie("elle ne compte que les envois réels", "event_type = 'sent'" in fn)
verifie("la mémoire du process reste en repli", "_DERNIER_ENVOI.get(mailbox)" in fn)
verifie("une boîte jamais utilisée n'est pas retenue", "return None" in fn)
verifie("l'écart par boîte reste à 4 minutes",
        __import__("maildoso_backend").ECART_MIN_BOITE == 240)

print("\n" + "=" * 62)
if ECHECS:
    print(f"{len(ECHECS)} ÉCHEC(S) : " + ", ".join(ECHECS))
    raise SystemExit(1)
print("Tout est vert.")
