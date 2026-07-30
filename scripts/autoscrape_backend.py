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

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
SERPER_BALANCE_FILE = BASE_DIR / "memory" / "seo" / "serper-balance.json"
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"
STATUS_DIR = BASE_DIR / "memory" / "autoscrape"   # statut + flag stop (process détaché)


def status_path(site: str) -> Path:
    return STATUS_DIR / f"{site}-status.json"


def stop_path(site: str) -> Path:
    return STATUS_DIR / f"{site}-stop.flag"


def progress_path(site: str) -> Path:
    """Fichier de reprise région : mémorise région + secteurs + départements déjà finis,
    pour que le retry quotidien reprenne là où Serper nous a stoppés."""
    return STATUS_DIR / f"{site}-region-progress.json"


def read_progress(site: str) -> dict:
    try:
        p = progress_path(site)
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return {}


def write_progress(site: str, data: dict) -> None:
    try:
        STATUS_DIR.mkdir(parents=True, exist_ok=True)
        d = dict(data)
        d["updated_at"] = time.time()
        progress_path(site).write_text(json.dumps(d, ensure_ascii=False))
    except Exception:
        pass


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


# Un run tué net (SIGKILL, OOM, reboot) n'écrit aucun statut final : les fichiers restent
# sur « running » et TOUS les mécanismes de reprise l'ignorent, puisqu'ils exigent un statut
# d'arrêt. Le run reste alors figé indéfiniment. On considère donc qu'au-delà de ce délai
# sans battement de cœur, le run est mort — l'API affichait déjà « interrupted » à la lecture,
# mais sans jamais le persister.
STALE_AFTER_SECONDS = 15 * 60
LIVE_STATUSES = ("running", "starting", "stopping", "cleaning")

# ── Fenêtre de scraping (demande user 2026-07-30) ─────────────────────────────
# Le scraping n'a lieu QUE la nuit, de 22h00 à 08h00 heure de Paris. Raison concrète :
# DuckDB n'admet qu'un écrivain OU des lecteurs. Un scrape en journée verrouille
# contacts.duckdb et rend les compteurs de l'interface (segments, cible de campagne,
# acquisition) indisponibles. En le confinant la nuit, on travaille au calme le jour.
# Le serveur tourne en UTC : la comparaison se fait explicitement en Europe/Paris.
SCRAPE_START = "22:00"
SCRAPE_END = "08:00"
SCRAPE_TZ = "Europe/Paris"
PENDING_NOTE = f"Programmé — démarrage automatique à {SCRAPE_START}"


def _paris_now():
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        return _dt.now(ZoneInfo(SCRAPE_TZ))
    except Exception:  # noqa: BLE001
        return _dt.now()


def within_scrape_window(now=None) -> tuple[bool, str]:
    """Peut-on scraper maintenant ? → (autorisé, motif du refus).

    Fenêtre à cheval sur minuit : autorisée si l'heure est >= 22:00 OU < 08:00.
    """
    now = now or _paris_now()
    hhmm = now.strftime("%H:%M")
    if hhmm >= SCRAPE_START or hhmm < SCRAPE_END:
        return True, ""
    return False, (f"scraping réservé à la plage {SCRAPE_START}–{SCRAPE_END} "
                   f"(il est {hhmm} à Paris)")


def pending_path(site: str) -> Path:
    """Demande de scrape en attente d'ouverture de la fenêtre nocturne."""
    return STATUS_DIR / f"{site}-pending.json"


def read_pending(site: str) -> dict:
    try:
        p = pending_path(site)
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return {}


def write_pending(site: str, req: dict) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    d = dict(req)
    d["queued_at"] = time.time()
    pending_path(site).write_text(json.dumps(d, ensure_ascii=False))


def clear_pending(site: str) -> None:
    try:
        pending_path(site).unlink(missing_ok=True)
    except Exception:
        pass


def heartbeat_age(site: str) -> float:
    """Secondes écoulées depuis le dernier battement du run (inf si jamais écrit)."""
    ts = read_status(site).get("updated_at")
    return (time.time() - ts) if ts else float("inf")


def is_stalled(site: str) -> bool:
    """Le run se dit vivant mais ne bat plus → processus mort sans statut final."""
    return (read_status(site).get("status") in LIVE_STATUSES
            and heartbeat_age(site) > STALE_AFTER_SECONDS)


