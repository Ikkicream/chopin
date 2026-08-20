"""
autoscrape_daily.py — Scraping automatique quotidien, piloté par la population.

Remplace `autoscrape_plan.py` (plan régional en dur, terminé le 2026-07-16 et arrêté
faute de secteur suivant activé). Règles demandées par Camille le 2026-08-06 :

  1. MAX_TARGETS_PER_NIGHT cibles par nuit (3), une à la fois, et UNIQUEMENT si aucun
     scrape ne tourne déjà (cron, UI ou reprise manuelle : on ne double jamais un run).
     Tout est terminé avant 8h00 heure de Paris — cf. « Butoirs horaires » plus bas :
     à 8h30 UTC le dispatch de campagnes a besoin de DuckDB, qui n'admet qu'un écrivain.
  2. Secteur prioritaire : immobilier, puis le reste de SECTOR_PRIORITY dans l'ordre.
  3. Cibles ordonnées par population DÉCROISSANTE — région d'abord, puis département
     à l'intérieur de la région.
  4. Cible de contacts : TARGET_PER_TARGET (2000) pour chaque couple secteur × dept.
  5. Table mémoire `autoscrape_targets` (god_mode.duckdb) : une cible n'est jamais
     jouée plus de MAX_RUNS_PER_TARGET (3) fois.

Ordre de la file : `runs ASC` d'abord, puis secteur / population. Conséquence voulue :
TOUTES les cibles reçoivent leur 1re passe (les plus peuplées en premier) avant qu'une
seule n'entame sa 2e. Sans ça, le département le plus peuplé monopoliserait les trois
premières nuits — « ne pas tourner 3 fois sur la même cible » veut dire l'inverse.

Une cible qui atteint les 2000 contacts passe en `done` et ne repasse jamais. Une cible
dont la géo est épuisée avant 2000 redevient `pending` : elle sera rejouée quand toutes
les autres auront eu leur passe (de nouvelles entreprises apparaissent), dans la limite
des 3 passes.

Fenêtre : le scraping reste confiné à 22h–08h (heure de Paris) par `autoscrape_backend`
— DuckDB n'admet qu'un écrivain, un scrape de jour gèlerait les compteurs de l'UI.

État  : memory/autoscrape/<site>-daily.json · pause : <site>-daily-pause.flag
Table : autoscrape_targets (god_mode.duckdb)
Log   : logs/autoscrape_daily.log
CLI   : tick | work | status | targets | pause | resume | reset | seed
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

import duckdb  # noqa: E402

SITE = "lcr"
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"

# ── Règles du plan ───────────────────────────────────────────────────────────────
TARGET_PER_TARGET = 2000      # contacts visés par couple secteur × département
MAX_RUNS_PER_TARGET = 3       # passes maximum sur une même cible (règle Camille)
MAX_TARGETS_PER_NIGHT = 3     # cibles travaillées par nuit (2026-08-06 : 1 → 3)
MAX_RESUMES_PER_PASS = 8      # garde-fou : une passe qui ne finit jamais est close d'office

# Butoirs horaires : ils vivent dans `autoscrape_backend` (SCRAPE_STOP / CLEANUP_STOP,
# 07:20 et 07:50 heure de Paris) pour s'appliquer à TOUS les points d'entrée — ici, le
# veilleur, le bouton « Relancer » de l'UI. On les lit, on ne les redéfinit pas.
MIN_MINUTES_TO_START = 45     # sous ce reliquat, on ne démarre plus de NOUVELLE cible

# Secteur prioritaire en tête. Les suivants sont consommés dans cet ordre, une fois que
# toutes les cibles « immobilier » ont eu leur passe.
SECTOR_PRIORITY = [
    "immobilier",
    "agence-marketing",
    "agence-web",
    "restaurant",
    "garagiste",
    "coiffeur",
    "retail",
    "artisan",
    "plombier",
    "electricien",
    "menuisier",
    "boulanger",
    "fleuriste",
    "avocat",
    "comptable",
    "consultant",
]

STATE_PATH = BASE_DIR / "memory" / "autoscrape" / f"{SITE}-daily.json"
PAUSE_PATH = BASE_DIR / "memory" / "autoscrape" / f"{SITE}-daily-pause.flag"

RESUMABLE = ("blocked_serper", "interrupted", "timeout", "stopped", "error")
LIVE = ("running", "starting", "stopping", "cleaning")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Connexion DuckDB tolérante au verrou ─────────────────────────────────────────
# god_mode.duckdb n'accepte qu'un écrivain : l'API (uvicorn), un dispatch de campagne
# ou un autre script peuvent le tenir quelques secondes. Un échec sec ferait perdre la
# comptabilité des passes, donc on réessaie — et en dernier recours on met l'écriture
# en file dans le fichier d'état, rejouée au tick suivant (cf. `_flush_pending`).
def _conn(read_only: bool = False, attempts: int = 12, delay: float = 5.0):
    last = None
    for i in range(attempts):
        try:
            return duckdb.connect(str(GOD_DB), read_only=read_only)
        except Exception as e:  # IOException: Could not set lock on file
            last = e
            if i < attempts - 1:
                time.sleep(delay)
    raise last


def _ensure_table() -> None:
    c = _conn()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS autoscrape_targets (
                id           VARCHAR PRIMARY KEY,
                site_code    VARCHAR,
                sector       VARCHAR,
                region_code  VARCHAR,
                region_name  VARCHAR,
                dept_code    VARCHAR,
                dept_name    VARCHAR,
                region_pop   BIGINT,
                dept_pop     BIGINT,
                runs         INTEGER DEFAULT 0,
                valid_total  INTEGER DEFAULT 0,
                status       VARCHAR DEFAULT 'pending',
                last_status  VARCHAR,
                last_run_at  TIMESTAMP,
                first_run_at TIMESTAMP,
                updated_at   TIMESTAMP
            )""")
    finally:
        c.close()


