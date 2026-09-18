#!/usr/bin/env python3
"""traffic_strategist.py — Agent « Stratège Trafic » AUTONOME.

Boucle hebdo (cron) : OBSERVE (GSC) → MÉMOIRE (DuckDB) → VÉRIFIE les recos passées
→ DÉCIDE (DeepSeek : recos priorisées + DRAFTS title/meta) → NOTIFIE (Telegram).
Niveau d'autonomie : PROPOSE des patchs prêts (l'utilisateur valide en 1 clic via l'UI),
n'écrit jamais sur le site tout seul.

Sources :
  - GSC (Search Console API, compte de service google-indexing-key.json) — gratuit, temps réel.
  - (le trafic on-site réel via Ahrefs Web Analytics sera ajouté ensuite)

Mémoire : god_mode.duckdb → seo_traffic_snapshots + seo_traffic_recos.
Cron : `python3 scripts/traffic_strategist.py --site lcr`.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))
GOD_DB = BASE_DIR / "data" / "god_mode.duckdb"

# Propriété GSC par site (format Search Console)
GSC_PROPERTY = {
    "lcr": ["sc-domain:leclientroi.com", "https://leclientroi.com/"],
    "mkd": ["sc-domain:mkdgroupe.com", "https://mkdgroupe.com/"],
}

# Seuils opportunités (cf. spec agent_strategie_trafic.md §3)
PAGE2_MIN_POS, PAGE2_MAX_POS, PAGE2_MIN_IMPR = 5.0, 20.0, 30      # page 2 à pousser
CTR_LEAK_MAX_POS, CTR_LEAK_MIN_IMPR, CTR_LEAK_MAX_CTR = 5.0, 40, 3.0  # page 1 mais CTR cassé


# ── .env ──────────────────────────────────────────────────────────────────────
def _env(key: str) -> str:
    for line in (BASE_DIR / ".env").read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ── Mémoire (DuckDB) ────────────────────────────────────────────────────────────
def _conn():
    return duckdb.connect(str(GOD_DB))


def ensure_schema() -> None:
    c = _conn()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS seo_traffic_snapshots (
                id VARCHAR, site VARCHAR, captured_at TIMESTAMP,
                source VARCHAR, period_start DATE, period_end DATE, payload JSON
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS seo_traffic_recos (
                id VARCHAR, site VARCHAR, created_at TIMESTAMP,
                target VARCHAR, target_url VARCHAR, keyword VARCHAR, kind VARCHAR,
                action VARCHAR, draft_title VARCHAR, draft_meta VARCHAR, why VARCHAR,
                impact VARCHAR, effort VARCHAR, success_metric VARCHAR,
                baseline JSON, status VARCHAR, outcome JSON, verified_at TIMESTAMP
            )""")
    finally:
        c.close()


# ── OBSERVE : GSC via compte de service ─────────────────────────────────────────
def fetch_gsc(site: str, days: int = 28, lag: int = 3) -> dict:
    """Renvoie {ok, reason?, rows:[{keyword, clicks, impressions, ctr, position, top_url}],
    period_start, period_end}. GSC a ~3j de latence → on décale la fenêtre de `lag` jours."""
    sa = _env("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa and not Path(sa).is_absolute():
        sa = str(BASE_DIR / sa)
    if not sa or not Path(sa).exists():
        return {"ok": False, "reason": "GOOGLE_SERVICE_ACCOUNT_JSON absent"}
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests as gtr
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"google-auth manquant: {e}"}
    end = date.today() - timedelta(days=lag)
    start = end - timedelta(days=days)
    try:
        creds = service_account.Credentials.from_service_account_file(
            sa, scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
        creds.refresh(gtr.Request())
        tok = creds.token
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"auth GSC: {e}"}

    body = {"startDate": start.isoformat(), "endDate": end.isoformat(),
            "dimensions": ["query", "page"], "rowLimit": 1000}
    last_err = None
    for prop in GSC_PROPERTY.get(site, []):
        url = ("https://searchconsole.googleapis.com/webmasters/v3/sites/"
               + requests.utils.quote(prop, safe="") + "/searchAnalytics/query")
        try:
            r = requests.post(url, headers={"Authorization": f"Bearer {tok}",
                              "Content-Type": "application/json"}, json=body, timeout=40)
        except Exception as e:  # noqa: BLE001
            last_err = str(e); continue
        if r.status_code == 200:
            rows = []
            for it in r.json().get("rows", []):
                kw, page = it["keys"][0], it["keys"][1]
                rows.append({"keyword": kw, "top_url": page,
                             "clicks": it.get("clicks", 0), "impressions": it.get("impressions", 0),
                             "ctr": round(it.get("ctr", 0) * 100, 2), "position": round(it.get("position", 0), 1)})
            return {"ok": True, "rows": rows, "property": prop,
                    "period_start": start.isoformat(), "period_end": end.isoformat()}
        last_err = f"HTTP {r.status_code}: {r.text[:160]}"
    return {"ok": False, "reason": last_err or "aucune propriété GSC accessible"}


