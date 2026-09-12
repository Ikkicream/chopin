#!/usr/bin/env python3
"""stephane.py — L'agent qui choisit quoi collecter, et ce qu'il a retenu.

Stéphane décide de la prochaine cible de collecte : un couple secteur × département. Il ne
devine pas, il compte — et il garde trace de ce qu'il a compté, pour que sa décision
d'aujourd'hui tienne compte de ce qu'il a observé la semaine dernière.

**Sa mémoire** (`memoire_stephane`) est ce qui le distingue d'un simple tri. À chaque
passage il fige, pour chaque couple secteur × département : combien d'emails y sont partis,
combien ont été ouverts, combien cliqués, combien de contacts on y possède, et combien de
fois on y a collecté. Cette table ne se réécrit pas au gré des jointures — comme
`stats_secteur_jour`, elle FIGE, parce qu'un contact sorti du pool ne doit pas effacer
rétroactivement la performance d'une zone.

**Ce qu'il regarde pour décider**, dans cet ordre d'importance :
  1. le rang du secteur (politique des secteurs) — un interdit n'est jamais proposé ;
  2. la performance MESURÉE du couple secteur × zone : d'abord le clic, puis l'ouverture.
     Le clic vaut plus que l'ouverture — une ouverture peut venir d'un proxy antispam, un
     clic est un geste. À défaut de mesure sur le couple, il se rabat sur la zone seule ;
  3. le terrain neuf : un couple jamais collecté vaut mieux qu'un couple déjà ratissé ;
  4. la rareté en base : inutile de retourner là où l'on a déjà tout pris.

**Ce qu'il ne fait pas** : lancer une collecte. Il propose, l'orchestrateur exécute.

**Pourquoi aucun modèle de langage.** Cette décision engage le budget Serper (7 crédits par
contact). Une note qu'on peut recalculer à la main se conteste, se corrige et s'explique ;
un avis de modèle ne se vérifie pas. Stéphane rend donc toujours sa note AVEC la phrase
qui la justifie.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

NOM = "Stéphane"

# Les poids. Ils sont ici, en clair, parce qu'ils se discutent : c'est la seule chose à
# changer si Camille juge qu'une zone qui répond compte plus que du terrain neuf.
POIDS = {
    "rang_prioritaire": 30,
    "rang_secondaire": 10,
    "performance": 30,      # clic + ouverture mesurés sur le couple secteur × zone
    "terrain_neuf": 20,
    "peu_possede": 20,
}

# Sous ce volume d'envois, un taux n'est pas un taux : c'est un accident.
MIN_ENVOIS = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS memoire_stephane (
    site_code    text NOT NULL,
    secteur      text NOT NULL,
    dept_code    text NOT NULL,
    envois       int  NOT NULL DEFAULT 0,
    ouvreurs     int  NOT NULL DEFAULT 0,
    cliqueurs    int  NOT NULL DEFAULT 0,
    taux_ouverture double precision,
    taux_clic      double precision,
    contacts_base  int NOT NULL DEFAULT 0,
    collectes      int NOT NULL DEFAULT 0,
    observe_le   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (site_code, secteur, dept_code)
);
CREATE INDEX IF NOT EXISTS idx_memoire_perf
    ON memoire_stephane (site_code, taux_clic DESC NULLS LAST);
"""


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


