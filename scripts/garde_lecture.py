#!/usr/bin/env python3
"""garde_lecture.py — Ce qu'un compte peut lire de la base de contacts, et à quel rythme.

La menace n'est pas un robot anonyme : c'est un compte LÉGITIME. Un commercial dispose
d'un jeton valide, ses requêtes sont signées, elles ressemblent trait pour trait à celles
de quelqu'un qui travaille. Un pare-feu applicatif (Cloudflare et consorts) ne voit rien à
y redire — il filtre l'origine, pas l'intention. La seule barrière qui tienne est ici,
là où l'on sait QUI demande, COMBIEN de lignes, et depuis QUAND.

Trois mesures, dans cet ordre d'utilité :

  1. **Le plafond de page.** Un écran affiche cinquante lignes ; personne n'a besoin d'en
     demander cinq cents. Le plafond ne bloque pas le travail, il rend l'aspiration lente
     et bruyante — il faut multiplier les requêtes, et chacune laisse une trace.
  2. **Le quota horaire.** Au-delà d'un volume manifestement supérieur à un usage humain,
     la lecture est refusée pour l'heure en cours. Un commercial consulte des fiches ; il
     n'en parcourt pas trois mille en soixante minutes.
  3. **Le journal.** Chaque lecture est enregistrée : qui, quand, combien. C'est ce qui
     permet de constater une aspiration APRÈS coup — et, avec `alertes.py`, de la voir
     pendant qu'elle se produit.

Ce que ça n'empêche pas, et qu'il faut savoir : quelqu'un qui a le droit de VOIR une fiche
peut toujours la recopier. Aucun réglage logiciel n'y changera rien. L'objectif n'est pas
l'impossibilité, c'est de rendre l'exfiltration lente, visible et attribuable.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

# Rôles sans bride : ce sont eux qui exportent, migrent et réconcilient.
SANS_BRIDE = ("superadmin", "admin")

# Lignes maximum par requête, par rôle. Le tableau en affiche 50 ; 100 laisse de la marge
# pour un tri ou une recherche large sans jamais servir de seau.
PLAFOND_PAGE = {"commercial": 100, "contenu": 100, "strategie": 100}
PLAFOND_PAGE_DEFAUT = 100

# Lignes maximum par heure glissante et par compte.
#
# 1 000 pour un commercial (réglage de Camille, 2026-08-21) : quarante pages pleines en une
# heure, soit une page toutes les quatre-vingt-dix secondes sans jamais s'arrêter. Un
# commercial ouvre des fiches et téléphone ; il ne parcourt pas mille contacts par heure.
# Et il faudrait plus de huit heures ininterrompues pour lire la base entière — largement
# le temps que l'alerte parte.
#
# Les rôles `superadmin` et `admin` n'ont AUCUN quota : ce sont eux qui exportent, migrent
# et réconcilient (voir SANS_BRIDE).
QUOTA_HEURE = {"commercial": 1000, "contenu": 1000, "strategie": 1000}
QUOTA_HEURE_DEFAUT = 1000

SCHEMA = """
CREATE TABLE IF NOT EXISTS lecture_contacts (
    id          bigserial PRIMARY KEY,
    lu_le       timestamptz NOT NULL DEFAULT now(),
    utilisateur text NOT NULL,
    role        text,
    site_code   text,
    route       text,
    lignes      int  NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_lecture_user ON lecture_contacts (utilisateur, lu_le DESC);
CREATE INDEX IF NOT EXISTS idx_lecture_date ON lecture_contacts (lu_le DESC);
"""

_table_prete = False


def _pool():
    import pool_pg
    return pool_pg


def _assurer_table() -> None:
    global _table_prete
    if _table_prete:
        return
    p = _pool()
    c = p._conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(SCHEMA)
    finally:
        p._rendre(c)
    _table_prete = True


def plafonner(role: str | None, demande: int, dur: int = 500) -> int:
    """Le nombre de lignes réellement servi pour cette demande."""
    demande = max(1, int(demande or 1))
    if (role or "") in SANS_BRIDE:
        return min(dur, demande)
    return min(PLAFOND_PAGE.get(role or "", PLAFOND_PAGE_DEFAUT), demande)


def lues_derniere_heure(utilisateur: str) -> int:
    if not utilisateur:
        return 0
    try:
        _assurer_table()
        return _pool()._q(
            "SELECT COALESCE(sum(lignes), 0) FROM lecture_contacts "
            "WHERE utilisateur = %s AND lu_le >= now() - interval '1 hour'",
            (utilisateur,))[0][0] or 0
    except Exception:  # noqa: BLE001 — le garde-fou ne doit jamais casser la page
        return 0


def verifier(utilisateur: str, role: str | None) -> dict:
    """Ce compte a-t-il encore le droit de lire ? Rendu, jamais levé."""
    if (role or "") in SANS_BRIDE:
        return {"ok": True, "lues": 0, "quota": None}
    quota = QUOTA_HEURE.get(role or "", QUOTA_HEURE_DEFAUT)
    lues = lues_derniere_heure(utilisateur)
    return {"ok": lues < quota, "lues": lues, "quota": quota,
            "reste": max(0, quota - lues)}


def journaliser(utilisateur: str, role: str | None, site: str, route: str,
                lignes: int) -> None:
    """Enregistre une lecture. Silencieux en cas d'échec : on ne bloque pas un écran
    parce que le journal est indisponible — mais on ne fait pas semblant non plus, le
    relevé technique voit tout de suite une table qui cesse de grossir."""
    if not utilisateur or (role or "") in SANS_BRIDE or lignes <= 0:
        return
    try:
        _assurer_table()
        p = _pool()
        c = p._conn()
        try:
            with c:
                with c.cursor() as cur:
                    cur.execute(
                        "INSERT INTO lecture_contacts (utilisateur, role, site_code, route, lignes) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (utilisateur, role, site, route, int(lignes)))
        finally:
            p._rendre(c)
    except Exception:  # noqa: BLE001
        pass


def refus(etat: dict) -> dict:
    """Le corps de réponse d'un refus — dit quoi faire, pas seulement non."""
    return {"error": "quota de lecture atteint",
            "detail": f"{etat['lues']} fiches lues dans l'heure (plafond {etat['quota']}). "
                      f"La lecture reprend automatiquement dans l'heure qui suit. "
                      f"Pour un export, passer par un administrateur.",
            "lues": etat["lues"], "quota": etat["quota"]}


def gros_lecteurs(heures: int = 24, seuil: int = 1000) -> list[dict]:
    """Qui a beaucoup lu récemment — matière première de l'alerte."""
    try:
        _assurer_table()
        lignes = _pool()._q("""
            SELECT utilisateur, role, sum(lignes)::int, count(*)::int,
                   min(lu_le)::text, max(lu_le)::text
            FROM lecture_contacts
            WHERE lu_le >= now() - (%s || ' hours')::interval
            GROUP BY utilisateur, role
            HAVING sum(lignes) >= %s
            ORDER BY 3 DESC""", (str(heures), seuil))
    except Exception:  # noqa: BLE001
        return []
    return [{"utilisateur": r[0], "role": r[1], "lignes": r[2], "requetes": r[3],
             "depuis": r[4], "jusqu_a": r[5]} for r in lignes]


if __name__ == "__main__":
    import json
    print(json.dumps({"gros_lecteurs_24h": gros_lecteurs()}, ensure_ascii=False, indent=2))
