#!/usr/bin/env python3
"""
cost_tracker.py — Suivi des coûts API par action.
À appeler après chaque usage Claude/DeepSeek/Higgsfield.

Usage:
    from scripts.cost_tracker import track, get_summary
    track("article-rcs", "content", "claude-sonnet-4-6", input_tok=1200, output_tok=3400)
"""

import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR   = Path(__file__).parent.parent
COSTS_FILE = BASE_DIR / "memory" / "shared" / "costs-log.json"

# Tarifs en USD/MTok (million tokens) — mis à jour mai 2026
PRICING = {
    # Claude
    "claude-sonnet-4-6":           {"in": 3.00,  "out": 15.00},
    "claude-sonnet-4-5":           {"in": 3.00,  "out": 15.00},
    "claude-opus-4-6":             {"in": 15.00, "out": 75.00},
    "claude-haiku-4-5-20251001":   {"in": 0.80,  "out": 4.00},
    "claude-haiku-4-5":            {"in": 0.80,  "out": 4.00},
    # DeepSeek
    "deepseek-chat":               {"in": 0.07,  "out": 1.10},
    "deepseek-reasoner":           {"in": 0.55,  "out": 2.19},
    # Higgsfield (par image)
    "higgsfield-soul":             {"flat": 0.02},
    "higgsfield-popcorn":          {"flat": 0.04},
    # Unsplash (gratuit)
    "unsplash":                    {"flat": 0.0},
}

EUR_RATE = 0.92  # 1 USD = 0.92 EUR (approximatif)


def usd_to_eur(usd: float) -> float:
    return round(usd * EUR_RATE, 6)


def compute_cost(model: str, input_tok: int = 0, output_tok: int = 0) -> dict:
    """Calcule le coût en USD et EUR pour un appel."""
    p = PRICING.get(model, {"in": 3.00, "out": 15.00})
    if "flat" in p:
        usd = p["flat"]
    else:
        usd = (input_tok / 1_000_000) * p["in"] + (output_tok / 1_000_000) * p["out"]
    return {
        "usd":   round(usd, 6),
        "eur":   usd_to_eur(usd),
        "cents": round(usd * 100, 4),
    }


def track(
    action: str,
    module: str,
    model: str,
    input_tok: int = 0,
    output_tok: int = 0,
    note: str = "",
    site: str = "",
) -> dict:
    """
    Enregistre un usage API dans costs-log.json.

    Args:
        action: description de l'action (ex: "article-rcs-messagerie", "briefing-daily")
        module: module Genesis (briefing, content, crm_sync, campaigns)
        model:  modèle utilisé (claude-sonnet-4-6, deepseek-chat, ...)
        input_tok:  tokens en entrée
        output_tok: tokens en sortie
        note:   note libre
    Returns:
        dict de l'entrée loggée
    """
    cost = compute_cost(model, input_tok, output_tok)
    entry = {
        "date":       datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "action":     action,
        "module":     module,
        "model":      model,
        "input_tok":  input_tok,
        "output_tok": output_tok,
        "total_tok":  input_tok + output_tok,
        "cost_usd":   cost["usd"],
        "cost_eur":   cost["eur"],
        "cost_cents": cost["cents"],
        "note":       note,
        "site":       site,
    }

    COSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if COSTS_FILE.exists():
        try:
            existing = json.loads(COSTS_FILE.read_text())
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []

    existing.append(entry)
    COSTS_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
    return entry


