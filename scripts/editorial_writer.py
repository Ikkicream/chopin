#!/usr/bin/env python3
"""
editorial_writer.py v2 — Pipeline éditorial complet intégrant les standards Paperclip.

Flow: SEO Brief → Rédaction → Internal Linking → QC /100 → Ready for review
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rag_query import get_site_context as rag_get_context
from llm_call import call_llm
import requests

BASE_DIR = Path(__file__).parent.parent
QUEUE_FILE = BASE_DIR / "memory" / "editorial" / "articles-queue.json"
SEO_DIR = BASE_DIR / "memory" / "seo"

# Load env
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip("'\""))

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
UNSPLASH_LCR_KEY = os.environ.get("UNSPLASH_LCR_ACCESS_KEY", "")
UNSPLASH_MKD_KEY = os.environ.get("UNSPLASH_MKD_ACCESS_KEY", "")

SITE_CONFIG = {
    "lcr": {
        "label": "LeClientROI",
        "domain": "leclientroi.com",
        "tone": "Expert mais accessible. Parle aux gérants de TPE/PME. Exemples concrets, chiffres français. Ton direct sans jargon excessif.",
        "audience": "Gérants de commerces locaux (restaurants, coiffeurs, immobilier, artisans) en France",
        "cta_guides": "https://leclientroi.com/guides",
        "cta_leadmagnet": "https://ik.imagekit.io/rgpdsimplement/Libreblanc.pdf",
        "unsplash_key": "UNSPLASH_LCR_ACCESS_KEY",
    },
    "mkd": {
        "label": "MKDgroupe",
        "domain": "mkdgroupe.com",
        "tone": "Professionnel B2B, factuel. Chiffres et ROI. Vocabulaire data marketing / RGPD. Autorité et expertise.",
        "audience": "Directeurs marketing, DPO, responsables data d'entreprises B2B en France",
        "cta_guides": "https://mkdgroupe.com/contact",
        "cta_leadmagnet": None,
        "unsplash_key": "UNSPLASH_MKD_ACCESS_KEY",
    },
}


def load_queue():
    if QUEUE_FILE.exists():
        return json.loads(QUEUE_FILE.read_text())
    return []

def save_queue(queue):
    QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False))


def call_deepseek(prompt, max_tokens=8000):
    """Call DeepSeek API."""
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    r = requests.post("https://api.deepseek.com/chat/completions", json={
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }, headers=headers, timeout=180)
    r.raise_for_status()
    result = r.json()
    return result["choices"][0]["message"]["content"], result.get("usage", {})


def call_haiku(prompt, max_tokens=2000):
    """Wrapper retrocompat → DeepSeek (cf. llm_call.py)."""
    return call_llm(prompt, max_tokens=max_tokens, module="editorial-writer", action="brief-or-revision")


# ─── STEP 1: SEO Brief (Haiku) ───────────────────────────────────────────────

def generate_seo_brief(title, keyword, site):
    """Generate a complete SEO brief: H2/H3 structure, internal links, meta."""
    cfg = SITE_CONFIG[site]

    # Load existing articles for internal linking
    ahrefs = {}
    f = SEO_DIR / f"{site}-ahrefs-latest.json"
    if f.exists():
        ahrefs = json.loads(f.read_text())

    prompt = f"""Tu es un SEO Strategist expert. Génère un brief SEO complet pour l'article suivant.

SITE : {cfg['label']} ({cfg['domain']})
TITRE H1 : {title}
MOT-CLÉ PRINCIPAL : {keyword}
AUDIENCE : {cfg['audience']}

DONNÉES AHREFS DU SITE :
- DR : {ahrefs.get('domain_rating', '?')}
- Keywords actuels : {json.dumps(ahrefs.get('top_keywords', [])[:5], ensure_ascii=False)}

