# Sync Emelia → Twenty CRM + Rapport Telegram hebdo

## 1. Sync Emelia → Twenty CRM

### Principe
Chaque contact prospecté via Emelia est créé/mis à jour dans Twenty CRM avec son statut de campagne (envoyé, ouvert, cliqué, répondu, bounced). Le CRM devient la source de vérité sur tous les prospects.

### Données à synchroniser

| Donnée Emelia | Champ Twenty CRM | Quand |
|---|---|---|
| email, firstName, lastName | Contact (création) | À l'injection dans Emelia |
| field1 (entreprise) | Company (lié au contact) | À l'injection |
| Statut "sent" | Tag/Status : `email_sent` | Après envoi Step 1 |
| Statut "opened" | Tag/Status : `email_opened` | Quand ouverture détectée |
| Statut "clicked" | Tag/Status : `email_clicked` | Quand clic détecté |
| Statut "replied" | Tag/Status : `email_replied` | Quand réponse reçue |
| Statut "bounced" | Tag/Status : `email_bounced` | Quand bounce |
| Statut "unsubscribed" | Tag/Status : `email_unsub` | Quand désinscription |
| Statut "interested" | Tag/Status : `lead_hot` | Classification Emelia |
| Campagne ID + nom | Note sur le contact | À l'injection |
| Date dernier email | Champ custom `lastEmailDate` | À chaque step |
| Lien TidyCal cliqué | Tag/Status : `demo_requested` | Quand clic sur TidyCal |

### Workflow de sync

```
Chaque jour à 19h UTC (après la journée d'envoi) :

1. GET /emails/campaigns/{id}/activities
   → Récupère tous les événements du jour (sent, opened, clicked, replied, bounced)

2. Pour chaque événement :
   a. Chercher le contact dans Twenty CRM par email
      GET https://localhost:3000/api/people?filter[email]={email}
   
   b. Si contact n'existe pas → le créer
      POST https://localhost:3000/api/people
      Body: {firstName, lastName, email, company: field1}
   
   c. Mettre à jour le statut
      PATCH https://localhost:3000/api/people/{id}
      Body: {tags: ["email_opened"], customFields: {lastEmailDate: "2026-05-15"}}

3. Mettre à jour le tracker local (injection-tracker.json)

4. Si statut = "replied" ET classification = "interested" :
   → Alerte Telegram immédiate : "🔥 Lead chaud : Jean Dupont (Carrefour) a répondu positivement"
   → Tag Twenty CRM : lead_hot
```

### API Twenty CRM

Base URL : `http://localhost:3000` (Docker sur le VPS)
Auth : Bearer token (TWENTY_API_KEY dans .env)

```bash
# Créer un contact
curl -X POST http://localhost:3000/api/people \
  -H "Authorization: Bearer $TWENTY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": {"firstName": "Jean", "lastName": "Dupont"}, "emails": [{"value": "j.dupont@carrefour.com"}]}'

# Mettre à jour
curl -X PATCH http://localhost:3000/api/people/{id} \
  -H "Authorization: Bearer $TWENTY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tags": ["email_opened"]}'
```

### Statuts dans le pipeline CRM

```
email_sent → email_opened → email_clicked → demo_requested → client
                          → email_replied → lead_hot → demo_requested → client
             email_bounced (exclu)
             email_unsub (exclu)
```

---

## 2. Rapport Telegram hebdomadaire

### Déclencheur
Cron chaque **lundi 9h Paris** (7h UTC) — via le skill `swarm-briefing`

### Données collectées

```
1. GET /emails/campaigns/{id}/statistics
   → sent, opened, clicked, replied, bounced (7 derniers jours)

2. GET /emails/campaigns/{id}/activities?filter=clicked
   → Liste nominative des cliqueurs

3. Requête Twenty CRM
   → Nombre de contacts dans chaque statut
```

### Format du message Telegram

```
📊 *Rapport Cold Email — Semaine du {{date}}*
leclientroi.com | juliette@leclientroi.com

━━━━━━━━━━━━━━━━━━━━━━━━

📬 *ENVOIS*
  Envoyés : {{sent}}
  Nouveaux contacts injectés : {{injected}}
  Total contacts en campagne : {{total}}

📖 *OUVERTURES*
  Ouverts : {{opened}} ({{open_rate}}%)
  {{open_rate < 18 ? "⚠️ Open rate bas — revoir les objets" : "✅ OK"}}

🖱 *CLICS*
  Clics : {{clicked}} ({{click_rate}}%)
  Clics TidyCal : {{tidycal_clicks}}

💬 *RÉPONSES*
  Réponses : {{replied}}
  Positives : {{positive}}
  Négatives : {{negative}}

🔴 *PROBLÈMES*
  Bounces : {{bounced}} ({{bounce_rate}}%)
  Désabonnements : {{unsub}}

━━━━━━━━━━━━━━━━━━━━━━━━

🏆 *CLIQUEURS DE LA SEMAINE*
{{for clicker in clickers}}
  • {{clicker.firstName}} {{clicker.lastName}} — {{clicker.company}}
    {{clicker.email}} — cliqué le {{clicker.date}}
{{endfor}}

━━━━━━━━━━━━━━━━━━━━━━━━

📈 *PIPELINE CRM*
  Envoyés : {{crm_sent}}
  Ouverts : {{crm_opened}}
  Cliqués : {{crm_clicked}}
  Leads chauds : {{crm_hot}}
  Démos bookées : {{crm_demo}}

💰 *BUDGET*
  Anthropic : ${{anthropic_remaining}} restants
  DeepSeek : ${{deepseek_remaining}} restants
  Coût campagne cette semaine : ${{weekly_cost}}
```

### Alertes instantanées (pas hebdo — en temps réel)

En plus du rapport hebdo, l'agent envoie des alertes Telegram immédiates pour :

| Événement | Message Telegram |
|---|---|
| Réponse positive | 🔥 Lead chaud : {{nom}} ({{entreprise}}) a répondu |
| Clic TidyCal | 📅 {{nom}} ({{entreprise}}) a cliqué sur la démo |
| Bounce > 3% | ⚠️ Bounce rate {{rate}}% — quota réduit |
| Bounce > 5% | 🛑 Campagne en PAUSE — bounce {{rate}}% |
| Open rate < 18% | ⚠️ Open rate {{rate}}% — revoir les objets |

---

## 3. Skill concerné : `swarm-campaign` (enrichi)

Le skill swarm-campaign intègre maintenant :

```
Matin 7h UTC :
  → Sélection batch + injection contacts (existant)
  → Vérification stats J-1

Soir 19h UTC (nouveau cron) :
  → Sync Emelia → Twenty CRM
  → GET /activities du jour
  → Créer/update contacts dans Twenty
  → Alertes Telegram si lead chaud

Lundi 7h UTC (nouveau) :
  → Rapport Telegram hebdo complet
  → Liste des cliqueurs
  → Stats pipeline CRM
```