def mark_interrupted(site: str, reason: str = "") -> dict:
    """Fige un run mort en « interrupted » dans le statut ET la progression, afin qu'il
    redevienne reprenable (bouton Relancer, retry quotidien, plan, veilleur de minuit)."""
    msg = reason or "Processus interrompu sans statut final."
    st = read_status(site)
    if st.get("status") in LIVE_STATUSES:
        st.update({"status": "interrupted", "message": msg, "finished_at": time.time()})
        write_status(site, st)
    prog = read_progress(site)
    if prog and prog.get("status") not in RESUMABLE_STATUSES:
        write_progress(site, {**prog, "status": "interrupted", "message": msg})
    return {"ok": True, "site": site, "status": "interrupted", "message": msg}

# Réglages internes (volontairement non exposés à l'utilisateur)
PER_CITY = 15          # objectif de contacts gardés par ville (Serper)
MAX_PAGES = 4          # pagination Serper max par requête
# NB : plus de "credit floor" préemptif ni de "volume cible". Demande user (2026-06-16) :
# on scrape EN CONTINU tant que Serper ne nous stoppe pas réellement (HTTP 429/402/403).
# Le seul vrai signal d'arrêt = SERPER_BLOCKED_STATUS levé par god_mode_agents.serper_places.
MAX_RUN_SECONDS = 6 * 3600  # garde-temps DUR (6 h) — anti-thread-zombie, pas une limite métier
TARGET_CONTACTS = 0    # 0 = illimité (scrape tout) ; N > 0 = stop quand valid >= N

# Grandes villes = 1 seule commune INSEE dans la donnée géo → on les éclate en
# arrondissements pour scraper réellement toute la ville (Serper localise bien par arr.).
ARRONDISSEMENTS = {"Paris": 20, "Lyon": 9, "Marseille": 16}


def _expand_arrondissements(cities: list[str]) -> list[str]:
    out: list[str] = []
    for c in cities:
        n = ARRONDISSEMENTS.get(c)
        if n:
            out.extend(f"{c} 1er" if i == 1 else f"{c} {i}e" for i in range(1, n + 1))
        else:
            out.append(c)
    return out


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


def _region_name(region: str) -> str:
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        from workflow_geo import list_regions
        for r in list_regions():
            if r.get("code") == region:
                return r.get("name") or region
    except Exception:
        pass
    return region


