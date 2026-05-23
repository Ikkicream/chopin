#!/usr/bin/env python3
"""
generate_changelog.py — Génère un .log humain pour chaque backup version.

Appelé par backup.sh après git commit.
Usage: python3 generate_changelog.py <output_log_path>

Le log contient :
  1. Header (date, version, taille zip si fourni)
  2. Résumé humain (DeepSeek si DEEPSEEK_API_KEY dispo, sinon template basique)
  3. Commits inclus depuis le précédent .log
  4. Fichiers modifiés groupés par catégorie
  5. Fonctions / classes Python touchées (extraits diff)
"""
import os
import subprocess
import sys
import re
from pathlib import Path
from datetime import datetime

BASE = Path("/home/autoblog/genesis")
BACKUP_DIR = BASE / "backups"


def git_run(args: list[str]) -> str:
    try:
        r = subprocess.run(args, cwd=str(BASE), capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception as e:
        return f"[git error: {e}]"


def find_previous_log_commit() -> str | None:
    """Trouve le sha du dernier .log existant (pour delta depuis lui)."""
    logs = sorted(BACKUP_DIR.glob("genesis-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for log in logs[:5]:
        try:
            content = log.read_text(errors="ignore")
            m = re.search(r"head_sha:\s*([a-f0-9]{7,40})", content)
            if m:
                return m.group(1)
        except Exception:
            continue
    return None


def categorize(file_path: str) -> str:
    if file_path.startswith("scripts/"):     return "Backend Python"
    if file_path.startswith("genesis-ui/"):  return "Frontend UI"
    if file_path.startswith("specs/"):        return "Spécifications"
    if file_path.startswith("data/"):          return "Données / DB"
    if file_path.startswith("memory/"):        return "Mémoire / RAG"
    if file_path.startswith("context/"):       return "Contexte sites"
    if file_path.startswith("logs/"):          return "Logs"
    if file_path in ("CLAUDE.md", "STATE.md", "ARCHITECTURE.md"):
        return "Documentation racine"
    if file_path.endswith(".md"):              return "Documentation"
    if file_path.endswith(".sh"):              return "Scripts shell"
    return "Autres"


def extract_functions_touched(diff_text: str) -> list[str]:
    """Récupère les fonctions/classes Python ou TS touchées depuis un git diff."""
    funcs = set()
    for line in diff_text.split("\n"):
        # Python : def foo(...) ou class Bar(...)
        m = re.match(r"^(?:@@.*?@@ )?\s*(def|class|async def)\s+([A-Za-z_][\w]*)", line)
        if m:
            funcs.add(f"{m.group(1)} {m.group(2)}()")
        # TS/JS : function foo, const foo = (, export default function foo
        m2 = re.search(r"\b(?:export\s+default\s+)?(?:async\s+)?function\s+([A-Za-z_][\w]*)", line)
        if m2:
            funcs.add(f"function {m2.group(1)}()")
        m3 = re.search(r"^(?:\+|-)?\s*export\s+(?:const|function|class)\s+([A-Za-z_][\w]*)", line)
        if m3:
            funcs.add(f"export {m3.group(1)}")
    return sorted(funcs)[:30]  # cap à 30


def humanize_with_deepseek(commits_msgs: list[str], categories: dict) -> str:
    """Si DEEPSEEK_API_KEY dispo, demande un résumé humain. Sinon fallback template."""
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not deepseek_key:
        return _fallback_summary(commits_msgs, categories)
    try:
        import requests
        commits_txt = "\n".join(f"- {m}" for m in commits_msgs[:30])
        cats_txt = "\n".join(f"- {cat}: {len(files)} fichier(s)" for cat, files in categories.items())
        prompt = f"""Résume en 2-3 phrases en français naturel ce qui a changé dans cette version Genesis (SaaS prospection cold email B2B).
Mets l'accent sur les nouvelles features et fixes importants. Pas de jargon technique inutile.

Commits :
{commits_txt}

Catégories de fichiers modifiés :
{cats_txt}

Résumé en 2-3 phrases :"""
        r = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 250,
                "temperature": 0.3,
            },
            timeout=20,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[changelog] deepseek failed: {e}")
    return _fallback_summary(commits_msgs, categories)


def _fallback_summary(commits_msgs: list[str], categories: dict) -> str:
    main_cat = max(categories.items(), key=lambda x: len(x[1]))[0] if categories else "divers"
    return (f"{len(commits_msgs)} commit(s) depuis la version précédente. "
            f"Modifications principalement dans : {main_cat}. "
            f"Catégories touchées : {', '.join(categories.keys())}.")


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_changelog.py <output_log_path>")
        sys.exit(1)
    out_path = Path(sys.argv[1])

    # Date / version
    now = datetime.now()
    head_sha = git_run(["git", "rev-parse", "--short", "HEAD"])
    commit_count = git_run(["git", "rev-list", "--count", "HEAD"])
    version = f"v{commit_count}.{head_sha}" if commit_count.isdigit() else head_sha

    # Delta depuis le précédent .log
    prev_sha = find_previous_log_commit()
    if prev_sha:
        commits_range = f"{prev_sha}..HEAD"
    else:
        # Pas de précédent log : prendre les 10 derniers commits
        commits_range = "HEAD~10..HEAD" if commit_count.isdigit() and int(commit_count) > 10 else "HEAD"

    # Récupère les commits
    commits_raw = git_run(["git", "log", commits_range, "--pretty=format:%h|%cI|%an|%s"]).split("\n")
    commits = []
    commits_msgs = []
    for line in commits_raw:
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append({"sha": parts[0], "date": parts[1], "author": parts[2], "msg": parts[3]})
            commits_msgs.append(parts[3])

    # Fichiers modifiés
    files_changed = git_run(["git", "diff", "--name-only", commits_range]).split("\n")
    files_changed = [f for f in files_changed if f.strip()]

    # Catégorisation
    categories: dict[str, list[str]] = {}
    for f in files_changed:
        cat = categorize(f)
        categories.setdefault(cat, []).append(f)

    # Stats détaillées (additions/suppressions)
    stat_lines = git_run(["git", "diff", "--stat", commits_range]).split("\n")

    # Fonctions touchées (parsing diff)
    full_diff = git_run(["git", "diff", commits_range])
    functions = extract_functions_touched(full_diff)

    # Résumé humain
    summary = humanize_with_deepseek(commits_msgs, categories)

    # Écriture du log
    BACKUP_DIR.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        f.write(f"# Genesis Changelog — Version {version}\n\n")
        f.write(f"**Date** : {now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        f.write(f"**head_sha** : {head_sha}\n")
        f.write(f"**commits_depuis_précédent** : {len(commits)}\n")
        f.write(f"**previous_sha** : {prev_sha or '(initial)'}\n\n")

        f.write("## Résumé en langage humain\n\n")
        f.write(f"{summary}\n\n")

        f.write("## Commits inclus\n\n")
        if commits:
            for c in commits:
                f.write(f"- `{c['sha']}` ({c['date'][:10]}) — {c['author']} : {c['msg']}\n")
        else:
            f.write("_(aucun commit dans cette plage)_\n")
        f.write("\n")

        f.write("## Fichiers modifiés (par catégorie)\n\n")
        for cat in sorted(categories.keys()):
            files = categories[cat]
            f.write(f"### {cat} ({len(files)} fichier(s))\n\n")
            for fl in sorted(files)[:20]:
                f.write(f"- `{fl}`\n")
            if len(files) > 20:
                f.write(f"- _… et {len(files) - 20} autres_\n")
            f.write("\n")

        f.write("## Fonctions / classes touchées\n\n")
        if functions:
            for fn in functions[:30]:
                f.write(f"- `{fn}`\n")
        else:
            f.write("_(aucune fonction nouvelle ou modifiée détectée)_\n")
        f.write("\n")

        f.write("## Statistiques git diff --stat\n\n")
        f.write("```\n")
        for line in stat_lines[-15:]:
            f.write(line + "\n")
        f.write("```\n")

    print(f"[OK] Changelog généré : {out_path}")


if __name__ == "__main__":
    main()
