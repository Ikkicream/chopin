"""Drain Mailnjoy en boucle — appelle check_pending_queue toutes les 5 min.

Démarré par pm2 (process `genesis-mailnjoy-drain`). Garde-fous internes :
- Skip si Mailnjoy non configuré
- Skip si crédit < 100 (check_pending_queue gère lui-même)
- Log JSON sur stdout pour pm2 logs
"""
import json
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, "/home/autoblog/genesis/scripts")
from mailnjoy_check import check_pending_queue, is_configured

INTERVAL = 300  # 5 minutes


def main() -> None:
    print(f"[mailnjoy-drain] started, interval={INTERVAL}s", flush=True)
    while True:
        try:
            if not is_configured():
                print(f"[{datetime.now(timezone.utc).isoformat()}] not_configured, skip", flush=True)
            else:
                res = check_pending_queue()
                # log compact
                # `chronic_remaining` et `retired_chronic` DOIVENT figurer ici : 397 lignes
                # se sont accumulées hors de la file entre mai et août 2026 précisément
                # parce qu'aucun log ne les mentionnait. Les taire, c'est reproduire le bug.
                summary = {k: res.get(k) for k in
                           ("total", "valid", "risky", "invalid", "errored",
                            "retired_chronic", "retired_pool_copies", "chronic_remaining",
                            "credit_left", "error") if res.get(k) is not None}
                print(f"[{datetime.now(timezone.utc).isoformat()}] {json.dumps(summary)}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{datetime.now(timezone.utc).isoformat()}] ERR {e}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
