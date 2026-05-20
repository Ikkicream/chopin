#!/usr/bin/env python3
"""
newsletter.py — Génération et envoi de newsletters mensuelles via Resend.

Sites :
  LCR — leclientroi.com  — SMS marketing & local
  MKD — mkdgroupe.com    — Data B2B, RGPD, RCS

Usage:
  python3 scripts/newsletter.py --site lcr --dry-run
  python3 scripts/newsletter.py --site mkd --live
  python3 scripts/newsletter.py --site both --preview   # génère HTML seulement
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"
NL_DIR   = BASE_DIR / "memory" / "newsletters"
NL_DIR.mkdir(parents=True, exist_ok=True)

RESEND_API = "https://api.resend.com"

SITES = {
    "lcr": {
        "domain":       "leclientroi.com",
        "label":        "LeClientROI",
        "from_name":    "LeClientROI",
        "from_email":   "newsletter@leclientroi.com",
        "subject_tpl":  "SMS Marketing — Les actus du mois {month}",
        "accent":       "#0066FF",
        "audience_id":  "",  # à configurer dans Resend dashboard
        "topics":       ["sms marketing", "campagne sms", "rcs messagerie", "marketing local"],
        "cta_url":      "https://leclientroi.com",
        "cta_label":    "Découvrir nos solutions SMS",
        "footer_desc":  "La newsletter des experts en SMS marketing et communication locale.",
        "emdash_token_env": "EMDASH_API_TOKEN",
    },
    "mkd": {
        "domain":       "mkdgroupe.com",
        "label":        "MKD Groupe",
        "from_name":    "MKD Groupe",
        "from_email":   "newsletter@mkdgroupe.com",
        "subject_tpl":  "Data B2B & RGPD — Veille du mois {month}",
        "accent":       "#00C48C",
        "audience_id":  "",
        "topics":       ["rgpd", "data marketing", "prospection b2b", "rcs entreprise"],
        "cta_url":      "https://mkdgroupe.com",
        "cta_label":    "Voir nos solutions B2B",
        "footer_desc":  "La newsletter des décideurs data marketing B2B & conformité RGPD.",
        "wp_site_env":  "WP_SITE_URL",
    },
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


# ── Récupération des articles ─────────────────────────────────────────────────

def get_lcr_articles(env: dict, limit: int = 5) -> list[dict]:
    """Articles récents Emdash (LCR)."""
    token = env.get("EMDASH_API_TOKEN", "")
    if not token:
        return []
    try:
        r = requests.get(
            f"http://localhost:4321/_emdash/api/content/posts?limit={limit}&status=published",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        items = r.json().get("data", {}).get("items", [])
        articles = []
        for item in items:
            data = item.get("data", {})
            articles.append({
                "title":   data.get("title", item.get("slug", "")),
                "slug":    item.get("slug", ""),
                "excerpt": data.get("excerpt") or data.get("description") or "",
                "url":     f"https://blog.leclientroi.com/posts/{item['slug']}",
                "date":    item.get("updatedAt") or item.get("createdAt", ""),
            })
        return articles
    except Exception as e:
        print(f"  ⚠ Emdash: {e}")
        return []


def get_mkd_articles(env: dict, limit: int = 5) -> list[dict]:
    """Articles récents WordPress (MKD)."""
    import base64
    username = env.get("WP_USERNAME", "")
    password = env.get("WP_APP_PASSWORD", "")
    site_url = env.get("WP_SITE_URL", "")
    if not all([username, password, site_url]):
        return []
    try:
        auth = base64.b64encode(f"{username}:{password}".encode()).decode()
        r = requests.get(
            f"{site_url}/wp-json/wp/v2/posts?per_page={limit}&status=publish&_fields=title,slug,excerpt,link,date",
            headers={"Authorization": f"Basic {auth}"},
            timeout=8,
        )
        articles = []
        for item in r.json():
            articles.append({
                "title":   item.get("title", {}).get("rendered", ""),
                "slug":    item.get("slug", ""),
                "excerpt": item.get("excerpt", {}).get("rendered", ""),
                "url":     item.get("link", ""),
                "date":    item.get("date", ""),
            })
        return articles
    except Exception as e:
        print(f"  ⚠ WordPress: {e}")
        return []


# ── Génération HTML newsletter ────────────────────────────────────────────────

def generate_html(site_key: str, articles: list[dict], stats: dict = None) -> str:
    """Génère le HTML de la newsletter."""
    cfg = SITES[site_key]
    now = datetime.now(timezone.utc)
    month_fr = [
        "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
    ][now.month]
    month_label = f"{month_fr} {now.year}"
    accent = cfg["accent"]

    # Articles HTML
    articles_html = ""
    for art in articles[:4]:
        excerpt = art.get("excerpt", "")
        # Nettoyer les balises HTML de l'excerpt WordPress
        import re
        excerpt = re.sub(r"<[^>]+>", "", excerpt).strip()[:150]
        if excerpt:
            excerpt = f'<p style="color:#666;font-size:14px;margin:8px 0 0">{excerpt}...</p>'
        date_str = art.get("date", "")[:10] if art.get("date") else ""
        articles_html += f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:20px;margin-bottom:16px">
          <div style="font-size:11px;color:#9ca3af;margin-bottom:6px">{date_str}</div>
          <a href="{art['url']}" style="color:{accent};font-size:16px;font-weight:600;text-decoration:none;line-height:1.4">
            {art['title']}
          </a>
          {excerpt}
          <br>
          <a href="{art['url']}" style="display:inline-block;margin-top:12px;padding:6px 14px;
            background:{accent};color:#fff;border-radius:4px;font-size:12px;text-decoration:none;font-weight:600">
            Lire l'article →
          </a>
        </div>"""

    if not articles_html:
        articles_html = '<p style="color:#9ca3af;padding:20px 0">Aucun article récent disponible.</p>'

    # Stats optionnelles
    stats_html = ""
    if stats:
        stats_html = f"""
        <div style="background:#f9fafb;border-radius:8px;padding:16px;margin-bottom:24px">
          <div style="display:flex;gap:24px;flex-wrap:wrap">
            {"".join(f'<div><div style="font-size:24px;font-weight:700;color:{accent}">{v}</div><div style="font-size:11px;color:#9ca3af">{k}</div></div>' for k,v in stats.items())}
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{cfg['label']} — Newsletter {month_label}</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:system-ui,-apple-system,sans-serif">
  <div style="max-width:600px;margin:0 auto;background:#fff">

    <!-- Header -->
    <div style="background:{accent};padding:32px 40px;text-align:center">
      <div style="color:rgba(255,255,255,.7);font-size:11px;letter-spacing:2px;margin-bottom:4px">NEWSLETTER</div>
      <div style="color:#fff;font-size:26px;font-weight:700;letter-spacing:-0.5px">{cfg['label']}</div>
      <div style="color:rgba(255,255,255,.8);font-size:13px;margin-top:6px">{month_label}</div>
    </div>

    <!-- Body -->
    <div style="padding:32px 40px">

      <h2 style="font-size:20px;font-weight:700;color:#111;margin:0 0 8px">
        Bonjour,
      </h2>
      <p style="color:#4b5563;font-size:15px;line-height:1.6;margin:0 0 24px">
        Voici une sélection de nos meilleurs contenus du mois sur
        {", ".join(cfg['topics'][:3])}.
      </p>

      {stats_html}

      <!-- Articles -->
      <h3 style="font-size:14px;font-weight:600;color:#9ca3af;letter-spacing:1px;text-transform:uppercase;margin:0 0 16px">
        Articles du mois
      </h3>
      {articles_html}

      <!-- CTA -->
      <div style="text-align:center;margin:32px 0">
        <a href="{cfg['cta_url']}"
           style="display:inline-block;padding:14px 28px;background:{accent};color:#fff;
                  border-radius:6px;font-size:15px;font-weight:600;text-decoration:none">
          {cfg['cta_label']}
        </a>
      </div>

    </div>

    <!-- Footer -->
    <div style="border-top:1px solid #e5e7eb;padding:24px 40px;text-align:center">
      <p style="color:#9ca3af;font-size:12px;margin:0 0 8px">{cfg['footer_desc']}</p>
      <p style="color:#d1d5db;font-size:11px;margin:0">
        {cfg['domain']} · <a href="{{{{unsubscribe_url}}}}" style="color:#d1d5db">Se désabonner</a>
      </p>
    </div>

  </div>
</body>
</html>"""


