#!/usr/bin/env python3
"""
editorial_reviser.py v2 — Correction ciblée point par point.
1. Prend chaque issue du QC
2. Envoie à DeepSeek avec l'article + instructions précises
3. Haiku vérifie chaque issue originale : résolue ou pas
4. Inclut les règles permanentes du site (CTA, liens, etc.)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent.parent
QUEUE_FILE = BASE_DIR / "memory" / "editorial" / "articles-queue.json"

env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip("'\""))

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Règles permanentes par site — appliquées à CHAQUE correction
SITE_RULES = {
    "lcr": [
        "CTA obligatoire en fin d'article : lien vers https://leclientroi.com avec texte incitatif",
        "Ajouter un CTA vers le livre blanc : https://ik.imagekit.io/rgpdsimplement/Libreblanc.pdf",
        "Image leadmagnet disponible : https://ik.imagekit.io/rgpdsimplement/leadmagnet.png",
        "Ne jamais inventer de statistiques sans source",
        "Ton : expert mais accessible, pour des gérants de TPE/PME",
        "Année 2026 partout (jamais 2025)",
        "Minimum 1000 mots",
        "Le mot-clé principal doit être dans les 100 premiers mots et dans au moins 2 H2",
    ],
    "mkd": [
        "CTA obligatoire en fin d'article : lien vers https://mkdgroupe.com/contact",
        "Ton : professionnel B2B, factuel, chiffres et ROI",
        "Année 2026 partout (jamais 2025)",
        "Minimum 1000 mots",
        "Le mot-clé principal doit être dans les 100 premiers mots et dans au moins 2 H2",
    ],
}


def call_deepseek(prompt, max_tokens=8000):
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    r = requests.post("https://api.deepseek.com/chat/completions", json={
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5,
        "max_tokens": max_tokens,
    }, headers=headers, timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"], r.json().get("usage", {})


def call_haiku(prompt, max_tokens=2000):
    from llm_call import call_llm
    return call_llm(prompt, max_tokens=max_tokens, module="editorial-reviser", action="qc-revision")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    args = parser.parse_args()

    queue = json.loads(QUEUE_FILE.read_text())
    art = next((a for a in queue if a["id"] == args.id), None)
    if not art:
        print(f"Article {args.id} not found")
        sys.exit(1)

    original_md = art.get("article", {}).get("markdown", "")
    qc = art.get("qc_report", {})
    issues = qc.get("issues", [])
    keyword = art["proposal"]["keyword"]
    title = art["proposal"]["title"]
    site = art["site"]
    site_rules = SITE_RULES.get(site, [])

    print(f"[reviser v2] {args.id} — {len(issues)} issues à corriger")

    # Build correction prompt — issue by issue
    issues_numbered = "\n".join([f"{i+1}. {issue}" for i, issue in enumerate(issues)])
    rules_text = "\n".join([f"- {r}" for r in site_rules])

    prompt = f"""Tu as écrit cet article mais le contrôle qualité l'a rejeté. Tu dois corriger CHAQUE problème listé ci-dessous.

TITRE : {title}
MOT-CLÉ : {keyword}

PROBLÈMES À CORRIGER (tu dois résoudre CHACUN) :
{issues_numbered}

RÈGLES PERMANENTES DU SITE (à appliquer OBLIGATOIREMENT) :
{rules_text}

ARTICLE ORIGINAL :
---
{original_md}
---

INSTRUCTIONS :
- Corrige chaque problème numéroté ci-dessus. Ne laisse AUCUN problème non résolu.
- L'article DOIT être complet avec une vraie conclusion et un CTA.
- Ne supprime pas les parties qui étaient bonnes.
- Minimum 1000 mots.
- 6+ mots en **gras**, 3+ en *italique*, 1 citation (>), 1 liste à puces.
- Markdown pur, pas de frontmatter, pas de HTML.

Écris l'article corrigé complet."""

    print("  Envoi à DeepSeek...")
    try:
        revised_md, tokens = call_deepseek(prompt)
        word_count = len(revised_md.split())
        print(f"  Reçu : {word_count} mots")
    except Exception as e:
        print(f"  ERREUR DeepSeek : {e}")
        art["status"] = "revision_needed"
        art["human_notes"] = f"Erreur revision: {e}"
        QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False))
        sys.exit(1)

    # Haiku vérifie CHAQUE issue originale
    print("  Vérification point par point (Haiku)...")
    verify_prompt = f"""Vérifie si chaque problème listé a été corrigé dans l'article révisé.

PROBLÈMES ORIGINAUX :
{issues_numbered}

ARTICLE RÉVISÉ :
---
{revised_md[:6000]}
---

Pour CHAQUE problème, réponds en JSON :
[
  {{"issue": "texte du problème", "resolved": true/false, "comment": "explication courte"}}
]"""

    try:
        verify_text = call_haiku(verify_prompt)
        if "```" in verify_text:
            verify_text = verify_text.split("```")[1]
            if verify_text.startswith("json"):
                verify_text = verify_text[4:]
        verifications = json.loads(verify_text)

        resolved_count = sum(1 for v in verifications if v.get("resolved"))
        total_issues = len(verifications)
        print(f"  {resolved_count}/{total_issues} issues résolues")

        # Build new QC report
        remaining_issues = [v["issue"] for v in verifications if not v.get("resolved")]
        resolved_issues = [v["issue"] + " ✓" for v in verifications if v.get("resolved")]

        new_score = min(95, 70 + (resolved_count * 5))
        new_qc = {
            "score": new_score,
            "issues": remaining_issues,
            "resolved": resolved_issues,
            "verification": verifications,
            "verdict": "APPROVED" if new_score >= 70 and not remaining_issues else "REVISION_NEEDED",
        }

    except Exception as e:
        print(f"  Verification error: {e}")
        new_qc = {"score": 0, "issues": [str(e)], "verdict": "ERROR"}

    # Update queue
    art["article"]["markdown"] = revised_md
    art["article"]["word_count"] = word_count
    art["article"]["revised_at"] = datetime.now(timezone.utc).isoformat()
    art["article"]["revision_count"] = art["article"].get("revision_count", 0) + 1
    art["qc_report"] = new_qc
    art["status"] = "ready_to_review" if new_qc.get("score", 0) >= 70 else "revision_needed"
    art["updated_at"] = datetime.now(timezone.utc).isoformat()

    QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False))
    print(f"  Score : {new_qc.get('score')}/100 — {art['status']}")
    print("[reviser v2] Done!")


if __name__ == "__main__":
    main()
