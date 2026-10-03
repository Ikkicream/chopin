#!/usr/bin/env python3
"""secteurs_backend.py — La politique des secteurs : prioritaire / secondaire / interdit.

Ce classement n'est pas décoratif : il PILOTE réellement deux choses.

  1. **L'ordre de la file de scraping** (`autoscrape_targets`). Les cibles d'un secteur
     prioritaire passent avant celles d'un secondaire ; un secteur interdit ne produit
     aucune cible et ses cibles existantes sont retirées de la file.
  2. **Le ciblage Basile.** Chaque secteur porte ses codes NAF ; `basile_backend` refuse
     désormais de collecter un secteur interdit, même appelé directement.

Pourquoi trois rangs et pas un simple ordre : « interdit » n'est pas « dernier ». Un
concurrent qui revend du SMS ou un cabinet soumis au démarchage réglementé ne doit jamais
être collecté, même si la file se vide. Le distinguer d'un secteur simplement moins
intéressant évite qu'un jour de disette ne le fasse remonter.

Stockage : table `sector_policy` (PostgreSQL). Tant que rien n'est enregistré, la
proposition ci-dessous s'applique — elle est marquée comme telle (`source = "defaut"`),
pour qu'on ne confonde jamais un choix de Camille avec une suggestion de la machine.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

RANGS = ("prioritaire", "secondaire", "interdit")


# ── Catalogue ────────────────────────────────────────────────────────────────────
# `naf` : codes NAF pour Basile. `naf_verifie` distingue les mappings CONFIRMÉS en
# production (repris de `basile_backend.SECTOR_NAF`, testés le 2026-06-17) de ceux ajoutés
# depuis le catalogue officiel sans avoir encore rapporté un seul contact. Un secteur sans
# NAF reste collectable par Serper : il n'est pas invalide, il est juste hors de Basile.
CATALOGUE: dict[str, dict] = {
    "immobilier":        {"label": "Immobilier",              "famille": "base client locale"},
    "restaurant":        {"label": "Restauration",            "famille": "base client locale"},
    "coiffeur":          {"label": "Coiffure & barbier",      "famille": "base client locale"},
    "garagiste":         {"label": "Garages & carrosserie",   "famille": "base client locale"},
    # `garagiste` = 45.20A/B, l'ENTRETIEN et la réparation. Il ne couvre pas la VENTE de
    # véhicules : un concessionnaire ou un mandataire relève de 45.11Z, un code que le
    # catalogue n'avait pas. Camille l'avait rangé sous « garages » faute de mieux, et
    # cherchait donc des vendeurs de voitures dans un fichier de garagistes.
    "concession-auto":   {"label": "Concession & mandataire auto", "famille": "base client locale",
                          "naf": ["45.11Z", "45.19Z"], "naf_verifie": False},
    "opticien":          {"label": "Opticiens",              "famille": "base client locale",
                          "naf": ["47.78A"], "naf_verifie": False},
    "boulanger":         {"label": "Boulangerie",             "famille": "base client locale"},
    "fleuriste":         {"label": "Fleuristes",              "famille": "base client locale"},
    "retail":            {"label": "Commerce de détail",      "famille": "base client locale"},
    "tourisme":          {"label": "Hôtellerie & tourisme",   "famille": "base client locale",
                          "naf": ["55.10Z", "55.20Z", "79.11Z", "79.12Z"], "naf_verifie": False},
    "education-formation": {"label": "Écoles & formation",    "famille": "base client locale",
                          "naf": ["85.59A", "85.59B", "85.53Z"], "naf_verifie": False},
    "artisan":           {"label": "Artisans du bâtiment",    "famille": "cycle long"},
    "plombier":          {"label": "Plomberie",               "famille": "cycle long"},
    "electricien":       {"label": "Électricité",             "famille": "cycle long"},
    "menuisier":         {"label": "Menuiserie",              "famille": "cycle long"},
    "transport":         {"label": "Transport & logistique",  "famille": "cycle long",
                          "naf": ["49.41A", "49.41B", "49.32Z"], "naf_verifie": False},
    "industrie":         {"label": "Industrie",               "famille": "cycle long",
                          "naf": ["25.62A", "25.62B", "33.12Z"], "naf_verifie": False},
    "agroalimentaire":   {"label": "Agroalimentaire",         "famille": "cycle long",
                          "naf": ["10.13A", "10.71D", "11.02A"], "naf_verifie": False},
    "luxe-mode":         {"label": "Mode & maroquinerie",     "famille": "cycle long",
                          "naf": ["47.71Z", "47.72A", "47.77Z"], "naf_verifie": False},
    "services-b2b":      {"label": "Services aux entreprises", "famille": "cycle long",
                          "naf": ["82.99Z", "82.11Z"], "naf_verifie": False},
    "consultant":        {"label": "Conseil",                 "famille": "cycle long"},
    "agence-marketing":  {"label": "Agences marketing",       "famille": "concurrent"},
    "agence-web":        {"label": "Agences web",             "famille": "concurrent"},
    "tech-digital":      {"label": "Éditeurs & tech",         "famille": "concurrent",
                          "naf": ["62.01Z", "62.02A", "63.11Z"], "naf_verifie": False},
    "banque":            {"label": "Banque",                  "famille": "démarchage réglementé",
                          "naf": ["64.19Z", "64.92Z"], "naf_verifie": False},
    "assurance":         {"label": "Assurance & courtage",    "famille": "démarchage réglementé",
                          "naf": ["65.12Z", "66.22Z"], "naf_verifie": False},
    "avocat":            {"label": "Avocats",                 "famille": "démarchage réglementé"},
    "comptable":         {"label": "Experts-comptables",      "famille": "démarchage réglementé"},
    "energie":           {"label": "Énergie & fournisseurs",  "famille": "démarchage réglementé",
                          "naf": ["35.11Z", "35.14Z"], "naf_verifie": False},
    "sante-pharma":      {"label": "Santé & pharmacie",       "famille": "données sensibles",
                          "naf": ["47.73Z", "86.21Z", "86.23Z"], "naf_verifie": False},
}

# Proposition du 2026-08-20, déduite du produit : leclientroi.com vend du SMS/RCS géolocalisé
# pour réactiver une base clients locale (promo, rappel de RDV, alerte). D'où le tri :
# prioritaire = base récurrente + achat impulsif ; secondaire = cycle long ou base faible ;
# interdit = concurrents, démarchage réglementé, données de santé (RGPD).
DEFAUT: dict[str, list[str]] = {
    "prioritaire": ["immobilier", "restaurant", "coiffeur", "garagiste", "boulanger",
                    "fleuriste", "retail", "tourisme", "education-formation",
                    "concession-auto", "opticien", "agence-marketing", "agence-web"],
    "secondaire":  ["artisan", "plombier", "electricien", "menuisier", "transport",
                    "industrie", "agroalimentaire", "luxe-mode", "services-b2b",
                    "consultant"],
    # 2026-08-29 : les agences marketing et web SORTENT de l'interdit. Elles y étaient au
    # titre de « concurrent », ce qui était faux — elles ne vendent pas de SMS marketing
    # local. Les deux vrais concurrents sont des SOCIÉTÉS, pas des secteurs : wellpack.fr
    # et spot-hit.fr, écartées nominativement par `email_validator.is_concurrent`. Ce qui
    # reste interdit ici l'est pour une raison de DROIT (démarchage réglementé) ou de
    # données sensibles — pas de concurrence.
    "interdit":    ["tech-digital", "banque", "assurance", "avocat", "comptable",
                    "energie", "sante-pharma"],
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS sector_policy (
    site_code   text NOT NULL,
    secteur     text NOT NULL,
    rang        text NOT NULL CHECK (rang IN ('prioritaire', 'secondaire', 'interdit')),
    position    int  NOT NULL DEFAULT 0,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    updated_by  text,
    PRIMARY KEY (site_code, secteur)
);
"""


