#!/usr/bin/env python3
"""garde_variables.py — aucun email ne part avec un trou dedans.

Deux défauts, tous deux constatés dans le code d'envoi avant le 2026-08-23 :

1. **La variable inconnue partait telle quelle.** `maildoso_backend._apply_tokens`
   remplaçait `{{prenom}}` et laissait `{{whatever}}` intact — le destinataire recevait
   les accolades. Et le motif ne couvrait QUE les doubles accolades : `{prenom}`,
   `[prenom]`, `[[prenom]]`, `%prenom%` traversaient sans même être vus.
2. **La variable vide laissait un trou.** « Bonjour , » était rustiné au cas par cas ;
   « chez  » ou « votre agence de  » ne l'étaient pas.

Le principe retenu, et il est volontairement brutal : **on ne répare pas un email douteux,
on ne l'envoie pas.** Un email sur deux mille qui part avec « Bonjour {{prenom}}, » coûte
plus cher que cent emails non envoyés — il ne se rattrape pas, il se lit.

Le module sert à deux moments, avec la même règle :
  - **à la pioche**, pour ne retenir que des contacts complets (le lot part plein) ;
  - **à l'envoi**, en dernier rideau sur le texte RENDU (le lot ne part pas troué).

Une variable peut être déclarée « tolérée à vide » : la phrase doit alors rester correcte
sans elle, et la ponctuation orpheline est nettoyée. La liste est courte et explicite —
tout le reste bloque.
"""
from __future__ import annotations

import re

# ── Ce qui ressemble à une variable non résolue ───────────────────────────────
# L'ordre n'a pas d'importance, tous les motifs sont cherchés. Les bornes de longueur
# évitent qu'un bloc de texte entre accolades ne soit pris pour une variable.
MOTIFS: list[tuple[str, str]] = [
    ("accolades doubles", r"\{\{[^{}]{0,120}\}\}"),
    ("accolade simple",   r"(?<![{$])\{\s*[A-Za-z_][A-Za-z0-9_.\- ]{0,60}\}(?!\})"),
    ("crochets doubles",  r"\[\[[^\[\]]{0,120}\]\]"),
    ("crochet simple",    r"(?<!\[)\[\s*[A-Za-z_][A-Za-z0-9_.\- ]{0,60}\](?!\])"),
    ("pourcentages",      r"%[A-Za-z_][A-Za-z0-9_]{0,40}%"),
    ("dollar-accolade",   r"\$\{[^}]{0,80}\}"),
    ("chevrons",          r"<<\s*[A-Za-z_][A-Za-z0-9_.\- ]{0,60}>>"),
]

# Les variables que les gabarits savent utiliser. Doit rester alignée sur
# `maildoso_backend._apply_tokens` : une variable connue de l'un et pas de l'autre est
# soit remplacée sans être contrôlée, soit refusée alors qu'elle est valide.
VARIABLES_CONNUES = {
    "prenom", "firstname", "firstName", "nom", "lastname", "lastName",
    "entreprise", "societe", "company", "ville", "city",
    "expediteur_prenom", "expediteur_nom",
    "UNSUBSCRIBE_LINK", "unsubscribe",
}

# Peuvent valoir vide SANS rendre la phrase fausse — la ponctuation orpheline est
# nettoyée juste après. Toute autre variable vide bloque l'envoi au destinataire.
TOLEREES_A_VIDE = {"prenom", "firstname", "firstName", "expediteur_nom"}

# D'où vient la valeur de chaque variable, côté contact.
_SOURCE = {
    "prenom": ("prenom",), "firstname": ("prenom",), "firstName": ("prenom",),
    "nom": ("nom",), "lastname": ("nom",), "lastName": ("nom",),
    "entreprise": ("societe", "entreprise"), "societe": ("societe",),
    "company": ("societe",),
    "ville": ("city", "ville"), "city": ("city",),
}

_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

# Blocs où les accolades et les crochets sont du code, pas des variables : une feuille de
# style contient `{ }` à chaque règle, un script en contient partout. On les retire avant
# de chercher, sinon tout gabarit HTML serait refusé.
_CODE = re.compile(r"<style\b[^>]*>.*?</style>|<script\b[^>]*>.*?</script>|<!--.*?-->",
                   re.I | re.S)


