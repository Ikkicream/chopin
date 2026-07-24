"""
autoscrape_plan.py — Plan de scraping automatique EN DUR (demande Camille 2026-07-08).

Parcourt les régions dans l'ORDRE EXACT du select du scrapper (haut → bas). Pour la
région courante, `autoscrape_backend.run_autoscrape` fait département par département
(villes ≥10k hab, Serper + Basile) jusqu'à TARGET_PER_REGION contacts valides, puis le
plan passe à la région suivante. Région bloquée (Serper) → reprise automatique au tick
suivant avec le reliquat, en sautant les départements déjà finis.

Secteur : immobilier d'abord. Les secteurs suivants sont pré-écrits mais COMMENTÉS —
on ne les active qu'après validation de Camille (« si tout se passe bien on passe aux
autres »). Fin de plan → notification Telegram.

Fonctionnement : cron `tick` toutes les 30 min, 07h-21h (crontab autoblog). Un tick est
instantané : il vérifie l'état et, si besoin, lance `work` en processus détaché qui
fait le run bloquant d'une région.

État : memory/autoscrape/<site>-plan.json · pause : <site>-plan-pause.flag
Log  : logs/autoscrape_plan.log
CLI  : tick | work | status | pause | resume | reset
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

SITE = "lcr"
TARGET_PER_REGION = 1000

# ── PROGRAMMATION EN DUR ─────────────────────────────────────────────────────────
# Secteurs, dans l'ordre. On ne décommente le suivant qu'après validation user.
PLAN_SECTORS = [
    "immobilier",
    # "agence-marketing",   # ← à décommenter quand l'immobilier est validé
    # "retail",
    # "artisan",
    # "fleuriste",
    # "plombier",
    # "restaurant",
]
# Régions : ordre EXACT du select du scrapper (haut → bas), métropole hors Corse.
REGION_ORDER = [
    ("11", "Île-de-France"),
    ("24", "Centre-Val de Loire"),
    ("27", "Bourgogne-Franche-Comté"),
    ("28", "Normandie"),
    ("32", "Hauts-de-France"),
    ("44", "Grand Est"),
    ("52", "Pays de la Loire"),
    ("53", "Bretagne"),
    ("75", "Nouvelle-Aquitaine"),
    ("76", "Occitanie"),
    ("84", "Auvergne-Rhône-Alpes"),
    ("93", "Provence-Alpes-Côte d'Azur"),
]

PLAN_PATH = BASE_DIR / "memory" / "autoscrape" / f"{SITE}-plan.json"
PAUSE_PATH = BASE_DIR / "memory" / "autoscrape" / f"{SITE}-plan-pause.flag"
SERPER_CHECK_THROTTLE = 3600  # s entre deux tests Serper live quand on est bloqué


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state() -> dict:
    try:
        return json.loads(PLAN_PATH.read_text())
    except Exception:
        return {"sector_idx": 0, "region_idx": 0, "history": [], "last_serper_check": 0}


def save_state(st: dict) -> None:
    st["updated_at"] = _now_iso()
    PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLAN_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2))


def current_step(st: dict):
    """(sector, (region_code, region_name)) ou (None, None) si plan terminé."""
    if st["sector_idx"] >= len(PLAN_SECTORS) or st["region_idx"] >= len(REGION_ORDER):
        return None, None
    return PLAN_SECTORS[st["sector_idx"]], REGION_ORDER[st["region_idx"]]


def _advance_region(st: dict, asb, sector: str, region, prog: dict) -> None:
    """Consigne la région finie et avance le curseur (région suivante, puis fin de secteur)."""
    st["history"].append({"sector": sector, "region": region[0], "region_name": region[1],
                          "valid": prog.get("valid"), "status": prog.get("status"),
                          "at": _now_iso()})
    st["region_idx"] += 1
    if st["region_idx"] >= len(REGION_ORDER):
        # Secteur terminé. On NE PASSE PAS au secteur suivant automatiquement :
        # validation manuelle demandée (décommenter dans PLAN_SECTORS + reset region_idx).
        asb.notify_telegram(
            f"🏁 *Plan autoscrape {SITE.upper()}* — secteur *{sector}* terminé "
            f"({len(REGION_ORDER)} régions). Valide les résultats puis active le secteur "
            f"suivant dans autoscrape_plan.PLAN_SECTORS.")
    save_state(st)


def tick(launch: bool = True) -> dict:
    import autoscrape_backend as asb

    if PAUSE_PATH.exists():
        return {"ok": True, "skipped": "plan en pause (flag)"}

    # Un run (du plan ou lancé à la main via l'UI) est déjà actif → on ne double pas.
    cur = asb.read_status(SITE)
    if cur.get("status") in ("running", "starting", "stopping", "cleaning") \
            and (time.time() - cur.get("updated_at", 0) < 300):
        return {"ok": True, "skipped": "un autoscrape est déjà en cours", "active": cur}

    st = load_state()
    sector, region = current_step(st)
    if not sector:
        return {"ok": True, "done": True, "note": "plan terminé (tous secteurs actifs faits)"}

    prog = asb.read_progress(SITE)
    ours = prog.get("region") == region[0] and set(prog.get("sectors") or []) == {sector}

    if ours and prog.get("status") == "done":
        _advance_region(st, asb, sector, region, prog)
        sector, region = current_step(st)
        if not sector:
            return {"ok": True, "done": True, "note": "plan terminé"}
        ours = False  # nouvelle région → run frais

    if ours and prog.get("status") == "blocked_serper":
        # Serper bloqué au dernier run : test live pas plus d'1×/heure, sinon on attend.
        if time.time() - (st.get("last_serper_check") or 0) < SERPER_CHECK_THROTTLE:
            return {"ok": True, "skipped": "Serper bloqué — prochain test dans <1h"}
        st["last_serper_check"] = time.time()
        save_state(st)
        import god_mode_agents as agents
        agents.SERPER_BLOCKED_STATUS = None
        try:
            agents.serper_places("restaurant Paris", location="Paris, France", num=1, site_code=SITE)
        except Exception:
            pass
        if getattr(agents, "SERPER_BLOCKED_STATUS", None):
            return {"ok": True, "skipped": f"Serper toujours bloqué ({agents.SERPER_BLOCKED_STATUS})"}

    if not launch:
        return {"ok": True, "would_run": {"sector": sector, "region": region[0]}}

    # Lance le run de région en détaché (le tick reste instantané pour le cron).
    log = open(BASE_DIR / "logs" / "autoscrape_plan.log", "ab")
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "work"],
                     stdout=log, stderr=log, start_new_session=True, cwd=str(BASE_DIR))
    return {"ok": True, "launched": {"sector": sector, "region": f"{region[1]} ({region[0]})",
                                     "resume": ours}}


def work() -> dict:
    """Run bloquant de la région courante du plan (appelé détaché par tick)."""
    import autoscrape_backend as asb

    # Re-garde anti-course (deux ticks rapprochés)
    cur = asb.read_status(SITE)
    if cur.get("status") in ("running", "starting", "stopping", "cleaning") \
            and (time.time() - cur.get("updated_at", 0) < 300):
        return {"ok": False, "skipped": "déjà en cours"}

    st = load_state()
    sector, region = current_step(st)
    if not sector:
        return {"ok": True, "done": True}

    prog = asb.read_progress(SITE)
    ours = prog.get("region") == region[0] and set(prog.get("sectors") or []) == {sector}
    depts_done = (prog.get("depts_done") or []) if ours else []
    target = TARGET_PER_REGION
    baseline = 0
    if ours:
        baseline = int(prog.get("valid") or 0)   # cumul des runs précédents de la région
        target = max(0, TARGET_PER_REGION - baseline)  # reliquat à scraper
        if target == 0:  # plafond déjà atteint pendant le run interrompu
            _advance_region(st, asb, sector, region, {**prog, "status": "done"})
            return {"ok": True, "advanced": True}

    # Purge un éventuel stop flag résiduel (comme daily_retry)
    sp = asb.stop_path(SITE)
    try:
        if sp.exists():
            sp.unlink()
    except Exception:
        pass

    print(f"[plan] {_now_iso()} run {sector} / {region[1]} ({region[0]}) "
          f"target={target} resume={ours} depts_done={depts_done}", flush=True)
    res = asb.run_autoscrape(SITE, [sector], region=region[0], region_name=region[1],
                             depts_done=depts_done,
                             cities_done=(prog.get("cities_done") or []) if ours else [],
                             cities_dept=prog.get("cities_dept") if ours else None,
                             target_contacts=target,
                             valid_baseline=baseline,
                             progress_cb=lambda s: asb.write_status(SITE, s),
                             should_stop=lambda: sp.exists())

    if res.get("status") == "done":
        final = asb.read_progress(SITE)
        _advance_region(st, asb, sector, region, final)
        nxt = current_step(load_state())
        nxt_label = f"{nxt[1][1]}" if nxt[0] else "plan terminé"
        asb.notify_telegram(f"✅ *Plan autoscrape {SITE.upper()}* — {sector} / {region[1]} : "
                            f"{final.get('valid', 0)} contacts. Suite : {nxt_label}.")
    else:
        print(f"[plan] {_now_iso()} région non terminée (status={res.get('status')}) — "
              f"reprise au prochain tick", flush=True)
    return {"ok": True, "status": res.get("status")}


def status() -> dict:
    import autoscrape_backend as asb
    st = load_state()
    sector, region = current_step(st)
    return {"paused": PAUSE_PATH.exists(),
            "current": {"sector": sector, "region": region},
            "state": st, "live": asb.read_status(SITE), "progress": asb.read_progress(SITE)}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "tick":
        out = tick()
    elif cmd == "work":
        out = work()
    elif cmd == "pause":
        PAUSE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PAUSE_PATH.touch()
        out = {"ok": True, "paused": True}
    elif cmd == "resume":
        PAUSE_PATH.unlink(missing_ok=True)
        out = {"ok": True, "paused": False}
    elif cmd == "reset":
        PLAN_PATH.unlink(missing_ok=True)
        out = {"ok": True, "reset": True}
    else:
        out = status()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