def _pool():
    import pool_pg
    return pool_pg


def _naf(code: str) -> tuple[list[str], bool]:
    """(codes NAF, confirmés en production ?) pour un secteur."""
    fiche = CATALOGUE.get(code) or {}
    try:
        import basile_backend as bb
        confirmes = bb.SECTOR_NAF.get(code)
    except Exception:  # noqa: BLE001 — Basile absent ne doit pas casser la page
        confirmes = None
    if confirmes:
        return list(confirmes), True
    return list(fiche.get("naf") or []), bool(fiche.get("naf_verifie"))


def _assurer_table() -> None:
    pool_pg = _pool()
    c = pool_pg._conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(SCHEMA)
    finally:
        pool_pg._rendre(c)


def politique(site: str = "lcr") -> dict:
    """Le classement en vigueur, avec sa provenance.

    Retourne `{"source": "defaut"|"enregistre", "prioritaire": [...], "secondaire": [...],
    "interdit": [...], "secteurs": {code: fiche}}`. Les secteurs du catalogue absents du
    classement enregistré atterrissent en secondaire : ajouter une ligne au catalogue ne
    doit jamais faire disparaître un secteur de l'écran ni le rendre implicitement interdit.
    """
    _assurer_table()
    lignes = _pool()._q(
        "SELECT secteur, rang, position FROM sector_policy WHERE site_code = %s "
        "ORDER BY rang, position, secteur", (site,))
    if lignes:
        classement = {r: [] for r in RANGS}
        for secteur, rang, _pos in lignes:
            if secteur in CATALOGUE and rang in classement:
                classement[rang].append(secteur)
        connus = {s for v in classement.values() for s in v}
        classement["secondaire"] += [s for s in CATALOGUE if s not in connus]
        source = "enregistre"
    else:
        classement = {r: list(DEFAUT.get(r) or []) for r in RANGS}
        connus = {s for v in classement.values() for s in v}
        classement["secondaire"] += [s for s in CATALOGUE if s not in connus]
        source = "defaut"

    fiches = {}
    for code, fiche in CATALOGUE.items():
        nafs, verifie = _naf(code)
        fiches[code] = {"code": code, "label": fiche.get("label") or code,
                        "famille": fiche.get("famille") or "",
                        "naf": nafs, "naf_verifie": verifie}
    return {"source": source, "site": site, "secteurs": fiches, **classement}


