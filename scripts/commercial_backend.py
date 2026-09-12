#!/usr/bin/env python3
"""commercial_backend.py — Le tableau de bord de celui qui décroche le téléphone.

Le mini-CRM sait tout ce qu'il faut faire et rien de ce qui a été fait : 82 rappels en
attente, **un seul appel journalisé**. Ce n'est pas un défaut de l'outil, c'est un défaut
de motivation — rien ne renvoie au commercial l'image de son travail. Une liste d'appels
qui ne raccourcit jamais et ne félicite jamais, on l'ouvre une fois.

D'où ce tableau. Trois idées, dans cet ordre :

  1. **Ma journée** — ce qui est à faire aujourd'hui, et où j'en suis de mon objectif.
     Un objectif atteignable (30 appels, le rythme réel constaté) avec une progression
     visible : le travail se voit avancer.
  2. **Ma série** — les jours consécutifs avec au moins un appel. C'est le ressort qui
     marche le mieux : on ne veut pas casser une série de onze jours.
  3. **Où ça mord** — les secteurs et les villes dont les prospects ouvrent et cliquent le
     plus. Appeler quelqu'un qui vient d'ouvrir un email, ce n'est pas le même appel.

Ce qu'on ne fait PAS : inventer des chiffres pour remplir l'écran. Quand une donnée
n'existe pas encore, le tableau le dit et explique comment elle se remplira. Un tableau de
bord qui affiche des zéros honnêtes reste crédible ; un tableau qui affiche des nombres
décoratifs ne l'est plus jamais.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

# Le rythme de référence, donné par Camille le 2026-08-21 : un commercial passe AU PLUS
# 30 appels dans l'heure de pointe. On en fait l'objectif de la JOURNÉE — atteignable,
# donc motivant ; un objectif qu'on ne touche jamais démotive plus qu'il n'entraîne.
OBJECTIF_APPELS_JOUR = 30

# Les paliers. Ils portent des noms de métier, pas des noms de jeu vidéo : on parle à des
# adultes qui vendent, l'ironie serait vexante.
PALIERS = [
    (0,    "Débutant",     "Les premiers appels"),
    (25,   "Prospecteur",  "25 appels passés"),
    (100,  "Closeur",      "100 appels passés"),
    (250,  "Vétéran",      "250 appels passés"),
    (500,  "Référence",    "500 appels passés"),
    (1000, "Légende",      "1 000 appels passés"),
]


def _pool():
    import pool_pg
    return pool_pg


def _palier(appels: int) -> dict:
    actuel = PALIERS[0]
    suivant = None
    for i, p in enumerate(PALIERS):
        if appels >= p[0]:
            actuel = p
            suivant = PALIERS[i + 1] if i + 1 < len(PALIERS) else None
    return {
        "nom": actuel[1], "aide": actuel[2], "seuil": actuel[0],
        "suivant": ({"nom": suivant[1], "seuil": suivant[0],
                     "reste": suivant[0] - appels} if suivant else None),
    }


def _serie(site: str, qui: str) -> dict:
    """Jours consécutifs, en remontant depuis aujourd'hui, avec au moins un appel."""
    try:
        jours = {r[0] for r in _pool()._q("""
            SELECT DISTINCT occurred_at::date FROM followup_events
            WHERE site_code = %s AND auteur = %s AND type = 'appel'
              AND occurred_at >= now() - interval '90 days'""", (site, qui))}
    except Exception:  # noqa: BLE001
        return {"jours": 0, "actif_aujourdhui": False}
    aujourdhui = date.today()
    actif = aujourdhui in jours
    # La série ne casse pas si on n'a pas encore appelé AUJOURD'HUI : on compte depuis hier.
    depart = aujourdhui if actif else aujourdhui - timedelta(days=1)
    n = 0
    while depart in jours:
        n += 1
        depart -= timedelta(days=1)
    return {"jours": n, "actif_aujourdhui": actif}


def _appels(site: str, qui: str) -> dict:
    def compte(depuis: str) -> int:
        try:
            return _pool()._q(
                "SELECT count(*) FROM followup_events WHERE site_code = %s AND auteur = %s "
                f"AND type = 'appel' AND occurred_at >= {depuis}", (site, qui))[0][0] or 0
        except Exception:  # noqa: BLE001
            return 0
    return {"aujourdhui": compte("current_date"),
            "semaine": compte("date_trunc('week', now())"),
            "mois": compte("date_trunc('month', now())"),
            "total": compte("'epoch'::timestamptz")}


def _files(site: str, qui: str, est_admin: bool) -> dict:
    """Ce qu'il reste à faire — la seule partie du tableau qui commande une action."""
    ou = "" if est_admin else " AND assigned_to = %s"
    args = (site,) if est_admin else (site, qui)
    def q(sql, a=None):
        try:
            return _pool()._q(sql, a or args)[0][0] or 0
        except Exception:  # noqa: BLE001
            return 0
    return {
        "a_faire": q(f"SELECT count(*) FROM contact_followup WHERE site_code = %s{ou} "
                     "AND statut = 'a_faire'"),
        "en_retard": q(f"SELECT count(*) FROM contact_followup WHERE site_code = %s{ou} "
                       "AND statut = 'a_faire' AND next_action_at < now()"),
        "aujourdhui": q(f"SELECT count(*) FROM contact_followup WHERE site_code = %s{ou} "
                        "AND next_action_at::date = current_date"),
        "jamais_appeles": q(f"SELECT count(*) FROM contact_followup WHERE site_code = %s{ou} "
                            "AND last_call_at IS NULL"),
    }


