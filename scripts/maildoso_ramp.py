"""
maildoso_ramp.py — Montée en charge progressive des boîtes Maildoso.

Routine simple, déterministe, appelée automatiquement après chaque campagne dispatchée
sur le canal maildoso (fin de la branche maildoso de campaign_engine._send_batch),
idempotente : 1 ajustement max par boîte et par jour.

Règle, dans l'ordre où elle est appliquée — les signaux qui font perdre un domaine
d'abord, la montée en dernier :

- plainte  > 0,1 %  → cap divisé par deux (plancher 10)
- rebond   > 3 %    → cap -10
- ouverture < 5 % sur ≥ 50 envois → cap -10
- erreur SMTP > 10 % → cap -10
- aucun signal ET dernier jour actif ≥ 60 % du cap → cap +5 (plafond 40)
- sinon → inchangé

**Pourquoi ces signaux-là et pas les erreurs SMTP seules.** La version d'origine ne
regardait que le taux d'erreur SMTP. Or il vaut ZÉRO depuis toujours — 1 462 envois
journalisés, aucun en erreur : un serveur qui accepte le message ne dit rien de ce qu'il
en fait ensuite. La règle ne pouvait donc que monter, jamais descendre, et une boîte en
train de se faire classer en indésirables continuait d'augmenter son volume. Ce qui
prévient vraiment, c'est ce que font les DESTINATAIRES : ils se plaignent, ça rebondit,
ils n'ouvrent plus. Ces trois-là arrivent des semaines avant le blocage.

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
# Les seuils de délivrabilité viennent de `sante_envoi` : un seuil écrit à deux endroits
# finit par diverger, et c'est celui qui protège le domaine.
try:
    from sante_envoi import (SEUIL_OUVERTURE, SEUIL_REBOND, SEUIL_PLAINTE,
                             VOLUME_MINIMUM)
except Exception:  # noqa: BLE001 — le module d'origine doit rester exécutable seul
    SEUIL_OUVERTURE, SEUIL_REBOND, SEUIL_PLAINTE, VOLUME_MINIMUM = 5.0, 3.0, 0.1, 50
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


def _decide(cap: int, sent_w: int, err_w: int, last_day_sent: int,
            sante: dict | None = None) -> tuple[int, str]:
    """Nouveau cap + raison.

    `sante` est le relevé de `sante_envoi.taux()` pour CETTE boîte : taux d'ouverture, de
    rebond et de plainte sur la fenêtre, plus un drapeau `concluant` qui dit si le volume
    suffit pour en tirer une conclusion. Absent, on retombe sur l'ancienne règle — un
    relevé indisponible ne doit pas figer la montée en charge, mais il ne doit pas non
    plus la laisser monter à l'aveugle : sans `sante`, on n'augmente pas.
    """
    sante = sante or {}
    concluant = bool(sante.get("concluant"))

    # 1. La plainte : le signal le plus grave et le plus rapide à coûter un domaine.
    #    On ne retire pas 10, on divise par deux — à ce stade, gagner du temps compte plus
    #    que garder du volume.
    if concluant and (sante.get("taux_plainte") or 0) > SEUIL_PLAINTE:
        return (max(CAP_MIN, cap // 2),
                f"plaintes {sante['taux_plainte']} % (> {SEUIL_PLAINTE} %) → cap divisé par deux")

    # 2. Le rebond : la liste s'abîme, ou la vérification laisse passer.
    if concluant and (sante.get("taux_rebond") or 0) > SEUIL_REBOND:
        return (max(CAP_MIN, cap - STEP_DOWN),
                f"rebonds {sante['taux_rebond']} % (> {SEUIL_REBOND} %) → -{STEP_DOWN}")

    # 3. L'ouverture : personne ne lit plus. Le message arrive encore, mais en indésirables.
    if concluant and (sante.get("taux_ouverture") or 0) < SEUIL_OUVERTURE:
        return (max(CAP_MIN, cap - STEP_DOWN),
                f"ouverture {sante['taux_ouverture']} % (< {SEUIL_OUVERTURE} %) → -{STEP_DOWN}")

    # 4. Les erreurs SMTP : rare, mais sans appel quand ça arrive.
    total = sent_w + err_w
    if total and err_w / total > ERROR_RATE_DOWN:
        return max(CAP_MIN, cap - STEP_DOWN), f"erreurs {err_w}/{total} (>10%) → -{STEP_DOWN}"

    # 5. La montée, seulement si tout le reste est propre ET qu'on a de quoi juger.
    if err_w == 0 and last_day_sent >= max(1, int(cap * USAGE_RATE_UP)):
        if cap >= CAP_MAX:
            return cap, f"plafond {CAP_MAX} atteint"
        if not concluant:
            return cap, (f"inchangé — {sante.get('envoyes', 0)} envois sur la fenêtre, "
                         f"pas assez pour conclure (minimum {VOLUME_MINIMUM})")
        return (min(CAP_MAX, cap + STEP_UP),
                f"journée propre ({last_day_sent}/{cap}), ouverture "
                f"{sante.get('taux_ouverture')} % → +{STEP_UP}")
    return cap, "inchangé (activité insuffisante ou erreurs résiduelles)"


def adjust_caps(site: str = "lcr", dry_run: bool = False, today: _date | None = None) -> dict:
    """Ajuste le daily_cap de chaque boîte active. Idempotent : 1 fois par boîte/jour."""
    today = today or _date.today()
    since = today - timedelta(days=WINDOW_DAYS)
    c = _conn()
    decisions = []
    try:
        _ensure_log_table(c)
        # Une seule requête PostgreSQL pour toutes les boîtes, avant la boucle : la
        # variante par boîte multipliait les allers-retours sans rien apporter.
        _volumes = None
        try:
            import journal_pg
            _volumes = journal_pg.volume_par_boite(site, since)
        except Exception as e:  # noqa: BLE001
            print(f"[ramp] volumes: PostgreSQL indisponible ({type(e).__name__}: {e}) "
                  f"— repli DuckDB", flush=True)
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
            # Volumes lus dans PostgreSQL (fin du Lot 1). C'est LA lecture qui décide
            # combien chaque boîte a le droit d'envoyer demain : la laisser sur
            # `god_mode.duckdb` revenait à piloter la délivrabilité depuis le fichier dont
            # le verrou fait échouer les écritures d'envoi. Le comptage y est fait par
            # ENVOI distinct (adresse, campagne, jour) et non par ligne : une reprise de
            # marquage pouvait écrire deux fois, et 316 lignes pour 160 envois auraient
            # fait croire les boîtes saturées.
            sent_w = err_w = None
            if _volumes is not None:
                v = _volumes.get(email)
                sent_w = int((v or {}).get("envoyes", 0))
                err_w = 0          # cf. journal_pg.stats_canal : aucun échec journalisé
                last_day_sent = int((v or {}).get("dernier_jour_envoyes", 0))
            if sent_w is None:
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
            # Le relevé de délivrabilité de CETTE boîte : c'est lui qui autorise ou
            # interdit la montée, pas le seul compteur d'envois.
            releve = None
            try:
                import sante_envoi
                releve = sante_envoi.taux(site, mailbox=email)
            except Exception as e:  # noqa: BLE001
                print(f"[ramp] santé de {email} illisible ({type(e).__name__}: {e}) "
                      f"— pas d'augmentation ce tour", flush=True)
            new_cap, reason = _decide(int(cap), int(sent_w), int(err_w), last_day_sent,
                                      sante=releve)
            decisions.append({"mailbox": email, "old_cap": int(cap), "new_cap": new_cap,
                              "reason": reason, "sent_3j": int(sent_w), "err_3j": int(err_w),
                              "ouverture": (releve or {}).get("taux_ouverture"),
                              "rebond": (releve or {}).get("taux_rebond"),
                              "plainte": (releve or {}).get("taux_plainte")})
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
