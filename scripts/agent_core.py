#!/usr/bin/env python3
"""agent_core.py — la boucle agentique partagée : observe → recall → decide → act.

But : transformer les agents one-shot/amnésiques en vrais agents avec contexte + mémoire,
SANS réécrire leur logique métier. Un agent existant importe ce module et appelle
`run_cycle(...)` au lieu de son appel DeepSeek brut.

Mémoire (god_mode.duckdb) : agent_actions / agent_outcomes / agent_state.
Moteur de décision : llm_call.call_llm_json (DeepSeek). Observe : GA4/GSC/Ahrefs (réutilise
traffic_strategist + ahrefs cache). Playbook : skills/{site}/{agent}.md (enfin branché).
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"
SKILLS = BASE_DIR / "skills"


# ── Store mémoire ───────────────────────────────────────────────────────────────
def _conn(retries: int = 6, base_delay: float = 0.5):
    """Connect avec retry-backoff si god_mode.duckdb est verrouillé par un autre
    process (typiquement le dashboard FastAPI qui garde un handle long-lived).
    6 tentatives × backoff exponentiel = ~30s max d'attente cumulative."""
    last = None
    for attempt in range(retries):
        try:
            return duckdb.connect(str(GOD_DB))
        except duckdb.IOException as e:  # noqa: PERF203
            last = e
            if "Conflicting lock" not in str(e) or attempt == retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
    raise last  # type: ignore[misc]


def ensure_schema() -> None:
    c = _conn()
    try:
        c.execute("""CREATE TABLE IF NOT EXISTS agent_actions (
            id VARCHAR, cycle_id VARCHAR, agent VARCHAR, site VARCHAR, ts TIMESTAMP,
            observed_snapshot JSON, reasoning VARCHAR, action_type VARCHAR,
            target VARCHAR, tags JSON, status VARCHAR)""")
        c.execute("""CREATE TABLE IF NOT EXISTS agent_outcomes (
            id VARCHAR, action_id VARCHAR, measured_at TIMESTAMP, metric VARCHAR,
            value_before DOUBLE, value_after DOUBLE, delta DOUBLE, verdict VARCHAR)""")
        c.execute("""CREATE TABLE IF NOT EXISTS agent_state (
            agent VARCHAR, site VARCHAR, key VARCHAR, value JSON, updated_at TIMESTAMP)""")
    finally:
        c.close()


# ── OBSERVE ─────────────────────────────────────────────────────────────────────
def observe(site: str, sources=("gsc",)) -> dict:
    """Construit un snapshot de l'état à partir des sources demandées (best-effort)."""
    snap: dict = {"site": site, "at": datetime.now(timezone.utc).isoformat(), "sources": {}}
    if "gsc" in sources:
        try:
            from traffic_strategist import fetch_gsc, opportunities
            g = fetch_gsc(site)
            if g.get("ok"):
                rows = g["rows"]
                snap["sources"]["gsc"] = {
                    "keywords": len(rows),
                    "clicks": sum(r["clicks"] for r in rows),
                    "impressions": sum(r["impressions"] for r in rows),
                    "opportunities": opportunities(rows)[:15],
                }
            else:
                snap["sources"]["gsc"] = {"error": g.get("reason")}
        except Exception as e:  # noqa: BLE001
            snap["sources"]["gsc"] = {"error": str(e)}
    if "ga4" in sources:
        try:
            from traffic_strategist import fetch_ga4_daily, fetch_ga4_channels
            d = fetch_ga4_daily(site)
            ch = fetch_ga4_channels(site)
            snap["sources"]["ga4"] = {
                "totals": d.get("totals", {}),
                "by_channel": ch.get("channels", []) if ch.get("ok") else [],
            }
        except Exception as e:  # noqa: BLE001
            snap["sources"]["ga4"] = {"error": str(e)}
    if "ahrefs" in sources:
        try:
            from traffic_strategist import _ahrefs_cache
            a = _ahrefs_cache(site)
            snap["sources"]["ahrefs"] = {k: a.get(k) for k in
                                         ("domain_rating", "org_keywords", "org_traffic", "ahrefs_rank")}
        except Exception as e:  # noqa: BLE001
            snap["sources"]["ahrefs"] = {"error": str(e)}
    return snap