def store_snapshot(site: str, gsc: dict) -> None:
    ensure_schema()
    c = _conn()
    try:
        c.execute("INSERT INTO seo_traffic_snapshots VALUES (?,?,?,?,?,?,?)",
                  [str(uuid.uuid4()), site, datetime.now(timezone.utc), "gsc",
                   gsc.get("period_start"), gsc.get("period_end"),
                   json.dumps(gsc.get("rows", []), ensure_ascii=False)])
    finally:
        c.close()


def latest_snapshot_rows(site: str, before: datetime | None = None) -> list[dict]:
    c = _conn()
    try:
        q = ("SELECT payload FROM seo_traffic_snapshots WHERE site=? AND source='gsc' "
             + ("AND captured_at < ? " if before else "")
             + "ORDER BY captured_at DESC LIMIT 1")
        params = [site] + ([before] if before else [])
        row = c.execute(q, params).fetchone()
    finally:
        c.close()
    return json.loads(row[0]) if row and row[0] else []


# ── OPPORTUNITÉS ────────────────────────────────────────────────────────────────
def opportunities(rows: list[dict]) -> list[dict]:
    """Agrège par mot-clé (best line) et classe page-2 + CTR-leak, triées par impressions."""
    by_kw: dict[str, dict] = {}
    for r in rows:
        k = r["keyword"]
        if k not in by_kw or r["impressions"] > by_kw[k]["impressions"]:
            by_kw[k] = r
    opps = []
    for r in by_kw.values():
        pos, impr, ctr = r["position"], r["impressions"], r["ctr"]
        kind = None
        if PAGE2_MIN_POS <= pos <= PAGE2_MAX_POS and impr >= PAGE2_MIN_IMPR:
            kind = "page2_push"
        elif pos < CTR_LEAK_MAX_POS and impr >= CTR_LEAK_MIN_IMPR and ctr <= CTR_LEAK_MAX_CTR:
            kind = "ctr_leak"
        if kind:
            opps.append({**r, "kind": kind})
    opps.sort(key=lambda o: o["impressions"], reverse=True)
    return opps


# ── VÉRIFIE les recos passées ───────────────────────────────────────────────────
def verify_open_recos(site: str, current_rows: list[dict]) -> list[dict]:
    """Pour chaque reco 'open'/'done', re-mesure la position actuelle du mot-clé cible."""
    pos_now = {r["keyword"]: r["position"] for r in current_rows}
    ensure_schema()
    c = _conn()
    verified = []
    try:
        recos = c.execute(
            "SELECT id, keyword, baseline FROM seo_traffic_recos "
            "WHERE site=? AND status IN ('open','done')", [site]).fetchall()
        for rid, kw, baseline in recos:
            base = json.loads(baseline) if baseline else {}
            base_pos = base.get("position")
            cur = pos_now.get(kw)
            if cur is None:
                status, note = "failed", "mot-clé sorti du top 100"
            elif base_pos is not None and cur < base_pos - 0.5:
                status, note = "validated", f"position {base_pos}→{cur}"
            elif base_pos is not None and cur > base_pos + 1.0:
                status, note = "failed", f"position {base_pos}→{cur} (recul)"
            else:
                status, note = "open", f"position stable ({cur})"  # on laisse ouvert
            c.execute("UPDATE seo_traffic_recos SET status=?, outcome=?, verified_at=? WHERE id=?",
                      [status, json.dumps({"position_now": cur, "note": note}), datetime.now(timezone.utc), rid])
            verified.append({"keyword": kw, "status": status, "note": note})
    finally:
        c.close()
    return verified