# ── État local (cible en cours, quota de la nuit, écritures en attente) ──────────
def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"current": None, "night": None, "history": [], "pending_writes": []}


def save_state(st: dict) -> None:
    st["updated_at"] = _now_iso()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2))


def _night_id(now=None) -> str:
    """Identifiant de la nuit en cours (date Paris de son DÉBUT).

    La fenêtre 22h→08h chevauche minuit : sans ça, un run lancé à 22h30 puis un autre
    à 00h30 compteraient pour deux jours différents et on démarrerait deux cibles la
    même nuit, alors que Camille en demande une par jour.
    """
    from zoneinfo import ZoneInfo
    now = now or datetime.now(ZoneInfo("Europe/Paris"))
    if now.hour < 8:
        now = now - timedelta(days=1)
    return now.date().isoformat()


def _night_worked(st: dict) -> list[str]:
    """Cibles déjà travaillées cette nuit. Une reprise entamée cette nuit compte comme
    une cible de la nuit : sinon une cible reprise + 3 nouvelles feraient 4 scrapes."""
    n = st.get("night") or {}
    return list(n.get("ids") or []) if n.get("id") == _night_id() else []


def _mark_night_worked(st: dict, tid: str) -> None:
    ids = _night_worked(st)
    if tid not in ids:
        ids.append(tid)
    st["night"] = {"id": _night_id(), "ids": ids}


# ── Population : régions et départements classés par habitants ───────────────────
def _population_index() -> tuple[dict, dict, dict, dict]:
    """(pop par région, pop par dept, nom région, nom dept) sur les villes ≥10k hab.

    Même assiette que le scrapper (il ne visite que les villes ≥10 000 habitants) :
    classer sur la population totale INSEE gonflerait des départements ruraux dont le
    scrapper ne verrait jamais les communes.
    """
    from workflow_geo import metropole_cities, metropole_departments, metropole_regions

    region_pop: dict[str, int] = {}
    dept_pop: dict[str, int] = {}
    for c in metropole_cities(None, None, min_pop=10000):
        region_pop[c["region"]] = region_pop.get(c["region"], 0) + int(c.get("pop") or 0)
        dept_pop[c["dept"]] = dept_pop.get(c["dept"], 0) + int(c.get("pop") or 0)
    region_name = {r["code"]: r.get("name") or r["code"] for r in metropole_regions()}
    dept_name = {d["code"]: d.get("name") or d["code"] for d in metropole_departments()}
    return region_pop, dept_pop, region_name, dept_name


