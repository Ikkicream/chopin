#!/usr/bin/env python3
"""humanize_article.py — Pilote du prompt d'humanisation cmux-drop.

Applique le prompt complet (Phase 1 nettoyage + Phase 2 style + Phase 3 auto-contrôle)
sur un article markdown du blog autoblog via DeepSeek (scripts/llm_call.py).
Écrit en place après backup .bak. Affiche un bilan terminal.

Usage : python3 scripts/humanize_article.py <article.md> [--prompt <fichier.md>]
        python3 scripts/humanize_article.py <article.md> --dry-run
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PROMPT = Path("/tmp/cmux-drop-e943bc70-13ba-40fa-8d64-6f6c9a93587a.md")

BLACKLIST = [
    "n'est pas une option, c'est une nécessité",
    "dans un monde en constante évolution",
    "la ressource la plus rare",
    "il est important de noter",
    "il convient de souligner",
    "n'hésitez pas à",
    "en conclusion, nous pouvons",
    "cela étant dit",
    "de nos jours",
    "plonger dans",
    "explorer ensemble",
    "les résultats parlent d'eux-mêmes",
    "prêt à passer à l'action",
    "ne laissez pas vos concurrents",
]

SCAFFOLDING_PATTERNS = [
    (r"^H[234] ?:\s*", "préfixe H2:/H3:/H4: dans titre"),
    (r"^## (Introduction|Conclusion)\s*$", "## Introduction/Conclusion en label nu"),
    (r"^Meta description\s*:", "Meta description: dans le corps"),
    (r"\[web:\d+\]", "citation [web:N]"),
    (r"\(lien vers", "placeholder (lien vers"),
    (r"\(à compléter\)", "placeholder (à compléter)"),
    (r"^```text\s*$", "bloc ```text vide"),
]


def split_frontmatter(text: str) -> tuple[str, str]:
    """Retourne (frontmatter_inclus, corps). frontmatter inclut les '---' encadrants."""
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end == -1:
        return "", text
    fm = text[: end + len("\n---\n")]
    body = text[end + len("\n---\n"):]
    return fm, body


def count_scaffolding(text: str) -> dict:
    """Compte les occurrences d'artefacts de scaffolding (toutes phases)."""
    counts = {}
    for pat, label in SCAFFOLDING_PATTERNS:
        n = len(re.findall(pat, text, flags=re.MULTILINE))
        if n:
            counts[label] = n
    n_2025 = len(re.findall(r"\b2025\b", text))
    if n_2025:
        counts["2025 (à passer en 2026 sauf source datée)"] = n_2025
    n_hr = len(re.findall(r"^---\s*$", text, flags=re.MULTILINE))
    if n_hr > 2:  # 2 du frontmatter = OK
        counts["règle horizontale --- dans le corps"] = n_hr - 2
    n_h1 = len(re.findall(r"^# ", text, flags=re.MULTILINE))
    if n_h1 > 1:
        counts["H1 dupliqué"] = n_h1 - 1
    return counts


def count_blacklist(text: str) -> dict:
    low = text.lower()
    return {b: low.count(b) for b in BLACKLIST if b in low}


