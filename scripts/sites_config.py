#!/usr/bin/env python3
"""
sites_config.py — Source unique de vérité pour la configuration multi-sites Genesis.

Fournit une API Python compatible avec les SITES dicts per-script existants.
Les scripts l'importent via try/except pour rester backwards-compatibles.
"""

from pathlib import Path
import json, copy
from datetime import datetime, timezone

BASE_DIR   = Path(__file__).parent.parent
CONFIG_FILE = BASE_DIR / "memory" / "sites-config.json"

# ── Fallback hardcodé (utilisé si le fichier JSON est absent) ─────────────────

_LEGACY = {
    "lcr": {
        "_meta": {"created_at": "2025-01-01T00:00:00Z", "status": "active"},
        "core": {
            "code": "lcr", "label": "LeClientROI", "domain": "leclientroi.com",
            "url": "https://leclientroi.com", "country": "fr", "language": "fr",
            "primary_color": "#0066FF",
        },
        "seo": {"keywords": ["sms marketing", "campagne sms", "sms geolocalise",
                              "rcs messagerie", "location donnees geolocalisees"]},
        "content": {
            "cms": "emdash",
            "blog_url": "https://leclientroi.com/blog/",
            "tone": "expert SME friendly, exemples concrets, chiffres, actionnable",
            "cta": "Découvrez la solution SMS de LeClientROI",
        },
        "seo_agent": {
            "rss_sources": [
                {"name": "Spot-Hit Blog",      "url": "https://www.spot-hit.fr/blog/feed/"},
                {"name": "SMS Mode Blog",      "url": "https://www.smsmode.com/blog/feed/"},
                {"name": "SMS Partner Blog",   "url": "https://www.smspartner.fr/blog/feed/"},
                {"name": "Sarbacane Blog",     "url": "https://www.sarbacane.com/blog/feed/"},
                {"name": "Digitaleo Blog",     "url": "https://www.digitaleo.com/blog/feed/"},
                {"name": "Blog du Modérateur", "url": "https://www.blogdumoderateur.com/feed/"},
                {"name": "Journal du Net",     "url": "https://www.journaldunet.com/rss/rss_jdn.xml"},
                {"name": "Codeur Blog",        "url": "https://www.codeur.com/blog/feed/"},
            ],
            "is_directory_target": True,
        },
        "newsletter": {
            "from_name": "LeClientROI", "from_email": "newsletter@leclientroi.com",
            "subject_tpl": "SMS Marketing — Les actus du mois {month}",
            "accent": "#0066FF", "audience_id": "",
            "topics": ["sms marketing", "campagne sms", "rcs messagerie", "marketing local"],
            "cta_url": "https://leclientroi.com", "cta_label": "Découvrir nos solutions SMS",
            "footer_desc": "La newsletter des experts en SMS marketing et communication locale.",
            "emdash_token_env": "EMDASH_API_TOKEN",
        },
        "indexation": {
            "sitemap_url": "https://leclientroi.com/sitemap.xml",
            "blog_prefix": "https://leclientroi.com/blog/",
            "indexnow_key": "genesis-lcr-indexnow-2026",
        },
        "api": {"site_modules": ["content", "briefing", "infographic"]},
        "cms_credentials": {"emdash_token_env": "EMDASH_API_TOKEN", "emdash_url_env": "EMDASH_API_URL"},
        "rag_context": {
            "business_description": (
                "LeClientROI est une plateforme SaaS de SMS marketing et communication locale "
                "pour les PME et commerces de proximité français. Elle permet d'envoyer des campagnes "
                "SMS en masse, des SMS géolocalisés pour cibler les clients proches, et des messages RCS "
                "enrichis (images, boutons, carrousels)."
            ),
            "primary_audience": "B2C et PME — responsables marketing, gérants de points de vente locaux, "
                                 "coiffeurs, restaurateurs, garagistes, professionnels de santé",
            "industry": "SaaS / Marketing digital / SMS / Communication locale",
            "value_proposition": "Solution SMS géolocalisé la plus accessible du marché français, "
                                  "avec ciblage par rayon géographique et tableau de bord analytique",
            "competitors": ["spot-hit.fr", "smsmode.com", "smspartner.fr", "sarbacane.com",
                            "digitaleo.com", "campagne-sms.org"],
            "tone_of_voice": "expert, friendly, concret, chiffres clés, exemples sectoriels, actionnable",
            "seo_goals": "Ranker #1 sur 'sms marketing', 'campagne sms', 'sms geolocalise'. "
                         "DR cible 15 fin 2026. 10 000 visites organiques/mois.",
            "products_services": ["envoi SMS en masse", "SMS géolocalisé", "campagnes RCS",
                                   "tableau de bord analytics", "API SMS", "intégrations CRM"],
        },
    },
    "mkd": {
        "_meta": {"created_at": "2025-01-01T00:00:00Z", "status": "active"},
        "core": {
            "code": "mkd", "label": "MKD Groupe", "domain": "mkdgroupe.com",
            "url": "https://mkdgroupe.com", "country": "fr", "language": "fr",
            "primary_color": "#00C48C",
        },
        "seo": {"keywords": ["prospection commerciale b2b", "rgpd marketing",
                              "data marketing b2b", "rcs entreprise", "base de donnees b2b"]},
        "content": {
            "cms": "wordpress",
            "blog_url": "https://mkdgroupe.com/",
            "tone": "expert B2B, précis, cas d'usage enterprise, données chiffrées",
            "cta": "Contactez MKD Groupe pour votre stratégie data",
        },
        "seo_agent": {
            "rss_sources": [
                {"name": "Cartegie Blog",    "url": "https://www.cartegie.com/blog/feed/"},
                {"name": "ECommerce Mag",    "url": "https://www.ecommercemag.fr/rss/"},
                {"name": "Relation Client",  "url": "https://www.relationclient-mag.fr/rss/"},
                {"name": "Blog du Modérateur","url": "https://www.blogdumoderateur.com/feed/"},
            ],
            "is_directory_target": False,
        },
        "newsletter": {
            "from_name": "MKD Groupe", "from_email": "newsletter@mkdgroupe.com",
            "subject_tpl": "Data B2B & RGPD — Veille du mois {month}",
            "accent": "#00C48C", "audience_id": "",
            "topics": ["rgpd", "data marketing", "prospection b2b", "rcs entreprise"],
            "cta_url": "https://mkdgroupe.com", "cta_label": "Voir nos solutions B2B",
            "footer_desc": "La newsletter des décideurs data marketing B2B & conformité RGPD.",
            "wp_site_env": "WP_SITE_URL",
        },
        "indexation": {
            "sitemap_url": "https://www.mkdgroupe.com/sitemap_index.xml",
            "blog_prefix": "https://mkdgroupe.com/",
            "indexnow_key": "genesis-mkd-indexnow-2026",
        },
        "api": {"site_modules": ["content", "crm_sync", "campaigns"]},
        "cms_credentials": {
            "wp_url_env": "WP_SITE_URL", "wp_user_env": "WP_USERNAME", "wp_pass_env": "WP_APP_PASSWORD",
        },
        "rag_context": {
            "business_description": (
                "MKD Groupe est une agence spécialisée en data marketing B2B, RGPD, et communication "
                "RCS pour les entreprises françaises. Elle propose des bases de données prospects qualifiées, "
                "des services d'enrichissement data, et des campagnes multicanal (SMS, RCS, email) pour "
                "les équipes commerciales et marketing des PME et ETI."
            ),
            "primary_audience": "B2B — directeurs marketing, responsables data, DSI de PME/ETI françaises",
            "industry": "Data marketing B2B / RGPD / Prospection commerciale",
            "value_proposition": "Données B2B qualifiées et conformes RGPD avec activation multicanal intégrée",
            "competitors": ["cartegie.com", "kompass.com", "decidento.com", "corporama.com"],
            "tone_of_voice": "expert, précis, cas d'usage enterprise, données chiffrées, professionnel",
            "seo_goals": "Ranker sur 'prospection commerciale b2b', 'base de données b2b'. "
                         "DR cible 25 fin 2026. 5 000 visites organiques/mois.",
            "products_services": ["bases de données B2B", "enrichissement data", "campagnes RCS",
                                   "scoring prospects", "RGPD compliance", "API data"],
        },
    },
}


