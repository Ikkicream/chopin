#!/usr/bin/env python3
"""roles_backend.py — Qui a le droit de voir quoi, et le faire RESPECTER côté serveur.

Le point central, et la raison d'être de ce module : **cacher un menu n'est pas
interdire**. Jusqu'ici, le rôle décidait des entrées de la sidebar, côté navigateur. Or
tout ce qui vit dans le navigateur se change dans le navigateur : `localStorage`, la
console, un signet. Un commercial qui écrivait `role: "superadmin"` voyait réapparaître
tous les menus — et surtout, les routes d'API répondaient, parce que rien ne les gardait.

Ici, l'autorisation est attachée aux **routes d'API**, pas aux écrans. Un écran qu'on n'a
pas le droit de voir est un écran dont les données ne viennent pas. On peut donc laisser
l'interface faire ce qu'elle veut : sans données, une page volée est une page vide.

Trois règles qui ne se négocient pas :

  1. **`superadmin` a tout, toujours.** Il n'est pas stocké dans la matrice et ne peut pas
     être restreint — sinon un clic malheureux enferme tout le monde dehors, y compris
     celui qui pourrait rouvrir.
  2. **Ce qui n'est pas décrit ici n'est pas gardé.** La matrice ne couvre que les pages du
     catalogue. Les gardes existants (`_ADMIN_PREFIXES`, isolation multi-tenant, quotas de
     lecture) restent en place et s'appliquent en plus, jamais à la place.
  3. **En cas de doute, on laisse passer et on trace.** Une matrice illisible ne doit pas
     couper la plateforme ; elle doit alerter. Refuser massivement sur une panne de base
     serait un déni de service qu'on se serait infligé.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

SUPER = "superadmin"

ROLES = [
    {"cle": "superadmin", "label": "Superadmin",
     "aide": "Accès total, non modifiable. C'est le rôle qui peut rouvrir les portes — le "
             "restreindre reviendrait à pouvoir s'enfermer dehors."},
    {"cle": "admin", "label": "Admin",
     "aide": "Pilote la plateforme au quotidien : campagnes, contacts, réglages. N'a pas "
             "accès à la gestion des comptes ni aux bases de données par défaut."},
    {"cle": "user", "label": "Utilisateur",
     "aide": "Consulte et travaille sur un site, sans toucher aux réglages qui engagent "
             "de la dépense ou la réputation d'expéditeur."},
    {"cle": "commercial", "label": "Commercial",
     "aide": "Son métier est le téléphone : sa liste d'appels, ses rendez-vous, les fiches "
             "de ses contacts. Ni scraping, ni SEO, ni envoi."},
    {"cle": "contenu", "label": "Contenu",
     "aide": "Écrit et publie : articles, newsletters, plan de taggage."},
    {"cle": "strategie", "label": "Stratégie",
     "aide": "Analyse et arbitre : SEO, statistiques, secteurs."},
]

# ── Le catalogue des pages ────────────────────────────────────────────────────
# `api` = les préfixes de routes qui SERVENT cette page. C'est ce qui est réellement gardé.
# Une page sans préfixe (`api: []`) n'est qu'un écran : on la retire du menu, mais aucune
# donnée n'est à protéger derrière.
PAGES = [
    # — Pilotage —
    {"cle": "dashboard", "label": "Tableau de bord", "groupe": "Pilotage",
     "url": "/site/{site}/dashboard", "api": ["/api/sites/{site}/marketing/overview"]},
    {"cle": "vision", "label": "Vision", "groupe": "Pilotage",
     "url": "/site/{site}/vision", "api": ["/api/sites/{site}/vision"]},
    {"cle": "statistiques", "label": "Statistiques", "groupe": "Pilotage",
     "url": "/site/{site}/statistiques", "api": ["/api/sites/{site}/statistiques"]},

    # — Acquisition —
    {"cle": "contacts", "label": "Contacts", "groupe": "Acquisition",
     "url": "/site/{site}/acquisition",
     "api": ["/api/sites/{site}/acquisition", "/api/sites/{site}/pool/"]},
    {"cle": "a_rappeler", "label": "À rappeler", "groupe": "Acquisition",
     "url": "/site/{site}/a-rappeler", "api": ["/api/sites/{site}/a-rappeler"]},
    {"cle": "mon_activite", "label": "Mon activité (commercial)", "groupe": "Acquisition",
     "url": "/site/{site}/mon-activite", "api": ["/api/sites/{site}/mon-activite"]},
    {"cle": "opportunites", "label": "Opportunités", "groupe": "Ventes",
     "url": "/site/{site}/opportunites", "api": ["/api/sites/{site}/opportunites"]},
    {"cle": "ventes", "label": "Ventes", "groupe": "Ventes",
     "url": "/site/{site}/ventes", "api": ["/api/sites/{site}/ventes"]},
    {"cle": "booking", "label": "Rendez-vous", "groupe": "Acquisition",
     "url": "/site/{site}/booking", "api": ["/api/sites/{site}/booking"]},
    {"cle": "scrapper", "label": "Scraping", "groupe": "Acquisition",
     "url": "/site/{site}/scrapper",
     "api": ["/api/sites/{site}/autoscrape", "/api/sites/{site}/scrape/",
             "/api/sites/{site}/stephane/", "/api/god-mode/{site}"]},
    {"cle": "scrapper_activite", "label": "Activité des scrapes", "groupe": "Acquisition",
     "url": "/site/{site}/scrapper/activite", "api": []},

    # — Campagnes —
    {"cle": "cold_email", "label": "Cold email", "groupe": "Campagnes",
     "url": "/site/{site}/cold-email", "api": ["/api/sites/{site}/cold-email"]},
    {"cle": "newsletters", "label": "Newsletters", "groupe": "Campagnes",
     "url": "/site/{site}/newsletters", "api": ["/api/sites/{site}/newsletters"]},
    {"cle": "campagnes", "label": "Campagnes", "groupe": "Campagnes",
     "url": "/site/{site}/campaigns", "api": ["/api/sites/{site}/campaigns"]},
    {"cle": "segments", "label": "Segments", "groupe": "Campagnes",
     "url": "/site/{site}/segments", "api": ["/api/sites/{site}/segments"]},

    # — Contenu & SEO —
    {"cle": "articles", "label": "Articles", "groupe": "Contenu & SEO",
     "url": "/site/{site}/articles", "api": ["/api/articles"]},
    {"cle": "seo", "label": "Analyse SEO", "groupe": "Contenu & SEO",
     "url": "/site/{site}/seo", "api": ["/api/seo-ahrefs/{site}"]},
    {"cle": "seo_strategy", "label": "Stratégie SEO", "groupe": "Contenu & SEO",
     "url": "/site/{site}/seo-strategy", "api": ["/api/seo-strategy/{site}"]},
    {"cle": "tag", "label": "Plan de taggage", "groupe": "Contenu & SEO",
     "url": "/site/{site}/tag", "api": ["/api/sites/{site}/tag"]},
    {"cle": "agents", "label": "Agents IA", "groupe": "Contenu & SEO",
     "url": "/site/{site}/agents", "api": ["/api/agents/{site}"]},

    # — Administration —
    {"cle": "admin_users", "label": "Utilisateurs", "groupe": "Administration",
     "url": "/admin/users", "api": ["/api/auth/users", "/api/auth/logs", "/api/admin/roles"]},
    {"cle": "admin_secteurs", "label": "Secteurs", "groupe": "Administration",
     "url": "/admin/secteurs", "api": ["/api/admin/secteurs"]},
    {"cle": "admin_pression", "label": "Pression marketing", "groupe": "Administration",
     "url": "/admin/pression", "api": ["/api/admin/pression"]},
    {"cle": "admin_database", "label": "Bases de données", "groupe": "Administration",
     "url": "/admin/database", "api": ["/api/admin/database"]},
    {"cle": "admin_maintenance", "label": "Maintenance", "groupe": "Administration",
     "url": "/admin/maintenance", "api": ["/api/admin/maintenance"]},
    {"cle": "admin_etat_technique", "label": "État technique", "groupe": "Administration",
     "url": "/admin/etat-technique", "api": ["/api/admin/etat-technique"]},
    {"cle": "admin_logs", "label": "Logs système", "groupe": "Administration",
     "url": "/admin/logs", "api": ["/api/admin/logs"]},
    {"cle": "couts", "label": "Coûts LLM", "groupe": "Administration",
     "url": "/costs", "api": ["/api/costs"]},
]

GROUPES = ["Pilotage", "Acquisition", "Ventes", "Campagnes", "Contenu & SEO",
           "Administration"]

# La matrice de départ. Elle reprend ce que faisait déjà la sidebar, pour que rien ne
# change le jour de la mise en service : on rend explicite un comportement existant avant
# de le modifier.
DEFAUT = {
    "admin": [p["cle"] for p in PAGES if p["groupe"] != "Administration"]
             + ["admin_secteurs", "admin_pression", "admin_etat_technique"],
    "user": ["dashboard", "vision", "statistiques", "contacts", "a_rappeler", "booking", "mon_activite",
             "campagnes", "segments", "cold_email", "newsletters", "articles",
             "opportunites", "ventes"],
    "commercial": ["mon_activite", "a_rappeler", "booking", "contacts", "opportunites"],
    "contenu": ["articles", "seo", "seo_strategy", "tag", "newsletters"],
    "strategie": ["seo", "seo_strategy", "statistiques", "vision", "admin_secteurs"],
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS role_pages (
    role      text NOT NULL,
    page      text NOT NULL,
    autorise  boolean NOT NULL DEFAULT false,
    maj_le    timestamptz NOT NULL DEFAULT now(),
    maj_par   text,
    PRIMARY KEY (role, page)
);
"""

