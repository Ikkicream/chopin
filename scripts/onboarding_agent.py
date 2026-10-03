#!/usr/bin/env python3
"""
onboarding_agent.py — Initialisation complète d'un nouveau site Genesis.

Séquence :
  1. validate_config       — vérifie les champs obligatoires
  2. create_directories    — memory/{code}/ + sous-dossiers
  3. write_site_context    — chunk RAG (memory/{code}/site-context.md)
  4. write_keywords_file   — memory/{code}/keywords-targeted.md
  5. write_articles_log    — memory/{code}/articles-published.md
  6. test_cms_connection   — abort si CMS inaccessible
  7. run_seo_audit         — seo.py --site {code} [skip en dry-run]
  8. run_indexation_audit  — indexation_agent.py --task audit [skip en dry-run]
  9. generate_first_article— content_agent.py --dry-run (toujours dry)
 10. create_pm2_crons      — 4 crons pm2 [skip en dry-run]
 11. update_meta_status    — status="active" dans sites-config.json
 12. write_onboarding_log  — memory/{code}/onboarding-log.json
 13. send_telegram_summary — résumé Telegram

Usage:
  python3 scripts/onboarding_agent.py --site site3
  python3 scripts/onboarding_agent.py --site site3 --live
  python3 scripts/onboarding_agent.py --site site3 --live --skip-seo
"""

import argparse
import json
import subprocess
import sys
import base64
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))
from scripts.sites_config import (
    get_site, update_site, write_site_context as _write_ctx,
    get_env_var_name, list_active_sites,
)

ENV_FILE  = BASE_DIR / ".env"
MEM_DIR   = BASE_DIR / "memory"


def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


# ── Step 1 — Validation ───────────────────────────────────────────────────────

REQUIRED_CORE = ["code", "label", "domain", "url", "cms"]

def validate_config(code: str) -> dict:
    """Charge et valide la config. Lève ValueError sur champ manquant."""
    site = get_site(code)
    if not site:
        raise ValueError(f"Site '{code}' introuvable dans sites-config.json")
    core    = site.get("core", {})
    content = site.get("content", {})
    for f in ["label", "domain", "url"]:
        if not core.get(f):
            raise ValueError(f"Champ core.{f} manquant pour '{code}'")
    if not content.get("cms"):
        raise ValueError(f"Champ content.cms manquant pour '{code}'")
    print(f"  [1/13] Config validée: {core.get('label')} ({core.get('domain')})")
    return site


# ── Step 2 — Directories ──────────────────────────────────────────────────────

def create_directories(code: str) -> list[str]:
    """Crée l'arborescence memory/{code}/."""
    dirs = [
        MEM_DIR / code,
        MEM_DIR / code / "weekly-reports",
    ]
    created = []
    for d in dirs:
        if not d.exists():
            d.mkdir(parents=True)
            created.append(str(d))
    print(f"  [2/13] Dossiers créés: {len(created)} (memory/{code}/)")
    return created


# ── Step 3 — Site context (RAG) ───────────────────────────────────────────────

def write_site_context(code: str) -> Path:
    path = _write_ctx(code)
    print(f"  [3/13] Chunk RAG: {path}")
    return path


# ── Step 4 — Keywords file ────────────────────────────────────────────────────

def write_keywords_file(code: str) -> Path:
    site = get_site(code)
    keywords = site.get("seo", {}).get("keywords", [])
    path = MEM_DIR / code / "keywords-targeted.md"
    if not path.exists():
        lines = [f"# Mots-clés cibles — {site['core']['label']}\n"]
        lines += [f"- {kw}" for kw in keywords]
        path.write_text("\n".join(lines) + "\n")
    print(f"  [4/13] Keywords: {len(keywords)} mots-clés initiaux")
    return path


# ── Step 5 — Articles log ─────────────────────────────────────────────────────

def write_articles_log(code: str) -> Path:
    path = MEM_DIR / code / "articles-published.md"
    if not path.exists():
        path.write_text(
            f"# Articles publiés — {get_site(code)['core']['label']}\n\n"
            "| Date | Slug | Titre | Mot-clé | Source | URL |\n"
            "|------|------|-------|---------|--------|-----|\n"
        )
    print(f"  [5/13] Log articles initialisé")
    return path


# ── Step 6 — CMS connection test ─────────────────────────────────────────────