def seed_targets(site: str = SITE) -> dict:
    """Crée les lignes manquantes (secteur × département). Idempotent : ne touche
    jamais aux compteurs d'une cible déjà connue.

    Appelée à chaque tick : elle commence par un COUNT en lecture seule et ne prend une
    connexion en ÉCRITURE que s'il manque des lignes. Sans ça, on rouvrirait
    god_mode.duckdb en écriture toutes les 15 min pour rien — et on se battrait avec
    l'API pour le verrou.
    """
    _ensure_table()
    from workflow_geo import metropole_departments

    region_pop, dept_pop, region_name, dept_name = _population_index()
    depts = [d for d in metropole_departments() if dept_pop.get(d["code"])]
    expected = len(SECTOR_PRIORITY) * len(depts)
    c = _conn(read_only=True)
    try:
        have = c.execute("SELECT COUNT(*) FROM autoscrape_targets WHERE site_code=?",
                         [site]).fetchone()[0]
    finally:
        c.close()
    if have >= expected:
        return {"ok": True, "created": 0, "total": have}

    rows = []
    for sector in SECTOR_PRIORITY:
        for d in depts:
            code = d["code"]
            rows.append((f"{site}:{sector}:{code}", site, sector, d.get("region_code"),
                         region_name.get(d.get("region_code"), ""), code,
                         dept_name.get(code, code),
                         int(region_pop.get(d.get("region_code"), 0)),
                         int(dept_pop.get(code, 0)), 0, 0, "pending", None, None, None,
                         datetime.now(timezone.utc)))
    c = _conn()
    try:
        before = c.execute("SELECT COUNT(*) FROM autoscrape_targets WHERE site_code=?",
                           [site]).fetchone()[0]
        c.executemany(
            "INSERT INTO autoscrape_targets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT (id) DO NOTHING", rows)
        after = c.execute("SELECT COUNT(*) FROM autoscrape_targets WHERE site_code=?",
                          [site]).fetchone()[0]
    finally:
        c.close()
    return {"ok": True, "created": after - before, "total": after}


def next_target(site: str = SITE) -> dict | None:
    """Prochaine cible : passes déjà faites croissant, puis secteur prioritaire, puis
    population région, puis population département — le tout décroissant."""
    _ensure_table()
    c = _conn(read_only=True)
    try:
        rows = c.execute(
            "SELECT id, sector, region_code, region_name, dept_code, dept_name, "
            "       region_pop, dept_pop, runs, valid_total, status "
            "FROM autoscrape_targets WHERE site_code=? AND status='pending' AND runs < ?",
            [site, MAX_RUNS_PER_TARGET]).fetchall()
    finally:
        c.close()
    if not rows:
        return None
    cols = ["id", "sector", "region_code", "region_name", "dept_code", "dept_name",
            "region_pop", "dept_pop", "runs", "valid_total", "status"]
    items = [dict(zip(cols, r)) for r in rows]
    prio = {s: i for i, s in enumerate(SECTOR_PRIORITY)}
    items.sort(key=lambda t: (t["runs"], prio.get(t["sector"], 999),
                              -(t["region_pop"] or 0), -(t["dept_pop"] or 0)))
    return items[0]


def get_target(tid: str) -> dict | None:
    c = _conn(read_only=True)
    try:
        r = c.execute(
            "SELECT id, sector, region_code, region_name, dept_code, dept_name, "
            "       region_pop, dept_pop, runs, valid_total, status, last_status "
            "FROM autoscrape_targets WHERE id=?", [tid]).fetchone()
    finally:
        c.close()
    if not r:
        return None
    cols = ["id", "sector", "region_code", "region_name", "dept_code", "dept_name",
            "region_pop", "dept_pop", "runs", "valid_total", "status", "last_status"]
    return dict(zip(cols, r))


