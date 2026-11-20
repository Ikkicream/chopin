#!/usr/bin/env python3
"""
content_agent.py — Agent de publication autonome.

Chaque exécution :
  1. Lit le brief SEO Ahrefs + backlog d'articles
  2. Choisit le meilleur sujet (opportunité KD, volume, pas encore publié)
  3. Génère l'article complet via DeepSeek
  4. Publie sur LCR (Emdash) ou MKD (WordPress)
  5. Logue le coût et met à jour le dashboard

Cron : tous les jours lun/mer/ven à 10h UTC (après briefing+SEO)
Usage : python3 scripts/content_agent.py --site lcr
        python3 scripts/content_agent.py --site mkd
        python3 scripts/content_agent.py --site lcr --dry-run
"""

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests


try:
    from text_utils import slugify as _slugify  # type: ignore
except ImportError:
    from scripts.text_utils import slugify as _slugify  # type: ignore

BASE_DIR   = Path(__file__).parent.parent
ENV_FILE   = BASE_DIR / ".env"
SEO_DIR    = BASE_DIR / "memory" / "seo"
MEMORY_DIR = BASE_DIR / "memory"
BACKLOG_DIR = Path("/home/autoblog/blog/articles")

# ── Config multi-sites (centrale si dispo, sinon fallback) ───────────────────
try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.sites_config import get_sites_for_script as _gss, get_site_context as _gsc
    SITES = _gss("content")
    def _get_site_rag(site: str) -> str:
        return _gsc(site)
except Exception as _e:
    print(f"  [sites_config] fallback: {_e}")
    SITES = {
        "lcr": {
            "label": "LeClientROI", "domain": "leclientroi.com",
            "blog_url": "https://blog.leclientroi.com/posts/", "cms": "emdash",
            "keywords": ["sms marketing", "campagne sms", "sms geolocalise",
                         "location donnees geolocalisees", "rcs messagerie",
                         "sms professionnel", "envoyer sms en masse"],
            "tone": "expert SME friendly, exemples concrets, chiffres, actionnable",
            "cta": "Découvrez la solution SMS de LeClientROI",
        },
        "mkd": {
            "label": "MKD Groupe", "domain": "mkdgroupe.com",
            "blog_url": "https://mkdgroupe.com/", "cms": "wordpress",
            "keywords": ["prospection commerciale b2b", "rgpd marketing",
                         "data marketing b2b", "rcs entreprise", "base de donnees b2b"],
            "tone": "expert B2B, précis, cas d'usage enterprise, données chiffrées",
            "cta": "Contactez MKD Groupe pour votre stratégie data",
        },
    }
    def _get_site_rag(site: str) -> str:
        return ""


def load_env() -> dict:
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


# ── Choix du sujet ────────────────────────────────────────────────────────────

def get_published_slugs(site: str, env: dict) -> set:
    """Récupère les slugs déjà publiés pour éviter les doublons."""
    slugs = set()
    try:
        if site == "lcr":
            r = requests.get(
                "http://localhost:4321/_emdash/api/content/posts?limit=200",
                headers={"Authorization": f"Bearer {env['EMDASH_API_TOKEN']}"},
                timeout=5,
            )
            for item in r.json().get("data", {}).get("items", []):
                slugs.add(item.get("slug", ""))
        else:
            import base64
            auth = base64.b64encode(f"{env['WP_USERNAME']}:{env['WP_APP_PASSWORD']}".encode()).decode()
            r = requests.get(
                f"{env['WP_SITE_URL']}/wp-json/wp/v2/posts?per_page=100&status=any&_fields=slug",
                headers={"Authorization": f"Basic {auth}"},
                timeout=8,
            )
            for item in r.json():
                slugs.add(item.get("slug", ""))
    except Exception as e:
        print(f"  ⚠ get_published_slugs: {e}")
    return slugs


