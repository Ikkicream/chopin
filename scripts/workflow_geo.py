#!/usr/bin/env python3
"""
workflow_geo.py — Sélection territoire région→département→villes pour le module Workflow.

Source de données : `data/geo/{regions,departments,cities-fr}.json`
- 18 régions (13 métropole + 5 DOM)
- 101 départements
- 1067 communes ≥ 10 000 habitants (recensement INSEE 2024)

Aucune dépendance réseau au runtime.
"""

import json
import random
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
GEO_DIR = BASE_DIR / "data" / "geo"


@lru_cache(maxsize=1)
def _regions() -> list[dict]:
    return json.loads((GEO_DIR / "regions.json").read_text())


@lru_cache(maxsize=1)
def _departments() -> list[dict]:
    return json.loads((GEO_DIR / "departments.json").read_text())


@lru_cache(maxsize=1)
def _cities() -> list[dict]:
    return json.loads((GEO_DIR / "cities-fr.json").read_text())


def list_regions() -> list[dict]:
    return _regions()


def list_departments(region_code: str | None = None) -> list[dict]:
    deps = _departments()
    if region_code:
        deps = [d for d in deps if d["region_code"] == region_code]
    return deps


import re as _re

# Suffixe d'arrondissement ajouté par le scrapper (« Paris 13e », « Lyon 3e »,
# « Marseille 8e », « Paris 1er », « … 2ème »). On le retire pour retomber sur la
# commune-mère indexée (« paris », « lyon », « marseille »).
_ARRDT_RE = _re.compile(r"\s+\d{1,2}\s*(?:er|e|ere|eme|ème)$", _re.IGNORECASE)


def _norm_city(name: str) -> str:
    s = (name or "").strip().lower()
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"), ("à", "a"), ("â", "a"),
                 ("î", "i"), ("ï", "i"), ("ô", "o"), ("û", "u"), ("ü", "u"), ("ç", "c"),
                 ("œ", "oe"), ("-", " "), ("'", " "), ("’", " ")):
        s = s.replace(a, b)
    s = " ".join(s.split())
    s = _ARRDT_RE.sub("", s).strip()  # « paris 13e » -> « paris »
    return s


@lru_cache(maxsize=1)
def _city_geo_index() -> dict:
    """Nom de ville normalisé → {dept, region}. Les grandes villes écrasent les petites
    homonymes (on trie par population croissante avant d'indexer)."""
    idx = {}
    for c in sorted(_cities(), key=lambda x: x.get("pop") or 0):
        idx[_norm_city(c["name"])] = {"dept": c["dept"], "region": c["region"]}
    return idx


@lru_cache(maxsize=1)
def _dept_region_index() -> dict:
    return {d["code"]: d["region_code"] for d in _departments()}


def region_of_dept(dept_code: str | None) -> str | None:
    return _dept_region_index().get(dept_code or "")


def resolve_city_geo(city: str | None, postal_code: str | None = None) -> dict:
    """Résout (dept_code, region_code) depuis un code postal (prioritaire) ou un nom de
    ville (communes ≥10k hab). Renvoie {"dept": ..., "region": ...} avec None si inconnu."""
    dept = None
    cp = (postal_code or "").strip()
    if len(cp) == 5 and cp.isdigit():
        d2 = cp[:2]
        if d2 == "20":  # Corse : hors périmètre, on ne devine pas 2A/2B
            d2 = None
        elif d2 in ("97", "98"):
            d2 = cp[:3]
        if d2 and d2 in _dept_region_index():
            dept = d2
    if not dept and city:
        hit = _city_geo_index().get(_norm_city(city))
        if hit:
            return {"dept": hit["dept"], "region": hit["region"]}
    return {"dept": dept, "region": region_of_dept(dept)}


def list_cities(dept_code: str | None = None, region_code: str | None = None,
                min_pop: int = 10000) -> list[dict]:
    """Villes filtrées par dept/region et population min."""
    cities = _cities()
    if dept_code:
        cities = [c for c in cities if c["dept"] == dept_code]
    elif region_code:
        cities = [c for c in cities if c["region"] == region_code]
    if min_pop:
        cities = [c for c in cities if (c.get("pop") or 0) >= min_pop]
    return sorted(cities, key=lambda c: (c.get("cp") or ["99999"])[0])


# Périmètre de scraping = France métropolitaine UNIQUEMENT. On exclut la Corse et les
# DOM-TOM (demande user 2026-06-16 : LeClientROI cible les commerçants de métropole).
EXCLUDED_REGION_CODES = {"94", "01", "02", "03", "04", "06"}   # Corse + 5 DOM
EXCLUDED_DEPT_CODES = {"2A", "2B", "971", "972", "973", "974", "975", "976", "977", "978"}


def metropole_regions() -> list[dict]:
    """Régions hors Corse et DOM-TOM (pour le scrapper)."""
    return [r for r in _regions() if r.get("code") not in EXCLUDED_REGION_CODES]


def metropole_departments(region_code: str | None = None) -> list[dict]:
    """Départements hors Corse et DOM-TOM (pour le scrapper)."""
    return [d for d in list_departments(region_code)
            if d.get("code") not in EXCLUDED_DEPT_CODES
            and d.get("region_code") not in EXCLUDED_REGION_CODES]


