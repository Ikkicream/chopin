#!/usr/bin/env python3
"""etat_technique.py — le relevé quotidien de l'état de la plateforme.

Une seule question : « est-ce que tout a tourné cette nuit ? ». Y répondre demandait
jusqu'ici d'ouvrir cinq écrans et deux terminaux. Ce module rassemble en un objet ce qu'on
veut vérifier chaque matin :

  - le POIDS des bases et le nombre de lignes par table (DuckDB et PostgreSQL) ;
  - ce qui est ENTRÉ hier : scraping Serper, collecte Basile ;
  - ce qui a été NETTOYÉ : vérifications Mailnjoy, rejets ;
  - ce qui a été ENRICHI : rapprochements data.gouv ;
  - ce qui est SORTI : emails envoyés, par canal ;
  - la FRAÎCHEUR des tâches planifiées (dernier passage de chaque cron).

Le relevé est écrit une fois par jour dans `etat_technique_journalier` (PostgreSQL) : une
photo par matin, qu'on peut comparer. Un compteur qui stagne trois jours de suite se voit
alors sans avoir à s'en souvenir.

Lecture seule sur les bases métier — ce module n'écrit que sa propre table.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
PARIS = ZoneInfo("Europe/Paris")
POOL_DB = BASE_DIR / "data" / "contacts.duckdb"
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"
AUTH_DB = BASE_DIR / "data" / "auth.duckdb"


def _dsn() -> str:
    for ligne in (BASE_DIR / ".env").read_text().splitlines():
        if ligne.startswith("PG_DSN="):
            return ligne.split("=", 1)[1].strip()
    raise RuntimeError("PG_DSN absent de .env")


def _pg():
    import psycopg2
    return psycopg2.connect(_dsn())


def _duck(chemin):
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    from duck_ouverture import ouvrir
    return ouvrir(chemin)


def _octets(p: Path) -> int:
    try:
        return p.stat().st_size
    except Exception:
        return 0


def _hier_paris() -> tuple[str, str]:
    """Bornes de la journée d'hier, en heure de Paris — la journée telle qu'on la vit."""
    minuit = datetime.now(PARIS).replace(hour=0, minute=0, second=0, microsecond=0)
    return (minuit - timedelta(days=1)).isoformat(), minuit.isoformat()


# ── Collecte ──────────────────────────────────────────────────────────────────

def _bases() -> dict:
    """Poids des fichiers et lignes par table. C'est la vue « qu'est-ce qui grossit ? »."""
    out = {"fichiers": {
        "contacts.duckdb": _octets(POOL_DB),
        "god_mode.duckdb": _octets(GOD_DB),
        "auth.duckdb": _octets(AUTH_DB),
    }, "tables": {}}

    for nom, chemin, tables in (
        ("pool", POOL_DB, ("contacts", "contact_site_history", "contact_enrichment",
                           "email_suppression")),
        ("god_mode", GOD_DB, ("scrappe", "scrappe_pending", "scrappe_rejected",
                              "maildoso_sent", "mass_campaigns", "sweego_events",
                              "god_mode_serper_calls", "autoscrape_targets")),
    ):
        try:
            c = _duck(chemin)
            try:
                for t in tables:
                    try:
                        out["tables"][f"{nom}.{t}"] = int(
                            c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0])
                    except Exception:
                        out["tables"][f"{nom}.{t}"] = None
            finally:
                c.close()
        except Exception as e:  # noqa: BLE001
            out.setdefault("erreurs", []).append(f"{nom}: {str(e)[:120]}")

    try:
        c = _pg()
        try:
            with c.cursor() as cur:
                cur.execute("SELECT pg_database_size(current_database())")
                out["fichiers"]["postgresql"] = int(cur.fetchone()[0])
                cur.execute("""SELECT relname, n_live_tup FROM pg_stat_user_tables
                               ORDER BY n_live_tup DESC""")
                for nom_t, n in cur.fetchall():
                    out["tables"][f"pg.{nom_t}"] = int(n)
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        out.setdefault("erreurs", []).append(f"postgresql: {str(e)[:120]}")
    return out


def _flux(debut: str, fin: str) -> dict:
    """Ce qui est entré, a été nettoyé, enrichi et envoyé sur la période."""
    f = {"scrape_serper": 0, "scrape_basile": 0, "mailnjoy_verifies": 0,
         "mailnjoy_rejetes": 0, "datagouv_enrichis": 0, "emails_envoyes": 0,
         "contacts_crees": 0, "en_attente_mailnjoy": 0}
    try:
        c = _duck(POOL_DB)
        try:
            f["contacts_crees"] = int(c.execute(
                "SELECT count(*) FROM contacts WHERE created_at >= ? AND created_at < ?",
                [debut, fin]).fetchone()[0])
            for source, cle in (("serper", "scrape_serper"), ("basile", "scrape_basile")):
                f[cle] = int(c.execute(
                    "SELECT count(*) FROM contacts WHERE primary_source = ? "
                    "AND created_at >= ? AND created_at < ?",
                    [source, debut, fin]).fetchone()[0])
            f["mailnjoy_verifies"] = int(c.execute(
                "SELECT count(*) FROM contacts WHERE mailnjoy_check IS NOT NULL "
                "AND json_extract_string(mailnjoy_check, '$.checked_at') >= ? "
                "AND json_extract_string(mailnjoy_check, '$.checked_at') < ?",
                [debut[:19], fin[:19]]).fetchone()[0])
            f["datagouv_enrichis"] = int(c.execute(
                "SELECT count(*) FROM contact_enrichment WHERE enriched_at >= ? "
                "AND enriched_at < ?", [debut, fin]).fetchone()[0])
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        f.setdefault("erreurs", []).append(f"pool: {str(e)[:120]}")

    try:
        c = _duck(GOD_DB)
        try:
            f["emails_envoyes"] = int(c.execute(
                "SELECT count(*) FROM maildoso_sent WHERE status = 'sent' "
                "AND created_at >= ? AND created_at < ?", [debut, fin]).fetchone()[0])
            f["mailnjoy_rejetes"] = int(c.execute(
                "SELECT count(*) FROM scrappe_rejected WHERE last_seen >= ? AND last_seen < ?",
                [debut, fin]).fetchone()[0])
            f["en_attente_mailnjoy"] = int(c.execute(
                "SELECT count(*) FROM scrappe_pending").fetchone()[0])
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        f.setdefault("erreurs", []).append(f"god_mode: {str(e)[:120]}")
    return f


def _crm() -> dict:
    """Ce que le suivi commercial contient — la sortie utile de toute la chaîne."""
    out = {"a_rappeler": 0, "attribues": 0, "appels_7j": 0, "rdv_a_traiter": 0}
    try:
        c = _pg()
        try:
            with c.cursor() as cur:
                cur.execute("SELECT count(*), count(*) FILTER (WHERE assigned_to IS NOT NULL) "
                            "FROM v_a_rappeler")
                out["a_rappeler"], out["attribues"] = cur.fetchone()
                cur.execute("SELECT count(*) FROM followup_events WHERE type = 'appel' "
                            "AND occurred_at > now() - interval '7 days'")
                out["appels_7j"] = int(cur.fetchone()[0])
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        out["erreur"] = str(e)[:120]
    return out


# Les tâches planifiées qu'on veut voir passer, et le fichier qui prouve leur passage.
_TACHES = {
    "enrichissement data.gouv": "logs/datagouv_enrich.log",
    "réconciliation PostgreSQL": "logs/pg_reconcile.log",
    # Le cron écrit dans memory/shared, pas dans logs/ : le chemin logs/ n'a jamais existé,
    # donc la tuile « dispatch campagnes » affichait « absent » alors que la tâche tournait
    # tous les jours. Un indicateur faux est pire que pas d'indicateur — il use la confiance.
    "dispatch campagnes": "memory/shared/campaign-dispatch.log",
    "sauvegarde": "backups/backup.log",
    # Ajoutées le 2026-08-23 avec les tâches correspondantes. Une tâche planifiée non
    # surveillée est une panne qui dure jusqu'à ce que quelqu'un la remarque : le
    # 2026-08-20, `pg_reconcile` s'est tu 74 heures parce qu'un fichier de log
    # appartenait à root, et rien ne l'a signalé. Chaque cron ajouté doit entrer ici en
    # même temps que dans la crontab.
    "rattrapage du pool": "logs/pool_rattrapage.log",
    "miroir enrichissement": "logs/pg_sync_enrichment.log",
    "délivrabilité": "logs/sante_envoi.log",
    "programmation des envois": "logs/programmation.log",
    "collecte": "logs/autoscrape_daily.log",
    "statistiques": "logs/stats.log",
    "plancher de collecte": "logs/plancher_collecte.log",
    "dirigeants nommés": "logs/dirigeants.log",
}


def _taches() -> dict:
    """Fraîcheur des tâches planifiées : l'heure du dernier passage, et son âge."""
    out = {}
    maintenant = datetime.now(timezone.utc)
    for nom, rel in _TACHES.items():
        p = BASE_DIR / rel
        if not p.exists():
            out[nom] = {"present": False}
            continue
        modifie = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
        out[nom] = {"present": True,
                    "dernier": modifie.isoformat(timespec="seconds"),
                    "heures": round((maintenant - modifie).total_seconds() / 3600, 1),
                    "octets": p.stat().st_size,
                    "echec": _fin_en_erreur(p)}
    return out


