#!/usr/bin/env python3
"""
workflow_qualifier.py — Agent DeepSeek qui décide si un prospect est un "potentiel acheteur".

S'exécute après le scrape Serper et avant le push Emelia.
Filtre les franchises nationales, administrations, sites indispos, secteurs non pertinents.

Coût attendu : ~150 in + 30 out tokens par prospect ≈ 0.00006 €/appel.
Pour 100 prospects/jour LCR+MKD = 0.006 €/jour, négligeable.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm_call import call_llm_json


SITE_PITCH = {
    "lcr": (
        "LeClientROI vend du SMS marketing, RCS, géolocalisation pour TPE/PME. "
        "Cible : commerce de proximité avec besoin de fidéliser ou promouvoir localement."
    ),
    "mkd": (
        "MKDgroupe vend de la location de bases de données B2B et du routage SMS aux entreprises. "
        "Cible : sociétés qui font de la prospection B2B, marketing direct, ou ont besoin de fichiers RGPD."
    ),
}


SYSTEM_PROMPT = """Tu es un commercial expérimenté en B2B France.
Tu reçois UN prospect TPE/PME et tu décides s'il est un POTENTIEL ACHETEUR de la solution proposée.

Critères de qualification (buyer = true) :
- TPE/PME indépendante locale ou régionale
- Présence Google Places confirmée (site web actif, fiche pro complète)
- Secteur cohérent avec un besoin marketing direct / fidélisation
- Taille raisonnable : ni micro (1 personne sans budget), ni énorme groupe

Critères de rejet (buyer = false) :
- Franchise nationale ou chaîne (McDo, Carrefour, Sephora, Quick…) → siège décide, pas la franchise
- Administration / collectif / association à but non lucratif
- Site web indisponible ou de qualité très médiocre
- Secteur non pertinent (ex : notaire isolé sans démarche commerciale)
- Email générique douteux (info@gmail.com, contact@hotmail.com)

Réponds en JSON STRICT, sans markdown, sans fence, sans préambule :
{"buyer": true|false, "reason": "raison courte max 100 chars en français"}"""


def qualify_prospect(prospect: dict, site: str = "lcr") -> dict:
    """Décide si un prospect est un potentiel acheteur via DeepSeek.

    Args:
        prospect: dict avec au minimum company_name, sector, city, email, website
        site: "lcr" ou "mkd" (détermine le pitch utilisé)

    Returns:
        {"buyer": bool, "reason": str}
        En cas d'erreur LLM, renvoie {"buyer": False, "reason": "qualification_error"}.
    """
    pitch = SITE_PITCH.get(site, SITE_PITCH["lcr"])
    facts = {
        "company": prospect.get("company_name") or "",
        "sector": prospect.get("sector") or "",
        "city": prospect.get("city") or "",
        "dept": prospect.get("dept_code") or "",
        "email": prospect.get("email") or "",
        "phone": prospect.get("phone") or "",
        "website": prospect.get("website") or "",
        "rating": (prospect.get("raw_data") or {}).get("rating"),
    }
    user_msg = (
        f"OFFRE : {pitch}\n\n"
        f"PROSPECT :\n{json.dumps(facts, ensure_ascii=False, indent=2)}\n\n"
        f"Décide buyer true/false avec une raison."
    )
    try:
        verdict = call_llm_json(
            user_msg,
            system=SYSTEM_PROMPT,
            max_tokens=120,
            temperature=0.2,
            module="workflow",
            action="qualify",
            site=site,
            note=f"sector={facts['sector']} city={facts['city']}",
        )
        buyer = bool(verdict.get("buyer", False))
        reason = str(verdict.get("reason", "")).strip()[:200]
        return {"buyer": buyer, "reason": reason}
    except Exception as e:
        return {"buyer": False, "reason": f"qualification_error: {type(e).__name__}"}


if __name__ == "__main__":
    # Test
    p = {
        "company_name": "Boulangerie Martin",
        "sector": "retail",
        "city": "Lille",
        "dept_code": "59",
        "email": "contact@boulangerie-martin.fr",
        "phone": "0320123456",
        "website": "https://boulangerie-martin.fr",
        "raw_data": {"rating": 4.6},
    }
    print("Prospect:", p["company_name"])
    print("Verdict:", qualify_prospect(p, site="lcr"))
