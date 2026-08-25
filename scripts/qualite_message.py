#!/usr/bin/env python3
"""qualite_message.py — ce qui fait tomber un email dans les indésirables.

Trois contrôles issus du guide de délivrabilité de Maildoso (analysé le 2026-08-25), qui
n'existaient nulle part dans la plateforme :

1. **Les mots qui déclenchent les filtres.** Le guide demande « zéro tolérance ». Le lint
   existant (`email_generator.BANNED`) traque des CLICHÉS de cold email — « je me permets »,
   « cordialement » — ce qui est une question de style, pas de délivrabilité. Ce module
   traite l'autre sujet : le vocabulaire commercial que les filtres notent.

2. **Le spintax.** Deux destinataires ne doivent jamais recevoir exactement le même texte :
   un message identique envoyé mille fois se reconnaît par empreinte. Le tirage est
   DÉTERMINISTE par destinataire — sans quoi une relance ne ressemblerait pas au premier
   message, et un renvoi produirait un texte différent du message déjà reçu.

3. **Les liens du premier message.** Le guide demande de les éviter au premier contact.
   Mesuré le 2026-08-25 : 2,4 liens en moyenne sur les huit premiers messages de LCR.

Le module ne réécrit RIEN tout seul. Il constate, et rend des motifs lisibles : c'est
l'appelant qui décide de bloquer (validation d'un modèle) ou d'alerter (envoi en cours).
"""
from __future__ import annotations

import hashlib
import random
import re

# ── 1. Vocabulaire qui pèse sur la note de spam ──────────────────────────────
# Deux niveaux, et la distinction compte : bloquer sur un mot ambigu ferait rejeter des
# messages corrects, et on cesserait de lire les alertes. `bloquant` = notoirement mauvais
# dans un premier contact B2B ; `avertissement` = à regarder, pas à interdire.
MOTS_BLOQUANTS = [
    "100% gratuit", "cent pour cent gratuit", "argent facile", "gagnez de l'argent",
    "revenus garantis", "risque zéro", "sans risque", "cliquez ici", "achetez maintenant",
    "offre limitée", "dernière chance", "agissez maintenant", "félicitations vous avez",
    "vous avez gagné", "opportunité unique", "devenez riche", "travaillez à domicile",
    "act now", "buy now", "click here", "risk free", "100% free", "make money",
    "earn money", "limited time offer", "you have won", "congratulations you",
]
MOTS_AVERTISSEMENT = [
    "gratuit", "promotion", "promo", "réduction", "remise exceptionnelle", "soldes",
    "économisez", "meilleur prix", "prix imbattable", "urgent", "immédiatement",
    "garantie", "sans engagement", "profitez", "exclusif", "exceptionnel", "incroyable",
    "révolutionnaire", "gagnant", "bonus", "cadeau", "offre spéciale",
    "free", "discount", "cheap", "guarantee", "winner", "bonus", "special offer",
]

# Mise en forme qui alourdit la note indépendamment du vocabulaire.
_MAJUSCULES = re.compile(r"\b[A-ZÀ-Þ]{4,}\b")
_EXCLAMATIONS = re.compile(r"!{2,}")
_DEVISES = re.compile(r"[€$]{2,}|\b\d+\s*%\s*(?:de\s*)?(?:remise|réduction)\b", re.I)
_TAGS = re.compile(r"<[^>]+>")


