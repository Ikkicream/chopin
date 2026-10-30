# swarm-briefing — Rapport Telegram Quotidien

## Format de réponse (RÈGLE DURE pour la boucle agent_core)

Tu réponds **UNIQUEMENT en JSON strict** :
```json
{
  "reasoning": "1-2 phrases : la signature du jour (calme/agitée/anomalie)",
  "plan": [
    {
      "action_type": "send_briefing",
      "target": "telegram",
      "why": "résumé en 1 phrase de ce qui mérite l'attention aujourd'hui",
      "tags": {
        "summary": "synthèse markdown courte (≤ 600 chars, FR, 3-5 bullets)",
        "highlights": ["fait 1", "fait 2", "fait 3"],
        "anomalies": ["anomalie 1 si applicable"],
        "actions_required": ["action user 1 si applicable"],
        "kpis": {
          "sessions_today": 0,
          "articles_published_today": 0,
          "actions_evaluated_today": 0
        }
      }
    }
  ]
}
```

**1 briefing par cycle**. Si rien de notable (KPIs nominaux, pas d'anomalie), reste utile : envoie un briefing court qui confirme que tout va bien (anti-silence dangereux). `plan: []` uniquement si pas de données.

**Capitalise sur la mémoire** : ne re-signale pas une anomalie déjà mentionnée hier qui n'a pas évolué — mentionne juste « toujours en cours ».

---

Modèle : Claude Haiku (default)
Déclenchement : chaque jour 7h UTC (= 8h Paris été / 9h hiver — ajuster si besoin)

## Initialisation

```bash
set -a; source /home/autoblog/genesis/.env; set +a
cd /home/autoblog/genesis
TODAY=$(date -u +%Y-%m-%d)
YESTERDAY=$(date -u -d "yesterday" +%Y-%m-%d 2>/dev/null || date -u -v-1d +%Y-%m-%d)
WEEK=$(date -u +%Y-W%V)
```

## Étape 1 : Articles publiés hier

```bash
LCR_ARTICLE=$(grep "$YESTERDAY" memory/lcr/articles-published.md 2>/dev/null | head -1 | awk -F'|' '{print $3}' | xargs || echo "(aucun)")
MKD_ARTICLE=$(grep "$YESTERDAY" memory/mkd/articles-published.md 2>/dev/null | head -1 | awk -F'|' '{print $3}' | xargs || echo "(aucun)")
```

## Étape 2 : Budget consommé

```bash
# Budget du jour
TODAY_COST=$(python3 -c "
import json
try:
    with open('memory/shared/costs-log.json') as f:
        data = json.load(f)
    cost = sum(e.get('cost_usd', 0) for e in data.get('entries', []) if e.get('date','').startswith('${TODAY}'))
    print(f'{cost:.4f}')
except:
    print('0.0000')
")

# Budget de la semaine
WEEK_COST=$(python3 -c "
import json
try:
    with open('memory/shared/costs-log.json') as f:
        data = json.load(f)
    cost = sum(e.get('cost_usd', 0) for e in data.get('entries', []) if e.get('week') == '${WEEK}')
    print(f'{cost:.4f}')
except:
    print('0.0000')
")
```

## Étape 3 : Stats Emelia

```bash
# Lister les campagnes actives
CAMPAIGNS_JSON=$(curl -s "https://api.emelia.io/emails/campaigns" \
  -H "Authorization: ${EMELIA_API_KEY}" 2>/dev/null)

EMELIA_STATS=$(echo "$CAMPAIGNS_JSON" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    campaigns = d if isinstance(d, list) else d.get('data', [])
    active = [c for c in campaigns if c.get('status') in ['active', 'running', 'sending']]
    if not active:
        print('Aucune campagne active')
    else:
        lines = []
        for c in active[:3]:
            name = c.get('name', 'Sans nom')[:30]
            cid = c.get('id', '')
            lines.append(f'• {name} (ID: {cid[:8]}...)')
        print('\n'.join(lines))
except Exception as e:
    print(f'Erreur Emelia: {e}')
" 2>/dev/null)

# Stats détaillées de la première campagne active
FIRST_CAMPAIGN_ID=$(echo "$CAMPAIGNS_JSON" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    campaigns = d if isinstance(d, list) else d.get('data', [])
    active = [c for c in campaigns if c.get('status') in ['active', 'running', 'sending']]
    print(active[0]['id'] if active else '')
except:
    print('')
" 2>/dev/null)

if [ -n "$FIRST_CAMPAIGN_ID" ]; then
  STATS=$(curl -s "https://api.emelia.io/emails/campaigns/${FIRST_CAMPAIGN_ID}/statistics" \
    -H "Authorization: ${EMELIA_API_KEY}" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    sent = d.get('sent', 0)
    opened = d.get('opened', 0)
    clicked = d.get('clicked', 0)
    replied = d.get('replied', 0)
    bounced = d.get('bounced', 0)
    open_rate = round(opened/sent*100, 1) if sent > 0 else 0
    bounce_rate = round(bounced/sent*100, 1) if sent > 0 else 0
    print(f'Envoyés: {sent} | Ouverture: {open_rate}% | Clics: {clicked} | Réponses: {replied} | Bounces: {bounce_rate}%')
except Exception as e:
    print(f'Stats indisponibles: {e}')
" 2>/dev/null)
else
  STATS="Aucune campagne active"
fi
```

## Étape 4 : Construire les alertes

```bash
ALERTS=""

# Vérifier open rate (si stats disponibles)
OPEN_RATE=$(echo "$STATS" | python3 -c "import sys,re; m=re.search(r'Ouverture: ([\d.]+)%', sys.stdin.read()); print(m.group(1) if m else '0')" 2>/dev/null)
if python3 -c "import sys; exit(0 if float('${OPEN_RATE:-0}') < 18 and float('${OPEN_RATE:-0}') > 0 else 1)" 2>/dev/null; then
  ALERTS="${ALERTS}⚠️ Open rate faible (${OPEN_RATE}%) — vérifier objet email\n"
fi

# Vérifier bounce rate
BOUNCE_RATE=$(echo "$STATS" | python3 -c "import sys,re; m=re.search(r'Bounces: ([\d.]+)%', sys.stdin.read()); print(m.group(1) if m else '0')" 2>/dev/null)
if python3 -c "import sys; exit(0 if float('${BOUNCE_RATE:-0}') > 3 else 1)" 2>/dev/null; then
  ALERTS="${ALERTS}🚨 Bounce rate élevé (${BOUNCE_RATE}%) — RÉDUIRE quota envoi\n"
fi

# Vérifier budget semaine
if python3 -c "import sys; exit(0 if float('${WEEK_COST:-0}') > 8.0 else 1)" 2>/dev/null; then
  ALERTS="${ALERTS}💸 Budget semaine > \$8 — attention au plafond \$10\n"
fi

[ -z "$ALERTS" ] && ALERTS="Rien à signaler ✅"
```

## Étape 5 : Envoyer le rapport Telegram

```bash
MSG=$(python3 -c "
import os
today = '${TODAY}'
lcr = '${LCR_ARTICLE}' or '(aucun)'
mkd = '${MKD_ARTICLE}' or '(aucun)'
week = '${WEEK}'
today_cost = '${TODAY_COST}'
week_cost = '${WEEK_COST}'
emelia = '''${EMELIA_STATS}'''
stats = '''${STATS}'''
alerts = '''${ALERTS}'''

msg = f'''📊 *Genesis — Briefing {today}*

📝 *Articles publiés hier*
LCR : {lcr}
MKD : {mkd}

📧 *Campagnes Emelia*
{emelia}
{stats}

💰 *Budget*
Aujourd'hui : \${today_cost}
Semaine {week} : \${week_cost} / \$10.00 max

⚠️ *Alertes*
{alerts}'''

print(msg)
")

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json
msg = open('/tmp/briefing_msg.txt').read() if False else '''${MSG}'''
print(json.dumps({'chat_id': '${TELEGRAM_CHAT_ID}', 'text': msg, 'parse_mode': 'Markdown'}))
")" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Telegram:', 'OK ✅' if d.get('ok') else '❌ ' + str(d.get('description')))"
```

## Notes

- Si le rapport Telegram échoue (réseau, format), logger l'erreur dans `memory/shared/agent-logs/sessions.jsonl`
- Le message doit rester < 4096 chars (limite Telegram)
- En cas de bounce > 5% → envoyer une alerte URGENTE séparée (message prioritaire)
