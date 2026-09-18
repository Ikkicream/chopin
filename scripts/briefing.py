#!/usr/bin/env python3
"""
briefing.py — Rapport quotidien Emelia + Telegram
Exécuté chaque matin à 7h UTC par pm2 cron.
Ne déclenche AUCUN envoi d'email. Lecture seule sur Emelia.
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"
COSTS_LOG = BASE_DIR / "memory" / "shared" / "costs-log.json"
DASHBOARD_JSON = BASE_DIR / "data" / "dashboard.json"

BOUNCE_THRESHOLD = 0.05  # 5% → alerte (pas d'auto-pause, seulement alerte)


def load_env():
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip()
    return env


def emelia_query(api_key: str, query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(
        "https://api.emelia.io/graphql",
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise ValueError(f"Emelia GraphQL error: {data['errors']}")
    return data.get("data", {})


def get_campaign_stats(api_key: str) -> list[dict]:
    """
    Récupère toutes les campagnes et tente de calculer les stats
    via le comptage de contacts par statut.
    """
    campaigns_data = emelia_query(api_key, """
    {
      campaigns {
        _id
        name
        status
        createdAt
      }
    }
    """)
    campaigns = campaigns_data.get("campaigns", [])

    results = []
    for camp in campaigns:
        cid = camp["_id"]
        name = camp["name"]
        status = camp["status"]

        # Compter les contacts par statut (CONTACTED, BOUNCED, REPLIED, OPENED)
        counts = {}
        for contact_status in ["CONTACTED", "BOUNCED", "REPLIED", "OPENED", "CLICKED", "UNSUBSCRIBED"]:
            try:
                data = emelia_query(api_key, f"""
                {{
                  contacts(query: "status:{contact_status}") {{
                    _id
                  }}
                }}
                """)
                counts[contact_status.lower()] = len(data.get("contacts", []))
            except Exception:
                counts[contact_status.lower()] = 0

        total_contacted = counts.get("contacted", 0)
        bounced = counts.get("bounced", 0)
        replied = counts.get("replied", 0)
        opened = counts.get("opened", 0)

        bounce_rate = (bounced / total_contacted) if total_contacted > 0 else 0.0
        open_rate = (opened / total_contacted) if total_contacted > 0 else 0.0
        reply_rate = (replied / total_contacted) if total_contacted > 0 else 0.0

        results.append({
            "id": cid,
            "name": name,
            "status": status,
            "contacted": total_contacted,
            "bounced": bounced,
            "replied": replied,
            "opened": opened,
            "clicked": counts.get("clicked", 0),
            "unsubscribed": counts.get("unsubscribed", 0),
            "bounce_rate": bounce_rate,
            "open_rate": open_rate,
            "reply_rate": reply_rate,
            "needs_pause": bounce_rate > BOUNCE_THRESHOLD and status == "RUNNING",
        })

    return results


def get_contact_lists(api_key: str) -> list[dict]:
    data = emelia_query(api_key, """
    {
      contact_lists {
        _id
        name
      }
    }
    """)
    lists = data.get("contact_lists", [])
    result = []
    for cl in lists:
        try:
            detail = emelia_query(api_key, f"""
            {{
              contact_list(id: "{cl['_id']}") {{
                _id
                name
                contacts {{
                  count
                }}
              }}
            }}
            """)
            cl_data = detail.get("contact_list", {})
            count = cl_data.get("contacts", {}).get("count", 0)
            result.append({"id": cl["_id"], "name": cl["name"], "count": count})
        except Exception:
            result.append({"id": cl["_id"], "name": cl["name"], "count": 0})
    return result


def get_weekly_costs() -> dict:
    """Lit les coûts de la semaine courante depuis costs-log.json.

    costs-log.json est une liste plate d'entrées avec un champ `date` (YYYY-MM-DD).
    On filtre sur la semaine ISO courante (lundi → dimanche).
    """
    try:
        with open(COSTS_LOG) as f:
            log = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"week_cost": 0.0, "entries": 0, "budget_remaining": 10.0}

    if not isinstance(log, list):
        log = log.get("entries", []) if isinstance(log, dict) else []

    now = datetime.now(timezone.utc).date()
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)

    entries = []
    for e in log:
        d = e.get("date", "")
        try:
            edate = datetime.strptime(d, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if monday <= edate <= sunday:
            entries.append(e)

    total = sum(e.get("cost_usd", 0) for e in entries)
    return {"week_cost": round(total, 4), "entries": len(entries), "budget_remaining": round(10.0 - total, 4)}


def get_recent_articles() -> list[dict]:
    """Lit les articles publiés récemment depuis les fichiers memory."""
    articles = []
    for site in ["lcr", "mkd"]:
        path = BASE_DIR / "memory" / site / "articles-published.md"
        if not path.exists():
            continue
        lines = path.read_text().strip().split("\n")
        for line in lines:
            if line.startswith("|") and not line.startswith("| Date") and not line.startswith("|---"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 3:
                    articles.append({"site": site.upper(), "date": parts[0], "slug": parts[1], "title": parts[2]})
    # Trier par date DESC et garder les 5 derniers
    articles.sort(key=lambda x: x["date"], reverse=True)
    return articles[:5]


def format_telegram_message(campaigns: list, lists: list, costs: dict, articles: list) -> str:
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    lines = [f"*Genesis — Briefing du {now}*", ""]

    # Campagnes Emelia
    lines.append("*EMELIA — Campagnes*")
    if not campaigns:
        lines.append("  Aucune campagne active")
    else:
        for camp in campaigns:
            status_icon = {"RUNNING": "🟢", "PAUSED": "⏸", "DONE": "✅", "DRAFT": "📝"}.get(camp["status"], "❓")
            lines.append(f"  {status_icon} *{camp['name']}* — {camp['status']}")
            if camp["contacted"] > 0:
                lines.append(f"     Contactés: {camp['contacted']} | Ouverts: {camp['opened']} ({camp['open_rate']:.1%})")
                lines.append(f"     Réponses: {camp['replied']} ({camp['reply_rate']:.1%}) | Bounces: {camp['bounced']} ({camp['bounce_rate']:.1%})")
                if camp["needs_pause"]:
                    lines.append(f"     ⚠️ BOUNCE RATE CRITIQUE ({camp['bounce_rate']:.1%}) — PAUSE RECOMMANDÉE")
                if camp["replied"] > 0:
                    lines.append(f"     💬 {camp['replied']} RÉPONSE(S) — À TRAITER")
            else:
                lines.append(f"     Pas encore de contacts envoyés")

    lines.append("")

    # Listes de contacts
    lines.append("*EMELIA — Listes*")
    if lists:
        for cl in lists:
            lines.append(f"  📋 {cl['name']}: {cl['count']:,} contacts")
    else:
        lines.append("  Aucune liste")

    lines.append("")

    # Budget
    lines.append("*BUDGET SEMAINE*")
    budget_icon = "🟢" if costs["week_cost"] < 5 else ("🟡" if costs["week_cost"] < 8 else "🔴")
    lines.append(f"  {budget_icon} Dépensé: ${costs['week_cost']:.4f} / $10.00")
    lines.append(f"  Restant: ${costs['budget_remaining']:.4f} | Entrées: {costs['entries']}")

    lines.append("")

    # Articles récents
    lines.append("*ARTICLES RÉCENTS*")
    if articles:
        for art in articles[:3]:
            lines.append(f"  [{art['site']}] {art['date']} — {art['title'][:40]}...")
    else:
        lines.append("  Aucun article publié récemment")

    lines.append("")
    lines.append("_Genesis Swarm v1.0 — leclientroi.com & mkdgroupe.com_")

    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, message: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    return result.get("ok", False)


def update_dashboard(campaigns: list, lists: list, costs: dict):
    """Met à jour dashboard.json avec les données fraîches."""
    now_iso = datetime.now(timezone.utc).isoformat()

    # Charger l'existant ou créer
    try:
        with open(DASHBOARD_JSON) as f:
            dash = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        dash = {
            "meta": {},
            "modules": [],
            "runs": [],
            "sites": {"mkd": {}, "lcr": {}},
            "emelia": {},
        }

    dash["meta"]["lastUpdate"] = now_iso
    dash["meta"]["budgetSpentCents"] = int(costs["week_cost"] * 100)
    dash["meta"]["budgetTotalCents"] = 1000  # $10

    dash["emelia"] = {
        "lastSync": now_iso,
        "campaigns": campaigns,
        "contactLists": lists,
    }

    DASHBOARD_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(DASHBOARD_JSON, "w", encoding="utf-8") as f:
        json.dump(dash, f, indent=2, ensure_ascii=False)


def main(dry_run: bool = False):
    env = load_env()
    emelia_key = env.get("EMELIA_API_KEY", "")
    tg_token = env.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = env.get("TELEGRAM_CHAT_ID", "")

    print(f"[briefing] Démarrage {datetime.now(timezone.utc).isoformat()}")

    # 1. Stats Emelia
    print("[briefing] Récupération des campagnes Emelia...")
    try:
        campaigns = get_campaign_stats(emelia_key)
        print(f"  → {len(campaigns)} campagne(s) trouvée(s)")
    except Exception as e:
        print(f"  ⚠ Erreur Emelia campaigns: {e}")
        campaigns = []

    print("[briefing] Récupération des listes de contacts...")
    try:
        lists = get_contact_lists(emelia_key)
        print(f"  → {len(lists)} liste(s) trouvée(s)")
    except Exception as e:
        print(f"  ⚠ Erreur Emelia lists: {e}")
        lists = []

    # 2. Coûts semaine
    costs = get_weekly_costs()
    print(f"[briefing] Coût semaine: ${costs['week_cost']}")

    # 3. Articles récents
    articles = get_recent_articles()
    print(f"[briefing] Articles récents: {len(articles)}")

    # 4. Alertes critiques
    critical_alerts = []
    for camp in campaigns:
        if camp.get("needs_pause"):
            critical_alerts.append(f"CRITIQUE: Campagne '{camp['name']}' bounce rate {camp['bounce_rate']:.1%} — À PAUSER MANUELLEMENT")
        if camp.get("replied", 0) > 0:
            critical_alerts.append(f"RÉPONSE: {camp['replied']} réponse(s) dans '{camp['name']}' — À TRAITER")

    for alert in critical_alerts:
        print(f"  ⚠ {alert}")

    # 5. Formater message Telegram
    message = format_telegram_message(campaigns, lists, costs, articles)

    if dry_run:
        print("\n[briefing] DRY-RUN — Message Telegram préparé:")
        print("─" * 60)
        print(message)
        print("─" * 60)
    else:
        print("[briefing] Envoi Telegram...")
        try:
            ok = send_telegram(tg_token, tg_chat, message)
            print(f"  → {'OK' if ok else 'ERREUR'}")
        except Exception as e:
            print(f"  ⚠ Erreur Telegram: {e}")

    # 6. Logger le coût du run briefing lui-même (appels API Emelia + Telegram = quasi nul)
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR))
        from scripts.cost_tracker import track
        track(
            action="briefing-daily",
            module="briefing",
            model="claude-haiku-4-5",   # modèle utilisé pour le résumé
            input_tok=600,
            output_tok=800,
            note=f"{len(campaigns)} campagnes · {len(lists)} listes"
        )
    except Exception as e:
        print(f"  ⚠ cost_tracker: {e}")

    # 7. Mise à jour dashboard.json
    update_dashboard(campaigns, lists, costs)
    print("[briefing] dashboard.json mis à jour")

    print(f"[briefing] Terminé {datetime.now(timezone.utc).isoformat()}")
    return {"campaigns": campaigns, "costs": costs, "alerts": critical_alerts}


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv or "-d" in sys.argv
    main(dry_run=dry)
