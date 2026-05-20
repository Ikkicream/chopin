#!/usr/bin/env python3
"""
orchestrator.py — Script maître remplaçant Paperclip
Tourne en cron via pm2. Orchestre tous les modules Genesis.

Schedule par défaut:
  - 07:00 UTC chaque jour : briefing.py (Telegram + stats)
  - 08:00 UTC lun-ven     : crm_sync.py (sync réponses → CRM)
  - 09:00 UTC lundi       : campaign_manager.py status
  - 10:00 UTC lundi       : article content (hebdomadaire)

Usage:
  python3 orchestrator.py                    # Lancer selon l'heure actuelle
  python3 orchestrator.py --task briefing    # Forcer une tâche spécifique
  python3 orchestrator.py --task crm-sync
  python3 orchestrator.py --task status      # Vue d'ensemble complète
  python3 orchestrator.py --dry-run          # Simuler sans action réelle
"""

import sys
import json
import subprocess
import argparse
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
LOGS_DIR = BASE_DIR / "memory" / "shared" / "agent-logs"
DASHBOARD_JSON = BASE_DIR / "data" / "dashboard.json"


def log_run(module: str, task: str, status: str, duration_s: float = 0, note: str = ""):
    """Append un run dans le dashboard.json et le log JSONL."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    entry = {
        "id": f"run_{now.strftime('%Y%m%d_%H%M%S')}",
        "date": now.isoformat(),
        "module": module,
        "task": task,
        "status": status,
        "duration": round(duration_s),
        "note": note,
    }

    # Append dans orchestrator.jsonl
    log_file = LOGS_DIR / "orchestrator.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Mettre à jour dashboard.json
    try:
        with open(DASHBOARD_JSON) as f:
            dash = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        dash = {"meta": {}, "modules": [], "runs": [], "sites": {}}

    dash.setdefault("runs", []).append(entry)
    # Garder les 100 derniers runs
    dash["runs"] = dash["runs"][-100:]
    dash["meta"]["lastUpdate"] = now.isoformat()

    with open(DASHBOARD_JSON, "w", encoding="utf-8") as f:
        json.dump(dash, f, indent=2, ensure_ascii=False)


def run_script(script_name: str, args: list[str] = None, dry_run: bool = False) -> tuple[int, str]:
    """Exécute un script Python et retourne (exit_code, output)."""
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name)]
    if args:
        cmd.extend(args)

    print(f"  → Exécution: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=300,  # 5 min max
        )
        output = result.stdout + result.stderr
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT après 5 minutes"
    except Exception as e:
        return 1, str(e)


def task_briefing(dry_run: bool = False) -> bool:
    """Rapport quotidien Emelia + Telegram."""
    print("\n[orchestrator] TÂCHE: briefing")
    import time
    start = time.time()

    args = ["--dry-run"] if dry_run else []
    code, output = run_script("briefing.py", args)

    duration = time.time() - start
    status = "success" if code == 0 else "error"
    print(output)
    log_run("briefing", "daily_briefing", status, duration, output[-200:] if output else "")
    return code == 0


def task_crm_sync(dry_run: bool = False) -> bool:
    """Synchronisation Emelia → Twenty CRM."""
    print("\n[orchestrator] TÂCHE: crm-sync")
    import time
    start = time.time()

    args = [] if not dry_run else []  # crm_sync est dry-run par défaut sans --live
    code, output = run_script("crm_sync.py", args)

    duration = time.time() - start
    status = "success" if code == 0 else "error"
    print(output)
    log_run("crm_sync", "sync_replies", status, duration)
    return code == 0


def task_campaign_status(dry_run: bool = False) -> bool:
    """Rapport statut des campagnes Emelia."""
    print("\n[orchestrator] TÂCHE: campaign-status")
    import time
    start = time.time()

    code, output = run_script("campaign_manager.py", ["--action", "status"])

    duration = time.time() - start
    status = "success" if code == 0 else "error"
    print(output)
    log_run("campaigns", "status_check", status, duration)
    return code == 0


def task_full_status() -> None:
    """Vue d'ensemble complète de tout le système Genesis."""
    print("\n" + "="*65)
    print(" GENESIS — VUE D'ENSEMBLE SYSTÈME")
    print("="*65)
    print(f" Date: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}")
    print("="*65)

    # Vérifier les scripts présents
    scripts = ["briefing.py", "campaign_manager.py", "crm_sync.py", "orchestrator.py"]
    print("\nSCRIPTS:")
    for s in scripts:
        exists = (SCRIPTS_DIR / s).exists()
        print(f"  {'✓' if exists else '✗'} {s}")

    # Lire dashboard.json
    try:
        with open(DASHBOARD_JSON) as f:
            dash = json.load(f)

        emelia = dash.get("emelia", {})
        campaigns = emelia.get("campaigns", [])
        meta = dash.get("meta", {})

        print("\nEMELIA:")
        if campaigns:
            for camp in campaigns:
                icon = {"RUNNING": "🟢", "PAUSED": "⏸", "DONE": "✅"}.get(camp["status"], "❓")
                print(f"  {icon} {camp['name']}: {camp['status']}")
                if camp.get("contacted", 0) > 0:
                    print(f"     Contactés:{camp['contacted']} Réponses:{camp['replied']} Bounces:{camp['bounced']} ({camp['bounce_rate']:.1%})")
        else:
            print("  Aucune campagne (pas encore de briefing lancé)")

        print("\nBUDGET:")
        spent = meta.get("budgetSpentCents", 0) / 100
        total = meta.get("budgetTotalCents", 1000) / 100
        print(f"  ${spent:.2f} / ${total:.2f} cette semaine")

        runs = dash.get("runs", [])
        if runs:
            print(f"\nDERNIERS RUNS ({len(runs)} au total):")
            for run in runs[-5:]:
                icon = "✓" if run["status"] == "success" else "✗"
                ts = run["date"][:16].replace("T", " ")
                print(f"  {icon} [{ts}] {run['module']} — {run['task']}")

    except (FileNotFoundError, json.JSONDecodeError):
        print("\n  Dashboard non initialisé (lancer briefing.py d'abord)")

    # Lire le log Emelia
    campaign_log = BASE_DIR / "memory" / "shared" / "campaigns-log.json"
    if campaign_log.exists():
        with open(campaign_log) as f:
            clog = json.load(f)
        entries = clog.get("entries", [])
        if entries:
            print(f"\nACTIONS CAMPAGNES: {len(entries)} entrée(s)")
            for e in entries[-3:]:
                print(f"  [{e['date'][:10]}] {e['action']}")

    print("\n" + "="*65)