# ── DÉCIDE (DeepSeek) : recos + drafts title/meta ───────────────────────────────
SYSTEM = (
    "Tu es un stratège SEO/acquisition pour des sites B2B francophones. On te donne des "
    "opportunités Search Console réelles (mots-clés où le site est déjà vu par Google mais "
    "mal cliqué). Tu rends des recommandations CONCRÈTES et, pour chaque page, un title et "
    "une meta description PRÊTS À POSER. Title ≤ 60 caractères, meta ≤ 155, en français, "
    "accrocheurs, avec le mot-clé cible. Réponds UNIQUEMENT en JSON valide."
)


def decide(site: str, opps: list[dict], verified: list[dict]) -> list[dict]:
    from llm_call import call_llm_json
    top = opps[:8]
    prompt = (
        "OPPORTUNITÉS (mot-clé · position · impressions · CTR% · page) :\n"
        + "\n".join(f"- {o['keyword']} · pos {o['position']} · {o['impressions']} impr · "
                    f"CTR {o['ctr']}% · {o['top_url']} · [{o['kind']}]" for o in top)
        + "\n\nRECOS PASSÉES VÉRIFIÉES :\n"
        + ("\n".join(f"- {v['keyword']} : {v['status']} ({v['note']})" for v in verified) or "- (aucune)")
        + "\n\nRends un JSON {\"recommandations\":[{"
        "\"keyword\":\"\",\"target_url\":\"\",\"kind\":\"page2_push|ctr_leak\","
        "\"action\":\"instruction concrète\",\"draft_title\":\"\",\"draft_meta\":\"\","
        "\"why\":\"raisonnement chiffré\",\"impact\":\"+X clics/mois\","
        "\"effort\":\"faible|moyen|élevé\",\"success_metric\":\"métrique+seuil+horizon\"}]} "
        "trié par impact décroissant, max 6 items."
    )
    try:
        out = call_llm_json(prompt, system=SYSTEM, max_tokens=3000,
                            module="traffic-strategist", action="decide", site=site)
    except Exception as e:  # noqa: BLE001
        print(f"  [decide] LLM KO: {e}")
        return []
    return out.get("recommandations", []) if isinstance(out, dict) else []


def store_recos(site: str, recos: list[dict], opps: list[dict]) -> int:
    base_by_kw = {o["keyword"]: o for o in opps}
    ensure_schema()
    c = _conn()
    n = 0
    try:
        for r in recos:
            kw = r.get("keyword", "")
            # remplace (supersede) les recos open précédentes du même mot-clé -> pas de doublons
            c.execute("UPDATE seo_traffic_recos SET status='superseded' WHERE site=? AND keyword=? AND status='open'", [site, kw])
            base = base_by_kw.get(kw, {})
            c.execute("INSERT INTO seo_traffic_recos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      [str(uuid.uuid4()), site, datetime.now(timezone.utc),
                       kw, r.get("target_url", ""), kw, r.get("kind", ""),
                       r.get("action", ""), r.get("draft_title", ""), r.get("draft_meta", ""),
                       r.get("why", ""), r.get("impact", ""), r.get("effort", ""),
                       r.get("success_metric", ""), json.dumps(base, ensure_ascii=False),
                       "open", None, None])
            n += 1
    finally:
        c.close()
    return n