def record_pass(tid: str, valid: int, run_status: str) -> dict:
    """Clôt une passe : +1 sur `runs`, cumul des contacts, nouveau statut de cible.

    - objectif atteint (≥ TARGET_PER_TARGET) → `done`, la cible ne repasse jamais ;
    - 3e passe consommée                     → `retired` ;
    - sinon                                  → `pending`, rejouable après les autres.
    """
    tgt = get_target(tid)
    if not tgt:
        return {"ok": False, "error": f"cible {tid} introuvable"}
    runs = int(tgt["runs"] or 0) + 1
    total = int(tgt["valid_total"] or 0) + max(0, int(valid or 0))
    if total >= TARGET_PER_TARGET:
        status = "done"
    elif runs >= MAX_RUNS_PER_TARGET:
        status = "retired"
    else:
        status = "pending"
    now = datetime.now(timezone.utc)
    c = _conn()
    try:
        c.execute("UPDATE autoscrape_targets SET runs=?, valid_total=?, status=?, "
                  "last_status=?, last_run_at=?, first_run_at=COALESCE(first_run_at, ?), "
                  "updated_at=? WHERE id=?",
                  [runs, total, status, run_status, now, now, now, tid])
    finally:
        c.close()
    return {"ok": True, "id": tid, "runs": runs, "valid_total": total, "status": status}


def _queue_pending(st: dict, tid: str, valid: int, run_status: str) -> None:
    st.setdefault("pending_writes", []).append(
        {"id": tid, "valid": valid, "run_status": run_status, "at": _now_iso()})
    save_state(st)


def _flush_pending(st: dict) -> int:
    """Rejoue les clôtures de passe qui n'ont pas pu être écrites (DuckDB verrouillé)."""
    pend = st.get("pending_writes") or []
    if not pend:
        return 0
    done = 0
    for w in list(pend):
        try:
            record_pass(w["id"], w.get("valid") or 0, w.get("run_status") or "unknown")
            pend.remove(w); done += 1
        except Exception:
            break
    st["pending_writes"] = pend
    if done:
        save_state(st)
    return done


# ── Décision ────────────────────────────────────────────────────────────────────
def _progress_is_ours(prog: dict, cur: dict) -> bool:
    """Le fichier de reprise décrit-il bien NOTRE cible ? Le fichier est partagé avec
    les runs manuels de l'UI : sans ce contrôle on reprendrait le scrape de quelqu'un
    d'autre, ou on compterait ses contacts sur notre cible."""
    if not prog or not cur:
        return False
    return (prog.get("dept") == cur.get("dept")
            and set(prog.get("sectors") or []) == {cur.get("sector")})