def _ordered_region_depts(region: str) -> list[dict]:
    """Départements (métropole) d'une région, triés par code (= 'dans le sens des
    département'). Corse + DOM-TOM exclus."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from workflow_geo import metropole_departments
    deps = metropole_departments(region)
    return sorted(deps, key=lambda d: str(d.get("code")))


def run_autoscrape(site: str, sectors, region: str | None = None, dept: str | None = None,
                   region_name: str | None = None, depts_done: list | None = None,
                   cities_done: list | None = None, cities_dept: str | None = None,
                   per_city: int = PER_CITY, max_pages: int = MAX_PAGES,
                   max_seconds: int = MAX_RUN_SECONDS,
                   target_contacts: int = TARGET_CONTACTS,
                   valid_baseline: int = 0,
                   progress_cb=None, should_stop=None) -> dict:
    """Scrape EN CONTINU (Serper + Basile) un périmètre, secteur(s) × villes (pop≥10k).

    Sources : Serper (Google Places, créditisé) ET Basile (registre B2B, illimité) tournent
    en séquence pour chaque ville. La cible `target_contacts` (défaut 100) est partagée entre
    les deux sources : dès que `valid_serper + valid_basile >= target`, on s'arrête.

    Si Serper est bloqué, Basile continue seul jusqu'à la cible. Seul un stop manuel ou
    l'épuisement géo met fin au run quand Basile est actif.

    - region : on enchaîne TOUS ses départements dans l'ordre du code, toutes les villes.
      À l'épuisement → statut 'done' message "Région <nom> finie."
    - dept (si pas de region) : mode mono-département (legacy).
    `depts_done` (reprise) : départements déjà finis à sauter (retry quotidien).
    `cities_done`/`cities_dept` (reprise) : villes déjà finies du dept en cours —
    sans ça, chaque reprise repartait de la ville 1 du dept et re-scannait les
    mêmes villes jusqu'au garde-temps sans jamais progresser."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from workflow_geo import metropole_cities as list_cities
    import god_mode_agents as agents
    import god_mode_backend as gm
    import basile_backend as bb

    # Repart d'un état "non bloqué" pour les deux sources.
    agents.SERPER_BLOCKED_STATUS = None
    bb.BASILE_BLOCKED_STATUS = None
    basile_available = bool(bb.BASILE_KEY)

    if isinstance(sectors, str):
        sectors = [sectors]
    sectors = [s.strip() for s in (sectors or []) if s and s.strip()]
    sector_label = ",".join(sectors)

    if region:
        region_name = region_name or _region_name(region)
        all_depts = _ordered_region_depts(region)
    else:
        all_depts = [{"code": dept, "name": dept}] if dept else []
    done_set = set(depts_done or [])
    todo_depts = [d for d in all_depts if d.get("code") not in done_set]

    # Pré-calcul des villes par département (pour le total + le scraping ordonné).
    dept_cities: dict[str, list[str]] = {}
    cities_total = 0
    for d in todo_depts:
        cs = [c.get("name") for c in list_cities(d["code"], None, min_pop=10000) if c.get("name")]
        cs = _expand_arrondissements(cs)
        dept_cities[d["code"]] = cs
        cities_total += len(cs)

    scope_label = f"Région {region_name}" if region else f"Dept {dept}"
    cum = {
        "site": site, "region": region, "region_name": region_name, "dept": dept,
        "sectors": sectors, "scope": scope_label,
        "depts_total": len(all_depts), "depts_done": len(done_set), "current_dept": None,
        "cities_total": cities_total, "cities_done": 0, "current_city": None,
        "examined": 0, "valid": 0, "rejected": 0, "duplicates": 0, "errors": 0, "kept_total": 0,
        "skipped_seen": 0,
        # Compteurs par source (Serper + Basile)
        "valid_serper": 0, "valid_basile": 0,
        "target_contacts": target_contacts,
        "serper_available": serper_available(),
        "basile_active": basile_available,
        "status": "running", "blocked": False, "stopped": False,
        "started_at": time.time(), "message": None,
    }
    all_city_names: list[str] = [c for cs in dept_cities.values() for c in cs]

    def emit():
        if progress_cb:
            try:
                progress_cb(dict(cum))
            except Exception:
                pass

    # Villes finies du dept EN COURS (reprise intra-département).
    city_progress = {"dept": cities_dept, "done": list(cities_done or [])}

    def persist_progress():
        write_progress(site, {
            "site": site, "region": region, "region_name": region_name,
            "dept": dept,  # mode mono-département : indispensable à la reprise manuelle
            "sectors": sectors, "depts_total": len(all_depts),
            "depts_done": sorted(done_set), "status": cum["status"],
            # `valid` CUMULÉ (runs précédents de la région + ce run) pour que la reprise
            # calcule remaining = target − valid sans re-scraper. `target_contacts` ici
            # est le RELIQUAT de ce run ; on persiste le plafond TOTAL région pour la reprise.
            "valid": valid_baseline + cum["valid"], "message": cum["message"],
            "target_contacts": valid_baseline + target_contacts,
            "cities_dept": city_progress["dept"], "cities_done": city_progress["done"],
        })

    emit()
    if not sectors or not todo_depts:
        cum["status"] = "done"
        cum["message"] = "Aucun secteur." if not sectors else f"{scope_label} : rien à scraper."
        emit()
        persist_progress()
        return cum

    # Une seule ligne d'activité par RUN (et non 1 par ville) : start_scrape unique.
    try:
        gm.log_action(site, "autoscrape", "system", "start_scrape",
                      resource="sector", resource_id=sector_label,
                      payload={"sectors": sectors, "region": region, "region_name": region_name,
                               "scope": scope_label, "cities": all_city_names, "auto": True})
    except Exception:
        pass

    def serper_blocked() -> int | None:
        return getattr(agents, "SERPER_BLOCKED_STATUS", None)

    def target_reached() -> bool:
        return target_contacts > 0 and cum["valid"] >= target_contacts

    # ── Boucle DÉPARTEMENT → VILLE → SECTEUR ───────────────────────────────────
    for d in todo_depts:
        if should_stop and should_stop():
            cum["stopped"] = True; cum["status"] = "stopped"; break
        # Si Serper ET Basile sont tous les deux bloqués/indisponibles → arrêt
        if serper_blocked() and not basile_available:
            break
        if target_reached():
            break
        dcode = d["code"]
        cum["current_dept"] = f"{dcode} {d.get('name', '')}".strip()
        emit()

        # Reprise intra-dept : villes déjà finies lors d'un run précédent de CE dept.
        if city_progress["dept"] != dcode:
            city_progress["dept"] = dcode
            city_progress["done"] = []
        skip_cities = set(city_progress["done"])
        cum["cities_done"] += len(skip_cities & set(dept_cities[dcode]))

        seen_basile_cities: set[str] = set()  # évite d'appeler Basile N fois pour PARIS/LYON/MARSEILLE
        for city in dept_cities[dcode]:
            if city in skip_cities:
                continue
            if should_stop and should_stop():
                cum["stopped"] = True; cum["status"] = "stopped"; break
            # Ne stoppe sur Serper seul que si Basile aussi indisponible
            if serper_blocked() and not basile_available:
                break
            if target_reached():
                break
            if time.time() - cum["started_at"] >= max_seconds:
                cum["status"] = "timeout"
                cum["message"] = f"Garde-temps {int(max_seconds/3600)} h atteint — arrêt ({cum['valid']} gardés)."
                break

            cum["current_city"] = city
            emit()
            for sector in sectors:
                if should_stop and should_stop() or target_reached():
                    break
                if serper_blocked() and not basile_available:
                    break

                # ── Source 1 : Serper ─────────────────────────────────────────
                if not serper_blocked():
                    _base_ex, _base_va = cum["examined"], cum["valid_serper"]
                    def _hb(c, sec, ex, va):
                        cum["current_city"] = c
                        cum["current_detail"] = f"{sec} · Serper {ex} examinés"
                        cum["examined"] = _base_ex + ex
                        cum["valid_serper"] = _base_va + va
                        cum["valid"] = cum["valid_serper"] + cum["valid_basile"]
                        cum["kept_total"] = cum["valid"]
                        emit()
                    try:
                        r = agents.scrape_sector(site, sector, cities=[city],
                                                 max_per_city=per_city, global_cap=per_city,
                                                 max_pages=max_pages, username="autoscrape",
                                                 heartbeat_cb=_hb)
                    except Exception:
                        cum["errors"] += 1
                        r = {"scraped": 0, "valid": 0, "rejected": 0, "errors": 1}
                    cum["examined"] = _base_ex + r.get("scraped", 0)
                    cum["valid_serper"] = _base_va + r.get("valid", 0)
                    cum["rejected"] += r.get("rejected", 0)
                    cum["duplicates"] += r.get("duplicates", 0)
                    cum["skipped_seen"] += r.get("skipped_seen", 0)
                    cum["errors"] += r.get("errors", 0)
                    cum["valid"] = cum["valid_serper"] + cum["valid_basile"]
                    cum["kept_total"] = cum["valid"]
                    emit()

                # ── Source 2 : Basile (illimité — continue si Serper bloqué) ─
                if basile_available and not target_reached():
                    # Basile normalise Paris 1er/2e/... → PARIS, idem Lyon/Marseille.
                    # On n'appelle Basile qu'UNE FOIS par ville Basile réelle par dept.
                    basile_city_key = f"{sector}:{bb._city_to_basile_city(city)}"
                    if basile_city_key in seen_basile_cities:
                        pass  # déjà fait pour cette ville Basile ce dept → skip
                    else:
                        seen_basile_cities.add(basile_city_key)
                        cum["current_detail"] = f"{sector} · Basile {city}"
                        emit()
                        remaining = max(1, target_contacts - cum["valid"]) if target_contacts else per_city
                        try:
                            rb = bb.run_sector_for_city(
                                site, sector, city,
                                dept_code=dcode, region_code=region,
                                target=min(remaining, per_city * 2),
                                dry_run=False,
                            )
                            cum["valid_basile"] += rb.get("valid", 0)
                            cum["rejected"] += rb.get("rejected", 0)
                            cum["duplicates"] += rb.get("duplicates", 0)
                            cum["errors"] += rb.get("errors", 0)
                            cum["valid"] = cum["valid_serper"] + cum["valid_basile"]
                            cum["kept_total"] = cum["valid"]
                            if rb.get("status") == "blocked":
                                basile_available = False
                        except Exception:
                            cum["errors"] += 1
                        emit()

            if not (serper_blocked() and not basile_available) and not (should_stop and should_stop()) and not target_reached():
                cum["cities_done"] += 1
                city_progress["done"].append(city)
                persist_progress()  # reprise intra-dept : la ville ne sera pas re-scannée
            elif not target_reached():
                pass  # city partielle : ne pas incrémenter cities_done
            else:
                cum["cities_done"] += 1  # ville complète avant cible atteinte
                city_progress["done"].append(city)
                persist_progress()
            emit()

        # Si on est sorti de la ville-loop sur blocage total ou cible atteinte ou stop,
        # on ne marque pas ce département comme fini (sauf cible atteinte = run complet).
        if (serper_blocked() and not basile_available) or cum["stopped"] or cum["status"] == "timeout":
            break
        if target_reached():
            break
        done_set.add(dcode)
        cum["depts_done"] = len(done_set)
        city_progress["dept"] = None
        city_progress["done"] = []
        persist_progress()
        emit()

    # ── Verdict ────────────────────────────────────────────────────────────────
    blk = serper_blocked()
    if target_contacts > 0 and cum["valid"] >= target_contacts and cum["status"] == "running":
        cum["status"] = "done"
        cum["message"] = (f"Cible {target_contacts} contacts atteinte — {cum['valid']} gardés "
                          f"(Serper {cum['valid_serper']} + Basile {cum['valid_basile']}).")
        notify_telegram(
            f"✅ *Autoscrape {site.upper()}* — Cible {target_contacts} atteinte · "
            f"{cum['valid']} contacts · Serper {cum['valid_serper']} + Basile {cum['valid_basile']}."
        )
    elif blk and not basile_available:
        cum["blocked"] = True
        cum["status"] = "blocked_serper"
        cum["message"] = (f"Serper stoppé (HTTP {blk}) et Basile indisponible. {cum['valid']} gardés. "
                          f"Reprise automatique chaque jour jusqu'à passage Serper.")
        notify_telegram(
            f"⛔ *Autoscrape {site.upper()}* stoppé Serper+Basile (HTTP {blk}).\n"
            f"{scope_label} · {sector_label} · {cum['valid']} gardés · "
            f"{cum['depts_done']}/{cum['depts_total']} dépts finis. Retry quotidien actif."
        )
    elif blk and basile_available:
        # Serper bloqué mais Basile a pu continuer jusqu'à épuisement géo
        cum["status"] = "done"
        cum["message"] = (f"Serper stoppé (HTTP {blk}) — Basile a complété. {cum['valid']} gardés "
                          f"(Serper {cum['valid_serper']} + Basile {cum['valid_basile']}).")
        notify_telegram(
            f"✅ *Autoscrape {site.upper()}* — Serper bloqué, Basile relayé. "
            f"{cum['valid']} contacts · {scope_label}."
        )
    elif cum["stopped"]:
        cum["message"] = f"Arrêt manuel — {cum['valid']} gardés."
    elif cum["status"] == "timeout":
        notify_telegram(f"⏱️ *Autoscrape {site.upper()}* garde-temps atteint — {scope_label} · {cum['valid']} gardés.")
    elif cum["status"] == "running":
        cum["status"] = "done"
        cum["message"] = (f"{scope_label} finie — {cum['valid']} contacts gardés "
                          f"({cum['depts_done']}/{cum['depts_total']} dépts · "
                          f"Serper {cum['valid_serper']} + Basile {cum['valid_basile']}).")
        notify_telegram(f"✅ *Autoscrape {site.upper()}* — {scope_label} finie · {cum['valid']} gardés.")

    cum["serper_available"] = serper_available()
    cum["scrape_finished_at"] = time.time()
    persist_progress()
    emit()

    # ── Nettoyage Mailnjoy automatique en fin de scrape ─────────────────────────
    # Draine scrappe_pending (god_mode.duckdb) via mailnjoy_check — c'est là que
    # scrape_sector écrit les nouveaux contacts. cleanup_backend opère sur contacts.duckdb
    # (pool) et n'a rien à voir avec les contacts fraîchement scrappés.
    if not (should_stop and should_stop()):
        prev_status = cum["status"]
        cum["status"] = "cleaning"
        cum["cleanup"] = {"status": "running", "valid": 0, "removed": 0, "total": 0}
        cum["message"] = f"Scrape fini ({cum['valid']} contacts) — nettoyage Mailnjoy en cours…"
        emit()
        try:
            sys.path.insert(0, str(BASE_DIR / "scripts"))
            import mailnjoy_check as mj

            total_valid = total_removed = total_processed = 0
            while True:
                if should_stop and should_stop():
                    break
                r = mj.check_pending_queue(site_code=site, delay_ms=100, max_rows=100)
                total_valid += r.get("valid", 0)
                total_removed += r.get("risky", 0) + r.get("invalid", 0)
                total_processed += r.get("total", 0)
                cum["cleanup"] = {"status": "running", "valid": total_valid,
                                  "removed": total_removed, "total": total_processed}
                emit()
                if r.get("error") or r.get("total", 0) == 0:
                    break

            cum["cleanup"] = {"status": "done", "valid": total_valid,
                              "removed": total_removed, "total": total_processed}
            cum["message"] = (f"{scope_label} : {cum['valid']} scrappés · Mailnjoy "
                              f"{total_valid} valides / {total_removed} supprimés.")
        except Exception as e:
            cum["cleanup"] = {"status": "error", "error": str(e)}
            cum["message"] = f"Scrape OK ({cum['valid']}) mais nettoyage en erreur : {e}"
        cum["status"] = prev_status

    # Ligne d'activité de fin (1 par run) + audit — loggée APRÈS le cleanup pour inclure
    # les doublons ET le net Mailnjoy (validés/supprimés). `net` = contacts gardés après
    # nettoyage = valid − supprimés par Mailnjoy.
    try:
        _cl = cum.get("cleanup") or {}
        _removed = int(_cl.get("removed", 0) or 0)
        _net = max(0, int(cum.get("valid", 0) or 0) - _removed)
        gm.log_action(site, "system", "autoscrape", "scrape",
                      resource="sector", resource_id=sector_label,
                      payload={"sector": sector_label, "region": region, "region_name": region_name,
                               "scope": scope_label, "scraped": cum["examined"], "valid": cum["valid"],
                               "valid_serper": cum.get("valid_serper", 0),
                               "valid_basile": cum.get("valid_basile", 0),
                               "rejected": cum["rejected"], "duplicates": cum["duplicates"],
                               "skipped_seen": cum.get("skipped_seen", 0),
                               "errors": cum["errors"], "status": cum["status"],
                               "cleanup": _cl, "net": _net, "message": cum["message"]},
                      success=not cum["blocked"])
    except Exception:
        pass

    cum["finished_at"] = time.time()
    persist_progress()
    emit()
    return cum


