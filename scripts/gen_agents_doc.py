#!/usr/bin/env python3
"""gen_agents_doc.py — régénère memory/AGENTS.md depuis l'ÉTAT LIVE (factuel, zéro pourrissement).

Source de vérité : `pm2 jlist` (crons réels) + grep des scripts (capacités) + logs PM2
(dernier passage / agent mort) + table agent_actions (mémoire). À lancer en fin de session
touchant aux agents (exigence user). Lecture seule sauf l'écriture de AGENTS.md.
"""
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = BASE_DIR / "scripts"
LOGS = Path.home() / ".pm2" / "logs"
OUT = BASE_DIR / "memory" / "AGENTS.md"

SIGNALS = {
    "LLM": r"call_llm|deepseek|DeepSeek",
    "Observe": r"ga4|analyticsdata|searchconsole|gsc|ahrefs|api_get|fetch_ga4|fetch_gsc",
    "Mémoire": r"INSERT INTO|agent_actions|seo_traffic|recommendations\.json|json\.dump|set_state",
    "Évalue": r"verify_open_recos|evaluate|agent_outcomes|value_after",
}


def pm2_cron_apps():
    try:
        out = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=20).stdout
        data = json.loads(out)
    except Exception:
        return []
    apps = []
    for p in data:
        e = p.get("pm2_env", {})
        cron = e.get("cron_restart")
        if cron and "genesis" in p["name"]:
            apps.append({
                "name": p["name"],
                "script": Path(e.get("pm_exec_path", "")).name,
                "args": " ".join(e.get("args", []) or []),
                "cron": cron,
            })
    return apps


def caps(script_name):
    f = SCRIPTS / script_name
    if not f.exists():
        return None
    txt = f.read_text(encoding="utf-8", errors="ignore")
    return {k: bool(re.search(rx, txt)) for k, rx in SIGNALS.items()}


def last_run(name):
    out = LOGS / f"{name}-out.log"
    err = LOGS / f"{name}-error.log"
    dead = False
    if err.exists():
        tail = err.read_text(errors="ignore")[-2000:]
        if "No such file or directory" in tail or "can't open file" in tail:
            dead = True
    line = ""
    if out.exists():
        lines = [l for l in out.read_text(errors="ignore").splitlines() if l.strip()]
        line = lines[-1][:90] if lines else ""
    return dead, line


def actions_count():
    try:
        import duckdb
        c = duckdb.connect(str(BASE_DIR / "data" / "god_mode.duckdb"), read_only=True)
        rows = c.execute("SELECT agent, COUNT(*) FROM agent_actions GROUP BY agent").fetchall()
        c.close()
        return {a: n for a, n in rows}
    except Exception:
        return {}


def main():
    apps = pm2_cron_apps()
    ac = actions_count()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# AGENTS — Genesis (généré automatiquement)",
        "",
        f"> ⚙️ Régénéré par `gen_agents_doc.py` le **{now}** depuis PM2 + code + mémoire. Ne pas éditer à la main.",
        "> Capacités détectées par grep : **LLM** (DeepSeek) · **Observe** (GA4/GSC/Ahrefs) · **Mémoire** · **Évalue**.",
        "",
        "| Cron PM2 | Script | Cron | LLM | Observe | Mém. | Éval. | Statut / dernier passage |",
        "|---|---|---|:--:|:--:|:--:|:--:|---|",
    ]
    yes = lambda b: "✅" if b else "—"
    for a in sorted(apps, key=lambda x: x["name"]):
        c = caps(a["script"])
        dead, line = last_run(a["name"])
        if c is None:
            statut = "🔴 **MORT** (script absent)"
            cap = {"LLM": False, "Observe": False, "Mémoire": False, "Évalue": False}
        elif dead:
            statut = "🔴 **MORT** (erreur d'exécution)"
            cap = c
        else:
            statut = (line or "—")
            cap = c
        cmd = (a["script"] + " " + a["args"]).strip()
        lines.append(
            f"| {a['name']} | `{cmd}` | `{a['cron']}` | "
            f"{yes(cap['LLM'])} | {yes(cap['Observe'])} | {yes(cap['Mémoire'])} | {yes(cap['Évalue'])} | {statut} |")
    lines += [
        "",
        f"**Mémoire agentique** (`agent_actions`) : " +
        (", ".join(f"{k}={v}" for k, v in ac.items()) if ac else "aucune action enregistrée encore"),
        "",
        "> Détail des rôles/skills et de la cible agentique : voir `ARCHITECTURE.md`. "
        "Les agents avec Observe+Mémoire+Évalue tournent dans la boucle `agent_core` "
        "(observe→recall→decide→act→evaluate) ; les autres sont mécaniques ou one-shot à migrer.",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"AGENTS.md régénéré : {len(apps)} agents, {sum(ac.values()) if ac else 0} actions en mémoire.")


if __name__ == "__main__":
    main()
