"""text_utils.py — Helpers texte partagés entre scripts Genesis.

À importer plutôt que de redéfinir localement (évite les divergences accents/slugs)."""
from __future__ import annotations

import re
import unicodedata


def slugify(text: str, max_len: int = 60) -> str:
    """Slugifie un texte FR : NFD → strip diacritiques → ascii minuscule + tirets.
    Évite les pertes silencieuses d'accents (`fidéliser` ne devient plus `fidliser`).

    >>> slugify("Comment fidéliser vos clients avec des SMS personnalisés")
    'comment-fideliser-vos-clients-avec-des-sms-personnalises'
    >>> slugify("L'expérience client en hôtellerie")
    'lexperience-client-en-hotellerie'
    """
    nfd = unicodedata.normalize("NFD", text)
    no_accents = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    s = no_accents.lower()
    s = re.sub(r"['’`]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:max_len].rstrip("-")
