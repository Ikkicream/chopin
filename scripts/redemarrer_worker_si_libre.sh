#!/usr/bin/env bash
# Redémarre `mass-mailing-worker` pour charger un correctif — SEULEMENT si c'est sans danger.
#
# Règles (consignes de production, 2026-11-23) :
#   - jamais entre 07:00 et 21:00 UTC (vagues d'envoi, dispatch Maildoso) ;
#   - jamais tant qu'un job est `running` dans une file (`mass_mailing.jobs`, `mmc_*.jobs`).
# Attend jusqu'à 2 h qu'aucun job ne tourne, puis redémarre et VÉRIFIE (nouveau PID,
# battement frais, /sante/worker en 200). N'agit jamais deux fois.
#
#   bash scripts/redemarrer_worker_si_libre.sh   (utilisateur autoblog)
set -uo pipefail
cd /home/autoblog/genesis || exit 1
journal() { echo "[$(date -u +%FT%TZ)] $1"; }

h=$((10#$(date -u +%H)))
if [ "$h" -ge 7 ] && [ "$h" -lt 21 ]; then
  journal "REFUS : il est ${h} h UTC, fenêtre 07-21 h interdite"; exit 1
fi

jobs_en_cours() {
  python3 - <<'EOF'
import sys
sys.path.insert(0, "mass_mailing")
from infra import pg
schemas = [r["nspname"] for r in pg.lignes(
    "SELECT nspname FROM pg_namespace WHERE nspname = 'mass_mailing' OR nspname LIKE 'mmc\\_%'")]
print(sum(int(pg.valeur(f"SELECT count(*) FROM {s}.jobs WHERE status = 'running'") or 0)
          for s in schemas if pg.valeur(f"SELECT to_regclass('{s}.jobs') IS NOT NULL")))
EOF
}

pid_worker() { pm2 pid mass-mailing-worker 2>/dev/null | tail -1; }

for essai in $(seq 1 24); do
  n="$(jobs_en_cours 2>&1)"
  if [ "$n" = "0" ]; then
    avant="$(pid_worker)"
    journal "aucun job en cours — redémarrage de mass-mailing-worker (PID $avant)"
    pm2 restart mass-mailing-worker >/dev/null
    sleep 20
    apres="$(pid_worker)"
    sante="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/api/public/mass-mailing/sante/worker)"
    # Le nouveau processus doit s'être annoncé ET avoir battu sous sa propre identité.
    annonce="$(grep -c "worker démarré ([^:]*:${apres})" /home/autoblog/.pm2/logs/mass-mailing-worker-out.log)"
    battu="$(python3 -c "import sys; sys.path.insert(0,'mass_mailing'); from infra import pg; print(pg.valeur(\"SELECT count(*) FROM mass_mailing.workers WHERE id LIKE %(i)s AND seen_at > now() - interval '2 minutes'\", {'i': '%:${apres}'}))")"
    journal "après : PID $apres, annonce=$annonce, battement=$battu, /sante/worker → $sante"
    if [ -n "$apres" ] && [ "$apres" != "$avant" ] && [ "$annonce" != "0" ] && [ "$battu" = "1" ] && [ "$sante" = "200" ]; then
      journal "OK : worker redémarré avec le correctif du battement"; exit 0
    fi
    journal "ÉCHEC : vérification après redémarrage non concluante — voir pm2 logs mass-mailing-worker"; exit 1
  fi
  journal "essai $essai : $n job(s) en cours, nouvelle tentative dans 5 min"
  sleep 300
done
journal "ABANDON : des jobs tournaient encore après 2 h — rien n'a été redémarré"
exit 1
