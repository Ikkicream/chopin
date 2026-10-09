#!/usr/bin/env python3
"""gen_agents_state.py — Snapshot du vrai état PM2 des agents Genesis.

Source de vérité pour la page /agents : `pm2 jlist` → JSON normalisé écrit dans
`memory/agents-pm2-state.json`. Remplace `memory/agent-crons.json` (absent) qui
faisait croire à un planner vide alors que les vrais crons tournent depuis PM2.

Exclut les services longs (dashboard, ui, mailnjoy-drain) pour ne lister que les
agents one-shot (cron_restart). Le suffixe `-lcr`/`-mkd` du nom PM2 sert à filtrer
par site côté API.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUT = BASE_DIR / "memory" / "agents-pm2-state.json"
LONG_RUNNING = {"genesis-dashboard", "genesis-ui", "genesis-mailnjoy-drain"}


def pm2_jlist() -> list[dict]:
    r = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        raise RuntimeError(f"pm2 jlist exit {r.returncode}: {r.stderr[:200]}")
    return json.loads(r.stdout) if r.stdout.strip() else []


def site_of(name: str) -> str | None:
    if name.endswith("-lcr"):
        return "lcr"
    if name.endswith("-mkd"):
        return "mkd"
    return None  # global (appliqué à tous les sites côté UI)


def _ms_to_iso(ms) -> str | None:
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:  # noqa: BLE001
        return None


def project(p: dict) -> dict:
    env = p.get("pm2_env", {}) or {}
    return {
        "name": p["name"],
        "site": site_of(p["name"]),
        "script": (env.get("pm_exec_path") or "").rsplit("/", 1)[-1] or None,
        "args": env.get("args") or [],
        "cron": env.get("cron_restart"),
        "status": env.get("status"),
        "autorestart": env.get("autorestart"),
        "restarts": env.get("restart_time", 0),
        "unstable_restarts": env.get("unstable_restarts", 0),
        "last_start": _ms_to_iso(env.get("pm_uptime")),
        "last_exit_code": env.get("exit_code"),
    }


def build_state() -> dict:
    procs = pm2_jlist()
    agents = [project(p) for p in procs
              if p["name"].startswith("genesis-") and p["name"] not in LONG_RUNNING]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "count": len(agents),
        "agents": sorted(agents, key=lambda a: a["name"]),
    }


def write(state: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUT)


if __name__ == "__main__":
    try:
        s = build_state()
        write(s)
        print(json.dumps({"ok": True, "count": s["count"], "path": str(OUT)}))
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        sys.exit(1)