def choose_topic(site: str, published_slugs: set) -> dict:
    """
    Choisit le prochain sujet à écrire selon la priorité :
    1. Opportunités SEO KD<10 non encore publiées
    2. Backlog articles existants non publiés
    3. Mots-clés cibles du site
    """
    site_cfg = SITES[site]

    # 1. Opportunités Ahrefs (latest.json)
    latest = SEO_DIR / f"{site}-latest.json"
    if latest.exists():
        data = json.loads(latest.read_text())
        opps = data.get("opportunities", [])
        kw_overview = data.get("kw_overview", [])

        # Trier par volume desc, KD asc
        candidates = sorted(
            [k for k in opps if (k.get("volume") or 0) > 0],
            key=lambda x: (-(x.get("volume") or 0), (x.get("difficulty") or 100))
        )
        for kw in candidates[:10]:
            slug = kw["keyword"].lower().replace(" ", "-").replace("'", "-")[:60]
            if slug not in published_slugs:
                return {
                    "keyword":    kw["keyword"],
                    "volume":     kw.get("volume", 0),
                    "kd":         kw.get("difficulty", 0),
                    "source":     "ahrefs_opportunity",
                    "slug_hint":  slug,
                }

        # Mots-clés overview non encore couverts
        for kw in kw_overview:
            slug = kw.get("keyword", "").lower().replace(" ", "-")[:60]
            if slug and slug not in published_slugs and (kw.get("volume") or 0) > 50:
                return {
                    "keyword":   kw["keyword"],
                    "volume":    kw.get("volume", 0),
                    "kd":        kw.get("difficulty", 0),
                    "source":    "ahrefs_overview",
                    "slug_hint": slug,
                }

    # 2. Backlog articles (LCR uniquement)
    if site == "lcr" and BACKLOG_DIR.exists():
        articles = sorted(BACKLOG_DIR.glob("*.md"))
        for art in articles:
            slug = art.stem.lower()
            if slug not in published_slugs:
                content = art.read_text(encoding="utf-8", errors="ignore")
                title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                title = title_match.group(1) if title_match else art.stem.replace("-", " ").title()
                # Trouver le mot-clé principal dans le titre
                keyword = title.lower()
                for kw in site_cfg["keywords"]:
                    if kw in keyword:
                        keyword = kw
                        break
                return {
                    "keyword":   keyword,
                    "volume":    0,
                    "kd":        0,
                    "source":    "backlog",
                    "backlog_file": str(art),
                    "title":     title,
                    "slug_hint": slug,
                }

    # 3. Fallback sur mots-clés cibles
    for kw in site_cfg["keywords"]:
        slug = kw.lower().replace(" ", "-")
        if slug not in published_slugs:
            return {
                "keyword":   kw,
                "volume":    0,
                "kd":        0,
                "source":    "keyword_list",
                "slug_hint": slug,
            }

    return {}


# ── Génération article ────────────────────────────────────────────────────────

ARTICLE_PROMPT = """Tu es un expert en {topic_domain} et rédacteur SEO professionnel francophone.

Rédige un article de blog complet, optimisé SEO, en français sur le sujet suivant :
MOT-CLÉ CIBLE : "{keyword}"
SITE : {site_label} ({domain})
TON : {tone}

STRUCTURE OBLIGATOIRE (Markdown strict) :
1. Titre principal en syntaxe `# Titre` (60-70 caractères, intègre le mot-clé)
2. Paragraphe d'accroche directement après le titre — PAS de label « Introduction »,
   on entre dans le sujet par un fait, un chiffre ou une affirmation
3. 5-7 sections en `## Titre concret` (200-300 mots chacune)
4. Sous-sections en `### Titre concret` si utile
5. Listes à puces (`- `) UNIQUEMENT pour ≥ 4 éléments ; sinon rédige en prose
6. Données chiffrées avec source quand c'est possible (`Selon X, …`)
7. CTA final en une phrase : "{cta}"
8. Section finale avec un titre `##` concret (pas de label « Conclusion » ni « En résumé »)

INTERDIT (corrige avant de répondre) :
- Aucun préfixe `H2 :`, `H3 :`, `H4 :` dans les titres : seule la syntaxe `##` / `###` compte
- Aucun titre `## Introduction`, `## Conclusion`, `## En résumé` en label nu
- Aucune règle horizontale `---` dans le corps (on n'utilise PAS de frontmatter ici)
- Pour les illustrations d'exemple, mets le label en italique : `*Exemple : ...*` ou
  intègre l'exemple dans la phrase. Pas de `**Exemple :**` en gras.
- Pas de phrases entières en gras ; le **gras** sert pour les chiffres-clés et verbes d'action.

CONTRAINTES SEO :
- Mot-clé dans : titre, 1er paragraphe, au moins 2 H2, et naturellement dans le corps
- Densité mot-clé : 1-2%
- Longueur : 1800-2500 mots
- Mots-clés sémantiquement liés à "{keyword}" intégrés naturellement

Commence DIRECTEMENT par le titre `# …` sans préambule."""