def variables_utilisees(gabarit: str) -> set[str]:
    """Les variables `{{...}}` qu'un gabarit référence."""
    return set(_VARIABLE.findall(gabarit or ""))


def variables_inconnues(gabarit: str) -> set[str]:
    """Les variables référencées qu'aucun moteur ne sait remplacer.

    À contrôler à l'enregistrement du message, pas seulement à l'envoi : c'est le seul
    moment où quelqu'un peut encore corriger la faute de frappe.
    """
    return variables_utilisees(gabarit) - VARIABLES_CONNUES


def _valeur(variable: str, contact: dict) -> str:
    for cle in _SOURCE.get(variable, (variable,)):
        v = (contact or {}).get(cle)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def manques(gabarits: list[str], contact: dict) -> list[str]:
    """Les variables que CE contact laisserait vides — hors tolérées.

    Utilisé à la pioche pour écarter un contact avant même de composer son message :
    mieux vaut un lot plus petit qu'un lot troué.
    """
    besoins: set[str] = set()
    for g in gabarits:
        besoins |= variables_utilisees(g or "")
    return sorted(v for v in besoins
                  if v in _SOURCE and v not in TOLEREES_A_VIDE and not _valeur(v, contact))


def nettoyer_ponctuation(s: str) -> str:
    """Referme les trous laissés par une variable tolérée vide.

    « Bonjour , » → « Bonjour, » ; « chez  ! » → « chez ! » ; les espaces doubles
    disparaissent. Sur le HTML on ne touche pas aux espaces multiples (ils y sont
    parfois significatifs pour la mise en page) : seule la ponctuation orpheline part.
    """
    if not s:
        return s
    # L'ordre compte : on retire d'abord les paires devenues vides, sinon elles laissent
    # l'espace double que l'étape suivante était censée absorber.
    s = re.sub(r"\(\s*\)|«\s*»|\"\s*\"", "", s)    # parenthèses et guillemets vides
    s = re.sub(r"[ \t]+([,.;:!?])", r"\1", s)     # espace avant ponctuation
    s = re.sub(r"([,;:])\s*\1+", r"\1", s)         # ponctuation doublée
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip() if s.strip() != s.strip(" ") else s


def controler_rendu(sujet: str, texte: str, html: str | None = None) -> list[dict]:
    """Dernier rideau : ce qui reste de variable dans le message RENDU.

    Rend la liste des problèmes ; vide = le message peut partir. Le HTML est débarrassé
    de ses feuilles de style et de ses scripts avant l'examen — sans quoi la moindre
    règle CSS passerait pour une variable oubliée.
    """
    problemes: list[dict] = []
    for champ, contenu, est_html in (("sujet", sujet, False), ("texte", texte, False),
                                     ("html", html, True)):
        if not contenu:
            continue
        a_examiner = _CODE.sub(" ", contenu) if est_html else contenu
        for nom, motif in MOTIFS:
            for m in re.finditer(motif, a_examiner):
                extrait = m.group(0)
                # Une entité ou une accolade isolée dans du texte libre n'est pas une
                # variable : on exige un identifiant plausible à l'intérieur.
                if not re.search(r"[A-Za-z_]", extrait):
                    continue
                problemes.append({"champ": champ, "type": nom, "extrait": extrait[:80]})
    return problemes


def verifier_avant_envoi(sujet: str, texte: str, html: str | None,
                         contact: dict | None = None,
                         gabarits: list[str] | None = None) -> dict:
    """Verdict complet pour UN destinataire.

    `{"ok": bool, "motifs": [...]}` — `ok=False` veut dire « ne pas envoyer à celui-là »,
    jamais « arrêter le lot » : un contact incomplet ne doit pas priver les autres.
    """
    motifs: list[str] = []
    if gabarits and contact is not None:
        for v in manques(gabarits, contact):
            motifs.append(f"variable vide : {v}")
    for p in controler_rendu(sujet, texte, html):
        motifs.append(f"{p['type']} non résolu dans le {p['champ']} : {p['extrait']}")
    return {"ok": not motifs, "motifs": motifs}
