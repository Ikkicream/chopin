#!/usr/bin/env python3
"""
modules_backend.py — Activation/désactivation des modules par site + mini-RAG d'instructions IA.

Concept : chaque site a un fichier `memory/{site}/modules.json` qui indique :
  - quels modules sont actifs (Articles, SEO, Cold Email, LinkedIn...)
  - quelles instructions IA s'appliquent quand un agent travaille sur ce module pour ce site

Lu par :
  - la sidebar UI (filtre les items)
  - la page dashboard du site (cartes-toggles)
  - les agents Python (skip si désactivé + injecte les instructions dans les prompts)

Format JSON :
{
  "articles":     { "enabled": true,  "instructions": "Ton TPE/PME...", "updated_at": "..." },
  "seo_analysis": { "enabled": true,  "instructions": "...", "updated_at": "..." },
  "linkedin":     { "enabled": false, "instructions": "",    "updated_at": "..." },
  ...
}
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"


# ── Catalogue des modules disponibles ────────────────────────────────────────
# Chaque module définit ses dépendances connecteur + le(s) item(s) sidebar associés.
# `sidebar_titles` = la liste des titres dans app-sidebar.tsx qui sont gouvernés par ce module.

MODULES_CATALOG: dict[str, dict] = {
    "articles": {
        "label":          "Articles",
        "description":    "Rédaction + publication d'articles SEO",
        "icon":           "FileText",
        "connectors":     ["deepseek", "emdash_or_wp"],  # at least one of these
        "sidebar_titles": ["Articles"],
        "default_enabled": True,
    },
    "seo_analysis": {
        "label":          "Analyse SEO",
        "description":    "Données Ahrefs (DR, traffic, keywords, concurrents)",
        "icon":           "Search",
        "connectors":     ["ahrefs"],
        "sidebar_titles": ["Analyse SEO"],
        "default_enabled": True,
    },
    "seo_strategy": {
        "label":          "Stratégie SEO",
        "description":    "Recos actionnables marché FR via Ahrefs + DeepSeek",
        "icon":           "Brain",
        "connectors":     ["ahrefs", "deepseek"],
        "sidebar_titles": ["Stratégie SEO"],
        "default_enabled": True,
    },
    "agents_ia": {
        "label":          "Agents IA",
        "description":    "Orchestration des agents Genesis",
        "icon":           "Bot",
        "connectors":     ["deepseek"],
        "sidebar_titles": ["Agents IA"],
        "default_enabled": True,
    },
    "acquisition": {
        "label":          "Acquisition (CRM/PRM/Lead)",
        "description":    "Pipeline contacts cold_email → prm → lead → client",
        "icon":           "Users",
        "connectors":     [],  # interne, pas de dépendance externe
        "sidebar_titles": ["Acquisition"],
        "default_enabled": True,
    },
    "cold_email": {
        "label":          "Cold Email (Emelia)",
        "description":    "Campagnes Emelia + sync replies/clicks",
        "icon":           "Send",
        "connectors":     ["emelia"],
        "sidebar_titles": ["Emelia"],
        "default_enabled": True,
    },
    "god_mode": {
        "label":          "God Mode",
        "description":    "Templates, prospects, périmètre, logs cold email",
        "icon":           "Wand2",
        "connectors":     ["emelia"],
        "sidebar_titles": ["God mode", "Vue d'ensemble", "Templates", "Prospects", "Campagnes", "Logs", "Périmètre"],
        "default_enabled": True,
    },
    "linkedin": {
        "label":          "LinkedIn",
        "description":    "Posts LinkedIn auto (DeepSeek) — pas de page UI dédiée",
        "icon":           "Linkedin",
        "connectors":     ["deepseek"],
        "sidebar_titles": [],  # pas de page sidebar
        "default_enabled": True,
    },
    "setup_api": {
        "label":          "Setup & API",
        "description":    "Configuration clés API du site",
        "icon":           "Settings",
        "connectors":     [],
        "sidebar_titles": ["Setup & API"],
        "default_enabled": True,
    },
}


# ── Catalogue des connecteurs et leur env var ────────────────────────────────

CONNECTOR_ENV: dict[str, str] = {
    "deepseek":      "DEEPSEEK_API_KEY",
    "ahrefs":        "AHREFS_API_KEY",
    "emelia":        "EMELIA_API_KEY",
    "serper":        "SERPER_API_KEY",
    "telegram":      "TELEGRAM_BOT_TOKEN",
    "emdash":        "EMDASH_API_TOKEN",
    "wordpress":     "WP_APP_PASSWORD",
    "emdash_or_wp":  "EMDASH_API_TOKEN|WP_APP_PASSWORD",  # OR logic
    "tally_lcr":     "TALLY_API_KEY_LCR",
    "tally_mkd":     "TALLY_API_KEY_MKD",
    "unsplash_lcr":  "UNSPLASH_LCR_ACCESS_KEY",
    "unsplash_mkd":  "UNSPLASH_MKD_ACCESS_KEY",
    "higgsfield":    "HIGGSFIELD_API_KEY",
    "resend":        "RESEND_API_KEY",
}


# ── Helpers fichier ──────────────────────────────────────────────────────────

def _modules_file(site: str) -> Path:
    return BASE_DIR / "memory" / site / "modules.json"


def _load_env() -> dict:
    out = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip("'\"")
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> dict:
    return {
        mid: {"enabled": m["default_enabled"], "instructions": "", "updated_at": _now()}
        for mid, m in MODULES_CATALOG.items()
    }


def _load_state(site: str) -> dict:
    path = _modules_file(site)
    if not path.exists():
        state = _default_state()
        _save_state(site, state)
        return state
    try:
        state = json.loads(path.read_text())
    except Exception:
        state = _default_state()
    # Ajoute les nouveaux modules au cas où le catalogue a évolué
    changed = False
    for mid, meta in MODULES_CATALOG.items():
        if mid not in state:
            state[mid] = {"enabled": meta["default_enabled"], "instructions": "", "updated_at": _now()}
            changed = True
    if changed:
        _save_state(site, state)
    return state


def _save_state(site: str, state: dict) -> None:
    path = _modules_file(site)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2))


# ── Statut des connecteurs (consulte .env pour chaque clé) ──────────────────

def _check_connector(name: str, site: str = "") -> bool:
    env = _load_env()
    env.update(os.environ)
    env_var = CONNECTOR_ENV.get(name, "")
    if not env_var:
        return True  # connecteur "interne" sans dépendance externe
    # OR logic : TALLY_API_KEY_LCR | TALLY_API_KEY_MKD
    for v in env_var.split("|"):
        # Substitue {SITE} si présent (cas tally_<site>)
        if v in env and env[v]:
            return True
    # Fallback : check version site-spécifique (TALLY_API_KEY_LCR par exemple)
    if name == "tally" and site:
        return bool(env.get(f"TALLY_API_KEY_{site.upper()}", ""))
    return False


def get_connector_status(site: str = "") -> dict:
    """Retourne {connector_id: {ok: bool, env_var: str}}."""
    out = {}
    for name, env_var in CONNECTOR_ENV.items():
        out[name] = {"ok": _check_connector(name, site=site), "env_var": env_var}
    return out


# ── API publique ─────────────────────────────────────────────────────────────

def get_modules(site: str) -> dict:
    """Retourne pour un site : {modules: [{id, label, enabled, instructions, connectors_status, ...}]}."""
    state = _load_state(site)
    connectors = get_connector_status(site=site)

    modules_list = []
    for mid, meta in MODULES_CATALOG.items():
        st = state.get(mid, {"enabled": meta["default_enabled"], "instructions": "", "updated_at": ""})

        # Statut des connecteurs requis pour ce module
        connectors_ok = True
        connectors_detail = []
        for cn in meta["connectors"]:
            c = connectors.get(cn, {"ok": False})
            connectors_detail.append({"name": cn, "ok": c["ok"]})
            if not c["ok"]:
                connectors_ok = False
        # Cas spécial emdash_or_wp : au moins un des deux suffit
        if "emdash_or_wp" in meta["connectors"]:
            emdash_ok = _check_connector("emdash", site=site)
            wp_ok = _check_connector("wordpress", site=site)
            connectors_ok = emdash_ok or wp_ok
            # Réécrit le detail pour cette ligne
            connectors_detail = [d for d in connectors_detail if d["name"] != "emdash_or_wp"]
            connectors_detail.append({"name": "emdash_or_wp", "ok": connectors_ok, "detail": f"emdash={emdash_ok} wp={wp_ok}"})

        modules_list.append({
            "id":               mid,
            "label":            meta["label"],
            "description":      meta["description"],
            "icon":             meta["icon"],
            "enabled":          st["enabled"],
            "instructions":     st["instructions"],
            "updated_at":       st.get("updated_at", ""),
            "connectors":       connectors_detail,
            "connectors_ok":    connectors_ok,
            "sidebar_titles":   meta["sidebar_titles"],
        })

    return {"site": site, "modules": modules_list}


def toggle(site: str, module_id: str, enabled: bool) -> dict:
    if module_id not in MODULES_CATALOG:
        return {"error": "unknown_module"}
    state = _load_state(site)
    state.setdefault(module_id, {"enabled": False, "instructions": "", "updated_at": ""})
    state[module_id]["enabled"] = bool(enabled)
    state[module_id]["updated_at"] = _now()
    _save_state(site, state)
    return {"ok": True, "module": module_id, "enabled": bool(enabled)}


def set_instructions(site: str, module_id: str, text: str) -> dict:
    if module_id not in MODULES_CATALOG:
        return {"error": "unknown_module"}
    state = _load_state(site)
    state.setdefault(module_id, {"enabled": MODULES_CATALOG[module_id]["default_enabled"], "instructions": "", "updated_at": ""})
    state[module_id]["instructions"] = text or ""
    state[module_id]["updated_at"] = _now()
    _save_state(site, state)
    return {"ok": True, "module": module_id}


# ── API consommée par les agents ────────────────────────────────────────────

def is_enabled(site: str, module_id: str) -> bool:
    """Vrai si le module est activé pour ce site. False si site ou module inconnu."""
    if module_id not in MODULES_CATALOG:
        return False
    state = _load_state(site)
    return bool(state.get(module_id, {}).get("enabled", MODULES_CATALOG[module_id]["default_enabled"]))


def get_instructions(site: str, module_id: str) -> str:
    """Retourne le texte d'instructions IA (vide si rien défini)."""
    state = _load_state(site)
    return state.get(module_id, {}).get("instructions", "") or ""


def enrich_prompt(prompt: str, site: str, module_id: str) -> str:
    """Concatène les instructions du module à un prompt si présentes.
    Helper pratique pour les agents : `prompt = enrich_prompt(prompt, site, "articles")`.
    """
    extra = get_instructions(site, module_id)
    if not extra:
        return prompt
    return prompt + (
        f"\n\n=== CONSIGNES SPÉCIFIQUES pour {site.upper()} / module {module_id} ===\n"
        f"{extra}\n=== FIN CONSIGNES ===\n"
    )


if __name__ == "__main__":
    import sys
    site = sys.argv[1] if len(sys.argv) > 1 else "lcr"
    data = get_modules(site)
    print(f"=== Modules {site} ===")
    for m in data["modules"]:
        ico = "🟢" if m["enabled"] else "🔴"
        ck = "✓" if m["connectors_ok"] else "✗"
        print(f"  {ico} {ck} {m['id']:18s} {m['label']}")