ARTICLE_PROMPT_BACKLOG = """Tu es un expert en {topic_domain} et rédacteur SEO professionnel francophone.

Réécris et optimise SEO le texte suivant pour le mot-clé "{keyword}" sur le site {site_label}.
Améliore la structure, l'optimisation SEO, et enrichis le contenu.
Garde le même sujet mais rends-le 2x plus complet et mieux structuré.
TON : {tone}
Longueur cible : 1800-2500 mots en Markdown.

TEXTE ORIGINAL :
{backlog_content}

Commence DIRECTEMENT par le titre H1."""


def generate_article(topic: dict, site: str, env: dict) -> dict:
    """Génère un article via DeepSeek."""
    site_cfg = SITES[site]
    keyword = topic["keyword"]

    topic_domain = {
        "lcr": "SMS marketing, marketing digital local, communication client",
        "mkd": "data marketing B2B, RGPD, prospection commerciale, RCS entreprise",
    }[site]

    if topic.get("source") == "backlog" and topic.get("backlog_file"):
        backlog_content = Path(topic["backlog_file"]).read_text(encoding="utf-8", errors="ignore")[:4000]
        prompt = ARTICLE_PROMPT_BACKLOG.format(
            topic_domain=topic_domain,
            keyword=keyword,
            site_label=site_cfg["label"],
            tone=site_cfg["tone"],
            backlog_content=backlog_content,
        )
    else:
        prompt = ARTICLE_PROMPT.format(
            topic_domain=topic_domain,
            keyword=keyword,
            domain=site_cfg["domain"],
            site_label=site_cfg["label"],
            tone=site_cfg["tone"],
            cta=site_cfg["cta"],
        )

    # Enrichit le prompt avec les instructions IA du module articles pour ce site
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from modules_backend import enrich_prompt as _enrich
        prompt = _enrich(prompt, site, "articles")
    except Exception:
        pass

    print(f"  Génération via DeepSeek ({len(prompt)} chars prompt)...")
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {env['DEEPSEEK_API_KEY']}", "Content-Type": "application/json"},
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4000,
            "temperature": 0.7,
        },
        timeout=120,
    )
    resp.raise_for_status()
    result = resp.json()
    content = result["choices"][0]["message"]["content"]
    input_tok  = result.get("usage", {}).get("prompt_tokens", 0)
    output_tok = result.get("usage", {}).get("completion_tokens", 0)

    # Extraire le titre
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else f"Guide {keyword.title()} 2026"

    return {
        "content_md": content,
        "title":      title,
        "input_tok":  input_tok,
        "output_tok": output_tok,
    }


# ── Publication LCR (Emdash) ──────────────────────────────────────────────────

_INLINE_PAT = re.compile(r"(\*\*[^*]+?\*\*|\*[^*]+?\*)")
# Citations « ... » à styler en blockquote
_LABEL_QUOTE_RE = re.compile(r"^([A-ZÉÀÔÊÎÛ][^:]{1,50}\s*:\s*)(«.+»)\s*\.?\s*$")
_PURE_QUOTE_RE = re.compile(r"^\s*«.+»\s*[\.\?!…]?\s*(—\s*[^«»]{1,60})?\s*$")


def _parse_inline(text: str) -> list:
    """Markdown inline → spans PortableText avec marks ['strong']/['em']."""
    spans, pos = [], 0
    for m in _INLINE_PAT.finditer(text):
        if m.start() > pos:
            spans.append({"_type": "span", "text": text[pos:m.start()], "marks": []})
        tok = m.group(0)
        if tok.startswith("**"):
            spans.append({"_type": "span", "text": tok[2:-2], "marks": ["strong"]})
        else:
            spans.append({"_type": "span", "text": tok[1:-1], "marks": ["em"]})
        pos = m.end()
    if pos < len(text):
        spans.append({"_type": "span", "text": text[pos:], "marks": []})
    return spans or [{"_type": "span", "text": text, "marks": []}]