def enregistrer(site: str, classement: dict, par: str = "ui") -> dict:
    """Enregistre le classement. Rejette tout ce qui n'est pas dans le catalogue.

    Écriture en une transaction : un classement à moitié appliqué laisserait des secteurs
    dans deux rangs à la fois, donc une file de scraping incohérente.
    """
    lignes = []
    vus = set()
    for rang in RANGS:
        for position, secteur in enumerate(classement.get(rang) or []):
            if secteur not in CATALOGUE:
                return {"ok": False, "error": f"secteur inconnu : {secteur}"}
            if secteur in vus:
                return {"ok": False, "error": f"secteur en double : {secteur}"}
            vus.add(secteur)
            lignes.append((site, secteur, rang, position, par))
    if not lignes:
        return {"ok": False, "error": "classement vide"}

    _assurer_table()
    pool_pg = _pool()
    c = pool_pg._conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute("DELETE FROM sector_policy WHERE site_code = %s", (site,))
                cur.executemany(
                    "INSERT INTO sector_policy (site_code, secteur, rang, position, updated_by) "
                    "VALUES (%s, %s, %s, %s, %s)", lignes)
    finally:
        pool_pg._rendre(c)

    retires = retirer_cibles_interdites(site)
    rendues = rehabiliter_cibles_autorisees(site)
    return {"ok": True, "enregistres": len(lignes),
            "cibles_retirees": retires.get("retirees", 0),
            "cibles_rendues": rendues.get("rehabilitees", 0),
            **{r: [l[1] for l in lignes if l[2] == r] for r in RANGS}}


def ordre_scraping(site: str = "lcr") -> list[str]:
    """Les secteurs collectables, dans l'ordre : prioritaires puis secondaires.

    Les interdits n'y figurent pas — c'est cette liste que consomme `autoscrape_daily`
    pour semer la file et pour trier les cibles.
    """
    p = politique(site)
    return list(p["prioritaire"]) + list(p["secondaire"])


def interdits(site: str = "lcr") -> set[str]:
    return set(politique(site)["interdit"])


def est_interdit(secteur: str, site: str = "lcr") -> bool:
    return secteur in interdits(site)


