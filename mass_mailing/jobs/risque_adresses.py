#!/usr/bin/env python3
"""mass_mailing/jobs/risque_adresses.py — agent « adresses à risque » (Camille, 30/09/2026).

But : estimer AVANT l'envoi la probabilité qu'une adresse rebondisse en HARD, pour écarter ou
envoyer en dernier les adresses à risque, même quand Mailnjoy les a déclarées valides.

Pourquoi Mailnjoy ne suffit pas (analyse du 30/09, skill `risque-adresses`) : une vérification
SMTP demande au serveur « acceptes-tu cette adresse ? » sans envoyer. Yahoo, AOL et plusieurs
fournisseurs d'accès répondent « oui » à tout le monde puis refusent au moment de l'envoi
(« mailbox is disabled », « blocked due to inactivity ») : le vérificateur ne peut pas le voir.

Le modèle : Bayes naïf à lissage de Laplace, appris sur NOS envois réels (logs Sweego du compte,
table `rebonds`). Il est volontairement simple et lisible : chaque facteur a un poids qu'on peut
expliquer (« laposte.net : ×3,1 »). Il se réapprend à chaque appel de `apprendre()`.

    risque = P(hard | domaine, messagerie, verdict Mailnjoy, forme de l'adresse)

« Déjà ouvert » a été retiré le 30/09 (revue) : il venait des mêmes envois que le résultat à prédire
(fuite de la cible, AUC gonflée). Le paramètre `deja_ouvert` de facteurs() est gardé mais ignoré.

Niveaux : faible < 5 % ≤ moyen < 15 % ≤ élevé < 30 % ≤ très élevé.
Les adresses DÉJÀ en liste noire (hard, soft, plainte, désinscription) ne sont pas scorées : exclues.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import pg, sweego  # noqa: E402
from jobs.capacite import groupe_de  # noqa: E402

VERSION = "2026-09-30-v3"
ANGLE_MORT_MAILNJOY = {"yahoo"}      # yahoo.*, aol.com, ymail (jobs/capacite.groupe_de)
SEUILS = ((0.05, "faible"), (0.15, "moyen"), (0.30, "eleve"), (1.01, "tres_eleve"))
LIBELLES = {"faible": "faible", "moyen": "moyen", "eleve": "élevé", "tres_eleve": "très élevé"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS risque_modele (
    version     TEXT        PRIMARY KEY,
    appris_le   TIMESTAMPTZ NOT NULL DEFAULT now(),
    modele      JSONB       NOT NULL,
    evaluation  JSONB
)
"""


# ── Facteurs d'une adresse (fonction pure) ────────────────────────────────────

def facteurs(email: str, mailnjoy: str | None = None, deja_ouvert: bool = False) -> dict[str, str]:
    local, _, dom = email.lower().partition("@")
    chiffres = len(re.findall(r"\d", local))
    g = groupe_de(dom)
    verdict = mailnjoy.upper() if mailnjoy else "non_verifie"
    # Angle mort de la vérification SMTP (30/09 : 0 hard sur 1 869 « VALID/SAFE » ailleurs, 5 sur 50
    # chez Yahoo/AOL) : Yahoo accepte toutes les adresses au contrôle puis refuse les comptes désactivés
    # à l'envoi. Le verdict y est donc un facteur À PART, avec son propre poids appris.
    if g in ANGLE_MORT_MAILNJOY and verdict != "non_verifie":
        verdict += "·" + g
    return {
        "domaine": dom,
        "messagerie": g,
        "mailnjoy": verdict,
        "chiffres": "0" if chiffres == 0 else ("1-3" if chiffres <= 3 else "4+"),
        "separateurs": str(len(re.findall(r"[._-]", local)) if len(re.findall(r"[._-]", local)) < 2 else "2+"),
    }


# ── Données d'apprentissage : nos envois réels ─────────────────────────────────

