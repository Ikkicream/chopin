"""
deliverability_agent.py — Garde-fou de délivrabilité : règles dures + explication IA.

Principe : un MOTEUR DE RÈGLES déterministe fixe le plafond d'envoi/jour par canal (on ne crame
jamais le domaine), puis une couche IA (DeepSeek) explique en clair la cadence et alerte. L'IA ne
décide JAMAIS des plafonds — elle ne fait qu'expliquer le plan calculé par les règles.

- channel_caps(site, channel)        : cap dur/jour + barème de montée (ramp)
- plan_cadence(site, channel, n, d0) : planning jour/jour + faisabilité + warnings
- explain(plan, channel, n)          : texte court (IA + fallback déterministe)
"""
from __future__ import annotations

from datetime import date as _date, timedelta

# Plafonds d'envoi/jour PLATS par canal (validés user 2026-06-24).
DAILY_CAP = {"emelia": 30, "sweego": 1000, "maildoso": 300}

# Fenêtre d'étalement raisonnable par canal : au-delà → mauvais canal (suggère un autre).
# Pensée pour : Emelia = petits lots ciblés ; Sweego = volume ; Maildoso = intermédiaire.
MAX_DAYS = {"emelia": 30, "sweego": 60, "maildoso": 60}


def channel_caps(site: str, channel: str) -> dict:
    """Plafond d'envoi par jour pour un canal (plat). `plateau` = cap stable,
    `ramp` = [plateau] (pas de montée progressive — cap fixe)."""
    channel = (channel or "").lower()
    cap = DAILY_CAP.get(channel, 0)
    return {"channel": channel, "ramp": [cap], "plateau": cap,
            "max_days": MAX_DAYS.get(channel, 30)}


def _cap_for_day(caps: dict, day_index: int) -> int:
    """Cap autorisé au jour day_index (0-based) selon la ramp puis le plateau."""
    ramp = caps.get("ramp") or [0]
    if day_index < len(ramp):
        return int(ramp[day_index] or 0)
    return int(caps.get("plateau") or 0)


def plan_cadence(site: str, channel: str, target_size: int, start_date: _date) -> dict:
    """Calcule le planning jour/jour pour envoyer target_size emails en respectant la ramp/cap.
    Retourne {feasible, schedule:[{date,count}], total_days, daily_cap, suggested_channel, warnings}."""
    channel = (channel or "").lower()
    caps = channel_caps(site, channel)
    warnings: list[str] = []
    schedule: list[dict] = []

    plateau = int(caps.get("plateau") or 0)
    if plateau <= 0 and not any(caps.get("ramp") or []):
        # Aucun envoi possible (ex. Emelia sans expéditeur actif, Maildoso désactivé)
        sugg = "sweego" if channel != "sweego" else None
        warnings.append(f"Aucune capacité d'envoi sur {channel} aujourd'hui.")
        return {"feasible": False, "schedule": [], "total_days": 0, "daily_cap": 0,
                "suggested_channel": sugg, "warnings": warnings, "channel": channel,
                "target_size": target_size}

    remaining = int(target_size)
    day_index = 0
    max_days = int(caps.get("max_days") or 30)
    while remaining > 0 and day_index < max_days:
        cap = _cap_for_day(caps, day_index)
        if cap <= 0:
            break
        count = min(cap, remaining)
        schedule.append({"date": (start_date + timedelta(days=day_index)).isoformat(),
                         "count": count})
        remaining -= count
        day_index += 1

    feasible = remaining <= 0
    if not feasible:
        # Trop gros pour ce canal dans la fenêtre raisonnable
        sugg = None
        if channel == "emelia":
            sugg = "sweego"
            warnings.append(
                f"{target_size} contacts en cold email dépassent ta capacité de chauffe "
                f"(plafond {plateau}/j). Il faudrait > {max_days} jours.")
        elif channel == "sweego":
            warnings.append(
                f"{target_size} en masse dépasse {plateau}/j sur {max_days} jours. "
                f"Réduis le volume ou étale sur plusieurs campagnes.")
        else:
            sugg = "sweego"
            warnings.append(f"Canal {channel} indisponible pour ce volume.")
        return {"feasible": False, "schedule": schedule, "total_days": day_index,
                "daily_cap": plateau, "suggested_channel": sugg, "warnings": warnings,
                "channel": channel, "target_size": target_size}

    if day_index > 1:
        warnings.append(f"Envoi étalé sur {day_index} jours pour préserver la réputation.")
    return {"feasible": True, "schedule": schedule, "total_days": day_index,
            "daily_cap": plateau, "suggested_channel": None, "warnings": warnings,
            "channel": channel, "target_size": target_size}


# ── Explication IA (avec fallback déterministe) ─────────────────────────────────
def _fallback_text(plan: dict, channel: str, target_size: int) -> str:
    if plan.get("feasible"):
        d = plan.get("total_days", 1)
        if d <= 1:
            return f"✅ {target_size} emails envoyés en 1 jour via {channel}. Cadence sûre."
        return (f"✅ {target_size} emails étalés sur {d} jours via {channel} "
                f"(max {plan.get('daily_cap')}/j) pour préserver ta réputation d'expéditeur.")
    sugg = plan.get("suggested_channel")
    base = " ".join(plan.get("warnings", [])) or f"Cadence infaisable sur {channel}."
    if sugg:
        base += f" Recommandation : utilise plutôt **{sugg}**."
    return "⚠️ " + base


def explain(plan: dict, channel: str, target_size: int) -> str:
    """Phrase d'explication claire pour l'utilisateur. IA si dispo, sinon fallback déterministe."""
    try:
        import llm_call
        sched = plan.get("schedule", [])
        sched_str = ", ".join(f"{s['date']}:{s['count']}" for s in sched[:8])
        prompt = (
            "Tu es un expert délivrabilité email. En 2 phrases max, en français simple, explique à "
            "un utilisateur non-technique la cadence d'envoi suivante et pourquoi elle protège sa "
            "réputation. Ne propose AUCUN autre plafond que celui donné.\n"
            f"Canal: {channel}\nVolume cible: {target_size}\nFaisable: {plan.get('feasible')}\n"
            f"Plafond/jour: {plan.get('daily_cap')}\nJours: {plan.get('total_days')}\n"
            f"Planning: {sched_str}\nAlertes: {plan.get('warnings')}\n"
            f"Canal suggéré si infaisable: {plan.get('suggested_channel')}"
        )
        txt = llm_call.call_llm(prompt, max_tokens=160, temperature=0.4,
                                module="deliverability_agent", action="explain_cadence")
        return (txt or "").strip() or _fallback_text(plan, channel, target_size)
    except Exception:
        return _fallback_text(plan, channel, target_size)


if __name__ == "__main__":
    import json
    for ch, n in [("emelia", 30000), ("sweego", 30000), ("sweego", 200), ("emelia", 50)]:
        p = plan_cadence("lcr", ch, n, _date.today())
        print(ch, n, "→ feasible=", p["feasible"], "days=", p["total_days"],
              "| ", _fallback_text(p, ch, n))
