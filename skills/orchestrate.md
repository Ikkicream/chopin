# swarm-orchestrate — Orchestrateur Hebdomadaire

Modèle : Claude Sonnet (think)
Déclenchement : lundi 6h UTC (cron) ou commande manuelle

## Initialisation

```bash
set -a; source /home/autoblog/genesis/.env; set +a
cd /home/autoblog/genesis
WEEK=$(date -u +%Y-W%V)
TODAY=$(date -u +%Y-%m-%d)
```

## Étape 1 — Lire la mémoire

Lire les fichiers suivants :
- `memory/lcr/articles-published.md` → noter les slugs et semaines déjà publiés
- `memory/mkd/articles-published.md` → idem pour MKD
- `memory/shared/costs-log.json` → budget consommé ce mois

Vérifier : y a-t-il déjà un article publié cette semaine ($WEEK) pour LCR ? Pour MKD ?
- Si oui pour LCR → NE PAS republier (skip tâche LCR)
- Si oui pour MKD → NE PAS republier (skip tâche MKD)

## Étape 2 — Calculer le budget restant

```bash
python3 -c "
import json
with open('memory/shared/costs-log.json') as f:
    data = json.load(f)
week_cost = sum(e.get('cost_usd', 0) for e in data.get('entries', []) if e.get('week') == '${WEEK}')
print(f'Budget semaine: \${week_cost:.4f} / \$10.00')
if week_cost > 9.0:
    print('ALERTE: budget presque épuisé cette semaine')
"
```

Si budget semaine > $9 → envoyer alerte Telegram et s'arrêter.

## Étape 3 — Exécuter le contenu LCR (si non skippé)

Suivre en entier les instructions de `skills/content.md` avec SITE=lcr.
Sauvegarder le résultat : TITRE_LCR, SLUG_LCR, URL_LCR.

## Étape 4 — Exécuter le contenu MKD (si non skippé)

Suivre en entier les instructions de `skills/content.md` avec SITE=mkd.
Sauvegarder le résultat : TITRE_MKD, SLUG_MKD, URL_MKD.

## Étape 5 — Mettre à jour la mémoire

Suivre les instructions de `skills/memory.md` pour logger les publications et les coûts.

Créer le rapport hebdomadaire `memory/lcr/weekly-reports/${WEEK}.md` et `memory/mkd/weekly-reports/${WEEK}.md`.

## Étape 6 — Rapport Telegram

```bash
MSG="🤖 *Genesis — Semaine ${WEEK}*

$([ -n "$TITRE_LCR" ] && echo "✅ *LCR* : \"${TITRE_LCR}\"" || echo "⏭️ *LCR* : déjà publié cette semaine")
$([ -n "$TITRE_MKD" ] && echo "✅ *MKD* : \"${TITRE_MKD}\"" || echo "⏭️ *MKD* : déjà publié cette semaine")

💰 Budget semaine : ~\$${WEEK_COST} / \$10 max
📅 Prochaine orchestration : lundi prochain 6h UTC"

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\":\"${TELEGRAM_CHAT_ID}\",\"text\":\"${MSG}\",\"parse_mode\":\"Markdown\"}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Telegram:', 'OK' if d.get('ok') else d.get('description'))"
```

## Contraintes absolues

- MAX 1 article/semaine/site — vérifier avant toute action
- MAX $10/semaine total — vérifier le budget avant chaque skill
- Toujours sourcer .env avant tout appel API
- Toujours mettre à jour memory/ après chaque publication