# ── RECALL ──────────────────────────────────────────────────────────────────────
def recall(agent: str, site: str, n: int = 10) -> dict:
    ensure_schema()
    c = _conn()
    try:
        acts = c.execute(
            "SELECT a.id, a.ts, a.action_type, a.target, a.reasoning, "
            "o.metric, o.delta, o.verdict "
            "FROM agent_actions a LEFT JOIN agent_outcomes o ON o.action_id = a.id "
            "WHERE a.agent=? AND a.site=? ORDER BY a.ts DESC LIMIT ?", [agent, site, n]).fetchall()
        st = c.execute("SELECT key, value FROM agent_state WHERE agent=? AND site=?",
                       [agent, site]).fetchall()
    finally:
        c.close()
    return {
        "recent_actions": [{"ts": str(r[1]), "action": r[2], "target": r[3],
                            "reasoning": (r[4] or "")[:200],
                            "outcome": ({"metric": r[5], "delta": r[6], "verdict": r[7]} if r[5] else None)}
                           for r in acts],
        "state": {k: json.loads(v) if v else None for k, v in st},
    }


def set_state(agent: str, site: str, key: str, value) -> None:
    ensure_schema()
    c = _conn()
    try:
        c.execute("DELETE FROM agent_state WHERE agent=? AND site=? AND key=?", [agent, site, key])
        c.execute("INSERT INTO agent_state VALUES (?,?,?,?,?)",
                  [agent, site, key, json.dumps(value, ensure_ascii=False), datetime.now(timezone.utc)])
    finally:
        c.close()


# ── PLAYBOOK + DECIDE ───────────────────────────────────────────────────────────
def load_playbook(agent: str, site: str) -> str:
    for p in (SKILLS / site / f"{agent}.md", SKILLS / f"{agent}.md"):
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""


_SYSTEM = (
    "Tu es un agent autonome. On te donne ta POLICY (playbook), un SNAPSHOT de l'état "
    "actuel, et ta MÉMOIRE (tes actions passées + leur résultat mesuré). Décide un plan "
    "d'actions CONCRET et justifié par les données. Capitalise sur ce qui a marché "
    "(verdict positif), change d'approche sur ce qui a échoué. Réponds UNIQUEMENT en JSON : "
    '{"reasoning":"2-3 phrases", "plan":[{"action_type":"", "target":"", "why":"", '
    '"tags":{}}]}. Si rien à faire ce cycle, plan=[] et explique pourquoi dans reasoning.'
)

# Types d'action autorisés par agent (source de vérité = filtres des _agentic_writer).
# Sert à (1) contraindre le prompt système de decide() — le playbook seul ne suffit pas,
# DeepSeek invente sinon create_article/update_article/audit… — et (2) filtrer les items
# hors-enum AVANT qu'ils ne polluent agent_actions. Override via le param allowed_actions.
ALLOWED_ACTION_TYPES = {
    "seo-strategist":      ["seo_reco"],
    "content-writer":      ["write_article", "propose_article"],
    "internal-linking":    ["add_internal_link"],
    "linkedin-specialist": ["linkedin_post"],
    "competitive-intel":   ["intel_signal"],
    "graphiste":           ["generate_header"],
    # humanizer : le writer ignore action_type (il agit sur `target`), mais sans contrainte
    # DeepSeek inventait read_file/Write → erreurs. Un seul type valide : humanize_article.
    "humanizer":           ["humanize_article"],
}


