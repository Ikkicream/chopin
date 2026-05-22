#!/usr/bin/env python3
"""
seo_strategy_agent.py — SEO STRATEGIST

Analyse les caches Ahrefs (memory/seo/*-audit-latest.json) et génère des
recommandations SEO actionnables avec explications pédagogiques.

DOC DE RÉFÉRENCE : specs/seo-playbook.md

Responsabilités (mises à jour 2026-05-22) :
  1. Lire les audits mensuels (memory/seo/{site}-audit-latest.json)
  2. Générer des recommandations actionnables via DeepSeek
  3. SURVEILLER LE BUDGET AHREFS et émettre une reco quand dépassement
  4. Notifier Telegram si recos critiques

Cron : lundi 7h UTC
Usage : python3 scripts/seo_strategy_agent.py [--site lcr|mkd|both]
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent.parent
SEO_DIR = BASE_DIR / "memory" / "seo"
RECO_FILE = BASE_DIR / "memory" / "seo" / "recommendations.json"

# Load env
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip("'\""))

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

SITE_CONTEXT = {
    "lcr": {
        "label": "LeClientROI",
        "domain": "leclientroi.com",
        "niche": "SMS marketing, RCS, géolocalisation, communication locale TPE/PME",
        "goal": "Être #1 France sur 'sms marketing', 'campagne sms', 'sms geolocalise'. Objectif 10k visites/mois en 6 mois.",
    },
    "mkd": {
        "label": "MKDgroupe",
        "domain": "mkdgroupe.com",
        "niche": "Prospection B2B, data marketing, RGPD, RCS entreprise",
        "goal": "Ranker sur 'prospection b2b', 'base de données b2b'. Objectif 5k visites/mois en 6 mois.",
    },
}


def load_recommendations():
    if RECO_FILE.exists():
        return json.loads(RECO_FILE.read_text())
    return {"lcr": [], "mkd": []}


def save_recommendations(data):
    RECO_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_ahrefs(site):
    f = SEO_DIR / f"{site}-ahrefs-latest.json"
    if f.exists():
        return json.loads(f.read_text())
    return {}


SEED_COMPETITORS_FR = {
    "lcr": [
        # Routage SMS pro
        "smsmode.com", "octopush.com", "esendex.fr", "primotexto.com",
        "allmysms.com", "smsfactor.com", "dexem.com", "smspartner.fr",
        "lemobilemarketing.com", "spothit.fr", "wellpack.fr",
        # Location données B2B/B2C
        "manageo.com", "sosdata.fr", "ecodata-france.com",
        "dekuple.com", "agence.dekuple.com",
    ],
    "mkd": [
        # Concurrents directs marché FR de la data B2B / prospection
        "kompass.com", "societe.com", "manageo.com", "easybusiness.com",
        "corporama.com", "infonet.fr", "dataimporter.fr", "lusha.com",
        "datananas.com", "explore-france.fr",
    ],
}

LEVIERS_BACKLINK_FR = {
    "annuaires_pro": [
        "Solutions Numériques (le-mag-itrnews)", "Companeo", "Hellopro",
        "Annuaire BPI France", "France Num (le portail public TPE/PME)",
        "Place du marché (les Echos)", "FrenchTech directory",
    ],
    "presse_specialisee": [
        "L'Argus de la presse Pro (Marketing-pro.fr)", "FrenchWeb",
        "Maddyness", "Frenchweb.fr / e-marketing.fr", "Stratégies (marketing pro)",
        "Action Co (Editialis)", "JDN (Le Journal du Net section marketing)",
    ],
    "partenariats_institutionnels": [
        "CCI locale (Chambre de Commerce et d'Industrie)",
        "CMA (Chambre de Métiers et de l'Artisanat)",
        "BPI France — guides & témoignages clients",
        "Réseau Entreprendre / Initiative France",
        "Cluster numérique régional (ex: Cap Digital, French Tech)",
    ],
    "guest_blogging": [
        "blog.payfit.com (payeur de salaires PME)", "blog.cegid.com",
        "blog.shopify.fr (e-commerce FR)", "blog.welcometothejungle.com",
        "blog.partoo.co (visibilité locale)", "blog.mailjet.com",
    ],
    "podcast_sponsoring": [
        "Génération Do It Yourself (Matthieu Stefani)",
        "Marketing Square (Joachim du Bois)",
        "Le Café Cremedelacreme (entrepreneurs)",
        "Marketing Mania (Stan Leloup) — pour les épisodes growth",
    ],
}


def generate_recommendations(site, ahrefs_data):
    """Génère des recos SEO ACTIONNABLES marché FR, basées sur les vrais concurrents."""
    ctx = SITE_CONTEXT[site]
    keywords = ahrefs_data.get("top_keywords", [])
    competitors = ahrefs_data.get("competitors", [])
    dr = ahrefs_data.get("domain_rating", 0)
    traffic = ahrefs_data.get("org_traffic", 0)
    total_kw = ahrefs_data.get("org_keywords", 0)

    seed = SEED_COMPETITORS_FR.get(site, [])
    leviers = LEVIERS_BACKLINK_FR

    prompt = f"""Tu es un consultant SEO sénior spécialisé MARCHÉ FRANÇAIS (FR uniquement, jamais .com US/UK).