def run_all_regions(site: str, sectors, target_contacts: int = TARGET_CONTACTS,
                    progress_cb=None, should_stop=None) -> dict:
    """Scrape TOUTES les régions métropole en séquence (75→84→27→…).
    Pour chaque région : tous les départements, toutes les villes ≥10k hab.
    S'arrête uniquement sur stop manuel ou blocage Serper + Basile simultané."""
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from workflow_geo import metropole_regions

    regions = sorted(metropole_regions(), key=lambda r: str(r.get("code")))
    total = {"regions_total": len(regions), "regions_done": 0, "valid": 0,
             "status": "running", "current_region": None}

    def emit(state=None):
        if progress_cb:
            try:
                progress_cb(state or total)
            except Exception:
                pass

    for r in regions:
        if should_stop and should_stop():
            total["status"] = "stopped"
            break
        code = r.get("code")
        name = r.get("name") or code
        total["current_region"] = f"{name} ({code})"
        emit()
        res = run_autoscrape(site, sectors, region=code, region_name=name,
                             target_contacts=target_contacts,
                             progress_cb=lambda s: (total.update({"valid": total["valid"] + s.get("valid", 0)}) or emit(s)),
                             should_stop=should_stop)
        total["regions_done"] += 1
        # Blocage Serper + pas de Basile = inutile de continuer les régions suivantes
        if res.get("status") == "blocked_serper":
            total["status"] = "blocked_serper"
            total["message"] = f"Serper bloqué après {name} — retry quotidien actif."
            break
    else:
        total["status"] = "done"
        total["message"] = f"Toutes les régions scrappées — {total['valid']} contacts."
        notify_telegram(f"✅ *Autoscrape {site.upper()} ALL REGIONS* — {total['valid']} contacts · {total['regions_done']} régions.")

    emit()
    return total


