#!/usr/bin/env python3
"""
autoscrape_backend.py — Autoscrape continu d'un DÉPARTEMENT pour un/des secteur(s).

Idée (demande user 2026-06-01) : on choisit un département + un secteur, et ça scrape
VILLE PAR VILLE en continu jusqu'à épuisement du département OU blocage des crédits
Serper. Plus aucun paramétrage manuel (max par ville / plafond). Au blocage crédit :
statut 'blocked_credits' + alerte Telegram.

Tourne dans un thread géré par l'API (cf. endpoints /autoscrape/* dans api.py).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
SERPER_BALANCE_FILE = BASE_DIR / "memory" / "seo" / "serper-balance.json"
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"

# Réglages internes (volontairement non exposés à l'utilisateur)
PER_CITY = 15          # objectif de contacts gardés par ville
MAX_PAGES = 4          # pagination Serper max par requête
CREDIT_FLOOR = 60      # on stoppe quand le solde Serper estimé descend sous ce seuil
ZERO_STREAK_STOP = 3   # n villes consécutives à 0 commerce examiné ⇒ on suppose un blocage


def _env(key: str) -> str:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith(key + "=") and "=" in line:
                return line.split("=", 1)[1].strip("'\"")
    return ""


def notify_telegram(message: str) -> None:
    token, chat = _env("TELEGRAM_TOKEN"), _env("TELEGRAM_CHAT_ID") or _env("TELEGRAM_CHAT")
    if not token or not chat:
        return
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except Exception:
        pass


def serper_available() -> int | None:
    """Crédits Serper restants estimés = solde snapshot − conso depuis le snapshot
    (table god_mode_serper_calls). None si pas de snapshot configuré."""
    try:
        cfg = json.loads(SERPER_BALANCE_FILE.read_text())
        balance, snap = cfg.get("balance"), cfg.get("snapshot_at")
        if balance is None or not snap:
            return None
        import duckdb
        c = duckdb.connect(str(GOD_DB), read_only=True)
        used = c.execute(
            "SELECT COALESCE(SUM(credits), 0) FROM god_mode_serper_calls WHERE created_at >= ?::TIMESTAMP",
            [snap[:19].replace("T", " ")]).fetchone()[0]
        c.close()
        return max(0, int(balance) - int(used or 0))
    except Exception:
        return None


def run_autoscrape(site: str, sectors, dept: str,
                   per_city: int = PER_CITY, credit_floor: int = CREDIT_FLOOR,
                   max_pages: int = MAX_PAGES,
                   progress_cb=None, should_stop=None) -> dict:
    """Scrape toutes les villes (pop≥10k) du `dept` pour chaque secteur, en continu,
    jusqu'à blocage crédit / stop / épuisement."""
    import sys
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from workflow_geo import list_cities
    import god_mode_agents as agents
    import god_mode_backend as gm

    if isinstance(sectors, str):
        sectors = [sectors]
    sectors = [s.strip() for s in (sectors or []) if s and s.strip()]
    cities = [c.get("name") for c in list_cities(dept, None, min_pop=10000) if c.get("name")]

    cum = {
        "site": site, "dept": dept, "sectors": sectors,
        "cities_total": len(cities), "cities_done": 0, "current_city": None,
        "examined": 0, "valid": 0, "rejected": 0, "errors": 0, "kept_total": 0,
        "serper_available": serper_available(),
        "status": "running", "blocked": False, "stopped": False,
        "started_at": time.time(), "message": None,
    }

    def emit():
        if progress_cb:
            try:
                progress_cb(dict(cum))
            except Exception:
                pass

    emit()
    if not sectors or not cities:
        cum["status"] = "done"
        cum["message"] = "Aucune ville ou secteur." if not cities else "Aucun secteur."
        emit()
        return cum

    zero_streak = 0
    for city in cities:
        if should_stop and should_stop():
            cum["stopped"] = True
            cum["status"] = "stopped"
            break

        avail = serper_available()
        cum["serper_available"] = avail
        if avail is not None and avail <= credit_floor:
            cum["blocked"] = True
            cum["status"] = "blocked_credits"
            cum["message"] = f"Crédits Serper bas (~{avail}). Arrêt automatique."
            notify_telegram(
                f"⚠️ *Autoscrape {site.upper()}* stoppé — crédits Serper bas (~{avail}).\n"
                f"Dept {dept} · {', '.join(sectors)}\n"
                f"{cum['valid']} contacts gardés sur {cum['cities_done']}/{len(cities)} villes."
            )
            break

        cum["current_city"] = city
        emit()

        city_examined = 0
        for sector in sectors:
            if should_stop and should_stop():
                break
            try:
                r = agents.scrape_sector(site, sector, cities=[city],
                                         max_per_city=per_city, global_cap=per_city,
                                         max_pages=max_pages, username="autoscrape")
            except Exception as e:
                cum["errors"] += 1
                r = {"scraped": 0, "valid": 0, "rejected": 0, "errors": 1}
            cum["examined"] += r.get("scraped", 0)
            cum["valid"] += r.get("valid", 0)
            cum["rejected"] += r.get("rejected", 0)
            cum["errors"] += r.get("errors", 0)
            city_examined += r.get("scraped", 0)

        cum["cities_done"] += 1
        cum["kept_total"] = cum["valid"]
        emit()

        # Détection réactive d'un blocage (Serper renvoie vide en boucle)
        zero_streak = zero_streak + 1 if city_examined == 0 else 0
        if zero_streak >= ZERO_STREAK_STOP:
            cum["blocked"] = True
            cum["status"] = "blocked_credits"
            cum["message"] = f"{zero_streak} villes sans résultat d'affilée — probable blocage Serper."
            notify_telegram(
                f"⚠️ *Autoscrape {site.upper()}* stoppé — Serper ne renvoie plus rien "
                f"({zero_streak} villes vides, probable épuisement crédits).\n"
                f"Dept {dept} · {', '.join(sectors)} · {cum['valid']} contacts gardés."
            )
            break

    if cum["status"] == "running":
        cum["status"] = "done"
        cum["message"] = f"Département {dept} terminé."
    cum["serper_available"] = serper_available()
    cum["finished_at"] = time.time()
    emit()

    try:
        gm.log_action(site, "system", "autoscrape", "autoscrape_done",
                      resource="dept", resource_id=dept, payload=cum,
                      success=not cum["blocked"])
    except Exception:
        pass
    return cum