def decide(site: str = SITE) -> dict:
    """Que faut-il faire maintenant ? (aucun effet de bord, hors flush des écritures)"""
    import autoscrape_backend as asb

    if PAUSE_PATH.exists():
        return {"action": "skip", "why": "plan quotidien en pause (flag)"}

    # Fenêtre d'abord : sinon `status` affiche « butoir atteint » en pleine journée,
    # alors que la vraie raison est qu'on est hors de la plage nocturne.
    in_window, why = asb.within_scrape_window()
    if not in_window:
        return {"action": "skip", "why": why}

    st = load_state()
    _flush_pending(st)

    live = asb.read_status(site)
    if live.get("status") in LIVE and (time.time() - (live.get("updated_at") or 0) < 300):
        return {"action": "skip", "why": "un scrape tourne déjà",
                "live": {k: live.get(k) for k in ("status", "scope", "valid", "current_city")}}

    cur = st.get("current")
    prog = asb.read_progress(site)

    # Butoir dur : passé CLEANUP_STOP on ne relance plus rien, même une reprise. Ce qui
    # tourne déjà s'arrête tout seul (butoirs internes à `run_autoscrape`).
    # Sans objet en mode continu : ce butoir servait à rendre DuckDB à la journée de
    # travail. Le laisser actif interdirait tout lancement passé 7 h 50, c'est-à-dire
    # pendant les seize heures qu'on vient d'ouvrir.
    if asb._fenetre() is not None and asb.seconds_until_paris(asb.CLEANUP_STOP) <= 0:
        return {"action": "skip", "why": f"butoir de nuit atteint ({asb.CLEANUP_STOP} "
                                         "Paris) — DuckDB rendu au routage des emails"}

    # Plafond du jour : le garde-fou qui remplace la fenêtre nocturne.
    plafond, motif = asb.quota_atteint(site)
    if plafond:
        return {"action": "skip", "why": motif}

    if cur:
        ours = _progress_is_ours(prog, cur)
        pstatus = prog.get("status") if ours else None
        if ours and pstatus == "done":
            return {"action": "close", "why": "passe terminée", "current": cur,
                    "valid": int(prog.get("valid") or 0), "run_status": "done"}
        if int(cur.get("resumes") or 0) >= MAX_RESUMES_PER_PASS:
            return {"action": "close", "why": f"passe close d'office ({MAX_RESUMES_PER_PASS} reprises)",
                    "current": cur, "valid": int((prog if ours else {}).get("valid") or 0),
                    "run_status": pstatus or "interrupted"}
        if ours and pstatus in RESUMABLE:
            return {"action": "resume", "why": f"reprise ({pstatus})", "current": cur,
                    "valid": int(prog.get("valid") or 0)}
        if not ours:
            # Le fichier de reprise a été écrasé par un run manuel : notre passe est
            # perdue. On la clôt avec ce qu'on sait pour ne pas bloquer la file.
            return {"action": "close", "why": "reprise impossible (fichier écrasé)",
                    "current": cur, "valid": 0, "run_status": "lost"}
        return {"action": "resume", "why": f"statut '{pstatus}' — relance", "current": cur,
                "valid": int(prog.get("valid") or 0)}

    worked = _night_worked(st)
    if len(worked) >= MAX_TARGETS_PER_NIGHT:
        return {"action": "skip", "why": f"quota de la nuit atteint "
                                         f"({len(worked)}/{MAX_TARGETS_PER_NIGHT} cibles)",
                "cibles_de_la_nuit": worked}

    # Démarrer une cible 20 min avant le butoir ne sert à rien : on brûle un créneau de
    # la nuit pour trois villes. Sous ce seuil, la nuit est finie.
    # En mode continu il n'y a plus de butoir, donc plus de créneau à brûler : on saute
    # ce test, sinon aucune cible ne démarrerait jamais en journée.
    left = (float("inf") if asb._fenetre() is None
            else asb.seconds_until_paris(asb.SCRAPE_STOP) / 60)
    if left < MIN_MINUTES_TO_START:
        return {"action": "skip", "why": f"trop tard pour une nouvelle cible "
                                         f"({int(left)} min avant {asb.SCRAPE_STOP} Paris)"}

    tgt = next_target(site)
    if not tgt:
        return {"action": "skip", "why": "aucune cible éligible (toutes done/retired "
                                         f"ou {MAX_RUNS_PER_TARGET} passes atteintes)"}
    return {"action": "start", "why": "nouvelle cible", "target": tgt}


def tick(launch: bool = True) -> dict:
    """Point d'entrée cron : instantané. Décide, puis lance `work` en détaché."""
    import autoscrape_backend as asb

    in_window, why = asb.within_scrape_window()
    if not in_window:
        return {"ok": True, "skipped": why}

    seed_targets()
    d = decide()

    if d["action"] == "skip":
        return {"ok": True, "skipped": d["why"], **{k: v for k, v in d.items()
                                                    if k not in ("action", "why")}}
    if d["action"] == "close":
        # Clôture pure : pas de scraping, on peut la faire ici même.
        st = load_state()
        try:
            res = record_pass(d["current"]["id"], d.get("valid") or 0,
                              d.get("run_status") or "done")
        except Exception as e:
            _queue_pending(st, d["current"]["id"], d.get("valid") or 0,
                           d.get("run_status") or "done")
            res = {"ok": False, "queued": True, "error": str(e)[:120]}
        st = load_state()
        st.setdefault("history", []).append({**d["current"], "closed_at": _now_iso(),
                                             "valid": d.get("valid"), "result": res})
        st["history"] = st["history"][-100:]
        st["current"] = None
        save_state(st)
        return {"ok": True, "closed": d["current"], "result": res, "why": d["why"]}

    if not launch:
        return {"ok": True, "would": d}

    log = open(BASE_DIR / "logs" / "autoscrape_daily.log", "ab")
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "work"],
                     stdout=log, stderr=log, start_new_session=True, cwd=str(BASE_DIR))
    label = d.get("target") or d.get("current")
    return {"ok": True, "launched": {"action": d["action"], "sector": label.get("sector"),
                                     "dept": f"{label.get('dept_code') or label.get('dept')} "
                                             f"{label.get('dept_name') or ''}".strip(),
                                     "why": d["why"]}}


