#!/usr/bin/env python3
"""
indexation_agent.py — Agent d'indexation autonome.

T1 : Audit sitemaps → liste URLs manquantes / non accessibles
T2 : Soumission IndexNow (Bing, Yandex, Seznam) + Bing Webmaster API
T3 : Génération sitemap dynamique LCR enrichi avec tous les articles Emdash

Usage:
  python3 scripts/indexation_agent.py --task audit
  python3 scripts/indexation_agent.py --task submit --site lcr
  python3 scripts/indexation_agent.py --task sitemap --site lcr
  python3 scripts/indexation_agent.py --task all
"""

import argparse
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"
SEO_DIR  = BASE_DIR / "memory" / "seo"
SEO_DIR.mkdir(parents=True, exist_ok=True)

INDEXNOW_KEY  = "genesis-lcr-indexnow-2026"   # clé à placer sur le site
INDEXNOW_HOST = "https://api.indexnow.org/IndexNow"

# ── Config multi-sites (centrale si dispo, sinon fallback) ───────────────────
try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.sites_config import get_sites_for_script as _gss
    SITES = _gss("indexation")
except Exception as _e:
    SITES = {
        "lcr": {"domain": "leclientroi.com", "sitemap_url": "https://leclientroi.com/sitemap.xml",
                "blog_prefix": "https://leclientroi.com/blog/", "cms": "emdash"},
        "mkd": {"domain": "mkdgroupe.com", "sitemap_url": "https://www.mkdgroupe.com/sitemap_index.xml",
                "blog_prefix": "https://mkdgroupe.com/", "cms": "wordpress"},
    }


def load_env() -> dict:
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


# ── T1 : Audit sitemap ────────────────────────────────────────────────────────