# ── I/O ───────────────────────────────────────────────────────────────────────

def _load_raw() -> dict:
    """Charge le fichier JSON. Retourne le fallback legacy si absent."""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {"version": 2, "sites": copy.deepcopy(_LEGACY)}


def _save_raw(data: dict) -> None:
    """Sauvegarde atomique du fichier JSON."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(CONFIG_FILE)


# ── API publique ──────────────────────────────────────────────────────────────

def load_all_sites() -> dict:
    """Retourne le dict complet des sites {code: config}."""
    return _load_raw().get("sites", {})


def get_site(code: str) -> dict | None:
    """Config complète d'un site ou None si inconnu."""
    return load_all_sites().get(code)


def list_active_sites() -> list[str]:
    """Codes des sites avec status == 'active'."""
    return [
        code for code, data in load_all_sites().items()
        if data.get("_meta", {}).get("status") == "active"
    ]


def get_site_context(code: str) -> str:
    """Retourne le chunk RAG (memory/{code}/site-context.md) ou '' si absent."""
    path = BASE_DIR / "memory" / code / "site-context.md"
    if path.exists():
        return path.read_text()
    # Fallback: génère depuis rag_context dict
    site = get_site(code)
    if not site:
        return ""
    return _render_site_context(code, site)


def get_sites_for_script(script: str) -> dict:
    """
    Retourne un dict {code: flat_config} compatible avec le pattern SITES de chaque script.

    script: "seo" | "content" | "newsletter" | "indexation" | "seo_agent" | "api"

    Seuls les sites avec status="active" sont inclus.
    """
    sites = load_all_sites()
    result = {}
    for code, data in sites.items():
        if data.get("_meta", {}).get("status") != "active":
            continue
        core = data.get("core", {})
        if script == "seo":
            result[code] = {
                "domain":   core.get("domain", ""),
                "url":      core.get("url", ""),
                "label":    core.get("label", code),
                "keywords": data.get("seo", {}).get("keywords", []),
            }
        elif script == "content":
            c = data.get("content", {})
            result[code] = {
                "label":    core.get("label", code),
                "domain":   core.get("domain", ""),
                "blog_url": c.get("blog_url", ""),
                "cms":      c.get("cms", ""),
                "keywords": data.get("seo", {}).get("keywords", []),
                "tone":     c.get("tone", ""),
                "cta":      c.get("cta", ""),
            }
        elif script == "newsletter":
            n = data.get("newsletter", {})
            result[code] = {
                "domain":          core.get("domain", ""),
                "label":           core.get("label", code),
                "from_name":       n.get("from_name", core.get("label", code)),
                "from_email":      n.get("from_email", ""),
                "subject_tpl":     n.get("subject_tpl", "Newsletter {month}"),
                "accent":          n.get("accent", core.get("primary_color", "#3b82f6")),
                "audience_id":     n.get("audience_id", ""),
                "topics":          n.get("topics", []),
                "cta_url":         n.get("cta_url", core.get("url", "")),
                "cta_label":       n.get("cta_label", "En savoir plus"),
                "footer_desc":     n.get("footer_desc", ""),
                "emdash_token_env": n.get("emdash_token_env", ""),
                "wp_site_env":     n.get("wp_site_env", ""),
            }
        elif script == "indexation":
            idx = data.get("indexation", {})
            c   = data.get("content", {})
            result[code] = {
                "domain":      core.get("domain", ""),
                "sitemap_url": idx.get("sitemap_url", ""),
                "blog_prefix": idx.get("blog_prefix", ""),
                "cms":         c.get("cms", ""),
            }
        elif script == "seo_agent":
            sa = data.get("seo_agent", {})
            result[code] = {
                "rss_sources":        sa.get("rss_sources", []),
                "is_directory_target": sa.get("is_directory_target", False),
            }
        elif script == "api":
            result[code] = {
                "label":        core.get("label", code),
                "domain":       core.get("domain", ""),
                "url":          core.get("url", ""),
                "site_modules": data.get("api", {}).get("site_modules", ["content"]),
                "cms":          data.get("content", {}).get("cms", ""),
                "primary_color": core.get("primary_color", "#3b82f6"),
            }
        else:
            # Retourne tout le core + le bloc spécifique si connu
            result[code] = {**core}
    return result