def _historique_sweego(debut: str) -> dict[str, dict]:
    """Par adresse : délivrée ? hard ? ouverte par un humain ? (logs Sweego, tout le compte)."""
    from jobs.rebonds import DOMAINES_ENVOI, _texte, classer
    par: dict[str, dict] = {}
    for dom in DOMAINES_ENVOI:
        off = 0
        while True:
            r = requests.post(sweego.SWEEGO_URL + "/logs", headers=sweego._headers(), timeout=180, json={
                "channel": "email", "domains": [dom], "start_date": debut, "size": 500, "offset": off})
            if r.status_code == 422:
                break
            r.raise_for_status()
            res = r.json().get("result") or []
            for x in res:
                e = (x.get("email_to") or "").strip().lower()
                if "@" not in e:
                    continue
                a = par.setdefault(e, {"ok": 0, "hard": 0, "ouvert": False})
                if x.get("status") == "undelivered":
                    if classer(_texte(x), str(x.get("email_state") or ""), x.get("bounce_type"))[0] == "hard":
                        a["hard"] += 1
                elif x.get("status") in ("delivered", "opened-proxy", "opened-human", "clicked-proxy", "clicked-human"):
                    # Seulement une LIVRAISON prouvée : « queued » (report temporaire) n'est pas une issue.
                    a["ok"] += 1
                    a["ouvert"] |= x.get("status") in ("opened-human", "clicked-human")
            if len(res) < 500:
                break
            off += 500
    return par


def _verdicts_mailnjoy() -> dict[str, str]:
    mj: dict[str, str] = {}
    for r in pg.lignes("SELECT lower(email) e, mailnjoy_check->>'result' v FROM public.contacts WHERE mailnjoy_check IS NOT NULL"):
        mj[r["e"]] = r["v"]
    for r in pg.lignes("SELECT email_normalized e, validation_provider_status v FROM recipients WHERE validation_provider_status IS NOT NULL"):
        mj.setdefault(r["e"], r["v"])
    return mj


def jeu_de_donnees(debut: str = "2026-08-01") -> list[tuple[dict, int]]:
    """[(facteurs, 1 si hard sinon 0)]. Une adresse sans aucune issue connue (seulement des refus liés à
    l'IP) est écartée : on ne sait pas si elle est bonne. Le « déjà ouvert » est exclu de l'apprentissage
    pour les adresses en hard (une ouverture passée ne prouve pas que la boîte vit encore)."""
    mj = _verdicts_mailnjoy()
    out = []
    for e, a in _historique_sweego(debut).items():
        if a["hard"]:
            out.append((facteurs(e, mj.get(e), False), 1))
        elif a["ok"]:
            out.append((facteurs(e, mj.get(e), a["ouvert"]), 0))
    return out


# ── Bayes naïf lisible ─────────────────────────────────────────────────────────

def entrainer(donnees: list[tuple[dict, int]], alpha: float = 2.0) -> dict:
    n1 = sum(y for _, y in donnees)
    n0 = len(donnees) - n1
    comptes: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for f, y in donnees:
        for k, v in f.items():
            comptes[k][v][y] += 1
    poids: dict[str, dict[str, float]] = {}
    for k, vals in comptes.items():
        nv = len(vals) + 1          # +1 : valeur jamais vue
        poids[k] = {}
        for v, (c0, c1) in vals.items():
            if k == "domaine" and c0 + c1 < 30:
                continue            # domaine rare : on s'en remet à la messagerie
            p1 = (c1 + alpha) / (n1 + alpha * nv)
            p0 = (c0 + alpha) / (n0 + alpha * nv)
            poids[k][v] = round(math.log(p1 / p0), 4)
    # Le domaine et la messagerie portent la même information : on ne garde la messagerie que
    # pour les domaines rares (sinon double compte).
    return {"version": VERSION, "a_priori": round(math.log((n1 + 1) / (n0 + 1)), 4), "poids": poids,
            "n": len(donnees), "hard": n1}


def probabilite(modele: dict, f: dict[str, str]) -> tuple[float, list[tuple[str, float]]]:
    """(probabilité de hard, [(facteur lisible, multiplicateur)] triés par effet)."""
    P = modele["poids"]
    lo = modele["a_priori"]
    effets = []
    for k, v in f.items():
        if k == "messagerie" and f["domaine"] in P.get("domaine", {}):
            continue
        w = P.get(k, {}).get(v)
        if w is None:
            continue
        lo += w
        effets.append((f"{k} = {v}", w))
    p = 1 / (1 + math.exp(-lo))
    # Tri sur le poids BRUT, arrondi seulement à l'affichage (revue du 30/09 : exp(-5,4) arrondi à 0 → log(0)).
    return p, [(f, round(math.exp(w), 3)) for f, w in sorted(effets, key=lambda x: -abs(x[1]))]