def get_summary(days: int = 7) -> dict:
    """Résumé des coûts sur N jours."""
    if not COSTS_FILE.exists():
        return {"entries": [], "total_usd": 0, "total_eur": 0, "total_tok": 0, "by_module": {}, "by_model": {}}

    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    entries = json.loads(COSTS_FILE.read_text()) if COSTS_FILE.exists() else []
    recent = [e for e in entries if e.get("date", "") >= cutoff]

    total_usd = sum(e.get("cost_usd", 0) for e in recent)
    total_eur = sum(e.get("cost_eur", 0) for e in recent)
    total_tok = sum(e.get("total_tok", 0) for e in recent)

    by_module: dict = {}
    for e in recent:
        m = e.get("module", "unknown")
        by_module.setdefault(m, {"usd": 0, "eur": 0, "tok": 0, "calls": 0})
        by_module[m]["usd"]   += e.get("cost_usd", 0)
        by_module[m]["eur"]   += e.get("cost_eur", 0)
        by_module[m]["tok"]   += e.get("total_tok", 0)
        by_module[m]["calls"] += 1

    by_model: dict = {}
    for e in recent:
        mdl = e.get("model", "unknown")
        by_model.setdefault(mdl, {"usd": 0, "eur": 0, "tok": 0, "calls": 0})
        by_model[mdl]["usd"]   += e.get("cost_usd", 0)
        by_model[mdl]["eur"]   += e.get("cost_eur", 0)
        by_model[mdl]["tok"]   += e.get("total_tok", 0)
        by_model[mdl]["calls"] += 1

    by_site: dict = {}
    for e in recent:
        s = e.get("site", "")
        if s:
            by_site.setdefault(s, {"usd": 0, "eur": 0, "tok": 0, "calls": 0})
            by_site[s]["usd"]   += e.get("cost_usd", 0)
            by_site[s]["eur"]   += e.get("cost_eur", 0)
            by_site[s]["tok"]   += e.get("total_tok", 0)
            by_site[s]["calls"] += 1

    return {
        "days":      days,
        "entries":   recent,
        "total_usd": round(total_usd, 4),
        "total_eur": round(total_eur, 4),
        "total_tok": total_tok,
        "by_module": by_module,
        "by_model":  by_model,
        "by_site":   by_site,
    }


# ──────────────────────────────────────────────────────────────────────────────
# AHREFS BUDGET GATE
# ──────────────────────────────────────────────────────────────────────────────
# Ajouté 2026-05-22 — protection contre les dépassements de quota Ahrefs.
# Tout script qui appelle l'API Ahrefs DOIT vérifier check_ahrefs_budget() avant.
#
# Config .env (optionnel) :
#   AHREFS_BUDGET_WARN_PCT  (défaut 70)  — seuil d'alerte
#   AHREFS_BUDGET_BLOCK_PCT (défaut 90)  — seuil de blocage des appels non-critiques
#   AHREFS_BUDGET_RESERVE   (défaut 500) — unités minimum à garder dispo
#
# Usage :
#   from cost_tracker import check_ahrefs_budget
#   ok, info = check_ahrefs_budget(cost_estimate=500, critical=False)
#   if not ok:
#       print(f"Budget bloqué : {info}"); sys.exit(0)
#
AHREFS_USAGE_CACHE = BASE_DIR / "memory" / "seo" / "ahrefs-usage.json"


