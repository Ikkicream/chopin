"""
maildoso_ramp.py — Montée en charge progressive des boîtes Maildoso.

Routine simple, déterministe, appelée automatiquement après chaque campagne dispatchée
sur le canal maildoso (fin de la branche maildoso de campaign_engine._send_batch),
idempotente : 1 ajustement max par boîte et par jour.

Règle (fenêtre = 3 derniers jours calendaires dans maildoso_sent) :
- taux d'erreur SMTP > 10 %                        → cap -10 (plancher 10)
- 0 erreur ET dernier jour actif ≥ 60 % du cap     → cap +5  (plafond 40)
- sinon                                            → inchangé

Le cap CANAL suit automatiquement : deliverability_agent lit la somme des caps
des boîtes actives, et la card Cheffer affiche ce que renvoie /channels.

CLI : python3 scripts/maildoso_ramp.py [run|status]   (run = ajuste, status = dry-run)
"""
from __future__ import annotations

import json
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"

CAP_MIN, CAP_MAX = 10, 40
STEP_UP, STEP_DOWN = 5, 10
WINDOW_DAYS = 3
ERROR_RATE_DOWN = 0.10   # >10 % d'erreurs SMTP → on réduit
USAGE_RATE_UP = 0.60     # dernier jour actif ≥ 60 % du cap → on peut monter


def _conn():
    return duckdb.connect(str(GOD_DB))


def _ensure_log_table(c):
    c.execute(
        """CREATE TABLE IF NOT EXISTS maildoso_ramp_log (
            mailbox     VARCHAR,
            day         DATE,
            old_cap     INTEGER,
            new_cap     INTEGER,
            reason      VARCHAR,
            sent_window INTEGER,
            err_window  INTEGER,
            created_at  TIMESTAMP,
            PRIMARY KEY (mailbox, day)
        )"""
    )


def _decide(cap: int, sent_w: int, err_w: int, last_day_sent: int) -> tuple[int, str]:
    """Nouveau cap + raison, à partir de la fenêtre (sent/err) et du dernier jour actif."""
    total = sent_w + err_w
    if total and err_w / total > ERROR_RATE_DOWN:
        return max(CAP_MIN, cap - STEP_DOWN), f"erreurs {err_w}/{total} (>10%) → -{STEP_DOWN}"
    if err_w == 0 and last_day_sent >= max(1, int(cap * USAGE_RATE_UP)):
        if cap >= CAP_MAX:
            return cap, f"plafond {CAP_MAX} atteint"
        return min(CAP_MAX, cap + STEP_UP), f"journée propre ({last_day_sent}/{cap}) → +{STEP_UP}"
    return cap, "inchangé (activité insuffisante ou erreurs résiduelles)"


def adjust_caps(site: str = "lcr", dry_run: bool = False, today: _date | None = None) -> dict:
    """Ajuste le daily_cap de chaque boîte active. Idempotent : 1 fois par boîte/jour."""
    today = today or _date.today()
    since = today - timedelta(days=WINDOW_DAYS)
    c = _conn()
    decisions = []
    try:
        _ensure_log_table(c)
        boxes = c.execute(
            "SELECT email, daily_cap FROM mailboxes "
            "WHERE site_code=? AND provider='maildoso' AND status='active' ORDER BY email",
            [site]).fetchall()
        for email, cap in boxes:
            already = c.execute("SELECT 1 FROM maildoso_ramp_log WHERE mailbox=? AND day=?",
                                [email, today]).fetchone()
            if already:
                decisions.append({"mailbox": email, "cap": cap, "reason": "déjà ajusté aujourd'hui"})
                continue
            sent_w, err_w = c.execute(
                "SELECT COALESCE(SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END),0), "
                "       COALESCE(SUM(CASE WHEN status='error' THEN 1 ELSE 0 END),0) "
                "FROM maildoso_sent WHERE mailbox=? AND created_at >= ?", [email, since]).fetchone()
            r = c.execute(
                "SELECT COUNT(*) FROM maildoso_sent WHERE mailbox=? AND status='sent' "
                "AND CAST(created_at AS DATE) = "
                "  (SELECT MAX(CAST(created_at AS DATE)) FROM maildoso_sent "
                "   WHERE mailbox=? AND status='sent' AND created_at >= ?)",
                [email, email, since]).fetchone()
            last_day_sent = int(r[0] or 0)
            new_cap, reason = _decide(int(cap), int(sent_w), int(err_w), last_day_sent)
            decisions.append({"mailbox": email, "old_cap": int(cap), "new_cap": new_cap,
                              "reason": reason, "sent_3j": int(sent_w), "err_3j": int(err_w)})
            if not dry_run:
                if new_cap != cap:
                    c.execute("UPDATE mailboxes SET daily_cap=? WHERE email=?", [new_cap, email])
                c.execute("INSERT INTO maildoso_ramp_log VALUES (?,?,?,?,?,?,?,?)",
                          [email, today, int(cap), new_cap, reason, int(sent_w), int(err_w),
                           datetime.now(timezone.utc)])
    finally:
        c.close()
    channel_cap = sum(d.get("new_cap", d.get("cap", 0)) for d in decisions)
    return {"ok": True, "dry_run": dry_run, "day": today.isoformat(),
            "decisions": decisions, "channel_cap": channel_cap}


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    res = adjust_caps(dry_run=(cmd != "run"))
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
