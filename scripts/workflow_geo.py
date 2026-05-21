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
    return sorted(cities, key=lambda c: -(c.get("pop") or 0))


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