# Un passage qui meurt laisse sa dernière ligne sur l'exception qui l'a tué. On cherche
# CETTE forme, et rien d'autre : chercher un mot comme « error » dans la fin du journal
# faisait crier `datagouv_enrich` pour un avertissement sur une société introuvable — un
# avertissement légitime, au milieu d'un passage qui s'est parfaitement terminé. Une
# alerte fausse est pire qu'aucune alerte : elle apprend à ne plus les lire.
import re as _re

_LIGNE_EXCEPTION = _re.compile(
    r"^\s*(?:[A-Za-z_][\w.]*\.)?[A-Za-z_]\w*"
    r"(?:Error|Exception|Interrupt|Exit|Timeout|Failure)\b\s*:")


def _fin_en_erreur(chemin, octets: int = 4000) -> str | None:
    """La dernière exécution s'est-elle terminée sur une exception ?

    La fraîcheur d'un journal ne dit rien de son contenu : une tâche qui meurt écrit son
    traceback, donc son fichier est tout frais et la surveillance de fraîcheur la déclare
    en forme. C'est ce qui a laissé `pg_sync_enrichment` mort pendant des heures le
    2026-08-24, avec un miroir dérivé de 2 650 lignes et aucune alerte.

    On ne regarde que la DERNIÈRE ligne utile : un passage réussi écrit après l'échec du
    précédent, et seul le dernier mot compte.
    """
    try:
        with open(chemin, "rb") as f:
            f.seek(max(0, chemin.stat().st_size - octets))
            fin = f.read().decode(errors="replace")
    except Exception:  # noqa: BLE001
        return None
    lignes = [l for l in fin.splitlines() if l.strip()]
    if not lignes:
        return None
    derniere = lignes[-1]
    if _LIGNE_EXCEPTION.match(derniere) or derniere.startswith("Traceback"):
        return derniere.strip()[:200]
    return None