def determine_scheduled_task() -> str | None:
    """
    Détermine la tâche à lancer selon l'heure et le jour actuels.
    Retourne le nom de la tâche ou None si rien à faire maintenant.
    """
    now = datetime.now(timezone.utc)
    hour = now.hour
    weekday = now.weekday()  # 0=lundi, 6=dimanche

    # 07:00 UTC tous les jours → briefing
    if hour == 7:
        return "briefing"

    # 08:00 UTC lun-ven → crm-sync
    if hour == 8 and weekday < 5:
        return "crm-sync"

    # 09:00 UTC lundi → status campagnes
    if hour == 9 and weekday == 0:
        return "campaign-status"

    return None


def main():
    parser = argparse.ArgumentParser(description="Orchestrateur Genesis — remplace Paperclip")
    parser.add_argument("--task", choices=["briefing", "crm-sync", "campaign-status", "status"],
                        help="Tâche à exécuter (défaut: auto selon heure)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulation — aucune action réelle")
    args = parser.parse_args()

    dry_run = args.dry_run

    if dry_run:
        print("⚠ MODE DRY-RUN actif\n")

    print(f"[orchestrator] Démarrage {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}")

    # Déterminer la tâche
    task = args.task
    if not task:
        task = determine_scheduled_task()
        if task:
            print(f"[orchestrator] Tâche planifiée détectée: {task}")
        else:
            print("[orchestrator] Aucune tâche planifiée à cette heure")
            print("  Lancer avec --task <nom> pour forcer une tâche")
            print("  Lancer avec --task status pour la vue d'ensemble")
            task_full_status()
            return

    # Exécuter la tâche
    success = False

    if task == "briefing":
        success = task_briefing(dry_run=dry_run)

    elif task == "crm-sync":
        success = task_crm_sync(dry_run=dry_run)

    elif task == "campaign-status":
        success = task_campaign_status(dry_run=dry_run)

    elif task == "status":
        task_full_status()
        return

    print(f"\n[orchestrator] {'✓ Succès' if success else '✗ Erreur'}")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