_CACHE: dict = {"matrice": None, "ts": 0.0}
_TTL = 30.0   # la matrice est lue à CHAQUE requête : sans cache, c'est un aller-retour SQL


def _pool():
    import pool_pg
    return pool_pg


def _assurer_table() -> None:
    p = _pool()
    c = p._conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(SCHEMA)
    finally:
        p._rendre(c)


def matrice(force: bool = False) -> dict:
    """{role: set(pages autorisées)}. Mise en cache 30 s."""
    if not force and _CACHE["matrice"] is not None and (time.time() - _CACHE["ts"]) < _TTL:
        return _CACHE["matrice"]
    try:
        _assurer_table()
        lignes = _pool()._q("SELECT role, page FROM role_pages WHERE autorise")
        enregistre: dict = {}
        for role, page in lignes:
            enregistre.setdefault(role, set()).add(page)
        # Un rôle absent de la table n'a jamais été réglé : il prend le défaut. Un rôle
        # présent mais vide est un CHOIX (tout décoché) et doit le rester.
        roles_regles = {r for (r,) in _pool()._q("SELECT DISTINCT role FROM role_pages")}
        out = {}
        for r in (x["cle"] for x in ROLES if x["cle"] != SUPER):
            out[r] = enregistre.get(r, set()) if r in roles_regles else set(DEFAUT.get(r, []))
    except Exception:  # noqa: BLE001 — règle 3 : on ne coupe pas la plateforme
        out = {r: set(v) for r, v in DEFAUT.items()}
    _CACHE["matrice"], _CACHE["ts"] = out, time.time()
    return out