# ── RUN ─────────────────────────────────────────────────────────────────────────
def run(site: str, seed_rows: list[dict] | None = None) -> dict:
    ensure_schema()
    if seed_rows is not None:
        rows = seed_rows
        gsc = {"ok": True, "rows": rows, "period_start": None, "period_end": None, "property": "seed"}
        print(f"[seed] {len(rows)} lignes GSC fournies")
    else:
        gsc = fetch_gsc(site)
        if not gsc.get("ok"):
            print(f"[{site}] GSC indisponible: {gsc.get('reason')}")
            # on tente quand même la vérif sur le dernier snapshot connu
            rows = latest_snapshot_rows(site)
            if not rows:
                return {"site": site, "error": gsc.get("reason"), "recos": 0}
        else:
            rows = gsc["rows"]
    fresh = seed_rows is not None or gsc.get("ok")
    verified = verify_open_recos(site, rows)
    opps = opportunities(rows)
    n = 0
    if fresh:
        store_snapshot(site, gsc)
        recos = decide(site, opps, verified)
        n = store_recos(site, recos, opps)
    else:
        print(f"[{site}] données GSC non fraîches → vérif seule, pas de nouvelles recos "
              "(active l'API Search Console pour des recos hebdo).")
    summary = {"site": site, "fresh": fresh, "gsc_rows": len(rows),
               "opportunities": len(opps), "new_recos": n, "verified": verified}
    try:
        from autoscrape_backend import notify_telegram
        val = sum(1 for v in verified if v["status"] == "validated")
        notify_telegram(
            f"📈 *Stratège Trafic {site.upper()}* — {len(opps)} opportunités GSC, "
            f"{n} recos+drafts générées, {val} reco(s) validée(s) ce cycle.")
    except Exception:
        pass
    return summary


# Propriété GA4 par site (Data API) — source des VISITES réelles
GA4_PROPERTY = {"lcr": "485325567"}  # mkd : à renseigner


def fetch_ga4_daily(site: str, days: int = 30) -> dict:
    """Visites par jour via GA4 Data API (compte de service, scope analytics.readonly).
    Renvoie {ok, reason?, daily:[{date,sessions,visitors,pageviews}], totals}."""
    prop = GA4_PROPERTY.get(site)
    if not prop:
        return {"ok": False, "reason": "pas de propriété GA4 configurée"}
    sa = _env("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa and not Path(sa).is_absolute():
        sa = str(BASE_DIR / sa)
    if not sa or not Path(sa).exists():
        return {"ok": False, "reason": "GOOGLE_SERVICE_ACCOUNT_JSON absent"}
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests as gtr
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"google-auth manquant: {e}"}
    try:
        creds = service_account.Credentials.from_service_account_file(
            sa, scopes=["https://www.googleapis.com/auth/analytics.readonly"])
        creds.refresh(gtr.Request())
        tok = creds.token
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"auth GA4: {e}"}
    body = {
        "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "yesterday"}],
        "dimensions": [{"name": "date"}],
        "metrics": [{"name": "sessions"}, {"name": "activeUsers"}, {"name": "screenPageViews"}],
        "orderBys": [{"dimension": {"dimensionName": "date"}}],
    }
    try:
        r = requests.post(
            f"https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json=body, timeout=40)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": str(e)}
    if r.status_code != 200:
        return {"ok": False, "reason": f"HTTP {r.status_code}: {r.text[:160]}"}
    daily = []
    for row in r.json().get("rows", []):
        dv = row["dimensionValues"][0]["value"]  # YYYYMMDD
        m = row["metricValues"]
        daily.append({"date": f"{dv[:4]}-{dv[4:6]}-{dv[6:]}",
                      "sessions": int(m[0]["value"]), "visitors": int(m[1]["value"]),
                      "pageviews": int(m[2]["value"])})
    return {"ok": True, "daily": daily, "totals": {
        "sessions": sum(d["sessions"] for d in daily),
        "visitors": sum(d["visitors"] for d in daily),
        "pageviews": sum(d["pageviews"] for d in daily)}}


