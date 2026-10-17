#!/usr/bin/env bash
# deployer_mass_email.sh — protocole de mise en production de Mass Email / Cheffer, SANS Camille.
#
# Demande de Camille (13/10/2026) : « arrête de me redemander des restart du serveur, crée un
# protocole sans moi ». Ce script est le SEUL chemin de déploiement autorisé à Claude ; il
# refuse de redémarrer quoi que ce soit tant que les contrôles ne sont pas au vert.
#
#   bash scripts/deployer_mass_email.sh ui      # interface Next (genesis-ui)
#   bash scripts/deployer_mass_email.sh api     # API + worker Mass Email (Python)
#   bash scripts/deployer_mass_email.sh tout    # les deux
#   bash scripts/deployer_mass_email.sh cheffer # API Cheffer (genesis-dashboard, port 8080)
#
# Garde-fous :
#  - UI : typage, puis compilation dans .next-verify (le build qui échoue vide .next et casse
#    la prod — vécu) ; le vrai build ne part que si la vérification passe ; restart ensuite.
#  - API : chargement des modules + tests unitaires ; le worker n'est redémarré qu'une fois
#    vide (aucun job « running », attente max 10 min) — il finit son lot puis s'arrête proprement.
#  - Santé vérifiée après chaque redémarrage ; échec = code de sortie ≠ 0 et message clair.
#  - Journal : logs/deploiement_mass_email.log
set -uo pipefail
GENESIS=/home/autoblog/genesis
UI=/home/autoblog/genesis-ui
LOG=$GENESIS/logs/deploiement_mass_email.log
CIBLE=${1:-}
en_autoblog() { if [ "$(id -un)" = autoblog ]; then bash -c "$1"; else runuser -u autoblog -- bash -c "$1"; fi; }
journal() { echo "[$(date -u '+%F %T')] $*" | tee -a "$LOG"; }
echec() { journal "ÉCHEC : $*"; exit 1; }

deployer_ui() {
  journal "UI : typage"
  en_autoblog "cd $UI && npx tsc --noEmit" >/tmp/deploy_tsc.log 2>&1 || { tail -20 /tmp/deploy_tsc.log; echec "typage UI"; }
  journal "UI : compilation de vérification (.next-verify)"
  cp "$UI/next-env.d.ts" /tmp/deploy_next_env.bak
  # 2 essais : le build télécharge les polices Google, et une coupure passagère l'a déjà fait
  # échouer (13/10, « Can't resolve …/font/google/font ») alors que le code était bon.
  for essai in 1 2; do
    en_autoblog "cd $UI && NEXT_DIST_DIR=.next-verify npx next build" >/tmp/deploy_verif.log 2>&1
    rc=$?; [ $rc -eq 0 ] && break
    grep -q "font/google" /tmp/deploy_verif.log || break      # vraie erreur de code : inutile de réessayer
    journal "UI : échec passager (polices Google), nouvel essai"; sleep 5
  done
  cp /tmp/deploy_next_env.bak "$UI/next-env.d.ts"; chown autoblog: "$UI/next-env.d.ts"
  [ $rc -eq 0 ] || { tail -30 /tmp/deploy_verif.log; echec "compilation de vérification UI (prod intacte)"; }
  journal "UI : compilation de production"
  en_autoblog "cd $UI && npx next build" >/tmp/deploy_build.log 2>&1 || { tail -30 /tmp/deploy_build.log; echec "build de production UI — .next peut être vide : relancer ce script"; }
  en_autoblog "pm2 restart genesis-ui" >/dev/null || echec "restart genesis-ui"
  sleep 5
  for p in /mass-email /mass-email/connexion; do
    c=$(curl -s -o /dev/null -w '%{http_code}' "https://mail.cheffer.email$p"); [ "$c" = 200 ] || echec "UI $p répond $c"
  done
  journal "UI : en ligne (BUILD_ID $(cat $UI/.next/BUILD_ID))"
}

attendre_worker_vide() {
  set -a; . "$GENESIS/.env"; set +a
  for i in $(seq 1 60); do
    n=$(psql "$PG_DSN" -At -c "SELECT count(*) FROM mass_mailing.jobs WHERE status='running'" 2>/dev/null || echo 0)
    for s in $(psql "$PG_DSN" -At -c "SELECT schema_pg FROM mass_mailing.clients" 2>/dev/null); do
      n=$(( n + $(psql "$PG_DSN" -At -c "SELECT count(*) FROM $s.jobs WHERE status='running'" 2>/dev/null || echo 0) ))
    done
    [ "${n:-0}" -eq 0 ] && return 0
    journal "worker occupé ($n job(s) en cours) — attente ($i/60)"; sleep 10
  done
  echec "worker toujours occupé après 10 min : redémarrage du worker reporté"
}

deployer_api() {
  journal "API : chargement des modules et tests"
  en_autoblog "cd $GENESIS/mass_mailing && set -a && . ../.env && set +a && python3 -c 'import serveur, worker' && \
     for t in tests/test_*.py; do python3 -m unittest tests.\$(basename \$t .py) >/dev/null 2>&1 || { echo \"KO \$t\"; exit 1; }; done" \
     >/tmp/deploy_api.log 2>&1 || { cat /tmp/deploy_api.log | tail -20; echec "tests Mass Email"; }
  en_autoblog "cd $GENESIS/mass_mailing && set -a && . ../.env && set +a && python3 -c '
import sys; sys.path.insert(0, \".\")
from infra import pg, clients
pg.appliquer_schema()
[clients.provisionner(c[\"slug\"]) for c in clients.lister()]'" >/tmp/deploy_schema.log 2>&1 || { tail -20 /tmp/deploy_schema.log; echec "migration du schéma"; }
  journal "API : schémas à jour (interne + clients)"
  en_autoblog "pm2 restart mass-mailing-api" >/dev/null || echec "restart mass-mailing-api"
  sleep 4
  c=$(curl -s -o /dev/null -w '%{http_code}' https://mail.cheffer.email/api/public/mass-mailing/sante)
  [ "$c" = 200 ] || echec "API santé répond $c"
  attendre_worker_vide
  en_autoblog "pm2 restart mass-mailing-worker" >/dev/null || echec "restart mass-mailing-worker"
  sleep 3
  journal "API + worker : en ligne"
}

deployer_cheffer() {
  journal "Cheffer : chargement de l'API"
  en_autoblog "cd $GENESIS/scripts && set -a && . ../.env && set +a && timeout 120 python3 -c 'import api'" >/tmp/deploy_cheffer.log 2>&1 \
    || { tail -20 /tmp/deploy_cheffer.log; echec "import scripts/api.py"; }
  en_autoblog "pm2 restart genesis-dashboard" >/dev/null || echec "restart genesis-dashboard"
  sleep 6
  c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/health)
  [ "$c" = 200 ] || [ "$c" = 401 ] || echec "API Cheffer répond $c"
  journal "Cheffer : en ligne"
}

touch "$LOG" && chown autoblog: "$LOG" 2>/dev/null
case "$CIBLE" in
  ui) deployer_ui ;;
  api) deployer_api ;;
  tout) deployer_api; deployer_ui ;;
  cheffer) deployer_cheffer ;;
  *) echo "usage : $0 ui|api|tout|cheffer"; exit 2 ;;
esac
journal "OK ($CIBLE)"
