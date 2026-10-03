#!/usr/bin/env python3
"""duck_ouverture.py — la SEULE façon d'ouvrir une base DuckDB dans le process de l'API.

Deux pièges, et un seul d'entre eux est un verrou.

1. **Le verrou d'écriture.** DuckDB accepte un écrivain OU des lecteurs, jamais les deux.
   Un scrape ou le nettoyage horaire tient la base : la connexion échoue, il faut réessayer.

2. **Le conflit de configuration — celui qui a fait tomber la page Campagnes.** Dans un
   même process, DuckDB met l'INSTANCE de base en cache, configuration comprise. Une
   connexion en lecture seule et une connexion en lecture-écriture sur le même fichier ne
   peuvent donc pas coexister : la seconde lève « Can't open a connection to same database
   file with a different configuration than existing connections ».

   Concrètement : `/api/serper/usage` ouvrait `god_mode.duckdb` en lecture seule toutes les
   60 secondes pour la barre latérale. Tant que cette connexion vivait, `campaign_engine`
   ne pouvait plus ouvrir la même base en écriture — et la page Campagnes affichait
   « la base est occupée ». Ce n'était pas un verrou : c'était nous, contre nous-mêmes.

Règle : dans le process de l'API, **tout le monde ouvre en lecture-écriture**, même pour
lire. C'est la configuration dont les écrivains ont besoin ; les lecteurs s'alignent. Le
repli en lecture seule ne sert que si l'écriture est de toute façon impossible (base tenue
par un autre process), auquel cas rien ne peut être écrit et le cache ne gêne personne.
"""
from __future__ import annotations

import time

import duckdb


def ouvrir(chemin, tentatives: int = 6, pause_s: float = 0.25):
    """Ouvre `chemin` en lecture-écriture, avec ré-essais, puis en lecture seule en dernier
    recours. Lève la dernière erreur si tout échoue."""
    derniere: Exception | None = None
    for i in range(tentatives):
        try:
            return duckdb.connect(str(chemin))
        except Exception as e:  # noqa: BLE001
            derniere = e
        if i < tentatives - 1:
            time.sleep(pause_s)
    try:
        return duckdb.connect(str(chemin), read_only=True)
    except Exception:
        raise derniere  # type: ignore[misc]
