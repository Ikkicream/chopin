#!/usr/bin/env python3
"""
god_mode_templates.py — Génération de templates email cold via DeepSeek.

Pour chaque (site, secteur), génère 1 template avec:
  - subject (variable: {{firstName}}, {{field1}})
  - raw text (avec variables Emelia)
  - HTML (avec signature Juliette injectée)
"""

import os
import re
import requests
from pathlib import Path

import god_mode_backend as gm

BASE_DIR = Path(__file__).parent.parent
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip("'\""))

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# Signature Juliette — EN TEXTE, plus en image.
# Le guide de délivrabilité de Maildoso demande une signature sans photo, sans lien et
# sans domaine. L'ancienne version était une image distante hébergée sur S3 : chaque
# email chargeait un fichier sur un domaine tiers, ce qui se voit et ne rapportait rien
# qu'un texte ne fasse. Le lien de désinscription reste : il est obligatoire.
SIGNATURE_HTML = (
    '<p>Juliette<br>LeClientROI</p>'
    '<p><a href="{{UNSUBSCRIBE_LINK}}" rel="noopener noreferrer" target="_blank">'
    "Si vous ne souhaitez plus recevoir d'email de ma part, cliquez ici"
    "</a></p>"
)

# Contexte par site (repris de editorial_writer.SITE_CONFIG)
SITE_CONTEXT = {
    "lcr": {
        "label": "LeClientROI",
        "domain": "leclientroi.com",
        "tone": "Expert mais accessible. Parle aux gérants de TPE/PME. Exemples concrets, chiffres français. Direct sans jargon excessif.",
        "audience": "Gérants de commerces locaux (restaurants, coiffeurs, immobilier, artisans) en France",
        "product": "SMS marketing géolocalisé pour booster les ventes locales — campagnes ciblées dans un rayon autour du commerce",
        "value_prop": "+30% de réservations/visites grâce au SMS géolocalisé",
    },
    "mkd": {
        "label": "MKDgroupe",
        "domain": "mkdgroupe.com",
        "tone": "Professionnel B2B, factuel. Chiffres et ROI. Vocabulaire data marketing. Autorité et expertise.",
        "audience": "Directeurs marketing, DPO, responsables data d'entreprises B2B",
        "product": "Solutions data marketing B2B conformes RGPD",
        "value_prop": "Enrichissement et activation de données B2B qualifiées",
    },
}

SECTOR_LABELS = {
    "immobilier": "agents immobiliers",
    "restaurant": "restaurateurs",
    "garagiste": "garagistes / mécaniciens",
    "coiffeur": "coiffeurs / salons de coiffure",
    "retail": "commerçants / retailers",
    "artisan": "artisans (plombiers, électriciens, menuisiers...)",
}


def call_deepseek(prompt: str, max_tokens: int = 1500) -> str:
    if not DEEPSEEK_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY manquante")
    r = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.5,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def build_prompt(site_code: str, sector: str) -> str:
    ctx = SITE_CONTEXT[site_code]
    sector_label = SECTOR_LABELS.get(sector, sector)
    return f"""Tu es un expert en cold email B2B pour le marché français.

CONTEXTE:
- Émetteur: Juliette, commerciale chez {ctx["label"]} ({ctx["domain"]})
- Produit: {ctx["product"]}
- Promesse: {ctx["value_prop"]}
- Cible de cette campagne: {sector_label} en France
- Ton: {ctx["tone"]}

OBJECTIF:
Générer 1 template d'email cold OUTREACH ultra-court (8-12 lignes max) en français, optimisé pour les {sector_label}.

CONTRAINTES STRICTES:
- Subject line: 5-8 mots, intriguant, sans clickbait, pas de "RE:" ou "FW:"
- Corps: tutoiement ou vouvoiement adapté, ton humain, NE PAS commencer par "J'espère que..."
- Variables Emelia OBLIGATOIRES dans le corps: {{{{firstName}}}}, {{{{field1}}}}, {{{{field2}}}}
- 1 question ouverte à la fin pour engager la réponse
- AUCUNE signature dans ton output (sera ajoutée séparément)
- AUCUN lien d'unsubscribe dans ton output
- Ne PAS mentionner "cold email" ni "prospection"

FORMAT DE SORTIE EXACT (rien d'autre):

SUBJECT: <ligne d'objet>

BODY:
<corps de l'email en texte brut, avec les variables Emelia>"""


def parse_response(text: str) -> tuple[str, str]:
    m_subj = re.search(r"^SUBJECT:\s*(.+?)$", text, re.M | re.I)
    m_body = re.search(r"^BODY:\s*(.+)$", text, re.M | re.I | re.S)
    subject = m_subj.group(1).strip() if m_subj else ""
    body = m_body.group(1).strip() if m_body else text.strip()
    return subject, body


def text_to_html(body: str) -> str:
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    html_paragraphs = []
    for p in paragraphs:
        p_html = p.replace("\n", "<br>")
        html_paragraphs.append(f"<p>{p_html}</p>")
    return "\n".join(html_paragraphs) + "\n" + SIGNATURE_HTML


def generate_template(site_code: str, sector: str, username: str) -> dict:
    if site_code not in gm.VALID_SITES:
        raise ValueError(f"Site invalide: {site_code}")
    if sector not in gm.SECTORS_GOD_MODE:
        raise ValueError(f"Secteur invalide: {sector}")
    existing = gm.get_template(site_code, sector)
    if existing and existing["locked"]:
        raise ValueError(f"Template {site_code}/{sector} verrouillé — déverrouiller avant régénération")

    prompt = build_prompt(site_code, sector)
    raw_response = call_deepseek(prompt)
    subject, body = parse_response(raw_response)
    if not subject or not body:
        raise ValueError(f"Parsing échoué — DeepSeek output: {raw_response[:200]}")

    html = text_to_html(body)
    raw_full = f"SUBJECT: {subject}\n\n{body}"
    gm.save_template(site_code, sector, subject, raw_full, html, username)
    return gm.get_template(site_code, sector)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: god_mode_templates.py <site> <sector>")
        sys.exit(1)
    site, sector = sys.argv[1], sys.argv[2]
    t = generate_template(site, sector, "cli")
    print("SUBJECT:", t["subject"])
    print("---RAW---")
    print(t["raw_content"])
    print("---HTML---")
    print(t["html_content"][:500])