def _load_env_var(key: str, default: str = "") -> str:
    import os
    v = os.environ.get(key)
    if v:
        return v
    env_f = BASE_DIR / ".env"
    if env_f.exists():
        for ln in env_f.read_text().splitlines():
            ln = ln.strip()
            if ln.startswith(f"{key}="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return default


def _ahrefs_usage_fresh(max_age_min: int = 60) -> dict:
    """Lit le cache ahrefs-usage.json s'il est frais, sinon re-fetch via API."""
    from datetime import datetime, timezone, timedelta
    import requests
    cache_ok = False
    cache = {}
    if AHREFS_USAGE_CACHE.exists():
        try:
            cache = json.loads(AHREFS_USAGE_CACHE.read_text())
            fetched = datetime.fromisoformat(cache.get("fetched_at", "1970-01-01T00:00:00+00:00"))
            if (datetime.now(timezone.utc) - fetched) < timedelta(minutes=max_age_min):
                cache_ok = True
        except Exception:
            pass

    if cache_ok:
        return cache

    # Re-fetch (gratuit côté Ahrefs : subscription-info ne consomme pas d'unités)
    api_key = _load_env_var("AHREFS_API_KEY")
    if not api_key:
        return cache or {"used": 0, "total": 10000, "error": "no_api_key"}
    try:
        r = requests.get(
            "https://api.ahrefs.com/v3/subscription-info/limits-and-usage",
            headers={"Authorization": f"Bearer {api_key}"}, timeout=10,
        )
        if r.status_code == 200:
            info = r.json().get("limits_and_usage", {})
            cache = {
                "used":       info.get("units_usage_api_key", 0),
                "total":      info.get("units_limit_api_key") or 10000,
                "reset_at":   info.get("usage_reset_date", ""),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            AHREFS_USAGE_CACHE.parent.mkdir(parents=True, exist_ok=True)
            AHREFS_USAGE_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    except Exception as e:
        cache = cache or {"used": 0, "total": 10000, "error": str(e)}
    return cache


def check_ahrefs_budget(cost_estimate: int = 0, critical: bool = False) -> tuple:
    """
    Vérifie le budget Ahrefs AVANT un appel.

    Args:
        cost_estimate : nombre d'unités que l'appel va coûter (ex: 50, 200, 1100)
        critical      : True = appel essentiel (Tier 1/2), passe même en warning
                        False = appel facultatif (Tier 3/4), bloqué dès warning

    Returns:
        (ok: bool, info: dict)
        info contient : used, total, pct, reset_at, decision, reason
    """
    warn_pct  = float(_load_env_var("AHREFS_BUDGET_WARN_PCT",  "70"))
    block_pct = float(_load_env_var("AHREFS_BUDGET_BLOCK_PCT", "90"))
    reserve   = int(  _load_env_var("AHREFS_BUDGET_RESERVE",   "500"))

    usage = _ahrefs_usage_fresh()
    used  = usage.get("used", 0)
    total = usage.get("total", 10000) or 10000
    projected = used + cost_estimate
    pct       = round((used  / total) * 100, 1) if total else 0
    proj_pct  = round((projected / total) * 100, 1) if total else 0

    info = {
        "used": used, "total": total, "pct": pct,
        "projected_used": projected, "projected_pct": proj_pct,
        "cost_estimate": cost_estimate, "critical": critical,
        "reset_at": usage.get("reset_at", ""),
    }

    # Réserve absolue : on ne descend jamais sous reserve unités dispo
    if total - projected < reserve and not critical:
        info["decision"] = "BLOCK"
        info["reason"]  = f"Reserve {reserve}u tampon : il resterait {total - projected}u après cet appel"
        return False, info

    # Bloc dur > block_pct
    if proj_pct >= block_pct and not critical:
        info["decision"] = "BLOCK"
        info["reason"]  = f"Projection {proj_pct}% >= seuil bloc {block_pct}% (non-critique)"
        return False, info

    # Bloc dur > 100% même pour critique
    if projected > total:
        info["decision"] = "BLOCK"
        info["reason"]  = f"Projection {projected}u > limite {total}u — quota dépassé"
        return False, info

    # Warning
    if proj_pct >= warn_pct:
        info["decision"] = "WARN"
        info["reason"]  = f"Projection {proj_pct}% >= seuil warn {warn_pct}% — surveiller"
        return True, info

    info["decision"] = "OK"
    info["reason"]   = f"Projection {proj_pct}% sous seuil {warn_pct}%"
    return True, info



if __name__ == "__main__":
    # Test : simuler les runs du jour
    print("Test cost_tracker...")
    track("briefing-daily",        "briefing",   "claude-haiku-4-5", input_tok=800,  output_tok=1200, note="Rapport Telegram 01/05")
    track("crm-sync-emelia",       "crm_sync",   "claude-haiku-4-5", input_tok=400,  output_tok=200,  note="3 contacts importés")
    track("article-rcs-entreprise","content",    "deepseek-chat",    input_tok=2100, output_tok=4800, note="Article LCR publié")
    track("schema-rcs-flow",       "content",    "higgsfield-popcorn", note="Infographie flowchart RCS")
    track("schema-rcs-comp",       "content",    "higgsfield-popcorn", note="Infographie comparaison RCS")

    s = get_summary(7)
    print(f"\nSemaine: {s['total_eur']:.4f} EUR | {s['total_tok']:,} tokens")
    print("Par module:", {k: f"{v['eur']:.4f}€" for k,v in s['by_module'].items()})
    print("Par modèle:", {k: f"{v['eur']:.4f}€" for k,v in s['by_model'].items()})
