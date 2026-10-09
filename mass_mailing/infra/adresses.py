#!/usr/bin/env python3
"""mass_mailing/infra/adresses.py — normaliser, contrôler, hacher une adresse.

UNE SEULE définition de « la même adresse » pour tout le module. L'import CSV, la
liste de suppression et les webhooks Sweego passent tous par `normaliser` puis
`hacher` : si deux d'entre eux normalisaient différemment, une désinscription
enregistrée depuis un webhook ne retrouverait pas l'adresse importée, et la
personne recevrait quand même le mail suivant.

Le contrôle syntaxique est volontairement PRAGMATIQUE, pas RFC 5322 : la RFC
accepte des adresses (guillemets, commentaires, IP littérales) qu'aucun fournisseur
d'envoi ne délivre. Mieux vaut les écarter ici que payer Mailnjoy pour l'apprendre.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

_LOCAL = re.compile(r"^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*$")
_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_TLD = re.compile(r"^([a-z]{2,63}|xn--[a-z0-9-]{1,59})$")

# Parasites fréquents des exports Excel / CRM, retirés avant tout contrôle.
_ESPACES = " ​‌‍﻿⁠"


def normaliser(brut: str | None) -> str:
    """Forme canonique : sans espaces ni guillemets, sans `mailto:`, en minuscules.

    La partie locale est mise en minuscules elle aussi. C'est techniquement permis
    par la RFC de la distinguer, mais aucun fournisseur grand public ne le fait, et
    garder `Jean@` et `jean@` comme deux personnes enverrait deux fois le même mail.
    """
    if not brut:
        return ""
    s = unicodedata.normalize("NFC", str(brut))
    for c in _ESPACES:
        s = s.replace(c, "")
    s = s.strip().strip("\"'").strip()
    if s.lower().startswith("mailto:"):
        s = s[7:]
    # « Jean Dupont <jean@x.fr> » → jean@x.fr
    if "<" in s and s.endswith(">"):
        s = s[s.rfind("<") + 1:-1]
    s = s.strip().rstrip(".;,").lower()
    if "@" in s:
        local, _, domaine = s.rpartition("@")
        try:
            domaine = domaine.encode("idna").decode("ascii")   # é → xn--…
        except UnicodeError:
            pass   # laissé tel quel, la syntaxe le rejettera
        s = f"{local}@{domaine}"
    return s


def syntaxe_valide(email: str) -> bool:
    """`email` doit déjà être normalisé."""
    if not email or len(email) > 254 or email.count("@") != 1:
        return False
    local, domaine = email.split("@")
    if not local or len(local) > 64 or not _LOCAL.match(local):
        return False
    labels = domaine.split(".")
    if len(labels) < 2 or not all(_LABEL.match(l) for l in labels):
        return False
    return bool(_TLD.match(labels[-1]))


def hacher(email_normalise: str) -> str:
    """SHA-256 hex de la forme normalisée. Stable, sans sel : il doit pouvoir être
    recalculé à l'identique par n'importe quel composant, des années plus tard."""
    return hashlib.sha256(email_normalise.encode("utf-8")).hexdigest()


def masquer(email: str) -> str:
    """Pour les logs et les rapports : `j***@exemple.fr`. Jamais d'adresse en clair."""
    if "@" not in (email or ""):
        return "***" if email else ""
    local, _, domaine = email.partition("@")
    return f"{local[:1]}***@{domaine}"