def daily_retry(site: str) -> dict:
    """Retry quotidien : si la dernière région a été stoppée par Serper et que Serper
    nous laisse de nouveau passer, on reprend la région là où on s'était arrêté."""
    prog = read_progress(site)
    if not prog or not prog.get("region"):
        return {"ok": True, "skipped": "aucune région en cours"}
    if prog.get("status") not in ("blocked_serper", "interrupted", "timeout", "stopped"):
        # Idem retry quotidien : un run mort sans statut final doit redevenir reprenable.
        if is_stalled(site):
            mark_interrupted(site, "Retry quotidien : run figé sans battement de cœur.")
            prog = read_progress(site)
        else:
            return {"ok": True, "skipped": f"statut '{prog.get('status')}' — rien à reprendre"}

    # Test : un appel Serper bon marché. S'il est encore refusé → Basile peut quand
    # même reprendre SEUL (sinon un Serper mort gèlerait toute l'acquisition).
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import god_mode_agents as agents
    import basile_backend as bb
    agents.SERPER_BLOCKED_STATUS = None
    try:
        agents.serper_places("restaurant Paris", location="Paris, France", num=1, site_code=site)
    except Exception:
        pass
    if getattr(agents, "SERPER_BLOCKED_STATUS", None) and not bb.BASILE_KEY:
        return {"ok": True, "still_blocked": True,
                "status": agents.SERPER_BLOCKED_STATUS, "region": prog.get("region")}

    # Serper repasse → on reprend la région en sautant les départements déjà finis.
    sp = stop_path(site)
    try:
        if sp.exists():
            sp.unlink()
    except Exception:
        pass
    # Respecte le plafond du run interrompu : on reprend avec le RELIQUAT (le compteur
    # `valid` repart de 0 à chaque run). Plafond atteint → rien à reprendre (0 = illimité,
    # donc on ne passe JAMAIS un reliquat nul).
    target = int(prog.get("target_contacts") or 0)
    remaining = 0
    if target > 0:
        remaining = target - int(prog.get("valid") or 0)
        if remaining <= 0:
            write_progress(site, {**prog, "status": "done",
                                  "message": "plafond de contacts atteint (retry)"})
            return {"ok": True, "skipped": "plafond de contacts déjà atteint",
                    "region": prog.get("region")}
    res = run_autoscrape(site, prog.get("sectors") or [], region=prog.get("region"),
                         region_name=prog.get("region_name"),
                         depts_done=prog.get("depts_done") or [],
                         cities_done=prog.get("cities_done") or [],
                         cities_dept=prog.get("cities_dept"),
                         target_contacts=remaining,
                         valid_baseline=int(prog.get("valid") or 0),
                         progress_cb=lambda s: write_status(site, s),
                         should_stop=lambda: sp.exists())
    return {"ok": True, "resumed": True, "region": prog.get("region"), "status": res.get("status")}


