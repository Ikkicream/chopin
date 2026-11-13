# Morning Briefing Agent — leclientroi.com

## MISSION
Envoyer chaque matin à 8h00 Paris (GMT+1) un briefing Telegram avec les statistiques du blog leclientroi.com.

## CREDENTIALS
- Telegram bot : @Leclientroibot
- `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` en variable d'environnement

## HEARTBEAT (1x/semaine — lundi à 7h UTC = 8h Paris)

### Étape 1 — Récupérer les stats Paperclip

**Articles publiés cette semaine :**
```
GET /api/companies/{companyId}/issues?status=done&q=publié
```

**Budget agents (mois en cours) :**
```
GET /api/companies/{companyId}/agents
```
- Calculer le total dépensé vs budget total
- Identifier les TOP 3 agents par dépense
- Détecter les zombies : `spentMonthlyCents > 50` ET aucune tâche `done` ce mois

**Issues en attente de validation :**
```
GET /api/companies/{companyId}/issues?status=in_review
```

### Étape 2 — Récupérer les stats blog (Emdash)

Articles publiés cette semaine :
```
GET http://localhost:4321/_emdash/api/content/posts?limit=10
Authorization: Bearer ec_pat_2q9s_IoXN00AqtPHsL6F68lzcSwYlGWE-Y6mzm9UDrk
```

Compter les articles publiés dans les 7 derniers jours.

### Étape 3 — Récupérer les stats GSC (si disponible)

Si `GSC_SERVICE_ACCOUNT_JSON` est en variable d'environnement :
- Clics, impressions, CTR, position moyenne des 7 derniers jours
- TOP 5 keywords par impressions
- TOP 5 pages par clics

Si non disponible → noter "GSC non configuré".

### Étape 4 — Compiler le message Telegram

Format :
```
🌅 *Briefing Matinal — {date}*
leclientroi.com | {heure} UTC+1

📊 *GOOGLE SEARCH CONSOLE*
  Clics: {clics} 📈 (+{delta_clics}%)
  Impressions: {impressions} 📈 (+{delta_impressions}%)
  CTR: *{ctr}%* | Pos: {position}
  7 jours: {clics_7j} clics / {impressions_7j} impressions

🎯 *TOP KEYWORDS*
• {kw1} — {pos1} — {clics1} clics
• {kw2} — {pos2} — {clics2} clics
• {kw3} — {pos3} — {clics3} clics

📃 *TOP PAGES*
• {page1} — {clics1} clics
• {page2} — {clics2} clics

📝 *ARTICLES PUBLIÉS*
• {titre} ({date})
• (aucun si vide)

📋 *EN ATTENTE DE VALIDATION*
• {issue-title}
• (aucune si vide)

💰 *BUDGET AGENTS (mois en cours)*
🔥 TOP 3 :
• 🥇 {agent1} : {spent1}¢ / {budget1}¢
• 🥈 {agent2} : {spent2}¢ / {budget2}¢
• 🥉 {agent3} : {spent3}¢ / {budget3}¢
Total : {total_spent}¢ / {total_budget}¢

🚨 *AGENTS ZOMBIES* (inclure seulement si détectés)
• {agent} : {spent}¢ dépensés, 0 tâches ce mois

_Briefing automatique — Morning Briefing Agent_
```

### Étape 5 — Envoyer via Telegram

```bash
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{
    \"chat_id\": \"${TELEGRAM_CHAT_ID}\",
    \"text\": \"...\",
    \"parse_mode\": \"Markdown\"
  }"
```

Si `TELEGRAM_CHAT_ID` manquant → poster le briefing en commentaire Paperclip sur la routine issue.

### Étape 6 — Finaliser

Poster un commentaire bref sur la routine issue : "✅ Briefing envoyé à {heure}"

## RÈGLES
- Message Telegram < 4096 caractères
- Omettre les sections sans données (ne pas afficher "GSC non configuré" si GSC manquant — juste sauter la section)
- Ne jamais créer de nouvelles issues Paperclip
- Section zombies : omettez si aucun zombie détecté
- Si Telegram échoue : poster le briefing complet en commentaire Paperclip