def retirer_cibles_interdites(site: str = "lcr") -> dict:
    """Sort de la file les cibles des secteurs devenus interdits.

    Elles passent en `interdit` plutôt que d'être supprimées : la mémoire de ce qui a déjà
    été collecté sert au dédoublonnage et aux compteurs. Le statut suffit à les écarter,
    la file ne piochant que les `pending`.
    """
    import duckdb
    from duck_ouverture import ouvrir
    inter = interdits(site)
    if not inter:
        return {"retirees": 0, "secteurs": []}
    try:
        c = ouvrir(BASE_DIR / "data" / "god_mode.duckdb")
    except duckdb.Error as e:  # noqa: BLE001 — base occupée : ce n'est pas bloquant
        return {"retirees": 0, "erreur": str(e)}
    try:
        n = c.execute(
            "SELECT count(*) FROM autoscrape_targets WHERE site_code = ? AND status = 'pending' "
            "AND sector = ANY(?)", [site, list(inter)]).fetchone()
        c.execute(
            "UPDATE autoscrape_targets SET status = 'interdit' WHERE site_code = ? "
            "AND status = 'pending' AND sector = ANY(?)", [site, list(inter)])
    finally:
        c.close()
    return {"retirees": int(n[0] or 0), "secteurs": sorted(inter)}


def rehabiliter_cibles_autorisees(site: str = "lcr") -> dict:
    """Remet en file les cibles d'un secteur qui n'est PLUS interdit.

    `retirer_cibles_interdites` n'avait pas d'inverse : autoriser un secteur à l'écran
    changeait le classement, mais ses cibles restaient au statut `interdit` et la file
    continuait de les ignorer — silencieusement, puisque rien ne distingue « aucune cible »
    de « cibles écartées ». Constaté le 2026-08-29 en sortant les agences de l'interdit :
    188 cibles seraient restées mortes. Le retrait et la réhabilitation vont par paire.

    On ne touche QUE le statut `interdit` : une cible `done` ou `retired` a été écartée
    pour une autre raison — objectif atteint, trois passes consommées — et la rouvrir
    relancerait une collecte que les compteurs ont déjà close.
    """
    import duckdb
    from duck_ouverture import ouvrir
    inter = interdits(site)
    try:
        c = ouvrir(BASE_DIR / "data" / "god_mode.duckdb")
    except duckdb.Error as e:  # noqa: BLE001 — base occupée : ce n'est pas bloquant
        return {"rehabilitees": 0, "erreur": str(e)}
    try:
        n = c.execute(
            "SELECT count(*) FROM autoscrape_targets WHERE site_code = ? AND status = 'interdit' "
            "AND NOT (sector = ANY(?))", [site, list(inter) or [""]]).fetchone()
        c.execute(
            "UPDATE autoscrape_targets SET status = 'pending' WHERE site_code = ? "
            "AND status = 'interdit' AND NOT (sector = ANY(?))", [site, list(inter) or [""]])
    finally:
        c.close()
    return {"rehabilitees": int(n[0] or 0)}


def resume_file(site: str = "lcr") -> dict:
    """Combien de cibles attendent, par rang — le « et concrètement, ça change quoi ? »."""
    import duckdb
    from duck_ouverture import ouvrir
    p = politique(site)
    rang_de = {s: r for r in RANGS for s in p[r]}
    try:
        c = ouvrir(BASE_DIR / "data" / "god_mode.duckdb")
    except duckdb.Error as e:  # noqa: BLE001
        return {"erreur": str(e)}
    try:
        rows = c.execute(
            "SELECT sector, status, count(*) FROM autoscrape_targets WHERE site_code = ? "
            "GROUP BY 1, 2", [site]).fetchall()
    finally:
        c.close()
    par_rang = {r: 0 for r in RANGS}
    en_attente = 0
    for secteur, statut, n in rows:
        if statut != "pending":
            continue
        en_attente += int(n)
        par_rang[rang_de.get(secteur, "secondaire")] += int(n)
    return {"cibles_en_attente": en_attente, "par_rang": par_rang}


if __name__ == "__main__":
    import json
    cmd = sys.argv[1] if len(sys.argv) > 1 else "politique"
    site = sys.argv[2] if len(sys.argv) > 2 else "lcr"
    if cmd == "politique":
        out = politique(site)
    elif cmd == "ordre":
        out = ordre_scraping(site)
    elif cmd == "file":
        out = resume_file(site)
    elif cmd == "nettoyer":
        out = retirer_cibles_interdites(site)
    else:
        out = {"error": f"commande inconnue : {cmd}"}
    print(json.dumps(out, ensure_ascii=False, indent=2))
