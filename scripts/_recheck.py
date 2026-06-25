import requests, duckdb, time, sys, json
sys.path.insert(0, "/home/autoblog/genesis/scripts")
from sweego_backend import _headers, SWEEGO_URL

h = _headers(); uuid = "bd0d7413-26ff-414c-9e31-232382ff1512"
r = requests.get(SWEEGO_URL + "/clients/" + uuid + "/webhooks", headers=h, timeout=20)
for wh in r.json():
    if wh.get("name") == "genesis-prm":
        print("genesis-prm | enabled:", wh.get("enabled"),
              "| success:", wh.get("success_count"), "| fail:", wh.get("fail_count"),
              "| last_update:", wh.get("last_update_dt"))

print("--- sweego_events (Genesis) ---")
c = None
for _ in range(12):
    try: c = duckdb.connect("/home/autoblog/genesis/data/god_mode.duckdb", read_only=True); break
    except Exception as e:
        if "lock" in str(e).lower(): time.sleep(3); continue
        raise
if c:
    tbls = [t[0] for t in c.execute("SHOW TABLES").fetchall()]
    if "sweego_events" in tbls:
        rows = c.execute("SELECT received_at,event_type,email,raw_payload FROM sweego_events ORDER BY received_at DESC LIMIT 6").fetchall()
        print("nb:", len(rows))
        for x in rows:
            print(" ", x[0], "|", repr(x[1]), "|", x[2], "|", (x[3] or "")[:300])
    else:
        print("table sweego_events absente — toujours 0 event reçu")
    c.close()
