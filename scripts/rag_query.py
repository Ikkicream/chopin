#!/usr/bin/env python3
"""
rag_query.py — Query the knowledge base for a site.
Simple text search (BM25) on the indexed documents.
Used by agents to get site context before generating content.

Usage: python3 scripts/rag_query.py --site lcr --query "sms marketing stratégie"
"""

import argparse
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DOCS_DIR = BASE_DIR / "tools" / "knowledge-rag" / "documents"


def simple_search(site, query, max_results=5):
    """Simple BM25-like text search on site documents."""
    site_dir = DOCS_DIR / site
    if not site_dir.exists():
        return []

    query_terms = set(re.findall(r'\w+', query.lower()))
    results = []

    for f in site_dir.iterdir():
        if not f.is_file():
            continue
        try:
            text = f.read_text(errors="ignore")
            text_lower = text.lower()

            # Score: count matching terms + bonus for title matches
            score = 0
            for term in query_terms:
                count = text_lower.count(term)
                score += min(count, 10)  # Cap per term to avoid bias
                # Bonus if in first 200 chars (likely title/summary)
                if term in text_lower[:200]:
                    score += 5

            if score > 0:
                # Extract best matching snippet
                snippet = ""
                for term in query_terms:
                    idx = text_lower.find(term)
                    if idx >= 0:
                        start = max(0, idx - 50)
                        end = min(len(text), idx + 100)
                        snippet = text[start:end].strip()
                        break

                results.append({
                    "file": f.name,
                    "score": score,
                    "snippet": snippet[:200],
                    "size": len(text),
                })
        except Exception:
            continue

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def get_site_context(site, query="", max_chars=2000):
    """Get relevant context from the site's knowledge base.
    Called by agents to inject context into their prompts."""
    results = simple_search(site, query, max_results=3)

    context_parts = []
    chars = 0
    for r in results:
        f = DOCS_DIR / site / r["file"]
        if f.exists():
            text = f.read_text(errors="ignore")
            remaining = max_chars - chars
            if remaining <= 0:
                break
            context_parts.append(f"--- {r['file']} ---\n{text[:remaining]}")
            chars += len(text[:remaining])

    return "\n\n".join(context_parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True, choices=["lcr", "mkd"])
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--context", action="store_true", help="Return full context instead of snippets")
    args = parser.parse_args()

    if args.context:
        ctx = get_site_context(args.site, args.query)
        print(ctx)
    else:
        results = simple_search(args.site, args.query, args.limit)
        for r in results:
            print(f"[{r['score']:3d}] {r['file']}: {r['snippet'][:80]}...")


if __name__ == "__main__":
    main()
