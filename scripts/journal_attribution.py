#!/usr/bin/env python3
"""Attribue chaque événement du journal au MODÈLE qui l'a produit (Lot B, 2026-08-26).

Le problème
-----------
`email_events` retenait la CAMPAGNE d'un envoi, jamais le message. La galerie ne pouvait
donc afficher que des chiffres par SECTEUR — partagés par les trois emails du secteur.
Impossible de dire lequel des trois fonctionne, donc impossible d'arbitrer une réécriture
d'objet autrement qu'à l'intuition.

Ce qui change
-------------
Depuis aujourd'hui, `record_send` écrit `meta.modele` à chaque envoi (chemin campagnes ET
chemin Mozart). Ce script reprend l'HISTORIQUE, qui est attribuable sans la moindre
approximation :

1. **Les envois.** Une campagne ne porte qu'un seul message (`campaigns.message_id`). Un
   envoi rattaché à une campagne connaît donc son modèle avec certitude — ce n'est pas une
   estimation, c'est une jointure. 1 750 des 1 782 envois `lcr` sont dans ce cas.

2. **Les ouvertures, clics, rebonds, plaintes.** Ils arrivent APRÈS, sans campagne ni
   contexte. On les rattache au dernier envoi attribué de la MÊME adresse sur le MÊME site,
   antérieur ou simultané. C'est la seule lecture correcte : une ouverture répond au
   dernier message reçu.

Ce que le script ne fait PAS
----------------------------
Il n'invente rien. Un envoi sans campagne (BAT, test, envoi de masse Sweego) reste **non
attribué**, et la galerie devra l'afficher comme tel. Répartir ces volumes au prorata entre
les modèles d'un secteur produirait des taux crédibles et faux — et c'est précisément sur
ces taux que se décidera la réécriture des objets. Un chiffre absent se voit ; un chiffre
faux se croit.

`meta.attribution` garde la trace de la PROVENANCE de l'attribution :
  - `envoi`               : écrit à l'envoi, source directe (à partir du 2026-08-26) ;
  - `reprise-campagne`    : déduit de la campagne, certain ;
  - `reprise-dernier-envoi` : déduit du dernier envoi de l'adresse, très sûr mais indirect.

Usage
-----
    python3 scripts/journal_attribution.py              # simulation, n'écrit rien
    python3 scripts/journal_attribution.py --apply      # applique
    python3 scripts/journal_attribution.py --site mkd   # un autre site
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

# Les événements qui suivent un envoi. `sent` en est évidemment exclu : c'est la source.
EVENEMENTS_SUIVIS = ("open", "click", "bounce", "complaint", "unsub", "reply")


def _dsn() -> str:
    for ligne in (RACINE / ".env").read_text().splitlines():
        if ligne.startswith("PG_DSN="):
            return ligne.split("=", 1)[1].strip()
    raise SystemExit("PG_DSN introuvable dans .env")


def _connexion():
    try:
        import psycopg  # type: ignore
        return psycopg.connect(_dsn()), "psycopg"
    except ImportError:
        pass
    try:
        import psycopg2  # type: ignore
        return psycopg2.connect(_dsn()), "psycopg2"
    except ImportError:
        raise SystemExit("ni psycopg ni psycopg2 — installer l'un des deux")


SQL_ENVOIS = """
UPDATE email_events ev
   SET meta = ev.meta
              || jsonb_build_object('modele', c.message_id,
                                    'attribution', 'reprise-campagne')
  FROM campaigns c
 WHERE ev.campaign_id = c.id
   AND ev.site_code   = %(site)s
   AND ev.event_type  = 'sent'
   AND NOT (ev.meta ? 'modele')
   AND c.message_id IS NOT NULL
   AND c.message_id <> ''
"""

# `DISTINCT ON` + tri décroissant : le dernier envoi attribué de cette adresse, sur ce
# site, antérieur ou simultané à l'événement. `<=` et non `<` — un rebond immédiat porte
# exactement le même horodatage que l'envoi qui l'a provoqué, et un `<` strict le
# laisserait orphelin.
SQL_SUIVIS = """
UPDATE email_events ev
   SET meta = ev.meta
              || jsonb_build_object('modele', src.modele,
                                    'attribution', 'reprise-dernier-envoi')
  FROM (
        SELECT e.id, dernier.modele
          FROM email_events e
          JOIN LATERAL (
                SELECT s.meta->>'modele' AS modele
                  FROM email_events s
                 WHERE s.email       = e.email
                   AND s.site_code   = e.site_code
                   AND s.event_type  = 'sent'
                   AND s.occurred_at <= e.occurred_at
                   AND s.meta ? 'modele'
                 ORDER BY s.occurred_at DESC
                 LIMIT 1
               ) AS dernier ON TRUE
         WHERE e.site_code  = %(site)s
           AND e.event_type = ANY(%(types)s)
           AND NOT (e.meta ? 'modele')
       ) AS src
 WHERE ev.id = src.id
"""

SQL_INDEX = """
CREATE INDEX IF NOT EXISTS idx_events_modele
    ON email_events ((meta->>'modele'), event_type, occurred_at DESC)
"""


def _etat(cur, site: str) -> list[tuple]:
    cur.execute("""
        SELECT event_type,
               count(*)                                    AS total,
               count(*) FILTER (WHERE meta ? 'modele')      AS attribues
          FROM email_events
         WHERE site_code = %(site)s
         GROUP BY 1 ORDER BY 2 DESC
    """, {"site": site})
    return cur.fetchall()


def _tableau(titre: str, lignes) -> None:
    print(f"\n  {titre}")
    print(f"    {'événement':<12} {'total':>7} {'attribués':>10} {'%':>6}")
    for t, total, att in lignes:
        pct = (100.0 * att / total) if total else 0.0
        print(f"    {t:<12} {total:>7} {att:>10} {pct:>5.0f}%")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", default="lcr")
    ap.add_argument("--apply", action="store_true",
                    help="écrit réellement (sans ce drapeau : simulation, rien n'est modifié)")
    args = ap.parse_args()

    cx, pilote = _connexion()
    print(f"Attribution du journal — site « {args.site} » ({pilote}, "
          f"{'APPLIQUÉ' if args.apply else 'SIMULATION'})")

    with cx:
        with cx.cursor() as cur:
            _tableau("avant", _etat(cur, args.site))

            cur.execute(SQL_ENVOIS, {"site": args.site})
            n_envois = cur.rowcount
            print(f"\n  envois attribués depuis leur campagne      : {n_envois}")

            cur.execute(SQL_SUIVIS, {"site": args.site,
                                     "types": list(EVENEMENTS_SUIVIS)})
            n_suivis = cur.rowcount
            print(f"  événements rattachés au dernier envoi      : {n_suivis}")

            if args.apply:
                cur.execute(SQL_INDEX)
                print("  index idx_events_modele                    : posé")

            _tableau("après", _etat(cur, args.site))

            if args.apply:
                cx.commit()
                print("\n  → écrit.")
            else:
                cx.rollback()
                print("\n  → SIMULATION : rien n'a été écrit. "
                      "Relancer avec --apply pour appliquer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
