#!/usr/bin/env python3
"""
Setup Knowledge RAG for Genesis — per-site knowledge bases.
1. Create config per site
2. Populate documents directory with site context
3. Index everything
"""

import os
import shutil
from pathlib import Path

BASE = Path("/home/autoblog/genesis")
RAG_DIR = BASE / "tools" / "knowledge-rag"
DOCS_BASE = RAG_DIR / "documents"

# Site document sources
SITES = {
    "lcr": {
        "label": "LeClientROI",
        "sources": [
            # Skills contextualisés
            (BASE / "skills" / "lcr", "*.md"),
            # Context du site
            (BASE / "context" / "lcr", "*.md"),
            # Shared context
            (BASE / "context" / "shared" / "cold-email-rules.md", None),
            (BASE / "context" / "shared" / "emelia-knowledge", "*.md"),
            # Memory SEO
            (BASE / "memory" / "seo" / "lcr-ahrefs-latest.json", None),
            (BASE / "memory" / "seo" / "STRATEGIE.md", None),
            # Memory site
            (BASE / "memory" / "lcr" / "articles-published.md", None),
            (BASE / "memory" / "lcr" / "keywords-targeted.md", None),
            (BASE / "memory" / "lcr" / "site-context.md", None),
            # Backup Paperclip agents (instructions riches)
            (BASE / "backup" / "lcr-agents", "*/instructions/*.md"),
            # Articles backlog (top 20)
            (Path("/home/autoblog/blog/articles"), "*.md"),
        ],
    },
    "mkd": {
        "label": "MKDgroupe",
        "sources": [
            (BASE / "skills" / "mkd", "*.md"),
            (BASE / "context" / "mkd", "*.md"),
            (BASE / "context" / "shared" / "cold-email-rules.md", None),
            (BASE / "context" / "shared" / "emelia-knowledge", "*.md"),
            (BASE / "memory" / "seo" / "mkd-ahrefs-latest.json", None),
            (BASE / "memory" / "mkd" / "articles-published.md", None),
            (BASE / "memory" / "mkd" / "keywords-targeted.md", None),
            (BASE / "memory" / "mkd" / "site-context.md", None),
            (BASE / "backup" / "mkd-agents", "*/AGENTS.md"),
            (BASE / "backup" / "mkd-agents", "*/MEMORY.md"),
        ],
    },
}


def copy_files(src, pattern, dest_dir, max_files=50):
    """Copy files matching pattern to destination."""
    copied = 0
    src = Path(src)

    if not src.exists():
        return 0

    if src.is_file() and pattern is None:
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        return 1

    if src.is_dir():
        if pattern and "*" in pattern:
            # Handle nested glob
            for f in sorted(src.rglob(pattern.lstrip("*/")))[:max_files]:
                if f.is_file():
                    # Flatten the name
                    flat_name = f.relative_to(src).as_posix().replace("/", "_")
                    shutil.copy2(f, dest_dir / flat_name)
                    copied += 1
        elif pattern:
            for f in sorted(src.glob(pattern))[:max_files]:
                if f.is_file():
                    shutil.copy2(f, dest_dir / f.name)
                    copied += 1
        else:
            for f in sorted(src.iterdir())[:max_files]:
                if f.is_file():
                    shutil.copy2(f, dest_dir / f.name)
                    copied += 1

    return copied


def setup_site(site_code, config):
    """Setup RAG documents for a site."""
    site_docs = DOCS_BASE / site_code
    site_docs.mkdir(parents=True, exist_ok=True)

    # Clean old docs
    for f in site_docs.iterdir():
        if f.is_file():
            f.unlink()

    total = 0
    for src, pattern in config["sources"]:
        copied = copy_files(src, pattern, site_docs)
        if copied:
            print(f"  {src.name}: {copied} files")
        total += copied

    print(f"  Total: {total} documents for {site_code}")
    return total


def create_config():
    """Create knowledge-rag config.yaml."""
    config = f"""# Genesis Knowledge RAG Configuration
# Auto-generated — do not edit manually

documents_dir: "{DOCS_BASE}"

# Indexing
chunk_size: 512
chunk_overlap: 64

# Search
default_results: 5
max_results: 20

# Embedding model (local ONNX)
embedding_model: "all-MiniLM-L6-v2"
"""
    config_path = RAG_DIR / "config.yaml"
    config_path.write_text(config)
    print(f"Config written to {config_path}")


def main():
    print("=== Setting up Knowledge RAG ===")
    DOCS_BASE.mkdir(parents=True, exist_ok=True)

    for site_code, config in SITES.items():
        print(f"\n[{site_code}] {config['label']}")
        setup_site(site_code, config)

    create_config()

    # Count total
    total = sum(1 for f in DOCS_BASE.rglob("*") if f.is_file())
    print(f"\n=== Total: {total} documents indexed ===")
    print("Run: cd tools/knowledge-rag && pip install -r requirements.txt && python -m knowledge_rag index")


if __name__ == "__main__":
    main()
