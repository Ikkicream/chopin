#!/usr/bin/env python3
"""Backfill scrappe_rejected depuis logs/mailnjoy_deletions.log + god_mode_logs."""
import json, sys, time
from pathlib import Path

BASE = Path("/home/autoblog/genesis")
sys.path.insert(0, str(BASE / "scripts"))
import duckdb

rejected = {}  # email -> (decision, reason, count)

# Source 1 : log JSONL des suppressions Mailnjoy (drain + imports)
log = BASE / "logs" / "mailnjoy_deletions.log"
n1 = 0
for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
    try:
        d = json.loads(line)
    except Exception:
        continue
    em = (d.get("email") or "").strip().lower()
    dec = d.get("decision") or "invalid"
    if not em or dec not in ("risky", "invalid", "drop"):
        continue
    reason = f"{d.get('status','')}/{d.get('category','')}"
    prev = rejected.get(em)
    rejected[em] = (dec, reason, (prev[2] + 1) if prev else 1)
    n1 += 1

# Source 2 : god_mode_logs cleanup_removed (inclut les drops validator local)
g = duckdb.connect(str(BASE / "data" / "god_mode.duckdb"), read_only=True)
rows = g.execute("""SELECT resource_id, payload FROM god_mode_logs
                    WHERE action='cleanup_removed'""").fetchall()
g.close()
n2 = 0
for em, payload in rows:
    em = (em or "").strip().lower()
    if not em or "@" not in em:
        continue
    try:
        p = json.loads(payload) if payload else {}
    except Exception:
        p = {}
    dec = p.get("decision") or "invalid"
    reason = p.get("reason") or ""
    prev = rejected.get(em)
    rejected[em] = (dec, reason, (prev[2] + 1) if prev else 1)
    n2 += 1

print(f"log mailnjoy: {n1} lignes, god_mode_logs: {n2} lignes, emails distincts: {len(rejected)}")

# Insert bulk (une connexion, retry sur lock)
import god_mode_backend as gm
gm._ensure_rejected_table()
for attempt in range(5):
    try:
        c = duckdb.connect(str(BASE / "data" / "god_mode.duckdb"))
        break
    except Exception as e:
        print("lock, retry...", e); time.sleep(2)
else:
    sys.exit("DB verrouillée, abandon")

existing = {r[0] for r in c.execute("SELECT email FROM scrappe_rejected").fetchall()}
ins = 0
for em, (dec, reason, cnt) in rejected.items():
    if em in existing:
        continue
    c.execute("""INSERT INTO scrappe_rejected (email, decision, reason, site_code, times_seen)
                 VALUES (?, ?, ?, 'lcr', ?)""", [em, dec, reason[:300], cnt])
    ins += 1
c.close()
print(f"insérés: {ins} (déjà présents: {len(rejected) - ins})")
