#!/usr/bin/env python3
"""verrou_watchdog.py — Veilleur du verrou de `contacts.duckdb`.

Pourquoi ce script existe (incident du 2026-09-21) : le nettoyage nocturne a gardé le
verrou d'écriture du pool de 03:00 à 13:40. `contacts.duckdb` n'accepte qu'UN seul
écrivain, donc pendant dix heures tout ce qui touche aux contacts est tombé — pixel
d'ouverture, compteurs, pages acquisition — SANS la moindre alerte, chaque appelant
avalant son erreur dans un coin. Le symptôme visible a été « 1 ouvreur au lieu de 40 »,
et c'est Camille qui l'a vu, pas la machine.

Ce que fait le veilleur, dans cet ordre :
  1. Il teste ce qui casse vraiment : ouvrir le pool en lecture. Pas de supposition,
     pas de lecture de PID — l'épreuve réelle.
  2. Si c'est bloqué, il identifie qui tient le fichier, et depuis combien de temps.
  3. Passé le seuil, il arrête le coupable — mais UNIQUEMENT s'il figure dans la liste
     blanche des travaux de fond interruptibles. L'API et l'interface ne sont jamais
     touchées : les arrêter transformerait une panne de compteurs en panne de service.
  4. Il rejoue la file de secours des engagements (`engagement_spool`), pour que les
     ouvertures encaissées pendant le blocage retrouvent leur place, à leur vraie date.
  5. Il alerte sur Telegram — une fois par incident, pas à chaque passage.

Usage :
  python3 scripts/verrou_watchdog.py              # veille + action
  python3 scripts/verrou_watchdog.py --dry-run    # diagnostic seul, n'arrête rien
  python3 scripts/verrou_watchdog.py --seuil 20   # seuil en minutes (défaut : 30)

Cron (toutes les 10 min) :
  */10 * * * * cd /home/autoblog/genesis && python3 scripts/verrou_watchdog.py >> logs/verrou_watchdog.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
POOL_DB = BASE_DIR / "data" / "contacts.duckdb"
ETAT = BASE_DIR / "logs" / "verrou_watchdog_etat.json"

SEUIL_MIN_DEFAUT = 30

# Travaux de fond qu'on peut interrompre sans rien perdre : ils reprennent au run
# suivant et leur travail est idempotent. Nom du script -> nom de l'app PM2 (ou None
# si lancé par cron, auquel cas on signale le PID directement).
INTERRUPTIBLES = {
    "nightly_cleanup.py": "genesis-nightly-cleanup",
    "datagouv_enrich.py": None,
    "pg_sync_enrichment.py": None,
    "pg_reconcile.py": None,
}

# Jamais touchés, quoi qu'il arrive : les arrêter coupe le service au lieu de le
# réparer. Le veilleur se contente d'alerter.
INTOUCHABLES = ("api.py", "uvicorn", "next", "node", "genesis-ui")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _notify(msg: str) -> None:
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    try:
        from autoscrape_backend import notify_telegram
        notify_telegram(msg)
    except Exception as e:  # noqa: BLE001
        print(f"[verrou_watchdog] alerte Telegram impossible : {e}", flush=True)


def pool_lisible() -> tuple[bool, str]:
    """Épreuve réelle : ouvrir le pool en lecture seule. Renvoie (ok, message)."""
    try:
        import duckdb
        c = duckdb.connect(str(POOL_DB), read_only=True)
        c.execute("SELECT 1").fetchone()
        c.close()
        return True, "pool lisible"
    except Exception as e:  # noqa: BLE001
        return False, str(e).split("\n")[0][:300]


def detenteurs() -> list[dict]:
    """Processus tenant le fichier du pool, avec leur âge et leur ligne de commande."""
    out: list[dict] = []
    try:
        r = subprocess.run(["fuser", str(POOL_DB)], capture_output=True, text=True, timeout=15)
        pids = [p for p in (r.stdout + " " + r.stderr).replace(str(POOL_DB) + ":", "").split() if p.isdigit()]
    except Exception:  # noqa: BLE001
        pids = []
    for pid in dict.fromkeys(pids):
        try:
            ps = subprocess.run(["ps", "-o", "etimes=,user=,args=", "-p", pid],
                                capture_output=True, text=True, timeout=10)
            ligne = ps.stdout.strip()
            if not ligne:
                continue
            parts = ligne.split(None, 2)
            out.append({"pid": int(pid), "age_s": int(parts[0]), "user": parts[1],
                        "cmd": parts[2] if len(parts) > 2 else ""})
        except Exception:  # noqa: BLE001
            continue
    return out


def _script_de(cmd: str) -> str | None:
    for nom in INTERRUPTIBLES:
        if nom in cmd:
            return nom
    return None


def arreter(d: dict, dry_run: bool) -> str:
    """Arrête un détenteur interruptible. Renvoie ce qui a été fait, en clair."""
    script = _script_de(d["cmd"])
    if script is None:
        return "laissé en place (hors liste blanche)"
    app = INTERRUPTIBLES[script]
    if dry_run:
        return f"À ARRÊTER : {script}" + (f" (pm2 {app})" if app else f" (PID {d['pid']})")
    if app:
        # Via PM2 quand c'est PM2 qui l'a lancé : sinon PM2 le relancerait aussitôt.
        subprocess.run(["sudo", "-u", "autoblog", "pm2", "stop", app],
                       capture_output=True, text=True, timeout=60)
        return f"arrêté via pm2 ({app})"
    subprocess.run(["kill", "-TERM", str(d["pid"])], capture_output=True, timeout=15)
    return f"SIGTERM envoyé au PID {d['pid']}"


def rejouer_engagements() -> dict:
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    try:
        import engagement_spool as spool
        if spool.en_attente() == 0:
            return {"rejoues": 0, "restants": 0}
        return spool.rejouer()
    except Exception as e:  # noqa: BLE001
        return {"erreur": str(e)[:200]}


def _etat_lu() -> dict:
    try:
        return json.loads(ETAT.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _etat_ecrit(d: dict) -> None:
    try:
        ETAT.parent.mkdir(parents=True, exist_ok=True)
        ETAT.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seuil", type=float, default=SEUIL_MIN_DEFAUT,
                    help="âge en minutes au-delà duquel un détenteur est arrêté")
    ap.add_argument("--dry-run", action="store_true", help="diagnostic seul")
    args = ap.parse_args()
    seuil_s = args.seuil * 60

    etat = _etat_lu()
    ok, msg = pool_lisible()

    if ok:
        # Base libre : on en profite pour vider la file de secours.
        rej = rejouer_engagements()
        if rej.get("rejoues"):
            print(f"[{_now()}] pool libre — {rej['rejoues']} engagement(s) rejoué(s), "
                  f"{rej.get('restants', 0)} restant(s)", flush=True)
        else:
            print(f"[{_now()}] pool libre — rien à rejouer", flush=True)
        if etat.get("incident"):
            duree = etat.get("depuis", "?")
            _notify(f"✅ *Pool contacts* — accès rétabli.\n"
                    f"Blocage ouvert depuis {duree}.\n"
                    f"Engagements rejoués : {rej.get('rejoues', 0)}.")
            _etat_ecrit({"incident": False, "dernier_ok": _now()})
        else:
            _etat_ecrit({"incident": False, "dernier_ok": _now()})
        return 0

    # Pool bloqué.
    dets = detenteurs()
    print(f"[{_now()}] POOL BLOQUÉ — {msg}", flush=True)
    for d in dets:
        print(f"    PID {d['pid']} ({d['user']}) depuis {d['age_s'] // 60} min : {d['cmd'][:110]}", flush=True)

    actions, bloqueurs = [], []
    for d in dets:
        intouchable = any(k in d["cmd"] for k in INTOUCHABLES)
        if intouchable:
            continue
        bloqueurs.append(d)
        if d["age_s"] >= seuil_s:
            fait = arreter(d, args.dry_run)
            actions.append(f"PID {d['pid']} ({d['age_s'] // 60} min) : {fait}")
            print(f"    -> {fait}", flush=True)

    rej = {}
    if actions and not args.dry_run:
        ok2, _ = pool_lisible()
        if ok2:
            rej = rejouer_engagements()
            print(f"    -> pool libéré, {rej.get('rejoues', 0)} engagement(s) rejoué(s)", flush=True)

    # Une alerte par incident, pas une par passage.
    if not etat.get("incident"):
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        try:
            import engagement_spool as spool
            attente = spool.en_attente()
        except Exception:  # noqa: BLE001
            attente = 0
        detail = "\n".join(f"• PID {d['pid']} — {d['age_s'] // 60} min — {Path(d['cmd'].split()[-1]).name}"
                           for d in (bloqueurs or dets)[:5]) or "• détenteur non identifié"
        _notify(f"\U0001f6a8 *Pool contacts bloqué*\n"
                f"Le pixel d'ouverture et les compteurs n'écrivent plus.\n\n"
                f"{detail}\n\n"
                f"Engagements en file : {attente}\n"
                + ("Action : " + " ; ".join(actions) if actions else "Aucune action : sous le seuil ou hors liste blanche."))
        _etat_ecrit({"incident": True, "depuis": _now(), "detenteurs": len(dets)})
    else:
        _etat_ecrit({**etat, "incident": True, "dernier_ko": _now()})

    return 1


if __name__ == "__main__":
    sys.exit(main())