def fetch_ga4_channels(site: str, days: int = 30) -> dict:
    """Visites par canal (sessionDefaultChannelGroup) sur GA4 — pour la répartition par source."""
    prop = GA4_PROPERTY.get(site)
    if not prop:
        return {"ok": False}
    sa = _env("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa and not Path(sa).is_absolute():
        sa = str(BASE_DIR / sa)
    if not sa or not Path(sa).exists():
        return {"ok": False}
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests as gtr
        creds = service_account.Credentials.from_service_account_file(
            sa, scopes=["https://www.googleapis.com/auth/analytics.readonly"])
        creds.refresh(gtr.Request())
    except Exception:
        return {"ok": False}
    body = {"dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "yesterday"}],
            "dimensions": [{"name": "sessionDefaultChannelGroup"}],
            "metrics": [{"name": "sessions"}],
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}]}
    try:
        r = requests.post(
            f"https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport",
            headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
            json=body, timeout=40)
    except Exception:
        return {"ok": False}
    if r.status_code != 200:
        return {"ok": False}
    chans = [{"channel": row["dimensionValues"][0]["value"], "sessions": int(row["metricValues"][0]["value"])}
             for row in r.json().get("rows", [])]
    return {"ok": True, "channels": chans}


def _ahrefs_cache(site: str) -> dict:
    f = BASE_DIR / "memory" / "seo" / f"{site}-ahrefs-latest.json"
    try:
        return json.loads(f.read_text())
    except Exception:
        return {}


def dashboard(site: str) -> dict:
    """Agrège les KPI SEO + recos pour la page /seo (KPI dashboard)."""
    ensure_schema()
    rows = latest_snapshot_rows(site)
    impr = sum(r["impressions"] for r in rows)
    clicks = sum(r["clicks"] for r in rows)
    ctr = round(clicks / impr * 100, 2) if impr else 0
    avg_pos = round(sum(r["position"] * r["impressions"] for r in rows) / impr, 1) if impr else None
    top_kw = sorted(rows, key=lambda r: r["impressions"], reverse=True)[:10]
    c = _conn()
    try:
        recos = c.execute(
            "SELECT keyword,target_url,kind,action,draft_title,draft_meta,impact,effort,status "
            "FROM seo_traffic_recos WHERE site=? AND status IN ('open','done') "
            "ORDER BY created_at DESC LIMIT 12", [site]).fetchall()
        snap = c.execute(
            "SELECT period_start, period_end FROM seo_traffic_snapshots "
            "WHERE site=? ORDER BY captured_at DESC LIMIT 1", [site]).fetchone()
        val = c.execute("SELECT COUNT(*) FROM seo_traffic_recos WHERE site=? AND status='validated'", [site]).fetchone()[0]
    finally:
        c.close()
    ah = _ahrefs_cache(site)
    ga = fetch_ga4_daily(site)
    gac = fetch_ga4_channels(site)
    chans = gac.get("channels", []) if gac.get("ok") else []
    tot_ch = sum(c["sessions"] for c in chans) or 0
    direct = next((c["sessions"] for c in chans if c["channel"] == "Direct"), 0)
    return {
        "ga4": {"has_data": bool(ga.get("ok") and ga.get("daily")), "reason": ga.get("reason"),
                "daily": ga.get("daily", []), "totals": ga.get("totals", {}),
                "by_channel": chans,
                "direct_pct": round(direct / tot_ch * 100) if tot_ch else None},
        "gsc": {"clicks": clicks, "impressions": impr, "ctr": ctr, "avg_position": avg_pos,
                "keywords": len(rows), "has_data": bool(rows),
                "period_start": str(snap[0]) if snap and snap[0] else None,
                "period_end": str(snap[1]) if snap and snap[1] else None},
        "ahrefs": {"domain_rating": ah.get("domain_rating"), "ahrefs_rank": ah.get("ahrefs_rank"),
                   "org_keywords": ah.get("org_keywords"), "org_traffic": ah.get("org_traffic")},
        "opportunities": sum(1 for r in recos if r[8] == "open"),
        "validated": val,
        "recos": [{"keyword": r[0], "target_url": r[1], "kind": r[2], "action": r[3],
                   "draft_title": r[4], "draft_meta": r[5], "impact": r[6], "effort": r[7],
                   "status": r[8]} for r in recos],
        "top_keywords": [{"keyword": r["keyword"], "position": r["position"],
                          "impressions": r["impressions"], "clicks": r["clicks"],
                          "ctr": r["ctr"], "top_url": r["top_url"]} for r in top_kw],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="lcr")
    args = ap.parse_args()
    print(json.dumps(run(args.site), ensure_ascii=False, default=str)[:600])
    return 0


if __name__ == "__main__":
    sys.exit(main())