Génère un brief structuré en JSON :
{{
  "h1": "{title}",
  "meta_title": "max 60 chars avec le keyword",
  "meta_description": "max 155 chars, descriptif et engageant",
  "structure": [
    {{"level": "h2", "title": "Titre H2 avec keyword ou variation", "notes": "Ce que cette section doit couvrir"}},
    {{"level": "h3", "title": "Sous-section si pertinent", "notes": "Détail"}},
  ],
  "secondary_keywords": ["kw1", "kw2", "kw3"],
  "semantic_terms": ["terme1", "terme2", "terme3"],
  "word_count_target": 1000,
  "internal_links_to_create": [
    {{"anchor": "texte d'ancre", "target_topic": "sujet de l'article cible existant"}}
  ],
  "schema_type": "Article ou HowTo ou FAQ",
  "angle": "L'angle unique à prendre pour se différencier des concurrents"
}}"""

    text = call_haiku(prompt)
    # Parse JSON
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


# ─── STEP 2: Content Writing (DeepSeek) ──────────────────────────────────────

def write_article(title, keyword, seo_brief, site, site_context_snippet=""):
    """Write the full article following the SEO brief and Paperclip standards."""
    cfg = SITE_CONFIG[site]
    structure = seo_brief.get("structure", [])
    structure_text = "\n".join([f"{'##' if s['level']=='h2' else '###'} {s['title']}" + (f" — {s['notes']}" if s.get('notes') else "") for s in structure])
    secondary_kw = ", ".join(seo_brief.get("secondary_keywords", []))
    semantic = ", ".join(seo_brief.get("semantic_terms", []))

    prompt = f"""Tu es un rédacteur SEO expert. Rédige un article complet en français.

═══ BRIEF SEO ═══
TITRE H1 : {title}
MOT-CLÉ PRINCIPAL : {keyword}
MOTS-CLÉS SECONDAIRES : {secondary_kw}
TERMES SÉMANTIQUES : {semantic}
ANGLE : {seo_brief.get('angle', 'Apporter une valeur unique')}
LONGUEUR CIBLE : {seo_brief.get('word_count_target', 1000)} mots

═══ STRUCTURE IMPOSÉE ═══
{structure_text}

═══ STANDARDS D'ÉCRITURE (NON NÉGOCIABLES) ═══

STYLE :
- Ton : {cfg['tone']}
- Français clair et confiant. Voix active. Varier la longueur des phrases.
- Ouvrir avec un HOOK puissant (question, fait marquant, affirmation audacieuse).
- JAMAIS de filler : "Dans cet article...", "Il est important de noter...", "En conclusion..."
- Paragraphes de 3-5 phrases MAXIMUM.

FORMATTING :
- **Gras** sur les phrases fortes et claims clés (PAS juste les keywords) — minimum 6 occurrences
- *Italique* pour nuances et termes techniques — minimum 3 occurrences
- 1 citation (blockquote >) d'un professionnel fictif mais crédible
- 1 liste à puces (minimum 5 items) avec des éléments actionnables
- 1 liste numérotée (étapes séquentielles) si pertinent

SEO :
- Le keyword DOIT être dans les 100 premiers mots
- Le keyword DOIT apparaître dans au moins 2 des H2
- Les keywords secondaires et termes sémantiques doivent être utilisés naturellement — JAMAIS de stuffing
- Respecter EXACTEMENT la structure H2/H3 du brief

LIENS INTERNES À INTÉGRER NATURELLEMENT :
{json.dumps(seo_brief.get('internal_links_to_create', []), ensure_ascii=False)}

APPEL À L'ACTION (fin d'article) :
- CTA clair orienté conversion vers {cfg['cta_guides']}
- Terminer avec une phrase mémorable, pas un résumé

═══ FORMAT DE SORTIE ═══
Markdown pur. Pas de frontmatter. Pas de HTML (sauf si lien interne).
Le H1 ne doit PAS être inclus (il sera ajouté automatiquement).
IMPORTANT : Tu DOIS écrire TOUTES les sections du brief sans exception. Ne jamais couper un article au milieu.
Terminer OBLIGATOIREMENT par une conclusion avec CTA.

