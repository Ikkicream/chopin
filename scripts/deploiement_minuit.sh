#!/usr/bin/env bash
# Redemarrage de l interface Cheffer, programme par Camille pour minuit (heure de Paris).
#
# Met en ligne trois chantiers deja compiles le 21/09 :
#   - messagerie Onoff : marque a l ecoute, pastille de la sidebar, onglet Archives
#   - alerte credits Serper deplacee du tableau de bord vers la barre superadmin
#   - sidebar : une seule entree surlignee, la plus precise
#
# Le build est deja fait : ce script ne compile rien, il bascule. Il verifie ensuite que
# l interface repond vraiment — un `pm2 restart` qui rend la main ne prouve pas que la
# page se sert.
set -uo pipefail

# Ce script est lance par `at`, qui herite de l environnement du moment ou le job a ete
# depose — ici celui de root. Sans HOME, `pm2` cherche son demon dans /root/.pm2, ne
# trouve rien, et le deploiement echoue en silence a minuit. On ne suppose donc aucun
# environnement : on le pose.
export HOME=/home/autoblog
export USER=autoblog
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

JOURNAL=/home/autoblog/genesis/logs/deploiement_ui.log
exec >> "$JOURNAL" 2>&1

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — redemarrage genesis-ui ==="
echo "build en place : $(cat /home/autoblog/genesis-ui/.next/BUILD_ID 2>/dev/null || echo inconnu)"

pm2 restart genesis-ui --update-env
sleep 15

etat=$(pm2 jlist | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    if p['name'] == 'genesis-ui':
        print(p['pm2_env']['status'])
        break
else:
    print('absent')
" 2>/dev/null)

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 http://127.0.0.1:3100/ || echo 000)

echo "statut pm2 : ${etat} · reponse HTTP : ${code}"

if [ "$etat" = "online" ] && [ "$code" != "000" ]; then
    msg="✅ *Cheffer* — interface redemarree a minuit. Messagerie Onoff, alerte Serper et sidebar sont en ligne. (HTTP ${code})"
    echo "OK"
else
    msg="🚨 *Cheffer* — le redemarrage de minuit a echoue. Statut pm2 : ${etat}, HTTP ${code}. L interface peut etre indisponible."
    echo "ECHEC"
fi

cd /home/autoblog/genesis && python3 -c "
import sys
sys.path.insert(0, 'scripts')
from autoscrape_backend import notify_telegram
notify_telegram('''${msg}''')
" 2>/dev/null || echo "(alerte Telegram non envoyee)"

echo "=== fin ==="
