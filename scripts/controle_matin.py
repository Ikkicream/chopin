"""Contrôle du matin (demande de Camille, 05/10) : « chaque matin, vérifier qu'une campagne
parte, et pendant 2 jours que le scraping se passe bien ».

Lecture seule. Envoie un rapport Telegram (canal d'alerte habituel) :
  1. campagnes programmées / en cours : envois du jour, erreur éventuelle ;
  2. Mozart : passages du jour par scénario actif ;
  3. collecte (jusqu'au SCRAPING_JUSQU_AU inclus) : contacts ajoutés depuis 24 h par source,
     erreurs de verrou contacts.duckdb depuis le dernier contrôle, crédits Basile / Serper.

Usage : python3 scripts/controle_matin.py [--dry]   (--dry : affiche sans envoyer)
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))

SITE = "lcr"
SCRAPING_JUSQU_AU = date(2026, 10, 7)
LOG_COLLECTE = BASE / "logs" / "autoscrape_daily.log"
ETAT = BASE / "memory" / "autoscrape" / "controle-matin.json"


def _dsn() -> str:
    for l in (BASE / ".env").read_text().splitlines():
        if l.startswith("PG_DSN="):
            return l.split("=", 1)[1].strip()
    raise RuntimeError("PG_DSN absent")


def _q(sql, params=None):
    import psycopg2
    with psycopg2.connect(_dsn()) as c, c.cursor() as cur:
        cur.execute(sql, params or [])
        return cur.fetchall()


def campagnes() -> tuple[list[str], bool]:
    lignes, alerte = [], False
    rows = _q("""
        SELECT c.name, c.status, c.sent_count, c.last_error,
               count(DISTINCT ev.email) FILTER (WHERE ev.event_type = 'sent')
        FROM campaigns c
        LEFT JOIN email_events ev ON ev.campaign_id = c.id
             AND ev.occurred_at >= date_trunc('day', now() AT TIME ZONE 'Europe/Paris') AT TIME ZONE 'Europe/Paris'
        WHERE c.site_code = %s AND c.status IN ('scheduled', 'running')
              AND c.schedule_start <= current_date
        GROUP BY 1, 2, 3, 4 ORDER BY 1""", [SITE])
    if not rows:
        return ["⚠️ aucune campagne programmée ou en cours"], True
    for nom, statut, total, err, auj in rows:
        ok = auj > 0
        alerte |= not ok
        l = f"{'✅' if ok else '❌'} {nom} : {auj} envoyés aujourd'hui (total {total}, {statut})"
        if err:
            l += f"\n   erreur : {err[:150]}"
        lignes.append(l)
    return lignes, alerte


def mozart() -> list[str]:
    rows = _q("""
        SELECT s.nom, s.statut,
               count(*) FILTER (WHERE p.type_noeud = 'email' AND p.quand >= current_date),
               count(*) FILTER (WHERE p.quand >= current_date)
        FROM mozart_scenarios s
        LEFT JOIN mozart_passages p ON p.scenario_id = s.id
        WHERE s.statut IN ('active', 'actif') GROUP BY 1, 2 ORDER BY 1""")
    return [f"• {nom} : {em} emails, {tot} passages" for nom, _, em, tot in rows] or ["• aucun scénario actif"]


def collecte() -> tuple[list[str], bool]:
    alerte = False
    rows = _q("""SELECT coalesce(primary_source, '?'), count(*) FROM contacts
                 WHERE created_at >= now() - interval '24 hours' GROUP BY 1 ORDER BY 2 DESC""")
    total = sum(n for _, n in rows)
    lignes = [f"Contacts ajoutés (24 h) : {total} — " + (", ".join(f"{s} {n}" for s, n in rows) or "aucun")]
    alerte |= total == 0

    etat = {}
    try:
        etat = json.loads(ETAT.read_text())
    except Exception:
        pass
    try:
        nb = sum(1 for l in LOG_COLLECTE.open(errors="ignore") if "Could not set lock" in l)
    except Exception:
        nb = None
    if nb is not None:
        nouv = nb - etat.get("erreurs_verrou", nb) if nb >= etat.get("erreurs_verrou", 0) else nb
        lignes.append(f"Leads perdus sur verrou contacts.duckdb depuis le dernier contrôle : {nouv}")
        alerte |= nouv > 0
        etat["erreurs_verrou"] = nb
    try:
        import basile_quota
        lignes.append(f"Basile restant : {basile_quota.restant():,}".replace(",", " "))
    except Exception as e:
        lignes.append(f"Basile : illisible ({type(e).__name__})")
    try:
        s = json.loads((BASE / "memory/seo/serper-balance.json").read_text())
        lignes.append(f"Serper : {s.get('balance'):,} crédits".replace(",", " "))
    except Exception:
        pass
    try:
        st = json.loads((BASE / "memory/autoscrape/lcr-status.json").read_text())
        lignes.append(f"Statut : {st.get('status')} — {st.get('message') or ''} (dépt {st.get('current_dept')}, gardés {st.get('kept_total')})")
    except Exception:
        pass
    etat["dernier"] = datetime.now().isoformat()
    try:
        ETAT.write_text(json.dumps(etat))
    except Exception:
        pass
    return lignes, alerte


def main():
    dry = "--dry" in sys.argv
    out = [f"☀️ Contrôle du matin {date.today():%d/%m}"]
    alerte = False
    try:
        l, a = campagnes(); alerte |= a
        out += ["", "📨 Campagnes"] + l
    except Exception as e:
        out += ["", f"📨 Campagnes : lecture impossible ({e})"]; alerte = True
    try:
        out += ["", "🎼 Mozart"] + mozart()
    except Exception as e:
        out += ["", f"🎼 Mozart : lecture impossible ({e})"]
    if date.today() <= SCRAPING_JUSQU_AU:
        try:
            l, a = collecte(); alerte |= a
            out += ["", "🔎 Collecte"] + l
        except Exception as e:
            out += ["", f"🔎 Collecte : lecture impossible ({e})"]; alerte = True
    out.insert(1, "🔴 À REGARDER" if alerte else "🟢 Tout part")
    msg = "\n".join(out)
    print(msg)
    if not dry:
        import autoscrape_backend as asb
        asb.notify_telegram(msg)


if __name__ == "__main__":
    main()