Tu analyses {ctx['label']} ({ctx['domain']}) — niche : {ctx['niche']}.
Objectif : {ctx['goal']}

ÉTAT ACTUEL DU SITE (Ahrefs) :
- Domain Rating : {dr}/100
- Trafic organique : {traffic} visites/mois
- Keywords positionnés : {total_kw}

TOP KEYWORDS RANKÉS :
{json.dumps(keywords[:10], ensure_ascii=False, indent=2)}

CONCURRENTS DÉTECTÉS PAR AHREFS (déjà filtrés pour exclure facebook/reddit/wikipédia) :
{json.dumps(competitors, ensure_ascii=False, indent=2)}

CONCURRENTS RÉELS DU MARCHÉ FR (référence sectorielle, à ANALYSER en priorité) :
{json.dumps(seed, ensure_ascii=False)}

LEVIERS BACKLINKS MARCHÉ FR DISPONIBLES (utilise ces noms concrets, pas des génériques) :
{json.dumps(leviers, ensure_ascii=False, indent=2)}

RÈGLES STRICTES (sinon réponse rejetée) :
1. ZÉRO conseil générique type "faire des backlinks de qualité" ou "publier du contenu".
2. Chaque reco DOIT citer un nom de site/média/annuaire FR PRÉCIS pris dans la liste leviers ci-dessus OU un concurrent FR de la seed.
3. Chaque reco DOIT donner un chiffre (volume kw, DR cible, nombre de backlinks, mois d'investissement).
4. Pour le keyword research, propose 3 keywords longue traîne FR spécifiques au secteur (pas "sms marketing" mais "logiciel sms client fidélisation restaurant").
5. Mentionne le contexte concurrentiel FR concret (ex: "smsmode.com a DR 67 et 25K visites/mois, ils backlinks via leur blog + JDN").

GÉNÈRE EXACTEMENT 5 RECOMMANDATIONS, JSON pur (pas de markdown wrapper) :
[
  {{
    "type": "content|backlink|technique|keyword|competitor",
    "title": "Action courte (max 80 chars)",
    "why": "Pourquoi MAINTENANT — cite un concurrent FR de la seed + son DR/trafic + ce qu'il fait que vous ne faites pas",
    "how": "Étapes concrètes : nommer 1 à 3 sites FR précis de la liste leviers, donner emails de contact si possible, donner un budget/temps réaliste",
    "priority": "haute|moyenne|basse",
    "impact": "Estimation chiffrée FR : ex '+30 visites/mois sur \"campagne sms boulangerie\" (vol 90/mois FR) en 4 mois' ou '+5 DR en 6 mois avec 8 backlinks DR40+'",
    "keyword": "mot-clé FR longue traîne SI applicable, sinon vide"
  }}
]"""

    from llm_call import call_llm_json
    try:
        from modules_backend import enrich_prompt
        prompt = enrich_prompt(prompt, site, "seo_strategy")
    except Exception:
        pass
    return call_llm_json(prompt, max_tokens=4000, module="seo-strategy", action="recommendations", site=site)


def notify_telegram(site, recos):
    """Send summary to Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    label = SITE_CONTEXT[site]["label"]
    summary = "\n".join([f"• {r['title']} ({r['priority']})" for r in recos[:5]])
    msg = (
        f"\U0001f4ca *Analyse SEO — {label}*\n\n"
        f"{summary}\n\n"
        f"_Voir détails sur le dashboard #seo-strategy_"
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        print(f"  Telegram: {e}")


def process_site(site):
    """Generate SEO recommendations for a site."""
    print(f"[seo-strategy] {site.upper()} — analyzing...")

    ahrefs = load_ahrefs(site)
    if not ahrefs:
        print(f"  No Ahrefs data for {site}")
        return

    try:
        recos = generate_recommendations(site, ahrefs)
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    print(f"  Generated {len(recos)} recommendations")
    for r in recos:
        print(f"    [{r['priority']}] {r['title']}")

    # Save recommendations
    all_recos = load_recommendations()
    now = datetime.now(timezone.utc).isoformat()

    # Add metadata to each reco
    for r in recos:
        r["id"] = f"reco_{site}_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{recos.index(r)+1:02d}"
        r["site"] = site
        r["status"] = "pending"  # pending | validated | done | ignored
        r["created_at"] = now

    # Replace old recommendations for this site (keep validated/done ones)
    existing = [r for r in all_recos.get(site, []) if r.get("status") in ("validated", "done")]
    all_recos[site] = existing + recos
    save_recommendations(all_recos)

    # Telegram
    notify_telegram(site, recos)
    print(f"  Saved + notified")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["lcr", "mkd", "both"], default="both")
    args = parser.parse_args()

    print(f"[seo_strategy_agent] {datetime.now(timezone.utc).isoformat()}")

    # === Surveillance budget Ahrefs (ajouté 2026-05-22) ===
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from cost_tracker import check_ahrefs_budget
        ok, info = check_ahrefs_budget(cost_estimate=0, critical=False)
        used, total, pct = info.get("used", 0), info.get("total", 10000), info.get("pct", 0)
        if pct >= 70:
            print(f"[BUDGET-ALERT] Ahrefs à {pct}% ({used}/{total}) — reset {info.get("reset_at", "")[:10]}")
            # Émet une reco prioritaire pour les 2 sites
            recos = load_recommendations()
            alert = {
                "id":         f"budget-alert-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                "priority":   "critical",
                "type":       "budget",
                "title":      f"Budget Ahrefs à {pct}%",
                "action":     f"Conso {used}/{total} unités. Reset {info.get('reset_at', '')[:10]}. Voir specs/seo-playbook.md.",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            for s in ["lcr", "mkd"]:
                recos.setdefault(s, [])
                if not any(r.get("id") == alert["id"] for r in recos[s]):
                    recos[s].insert(0, alert)
            save_recommendations(recos)
            try:
                notify_telegram("system", [alert])
            except Exception:
                pass
    except Exception as e:
        print(f"[BUDGET-MONITOR] skip: {e}")

    try:
        from modules_backend import is_enabled
    except Exception:
        is_enabled = lambda *_: True

    sites = ["lcr", "mkd"] if args.site == "both" else [args.site]
    for site in sites:
        if not is_enabled(site, "seo_strategy"):
            print(f"[seo_strategy] {site}: module désactivé → skip")
            continue
        process_site(site)
    print("[seo_strategy_agent] Done!")


if __name__ == "__main__":
    main()
