#!/usr/bin/env python3
"""
llm_call.py — Wrapper unique pour les appels LLM côté Genesis.

Route systématiquement vers DeepSeek (API OpenAI-compatible).
Pourquoi : la clé Anthropic facturait par token et a coûté ~$2000.
Désormais, seul l'orchestrateur cold email peut utiliser Sonnet via ccr (abonnement),
jamais via clé API directe.

Usage drop-in pour remplacer les anciennes fonctions call_haiku() :

    from llm_call import call_llm
    text = call_llm(prompt, max_tokens=2000, module="content", action="article-lcr", site="lcr")
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
TIMEOUT_S = 120


def _load_key() -> str:
    if key := os.environ.get("DEEPSEEK_API_KEY"):
        return key
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY=") and "=" in line:
                return line.split("=", 1)[1].strip("'\"")
    raise RuntimeError("DEEPSEEK_API_KEY introuvable (env ou .env)")


def _log_cost(model: str, input_tok: int, output_tok: int, module: str, action: str, site: str, note: str = "") -> None:
    """Logge l'appel dans memory/shared/costs-log.json via cost_tracker.track()."""
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR))
        from scripts.cost_tracker import track
        track(action or "generic", module or "llm_call", model, input_tok=input_tok, output_tok=output_tok, site=site, note=note)
    except Exception:
        pass  # Ne jamais faire échouer un appel LLM à cause du tracking


def call_llm(
    prompt: str,
    max_tokens: int = 2000,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    system: str | None = None,
    module: str = "llm_call",
    action: str = "generic",
    site: str = "",
    note: str = "",
) -> str:
    """Appel DeepSeek (OpenAI-compatible) → retourne le texte de la réponse.

    - `module` / `action` / `site` servent au logging costs-log (filtrables dans le dashboard /costs).
    - Lève RuntimeError si la clé manque, requests.HTTPError si DeepSeek répond mal.
    """
    key = _load_key()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    t0 = time.time()
    r = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=TIMEOUT_S)
    r.raise_for_status()
    data = r.json()

    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    _log_cost(
        model=model,
        input_tok=usage.get("prompt_tokens", 0),
        output_tok=usage.get("completion_tokens", 0),
        module=module,
        action=action,
        site=site,
        note=note or f"{(time.time()-t0):.1f}s",
    )
    return text


def call_llm_json(prompt: str, **kwargs) -> dict:
    """Variante qui parse la réponse en JSON. Tolère les wrappers ```json ... ```."""
    text = call_llm(prompt, **kwargs).strip()
    if text.startswith("```"):
        # Enlever les fences markdown
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


if __name__ == "__main__":
    # Test rapide depuis la CLI : python3 scripts/llm_call.py "Dis 'pong' en un mot."
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "Dis 'pong' en un mot."
    print(call_llm(q, max_tokens=50, module="llm_call", action="cli-test"))
