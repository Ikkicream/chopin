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
#
# `aide` = à quoi sert la page, en une phrase. Posé ICI et pas dans le guide, parce que la
# documentation était un texte unique qui décrivait des pages que la moitié des comptes ne
# voit pas — un commercial y lisait comment lancer un scraping. La même table décide donc
# désormais ce qu'on VOIT et ce qu'on LIT : ajouter une page sans sa phrase se remarque,
# et le guide ne peut plus parler d'un écran qui n'existe plus.
PAGES = [
    # — Pilotage —
    {"cle": "dashboard", "label": "Tableau de bord", "groupe": "Pilotage",
     "aide": "L'état du jour en un écran : ce qui est parti, ce qui est entré, ce qui alerte.",
     "url": "/site/{site}/dashboard", "api": ["/api/sites/{site}/marketing/overview"]},
    {"cle": "vision", "label": "Vision", "groupe": "Pilotage",
     "aide": "La vue d'ensemble du site : volumes, tendances, santé de la base.",
     "url": "/site/{site}/vision", "api": ["/api/sites/{site}/vision"]},
    {"cle": "statistiques", "label": "Statistiques", "groupe": "Pilotage",
     "aide": "Les résultats mesurés : envois, ouvertures, clics, par campagne et par jour. "
             "C'est l'outil d'arbitrage — sans lui on décide à l'intuition.",
     "url": "/site/{site}/statistiques", "api": ["/api/sites/{site}/statistiques"]},

    # — Acquisition —
    {"cle": "contacts", "label": "Contacts", "groupe": "Acquisition",
     "aide": "Le fichier : chercher, filtrer, ouvrir une fiche, voir l'historique d'un contact.",
     "url": "/site/{site}/acquisition",
     "api": ["/api/sites/{site}/acquisition", "/api/sites/{site}/pool/"]},
    {"cle": "a_rappeler", "label": "À rappeler", "groupe": "Acquisition",
     "aide": "Ta liste d'appels du jour, avec le script et la fiche à portée de main.",
     "url": "/site/{site}/a-rappeler", "api": ["/api/sites/{site}/a-rappeler"]},
    {"cle": "mon_activite", "label": "Mon activité (commercial)", "groupe": "Acquisition",
     "aide": "Ce que TU as fait : appels passés, rendez-vous pris, contacts qui te sont attribués.",
     "url": "/site/{site}/mon-activite", "api": ["/api/sites/{site}/mon-activite"]},
    {"cle": "opportunites", "label": "Opportunités", "groupe": "Ventes",
     "aide": "Les affaires en cours, de la prise de contact à la décision.",
     "url": "/site/{site}/opportunites", "api": ["/api/sites/{site}/opportunites"]},
    {"cle": "ventes", "label": "Ventes", "groupe": "Ventes",
     "aide": "Ce qui est signé, et ce que ça représente.",
     "url": "/site/{site}/ventes", "api": ["/api/sites/{site}/ventes"]},
    {"cle": "booking", "label": "Rendez-vous", "groupe": "Acquisition",
     "aide": "L'agenda des rendez-vous pris, et par qui.",
     "url": "/site/{site}/booking", "api": ["/api/sites/{site}/booking"]},
    {"cle": "scrapper", "label": "Scraping", "groupe": "Acquisition",
     "aide": "Aller chercher de nouveaux contacts. Attention : chaque passe coûte des "
             "crédits, et la collecte tourne déjà toute seule la nuit.",
     "url": "/site/{site}/scrapper",
     "api": ["/api/sites/{site}/autoscrape", "/api/sites/{site}/scrape/",
             "/api/sites/{site}/stephane/", "/api/god-mode/{site}"]},
    {"cle": "scrapper_activite", "label": "Activité des scrapes", "groupe": "Acquisition",
     "aide": "Ce que la collecte a fait cette nuit : cibles, retenus, écartés et pourquoi.",
     "url": "/site/{site}/scrapper/activite", "api": []},

    # — Campagnes —
    {"cle": "cold_email", "label": "Cold email", "groupe": "Campagnes",
     "aide": "La galerie des messages : cold emails ET newsletters dans une seule table, "
             "filtrable par secteur, avec ce que chacun a réellement produit.",
     "url": "/site/{site}/cold-email", "api": ["/api/sites/{site}/cold-email"]},
    {"cle": "newsletters", "label": "Newsletters", "groupe": "Campagnes",
     "aide": "L'éditeur par blocs des emailings : bannière, titre, images, pied de page.",
     "url": "/site/{site}/newsletters", "api": ["/api/sites/{site}/newsletters"]},
    {"cle": "campagnes", "label": "Campagnes", "groupe": "Campagnes",
     "aide": "Décider QUI reçoit QUOI, et à quel rythme. Créer une campagne reste une "
             "décision humaine : la machine prolonge, elle n'invente pas.",
     "url": "/site/{site}/campaigns", "api": ["/api/sites/{site}/campaigns"]},
    {"cle": "segments", "label": "Segments", "groupe": "Campagnes",
     "aide": "Composer une cible par règles (ET / OU / exclusion) et la réutiliser.",
     "url": "/site/{site}/segments", "api": ["/api/sites/{site}/segments"]},
    # Mozart doit figurer ICI pour exister aux yeux de la matrice des droits. Une page
    # absente de ce registre n'est pas « ouverte à tous » : elle est invisible du réglage
    # par rôle, donc impossible à retirer à quelqu'un — et personne ne s'en aperçoit avant
    # d'en avoir besoin.
    # `beta: True` : la page reste VISIBLE de tous — grisée, avec une étiquette — mais
    # n'est utilisable que par les comptes de la liste ci-dessous. Visible plutôt que
    # cachée, parce qu'une fonctionnalité qui apparaît un jour sans prévenir surprend, et
    # qu'une équipe qui la voit arriver pose ses questions avant, pas après.
    {"cle": "mozart", "label": "Mozart (scénarios)", "groupe": "Campagnes", "beta": True,
     "aide": "Des scénarios qui s'exécutent tout seuls : déclencheur, délai, email, "
             "condition. Un nœud peut suivre le secteur du contact. Le graphe affiché est "
             "celui qui tourne.",
     "url": "/site/{site}/mozart",
     "api": ["/api/sites/{site}/mozart", "/api/sites/{site}/mozart-expediteurs"]},

    {"cle": "expediteurs", "label": "Adresses d'envoi", "groupe": "Configuration",
     "aide": "Les boîtes qui envoient, leur plafond du jour et leur montée en charge. "
             "Un contact garde SON adresse à vie : y toucher se paie en réputation.",
     "url": "/site/{site}/setup/expediteurs", "api": ["/api/sites/{site}/expediteurs"]},

    # — Téléphonie (Onoff Business) —
    # En bêta comme Mozart : le connecteur dépend d'un abonnement Onoff « Max » pour
    # l'API, et la partie appel repose sur l'application Onoff installée côté poste.
    # Autant l'éprouver sur un compte avant de l'ouvrir à l'équipe.
    {"cle": "onoff", "label": "Téléphonie (ON/OFF)", "groupe": "Acquisition", "beta": True,
     "aide": "Le suivi des appels ON/OFF. Lecture seule : ni appel ni SMS depuis ici, "
             "c'est l'application Onoff qui les passe.",
     "url": "/site/{site}/onoff",
     "api": ["/api/sites/{site}/onoff", "/api/sites/{site}/onoff/etat"]},
    {"cle": "onoff_messagerie", "label": "Répondeur", "groupe": "Acquisition", "beta": True,
     "aide": "Les messages laissés sur le répondeur, transmis par webhook.",
     "url": "/site/{site}/onoff/messagerie",
     "api": ["/api/sites/{site}/onoff/messagerie"]},

    # — Contenu & SEO —
    {"cle": "articles", "label": "Articles", "groupe": "Contenu & SEO",
     "aide": "Les articles du blog : file de rédaction, relecture, publication.",
     "url": "/site/{site}/articles", "api": ["/api/articles"]},
    {"cle": "seo", "label": "Analyse SEO", "groupe": "Contenu & SEO",
     "aide": "Les positions et les liens, tirés d'Ahrefs. Les données arrivent par un cron "
             "quotidien : rafraîchir ici ne va pas plus vite.",
     "url": "/site/{site}/seo", "api": ["/api/seo-ahrefs/{site}"]},
    {"cle": "seo_strategy", "label": "Stratégie SEO", "groupe": "Contenu & SEO",
     "aide": "Ce qu'il faudrait écrire, et pourquoi : mots-clés visés, trous à combler.",
     "url": "/site/{site}/seo-strategy", "api": ["/api/seo-strategy/{site}"]},
    {"cle": "tag", "label": "Plan de taggage", "groupe": "Contenu & SEO",
     "aide": "L'organisation des étiquettes du site, pour que le contenu se range tout seul.",
     "url": "/site/{site}/tag", "api": ["/api/sites/{site}/tag"]},
    {"cle": "agents", "label": "Agents IA", "groupe": "Contenu & SEO",
     "aide": "Les agents qui écrivent et analysent, leur planning et leur dernier passage.",
     "url": "/site/{site}/agents", "api": ["/api/agents/{site}"]},

    # — Administration —
    {"cle": "admin_users", "label": "Utilisateurs", "groupe": "Administration",
     "aide": "Les comptes, leur rôle, et la matrice qui décide qui voit quoi.",
     "url": "/admin/users", "api": ["/api/auth/users", "/api/auth/logs", "/api/admin/roles"]},
    {"cle": "admin_secteurs", "label": "Secteurs", "groupe": "Administration",
     "aide": "Quels métiers on démarche, dans quel ordre, et lesquels sont interdits.",
     "url": "/admin/secteurs", "api": ["/api/admin/secteurs"]},
    {"cle": "admin_pression", "label": "Pression marketing", "groupe": "Administration",
     "aide": "À quelle fréquence une même personne peut être sollicitée. Un email reçu "
             "vaut 120 jours de silence — cette règle ne s'assouplit pas.",
     "url": "/admin/pression", "api": ["/api/admin/pression"]},
    {"cle": "admin_database", "label": "Bases de données", "groupe": "Administration",
     "aide": "L'état des bases et leur volume. À regarder avant de conclure qu'un compteur "
             "ment : une base occupée n'est pas une base en panne.",
     "url": "/admin/database", "api": ["/api/admin/database"]},
    {"cle": "admin_maintenance", "label": "Maintenance", "groupe": "Administration",
     "aide": "Nettoyages, purges et tâches de fond, avec ce qu'elles ont fait la dernière fois.",
     "url": "/admin/maintenance", "api": ["/api/admin/maintenance"]},
    {"cle": "admin_etat_technique", "label": "État technique", "groupe": "Administration",
     "aide": "Ce qui tourne, ce qui est tombé, et depuis quand.",
     "url": "/admin/etat-technique", "api": ["/api/admin/etat-technique"]},
    {"cle": "admin_logs", "label": "Logs système", "groupe": "Administration",
     "aide": "Les journaux bruts, quand le reste ne suffit plus à comprendre.",
     "url": "/admin/logs", "api": ["/api/admin/logs"]},
    {"cle": "couts", "label": "Coûts LLM", "groupe": "Administration",
     "aide": "Ce que consomment les modèles, par agent et par jour.",
     "url": "/costs", "api": ["/api/costs"]},
    # La page existait depuis mai et n'était dans AUCUN registre : donc absente de la
    # barre de gauche, absente du réglage par rôle, absente du guide. Personne ne pouvait
    # la trouver sans connaître son URL. Troisième fois que ce piège se referme — Mozart
    # le 24/08, Onoff et les adresses d'envoi le 25/08 : **une page qui n'est pas ici
    # n'est pas « ouverte à tous », elle est invisible.**
    {"cle": "versions", "label": "Nouveautés et versions", "groupe": "Administration",
     "aide": "Ce qui a changé et quand : corrections, ajouts, sauvegardes, et l'écart "
             "entre ce qui tourne ici et le dépôt distant.",
     "url": "/versions", "api": ["/api/versions"]},
]

