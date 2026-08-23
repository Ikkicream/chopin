#!/usr/bin/env python3
"""La montée en charge doit protéger le domaine, pas seulement compter les envois.

La règle d'origine ne regardait que le taux d'erreur SMTP — nul depuis toujours (1 462
envois journalisés, zéro erreur). Elle ne pouvait donc que monter. Une boîte en train de
se faire classer en indésirables voyait son volume augmenter chaque jour.

Chaque cas ci-dessous est une boîte en train de se dégrader : la décision attendue est
celle qui coûte du volume aujourd'hui pour garder le domaine demain.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def lance() -> int:
    import maildoso_ramp as mr
    import sante_envoi as se

    sain = {"concluant": True, "taux_ouverture": 40.0, "taux_rebond": 0.2,
            "taux_plainte": 0.0, "envoyes": 120}

    print("Ce qui doit FAIRE BAISSER le plafond")
    cap, raison = mr._decide(40, 120, 0, 30, dict(sain, taux_plainte=0.5))
    verifie("plainte à 0,5 % → cap divisé par deux", cap == 20, f"({cap}, {raison})")
    cap, raison = mr._decide(40, 120, 0, 30, dict(sain, taux_rebond=6.0))
    verifie("rebond à 6 % → -10", cap == 30, f"({cap}, {raison})")
    cap, raison = mr._decide(40, 120, 0, 30, dict(sain, taux_ouverture=2.0))
    verifie("ouverture à 2 % → -10", cap == 30, f"({cap}, {raison})")
    cap, raison = mr._decide(40, 100, 20, 30, sain)
    verifie("erreurs SMTP à 17 % → -10", cap == 30, f"({cap}, {raison})")
    cap, _ = mr._decide(12, 120, 0, 10, dict(sain, taux_plainte=5.0))
    verifie("le plancher tient", cap == mr.CAP_MIN, f"({cap})")

    print("\nPriorité : la plainte l'emporte sur tout le reste")
    cap, raison = mr._decide(40, 120, 0, 30,
                             {"concluant": True, "taux_ouverture": 1.0,
                              "taux_rebond": 9.0, "taux_plainte": 1.0, "envoyes": 120})
    verifie("trois signaux → la plainte décide", cap == 20 and "plainte" in raison,
            f"({cap}, {raison})")

    print("\nCe qui doit FAIRE MONTER — ou surtout, ne pas faire monter")
    cap, raison = mr._decide(20, 120, 0, 15, sain)
    verifie("boîte saine et bien utilisée → +5", cap == 25, f"({cap}, {raison})")
    cap, raison = mr._decide(20, 12, 0, 15, dict(sain, concluant=False, envoyes=12))
    verifie("volume trop faible → on ne monte PAS", cap == 20, f"({cap}, {raison})")
    cap, raison = mr._decide(20, 120, 0, 15, None)
    verifie("relevé indisponible → on ne monte PAS", cap == 20, f"({cap}, {raison})")
    cap, raison = mr._decide(40, 120, 0, 35, sain)
    verifie("plafond respecté", cap == 40, f"({cap}, {raison})")
    cap, raison = mr._decide(20, 120, 0, 3, sain)
    verifie("boîte peu utilisée → inchangé", cap == 20, f"({cap}, {raison})")

    print("\nLes seuils viennent d'un seul endroit")
    verifie("seuils partagés avec sante_envoi",
            (mr.SEUIL_OUVERTURE, mr.SEUIL_REBOND, mr.SEUIL_PLAINTE)
            == (se.SEUIL_OUVERTURE, se.SEUIL_REBOND, se.SEUIL_PLAINTE))

    print("\nListes noires : un refus de consultation n'est pas une inscription")
    faux = {"hote": "x", "ips": ["8.8.8.8"], "inscrit_dans": [],
            "non_verifiables": ["zen.spamhaus.org"], "problemes": []}
    verifie("aucune inscription déclarée sur un refus", not faux["inscrit_dans"])
    reel = se.controler_listes_noires("smtp.maildoso.com")
    verifie("le serveur d'envoi n'est PAS déclaré en liste noire à tort",
            not reel["inscrit_dans"],
            f"({len(reel['inscrit_dans'])} inscription(s), "
            f"{len(reel.get('non_verifiables') or [])} liste(s) non consultable(s))")

    print("\nLa forme du domaine expéditeur")
    d = se.controler_domaine("leclient-roi.com")
    verifie("SPF présent", bool(d["spf"]), f"({d['spf']})")
    verifie("DKIM présent", bool(d["dkim"]), f"({d['dkim']})")
    verifie("DMARC présent", bool(d["dmarc"]), f"({d['dmarc']})")
    verifie("MX présent", bool(d["mx"]))
    verifie("aucun problème de configuration", not d["problemes"], f"({d['problemes']})")

    print("\nLes taux se mesurent sur les destinataires de la boîte, pas sur ses événements")
    g = se.taux("lcr")
    verifie("le taux global est renseigné", g["taux_ouverture"] is not None,
            f"({g['taux_ouverture']} % sur {g['envoyes']} envois)")
    import expediteur as ex
    for b in ex.boites("lcr"):
        t = se.taux("lcr", mailbox=b["email"])
        verifie(f"{b['email'].split('@')[0]} : ouverture non nulle",
                (t["taux_ouverture"] or 0) > 0,
                f"({t['taux_ouverture']} % sur {t['envoyes']} envois)")

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("La montée en charge réagit aux vrais signaux de délivrabilité.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