Commencer directement par le paragraphe d'accroche.
"""

    content, tokens = call_deepseek(prompt, max_tokens=8000)
    return content, tokens


# ─── STEP 3: Quality Check (Haiku) ───────────────────────────────────────────

def quality_check(article_md, keyword, seo_brief):
    """Score /100 on 5 dimensions like Paperclip Quality Editor."""
    prompt = f"""Tu es un Quality Editor strict. Note cet article sur 100 points.

MOT-CLÉ CIBLE : {keyword}
STRUCTURE ATTENDUE : {json.dumps([s['title'] for s in seo_brief.get('structure', [])], ensure_ascii=False)}

ARTICLE :
---
{article_md[:3000]}
---

Score sur 5 dimensions :
1. SUBSTANCE & PROFONDEUR (25 pts) : Va au-delà du surface ? Exemples concrets ? Angle unique ?
2. EXACTITUDE & CRÉDIBILITÉ (20 pts) : Pas de stats inventées ? Noms corrects ? Pas de phrases vagues ?
3. LISIBILITÉ & FLOW (20 pts) : Clair, bien organisé ? Transitions fluides ? Ton adapté ?
4. ALIGNEMENT SEO (20 pts) : Keyword dans intro + H2 + conclusion ? Structure respectée ? Secondary KW naturels ?
5. ENGAGEMENT & VALEUR (15 pts) : Hook efficace ? CTA clair ? Un lecteur réel lirait-il ça ?

Seuil : 70/100 minimum.