def work() -> dict:
    """Run bloquant de la cible courante (lancé détaché par `tick`)."""
    import autoscrape_backend as asb

    in_window, why = asb.within_scrape_window()
    if not in_window:
        return {"ok": False, "skipped": why}

    d = decide()  # re-décide : deux ticks rapprochés ne doivent pas lancer deux runs
    if d["action"] not in ("start", "resume"):
        return {"ok": True, "skipped": d.get("why"), "action": d["action"]}

    st = load_state()
    if d["action"] == "start":
        t = d["target"]
        cur = {"id": t["id"], "sector": t["sector"], "dept": t["dept_code"],
               "dept_name": t["dept_name"], "region_name": t["region_name"],
               "night": _night_id(), "started_at": _now_iso(), "resumes": 0}
        st["current"] = cur
        _mark_night_worked(st, cur["id"])
        save_state(st)
        baseline, cities_done, cities_dept = 0, [], None
    else:
        cur = d["current"]
        prog = asb.read_progress(SITE)
        baseline = int(prog.get("valid") or 0)
        cities_done = prog.get("cities_done") or []
        cities_dept = prog.get("cities_dept")
        cur["resumes"] = int(cur.get("resumes") or 0) + 1
        st["current"] = cur
        _mark_night_worked(st, cur["id"])
        save_state(st)

    remaining = max(0, TARGET_PER_TARGET - baseline)
    if remaining == 0:
        return tick(launch=False)  # plafond atteint → la décision suivante clôturera

    # Purge d'un éventuel flag stop résiduel (sinon le run s'arrête à la 1re ville).
    sp = asb.stop_path(SITE)
    try:
        if sp.exists():
            sp.unlink()
    except Exception:
        pass

    # Les butoirs de nuit (07:20 scraping / 07:50 nettoyage) sont appliqués par
    # `run_autoscrape` lui-même — inutile de les repasser ici, et impossible de les
    # oublier ailleurs.
    budget_min = int(asb.seconds_until_paris(asb.SCRAPE_STOP) / 60)
    print(f"[daily] {_now_iso()} {d['action']} {cur['sector']} / dept {cur['dept']} "
          f"{cur.get('dept_name', '')} — cible={TARGET_PER_TARGET} reliquat={remaining} "
          f"acquis={baseline} · scrape jusqu'à {asb.SCRAPE_STOP} ({budget_min} min), "
          f"nettoyage jusqu'à {asb.CLEANUP_STOP} Paris", flush=True)

    res = asb.run_autoscrape(SITE, [cur["sector"]], dept=cur["dept"],
                             cities_done=cities_done, cities_dept=cities_dept,
                             target_contacts=remaining, valid_baseline=baseline,
                             progress_cb=lambda s: asb.write_status(SITE, s),
                             should_stop=lambda: sp.exists())

    final = asb.read_progress(SITE)
    valid = int(final.get("valid") or 0)
    status = res.get("status") or final.get("status")

    if status == "done":
        st = load_state()
        try:
            out = record_pass(cur["id"], valid, status)
        except Exception as e:
            _queue_pending(st, cur["id"], valid, status)
            out = {"ok": False, "queued": True, "error": str(e)[:120]}
        st = load_state()
        st.setdefault("history", []).append({**cur, "closed_at": _now_iso(),
                                             "valid": valid, "result": out})
        st["history"] = st["history"][-100:]
        st["current"] = None
        save_state(st)
        nxt = next_target(SITE)
        asb.notify_telegram(
            f"✅ *Autoscrape {SITE.upper()}* — {cur['sector']} / {cur['dept']} "
            f"{cur.get('dept_name', '')} : {valid} contacts "
            f"(passe {out.get('runs', '?')}/{MAX_RUNS_PER_TARGET}, cible {TARGET_PER_TARGET}).\n"
            f"Suite : {nxt['sector'] + ' / ' + nxt['dept_name'] if nxt else 'file épuisée'}.")
        return {"ok": True, "closed": True, "valid": valid, "result": out}

    print(f"[daily] {_now_iso()} passe non terminée (status={status}) — reprise au "
          f"prochain tick", flush=True)
    return {"ok": True, "status": status, "valid": valid}