RESUMABLE_STATUSES = ("blocked_serper", "interrupted", "timeout", "stopped", "error")


def resume_stopped(site: str) -> dict:
    """Reprise MANUELLE (bouton UI) d'un run arrêté, là où il s'était arrêté.
    Contrairement à daily_retry (cron, mode région uniquement), gère aussi les runs
    mono-département et tous les statuts d'arrêt (stop manuel, erreur, timeout…)."""
    prog = read_progress(site)
    if not prog:
        return {"ok": False, "error": "Aucune progression enregistrée — rien à reprendre."}
    region = prog.get("region")
    # Ancien format sans champ `dept` : en mode mono-dept, cities_dept EST le département.
    dept = prog.get("dept") or (None if region else prog.get("cities_dept"))
    if not region and not dept:
        return {"ok": False, "error": "Progression illisible (ni région ni département)."}
    if prog.get("status") not in RESUMABLE_STATUSES:
        # Un run figé sur « running » sans battement depuis 15 min est mort : on le
        # requalifie avant de refuser, sinon il resterait bloqué à vie.
        if is_stalled(site):
            mark_interrupted(site, "Reprise manuelle : run figé sans battement de cœur.")
            prog = read_progress(site)
        else:
            return {"ok": False, "error": f"Statut « {prog.get('status')} » — rien à reprendre."}

    # Reliquat : le plafond persisté est le TOTAL du périmètre, `valid` le cumul déjà gardé.
    target = int(prog.get("target_contacts") or 0)
    baseline = int(prog.get("valid") or 0)
    remaining = 0
    if target > 0:
        remaining = target - baseline
        if remaining <= 0:
            write_progress(site, {**prog, "status": "done",
                                  "message": "plafond de contacts atteint (reprise)"})
            return {"ok": False, "error": "Plafond de contacts déjà atteint — rien à reprendre."}

    sp = stop_path(site)
    try:
        if sp.exists():
            sp.unlink()
    except Exception:
        pass
    res = run_autoscrape(site, prog.get("sectors") or [], region=region, dept=dept,
                         region_name=prog.get("region_name"),
                         depts_done=prog.get("depts_done") or [],
                         cities_done=prog.get("cities_done") or [],
                         cities_dept=prog.get("cities_dept"),
                         target_contacts=remaining,
                         valid_baseline=baseline,
                         progress_cb=lambda s: write_status(site, s),
                         should_stop=lambda: sp.exists())
    return {"ok": True, "resumed": True, "region": region, "dept": dept,
            "status": res.get("status")}