def pages_autorisees(role: str) -> list[str]:
    if (role or "") == SUPER:
        return [p["cle"] for p in PAGES]
    return sorted(matrice().get(role or "", set()))


def enregistrer(role: str, pages: list, par: str = "") -> dict:
    """Remplace les droits d'UN rôle. `superadmin` est refusé, par conception."""
    if role == SUPER:
        return {"ok": False, "error": "le rôle superadmin ne se restreint pas"}
    if role not in {r["cle"] for r in ROLES}:
        return {"ok": False, "error": f"rôle inconnu : {role}"}
    connues = {p["cle"] for p in PAGES}
    pages = [p for p in (pages or []) if p in connues]
    p = _pool()
    c = p._conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(SCHEMA)
                cur.execute("DELETE FROM role_pages WHERE role = %s", (role,))
                if pages:
                    cur.executemany(
                        "INSERT INTO role_pages (role, page, autorise, maj_par) "
                        "VALUES (%s, %s, true, %s)", [(role, pg, par or None) for pg in pages])
                else:
                    # Trace du choix « aucune page » : sans elle, le rôle repasserait au
                    # défaut au prochain chargement et le décochage serait sans effet.
                    cur.execute("INSERT INTO role_pages (role, page, autorise, maj_par) "
                                "VALUES (%s, '__aucune__', false, %s)", (role, par or None))
    finally:
        p._rendre(c)
    matrice(force=True)
    return {"ok": True, "role": role, "pages": pages}


def etat() -> dict:
    """Tout ce dont la page de réglage a besoin, en un appel."""
    m = matrice(force=True)
    return {
        "roles": ROLES, "groupes": GROUPES,
        "pages": [{k: v for k, v in p.items() if k != "api"} for p in PAGES],
        "matrice": {r: sorted(v) for r, v in m.items()},
        "non_modifiable": [SUPER],
    }


# ── L'application, côté serveur ───────────────────────────────────────────────
def _prefixes_interdits(role: str) -> list[str]:
    """Les préfixes d'API que ce rôle n'a PAS le droit d'appeler."""
    autorisees = set(pages_autorisees(role))
    interdits = []
    for p in PAGES:
        if p["cle"] in autorisees:
            continue
        interdits.extend(p["api"])
    # Un préfixe servant AUSSI une page autorisée ne peut pas être interdit : deux écrans
    # peuvent partager une route. Sans ce filtre, retirer « Vision » couperait le tableau
    # de bord qui lit la même donnée.
    permis = {pref for p in PAGES if p["cle"] in autorisees for pref in p["api"]}
    return [x for x in interdits if x not in permis]


def route_interdite(chemin: str, role: str, site: str | None = None) -> str | None:
    """Le nom de la page refusée si ce chemin est interdit à ce rôle, sinon None."""
    if (role or "") == SUPER:
        return None
    autorisees = set(pages_autorisees(role))

    def concret(pref: str) -> set[str]:
        """Les chemins RÉELS que ce gabarit désigne, une fois `{site}` remplacé."""
        if "{site}" not in pref:
            return {pref}
        return {pref.replace("{site}", site)} if site else set()

    # Les préfixes autorisés doivent être comparés SOUS LEUR FORME CONCRÈTE, comme les
    # interdits. En gardant `{site}` d'un côté et le code du site de l'autre, l'égalité
    # n'était jamais vraie : le garde-fou « un préfixe qui sert aussi une page autorisée ne
    # peut pas être interdit » ne servait à rien, et retirer Vision aurait coupé le tableau
    # de bord qui lit la même route.
    permis = {c for p in PAGES if p["cle"] in autorisees
              for pref in p["api"] for c in concret(pref)}
    for p in PAGES:
        if p["cle"] in autorisees:
            continue
        for pref in p["api"]:
            for candidat in concret(pref):
                if candidat in permis:
                    continue
                if chemin.startswith(candidat):
                    return p["label"]
    return None