Réponds en JSON :
{{
  "score": nombre_total,
  "dimensions": {{
    "substance": {{"score": X, "max": 25, "notes": "..."}},
    "accuracy": {{"score": X, "max": 20, "notes": "..."}},
    "readability": {{"score": X, "max": 20, "notes": "..."}},
    "seo": {{"score": X, "max": 20, "notes": "..."}},
    "engagement": {{"score": X, "max": 15, "notes": "..."}}
  }},
  "issues": ["problème 1", "problème 2"],
  "strengths": ["point fort 1", "point fort 2"],
  "verdict": "APPROVED" ou "REVISION_NEEDED"
}}"""

    text = call_haiku(prompt, max_tokens=1500)
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


# ─── STEP 4: Image sourcing (Unsplash) ───────────────────────────────────────

def find_image(keyword, site):
    """Find a relevant image on Unsplash."""
    key = os.environ.get(SITE_CONFIG[site]["unsplash_key"], "")
    if not key:
        return None

    # Translate keyword to English for better Unsplash results
    kw_map = {"sms": "sms marketing", "marketing": "digital marketing", "restaurant": "restaurant",
              "b2b": "business meeting", "rgpd": "data privacy", "prospection": "sales",
              "geolocalise": "location map", "rcs": "mobile messaging"}
    search_term = kw_map.get(keyword.split()[0].lower(), keyword)

    try:
        r = requests.get("https://api.unsplash.com/search/photos", params={
            "query": search_term, "per_page": 3, "orientation": "landscape"
        }, headers={"Authorization": f"Client-ID {key}"}, timeout=10)
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                photo = results[0]
                # Trigger download (Unsplash ToS)
                requests.get(photo["links"]["download_location"],
                           headers={"Authorization": f"Client-ID {key}"}, timeout=5)
                return {
                    "url": photo["urls"]["regular"],
                    "thumb": photo["urls"]["small"],
                    "alt": f"{keyword} - {photo.get('description', '')}",
                    "credit": f"Photo by {photo['user']['name']} on Unsplash",
                    "credit_url": photo["user"]["links"]["html"],
                }
    except Exception:
        pass
    return None


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", help="Article ID to write")
    args = parser.parse_args()

    queue = load_queue()
    art = None
    for a in queue:
        if args.id and a["id"] == args.id:
            art = a
            break
        elif not args.id and a["status"] == "approved":
            art = a
            break

    if not art:
        print("No approved article found")
        sys.exit(0)

    title = art["proposal"]["title"]
    keyword = art["proposal"]["keyword"]
    site = art["site"]
    print(f"[editorial_writer v2] {art['id']} — {title}")

    # Load site context from RAG knowledge base
    site_context = rag_get_context(site, keyword + " " + title, max_chars=2000)
    print(f"  RAG context: {len(site_context)} chars loaded for {site}")

    # Update status
    art["status"] = "writing"
    art["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_queue(queue)

    # STEP 1: SEO Brief
    print("  Step 1: SEO Brief (Haiku)...")
    try:
        seo_brief = generate_seo_brief(title, keyword, site)
        print(f"    Structure: {len(seo_brief.get('structure', []))} sections")
        print(f"    Meta title: {seo_brief.get('meta_title', '?')[:50]}")
    except Exception as e:
        print(f"    ERROR: {e} — using default brief")
        seo_brief = {
            "structure": [
                {"level": "h2", "title": "Pourquoi " + keyword, "notes": "Contexte et enjeux"},
                {"level": "h2", "title": "Comment mettre en place " + keyword, "notes": "Étapes concrètes"},
                {"level": "h2", "title": "Les erreurs à éviter", "notes": "Pièges courants"},
                {"level": "h2", "title": "Exemples et cas concrets", "notes": "Illustrations"},
                {"level": "h2", "title": "Conclusion et prochaines étapes", "notes": "CTA"},
            ],
            "secondary_keywords": [],
            "semantic_terms": [],
            "word_count_target": 1200,
            "angle": "Guide pratique et actionnable",
        }

    # STEP 2: Content Writing
    print("  Step 2: Rédaction (DeepSeek)...")
    try:
        content_md, tokens = write_article(title, keyword, seo_brief, site, site_context[:300] if site_context else "")
        word_count = len(content_md.split())
        print(f"    {word_count} mots, {tokens.get('total_tokens', 0)} tokens")
    except Exception as e:
        print(f"    ERROR: {e}")
        art["status"] = "revision_needed"
        art["human_notes"] = f"Erreur rédaction: {e}"
        save_queue(queue)
        sys.exit(1)

    # STEP 2b: Internal Linking (Haiku)
    print('  Step 2b: Internal Linking (Haiku)...')
    try:
        import subprocess
        result = subprocess.run(
            ['python3', 'scripts/internal_linking_agent.py', '--id', art['id'], '--mode', 'pre'],
            capture_output=True, text=True, cwd=str(BASE_DIR), timeout=60
        )
        # Reload queue to get updated article with links
        queue = load_queue()
        art = next((a for a in queue if a['id'] == art['id']), art)
        content_md = art.get('article', {}).get('markdown', content_md)
        links_applied = art.get('article', {}).get('internal_links_applied', 0)
        print(f'    {links_applied} liens internes ajoutés')
    except Exception as e:
        print(f'    Internal linking error: {e}')

    # STEP 3: Quality Check
    print("  Step 3: Quality Check (Haiku)...")
    try:
        qc = quality_check(content_md, keyword, seo_brief)
        print(f"    Score: {qc['score']}/100 — {qc.get('verdict', '?')}")
    except Exception as e:
        print(f"    QC error: {e}")
        qc = {"score": 0, "issues": [str(e)], "verdict": "ERROR"}

    # STEP 4: Image
    print("  Step 4: Image (Unsplash)...")
    image = find_image(keyword, site)
    if image:
        print(f"    Found: {image['url'][:60]}...")
    else:
        print("    No image found")

    # Save everything to queue
    art["article"] = {
        "markdown": content_md,
        "word_count": word_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "deepseek-chat",
        "tokens": tokens,
        "seo_brief": seo_brief,
        "image": image,
    }
    art["qc_report"] = qc
    art["status"] = "ready_to_review" if qc.get("score", 0) >= 70 else "revision_needed"
    art["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_queue(queue)

    print(f"  Status: {art['status']}")
    print("  Done!")


if __name__ == "__main__":
    main()