def check_constraints(rewritten: str, original_fm: str) -> list[str]:
    """Retourne la liste des contraintes violées (vide si OK)."""
    errors = []
    fm_rw, body_rw = split_frontmatter(rewritten)
    if fm_rw != original_fm:
        errors.append("frontmatter altéré (devrait être identique octet pour octet)")
    # Pas de --- dans le corps
    if re.search(r"^---\s*$", body_rw, flags=re.MULTILINE):
        errors.append("règle horizontale '---' présente dans le corps")
    # Pas de label H2:/H3:/H4:
    if re.search(r"H[234] ?:", rewritten):
        errors.append("préfixe H2:/H3:/H4: encore présent")
    # Pas de ## Introduction/Conclusion nu
    if re.search(r"^## (Introduction|Conclusion)\s*$", rewritten, flags=re.MULTILINE):
        errors.append("## Introduction ou ## Conclusion en label nu encore présent")
    # Pas de Meta description dans le corps
    if "Meta description" in body_rw:
        errors.append("'Meta description' encore dans le corps")
    # Pas de [web:N]
    if re.search(r"\[web:\d+\]", rewritten):
        errors.append("citation [web:N] encore présente")
    # H1 unique
    n_h1 = len(re.findall(r"^# ", body_rw, flags=re.MULTILINE))
    if n_h1 > 1:
        errors.append(f"H1 dupliqué ({n_h1} occurrences)")
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("article", type=Path)
    ap.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    ap.add_argument("--dry-run", action="store_true",
                    help="Affiche le diagnostic + estime le coût, n'appelle pas le LLM")
    args = ap.parse_args()

    if not args.article.exists():
        sys.exit(f"Article introuvable: {args.article}")
    if not args.prompt.exists():
        sys.exit(f"Prompt introuvable: {args.prompt}")

    original = args.article.read_text(encoding="utf-8")
    fm, body = split_frontmatter(original)
    if not fm:
        sys.exit("Frontmatter YAML --- ... --- introuvable en tête de l'article")

    print(f"[humanize] {args.article.name}")
    print(f"  taille originale: {len(original)} chars ({len(original.splitlines())} lignes)")
    print(f"  frontmatter: {len(fm)} chars (préservé tel quel)")

    scaff = count_scaffolding(original)
    bl = count_blacklist(original)
    print("  artefacts scaffolding détectés:")
    for k, v in sorted(scaff.items(), key=lambda x: -x[1]):
        print(f"    - {v}× {k}")
    print("  tournures blacklist détectées:")
    if not bl:
        print("    (aucune)")
    for k, v in sorted(bl.items(), key=lambda x: -x[1]):
        print(f"    - {v}× « {k} »")

    if args.dry_run:
        print("  [dry-run] OK, exit sans appel LLM.")
        return

    system_prompt = args.prompt.read_text(encoding="utf-8")
    user_prompt = (
        "Voici le fichier markdown à réécrire selon tes instructions. "
        "Renvoie UNIQUEMENT le contenu réécrit du fichier, intégralement (frontmatter "
        "compris, identique à l'original), sans préambule, sans bloc ```md autour, "
        "sans commentaire. Le bilan se fera côté terminal, pas dans le fichier.\n\n"
        f"=== FICHIER ORIGINAL ({args.article.name}) ===\n{original}"
    )

    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from llm_call import call_llm

    print("  appel DeepSeek (max_tokens=8000, temperature=0.4)...")
    rewritten = call_llm(
        prompt=user_prompt, system=system_prompt,
        max_tokens=8000, temperature=0.4,
        module="humanizer", action=f"humanize-{args.article.stem[:40]}", site="lcr",
    ).strip()

    # Strip fences ```md ... ``` au cas où le LLM aurait wrappé
    if rewritten.startswith("```"):
        first_nl = rewritten.find("\n")
        rewritten = rewritten[first_nl + 1:]
        if rewritten.endswith("```"):
            rewritten = rewritten[:-3]
        rewritten = rewritten.strip()

    print(f"  sortie reçue: {len(rewritten)} chars ({len(rewritten.splitlines())} lignes)")

    # Phase 3 : auto-contrôle
    errors = check_constraints(rewritten, fm)
    scaff_after = count_scaffolding(rewritten)
    bl_after = count_blacklist(rewritten)

    print("  artefacts scaffolding restants:")
    if not scaff_after:
        print("    (aucun) ✓")
    for k, v in scaff_after.items():
        print(f"    - {v}× {k}")
    print("  tournures blacklist restantes:")
    if not bl_after:
        print("    (aucune) ✓")
    for k, v in bl_after.items():
        print(f"    - {v}× « {k} »")

    # Sortie de secours : toujours écrire .rewritten.md à côté pour comparaison/inspection
    debug_path = args.article.with_suffix(".rewritten.md")
    debug_path.write_text(rewritten, encoding="utf-8")
    print(f"  sortie sauvegardée : {debug_path}")

    if errors:
        print("  ⚠ violations contraintes dures (fichier NON écrit en place):")
        for e in errors:
            print(f"    - {e}")
        sys.exit(1)

    # Backup + écriture en place
    bak = args.article.with_suffix(".md.bak")
    try:
        shutil.copy2(args.article, bak)
        args.article.write_text(rewritten, encoding="utf-8")
        print(f"  ✓ fichier réécrit en place. Backup : {bak.name}")
    except PermissionError as e:
        print(f"  ⚠ write en place refusé ({e.strerror}). Le diff est dans : {debug_path}")
        sys.exit(2)


if __name__ == "__main__":
    main()