def register_site(code: str, site_data: dict) -> None:
    """Enregistre un nouveau site. Lève ValueError si le code existe déjà."""
    raw = _load_raw()
    if code in raw.get("sites", {}):
        raise ValueError(f"Site '{code}' existe déjà.")
    raw.setdefault("sites", {})[code] = site_data
    _save_raw(raw)


def update_site(code: str, partial: dict) -> None:
    """Deep-merge partiel dans un site existant."""
    raw = _load_raw()
    if code not in raw.get("sites", {}):
        raise KeyError(f"Site '{code}' introuvable.")
    _deep_merge(raw["sites"][code], partial)
    _save_raw(raw)


def get_env_var_name(code: str, var_type: str) -> str:
    """
    Retourne le nom de la variable .env pour ce site.
    Gère le cas legacy LCR (pas de suffixe _CODE).

    var_type: "emdash_token" | "emdash_url" | "wp_url" | "wp_user" | "wp_pass"
    """
    site = get_site(code)
    creds = site.get("cms_credentials", {}) if site else {}

    if var_type == "emdash_token":
        return creds.get("emdash_token_env", f"EMDASH_API_TOKEN_{code.upper()}")
    if var_type == "emdash_url":
        return creds.get("emdash_url_env", f"EMDASH_API_URL_{code.upper()}")
    if var_type == "wp_url":
        return creds.get("wp_url_env", f"WP_SITE_URL_{code.upper()}")
    if var_type == "wp_user":
        return creds.get("wp_user_env", f"WP_USERNAME_{code.upper()}")
    if var_type == "wp_pass":
        return creds.get("wp_pass_env", f"WP_APP_PASSWORD_{code.upper()}")
    return f"{var_type.upper()}_{code.upper()}"