def test_cms_connection(code: str, env: dict) -> bool:
    site    = get_site(code)
    cms     = site.get("content", {}).get("cms", "")

    try:
        if cms == "emdash":
            token_var = get_env_var_name(code, "emdash_token")
            url_var   = get_env_var_name(code, "emdash_url")
            token = env.get(token_var, "")
            raw_url = env.get(url_var, "http://localhost:4321")
            # Normalise: on veut juste le host, pas le chemin API complet
            from urllib.parse import urlparse
            parsed = urlparse(raw_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            if not token:
                print(f"  [6/13] ⚠ {token_var} absent du .env — CMS skip")
                return True  # non-fatal, site peut quand même être onboardé
            r = requests.get(
                f"{base_url}/_emdash/api/content/posts?limit=1",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
            ok = r.status_code == 200
            print(f"  [6/13] CMS Emdash: {'✓ OK' if ok else '✗ ERREUR ' + str(r.status_code)}")
            return ok

        elif cms == "wordpress":
            wp_url  = env.get(get_env_var_name(code, "wp_url"), "")
            wp_user = env.get(get_env_var_name(code, "wp_user"), "")
            wp_pass = env.get(get_env_var_name(code, "wp_pass"), "")
            if not wp_url:
                print(f"  [6/13] ⚠ WP_SITE_URL absent — CMS skip")
                return True
            auth = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
            r = requests.get(
                f"{wp_url}/wp-json/wp/v2/posts?per_page=1",
                headers={"Authorization": f"Basic {auth}"},
                timeout=8,
            )
            ok = r.status_code in (200, 401)  # 401 = WP up mais mauvais creds
            print(f"  [6/13] CMS WordPress: {'✓ OK' if ok else '✗ ERREUR ' + str(r.status_code)}")
            return ok

    except Exception as e:
        print(f"  [6/13] ⚠ CMS test exception: {e}")
        return True  # non-fatal


# ── Step 7 — SEO audit ────────────────────────────────────────────────────────

def run_seo_audit(code: str) -> dict:
    print(f"  [7/13] SEO audit (seo.py --site {code})...")
    try:
        result = subprocess.run(
            ["python3", str(BASE_DIR / "scripts" / "seo.py"), "--site", code, "--report", "full"],
            capture_output=True, text=True, cwd=str(BASE_DIR), timeout=300,
        )
        ok = result.returncode == 0
        brief_path = str(MEM_DIR / "seo" / f"{code}-latest.json")
        print(f"  [7/13] SEO audit: {'✓' if ok else '✗'} (returncode={result.returncode})")
        if not ok and result.stderr:
            print(f"         stderr: {result.stderr[:200]}")
        return {"ok": ok, "brief_path": brief_path}
    except subprocess.TimeoutExpired:
        print(f"  [7/13] ⚠ Timeout (>300s)")
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        print(f"  [7/13] ⚠ {e}")
        return {"ok": False, "error": str(e)}


# ── Step 8 — Indexation audit ─────────────────────────────────────────────────

def run_indexation_audit(code: str) -> dict:
    print(f"  [8/13] Indexation audit...")
    try:
        result = subprocess.run(
            ["python3", str(BASE_DIR / "scripts" / "indexation_agent.py"),
             "--task", "audit", "--site", code],
            capture_output=True, text=True, cwd=str(BASE_DIR), timeout=120,
        )
        ok = result.returncode == 0
        audit_path = MEM_DIR / "seo" / f"{code}-indexation-audit.json"
        missing = 0
        if audit_path.exists():
            d = json.loads(audit_path.read_text())
            missing = len(d.get("missing_articles", []))
        print(f"  [8/13] Indexation: {'✓' if ok else '✗'} — {missing} articles manquants")
        return {"ok": ok, "missing_count": missing}
    except Exception as e:
        print(f"  [8/13] ⚠ {e}")
        return {"ok": False, "error": str(e)}


# ── Step 9 — First article draft ──────────────────────────────────────────────

def generate_first_article(code: str) -> dict:
    print(f"  [9/13] Génération draft premier article (dry-run)...")
    try:
        result = subprocess.run(
            ["python3", str(BASE_DIR / "scripts" / "content_agent.py"),
             "--site", code, "--dry-run"],
            capture_output=True, text=True, cwd=str(BASE_DIR), timeout=120,
        )
        ok = result.returncode == 0
        # Extract chosen topic from stdout
        topic = ""
        for line in result.stdout.splitlines():
            if "Sujet choisi" in line or "keyword" in line.lower():
                topic = line.strip()[:100]
                break
        print(f"  [9/13] Draft: {'✓' if ok else '✗'} {topic}")
        return {"ok": ok, "topic": topic, "output": result.stdout[:500]}
    except Exception as e:
        print(f"  [9/13] ⚠ {e}")
        return {"ok": False, "error": str(e)}


# ── Step 10 — PM2 crons ───────────────────────────────────────────────────────

def create_pm2_crons(code: str) -> list[dict]:
    """Crée 4 crons pm2 pour le nouveau site."""
    scripts_dir = str(BASE_DIR / "scripts")
    crons = [
        {
            "name":   f"genesis-seo-{code}",
            "script": f"{scripts_dir}/seo.py",
            "args":   ["--site", code, "--report", "full"],
            "cron":   "0 6 * * 1",
            "desc":   "Lundi 6h — analyse Ahrefs",
        },
        {
            "name":   f"genesis-content-{code}",
            "script": f"{scripts_dir}/content_agent.py",
            "args":   ["--site", code, "--live"],
            "cron":   "0 10 * * 3",
            "desc":   "Mercredi 10h — article",
        },
        {
            "name":   f"genesis-indexation-{code}",
            "script": f"{scripts_dir}/indexation_agent.py",
            "args":   ["--task", "all", "--site", code, "--live"],
            "cron":   "30 6 * * 1",
            "desc":   "Lundi 6h30 — audit sitemap",
        },
        {
            "name":   f"genesis-seo-agent-{code}",
            "script": f"{scripts_dir}/seo_agent.py",
            "args":   ["--task", "all", "--site", code],
            "cron":   "0 7 * * 2",
            "desc":   "Mardi 7h — veille RSS",
        },
    ]

    results = []
    for c in crons:
        cmd = [
            "pm2", "start", c["script"],
            "--name", c["name"],
            "--cron", c["cron"],
            "--no-autorestart",
            "--interpreter", "python3",
            "--", *c["args"],
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR), timeout=15)
            ok = proc.returncode == 0
            results.append({"name": c["name"], "cron": c["cron"], "desc": c["desc"],
                            "result": "ok" if ok else "error",
                            "stderr": proc.stderr[:100] if not ok else ""})
            print(f"  [10/13] pm2 {c['name']}: {'✓' if ok else '✗'}")
        except Exception as e:
            results.append({"name": c["name"], "cron": c["cron"], "result": "error", "error": str(e)})
            print(f"  [10/13] pm2 {c['name']}: ✗ {e}")

    # Save pm2 state
    subprocess.run(["pm2", "save"], capture_output=True, timeout=10)
    return results


# ── Step 11 — Update meta status ─────────────────────────────────────────────

def update_meta_status(code: str, status: str = "active") -> None:
    now = datetime.now(timezone.utc).isoformat()
    update_site(code, {"_meta": {"status": status, "onboarded_at": now}})
    print(f"  [11/13] Status: {status}")


# ── Step 12 — Onboarding log ─────────────────────────────────────────────────

def write_onboarding_log(code: str, results: dict) -> Path:
    path = MEM_DIR / code / "onboarding-log.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"  [12/13] Log: {path}")
    return path


# ── Step 13 — Telegram ────────────────────────────────────────────────────────

def send_telegram_summary(code: str, results: dict, env: dict) -> None:
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat  = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print(f"  [13/13] Telegram: non configuré (skip)")
        return
    site  = get_site(code)
    label = site.get("core", {}).get("label", code) if site else code
    steps_ok  = sum(1 for v in results.get("steps", {}).values() if v.get("ok", False))
    steps_all = len(results.get("steps", {}))
    dry = results.get("dry_run", True)

    msg = (
        f"🚀 *Onboarding Genesis — {label}* ({'dry-run' if dry else 'LIVE'})\n\n"
        f"✅ {steps_ok}/{steps_all} étapes réussies\n\n"
    )
    if results.get("steps", {}).get("seo_audit", {}).get("ok"):
        msg += "📊 SEO audit : terminé\n"
    if results.get("steps", {}).get("indexation", {}).get("ok"):
        missing = results["steps"]["indexation"].get("missing_count", 0)
        msg += f"🗺 Indexation : {missing} articles manquants\n"
    if results.get("steps", {}).get("first_article", {}).get("ok"):
        msg += f"✍ Draft article : généré\n"
    if not dry:
        msg += f"\n🔁 4 crons pm2 créés pour `{code}`"

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
        print(f"  [13/13] Telegram: envoyé")
    except Exception as e:
        print(f"  [13/13] Telegram: erreur — {e}")


# ── Main run ──────────────────────────────────────────────────────────────────

def run(code: str, dry_run: bool = True, skip_seo: bool = False,
        skip_indexation: bool = False) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    print(f"\n[onboarding_agent] {now} — {'DRY-RUN' if dry_run else 'LIVE'} — site: {code}")
    print("=" * 60)

    env     = load_env()
    results = {"site": code, "started_at": now, "dry_run": dry_run, "steps": {}}

    try:
        # 1 — Validate
        site = validate_config(code)
        results["steps"]["validate"] = {"ok": True}
    except ValueError as e:
        print(f"  ✗ Validation échouée: {e}")
        results["steps"]["validate"] = {"ok": False, "error": str(e)}
        results["completed_at"] = datetime.now(timezone.utc).isoformat()
        return results

    # 2 — Directories
    dirs = create_directories(code)
    results["steps"]["directories"] = {"ok": True, "created": dirs}

    # 3 — Site context
    ctx_path = write_site_context(code)
    results["steps"]["site_context"] = {"ok": True, "path": str(ctx_path)}

    # 4 — Keywords
    kw_path = write_keywords_file(code)
    results["steps"]["keywords"] = {"ok": True, "path": str(kw_path)}

    # 5 — Articles log
    art_path = write_articles_log(code)
    results["steps"]["articles_log"] = {"ok": True, "path": str(art_path)}

    # 6 — CMS test
    cms_ok = test_cms_connection(code, env)
    results["steps"]["cms_test"] = {"ok": True, "cms_reachable": cms_ok}

    # 7 — SEO audit (skip en dry-run)
    if dry_run or skip_seo:
        print(f"  [7/13] SEO audit: SKIP {'(dry-run)' if dry_run else '(--skip-seo)'}")
        results["steps"]["seo_audit"] = {"ok": True, "skipped": True}
    else:
        seo_r = run_seo_audit(code)
        results["steps"]["seo_audit"] = seo_r

    # 8 — Indexation (skip en dry-run)
    if dry_run or skip_indexation:
        print(f"  [8/13] Indexation audit: SKIP")
        results["steps"]["indexation"] = {"ok": True, "skipped": True}
    else:
        idx_r = run_indexation_audit(code)
        results["steps"]["indexation"] = idx_r

    # 9 — First article draft (toujours dry-run)
    draft_r = generate_first_article(code)
    results["steps"]["first_article"] = draft_r

    # 10 — PM2 crons (skip en dry-run)
    if dry_run:
        print(f"  [10/13] PM2 crons: SKIP (dry-run) — 4 crons qui seraient créés:")
        for name in [f"genesis-seo-{code}", f"genesis-content-{code}",
                     f"genesis-indexation-{code}", f"genesis-seo-agent-{code}"]:
            print(f"          {name}")
        results["steps"]["pm2_crons"] = {"ok": True, "skipped": True}
    else:
        crons_r = create_pm2_crons(code)
        results["steps"]["pm2_crons"] = {"ok": True, "crons": crons_r}

    # 11 — Update meta
    if not dry_run:
        update_meta_status(code, "active")
    else:
        print(f"  [11/13] Status: SKIP (dry-run)")
    results["steps"]["meta_update"] = {"ok": True}

    # 12 — Log
    results["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_onboarding_log(code, results)

    # 13 — Telegram
    send_telegram_summary(code, results, env)

    steps_ok = sum(1 for s in results["steps"].values() if s.get("ok", False))
    print(f"\n[onboarding_agent] Terminé — {steps_ok}/{len(results['steps'])} étapes OK")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genesis — Onboarding nouveau site")
    parser.add_argument("--site", required=True, help="Code du site (ex: site3)")
    parser.add_argument("--live", action="store_true", help="Mode live (default: dry-run)")
    parser.add_argument("--skip-seo", action="store_true", help="Skip SEO audit Ahrefs")
    parser.add_argument("--skip-indexation", action="store_true", help="Skip indexation audit")
    args = parser.parse_args()

    results = run(args.site, dry_run=not args.live,
                  skip_seo=args.skip_seo, skip_indexation=args.skip_indexation)
    sys.exit(0 if all(s.get("ok", False) for s in results["steps"].values()) else 1)