def parse_sitemap(url: str, visited: set = None) -> list[str]:
    """Parse un sitemap XML (supporte les sitemap index)."""
    if visited is None:
        visited = set()
    if url in visited:
        return []
    visited.add(url)

    try:
        r = requests.get(url, timeout=10, allow_redirects=True,
                        headers={"User-Agent": "Genesis-IndexBot/1.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        # Sitemap index → récurser
        sitemaps = root.findall("sm:sitemap/sm:loc", ns)
        if sitemaps:
            urls = []
            for sm in sitemaps:
                child_url = sm.text.strip()
                urls.extend(parse_sitemap(child_url, visited))
            return urls

        # Sitemap normal
        return [loc.text.strip() for loc in root.findall("sm:url/sm:loc", ns) if loc.text]
    except Exception as e:
        print(f"  ⚠ Erreur sitemap {url}: {e}")
        return []


def check_url_status(url: str, timeout: int = 8) -> dict:
    """Vérifie le statut HTTP d'une URL."""
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        return {"url": url, "status": r.status_code, "ok": r.status_code < 400}
    except Exception as e:
        return {"url": url, "status": 0, "ok": False, "error": str(e)}


def get_emdash_articles(env: dict) -> list[dict]:
    """Récupère tous les articles publiés Emdash (pagination, max 100/page)."""
    try:
        all_items = []
        cursor = None
        while True:
            url = "http://localhost:4321/_emdash/api/content/posts?limit=100"
            if cursor:
                url += f"&cursor={cursor}"
            r = requests.get(
                url,
                headers={"Authorization": f"Bearer {env['EMDASH_API_TOKEN']}"},
                timeout=10,
            )
            data = r.json().get("data", {})
            items = data.get("items", [])
            all_items.extend(items)
            cursor = data.get("nextCursor")
            if not cursor or len(items) < 100:
                break
        published = [i for i in all_items if i.get("status") == "published"]
        return [{
            "slug":  item["slug"],
            "url":   f"https://leclientroi.com/blog/{item['slug']}",
            "title": item.get("data", {}).get("title", item["slug"]),
            "date":  item.get("updatedAt") or item.get("createdAt", ""),
        } for item in published]
    except Exception as e:
        print(f"  ⚠ Emdash: {e}")
        return []


def get_wp_articles(env: dict) -> list[dict]:
    """Récupère tous les articles WordPress publiés."""
    import base64
    auth = base64.b64encode(f"{env['WP_USERNAME']}:{env['WP_APP_PASSWORD']}".encode()).decode()
    articles = []
    page = 1
    while True:
        try:
            r = requests.get(
                f"{env['WP_SITE_URL']}/wp-json/wp/v2/posts?per_page=100&status=publish&page={page}&_fields=slug,link,title,modified",
                headers={"Authorization": f"Basic {auth}"},
                timeout=8,
            )
            items = r.json()
            if not items or isinstance(items, dict):
                break
            for item in items:
                articles.append({
                    "slug":  item.get("slug", ""),
                    "url":   item.get("link", ""),
                    "title": item.get("title", {}).get("rendered", ""),
                    "date":  item.get("modified", ""),
                })
            if len(items) < 100:
                break
            page += 1
        except Exception as e:
            print(f"  ⚠ WP: {e}")
            break
    return articles


def audit(site: str, env: dict) -> dict:
    """Audit complet : sitemap vs articles réels vs statuts HTTP."""
    cfg = SITES[site]
    print(f"\n[T1] Audit {site.upper()} — {cfg['domain']}")

    # Sitemap
    print(f"  Parsing sitemap: {cfg['sitemap_url']}")
    sitemap_urls = parse_sitemap(cfg["sitemap_url"])
    print(f"  {len(sitemap_urls)} URLs dans le sitemap")

    # Articles réels
    if cfg["cms"] == "emdash":
        articles = get_emdash_articles(env)
    else:
        articles = get_wp_articles(env)
    print(f"  {len(articles)} articles publiés sur le CMS")

    # URLs manquantes dans le sitemap
    sitemap_set = set(sitemap_urls)
    missing_from_sitemap = [a for a in articles if a["url"] not in sitemap_set]
    print(f"  {len(missing_from_sitemap)} articles MANQUANTS dans le sitemap")

    # Check HTTP sur un échantillon (max 20 pour ne pas surcharger)
    print(f"  Vérification HTTP statuts (échantillon 20 URLs)...")
    sample = sitemap_urls[:10] + [a["url"] for a in missing_from_sitemap[:10]]
    statuses = []
    for url in sample:
        s = check_url_status(url)
        statuses.append(s)
        icon = "✓" if s["ok"] else "✗"
        print(f"    {icon} {s['status']} {url[:70]}")
        time.sleep(0.2)

    broken = [s for s in statuses if not s["ok"]]

    result = {
        "site":                  site,
        "domain":                cfg["domain"],
        "date":                  datetime.now(timezone.utc).isoformat(),
        "sitemap_count":         len(sitemap_urls),
        "published_count":       len(articles),
        "missing_from_sitemap":  [a["url"] for a in missing_from_sitemap],
        "missing_articles":      missing_from_sitemap,
        "broken_urls":           broken,
        "sitemap_urls":          sitemap_urls,
        "all_articles":          articles,
    }

    # Sauvegarder
    out = SEO_DIR / f"{site}-indexation-audit.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"  Rapport: {out}")

    # Rapport Markdown lisible
    md = [
        f"# Audit Indexation — {site.upper()} — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"## Résumé",
        f"- URLs dans sitemap : **{len(sitemap_urls)}**",
        f"- Articles publiés CMS : **{len(articles)}**",
        f"- Manquants dans sitemap : **{len(missing_from_sitemap)}**",
        f"- URLs cassées (échantillon) : **{len(broken)}**",
        "",
        f"## Articles manquants dans le sitemap",
        f"*Ces {len(missing_from_sitemap)} articles sont publiés mais Google ne les voit pas :*",
        "",
    ]
    for a in missing_from_sitemap:
        md.append(f"- [{a['title'][:60]}]({a['url']})")

    if broken:
        md += ["", "## URLs cassées (404/erreur)", ""]
        for b in broken:
            md.append(f"- {b['status']} — {b['url']}")

    md_path = SEO_DIR / f"{site}-indexation-rapport.md"
    md_path.write_text("\n".join(md))
    print(f"  Rapport MD: {md_path}")

    return result


# ── T2 : Soumission IndexNow ──────────────────────────────────────────────────

def generate_indexnow_key_file(site: str) -> str:
    """Génère les instructions pour placer la clé IndexNow sur le site."""
    key = INDEXNOW_KEY
    cfg = SITES[site]
    instructions = f"""
# IndexNow — Instructions de configuration pour {site.upper()}

## 1. Clé générée : {key}

## 2. Fichier à placer sur le site
Créer le fichier : https://{cfg['domain']}/{key}.txt
Contenu du fichier (une seule ligne) :
{key}

## Pour LCR (Emdash)
Demander à l'équipe Emdash de servir ce fichier statique, OU
ajouter une route dans le serveur nginx :
location = /{key}.txt {{
    return 200 '{key}';
    add_header Content-Type text/plain;
}}

## Pour MKD (WordPress)
Créer le fichier : /var/www/mkdgroupe.com/{key}.txt
Avec le contenu : {key}

## 3. Tester
curl https://{cfg['domain']}/{key}.txt
# Doit retourner : {key}
"""
    key_file = SEO_DIR / f"{site}-indexnow-setup.md"
    key_file.write_text(instructions)
    return key


def submit_indexnow(urls: list[str], domain: str, dry_run: bool = False) -> dict:
    """Soumet des URLs via IndexNow (Bing, Yandex, Seznam...)."""
    if not urls:
        return {"submitted": 0}

    # Batch max 10,000 URLs
    chunks = [urls[i:i+500] for i in range(0, len(urls), 500)]
    total_submitted = 0

    for chunk in chunks:
        payload = {
            "host":    domain,
            "key":     INDEXNOW_KEY,
            "keyLocation": f"https://{domain}/{INDEXNOW_KEY}.txt",
            "urlList": chunk,
        }

        if dry_run:
            print(f"  DRY-RUN — {len(chunk)} URLs prêtes pour IndexNow")
            print(f"  Premier: {chunk[0]}")
            total_submitted += len(chunk)
            continue

        try:
            r = requests.post(
                INDEXNOW_HOST,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            if r.status_code in (200, 202):
                print(f"  ✓ IndexNow: {len(chunk)} URLs soumises (status {r.status_code})")
                total_submitted += len(chunk)
            else:
                print(f"  ⚠ IndexNow: {r.status_code} — {r.text[:100]}")
        except Exception as e:
            print(f"  ⚠ IndexNow erreur: {e}")
        time.sleep(1)

    return {"submitted": total_submitted, "domain": domain}


def submit_bing_webmaster(urls: list[str], site_url: str, api_key: str) -> dict:
    """Soumet des URLs via Bing Webmaster API."""
    if not api_key:
        print("  BING_WEBMASTER_KEY manquant dans .env — skip Bing direct")
        return {"submitted": 0, "skipped": True}

    endpoint = f"https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlbatch?apikey={api_key}"
    payload  = {"siteUrl": site_url, "urlList": urls[:500]}

    try:
        r = requests.post(endpoint, json=payload,
                         headers={"Content-Type": "application/json"}, timeout=15)
        if r.status_code == 200:
            print(f"  ✓ Bing Webmaster: {len(urls[:500])} URLs soumises")
            return {"submitted": len(urls[:500])}
        else:
            print(f"  ⚠ Bing: {r.status_code} — {r.text[:100]}")
            return {"submitted": 0, "error": r.text}
    except Exception as e:
        print(f"  ⚠ Bing erreur: {e}")
        return {"submitted": 0, "error": str(e)}


def submit_task(site: str, env: dict, dry_run: bool = True):
    """Lance la soumission IndexNow + Bing pour un site."""
    cfg  = SITES[site]
    print(f"\n[T2] Soumission indexation {site.upper()}")

    # Charger l'audit existant
    audit_file = SEO_DIR / f"{site}-indexation-audit.json"
    if not audit_file.exists():
        print("  Audit manquant — lancer d'abord --task audit")
        return

    data    = json.loads(audit_file.read_text())
    missing = data.get("missing_from_sitemap", [])
    all_urls = data.get("sitemap_urls", [])

    # Prioriser les manquants, puis tout le reste
    urls_to_submit = missing + [u for u in all_urls if u not in missing]
    print(f"  {len(urls_to_submit)} URLs à soumettre ({len(missing)} prioritaires)")

    # Générer la clé IndexNow
    generate_indexnow_key_file(site)
    print(f"  Clé IndexNow: {INDEXNOW_KEY}")
    print(f"  Fichier à placer: https://{cfg['domain']}/{INDEXNOW_KEY}.txt")

    # Soumettre IndexNow
    result_indexnow = submit_indexnow(urls_to_submit, cfg["domain"], dry_run=dry_run)

    # Bing Webmaster direct
    bing_key = env.get("BING_WEBMASTER_KEY", "")
    result_bing = submit_bing_webmaster(urls_to_submit, f"https://{cfg['domain']}", bing_key)

    # Logger
    log = {
        "date":         datetime.now(timezone.utc).isoformat(),
        "site":         site,
        "indexnow":     result_indexnow,
        "bing":         result_bing,
        "urls_count":   len(urls_to_submit),
        "dry_run":      dry_run,
    }
    log_file = SEO_DIR / f"{site}-submission-log.json"
    existing = []
    if log_file.exists():
        try:
            existing = json.loads(log_file.read_text())
        except Exception:
            pass
    existing.append(log)
    log_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
    return log


# ── T3 : Sitemap dynamique LCR ───────────────────────────────────────────────

def generate_sitemap_lcr(env: dict) -> str:
    """Génère un sitemap.xml complet pour LCR incluant tous les articles Emdash."""
    print("\n[T3] Génération sitemap dynamique LCR")

    articles = get_emdash_articles(env)
    print(f"  {len(articles)} articles publiés trouvés")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Pages statiques (conservées du sitemap original)
    static_pages = [
        ("https://leclientroi.com/",                     today,  "weekly",  "1.0"),
        ("https://leclientroi.com/tarifs",               today,  "monthly", "0.9"),
        ("https://leclientroi.com/fonctionnalites",      today,  "monthly", "0.8"),
        ("https://leclientroi.com/sms-marketing",        today,  "weekly",  "0.9"),
        ("https://leclientroi.com/contact",              today,  "monthly", "0.7"),
        ("https://leclientroi.com/a-propos",             today,  "monthly", "0.6"),
        ("https://leclientroi.com/guides",               today,  "weekly",  "0.8"),
        ("https://leclientroi.com/secteurs",             today,  "monthly", "0.7"),
        ("https://leclientroi.com/blog",                 today,  "daily",   "0.9"),
        ("https://leclientroi.com/calculateur-roi",      today,  "monthly", "0.8"),
        ("https://leclientroi.com/affiliation",          today,  "monthly", "0.6"),
    ]

    # Pages géo SMS marketing (villes)
    villes = [
        "paris","marseille","lyon","toulouse","nice","nantes","montpellier",
        "strasbourg","bordeaux","lille","rennes","reims","saint-etienne","toulon",
        "le-havre","grenoble","dijon","angers","nimes","villeurbanne","caen",
        "aix-en-provence","clermont-ferrand","brest","tours","amiens","limoges",
        "perpignan","metz","besancon","orleans","rouen","mulhouse","annecy",
        "le-mans","bourg-en-bresse",
    ]
    geo_pages = [
        (f"https://leclientroi.com/sms-marketing/{v}", today, "monthly", "0.7")
        for v in villes
    ]

    # Pages secteurs
    secteurs = [
        "immobilier","beaute-bien-etre","sms-restauration","sms-automobile",
        "sms-retail-franchise","services-personne",
    ]
    secteur_pages = [
        (f"https://leclientroi.com/secteurs/{s}", today, "monthly", "0.7")
        for s in secteurs
    ]

    # Guides
    guides = ["sms-globale","sms-artisans","sms-immobilier","sms-boutiques"]
    guide_pages = [
        (f"https://leclientroi.com/guides/{g}", today, "monthly", "0.7")
        for g in guides
    ]

    # Articles blog (dynamiques depuis Emdash)
    blog_pages = [
        (a["url"], (a["date"] or today)[:10], "weekly", "0.8")
        for a in articles
    ]

    all_pages = static_pages + geo_pages + secteur_pages + guide_pages + blog_pages

    # Générer le XML
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
        '',
        '  <!-- Généré automatiquement par Genesis SEO Agent -->',
        f'  <!-- Dernière mise à jour : {today} — {len(all_pages)} URLs -->',
        '',
    ]

    sections = [
        ("Pages principales", static_pages),
        ("Pages géolocalisées SMS", geo_pages),
        ("Secteurs d'activité", secteur_pages),
        ("Guides", guide_pages),
        (f"Articles blog ({len(blog_pages)})", blog_pages),
    ]

    for section_name, pages in sections:
        lines.append(f"  <!-- {section_name} -->")
        for url, lastmod, changefreq, priority in pages:
            lines += [
                "  <url>",
                f"    <loc>{url}</loc>",
                f"    <lastmod>{lastmod}</lastmod>",
                f"    <changefreq>{changefreq}</changefreq>",
                f"    <priority>{priority}</priority>",
                "  </url>",
            ]
        lines.append("")

    lines.append("</urlset>")
    sitemap_xml = "\n".join(lines)

    # Sauvegarder localement
    sitemap_path = BASE_DIR / "data" / "sitemap-lcr.xml"
    sitemap_path.parent.mkdir(parents=True, exist_ok=True)
    sitemap_path.write_text(sitemap_xml)
    print(f"  Sitemap généré: {sitemap_path} ({len(all_pages)} URLs)")
    print(f"  Articles blog inclus: {len(blog_pages)}")

    # Instructions pour déployer
    instructions = f"""
# Déploiement sitemap LCR

Le sitemap complet est dans : {sitemap_path}
Il contient {len(all_pages)} URLs dont {len(blog_pages)} articles blog.

## Option A — Remplacer le sitemap Emdash (recommandé)
Configurer nginx pour servir ce fichier à la place du sitemap Emdash :

location = /sitemap.xml {{
    alias {sitemap_path};
    add_header Content-Type application/xml;
    add_header Cache-Control "max-age=3600";
}}

## Option B — Soumettre manuellement à Google
1. Aller sur search.google.com/search-console
2. Sitemaps → Ajouter un sitemap
3. Entrer l'URL du sitemap

## Option C — Utiliser le sitemap Emdash amélioré
Demander à Emdash de configurer le sitemap pour inclure automatiquement tous les articles /blog/*.

## Resoumission automatique via cron
Le genesis-seo-agent regénère ce sitemap à chaque run (tous les matins 5h UTC).
"""
    (SEO_DIR / "sitemap-deploy-instructions.md").write_text(instructions)
    print(f"  Instructions: {SEO_DIR}/sitemap-deploy-instructions.md")

    return sitemap_xml


# ── Exposition via API nginx ──────────────────────────────────────────────────

def generate_nginx_patches() -> str:
    """Génère les patches nginx pour servir le sitemap et la clé IndexNow."""
    patch = f"""
# === Genesis SEO — Patches nginx pour leclientroi.com ===
# Ajouter dans le bloc server{{}} de leclientroi.com

# Sitemap dynamique (généré par Genesis)
location = /sitemap.xml {{
    alias /home/autoblog/genesis/data/sitemap-lcr.xml;
    add_header Content-Type application/xml;
    add_header Cache-Control "max-age=3600";
}}

# Clé IndexNow (Bing, Yandex, Seznam)
location = /{INDEXNOW_KEY}.txt {{
    return 200 '{INDEXNOW_KEY}';
    add_header Content-Type text/plain;
}}

# === Fin patches Genesis ===
"""
    patch_file = BASE_DIR / "dashboard" / "nginx-seo-patches.conf"
    patch_file.write_text(patch)
    print(f"  Nginx patches: {patch_file}")
    print(f"  -> Envoyer à l'admin pour intégration dans la config nginx LCR")
    return patch


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task",    choices=["all", "audit", "submit", "sitemap", "daily"], default="all")
    parser.add_argument("--site",    choices=["lcr", "mkd", "both"],                         default="both")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--live",    action="store_true")
    args = parser.parse_args()

    env     = load_env()
    dry_run = not args.live
    sites   = ["lcr", "mkd"] if args.site == "both" else [args.site]

    print(f"[indexation_agent] {datetime.now(timezone.utc).isoformat()} — {'DRY-RUN' if dry_run else 'LIVE'}")

    for site in sites:
        if args.task == "daily":
            daily_task(site, env, dry_run=dry_run)
            continue

        if args.task in ("all", "audit"):
            audit(site, env)

        if args.task in ("all", "submit"):
            submit_task(site, env, dry_run=dry_run)

        if args.task in ("all", "sitemap") and site == "lcr":
            generate_sitemap_lcr(env)
            generate_nginx_patches()

    print(f"\n[indexation_agent] Terminé {datetime.now(timezone.utc).isoformat()}")

# ── T4 : Mode quotidien (diff + soumission seulement des nouveaux) ─────────────

SUBMITTED_LOG_TMPL = "memory/seo/{site}-submitted-urls.json"


def load_submitted_log(site: str) -> dict:
    """Charge le log des URLs déjà soumises.
    Structure: { url: {first_submitted, last_submitted, count, engines[]} }
    """
    path = BASE_DIR / SUBMITTED_LOG_TMPL.format(site=site)
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_submitted_log(site: str, log: dict) -> None:
    path = BASE_DIR / SUBMITTED_LOG_TMPL.format(site=site)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2))