# ── Lecture ─────────────────────────────────────────────────────────────────────
def targets(limit: int = 20, site: str = SITE) -> dict:
    _ensure_table()
    c = _conn(read_only=True)
    try:
        rows = c.execute(
            "SELECT status, COUNT(*), COALESCE(SUM(valid_total),0) FROM autoscrape_targets "
            "WHERE site_code=? GROUP BY status", [site]).fetchall()
        played = c.execute(
            "SELECT sector, dept_code, dept_name, region_name, runs, valid_total, status, "
            "       last_run_at FROM autoscrape_targets WHERE site_code=? AND runs > 0 "
            "ORDER BY last_run_at DESC LIMIT ?", [site, limit]).fetchall()
    finally:
        c.close()
    nxt = []
    prio = {s: i for i, s in enumerate(SECTOR_PRIORITY)}
    c = _conn(read_only=True)
    try:
        cand = c.execute(
            "SELECT sector, dept_code, dept_name, region_name, region_pop, dept_pop, runs "
            "FROM autoscrape_targets WHERE site_code=? AND status='pending' AND runs < ?",
            [site, MAX_RUNS_PER_TARGET]).fetchall()
    finally:
        c.close()
    cand = sorted(cand, key=lambda r: (r[6], prio.get(r[0], 999), -(r[4] or 0), -(r[5] or 0)))
    for r in cand[:limit]:
        nxt.append({"secteur": r[0], "dept": f"{r[1]} {r[2]}", "region": r[3],
                    "pop_region": r[4], "pop_dept": r[5], "passes": r[6]})
    return {"resume": {r[0]: {"cibles": r[1], "contacts": r[2]} for r in rows},
            "prochaines": nxt,
            "jouees": [{"secteur": p[0], "dept": f"{p[1]} {p[2]}", "region": p[3],
                        "passes": p[4], "contacts": p[5], "statut": p[6],
                        "dernier_run": str(p[7]) if p[7] else None} for p in played]}


def status() -> dict:
    import autoscrape_backend as asb
    st = load_state()
    worked = _night_worked(st)
    return {"paused": PAUSE_PATH.exists(), "nuit": _night_id(),
            "cibles_de_la_nuit": f"{len(worked)}/{MAX_TARGETS_PER_NIGHT}", "detail": worked,
            "cible_en_cours": st.get("current"),
            "ecritures_en_attente": len(st.get("pending_writes") or []),
            "butoirs": {"scraping": f"{asb.SCRAPE_STOP} Paris (dans "
                                    f"{int(asb.seconds_until_paris(asb.SCRAPE_STOP) / 60)} min)",
                        "nettoyage": f"{asb.CLEANUP_STOP} Paris (dans "
                                     f"{int(asb.seconds_until_paris(asb.CLEANUP_STOP) / 60)} min)"},
            "decision": decide(), "live": asb.read_status(SITE),
            "regles": {"cible_contacts": TARGET_PER_TARGET,
                       "passes_max": MAX_RUNS_PER_TARGET,
                       "cibles_par_nuit": MAX_TARGETS_PER_NIGHT},
            **targets(limit=5)}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "tick":
        out = tick()
    elif cmd == "work":
        out = work()
    elif cmd == "seed":
        out = seed_targets()
    elif cmd == "targets":
        out = targets(limit=int(sys.argv[2]) if len(sys.argv) > 2 else 20)
    elif cmd == "pause":
        PAUSE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PAUSE_PATH.touch()
        out = {"ok": True, "paused": True}
    elif cmd == "resume":
        PAUSE_PATH.unlink(missing_ok=True)
        out = {"ok": True, "paused": False}
    elif cmd == "reset":
        # Remet les compteurs de passes à zéro (la file repart de la cible la plus peuplée).
        c = _conn()
        try:
            c.execute("UPDATE autoscrape_targets SET runs=0, valid_total=0, status='pending', "
                      "last_status=NULL WHERE site_code=?", [SITE])
        finally:
            c.close()
        STATE_PATH.unlink(missing_ok=True)
        out = {"ok": True, "reset": True}
    else:
        out = status()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
