#!/usr/bin/env python3
"""humanizer_agent.py — Agent agentique pour humaniser le backlog Arvow.

Boucle observe → recall → decide → act → record :
- observe : scan /home/autoblog/blog/articles/*.md, score scaffolding par article,
  exclut ceux déjà humanisés (présence d'un `.bak` à côté)
- recall : actions humanizer passées via agent_actions
- decide : DeepSeek (via scripts/llm_call.call_llm_json) choisit l'article prioritaire
  en exploitant le playbook skills/humanizer.md
- act : invoque humanize_article.humanize_one() sur l'article choisi
- record : trace dans agent_actions (site=shared, agent=humanizer)

Cron suggéré : 1 article par run, 1 run par jour → ~7 mois pour 212 articles.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ARTICLES_DIR = Path("/home/autoblog/blog/articles")
sys.path.insert(0, str(BASE_DIR / "scripts"))

from agent_core import (  # noqa: E402
    decide, ensure_schema, load_playbook, recall, record_action,
)

SCAFFOLDING_RE = re.compile(
    r"(^## (Introduction|Conclusion)\s*$|H[234] ?:|^---\s*$|Meta description|\[web:|"
    r"\(lien vers|\(à compléter\)|^```text\s*$|\b2025\b)",
    re.MULTILINE,
)


def score_article(path: Path) -> dict:
    """Retourne un dict {path, score, kb, status}. score = nb d'artefacts détectés."""
    try:
        txt = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:  # noqa: BLE001
        return {"path": str(path), "score": -1, "kb": 0, "error": str(e)}
    matches = len(SCAFFOLDING_RE.findall(txt))
    return {"path": str(path), "name": path.name, "score": matches, "kb": len(txt) // 1024}


def observe_articles(top_n: int = 10) -> dict:
    """Scan articles, exclut ceux déjà humanisés (présence d'un .md.bak), trie par score."""
    candidates = []
    for p in sorted(ARTICLES_DIR.glob("*.md")):
        bak = p.with_suffix(".md.bak")
        if bak.exists():
            continue
        candidates.append(score_article(p))
    candidates = [c for c in candidates if c["score"] > 0]
    candidates.sort(key=lambda c: -c["score"])
    return {
        "site": "shared",
        "at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "articles_backlog": {
                "total_unhumanized": len(candidates),
                "top_candidates": [
                    {"name": c["name"], "score": c["score"], "kb": c["kb"]}
                    for c in candidates[:top_n]
                ],
            }
        },
    }


def write_humanize(item: dict, snapshot: dict, *, dry_run: bool):
    """writer_fn : exécute humanize_article sur l'article choisi par decide()."""
    target = item.get("target")
    if not target:
        raise ValueError("plan sans target (nom de fichier)")
    article = ARTICLES_DIR / target
    if not article.exists():
        raise FileNotFoundError(f"article introuvable : {article}")
    if dry_run:
        print(f"  [agentic] DRY-RUN humanize {article}")
        item["dry_run"] = True
        return

    # Invoque humanize_article.main() en in-process pour éviter un subprocess fork
    import subprocess
    cmd = ["python3", str(BASE_DIR / "scripts" / "humanize_article.py"), str(article)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    item["humanizer_exit"] = r.returncode
    item["humanizer_stdout_tail"] = r.stdout[-400:]
    if r.returncode != 0:
        raise RuntimeError(f"humanize_article exit {r.returncode} : {r.stderr[-300:]}")


def run_cycle(site: str = "shared", dry_run: bool = True) -> dict:
    ensure_schema()
    cycle_id = str(uuid.uuid4())
    snap = observe_articles()
    mem = recall("humanizer", site)
    playbook = load_playbook("humanizer", site)
    plan = decide("humanizer", site, playbook, snap, mem)
    items = plan.get("plan", []) if isinstance(plan, dict) else []
    reasoning = plan.get("reasoning", "") if isinstance(plan, dict) else ""
    print(f"[humanizer] cycle {cycle_id[:8]} : {len(items)} item(s), reasoning="
          f"{reasoning[:200]!r}")

    written = 0
    if not items:
        record_action(cycle_id, "humanizer", site, snap,
                      reasoning or "rien à faire (backlog vide ou snapshot KO)",
                      "noop", None, {}, status="done")
        written = 1

    for it in items:
        status = "planned"
        try:
            write_humanize(it, snap, dry_run=dry_run)
            status = "done"
        except Exception as e:  # noqa: BLE001
            it["error"] = str(e)
            status = "error"
            print(f"  [error] {e}")
        record_action(cycle_id, "humanizer", site, snap, reasoning,
                      it.get("action_type", "?"), it.get("target"),
                      it.get("tags") or {}, status=status)
        written += 1

    return {"cycle_id": cycle_id, "agent": "humanizer", "site": site,
            "observed_candidates": len(snap["sources"]["articles_backlog"]["top_candidates"]),
            "reasoning": reasoning, "plan_items": len(items),
            "actions_written": written}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="shared")
    ap.add_argument("--live", action="store_true",
                    help="Exécute pour de vrai (sinon dry-run)")
    args = ap.parse_args()
    out = run_cycle(site=args.site, dry_run=not args.live)
    print(json.dumps(out, ensure_ascii=False, default=str))