def md_to_portable_text(md: str) -> list:
    """Convertit Markdown en Portable Text pour Emdash.
    Préserve **bold** et *italic* via marks. Ignore le H1 du corps (emdash affiche
    déjà data.title comme titre de page → évite le doublon de titre)."""
    blocks = []
    lines = md.strip().split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("# "):
            i += 1  # skip : emdash affiche déjà data.title
            continue
        if re.fullmatch(r"-{3,}", line):
            i += 1  # règle horizontale markdown → ignorée (pas de divider PortableText)
            continue
        if line.startswith("## "):
            blocks.append({"_type": "block", "style": "h2",
                           "children": _parse_inline(line[3:].strip())})
        elif line.startswith("### "):
            blocks.append({"_type": "block", "style": "h3",
                           "children": _parse_inline(line[4:].strip())})
        elif line.startswith("- ") or line.startswith("* "):
            while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")):
                item = lines[i].strip()[2:]
                blocks.append({"_type": "block", "style": "normal", "listItem": "bullet",
                               "children": _parse_inline(item)})
                i += 1
            continue
        else:
            # Détection citation pour stylage blockquote
            m_lq = _LABEL_QUOTE_RE.match(line)
            if m_lq:
                label = m_lq.group(1).rstrip(": ").strip()
                quote = m_lq.group(2).strip()
                blocks.append({"_type": "block", "style": "normal",
                               "children": [{"_type": "span", "text": label, "marks": ["strong"]}]})
                blocks.append({"_type": "block", "style": "blockquote",
                               "children": [{"_type": "span", "text": quote, "marks": []}]})
            elif _PURE_QUOTE_RE.match(line):
                blocks.append({"_type": "block", "style": "blockquote",
                               "children": _parse_inline(line)})
            else:
                blocks.append({"_type": "block", "style": "normal",
                               "children": _parse_inline(line)})
        i += 1
    return blocks


def publish_lcr(title: str, slug: str, content_md: str, keyword: str, env: dict,
                image_url: str | None = None) -> str:
    """Publie un article sur LCR via Emdash API. `image_url` (si fourni) devient
    l'image OG/featured dans seo.image."""
    token = env["EMDASH_API_TOKEN"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Origin": "http://localhost:4321",
    }

    # Extraire excerpt (2ème paragraphe)
    paras = [p.strip() for p in content_md.split("\n\n") if p.strip() and not p.startswith("#")]
    excerpt = re.sub(r"\*+", "", paras[0])[:200] if paras else f"Guide complet sur {keyword}"

    blocks = md_to_portable_text(content_md)

    # Schéma emdash actuel : data = {title, content} ; seo au top-level
    # avec champs {title, description, image}. excerpt/tags/keywords ne sont plus
    # stockés par le CMS — retirés du payload pour éviter "ec_posts has no column ...".
    seo: dict = {
        "title":       title[:60],
        "description": excerpt[:155],
    }
    if image_url:
        seo["image"] = image_url

    payload = {
        "slug":   slug,
        "status": "draft",
        "data": {
            "title":   title,
            "content": blocks,
        },
        "seo": seo,
    }

    # Créer
    r = requests.post(
        "http://localhost:4321/_emdash/api/content/posts",
        headers=headers, json=payload, timeout=15,
    )
    r.raise_for_status()
    post_id = r.json()["data"]["item"]["id"]
    print(f"  Draft créé: {post_id}")

    # Publier
    r2 = requests.post(
        f"http://localhost:4321/_emdash/api/content/posts/{post_id}/publish",
        headers=headers, timeout=10,
    )
    r2.raise_for_status()
    url = f"https://blog.leclientroi.com/posts/{slug}"
    print(f"  Publié: {url}")
    return url