# ── Envoi Resend ──────────────────────────────────────────────────────────────

def send_newsletter(site_key: str, html: str, env: dict, test_email: str = None) -> dict:
    """Envoie la newsletter via Resend API."""
    resend_key = env.get("RESEND_API_KEY", "")
    if not resend_key:
        raise ValueError("RESEND_API_KEY non configuré dans .env")

    cfg = SITES[site_key]
    now = datetime.now(timezone.utc)
    month_fr = ["","Janvier","Février","Mars","Avril","Mai","Juin",
                "Juillet","Août","Septembre","Octobre","Novembre","Décembre"][now.month]
    subject = cfg["subject_tpl"].format(month=f"{month_fr} {now.year}")

    payload = {
        "from":    f"{cfg['from_name']} <{cfg['from_email']}>",
        "subject": subject,
        "html":    html,
    }

    if test_email:
        # Envoi test à une seule adresse
        payload["to"] = [test_email]
        print(f"  → Envoi test à {test_email}")
    else:
        # Envoi à l'audience Resend
        audience_id = cfg.get("audience_id", "")
        if not audience_id:
            raise ValueError(f"audience_id non configuré pour {site_key} dans SITES config")
        payload["to"] = [f"audience:{audience_id}"]
        print(f"  → Envoi à audience {audience_id}")

    r = requests.post(
        f"{RESEND_API}/emails",
        headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )

    if r.status_code not in (200, 201):
        raise ValueError(f"Resend error {r.status_code}: {r.text}")

    return r.json()