def niveau(p: float) -> str:
    return next(n for s, n in SEUILS if p < s)


def auc(scores: list[tuple[float, int]]) -> float:
    """AUC de Mann-Whitney, rangs MOYENS pour les ex æquo (fréquents avec des facteurs catégoriels)."""
    s = sorted(scores, key=lambda x: x[0])
    pos = sum(y for _, y in s)
    neg = len(s) - pos
    somme, i = 0.0, 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1][0] == s[i][0]:
            j += 1
        rang_moyen = (i + j) / 2 + 1
        somme += rang_moyen * sum(y for _, y in s[i:j + 1])
        i = j + 1
    return (somme - pos * (pos + 1) / 2) / (pos * neg) if pos and neg else float("nan")


def evaluer(donnees: list[tuple[dict, int]], graine: int = 7) -> dict:
    random.Random(graine).shuffle(donnees)
    coupe = int(len(donnees) * 0.7)
    m = entrainer(donnees[:coupe])
    test = [(probabilite(m, f)[0], y) for f, y in donnees[coupe:]]
    par_niv: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for p, y in test:
        par_niv[niveau(p)][0] += 1
        par_niv[niveau(p)][1] += y
    return {"auc": round(auc(test), 3), "test": len(test),
            "par_niveau": {n: {"adresses": a, "hard": b, "taux": round(b / a, 3) if a else None}
                           for n, (a, b) in par_niv.items()}}


def apprendre(debut: str = "2026-08-01") -> dict:
    pg.ecrire(SCHEMA)
    d = jeu_de_donnees(debut)
    ev = evaluer(list(d))
    m = entrainer(d)
    pg.ecrire("""INSERT INTO risque_modele (version, modele, evaluation) VALUES (%(v)s, %(m)s, %(e)s)
                 ON CONFLICT (version) DO UPDATE SET modele = EXCLUDED.modele, evaluation = EXCLUDED.evaluation, appris_le = now()""",
              {"v": VERSION, "m": json.dumps(m), "e": json.dumps(ev)})
    return {"n": m["n"], "hard": m["hard"], **ev}


def modele_courant() -> dict | None:
    r = pg.ligne("SELECT modele FROM risque_modele ORDER BY appris_le DESC LIMIT 1")
    return r["modele"] if r else None


# ── Scorer une campagne ─────────────────────────────────────────────────────────

def scorer_campagne(campaign_id: str, seulement_restants: bool = True) -> dict:
    """Risque de chaque destinataire (encore à envoyer, par défaut). Lecture seule."""
    m = modele_courant()
    if not m:
        return {"erreur": "modèle pas encore appris : lancer apprendre()"}
    ouverts = {r["e"] for r in pg.lignes("""SELECT DISTINCT r.email_normalized e FROM recipients r
                                             WHERE r.opened_at IS NOT NULL""")}
    filtre = "AND r.send_status = 'queued'" if seulement_restants else ""
    lignes = pg.lignes(f"""SELECT r.id, r.email_normalized e, r.validation_provider_status v,
                                  EXISTS (SELECT 1 FROM suppressions s WHERE s.email_hash = r.email_hash AND s.scope = 'global') AS en_liste
                             FROM recipients r WHERE r.campaign_id = %(c)s {filtre}""", {"c": campaign_id})
    res = {"faible": 0, "moyen": 0, "eleve": 0, "tres_eleve": 0, "deja_en_liste_noire": 0}
    hard_attendus = 0.0
    detail = []
    for x in lignes:
        if x["en_liste"]:
            res["deja_en_liste_noire"] += 1
            continue
        p, eff = probabilite(m, facteurs(x["e"], x["v"], x["e"] in ouverts))
        res[niveau(p)] += 1
        hard_attendus += p
        detail.append({"id": x["id"], "domaine": x["e"].split("@")[1], "p": round(p, 3), "niveau": niveau(p), "facteurs": eff[:3]})
    return {"version": m["version"], "adresses": len(lignes), "par_niveau": res,
            "hard_attendus": round(hard_attendus), "detail": sorted(detail, key=lambda d: -d["p"])}


if __name__ == "__main__":
    print(json.dumps(apprendre(sys.argv[1] if len(sys.argv) > 1 else "2026-08-01"), ensure_ascii=False, indent=1))