def find_new_articles(site: str, env: dict) -> list[dict]:
    """Retourne les articles publiés MAIS pas encore dans le log de soumission."""
    cfg = SITES.get(site, {})
    if cfg.get("cms") == "emdash":
        articles = get_emdash_articles(env)
    elif cfg.get("cms") == "wordpress":
        articles = get_wp_articles(env)
    else:
        return []

    submitted = load_submitted_log(site)
    new = [a for a in articles if a["url"] not in submitted]
    return new


def submit_google_indexing_api(urls: list[str], service_account_json: str) -> dict:
    """
    Soumet des URLs à Google via la Indexing API (nécessite un Service Account JSON).
    Officiellement pour JobPosting/BroadcastEvent, mais fonctionne pour tous les types.

    Pour l'activer :
    1. Google Cloud Console → activer "Indexing API"
    2. Créer un Service Account → télécharger le JSON
    3. Dans Google Search Console → Ajouter le Service Account comme "Propriétaire"
    4. Mettre le chemin du JSON dans .env : GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/key.json

    Limite : 200 URLs/jour par projet.
    """
    if not service_account_json or not Path(service_account_json).exists():
        print("  ⚠ GOOGLE_SERVICE_ACCOUNT_JSON absent ou fichier introuvable — skip Google")
        return {"submitted": 0, "skipped": True}

    try:
        import importlib
        google_auth = importlib.import_module("google.oauth2.service_account")
        google_req  = importlib.import_module("google.auth.transport.requests")
    except ImportError:
        print("  ⚠ Package 'google-auth' non installé — pip install google-auth")
        print("    (pour soumettre à Google Indexing API)")
        return {"submitted": 0, "skipped": True, "error": "google-auth not installed"}

    SCOPES = ["https://www.googleapis.com/auth/indexing"]
    try:
        creds = google_auth.Credentials.from_service_account_file(
            service_account_json, scopes=SCOPES
        )
        authed_session = google_req.AuthorizedSession(creds)

        submitted = 0
        errors    = []
        for url in urls[:200]:  # limite quotidienne Google
            payload = {"url": url, "type": "URL_UPDATED"}
            resp = authed_session.post(
                "https://indexing.googleapis.com/v3/urlNotifications:publish",
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                submitted += 1
            else:
                errors.append(f"{url}: {resp.status_code} {resp.text[:80]}")
            time.sleep(0.1)  # 10 req/s max

        print(f"  ✓ Google Indexing API: {submitted}/{len(urls[:200])} URLs soumises")
        if errors:
            print(f"  ⚠ {len(errors)} erreurs: {errors[0]}")
        return {"submitted": submitted, "errors": errors}

    except Exception as e:
        print(f"  ⚠ Google Indexing API erreur: {e}")
        return {"submitted": 0, "error": str(e)}


def generate_sitemap_mkd(env: dict) -> str:
    """Génère un sitemap dynamique pour MKD Groupe (WordPress)."""
    import base64

    wp_url  = env.get("WP_SITE_URL", "https://mkdgroupe.com").rstrip("/")
    wp_user = env.get("WP_USERNAME", "")
    wp_pass = env.get("WP_APP_PASSWORD", "")
    auth    = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()

    # Fetch all published WP posts
    all_posts = []
    page = 1
    while True:
        try:
            r = requests.get(
                f"{wp_url}/wp-json/wp/v2/posts?per_page=100&status=publish&page={page}"
                "&_fields=slug,link,date,modified",
                headers={"Authorization": f"Basic {auth}"},
                timeout=15,
            )
            if r.status_code != 200:
                break
            posts = r.json()
            if not posts:
                break
            all_posts.extend(posts)
            if len(posts) < 100:
                break
            page += 1
        except Exception as e:
            print(f"  ⚠ WP posts page {page}: {e}")
            break

    print(f"  {len(all_posts)} articles WP récupérés")

    # Also fetch pages
    try:
        r = requests.get(
            f"{wp_url}/wp-json/wp/v2/pages?per_page=100&status=publish"
            "&_fields=slug,link,date,modified",
            headers={"Authorization": f"Basic {auth}"},
            timeout=10,
        )
        pages = r.json() if r.status_code == 200 else []
    except Exception:
        pages = []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = []

    # Static pages
    static = [
        (wp_url + "/", "weekly", "1.0"),
        (wp_url + "/blog/", "daily", "0.9"),
        (wp_url + "/contact/", "monthly", "0.7"),
    ]
    for loc, freq, prio in static:
        urls.append(f"  <url><loc>{loc}</loc><changefreq>{freq}</changefreq><priority>{prio}</priority><lastmod>{now}</lastmod></url>")

    # WP pages
    for p in pages:
        loc = p.get("link", "")
        mod = p.get("modified", now)[:10]
        if loc:
            urls.append(f"  <url><loc>{loc}</loc><changefreq>monthly</changefreq><priority>0.7</priority><lastmod>{mod}</lastmod></url>")

    # WP posts (articles)
    for p in all_posts:
        loc = p.get("link", "")
        mod = p.get("modified", now)[:10]
        if loc:
            urls.append(f"  <url><loc>{loc}</loc><changefreq>monthly</changefreq><priority>0.8</priority><lastmod>{mod}</lastmod></url>")

    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap_xml += "\n".join(urls) + "\n"
    sitemap_xml += "</urlset>\n"

    out_path = BASE_DIR / "data" / "sitemap-mkd.xml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sitemap_xml, encoding="utf-8")

    print(f"  Sitemap MKD: {out_path} ({len(all_posts)} articles + {len(pages)} pages)")
    return sitemap_xml


def daily_task(site: str, env: dict, dry_run: bool = True) -> dict:
    """
    Pipeline quotidien pour un site :
    1. Récupère tous les articles publiés depuis le CMS
    2. Charge le log de soumission précédent
    3. Identifie les NOUVEAUX articles (jamais soumis)
    4. Régénère le sitemap
    5. Soumet les nouveaux articles à IndexNow + Google Indexing API
    6. Met à jour le log de soumission
    7. Retourne le rapport

    Avantage par rapport au mode "all" : ne soumet QUE les nouveaux articles,
    pas toute la liste à chaque run (évite les pénalités de spam).
    """
    cfg    = SITES.get(site, {})
    domain = cfg.get("domain", "")
    now    = datetime.now(timezone.utc).isoformat()

    print(f"\n[T4-daily] {site.upper()} — {'DRY-RUN' if dry_run else 'LIVE'}")

    # 1. Fetch published articles
    if cfg.get("cms") == "emdash":
        articles = get_emdash_articles(env)
    elif cfg.get("cms") == "wordpress":
        articles = get_wp_articles(env)
    else:
        print(f"  ⚠ CMS inconnu pour {site}")
        return {"site": site, "error": "unknown cms"}

    print(f"  {len(articles)} articles publiés dans le CMS")

    # 2. Load submitted log
    submitted_log = load_submitted_log(site)
    all_known_urls = set(submitted_log.keys())

    # 3. Find new articles
    new_articles = [a for a in articles if a["url"] not in all_known_urls]
    already_submitted = len(articles) - len(new_articles)

    print(f"  {already_submitted} déjà soumis | {len(new_articles)} nouveaux à soumettre")

    if not new_articles and not dry_run:
        print(f"  Rien de nouveau — skip soumission")
        return {
            "site": site, "date": now,
            "total_articles": len(articles),
            "new_articles": 0,
            "already_submitted": already_submitted,
            "submitted_indexnow": 0,
            "submitted_google": 0,
        }

    new_urls = [a["url"] for a in new_articles]

    # 4. Régénération sitemap
    print(f"  Régénération sitemap {site.upper()}...")
    if site == "lcr":
        generate_sitemap_lcr(env)
    elif site == "mkd":
        generate_sitemap_mkd(env)

    # 5a. IndexNow — seulement les nouveaux
    if new_urls:
        indexnow_key = cfg.get("indexnow_key", INDEXNOW_KEY)
        result_indexnow = submit_indexnow_daily(new_urls, domain, indexnow_key, dry_run)
    else:
        result_indexnow = {"submitted": 0, "skipped": True}

    # 5b. Google Indexing API (optionnel)
    google_sa = env.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if new_urls and google_sa and not dry_run:
        result_google = submit_google_indexing_api(new_urls, google_sa)
    else:
        if google_sa:
            print(f"  Google Indexing API: {len(new_urls)} URLs prêtes (skip en dry-run)")
        else:
            print(f"  Google Indexing API: non configuré (GOOGLE_SERVICE_ACCOUNT_JSON manquant)")
            print(f"    → Voir docs: scripts/indexation_agent.py (fonction submit_google_indexing_api)")
        result_google = {"submitted": 0, "skipped": True}

    # 5c. Bing Webmaster direct (si clé configurée)
    bing_key = env.get("BING_WEBMASTER_KEY", "")
    if new_urls and bing_key and not dry_run:
        site_url = cfg.get("url", f"https://{domain}")
        submit_bing_webmaster(new_urls, site_url, bing_key)

    # 6. Mise à jour du log de soumission
    if not dry_run and new_urls:
        engines = ["bing", "yandex", "seznam"]
        if google_sa:
            engines.append("google")
        for article in new_articles:
            url = article["url"]
            if url in submitted_log:
                submitted_log[url]["last_submitted"] = now
                submitted_log[url]["count"] += 1
            else:
                submitted_log[url] = {
                    "title":           article.get("title", ""),
                    "slug":            article.get("slug", ""),
                    "first_submitted": now,
                    "last_submitted":  now,
                    "count":           1,
                    "engines":         engines,
                }
        save_submitted_log(site, submitted_log)
        print(f"  Log mis à jour: {len(submitted_log)} URLs connues")
    elif dry_run and new_urls:
        print(f"  DRY-RUN: log non mis à jour ({len(new_urls)} URLs seraient enregistrées)")

    result = {
        "site":              site,
        "date":              now,
        "total_articles":    len(articles),
        "new_articles":      len(new_articles),
        "already_submitted": already_submitted,
        "new_urls":          new_urls[:10],  # preview dans rapport
        "submitted_indexnow": result_indexnow.get("submitted", 0),
        "submitted_google":   result_google.get("submitted", 0),
        "dry_run":            dry_run,
    }

    # Rapport JSON quotidien
    report_path = SEO_DIR / f"{site}-daily-report.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"  Rapport: {report_path}")

    return result


def submit_indexnow_daily(urls: list[str], domain: str, key: str, dry_run: bool) -> dict:
    """Soumet via IndexNow avec la clé spécifique au site."""
    if not urls:
        return {"submitted": 0}
    if dry_run:
        print(f"  DRY-RUN — {len(urls)} nouvelles URLs prêtes pour IndexNow")
        for u in urls[:3]:
            print(f"    → {u}")
        return {"submitted": len(urls)}

    chunks = [urls[i:i+500] for i in range(0, len(urls), 500)]
    total  = 0
    for chunk in chunks:
        payload = {
            "host":        domain,
            "key":         key,
            "keyLocation": f"https://{domain}/{key}.txt",
            "urlList":     chunk,
        }
        try:
            r = requests.post(INDEXNOW_HOST, json=payload,
                            headers={"Content-Type": "application/json"}, timeout=15)
            if r.status_code in (200, 202):
                print(f"  ✓ IndexNow: {len(chunk)} URLs soumises → {domain}")
                total += len(chunk)
            else:
                print(f"  ⚠ IndexNow {r.status_code}: {r.text[:100]}")
        except Exception as e:
            print(f"  ⚠ IndexNow: {e}")
        time.sleep(1)
    return {"submitted": total}


if __name__ == "__main__":
    main()