def get_resend_audiences(env: dict) -> list[dict]:
    """Liste les audiences Resend existantes."""
    resend_key = env.get("RESEND_API_KEY", "")
    if not resend_key:
        return []
    try:
        r = requests.get(
            f"{RESEND_API}/audiences",
            headers={"Authorization": f"Bearer {resend_key}"},
            timeout=10,
        )
        return r.json().get("data", [])
    except Exception as e:
        print(f"  ⚠ Resend audiences: {e}")
        return []


def create_resend_audience(name: str, env: dict) -> dict:
    """Crée une audience Resend."""
    resend_key = env.get("RESEND_API_KEY", "")
    r = requests.post(
        f"{RESEND_API}/audiences",
        headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
        json={"name": name},
        timeout=10,
    )
    return r.json()


def add_contact_to_audience(audience_id: str, email: str, first_name: str,
                             last_name: str, env: dict) -> dict:
    """Ajoute un contact à une audience Resend."""
    resend_key = env.get("RESEND_API_KEY", "")
    r = requests.post(
        f"{RESEND_API}/audiences/{audience_id}/contacts",
        headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
        json={"email": email, "first_name": first_name, "last_name": last_name, "unsubscribed": False},
        timeout=10,
    )
    return r.json()


# ── Main ──────────────────────────────────────────────────────────────────────

def run(site_key: str, mode: str = "dry-run", test_email: str = None):
    """
    mode: dry-run (génère + sauvegarde HTML) | preview (stdout HTML) | live (envoie)
    """
    env = load_env()
    cfg = SITES[site_key]
    now = datetime.now(timezone.utc)
    print(f"[newsletter] Site: {site_key.upper()} — mode: {mode} — {now.isoformat()}")

    # 1. Articles
    print("[newsletter] Récupération des articles...")
    if site_key == "lcr":
        articles = get_lcr_articles(env)
    else:
        articles = get_mkd_articles(env)
    print(f"  → {len(articles)} article(s)")

    # 2. Génération HTML
    print("[newsletter] Génération HTML...")
    html = generate_html(site_key, articles)

    # 3. Sauvegarde
    out_file = NL_DIR / f"{site_key}-{now.strftime('%Y-%m')}.html"
    out_file.write_text(html, encoding="utf-8")
    print(f"  → Sauvegardé: {out_file}")

    if mode == "preview":
        print(html)
        return

    if mode == "dry-run":
        print(f"[newsletter] DRY-RUN — HTML généré ({len(html)} chars). Pas d'envoi.")
        print(f"  Voir: {out_file}")
        return

    # 4. Envoi live
    if mode == "live":
        resend_key = env.get("RESEND_API_KEY", "")
        if not resend_key:
            print("[newsletter] ⚠ RESEND_API_KEY manquant — configurez .env puis relancez")
            return
        print("[newsletter] Envoi via Resend...")
        try:
            result = send_newsletter(site_key, html, env, test_email=test_email)
            print(f"  → OK: id={result.get('id')}")

            # Logger le coût (Resend = ~0.001$ par email — estimer 500 contacts)
            sys.path.insert(0, str(BASE_DIR))
            from scripts.cost_tracker import track
            track(
                action=f"newsletter-{site_key}-{now.strftime('%Y-%m')}",
                module="newsletter",
                model="unsplash",  # pas de modèle AI — coût API Resend (flat)
                input_tok=0,
                output_tok=0,
                note=f"{site_key.upper()} newsletter {now.strftime('%B %Y')} — {len(articles)} articles",
            )
        except Exception as e:
            print(f"  ⚠ Erreur envoi: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site",       choices=["lcr", "mkd", "both"], default="lcr")
    parser.add_argument("--mode",       choices=["dry-run", "preview", "live"], default="dry-run")
    parser.add_argument("--test-email", help="Envoyer en test à cet email uniquement")
    parser.add_argument("--audiences",  action="store_true", help="Lister les audiences Resend")
    parser.add_argument("--setup",      action="store_true", help="Créer les audiences Resend")
    args = parser.parse_args()

    env = load_env()

    if args.audiences:
        print("[newsletter] Audiences Resend :")
        for a in get_resend_audiences(env):
            print(f"  - {a.get('name')} (id: {a.get('id')}, contacts: {a.get('contact_count','?')})")
        sys.exit(0)

    if args.setup:
        resend_key = env.get("RESEND_API_KEY", "")
        if not resend_key:
            print("⚠ RESEND_API_KEY manquant")
            sys.exit(1)
        print("[newsletter] Création des audiences Resend...")
        for sk in ["lcr", "mkd"]:
            name = f"{SITES[sk]['label']} Newsletter"
            result = create_resend_audience(name, env)
            print(f"  {sk.upper()}: {result}")
        sys.exit(0)

    sites_to_run = ["lcr", "mkd"] if args.site == "both" else [args.site]
    for s in sites_to_run:
        run(s, mode=args.mode, test_email=args.test_email)