def observer(site: str = "lcr") -> dict:
    """Met la mémoire à jour depuis ce qui est mesurable aujourd'hui.

    Appelé après chaque reconstruction des statistiques. Les couples déjà connus sont
    ACTUALISÉS (les chiffres d'engagement ne font que grossir) ; les couples qui
    disparaissent des sources gardent leur dernière valeur connue — c'est le principe même
    d'une mémoire.
    """
    _assurer_table()
    p = _pool()
    c = p._conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO memoire_stephane (site_code, secteur, dept_code, envois,
                        ouvreurs, cliqueurs, taux_ouverture, taux_clic, contacts_base, observe_le)
                    SELECT r.site_code, r.secteur, r.dept_code, count(*),
                           count(r.opened_at), count(r.clicked_at),
                           round(100.0 * count(r.opened_at)  / NULLIF(count(*), 0), 1)::float8,
                           round(100.0 * count(r.clicked_at) / NULLIF(count(*), 0), 1)::float8,
                           0, now()
                    FROM campaign_recipients r
                    WHERE r.site_code = %s AND r.secteur <> 'inconnu' AND r.dept_code <> 'inconnu'
                    GROUP BY r.site_code, r.secteur, r.dept_code
                    ON CONFLICT (site_code, secteur, dept_code) DO UPDATE SET
                        envois = EXCLUDED.envois, ouvreurs = EXCLUDED.ouvreurs,
                        cliqueurs = EXCLUDED.cliqueurs,
                        taux_ouverture = EXCLUDED.taux_ouverture,
                        taux_clic = EXCLUDED.taux_clic, observe_le = now()
                """, (site,))
                # Ce qu'on possède en base, couple par couple.
                cur.execute("""
                    INSERT INTO memoire_stephane (site_code, secteur, dept_code, contacts_base)
                    SELECT %s, COALESCE(sectors[1], '?'), COALESCE(dept_code, '?'), count(*)
                    FROM contacts WHERE etat = 'ok'
                      AND dept_code IS NOT NULL AND sectors IS NOT NULL
                    GROUP BY 2, 3
                    ON CONFLICT (site_code, secteur, dept_code) DO UPDATE SET
                        contacts_base = EXCLUDED.contacts_base
                """, (site,))
                cur.execute("SELECT count(*) FROM memoire_stephane WHERE site_code = %s", (site,))
                n = cur.fetchone()[0]
    finally:
        p._rendre(c)
    return {"ok": True, "couples_en_memoire": n}


def memoire(site: str = "lcr", limite: int = 20) -> dict:
    """Ce que Stéphane a retenu — les couples qui marchent, ceux qui ne marchent pas."""
    try:
        _assurer_table()
        lignes = _pool()._q("""
            SELECT secteur, dept_code, envois, ouvreurs, cliqueurs,
                   taux_ouverture, taux_clic, contacts_base, collectes, observe_le::text
            FROM memoire_stephane
            WHERE site_code = %s AND envois >= %s
            ORDER BY taux_clic DESC NULLS LAST, taux_ouverture DESC NULLS LAST
            LIMIT %s""", (site, MIN_ENVOIS, limite))
    except Exception:  # noqa: BLE001
        return {"couples": [], "erreur": "mémoire indisponible"}
    return {"couples": [
        {"secteur": r[0], "dept": r[1], "envois": r[2], "ouvreurs": r[3], "cliqueurs": r[4],
         "taux_ouverture": r[5], "taux_clic": r[6], "contacts_base": r[7],
         "collectes": r[8], "observe_le": r[9]} for r in lignes],
        "seuil_envois": MIN_ENVOIS}


def _perf(site: str) -> tuple[dict, dict]:
    """({(secteur,dept): (ouv, clic)}, {dept: (ouv, clic)}) — la mesure fine et son repli."""
    fin: dict = {}
    zone: dict = {}
    try:
        _assurer_table()
        for r in _pool()._q("""
            SELECT secteur, dept_code, taux_ouverture, taux_clic
            FROM memoire_stephane WHERE site_code = %s AND envois >= %s""",
                            (site, MIN_ENVOIS)):
            fin[(r[0], r[1])] = (r[2] or 0.0, r[3] or 0.0)
        for r in _pool()._q("""
            SELECT dept_code,
                   round(100.0 * count(opened_at)  / NULLIF(count(*), 0), 1)::float8,
                   round(100.0 * count(clicked_at) / NULLIF(count(*), 0), 1)::float8
            FROM campaign_recipients
            WHERE site_code = %s AND dept_code <> 'inconnu'
            GROUP BY dept_code HAVING count(*) >= %s""", (site, MIN_ENVOIS)):
            zone[r[0]] = (r[1] or 0.0, r[2] or 0.0)
    except Exception:  # noqa: BLE001
        pass
    return fin, zone


# ── Les trois critères réglables ──────────────────────────────────────────────
# Stéphane décide seul, mais dans un cadre que Camille pose : sur QUOI il a le droit de
# collecter (secteurs), (départements), et ce qui doit PRIMER quand il arbitre.
SCHEMA_CONFIG = """
CREATE TABLE IF NOT EXISTS config_stephane (
    site_code  text PRIMARY KEY,
    secteurs   text[] NOT NULL DEFAULT '{}',
    depts      text[] NOT NULL DEFAULT '{}',
    priorite   text   NOT NULL DEFAULT 'equilibre',
    maj_le     timestamptz NOT NULL DEFAULT now(),
    maj_par    text
);
"""

# Le troisième critère : ce qui l'emporte en cas d'égalité. Chaque choix REDISTRIBUE les
# poids — il ne les remplace pas, sinon un secteur interdit pourrait remonter.
PRIORITES = {
    "equilibre":     {"libelle": "Équilibré",
                      "aide": "les quatre critères comptent également"},
    "performance":   {"libelle": "Ce qui répond",
                      "aide": "priorité aux zones qui ouvrent et cliquent le plus"},
    "terrain_neuf":  {"libelle": "Terrain neuf",
                      "aide": "priorité à ce qui n'a jamais été collecté"},
    "volume":        {"libelle": "Volume",
                      "aide": "priorité aux départements les plus peuplés"},
}


def config(site: str = "lcr") -> dict:
    p = _pool()
    c = p._conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(SCHEMA_CONFIG)
                cur.execute("SELECT secteurs, depts, priorite, maj_le::text, maj_par "
                            "FROM config_stephane WHERE site_code = %s", (site,))
                r = cur.fetchone()
    finally:
        p._rendre(c)
    if not r:
        # Rien d'enregistré : Stéphane travaille sans restriction, en mode équilibré. On le
        # DIT (`source`), pour qu'on ne prenne jamais un défaut pour un choix.
        return {"site": site, "secteurs": [], "depts": [], "priorite": "equilibre",
                "source": "defaut", "priorites": PRIORITES}
    return {"site": site, "secteurs": list(r[0] or []), "depts": list(r[1] or []),
            "priorite": r[2], "maj_le": r[3], "maj_par": r[4],
            "source": "enregistre", "priorites": PRIORITES}


def enregistrer_config(site: str, secteurs: list, depts: list, priorite: str,
                       par: str = "") -> dict:
    if priorite not in PRIORITES:
        return {"ok": False, "error": f"priorité inconnue : {priorite}"}
    secteurs = [s.strip() for s in (secteurs or []) if s and s.strip()]
    depts = [d.strip() for d in (depts or []) if d and d.strip()]
    p = _pool()
    c = p._conn()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(SCHEMA_CONFIG)
                cur.execute("""
                    INSERT INTO config_stephane (site_code, secteurs, depts, priorite, maj_par)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (site_code) DO UPDATE SET
                        secteurs = EXCLUDED.secteurs, depts = EXCLUDED.depts,
                        priorite = EXCLUDED.priorite, maj_le = now(),
                        maj_par = EXCLUDED.maj_par
                """, (site, secteurs, depts, priorite, par or None))
    finally:
        p._rendre(c)
    return {"ok": True, "secteurs": secteurs, "depts": depts, "priorite": priorite}


def _poids(priorite: str) -> dict:
    """Les poids, redistribués selon ce qui doit primer. Le rang du secteur ne bouge
    jamais : c'est une règle, pas une préférence."""
    w = dict(POIDS)
    if priorite == "performance":
        w["performance"] = 45; w["terrain_neuf"] = 12; w["peu_possede"] = 13
    elif priorite == "terrain_neuf":
        w["terrain_neuf"] = 40; w["performance"] = 15; w["peu_possede"] = 15
    elif priorite == "volume":
        w["performance"] = 15; w["terrain_neuf"] = 15; w["peu_possede"] = 10
        w["population"] = 30
    return w


