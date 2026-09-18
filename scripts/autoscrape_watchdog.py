#!/usr/bin/env python3
"""
autoscrape_watchdog.py — Veilleur : détecte un scrape mort et le relance là où il s'était arrêté.

Pourquoi ce script existe (constat du 2026-07-30) : quand le process d'autoscrape est tué
net (signal, OOM, redémarrage), il n'écrit aucun statut final. Les fichiers restent sur
« running », alors que plus rien ne tourne. Or TOUS les mécanismes de reprise
(retry quotidien 6h, plan toutes les 30 min, bouton « Relancer » de l'UI) exigent un statut
d'arrêt : un run figé sur « running » était donc ignoré indéfiniment. Un scrape est ainsi
resté bloqué à 297/1000 contacts pendant des heures sans que rien ne le reprenne.

Le veilleur ferme ce trou : il requalifie le run mort en « interrupted » (via
`mark_interrupted`) puis relance `autoscrape_backend --resume`, qui saute les départements
et villes déjà faits et ne réclame que le reliquat de la cible.

Usage :
  python3 scripts/autoscrape_watchdog.py            # tous les sites
  python3 scripts/autoscrape_watchdog.py --site lcr
  python3 scripts/autoscrape_watchdog.py --dry-run  # diagnostic seul, ne relance rien

Cron (minuit) :
  0 0 * * * cd /home/autoblog/genesis && python3 scripts/autoscrape_watchdog.py >> logs/autoscrape_watchdog.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SITES = ("lcr", "mkd")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def check_site(site: str, dry_run: bool = False) -> dict:
    """Diagnostique un site et relance son scrape si celui-ci est mort en cours de route."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import autoscrape_backend as asb

    st = asb.read_status(site)
    prog = asb.read_progress(site)
    status = st.get("status", "idle")
    age = asb.heartbeat_age(site)
    age_min = round(age / 60, 1) if age != float("inf") else None  # None : jamais démarré

    out = {"site": site, "status": status, "heartbeat_min": age_min,
           "valid": st.get("valid"), "target": st.get("target_contacts")}

    # Hors fenêtre nocturne, on ne lance jamais rien : la journée doit rester libre de
    # tout verrou sur contacts.duckdb.
    in_window, why = asb.within_scrape_window()
    if not in_window:
        out["action"] = f"rien — {why}"
        return out

    # 1) Demande programmée pendant la journée : c'est l'heure, on la démarre.
    pending = asb.read_pending(site)
    if pending and status not in asb.LIVE_STATUSES:
        out["action"] = "DÉMARRE la demande programmée"
        out["demande"] = {k: pending.get(k) for k in ("sectors", "region", "dept", "all_regions", "target_contacts")}
        if dry_run:
            out["action"] += " (dry-run)"
            return out
        cmd = ["python3", "scripts/autoscrape_backend.py", "--site", site,
               "--sectors", ",".join(pending.get("sectors") or []),
               "--target-contacts", str(int(pending.get("target_contacts") or 0))]
        if pending.get("all_regions"):
            cmd.append("--all-regions")
        elif pending.get("region"):
            cmd += ["--region", str(pending["region"])]
        elif pending.get("dept"):
            cmd += ["--dept", str(pending["dept"])]
        log = BASE_DIR / "logs" / f"autoscrape-{site}.log"
        with open(log, "a") as f:
            f.write(f"\n=== [veilleur {_now()}] démarrage de la demande programmée ===\n")
            subprocess.Popen(cmd, cwd=str(BASE_DIR), start_new_session=True,
                             stdout=f, stderr=subprocess.STDOUT)
        asb.clear_pending(site)
        return out

    if not prog:
        out["action"] = "rien — aucune progression enregistrée"
        return out

    # Un run réellement vivant bat toutes les quelques secondes : on ne le touche jamais.
    if status in asb.LIVE_STATUSES and not asb.is_stalled(site):
        out["action"] = "rien — scrape actif (battement récent)"
        return out

    stalled = asb.is_stalled(site)
    if stalled:
        out["requalifie"] = "running → interrupted"
        # Un dry-run doit rester en LECTURE SEULE : on n'écrit la requalification que
        # pour une vraie passe, et on raisonne sur le statut effectif dans les deux cas.
        if not dry_run:
            asb.mark_interrupted(site, f"Veilleur : aucun battement depuis {age_min} min.")
            prog = asb.read_progress(site)

    effective = "interrupted" if stalled else prog.get("status")
    if effective not in asb.RESUMABLE_STATUSES:
        out["action"] = f"rien — statut « {effective} » non reprenable"
        return out

    # Reliquat : inutile de relancer une cible déjà atteinte.
    target = int(prog.get("target_contacts") or 0)
    done = int(prog.get("valid") or 0)
    if target and done >= target:
        out["action"] = f"rien — cible atteinte ({done}/{target})"
        return out

    region, dept = prog.get("region"), prog.get("dept") or prog.get("cities_dept")
    out["perimetre"] = f"région {region}" if region else f"dept {dept}"
    out["reliquat"] = f"{done}/{target}" if target else "illimité"

    if dry_run:
        out["action"] = "RELANCERAIT (dry-run)"
        return out

    log = BASE_DIR / "logs" / f"autoscrape-{site}.log"
    with open(log, "a") as f:
        f.write(f"\n=== [veilleur {_now()}] reprise automatique après arrêt anormal ===\n")
        subprocess.Popen(["python3", "scripts/autoscrape_backend.py", "--site", site, "--resume"],
                         cwd=str(BASE_DIR), start_new_session=True,
                         stdout=f, stderr=subprocess.STDOUT)
    out["action"] = "RELANCÉ (--resume)"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=None, help="lcr | mkd (défaut : les deux)")
    ap.add_argument("--dry-run", action="store_true", help="diagnostic seul")
    args = ap.parse_args()

    results = [check_site(s, dry_run=args.dry_run) for s in ([args.site] if args.site else SITES)]
    print(f"[veilleur autoscrape] {_now()}")
    for r in results:
        print("  " + json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