def _ou_ca_mord(site: str, limite: int = 5) -> dict:
    """Les secteurs et les villes dont les prospects réagissent le plus.

    Source : `campaign_recipients`, la table qui sait qui a ouvert et qui a cliqué. Le clic
    passe avant l'ouverture — appeler quelqu'un qui a CLIQUÉ, c'est appeler quelqu'un qui
    s'est déplacé vers nous.
    """
    def lignes(dimension: str, mini: int):
        try:
            return _pool()._q(f"""
                SELECT {dimension}, count(*) envois, count(opened_at), count(clicked_at),
                       round(100.0 * count(clicked_at) / NULLIF(count(*), 0), 1)::float8,
                       round(100.0 * count(opened_at)  / NULLIF(count(*), 0), 1)::float8
                FROM campaign_recipients
                WHERE site_code = %s AND {dimension} <> 'inconnu'
                GROUP BY 1 HAVING count(*) >= {mini}
                ORDER BY 5 DESC NULLS LAST, 6 DESC NULLS LAST
                LIMIT {int(limite)}""", (site,))
        except Exception:  # noqa: BLE001
            return []
    def rendre(rs, cle):
        return [{cle: r[0], "envois": r[1], "ouvreurs": r[2], "cliqueurs": r[3],
                 "taux_clic": r[4], "taux_ouverture": r[5]} for r in rs]
    return {"secteurs": rendre(lignes("secteur", 20), "secteur"),
            "zones": rendre(lignes("dept_code", 20), "dept"),
            "seuil": 20}


def _a_rappeler_en_priorite(site: str, qui: str, est_admin: bool, limite: int = 5) -> list:
    """Les contacts de MA liste qui viennent de cliquer — les appels à passer en premier."""
    ou = "" if est_admin else " AND f.assigned_to = %s"
    args = (site,) if est_admin else (site, qui)
    try:
        return [{"email": r[0], "societe": r[1], "ville": r[2], "secteur": r[3],
                 "clique_le": str(r[4])[:16] if r[4] else None}
                for r in _pool()._q(f"""
            SELECT f.email, c.societe, c.city, COALESCE(c.sectors[1], '—'), r.clicked_at
            FROM contact_followup f
            JOIN campaign_recipients r ON r.email = f.email AND r.site_code = f.site_code
            LEFT JOIN contacts c ON c.email::text = f.email
            WHERE f.site_code = %s{ou} AND f.statut = 'a_faire' AND r.clicked_at IS NOT NULL
            ORDER BY r.clicked_at DESC LIMIT {int(limite)}""", args)]
    except Exception:  # noqa: BLE001
        return []


def _classement(site: str) -> list:
    """Le classement des rappelants sur le mois. Amical : on affiche tout le monde, et le
    nombre d'appels, pas un score inventé."""
    try:
        return [{"qui": r[0], "appels": r[1]} for r in _pool()._q("""
            SELECT auteur, count(*) FROM followup_events
            WHERE site_code = %s AND type = 'appel'
              AND occurred_at >= date_trunc('month', now())
            GROUP BY auteur ORDER BY 2 DESC LIMIT 10""", (site,))]
    except Exception:  # noqa: BLE001
        return []


def tableau_de_bord(site: str, qui: str, role: str = "") -> dict:
    est_admin = role in ("admin", "superadmin")
    appels = _appels(site, qui)
    serie = _serie(site, qui)
    files = _files(site, qui, est_admin)
    fait = appels["aujourdhui"]
    return {
        "site": site, "qui": qui, "vue_admin": est_admin,
        "objectif": {
            "cible": OBJECTIF_APPELS_JOUR, "fait": fait,
            "reste": max(0, OBJECTIF_APPELS_JOUR - fait),
            "pourcent": min(100, round(100 * fait / OBJECTIF_APPELS_JOUR)),
            "atteint": fait >= OBJECTIF_APPELS_JOUR,
        },
        "appels": appels,
        "serie": serie,
        "palier": _palier(appels["total"]),
        "files": files,
        "priorites": _a_rappeler_en_priorite(site, qui, est_admin),
        "ou_ca_mord": _ou_ca_mord(site),
        "classement": _classement(site),
        # Dire la vérité sur la maigreur des données plutôt que de la masquer.
        "donnees_maigres": appels["total"] < 10,
    }


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(description="Tableau de bord commercial")
    ap.add_argument("--site", default="lcr")
    ap.add_argument("--qui", default="Romeo")
    ap.add_argument("--role", default="")
    a = ap.parse_args()
    print(json.dumps(tableau_de_bord(a.site, a.qui, a.role), ensure_ascii=False,
                     indent=2, default=str))