def _texte(html_ou_texte: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", html_ou_texte or "", flags=re.I)
    s = re.sub(r"</p>", " ", s, flags=re.I)
    return re.sub(r"\s+", " ", _TAGS.sub(" ", s)).strip()


def mots_spam(sujet: str, corps: str) -> dict:
    """Les termes repérés, séparés par gravité. Insensible à la casse et aux accents ASCII."""
    plein = f"{sujet or ''} {_texte(corps)}".lower()
    return {
        "bloquants": sorted({m for m in MOTS_BLOQUANTS if m in plein}),
        "avertissements": sorted({m for m in MOTS_AVERTISSEMENT if m in plein}),
    }


def mise_en_forme(sujet: str, corps: str) -> list[str]:
    """Les excès de forme : capitales, points d'exclamation en rafale, symboles monétaires."""
    motifs: list[str] = []
    texte = _texte(corps)
    # Les capitales de l'objet pèsent plus que celles du corps : c'est ce qui se voit.
    caps_sujet = [m for m in _MAJUSCULES.findall(sujet or "") if m not in ("ROI", "SEO", "PDF", "TVA")]
    if caps_sujet:
        motifs.append(f"mots en capitales dans l'objet : {', '.join(caps_sujet[:3])}")
    if _EXCLAMATIONS.search((sujet or "") + " " + texte):
        motifs.append("points d'exclamation en rafale (!!)")
    if _DEVISES.search((sujet or "") + " " + texte):
        motifs.append("symboles monétaires ou pourcentage de remise en évidence")
    return motifs


# ── 2. Liens et images ───────────────────────────────────────────────────────

def liens(html: str) -> list[str]:
    """Les URL du message, hors désinscription — celle-ci est obligatoire, pas décorative."""
    trouves = re.findall(r'href="([^"]+)"', html or "")
    return [u for u in trouves
            if not u.lower().startswith("mailto:")
            and "unsubscribe" not in u.lower()
            and "desabonn" not in u.lower()
            and "{{" not in u]


def images(html: str) -> list[str]:
    return re.findall(r'<img[^>]+src="([^"]+)"', html or "")


# ── 3. Spintax ───────────────────────────────────────────────────────────────
# `{option a|option b}`. Le pipe est OBLIGATOIRE dans le motif : sans lui, `{prenom}` et
# `{{prenom}}` seraient avalés comme des choix, et la personnalisation partirait en fumée.
_SPIN = re.compile(r"\{([^{}]*\|[^{}]*)\}")


def variantes(gabarit: str) -> int:
    """Combien de textes différents ce gabarit peut produire. 1 = aucune variation."""
    n = 1
    reste = gabarit or ""
    while True:
        m = _SPIN.search(reste)
        if not m:
            return n
        n *= max(1, len(m.group(1).split("|")))
        reste = reste[:m.start()] + m.group(1).split("|")[0] + reste[m.end():]


def spintax(gabarit: str, graine: str = "") -> str:
    """Développe le spintax, de l'intérieur vers l'extérieur, de façon DÉTERMINISTE.

    La graine (l'adresse du destinataire) est hachée avec `hashlib` et non `hash()` :
    le hachage natif de Python est salé à chaque démarrage du processus, donc un même
    destinataire aurait reçu une relance rédigée autrement que son premier message.
    """
    if not gabarit or "|" not in gabarit:
        return gabarit or ""
    empreinte = hashlib.sha256((graine or "").encode("utf-8")).hexdigest()
    tirage = random.Random(int(empreinte[:16], 16))

    out = gabarit
    for _ in range(50):                    # borne dure : un gabarit mal formé ne boucle pas
        m = _SPIN.search(out)
        if not m:
            break
        choix = [c.strip() for c in m.group(1).split("|")]
        out = out[:m.start()] + tirage.choice(choix) + out[m.end():]
    return out


# ── Contrôle d'ensemble ──────────────────────────────────────────────────────

# Deux liens au premier contact, et pas un de plus. Le guide en conseille ZÉRO — un lien
# dans un premier message ressemble à un appât. Mais deux sont imposés par ailleurs : le
# lint exige un CTA de prise de rendez-vous, et Camille a demandé le 2026-08-25 que le lien
# vers leclientroi.com soit toujours présent. C'est un arbitrage assumé, pas un oubli : le
# seuil reste bas pour que le TROISIÈME lien, lui, soit refusé.
LIENS_MAX_PREMIER = 2


def controler(sujet: str, corps_html: str, premier_contact: bool = False,
              liens_max_premier: int = LIENS_MAX_PREMIER) -> dict:
    """Le verdict complet. `bloquants` justifie un refus, `avertissements` une alerte.

    `premier_contact` durcit la règle sur les liens : le guide Maildoso demande de les
    éviter au tout premier message, moment où le destinataire ne connaît pas l'expéditeur
    et où un lien ressemble à un appât.
    """
    spam = mots_spam(sujet, corps_html)
    bloquants = [f"terme à risque : « {m} »" for m in spam["bloquants"]]
    avertissements = [f"terme à surveiller : « {m} »" for m in spam["avertissements"]]
    avertissements += mise_en_forme(sujet, corps_html)

    urls = liens(corps_html)
    imgs = images(corps_html)
    if premier_contact:
        if len(urls) > liens_max_premier:
            bloquants.append(f"{len(urls)} liens dans un premier message "
                             f"(maximum {liens_max_premier})")
        if imgs:
            bloquants.append(f"{len(imgs)} image(s) dans un premier message")
    elif len(urls) > 3:
        avertissements.append(f"{len(urls)} liens dans le message")

    return {"ok": not bloquants, "bloquants": bloquants, "avertissements": avertissements,
            "liens": len(urls), "images": len(imgs),
            "variantes": variantes((sujet or "") + (corps_html or ""))}
