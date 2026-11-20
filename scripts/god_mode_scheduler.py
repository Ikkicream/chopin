#!/usr/bin/env python3
"""
god_mode_scheduler.py — Programmation des campagnes cold email avec garde-fous.

Règles strictes:
  - GOD MODE actif
  - Template du secteur existe ET verrouillé
  - 0 campagne déjà programmée le jour J pour ce site
  - Pas dimanche
  - Samedi: secteur=immobilier uniquement
  - Plage 8h-20h
  - Lissage Emelia 1 email / 20 min
  - Quota daily_quota (défaut 35)
  - Au moins 1 prospect validated dispo
"""

import os
from datetime import date, datetime, timedelta
from pathlib import Path

import god_mode_backend as gm

BASE_DIR = Path(__file__).parent.parent
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip("'\""))


SECTOR_SATURDAY_ALLOWED = {"immobilier"}
WINDOW_START_H = 8
WINDOW_END_H = 20
LISS_INTERVAL_MIN = 20


def validate_schedule(site: str, sector: str, scheduled_date: date, prospect_count: int = None) -> dict:
    """Retourne {ok: bool, errors: [str], warnings: [str], slots: int}."""
    errors = []
    warnings = []

    state = gm.get_state(site)
    if not state or not state.get("enabled"):
        errors.append("GOD MODE désactivé pour ce site")

    settings = gm.get_settings(site) or {"daily_quota": 35}
    daily_quota = settings.get("daily_quota", 35)

    weekday = scheduled_date.weekday()  # 0=lun, 6=dim
    if weekday == 6:
        errors.append("Dimanche interdit")
    if weekday == 5 and sector not in SECTOR_SATURDAY_ALLOWED:
        errors.append(f"Samedi: seul le secteur '{', '.join(SECTOR_SATURDAY_ALLOWED)}' est autorisé")

    if scheduled_date < date.today():
        errors.append("Date dans le passé")

    if sector not in gm.SECTORS_GOD_MODE:
        errors.append(f"Secteur invalide: {sector}")

    template = gm.get_template(site, sector)
    if not template:
        errors.append(f"Aucun template pour {site}/{sector} — générer d'abord")
    elif not template.get("locked"):
        errors.append(f"Template {site}/{sector} non verrouillé — verrouiller avant de programmer")

    existing = gm.get_today_campaign(site, scheduled_date)
    if existing:
        errors.append(f"Une campagne existe déjà le {scheduled_date} pour {site} (secteur={existing['sector']})")

    available_prospects = [p for p in gm.list_prospects(site, status="validated", sector=sector, limit=1000)]
    available_count = len(available_prospects)
    if available_count == 0:
        errors.append(f"Aucun prospect validated pour {site}/{sector} — lancer un scrape d'abord")

    # Slots possibles
    window_min = (WINDOW_END_H - WINDOW_START_H) * 60
    max_slots_per_day = window_min // LISS_INTERVAL_MIN
    target = prospect_count if prospect_count is not None else min(available_count, daily_quota, max_slots_per_day)
    if target > daily_quota:
        warnings.append(f"target {target} > daily_quota {daily_quota} — sera capé")
        target = daily_quota
    if target > max_slots_per_day:
        warnings.append(f"target {target} > slots possibles {max_slots_per_day} entre 8h-20h à 1/{LISS_INTERVAL_MIN}min")
        target = max_slots_per_day
    if target > available_count:
        warnings.append(f"target {target} > prospects disponibles {available_count}")
        target = available_count

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "slots": target,
        "available_prospects": available_count,
        "daily_quota": daily_quota,
        "weekday": ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"][weekday],
        "template": {"exists": bool(template), "locked": template["locked"] if template else False, "subject": template["subject"] if template else None},
    }


def schedule_campaign(site: str, sector: str, scheduled_date: date, username: str, prospect_count: int = None) -> dict:
    """Programme une campagne après validation. Retourne campaign dict ou raise ValueError."""
    check = validate_schedule(site, sector, scheduled_date, prospect_count)
    if not check["ok"]:
        raise ValueError("; ".join(check["errors"]))

    template = gm.get_template(site, sector)
    target = check["slots"]

    # Sélection des N meilleurs prospects (par score desc)
    available = gm.list_prospects(site, status="validated", sector=sector, limit=1000)
    available.sort(key=lambda p: p.get("score") or 0, reverse=True)
    selected = available[:target]

    cid = gm.create_campaign(
        site_code=site,
        sector=sector,
        scheduled_date=scheduled_date,
        prospect_count=len(selected),
        template_id=template["id"],
        emelia_campaign_id=None,  # MVP: à intégrer Emelia plus tard
        username=username,
    )

    gm.log_action(site, username, "system", "schedule_campaign",
                  resource="campaign", resource_id=cid,
                  payload={"sector": sector, "date": str(scheduled_date), "prospect_count": len(selected),
                           "template_subject": template["subject"]})

    return {
        "campaign_id": cid,
        "site": site,
        "sector": sector,
        "scheduled_date": str(scheduled_date),
        "prospect_count": len(selected),
        "template_subject": template["subject"],
        "selected_emails": [p["email"] for p in selected[:10]],
        "warnings": check["warnings"],
    }


if __name__ == "__main__":
    import sys
    from datetime import date as d
    if len(sys.argv) < 4:
        print("Usage: god_mode_scheduler.py <site> <sector> <YYYY-MM-DD> [validate|schedule]")
        sys.exit(1)
    site, sector, day_str = sys.argv[1], sys.argv[2], sys.argv[3]
    action = sys.argv[4] if len(sys.argv) > 4 else "validate"
    day = d.fromisoformat(day_str)
    if action == "validate":
        print(validate_schedule(site, sector, day))
    else:
        print(schedule_campaign(site, sector, day, "cli"))