# ── Génération du chunk RAG ───────────────────────────────────────────────────

def _render_site_context(code: str, data: dict) -> str:
    """Génère le texte du chunk RAG depuis le dict de config."""
    core = data.get("core", {})
    rag  = data.get("rag_context", {})
    cont = data.get("content", {})
    seo  = data.get("seo", {})
    now  = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    competitors = "\n".join(f"- {c}" for c in rag.get("competitors", []))
    products    = "\n".join(f"- {p}" for p in rag.get("products_services", []))
    keywords    = ", ".join(seo.get("keywords", []))

    return f"""# Contexte site — {core.get('label', code)} ({code})
> Généré le {now} | Source: sites-config.json

## Identité
- Domaine : {core.get('domain', '')} | URL : {core.get('url', '')}
- Secteur : {rag.get('industry', '')} | Pays : {core.get('country', 'fr')} | Langue : {core.get('language', 'fr')}

## Description de l'activité
{rag.get('business_description', '')}

## Audience principale
{rag.get('primary_audience', '')}

## Proposition de valeur
{rag.get('value_proposition', '')}

## Produits et services
{products}

## Ton éditorial
{rag.get('tone_of_voice', '')}
- Ton rédactionnel : {cont.get('tone', '')}
- CTA type : "{cont.get('cta', '')}"

## Objectifs SEO
{rag.get('seo_goals', '')}
Mots-clés prioritaires : {keywords}

## Concurrents principaux
{competitors}

## Règles de publication
- 1 article max/semaine | 1800-2500 mots | Format Markdown H2/H3
- Mot-clé principal dans : H1, premier paragraphe, au moins 2 H2
- CTA final obligatoire : "{cont.get('cta', '')}"
"""


def write_site_context(code: str) -> Path:
    """Écrit/met à jour memory/{code}/site-context.md. Retourne le chemin."""
    site = get_site(code)
    if not site:
        raise KeyError(f"Site '{code}' introuvable.")
    path = BASE_DIR / "memory" / code / "site-context.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_site_context(code, site))
    return path


def seed_config_file() -> None:
    """Crée le fichier sites-config.json avec LCR + MKD si absent."""
    if CONFIG_FILE.exists():
        return
    data = {"version": 2, "sites": copy.deepcopy(_LEGACY)}
    _save_raw(data)
    print(f"[sites_config] Fichier créé: {CONFIG_FILE}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _deep_merge(base: dict, overlay: dict) -> dict:
    """Merge récursif de overlay dans base (modifie base in-place)."""
    for k, v in overlay.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


# ── CLI de test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    seed_config_file()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "list":
        sites = load_all_sites()
        print(f"Sites enregistrés ({len(sites)}):")
        for code, data in sites.items():
            status = data.get("_meta", {}).get("status", "?")
            label  = data.get("core", {}).get("label", code)
            print(f"  [{status}] {code} — {label}")

    elif cmd == "context" and len(sys.argv) > 2:
        code = sys.argv[2]
        path = write_site_context(code)
        print(f"Chunk RAG écrit: {path}")
        print(get_site_context(code)[:500])

    elif cmd == "test-script" and len(sys.argv) > 2:
        script = sys.argv[2]
        sites = get_sites_for_script(script)
        print(f"SITES pour '{script}' ({len(sites)} sites):")
        for code, cfg in sites.items():
            print(f"  {code}: {list(cfg.keys())}")