def publish_mkd(title: str, slug: str, content_md: str, keyword: str, env: dict) -> str:
    """Publie un article sur MKD via WordPress REST API."""
    import base64
    import html

    auth = base64.b64encode(f"{env['WP_USERNAME']}:{env['WP_APP_PASSWORD']}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}

    # Convertir MD en HTML simple
    content_html = content_md
    content_html = re.sub(r"^# (.+)$", r"", content_html, flags=re.MULTILINE)  # retirer H1
    content_html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", content_html, flags=re.MULTILINE)
    content_html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", content_html, flags=re.MULTILINE)
    content_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content_html)
    content_html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content_html)
    content_html = re.sub(r"^- (.+)$", r"<li>\1</li>", content_html, flags=re.MULTILINE)
    content_html = re.sub(r"(<li>.*</li>\n?)+", lambda m: f"<ul>{m.group()}</ul>", content_html)
    paras = [p.strip() for p in content_html.split("\n\n") if p.strip() and not p.startswith("<h")]
    content_html = "\n\n".join(
        p if p.startswith("<") else f"<p>{p}</p>" for p in paras
    )

    payload = {
        "title":   title,
        "slug":    slug,
        "content": content_html,
        "status":  "publish",
        "excerpt": re.sub(r"<[^>]+>", "", content_html)[:200],
    }

    r = requests.post(
        f"{env['WP_SITE_URL']}/wp-json/wp/v2/posts",
        headers=headers, json=payload, timeout=15,
    )
    r.raise_for_status()
    link = r.json().get("link", f"https://mkdgroupe.com/{slug}")
    print(f"  Publié WP: {link}")
    return link


# ── Logging ───────────────────────────────────────────────────────────────────

def log_published(site: str, title: str, slug: str, url: str, keyword: str, source: str):
    """Logue l'article dans memory/{site}/articles-published.md."""
    pub_file = MEMORY_DIR / site / "articles-published.md"
    pub_file.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    line = f"| {today} | {slug} | {title[:50]} | {keyword} | {source} | {url} |\n"
    if not pub_file.exists():
        pub_file.write_text("| Date | Slug | Titre | Keyword | Source | URL |\n|------|------|-------|---------|--------|-----|\n")
    with open(pub_file, "a") as f:
        f.write(line)


# ── Main ──────────────────────────────────────────────────────────────────────

def run(site: str, dry_run: bool = True, force_keyword: str = None):
    env = load_env()
    site_cfg = SITES[site]
    now = datetime.now(timezone.utc)
    print(f"[content_agent] Site: {site.upper()} — {'DRY-RUN' if dry_run else 'LIVE'} — {now.isoformat()}")

    # 1. Articles déjà publiés
    published = get_published_slugs(site, env)
    print(f"  {len(published)} articles déjà publiés")

    # 2. Choisir le sujet
    if force_keyword:
        topic = {
            "keyword":   force_keyword,
            "volume":    0, "kd": 0,
            "source":    "manual",
            "slug_hint": force_keyword.lower().replace(" ", "-")[:60],
        }
    else:
        topic = choose_topic(site, published)

    if not topic:
        print("  Aucun sujet disponible — tous les mots-clés déjà couverts")
        return

    keyword  = topic["keyword"]
    slug     = _slugify(topic.get("slug_hint") or keyword)
    print(f"  Sujet choisi: '{keyword}' (source: {topic['source']}, vol: {topic.get('volume',0)}, KD: {topic.get('kd','?')})")

    if dry_run:
        print(f"  DRY-RUN — slug: {slug} — pas de génération ni publication")
        return

    # 3. Générer
    print(f"  Génération article...")
    try:
        article = generate_article(topic, site, env)
        title   = article["title"]
        print(f"  Titre: {title} ({len(article['content_md'])} chars, {article['output_tok']} tokens)")
    except Exception as e:
        print(f"  ERREUR génération: {e}")
        return

    # 4. Publier
    print(f"  Publication sur {site.upper()}...")
    try:
        if site == "lcr":
            url = publish_lcr(title, slug, article["content_md"], keyword, env)
        else:
            url = publish_mkd(title, slug, article["content_md"], keyword, env)
    except Exception as e:
        print(f"  ERREUR publication: {e}")
        return

    # 5. Logger le coût
    try:
        sys.path.insert(0, str(BASE_DIR))
        from scripts.cost_tracker import track
        track(
            action=f"article-{site}-{slug[:30]}",
            module="content",
            model="deepseek-chat",
            input_tok=article["input_tok"],
            output_tok=article["output_tok"],
            note=f"{site.upper()} · {keyword} · {url}",
        )
    except Exception as e:
        print(f"  ⚠ cost_tracker: {e}")

    # 6. Logger dans published.md
    log_published(site, title, slug, url, keyword, topic["source"])

    print(f"[content_agent] Terminé — {url}")
    return {"site": site, "title": title, "url": url, "keyword": keyword}