def metropole_cities(dept_code: str | None = None, region_code: str | None = None,
                     min_pop: int = 10000) -> list[dict]:
    """Villes hors Corse et DOM-TOM (pour le scrapper)."""
    return [c for c in list_cities(dept_code, region_code, min_pop=min_pop)
            if c.get("dept") not in EXCLUDED_DEPT_CODES
            and c.get("region") not in EXCLUDED_REGION_CODES]


def count_eligible(dept_codes: list[str] | None = None, region_codes: list[str] | None = None,
                   min_pop: int = 10000) -> int:
    """Compte de villes éligibles selon le périmètre (pour preview UI)."""
    cities = _cities()
    if dept_codes:
        cities = [c for c in cities if c["dept"] in dept_codes]
    elif region_codes:
        cities = [c for c in cities if c["region"] in region_codes]
    return sum(1 for c in cities if (c.get("pop") or 0) >= min_pop)


def pick_random_dept_weighted_pop(rng: random.Random | None = None,
                                  excluded: list[str] | None = None) -> dict:
    """Tire un département aléatoire pondéré par la somme des populations de ses villes ≥10k.
    Permet de prospecter davantage là où il y a plus de TPE/PME potentielles.
    """
    rng = rng or random.Random()
    excluded = set(excluded or [])

    pop_by_dept: dict[str, int] = {}
    for c in _cities():
        if (c.get("pop") or 0) < 10000:
            continue
        if c["dept"] in excluded:
            continue
        pop_by_dept[c["dept"]] = pop_by_dept.get(c["dept"], 0) + c["pop"]

    if not pop_by_dept:
        raise RuntimeError("Aucun département éligible après exclusions")

    depts = list(pop_by_dept.keys())
    weights = [pop_by_dept[d] for d in depts]
    chosen_code = rng.choices(depts, weights=weights, k=1)[0]
    return next(d for d in _departments() if d["code"] == chosen_code)


def resolve_dept_to_cities(dept_code: str, top_n: int = 5,
                           rng: random.Random | None = None) -> list[dict]:
    """Renvoie les `top_n` plus grandes villes d'un département (par population).
    Si top_n > nb_villes dispo, renvoie tout.
    """
    cities = list_cities(dept_code=dept_code, min_pop=10000)
    return cities[:top_n]


def city_label(city: dict) -> str:
    """Label affichable d'une ville pour log/UI : 'Marseille (13, 870 731 hab)'."""
    pop = city.get("pop") or 0
    return f"{city['name']} ({city.get('dept', '?')}, {pop:,} hab)".replace(",", " ")


if __name__ == "__main__":
    import sys
    print(f"Régions:    {len(list_regions())}")
    print(f"Départ.:    {len(list_departments())}")
    print(f"Villes 10k: {len(list_cities())}")
    print()
    if len(sys.argv) > 1 and sys.argv[1] == "pick":
        d = pick_random_dept_weighted_pop()
        print(f"Dept tiré: {d['name']} ({d['code']})")
        for c in resolve_dept_to_cities(d['code'], top_n=8):
            print(f"  - {city_label(c)}")
    else:
        # Demo : Paris
        print("Villes du 75:")
        for c in list_cities(dept_code="75"):
            print(f"  - {city_label(c)}")
        print()
        print("Île-de-France (région 11):")
        for c in list_cities(region_code="11")[:10]:
            print(f"  - {city_label(c)}")

# Liste de priorité user (2026-05-22) : départements à scraper en premier.
# Après ceux-ci, on cycle sur tous les autres départements éligibles
# (>= 10k hab en ville) classés par population totale décroissante.
PRIORITY_DEPTS = ["92", "75", "59", "69"]


def _ordered_depts() -> list[str]:
    """Construit la liste ordonnée : PRIORITY_DEPTS d'abord, puis le reste par pop décroissante.
    Filtre les depts qui ne sont pas définis dans departments.json (sécurité DOM-TOM)."""
    valid_dept_codes = {d["code"] for d in _departments()}

    pop_by_dept: dict[str, int] = {}
    for c in _cities():
        if (c.get("pop") or 0) < 10000:
            continue
        if c["dept"] not in valid_dept_codes:
            continue
        pop_by_dept[c["dept"]] = pop_by_dept.get(c["dept"], 0) + c["pop"]

    others = [d for d in pop_by_dept if d not in PRIORITY_DEPTS]
    others.sort(key=lambda d: -pop_by_dept[d])

    priority_present = [d for d in PRIORITY_DEPTS if d in pop_by_dept]
    return priority_present + others


# Date de calibrage : ce jour-là, le scrape part du dept 92 (position 0 de l'ordre).
# Choisi 2026-05-22 (jour où la priorité user a été décidée).
ROTATION_EPOCH = "2026-05-22"


def next_dept_by_priority(pivot_date=None) -> dict:
    """Retourne le département à scraper selon la priorité user (2026-05-22) :
    ordre = [92, 75, 59, 69, puis tous les autres par pop décroissante].
    Calibrage : pivot_date = 2026-05-22 → dept 92. Avance jour par jour ensuite.
    """
    from datetime import date as _date
    pivot = pivot_date or _date.today()
    epoch = _date.fromisoformat(ROTATION_EPOCH)
    ordered = _ordered_depts()
    if not ordered:
        raise RuntimeError("Aucun département éligible")
    days_since_epoch = (pivot - epoch).days
    idx = days_since_epoch % len(ordered)
    chosen_code = ordered[idx]
    return next(d for d in _departments() if d["code"] == chosen_code)