def decide(agent: str, site: str, playbook: str, snapshot: dict, recalled: dict,
           allowed_actions: list | None = None) -> dict:
    from llm_call import call_llm_json
    allowed = allowed_actions or ALLOWED_ACTION_TYPES.get(agent)
    system = _SYSTEM
    if allowed:
        system = (
            f"{_SYSTEM}\n\nCONTRAINTE DURE : le champ `action_type` de CHAQUE item du plan "
            f"DOIT valoir EXACTEMENT l'une de ces valeurs : {allowed}. Toute autre valeur "
            "est INTERDITE et sera rejetée. N'invente JAMAIS de type (interdit : "
            "create_article, update_article, write_article hors liste, audit_*, fetch_*, "
            "research_*, etc.). Encode toujours ton intention via le `tags` d'un type autorisé."
        )
    base = (
        f"=== TON PLAYBOOK ===\n{playbook[:6000] or '(aucun playbook)'}\n\n"
        f"=== SNAPSHOT (état observé) ===\n{json.dumps(snapshot, ensure_ascii=False)[:6000]}\n\n"
        f"=== TA MÉMOIRE ===\n{json.dumps(recalled, ensure_ascii=False)[:4000]}\n\n"
        "Décide le plan (JSON strict)."
    )

    def _ask(extra: str = "") -> dict:
        try:
            out = call_llm_json(base + extra, system=system, max_tokens=2500,
                                module="agent_core", action=f"decide-{agent}", site=site)
            return out if isinstance(out, dict) else {"reasoning": "", "plan": []}
        except Exception as e:  # noqa: BLE001
            return {"reasoning": f"decide KO: {e}", "plan": []}

    out = _ask()
    if not allowed:
        return out

    def _violations(o: dict) -> list:
        return [it.get("action_type") for it in (o.get("plan") or [])
                if isinstance(it, dict) and it.get("action_type") not in allowed]

    # 1 passe de réparation si le modèle a inventé des types.
    bad = _violations(out)
    if bad:
        out = _ask(f"\n\n⚠️ Ta réponse précédente contenait des action_type INTERDITS : "
                   f"{bad}. Recommence en n'utilisant QUE {allowed}. Réémets le plan complet.")

    # Filet final : on jette les items hors-enum pour ne pas polluer agent_actions.
    if isinstance(out, dict) and isinstance(out.get("plan"), list):
        kept = [it for it in out["plan"]
                if isinstance(it, dict) and it.get("action_type") in allowed]
        dropped = len(out["plan"]) - len(kept)
        if dropped:
            out["reasoning"] = (out.get("reasoning") or "") + \
                f" [garde-fou: {dropped} item(s) hors-enum filtré(s)]"
        out["plan"] = kept
    return out


# ── ACT (écrit toujours dans agent_actions) ─────────────────────────────────────
def record_action(cycle_id, agent, site, snapshot, reasoning, action_type, target, tags, status="planned"):
    ensure_schema()
    c = _conn()
    aid = str(uuid.uuid4())
    try:
        c.execute("INSERT INTO agent_actions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  [aid, cycle_id, agent, site, datetime.now(timezone.utc),
                   json.dumps(snapshot, ensure_ascii=False), (reasoning or "")[:2000],
                   action_type, target, json.dumps(tags or {}, ensure_ascii=False), status])
    finally:
        c.close()
    return aid


# ── EVALUATE (boucle de feedback nocturne) ─────────────────────────────────────
# Pour chaque action `done` sans outcome dont l'âge ∈ [min_age_days, max_age_days],
# on re-mesure une métrique cible (position GSC du mot-clé visé, sinon clics GSC site,
# sinon sessions GA4) en comparant le snapshot stocké au snapshot live.
# Verdict : `validated` (mieux), `failed` (pire), `neutral` (pas de bouger franc).
# Inspiré de traffic_strategist.verify_open_recos.

def _gsc_pos_index(gsc_block: dict) -> dict:
    """Index {keyword: position} à partir d'un snapshot ou d'un live observe."""
    return {o.get("keyword"): o.get("position")
            for o in (gsc_block or {}).get("opportunities") or [] if o.get("keyword")}


