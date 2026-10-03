#!/usr/bin/env python3
"""backfill_prenoms.py — Renseigne le prénom des contacts qui n'en ont pas, depuis leur email.

Pourquoi : 7 des 10 modèles d'email utilisent `{{prenom}}`, remplacé par une chaîne vide
quand il manque. Aucun contact scrapé n'ayant de prénom, tous les cold emails partaient avec
« Bonjour, » — et un commercial au téléphone n'a rien pour accrocher son interlocuteur.

Deux garde-fous :
  - on n'écrase JAMAIS un prénom existant (saisi à la main, il fait foi) ;
  - chaque valeur déduite est tracée dans `prenom_source` (« email:<forme> »), ce qui rend
    l'opération réversible et permet de distinguer une donnée vérifiée d'une déduction.

Usage :
    python3 scripts/backfill_prenoms.py --dry-run   # compte sans écrire
    python3 scripts/backfill_prenoms.py             # applique
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))


def executer(dry_run: bool = False) -> dict:
    import contacts_pool_backend as pool
    import name_extract as ne

    c = pool._conn()
    try:
        rows = c.execute("""
            SELECT id, email, prenom, nom FROM contacts
            WHERE email IS NOT NULL AND trim(email) <> ''
              AND (prenom IS NULL OR trim(prenom) = '')
        """).fetchall()

        formes = Counter()
        maj_prenom = maj_nom = 0
        lot: list[tuple] = []
        for cid, email, _p, nom_actuel in rows:
            r = ne.extraire(email)
            formes[r["forme"]] += 1
            if not r["prenom"] and not r["nom"]:
                continue
            # Le nom n'est écrit que s'il est vide : un nom saisi vaut mieux qu'un nom deviné.
            nouveau_nom = r["nom"] if (r["nom"] and not (nom_actuel or "").strip()) else None
            if r["prenom"]:
                maj_prenom += 1
            if nouveau_nom:
                maj_nom += 1
            lot.append((r["prenom"], nouveau_nom, f"email:{r['forme']}", cid))

        if not dry_run and lot:
            c.executemany("""
                UPDATE contacts
                SET prenom        = COALESCE(?, prenom),
                    nom           = COALESCE(?, nom),
                    prenom_source = ?,
                    updated_at    = CURRENT_TIMESTAMP
                WHERE id = ?
            """, lot)
    finally:
        c.close()

    bilan = {"examines": len(rows), "prenoms_ecrits": maj_prenom, "noms_ecrits": maj_nom,
             "par_forme": dict(formes.most_common()), "dry_run": dry_run}

    # PostgreSQL suit : la porte d'entrée décide si le contact y a sa place, et les contacts
    # déjà promus doivent voir leur prénom mis à jour — c'est lui qui sert la personnalisation.
    if not dry_run and lot:
        try:
            import pg_sync
            ok = sum(1 for l in lot if pg_sync.promote_contact(l[3]))
            bilan["propages_postgres"] = ok
        except Exception as e:  # noqa: BLE001
            bilan["erreur_postgres"] = str(e)[:150]
    return bilan


if __name__ == "__main__":
    import json
    b = executer(dry_run="--dry-run" in sys.argv)
    print(json.dumps(b, indent=2, ensure_ascii=False))