# ── Mode agentique (boucle agent_core) ──────────────────────────────────────
# Au lieu du choose_topic() heuristique, on délègue la décision à
# agent_core.run_cycle qui : observe GSC/GA4, recall les actions passées
# (skills/content-writer.md comme policy), demande à DeepSeek un plan
# {action_type:'write_article', target:'<mot-clé>'}, puis appelle writer_fn ici
# pour exécuter generate + publish. Chaque action est tracée dans agent_actions
# → evaluable plus tard par agent_core.evaluate().

def _agentic_writer(item: dict, snapshot: dict, *, site: str, env: dict, dry_run: bool):
    """Exécute un item du plan agentique : write_article sur le keyword cible."""
    if item.get("action_type") != "write_article":
        print(f"  [agentic] action_type non géré: {item.get('action_type')!r} — skip")
        return
    keyword = item.get("target") or (item.get("tags") or {}).get("keyword")
    if not keyword:
        raise ValueError("plan sans target/keyword")
    slug = _slugify(keyword)
    topic = {"keyword": keyword, "volume": 0, "kd": 0, "source": "agentic",
             "slug_hint": slug}
    if dry_run:
        print(f"  [agentic] DRY-RUN keyword={keyword!r} slug={slug}")
        item["dry_run"] = True
        return
    article = generate_article(topic, site, env)
    title = article["title"]

    # Note : la génération d'image header est déléguée à l'agent graphiste
    # (scripts/graphiste_agent.py), qui tournera en post-traitement via son
    # propre cron. Ici on publie SANS seo.image — graphiste posera l'image plus tard.
    url = (publish_lcr(title, slug, article["content_md"], keyword, env)
           if site == "lcr"
           else publish_mkd(title, slug, article["content_md"], keyword, env))
    try:
        sys.path.insert(0, str(BASE_DIR))
        from scripts.cost_tracker import track
        track(action=f"article-{site}-{slug[:30]}", module="content",
              model="deepseek-chat", input_tok=article["input_tok"],
              output_tok=article["output_tok"],
              note=f"{site.upper()} · {keyword} · {url}")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ cost_tracker: {e}")
    log_published(site, title, slug, url, keyword, "agentic")
    item["url"], item["title"], item["slug"] = url, title, slug


def run_agentic(site: str, dry_run: bool = True) -> dict:
    """Variante agentique : pilotée par agent_core (observe→recall→decide→act)."""
    from functools import partial
    env = load_env()
    print(f"[content_agent agentic] Site: {site.upper()} — "
          f"{'DRY-RUN' if dry_run else 'LIVE'}")
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from agent_core import run_cycle
    writer = partial(_agentic_writer, site=site, env=env, dry_run=dry_run)
    result = run_cycle(agent="content-writer", site=site,
                       sources=("gsc", "ga4", "ahrefs"), writer_fn=writer,
                       allowed_actions=["write_article"])
    print(json.dumps(result, ensure_ascii=False, default=str))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site",    choices=["lcr", "mkd", "both"], default="lcr")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--live",    action="store_true")
    parser.add_argument("--keyword", help="Forcer un mot-clé spécifique")
    parser.add_argument("--agentic", action="store_true",
                        help="Passe par la boucle agent_core (observe/recall/decide/act)")
    args = parser.parse_args()

    dry = not args.live

    sites = ["lcr", "mkd"] if args.site == "both" else [args.site]
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from modules_backend import is_enabled
    except Exception:
        is_enabled = lambda *_: True

    for s in sites:
        if not is_enabled(s, "articles"):
            print(f"[content_agent] {s}: module 'articles' désactivé → skip")
            continue
        if args.agentic:
            run_agentic(s, dry_run=dry)
        else:
            run(s, dry_run=dry, force_keyword=args.keyword)