def main() -> int:
    """Process DÉTACHÉ (lancé par l'API) ou retry quotidien (cron PM2). Écrit
    l'avancement dans memory/autoscrape/<site>-status.json ; stop via flag fichier."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True)
    ap.add_argument("--region", default=None, help="code région INSEE — scrape tous ses dépts")
    ap.add_argument("--dept", default=None, help="mode mono-département (legacy)")
    ap.add_argument("--sectors", default="", help="secteurs séparés par des virgules")
    ap.add_argument("--target-contacts", type=int, default=TARGET_CONTACTS,
                    help="cible contacts valides (Serper + Basile) avant arrêt")
    ap.add_argument("--all-regions", action="store_true",
                    help="scrape toutes les régions métropole en séquence")
    ap.add_argument("--daily-retry", action="store_true",
                    help="reprend la région stoppée si Serper repasse (cron)")
    ap.add_argument("--resume", action="store_true",
                    help="reprise manuelle du run arrêté (bouton UI) — région ou département")
    args = ap.parse_args()

    if args.resume:
        try:
            out = resume_stopped(args.site)
            print(json.dumps(out, ensure_ascii=False))
            return 0 if out.get("ok") else 1
        except Exception as e:
            cur = read_status(args.site)
            cur.update({"status": "error", "message": f"reprise: {e}", "finished_at": time.time()})
            write_status(args.site, cur)
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return 1

    if args.daily_retry:
        try:
            out = daily_retry(args.site)
            print(json.dumps(out, ensure_ascii=False))
            return 0
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return 1

    sectors = [s.strip() for s in args.sectors.split(",") if s.strip()]
    if not args.all_regions and not args.region and not args.dept:
        print("--region, --dept ou --all-regions requis"); return 2

    sp = stop_path(args.site)
    try:
        if sp.exists():
            sp.unlink()
    except Exception:
        pass

    def progress_cb(state):
        write_status(args.site, state)

    def should_stop():
        # Arrêt manuel (drapeau) OU sortie de la fenêtre nocturne. Dans le 2e cas, la
        # boucle sort proprement en écrivant sa progression : le scrape reprendra la nuit
        # suivante exactement là où il s'est arrêté, sans re-scanner les villes déjà faites.
        if sp.exists():
            return True
        ok, why = within_scrape_window()
        if not ok:
            cur = read_status(args.site)
            cur["message"] = f"Pause de jour — {why}. Reprise à {SCRAPE_START}."
            write_status(args.site, cur)
            return True
        return False

    # Arrêt externe (SIGTERM d'un déploiement, SIGINT, kill) : on demande un arrêt PROPRE
    # via le flag, pour que la boucle sorte en écrivant sa progression. Sans ça, le run
    # mourait en laissant « running » derrière lui, et plus aucun mécanisme de reprise ne
    # le reconnaissait comme repartable — c'est ainsi qu'un scrape restait figé des jours.
    import signal as _signal

    def _on_signal(signum, _frame):
        try:
            sp.write_text("stop")   # la boucle le verra au prochain tour de ville
            mark_interrupted(args.site, f"Arrêt externe (signal {signum}) — reprise possible.")
        finally:
            raise KeyboardInterrupt

    for _sig in (_signal.SIGTERM, _signal.SIGINT, _signal.SIGHUP):
        try:
            _signal.signal(_sig, _on_signal)
        except Exception:  # noqa: BLE001
            pass

    try:
        if args.all_regions:
            run_all_regions(args.site, sectors, target_contacts=args.target_contacts,
                            progress_cb=progress_cb, should_stop=should_stop)
        else:
            run_autoscrape(args.site, sectors, region=args.region, dept=args.dept,
                           target_contacts=args.target_contacts,
                           progress_cb=progress_cb, should_stop=should_stop)
    except KeyboardInterrupt:
        mark_interrupted(args.site, "Interrompu — reprise possible là où il s'est arrêté.")
        return 130
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