def evaluate(site: str, agent: str | None = None,
             min_age_days: int = 7, max_age_days: int = 30) -> dict:
    """Mesure le delta réel des actions passées et écrit dans agent_outcomes."""
    ensure_schema()
    now = datetime.now(timezone.utc)
    live = observe(site, sources=("gsc", "ga4"))
    live_gsc = live["sources"].get("gsc", {}) or {}
    live_ga4_tot = (live["sources"].get("ga4", {}) or {}).get("totals") or {}
    live_pos = _gsc_pos_index(live_gsc)
    live_clicks = live_gsc.get("clicks") or 0
    live_sessions = live_ga4_tot.get("sessions") or 0

    q = ("SELECT a.id, a.agent, a.action_type, a.target, a.tags, a.observed_snapshot "
         "FROM agent_actions a LEFT JOIN agent_outcomes o ON o.action_id=a.id "
         "WHERE a.site=? AND a.status='done' AND a.action_type != 'noop' "
         "AND o.id IS NULL AND a.ts BETWEEN ? AND ?")
    params: list = [site, now - timedelta(days=max_age_days),
                    now - timedelta(days=min_age_days)]
    if agent:
        q += " AND a.agent=?"
        params.append(agent)

    written = skipped = 0
    by_verdict = {"validated": 0, "failed": 0, "neutral": 0}
    c = _conn()
    try:
        rows = c.execute(q, params).fetchall()
        for aid, agt, atype, target, tags_json, snap_json in rows:
            tags = json.loads(tags_json) if tags_json else {}
            snap = json.loads(snap_json) if snap_json else {}
            base_gsc = (snap.get("sources") or {}).get("gsc") or {}
            base_ga4_tot = ((snap.get("sources") or {}).get("ga4") or {}).get("totals") or {}
            base_pos = _gsc_pos_index(base_gsc)

            keyword = tags.get("keyword") or target
            metric = before = after = verdict = None

            if keyword and keyword in live_pos and keyword in base_pos:
                metric = f"gsc_position:{keyword}"
                before, after = base_pos[keyword], live_pos[keyword]
                delta = after - before  # plus bas = mieux
                verdict = ("validated" if delta <= -0.5
                           else "failed" if delta >= 1.0 else "neutral")
            elif base_gsc.get("clicks") is not None:
                metric = "gsc_clicks_total"
                before, after = base_gsc["clicks"] or 0, live_clicks
                delta = after - before
                pct = (delta / before) if before else 0
                verdict = ("validated" if pct >= 0.05
                           else "failed" if pct <= -0.05 else "neutral")
            elif base_ga4_tot.get("sessions") is not None:
                metric = "ga4_sessions_total"
                before, after = base_ga4_tot["sessions"] or 0, live_sessions
                delta = after - before
                pct = (delta / before) if before else 0
                verdict = ("validated" if pct >= 0.05
                           else "failed" if pct <= -0.05 else "neutral")
            else:
                skipped += 1
                continue

            c.execute("INSERT INTO agent_outcomes VALUES (?,?,?,?,?,?,?,?)",
                      [str(uuid.uuid4()), aid, now, metric,
                       float(before or 0), float(after or 0),
                       float((after or 0) - (before or 0)), verdict])
            written += 1
            by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
    finally:
        c.close()
    return {"site": site, "agent": agent, "evaluated": written, "skipped": skipped,
            "by_verdict": by_verdict, "min_age_days": min_age_days,
            "max_age_days": max_age_days}


# ── LA BOUCLE ────────────────────────────────────────────────────────────────────
def run_cycle(agent: str, site: str, sources=("gsc",), writer_fn=None,
              allowed_actions: list | None = None) -> dict:
    """observe → recall → decide → act. writer_fn(item, snapshot) exécute l'action métier
    (optionnel) ; dans tous les cas chaque item du plan est écrit dans agent_actions.
    allowed_actions : restreint les action_type pour ce consommateur précis (utile quand
    plusieurs agents partagent un même playbook, ex content_agent vs brief_agent)."""
    ensure_schema()
    cycle_id = str(uuid.uuid4())
    snap = observe(site, sources)
    mem = recall(agent, site)
    playbook = load_playbook(agent, site)
    plan = decide(agent, site, playbook, snap, mem, allowed_actions=allowed_actions)
    items = plan.get("plan", []) if isinstance(plan, dict) else []
    reasoning = plan.get("reasoning", "") if isinstance(plan, dict) else ""
    written = 0
    if not items:
        record_action(cycle_id, agent, site, snap, reasoning or "rien à faire ce cycle",
                      "noop", None, {}, status="done")
        written = 1
    for it in items:
        status = "planned"
        if writer_fn:
            try:
                writer_fn(it, snap)
                status = "done"
            except Exception as e:  # noqa: BLE001
                it["error"] = str(e)
                status = "error"
        record_action(cycle_id, agent, site, snap, reasoning, it.get("action_type", "?"),
                      it.get("target"), it.get("tags", {}), status=status)
        written += 1
    return {"cycle_id": cycle_id, "agent": agent, "site": site,
            "observed": list(snap["sources"].keys()), "reasoning": reasoning,
            "plan_items": len(items), "actions_written": written}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["cycle", "evaluate"], default="cycle")
    ap.add_argument("--agent", default=None,
                    help="Requis pour cycle ; optionnel pour evaluate (sinon tous les agents)")
    ap.add_argument("--site", default="lcr")
    ap.add_argument("--sources", default="gsc")
    ap.add_argument("--min-age-days", type=int, default=7)
    ap.add_argument("--max-age-days", type=int, default=30)
    args = ap.parse_args()
    if args.mode == "evaluate":
        out = evaluate(args.site, agent=args.agent,
                       min_age_days=args.min_age_days, max_age_days=args.max_age_days)
    else:
        if not args.agent:
            ap.error("--agent est requis en mode cycle")
        out = run_cycle(args.agent, args.site, tuple(args.sources.split(",")))
    print(json.dumps(out, ensure_ascii=False, default=str))
