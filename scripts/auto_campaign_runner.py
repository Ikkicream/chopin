#!/usr/bin/env python3
"""
auto_campaign_runner.py — Orchestrateur des campagnes cold-email AUTOMATISÉES.

Tourne en PROCESS DÉTACHÉ (jamais thread API — DuckDB 1 writer), lancé par le cron PM2
(1 run/jour/site) ou par le trigger manuel de l'API. Pour chaque campagne 'active' :

  cap = min(daily_target, warmup_quota(sender) − déjà_envoyé_aujourd'hui)
  boucle :  pick pool (secteur) → push à la campagne Emelia
            si pool sec ET source_mode='autoscrape' → run_autoscrape(dept) INLINE → re-pick
  arrêts : pushed>=cap | pool vide | scrape bloqué | no_progress>=3 | timeout | stop/pause

La boucle est pilotée sur le PUSH (synchrone) — JAMAIS sur l'envoi Emelia (asynchrone) —
pour éliminer tout risque de boucle infinie. Statut live dans
memory/auto_campaigns/<site>-status.json. Flags stop/pause par fichier.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone, date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

import auto_campaign_backend as ab
import workflow_emelia_push as wep
import contacts_pool_backend as pool
import autoscrape_backend as asb
from autoscrape_backend import notify_telegram

STATUS_DIR = BASE_DIR / "memory" / "auto_campaigns"

MAX_NO_PROGRESS = 3        # tours de scrape sans nouveau contact piochable → stop
MAX_RUN_SECONDS = 4 * 3600 # borne dure du wall-clock par run de campagne


# ── Statut / flags fichier (pattern autoscrape) ────────────────────────────────
def status_path(site: str) -> Path:
    return STATUS_DIR / f"{site}-status.json"


def stop_path(site: str) -> Path:
    return STATUS_DIR / f"{site}-stop.flag"


def pause_path(camp_id: str) -> Path:
    return STATUS_DIR / f"{camp_id}-pause.flag"


def write_status(site: str, state: dict) -> None:
    try:
        STATUS_DIR.mkdir(parents=True, exist_ok=True)
        st = dict(state)
        st["updated_at"] = time.time()
        status_path(site).write_text(json.dumps(st, ensure_ascii=False))
    except Exception:
        pass


def read_status(site: str) -> dict:
    try:
        p = status_path(site)
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return {"status": "idle"}


# ── Cap warmup ─────────────────────────────────────────────────────────────────
def compute_cap(site: str, sender_email: str, daily_target: int) -> int:
    """cap = max(0, min(cible, quota_warmup(sender) − déjà_envoyé_aujourd'hui)).
    'déjà_envoyé' = events SENT réels (emelia_events) → respecte le warmup même
    multi-campagnes par sender."""
    try:
        quota = wep.daily_warmup_quota(sender_email)
        sent_today = wep.emelia_sent_today_by_sender(sender_email)
    except Exception:
        quota, sent_today = 0, 0
    return max(0, min(int(daily_target or 0), int(quota) - int(sent_today)))


# ── Run d'UNE campagne ─────────────────────────────────────────────────────────
def run_one_campaign(camp: dict, should_stop=None, on_progress=None, dry_run: bool = False) -> dict:
    cid = camp["id"]
    site = camp["site_code"]
    sender = camp["sender_email"]
    sectors = [s for s in (camp.get("sectors") or []) if s]
    primary = sectors[0] if sectors else None
    target = int(camp.get("daily_target") or 0)
    cap = compute_cap(site, sender, target)

    if not primary:
        return {"campaign_id": cid, "pushed": 0, "end_reason": "no_sector", "cap": cap}

    # DRY-RUN : pas d'effet de bord (ni run, ni push, ni scrape) — juste un diagnostic.
    if dry_run:
        avail = sum(pool.count_available_for_sector(site, s) for s in sectors)
        would_scrape = avail < cap and camp.get("source_mode") == "autoscrape" and bool(camp.get("dept"))
        return {"campaign_id": cid, "name": camp.get("name"), "cap": cap, "target": target,
                "available_pool": avail, "would_scrape": would_scrape, "end_reason": "dry_run"}

    run_id = ab.start_run(cid, site, cap)
    pushed = 0
    scrape_invoked = False
    end_reason = None
    err = None

    def emit(extra=None):
        if on_progress:
            try:
                on_progress({"campaign_id": cid, "name": camp.get("name"), "sector": primary,
                             "cap": cap, "pushed": pushed, "phase": (extra or "pushing")})
            except Exception:
                pass

    try:
        if cap <= 0:
            end_reason = "warmup_cap"
        else:
            emelia_cid = camp.get("emelia_campaign_id")
            if not emelia_cid:
                emelia_cid = wep.ensure_campaign_for_auto(site, primary)
                if emelia_cid:
                    ab.update_auto_campaign(cid, emelia_campaign_id=emelia_cid)
            if not emelia_cid:
                end_reason = "no_campaign"
            else:
                no_progress = 0
                deadline = time.monotonic() + MAX_RUN_SECONDS
                while pushed < cap:
                    if should_stop and should_stop():
                        end_reason = "stopped"; break
                    if pause_path(cid).exists():
                        end_reason = "paused"; break
                    if time.monotonic() > deadline:
                        end_reason = "timeout"; break

                    progressed = 0
                    for sec in sectors:
                        if pushed >= cap:
                            break
                        res = wep.push_batch_to_campaign(site, emelia_cid, sec, cap - pushed, sender)
                        progressed += res.get("pushed", 0)
                        pushed += res.get("pushed", 0)
                    emit()

                    if pushed >= cap:
                        end_reason = "target_reached"; break

                    if progressed == 0:
                        # Pool sec pour tous les secteurs.
                        if camp.get("source_mode") == "autoscrape" and camp.get("dept"):
                            scrape_invoked = True
                            emit("scraping")
                            cum = asb.run_autoscrape(site, sectors, camp["dept"], should_stop=should_stop)
                            st = (cum or {}).get("status")
                            if st in ("blocked_credits", "stalled"):
                                end_reason = "scrape_blocked"; break
                            no_progress += 1
                            if no_progress >= MAX_NO_PROGRESS:
                                end_reason = "no_progress"; break
                        else:
                            end_reason = "pool_exhausted"; break
                    else:
                        no_progress = 0
                if end_reason is None:
                    end_reason = "target_reached" if pushed >= cap else "done"
    except Exception as e:
        end_reason = "error"
        err = str(e)

    sent_observed = wep.emelia_sent_today_by_sender(sender)
    ab.finish_run(run_id, pushed, sent_observed, end_reason, scrape_invoked, err)
    ab.record_campaign_result(cid, pushed, err or (end_reason if end_reason in
                              ("scrape_blocked", "no_progress", "timeout", "pool_exhausted", "warmup_cap") else None))

    if end_reason in ("scrape_blocked", "no_progress", "timeout", "error"):
        notify_telegram(
            f"⚠️ *Campagne auto {site.upper()}* « {camp.get('name')} » arrêtée : {end_reason}."
            f"\n{pushed}/{cap} poussés aujourd'hui." + (f"\nErreur : {err}" if err else ""))

    return {"campaign_id": cid, "name": camp.get("name"), "pushed": pushed, "cap": cap,
            "target": target, "end_reason": end_reason, "scrape_invoked": scrape_invoked,
            "sent_observed": sent_observed, "error": err}


# ── Run de TOUTES les campagnes actives d'un site ──────────────────────────────
def run_site(site: str, only_campaign_id: str | None = None, dry_run: bool = False,
             should_stop=None) -> dict:
    camps = ab.list_active(site)
    if only_campaign_id:
        camps = [c for c in camps if c["id"] == only_campaign_id]

    results = []
    status = {"site": site, "status": "running", "started_at": time.time(),
              "current": None, "campaigns": []}
    write_status(site, status)

    def _emit_campaign_progress(p):
        status["current"] = p
        write_status(site, status)

    for camp in camps:
        if should_stop and should_stop():
            break
        # Garde "1 run terminé/jour/sender" (idempotence relance PM2) — sauf trigger manuel ciblé.
        if not only_campaign_id and not dry_run and \
           ab.sender_has_completed_run_today(camp["sender_email"]):
            results.append({"campaign_id": camp["id"], "name": camp.get("name"),
                            "end_reason": "already_ran_today", "pushed": 0})
            continue
        status["current"] = {"campaign_id": camp["id"], "name": camp.get("name"), "phase": "starting"}
        write_status(site, status)
        res = run_one_campaign(camp, should_stop=should_stop, on_progress=_emit_campaign_progress,
                               dry_run=dry_run)
        results.append(res)
        status["campaigns"] = results
        write_status(site, status)

    status["status"] = "done"
    status["current"] = None
    status["finished_at"] = time.time()
    status["campaigns"] = results
    write_status(site, status)
    return {"site": site, "results": results}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True)
    ap.add_argument("--campaign-id", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sp = stop_path(args.site)
    try:
        if sp.exists():
            sp.unlink()
    except Exception:
        pass

    def should_stop():
        return sp.exists()

    try:
        out = run_site(args.site, only_campaign_id=args.campaign_id,
                       dry_run=args.dry_run, should_stop=should_stop)
        print(json.dumps(out, ensure_ascii=False))
    except Exception as e:
        cur = read_status(args.site)
        cur.update({"status": "error", "message": str(e), "finished_at": time.time()})
        write_status(args.site, cur)
        return 1
    finally:
        try:
            if sp.exists():
                sp.unlink()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