def _services() -> dict:
    """Process PM2 attendus. On ne redémarre rien : on constate.

    On interroge PM2 lui-même. L'ancien `pgrep -af "PM2|uvicorn|next"` cherchait le NOM PM2
    (« genesis-dashboard ») dans la ligne de commande des process — or il n'y figure pas :
    les trois services étaient donc annoncés éteints en permanence, y compris à l'instant où
    ils répondaient. Depuis root, PM2 ne voit pas les process d'autoblog : on repasse par lui.
    """
    attendus = ("genesis-dashboard", "genesis-ui", "genesis-mailnjoy-drain")
    etat = {n: False for n in attendus}
    for cmd in (["pm2", "jlist"], ["sudo", "-n", "-u", "autoblog", "pm2", "jlist"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            procs = json.loads(r.stdout or "[]")
        except Exception:  # noqa: BLE001 — PM2 absent ou sortie illisible : on tente la suite
            continue
        for p in procs:
            nom = p.get("name")
            if nom in etat and (p.get("pm2_env") or {}).get("status") == "online":
                etat[nom] = True
        if any(etat.values()):
            break
    return etat


def releve() -> dict:
    """Le relevé complet, prêt à afficher comme à stocker."""
    debut, fin = _hier_paris()
    return {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "jour": (datetime.now(PARIS).date() - timedelta(days=1)).isoformat(),
        "bases": _bases(),
        "flux_hier": _flux(debut, fin),
        "crm": _crm(),
        "taches": _taches(),
        "services": _services(),
    }


# ── Stockage : une photo par jour ─────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS etat_technique_journalier (
    jour        date PRIMARY KEY,          -- la journée décrite (hier)
    releve_at   timestamptz NOT NULL DEFAULT now(),
    donnees     jsonb NOT NULL
);
"""


def enregistrer(r: dict | None = None) -> dict:
    """Écrit le relevé du jour. Rejouable : une seule ligne par journée."""
    r = r or releve()
    c = _pg()
    try:
        with c:
            with c.cursor() as cur:
                cur.execute(SCHEMA)
                cur.execute("""INSERT INTO etat_technique_journalier (jour, donnees)
                               VALUES (%s, %s::jsonb)
                               ON CONFLICT (jour) DO UPDATE
                                 SET donnees = EXCLUDED.donnees, releve_at = now()""",
                            [r["jour"], json.dumps(r, ensure_ascii=False)])
    finally:
        c.close()
    return r


def historique(jours: int = 14) -> list[dict]:
    """Les derniers relevés, du plus récent au plus ancien."""
    c = _pg()
    try:
        with c.cursor() as cur:
            cur.execute("SELECT to_regclass('etat_technique_journalier')")
            if cur.fetchone()[0] is None:
                return []
            cur.execute("""SELECT jour, releve_at, donnees FROM etat_technique_journalier
                           ORDER BY jour DESC LIMIT %s""", [jours])
            return [{"jour": str(j), "releve_at": str(a), **d} for j, a, d in cur.fetchall()]
    finally:
        c.close()


if __name__ == "__main__":
    r = enregistrer() if "--enregistrer" in sys.argv else releve()
    print(json.dumps(r, indent=1, ensure_ascii=False))