GROUPES = ["Pilotage", "Acquisition", "Ventes", "Campagnes", "Contenu & SEO",
           "Configuration", "Administration"]

# La matrice de départ. Elle reprend ce que faisait déjà la sidebar, pour que rien ne
# change le jour de la mise en service : on rend explicite un comportement existant avant
# de le modifier.
DEFAUT = {
    # `versions` est ajouté explicitement : il vit dans « Administration », donc la
    # compréhension par groupe l'exclurait. Savoir ce qui a changé et quand n'est pas un
    # pouvoir d'administration — c'est ce qui permet de comprendre pourquoi un écran ne
    # ressemble plus à hier.
    "admin": [p["cle"] for p in PAGES if p["groupe"] != "Administration"]
             + ["admin_secteurs", "admin_pression", "admin_etat_technique", "versions"],
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
        lignes = _pool()._q("SELECT role, page, autorise FROM role_pages")
        enregistre: dict = {}
        connues_du_role: dict = {}
        for role, page, autorise in lignes:
            connues_du_role.setdefault(role, set()).add(page)
            if autorise:
                enregistre.setdefault(role, set()).add(page)
        # Un rôle absent de la table n'a jamais été réglé : il prend le défaut. Un rôle
        # présent mais vide est un CHOIX (tout décoché) et doit le rester.
        roles_regles = set(connues_du_role)
        toutes = {p["cle"] for p in PAGES}
        out = {}
        for r in (x["cle"] for x in ROLES if x["cle"] != SUPER):
            if r not in roles_regles:
                out[r] = set(DEFAUT.get(r, []))
                continue
            droits = set(enregistre.get(r, set()))
            # Une page que ce rôle n'a JAMAIS vue passer — donc ajoutée après son réglage —
            # n'a pas été refusée : elle n'existait pas. Elle prend le défaut, sinon toute
            # page nouvelle resterait invisible pour toujours et en silence.
            nouvelles = toutes - connues_du_role.get(r, set())
            droits |= (nouvelles & set(DEFAUT.get(r, [])))
            out[r] = droits
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
                # On enregistre les pages REFUSÉES autant que les autorisées. Avant, seules
                # les autorisées étaient écrites : impossible ensuite de distinguer « on a
                # décoché cette page » de « cette page n'existait pas encore ». Conséquence
                # concrète : le jour où un rôle est réglé, toute page ajoutée PLUS TARD lui
                # reste invisible à jamais — et personne ne s'en aperçoit, puisque rien
                # n'apparaît. C'est ce qui est arrivé quatre fois : Mozart le 24/08, Onoff
                # et les adresses d'envoi le 25/08, la page Nouveautés le 26/08.
                #
                # Avec la trace du refus, `matrice()` sait qu'une page absente des lignes
                # d'un rôle réglé est NOUVELLE, et lui applique le défaut.
                choisies = set(pages)
                cur.executemany(
                    "INSERT INTO role_pages (role, page, autorise, maj_par) "
                    "VALUES (%s, %s, %s, %s)",
                    [(role, pg, pg in choisies, par or None) for pg in sorted(connues)])
                if not pages:
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


# Qui a le droit d'utiliser les pages marquées `beta`. Lu dans `.env` pour qu'ouvrir une
# bêta à quelqu'un ne demande pas de toucher au code — ni de redéployer.
#   PAGES_BETA_TESTEURS=camille,gilles
_BETA_CACHE: tuple[float, set[str]] | None = None


def beta_testeurs() -> set[str]:
    """Lu une fois par minute, pas à chaque requête.

    Cette fonction est appelée par le middleware sur CHAQUE requête authentifiée : la
    relire depuis le disque à chaque fois, c'est un accès fichier par requête sur la boucle
    d'événements. Une minute de cache suffit — ouvrir une bêta à quelqu'un peut attendre
    soixante secondes.

    Les guillemets sont retirés : `PAGES_BETA_TESTEURS="camille"` produisait `{'"camille"'}`
    et fermait la bêta à la personne qu'elle devait ouvrir.
    """
    global _BETA_CACHE
    import time
    if _BETA_CACHE and (time.time() - _BETA_CACHE[0]) < 60:
        return _BETA_CACHE[1]
    valeurs = {"camille"}
    try:
        for ligne in (BASE_DIR / ".env").read_text().splitlines():
            if ligne.startswith("PAGES_BETA_TESTEURS="):
                v = ligne.split("=", 1)[1].strip().strip('"').strip("'")
                trouves = {x.strip().strip('"').strip("'").lower()
                           for x in v.split(",") if x.strip()}
                if trouves:
                    valeurs = trouves
                break
    except Exception:  # noqa: BLE001
        pass
    _BETA_CACHE = (time.time(), valeurs)
    return valeurs


def pages_beta() -> set[str]:
    return {p["cle"] for p in PAGES if p.get("beta")}


def beta_interdite(chemin: str, utilisateur: str, site: str | None = None) -> str | None:
    """Le libellé de la page si ce chemin relève d'une bêta fermée à cet utilisateur.

    Le contrôle porte sur le COMPTE, pas sur le rôle : une bêta s'ouvre à des personnes
    nommées, pas à une catégorie. Un superadmin qui n'est pas dans la liste n'y a pas accès
    non plus — sans quoi « réservé à mes tests » ne voudrait rien dire.
    """
    if (utilisateur or "").strip().lower() in beta_testeurs():
        return None
    for p in PAGES:
        if not p.get("beta"):
            continue
        for pref in p["api"]:
            if "{site}" not in pref:
                if chemin.startswith(pref):
                    return p["label"]
                continue
            if site:
                if chemin.startswith(pref.replace("{site}", site)):
                    return p["label"]
                continue
            # Site inconnu ou absent : on ne peut pas construire le chemin exact, mais on
            # peut reconnaître sa FORME. Sans cela, `/api/sites/zzz/mozart/<id>` échappait
            # au contrôle — un code de site inventé suffisait à ouvrir la bêta.
            # Un garde-fou qui s'annule sur une entrée inattendue n'est pas un garde-fou.
            debut, fin = pref.split("{site}", 1)
            if chemin.startswith(debut) and fin.lstrip("/").split("/")[0] in chemin:
                return p["label"]
    return None


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
