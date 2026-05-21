#!/usr/bin/env python3
"""
rag_writer.py — Persistance RAG : à chaque burn de tokens DeepSeek/Ahrefs,
on stocke le contenu enrichi en chunks markdown pour réutilisation future.

Pourquoi : on paie pour chaque appel LLM/Ahrefs, autant en capitaliser la valeur.
Au lieu de jeter la réponse après usage, on l'archive en mémoire structurée.

Structure :
  memory/rag/{site}/{source}/{YYYY}/{MM}/{slug}-{ts}.md

Chaque fichier markdown contient :
  - Front-matter YAML : site, source, agent, timestamp, cost, tokens, tags
  - Corps : contenu chunked (~ 500-1500 mots par chunk, séparé par `---`)

Usage depuis un agent :
  from rag_writer import save_chunk
  save_chunk(
      site="lcr",
      source="deepseek",       # ou "ahrefs", "serper", "scraper"
      agent="brief_agent",      # qui a généré
      content="...",            # le texte enrichi à conserver
      metadata={
          "prompt_summary": "Génération article SEO sur sms marketing",
          "tokens_in": 800, "tokens_out": 320,
          "cost_eur": 0.000123,
          "tags": ["seo", "lcr", "rcs"],
      }
  )

Lookup futur (search RAG) :
  from rag_writer import search_chunks
  results = search_chunks(site="lcr", query="message rcs", limit=10)
"""

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
RAG_BASE = BASE_DIR / "memory" / "rag"

# Limites pour ne pas archiver les micro-réponses (cli-tests, pong, etc.)
MIN_CONTENT_CHARS = 100


def _slugify(s: str, maxlen: int = 50) -> str:
    if not s:
        return "chunk"
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9_\-]+", "-", s.lower()).strip("-")
    return (s or "chunk")[:maxlen]


def _chunk_text(text: str, target_words: int = 800) -> list[str]:
    """Découpe le texte en chunks de ~target_words mots, sur des frontières de paragraphe."""
    text = text.strip()
    if not text:
        return []
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for p in paragraphs:
        words_in_p = len(p.split())
        if current_words + words_in_p > target_words and current:
            chunks.append("\n\n".join(current))
            current = [p]
            current_words = words_in_p
        else:
            current.append(p)
            current_words += words_in_p
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def save_chunk(
    site: str,
    source: str,
    content: str,
    agent: str = "",
    metadata: dict | None = None,
) -> Path | None:
    """Persiste un contenu en markdown chunké pour usage RAG futur.

    Retourne le chemin du fichier créé, ou None si contenu trop court / erreur.
    """
    if not content or not isinstance(content, str):
        return None
    if len(content.strip()) < MIN_CONTENT_CHARS:
        return None  # micro-réponse, pas la peine d'archiver

    site = (site or "shared").lower()
    source = (source or "unknown").lower()
    metadata = dict(metadata or {})

    now = datetime.now(timezone.utc)
    ts_str = now.strftime("%Y%m%dT%H%M%SZ")
    slug = _slugify(metadata.get("prompt_summary") or metadata.get("action") or agent or source)

    out_dir = RAG_BASE / site / source / now.strftime("%Y") / now.strftime("%m")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{ts_str}-{slug}.md"

    # Build front-matter YAML
    tags = metadata.pop("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    front = {
        "site":      site,
        "source":    source,
        "agent":     agent or "unknown",
        "timestamp": now.isoformat(),
        "tags":      tags or [],
        **{k: v for k, v in metadata.items() if k not in ("prompt_summary",)},
    }
    front_yaml = "---\n"
    for k, v in front.items():
        if isinstance(v, (list, dict)):
            front_yaml += f"{k}: {json.dumps(v, ensure_ascii=False)}\n"
        elif isinstance(v, str):
            front_yaml += f'{k}: "{v}"\n'
        else:
            front_yaml += f"{k}: {v}\n"
    front_yaml += "---\n\n"

    title = metadata.get("prompt_summary", f"{source.upper()} — {agent}")
    body = f"# {title}\n\n"

    chunks = _chunk_text(content)
    for i, ch in enumerate(chunks):
        if i > 0:
            body += "\n\n---\n\n"  # séparateur de chunk
        body += f"<!-- chunk {i+1}/{len(chunks)} -->\n{ch}\n"

    try:
        out_file.write_text(front_yaml + body, encoding="utf-8")
        return out_file
    except Exception:
        return None


def search_chunks(site: str = "", query: str = "", limit: int = 20) -> list[dict]:
    """Recherche simple par grep dans les chunks RAG. Retourne snippets + paths."""
    if not query:
        return []
    pat = re.compile(re.escape(query.lower()))
    base = (RAG_BASE / site) if site else RAG_BASE
    if not base.exists():
        return []
    results = []
    for f in base.rglob("*.md"):
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if pat.search(txt.lower()):
            # Trouve l'emplacement et extrait un snippet
            idx = txt.lower().find(query.lower())
            start = max(0, idx - 100)
            end = min(len(txt), idx + 200)
            snippet = txt[start:end].replace("\n", " ")
            results.append({
                "path":    str(f.relative_to(BASE_DIR)),
                "site":    f.parts[-5] if len(f.parts) >= 5 else "",
                "source":  f.parts[-4] if len(f.parts) >= 4 else "",
                "snippet": snippet,
            })
            if len(results) >= limit:
                break
    return results


def stats() -> dict:
    """Stats globales du RAG par site/source."""
    out: dict = {"total_files": 0, "by_site": {}, "by_source": {}, "total_size_kb": 0}
    if not RAG_BASE.exists():
        return out
    for f in RAG_BASE.rglob("*.md"):
        out["total_files"] += 1
        try:
            out["total_size_kb"] += f.stat().st_size / 1024
        except Exception:
            pass
        parts = f.relative_to(RAG_BASE).parts
        if parts:
            site = parts[0]
            out["by_site"][site] = out["by_site"].get(site, 0) + 1
            if len(parts) > 1:
                src = parts[1]
                out["by_source"][src] = out["by_source"].get(src, 0) + 1
    out["total_size_kb"] = round(out["total_size_kb"], 1)
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        print(json.dumps(stats(), ensure_ascii=False, indent=2))
    elif len(sys.argv) > 2 and sys.argv[1] == "search":
        print(json.dumps(search_chunks(query=sys.argv[2], limit=5), ensure_ascii=False, indent=2))
    else:
        print("Usage: python3 rag_writer.py stats | search <query>")