def _file(site: str) -> list[dict]:
    from duck_ouverture import ouvrir
    c = ouvrir(str(BASE_DIR / "data" / "god_mode.duckdb"))
    try:
        lignes = c.execute("""
            SELECT id, sector, dept_code, dept_name, region_name, dept_pop,
                   COALESCE(runs, 0), COALESCE(valid_total, 0), last_run_at
            FROM autoscrape_targets WHERE site_code = ? AND status = 'pending'""",
                           [site]).fetchall()
    finally:
        c.close()
    return [{"id": r[0], "secteur": r[1], "dept": r[2], "dept_nom": r[3], "region": r[4],
             "pop": r[5] or 0, "runs": r[6], "collectes": r[7],
             "dernier_run": str(r[8]) if r[8] else None} for r in lignes]


def conseiller(site: str = "lcr", combien: int = 10) -> dict:
    """La décision de Stéphane : les prochaines cibles, notées et justifiées."""
    cfg = config(site)
    w = _poids(cfg["priorite"])
    fin, zone = _perf(site)

    try:
        import secteurs_backend as sb
        pol = sb.politique(site)
        rangs = {code: rang for rang in sb.RANGS for code in (pol.get(rang) or [])}
    except Exception:  # noqa: BLE001
        rangs = {}

    # Repères de normalisation : une note se compare à la meilleure valeur observée, pas à
    # un maximum théorique que personne n'atteint jamais.
    tous = list(fin.values()) + list(zone.values())
    max_clic = max([c for _, c in tous] or [0]) or 1
    max_ouv = max([o for o, _ in tous] or [0]) or 1
    cibles = _file(site)
    max_pop = max([c["pop"] for c in cibles] or [1]) or 1

    notes = []
    for cible in cibles:
        rang = rangs.get(cible["secteur"], "non classé")
        if rang == "interdit":
            continue
        if cfg["secteurs"] and cible["secteur"] not in cfg["secteurs"]:
            continue
        if cfg["depts"] and cible["dept"] not in cfg["depts"]:
            continue

        note = 0.0
        pourquoi = []

        if rang == "prioritaire":
            note += w["rang_prioritaire"]; pourquoi.append("secteur prioritaire")
        elif rang == "secondaire":
            note += w["rang_secondaire"]; pourquoi.append("secteur secondaire")

        # Performance : le couple d'abord, la zone à défaut. Le clic pèse deux tiers de la
        # note — une ouverture peut venir d'un proxy antispam, un clic est un geste.
        mesure = fin.get((cible["secteur"], cible["dept"]))
        precis = mesure is not None
        if mesure is None:
            mesure = zone.get(cible["dept"])
        if mesure:
            ouv, clic = mesure
            note += w["performance"] * (0.67 * (clic / max_clic) + 0.33 * (ouv / max_ouv))
            pourquoi.append(
                f"{'ce secteur y' if precis else 'cette zone'} fait {clic} % de clic "
                f"et {ouv} % d'ouverture")
        else:
            pourquoi.append("jamais sollicité par email")

        if cible["runs"] == 0:
            note += w["terrain_neuf"]; pourquoi.append("jamais collecté")
        else:
            pourquoi.append(f"déjà {cible['collectes']} contacts en {cible['runs']} passage(s)")

        deja = 0
        try:
            deja = _pool()._q("SELECT contacts_base FROM memoire_stephane WHERE site_code=%s "
                              "AND secteur=%s AND dept_code=%s",
                              (site, cible["secteur"], cible["dept"]))[0][0]
        except Exception:  # noqa: BLE001
            pass
        note += w["peu_possede"] * max(0.0, 1 - min(deja, 500) / 500)
        pourquoi.append(f"{deja} contacts en base" if deja else "aucun contact en base")

        if "population" in w:
            note += w["population"] * (cible["pop"] / max_pop)

        notes.append({**cible, "rang": rang, "note": round(note, 1),
                      "mesure_precise": precis, "pourquoi": " · ".join(pourquoi)})

    notes.sort(key=lambda x: (-x["note"], -x["pop"]))
    return {
        "agent": NOM, "site": site, "candidats": len(notes),
        "priorite": cfg["priorite"], "priorite_libelle": PRIORITES[cfg["priorite"]]["libelle"],
        "cadre": {"secteurs": cfg["secteurs"], "depts": cfg["depts"], "source": cfg["source"]},
        "couples_en_memoire": len(fin),
        "conseil": notes[:max(1, combien)],
        "methode": (f"Note sur 100, priorité « {PRIORITES[cfg['priorite']]['libelle']} » : "
                    f"rang du secteur ({w['rang_prioritaire']}) + performance mesurée "
                    f"({w['performance']}, dont deux tiers sur le clic) + terrain neuf "
                    f"({w['terrain_neuf']}) + rareté en base ({w['peu_possede']})"
                    + (f" + population ({w['population']})" if "population" in w else "")
                    + ". Les secteurs interdits sont écartés, pas notés."),
    }


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(description=f"{NOM} — l'agent de collecte")
    ap.add_argument("commande", choices=["conseil", "memoire", "observer", "config"],
                    nargs="?", default="conseil")
    ap.add_argument("--site", default="lcr")
    ap.add_argument("--combien", type=int, default=10)
    a = ap.parse_args()
    f = {"conseil": lambda: conseiller(a.site, a.combien),
         "memoire": lambda: memoire(a.site, a.combien),
         "observer": lambda: observer(a.site),
         "config": lambda: config(a.site)}[a.commande]
    print(json.dumps(f(), ensure_ascii=False, indent=2, default=str))
