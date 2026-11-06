#!/usr/bin/env python3
"""name_extract.py — Devine le prénom (et le nom) depuis une adresse email professionnelle.

Pourquoi : 7 des 10 modèles d'email utilisent `{{prenom}}`, et le moteur d'envoi le remplace
par une chaîne vide quand il est absent. Aucun contact scrapé n'ayant de prénom, tous les
cold emails partaient avec « Bonjour, ». Un commercial au téléphone a le même problème.

**Le dictionnaire fait toute la valeur.** Sans lui, l'extraction naïve produit « Bonjour
Graphisme », « Bonjour Assistante », « Bonjour Fontainebleau » — pire que pas de prénom du
tout, parce que ça signale un envoi automatisé mal fait. On n'accepte donc QUE des mots
présents dans `data/ref/prenoms.tsv` (data.gouv, filtré à >= 50 naissances), et on
compare au besoin leur fréquence comme PATRONYME : « dupont » compte 50 naissances contre
8 033 porteurs du nom.

Règle de prudence générale : dans le doute, on ne renseigne rien.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DICO_FICHIER = BASE_DIR / "data" / "ref" / "prenoms.tsv"

# prenom -> (naissances, porteurs_du_patronyme)
_DICO: dict[str, tuple[int, int]] | None = None

# Parties locales qui désignent une fonction ou un lieu, jamais une personne. Elles ne sont
# pas dans le dictionnaire, mais les lister évite de les traiter comme des noms de famille
# dans la forme « prenom.nom ».
GENERIQUES = {
    "contact", "info", "infos", "hello", "bonjour", "accueil", "agence", "gerance",
    "syndic", "commercial", "commerce", "direction", "secretariat", "admin", "service",
    "services", "mail", "email", "courrier", "location", "gestion", "transaction",
    "immobilier", "immo", "rh", "compta", "comptabilite", "facturation", "devis",
    "support", "siege", "boutique", "magasin", "atelier", "bureau", "cabinet", "groupe",
    "societe", "sav", "reservation", "booking", "rdv", "planning", "marketing",
    "communication", "presse", "recrutement", "emploi", "stage", "partenariat",
    "clients", "client", "vente", "ventes", "achat", "achats", "logistique", "technique",
    "qualite", "production", "export", "assistante", "assistant", "secretaire", "graphisme",
    "webmaster", "noreply", "no-reply", "postmaster", "abuse", "dpo", "rgpd",
}


def _sans_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").strip().lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def dictionnaire() -> dict[str, tuple[int, int]]:
    """Prénoms connus et leurs deux fréquences, chargés une fois par process."""
    global _DICO
    if _DICO is None:
        d: dict[str, tuple[int, int]] = {}
        try:
            for ligne in DICO_FICHIER.read_text(encoding="utf-8").splitlines():
                if not ligne.strip() or ligne.startswith("#"):
                    continue
                parts = ligne.split("\t")
                if len(parts) == 3:
                    d[parts[0]] = (int(parts[1]), int(parts[2]))
        except Exception as e:  # noqa: BLE001
            # Sans dictionnaire, on n'extrait RIEN : mieux vaut ne pas personnaliser que
            # d'écrire « Bonjour Trocadéro ». L'incident est signalé, pas avalé.
            print(f"[name_extract] dictionnaire illisible ({e}) — extraction désactivée",
                  flush=True)
        _DICO = d
    return _DICO


def est_prenom(mot: str) -> bool:
    """Le mot figure-t-il parmi les prénoms connus ?"""
    return mot in dictionnaire() and mot not in GENERIQUES


def prenom_dominant(mot: str) -> bool:
    """Le mot est-il PLUS souvent un prénom qu'un nom de famille ?

    Exigé quand la position ne renseigne pas : dans « dupont@agence.fr », rien ne dit que
    c'est un prénom, et 8 033 personnes portent Dupont comme patronyme contre 50 qui le
    portent comme prénom. Dans « marie.dupont@ », en revanche, la position tranche.
    """
    naiss, porteurs = dictionnaire().get(mot, (0, 0))
    return naiss >= 50 and naiss >= porteurs


def _capitaliser(mot: str) -> str:
    """« jean-pierre » → « Jean-Pierre », « o'brien » → « O'Brien »."""
    out = []
    for bloc in re.split(r"([-'])", mot):
        out.append(bloc if bloc in "-'" else bloc.capitalize())
    return "".join(out)


def extraire(email: str) -> dict:
    """Prénom et nom devinés depuis l'adresse.

    Retourne `{"prenom": str|None, "nom": str|None, "forme": str, "confiance": str}`.
    `forme` documente la règle qui a décidé — indispensable pour auditer un rattrapage de
    masse sans relire les 3 500 adresses une par une.
    """
    vide = {"prenom": None, "nom": None, "forme": "aucune", "confiance": "nulle"}
    email = (email or "").strip().lower()
    if "@" not in email:
        return vide
    local = _sans_accents(email.split("@", 1)[0])
    local = re.sub(r"\d+$", "", local)          # « marie2 » → « marie »
    if not local or len(local) > 40:
        return vide

    dico = dictionnaire()
    if not dico:
        return vide

    # Forme 1 — deux mots séparés : « prenom.nom » ou « nom.prenom ».
    m = re.match(r"^([a-z]{2,})[._-]([a-z]{2,})$", local)
    if m:
        a, b = m.group(1), m.group(2)
        if est_prenom(a) and b not in GENERIQUES:
            return {"prenom": _capitaliser(a), "nom": _capitaliser(b),
                    "forme": "prenom.nom", "confiance": "haute"}
        # L'ordre inverse existe (« dupont.jean ») mais reste minoritaire : on l'accepte
        # seulement si le second mot est un prénom ET le premier n'en est pas un, sans quoi
        # « pierre.paul » serait arbitrairement retourné.
        if est_prenom(b) and a not in dico and a not in GENERIQUES:
            return {"prenom": _capitaliser(b), "nom": _capitaliser(a),
                    "forme": "nom.prenom", "confiance": "moyenne"}
        return vide

    # Forme 2 — initiale + nom : « j.dupont ». Le prénom reste inconnu (une initiale ne
    # suffit pas à s'adresser à quelqu'un), mais le NOM est exploitable pour la recherche.
    m = re.match(r"^([a-z])[._-]([a-z]{3,})$", local)
    if m and m.group(2) not in GENERIQUES:
        # Après une initiale, le second mot est le NOM DE FAMILLE — c'est la convention
        # dominante des adresses professionnelles françaises (« j.dupont »). On ne le
        # traite JAMAIS comme un prénom : « Bonjour Dupont » est pire que « Bonjour ».
        return {"prenom": None, "nom": _capitaliser(m.group(2)),
                "forme": "initiale.nom", "confiance": "moyenne"}

    # Forme 3 — un seul mot. On n'accepte que s'il est au dictionnaire : c'est ici que se
    # jouent tous les faux positifs (« assistante », « fontainebleau », « projardins »).
    if re.match(r"^[a-z]{3,}$", local):
        if prenom_dominant(local) and local not in GENERIQUES:
            return {"prenom": _capitaliser(local), "nom": None,
                    "forme": "prenom_seul", "confiance": "haute"}
        return vide

    # Forme 4 — prénom collé au nom, « jeandupont ». On teste les préfixes connus, du plus
    # long au plus court pour ne pas confondre « Jean » avec « Jeanne ».
    if re.match(r"^[a-z]{6,}$", local):
        for taille in range(min(12, len(local) - 2), 2, -1):
            tete = local[:taille]
            if prenom_dominant(tete) and tete not in GENERIQUES:
                return {"prenom": _capitaliser(tete), "nom": _capitaliser(local[taille:]),
                        "forme": "prenomnom_colles", "confiance": "faible"}
    return vide


if __name__ == "__main__":
    import sys
    tests = sys.argv[1:] or [
        "helene.aubinais@cbnews.fr", "gerance@anbadele-immo.com", "assistante@labelleagence.immo",
        "j.dupont@immo.fr", "pierrick@bppimmo.fr", "graphisme@animage.fr",
        "fontainebleau@dafonseca.com", "m.claire@agence.fr", "jeandupont@immo.fr",
        "monts-jura@lamontagne-immo.com",
    ]
    print(f"dictionnaire : {len(dictionnaire())} prénoms\n")
    for t in tests:
        r = extraire(t)
        rendu = f"{r['prenom'] or '—'} / {r['nom'] or '—'}"
        print(f"  {t:42s} {rendu:32s} [{r['forme']}, {r['confiance']}]")
