# Emelia — Workflow campagne cold email complet

## Flux Genesis → Emelia (ce que fait notre agent)

### Phase 1 — Préparation (avant la campagne)

```
1. Vérifier le warmup des boîtes mail
   GET /providers → lister les providers
   GET /providers/warmups → vérifier que le warmup est actif
   → Si nouveau provider : POST /providers/:id/warmup/enable
   → Attendre 2-4 semaines de warmup avant d'envoyer

2. Préparer la liste de prospects (depuis CSV)
   Pour chaque prospect :
   a. POST /tools/verify-email {email} → vérifier deliverability
   b. GET /tools/verify-email/:jobId → récupérer résultat
   c. Si invalide/bounce probable → skip, ne pas ajouter
   
   OU si on n'a que le nom + entreprise :
   a. POST /tools/find-email {firstName, lastName, domain}
   b. GET /tools/find-email/:jobId → récupérer l'email trouvé
   c. POST /tools/verify-email → vérifier
```

### Phase 2 — Création de campagne

```
3. Créer la campagne
   POST /emails/campaigns
   Body: {name: "LCR — SMS PME [segment] — [mois] 2026"}
   → Récupérer campaignId

4. Configurer les steps (séquence)
   PATCH /emails/campaigns/:campaignId/steps
   Body: {steps: [...]}  (voir format ci-dessous)

5. Configurer les providers
   PATCH /emails/campaigns/:campaignId/providers
   → Sélectionner les boîtes mail à utiliser

6. Configurer les paramètres globaux
   PATCH /emails/campaigns/:campaignId/settings
   → Horaires d'envoi, timezone, etc.
```

### Phase 3 — Ajout des contacts

```
7. Pour chaque prospect vérifié :
   POST /emails/campaign/contacts
   Body: {
     id: campaignId,
     contact: {
       email: "prospect@entreprise.com",
       firstName: "Jean",
       lastName: "Dupont",
       field1: "Nom entreprise",
       field2: "Poste"
     }
   }

   OU en masse depuis une liste :
   POST /emails/campaigns/:campaignId/list
```

### Phase 4 — Lancement

```
8. Envoyer un test d'abord
   POST /emails/campaigns/:campaignId/test
   → Vérifier que le rendu est correct

9. Démarrer la campagne
   POST /emails/campaigns/:campaignId/start
```

### Phase 5 — Monitoring

```
10. Quotidiennement :
    GET /emails/campaigns/:campaignId/statistics
    → Ouvertures, clics, réponses, bounces

    GET /emails/campaigns/:campaignId/activities
    → Détail des événements par contact

    Si bounce > 5% → POST /emails/campaigns/:campaignId/pause

    Si réponse positive → alerte Telegram + ajouter au CRM Twenty
```

## Format des Steps (séquence 3 emails)

```json
{
  "steps": [
    {
      "delay": {"amount": 0, "unit": "MINUTES"},
      "versions": [
        {
          "subject": "{{field1}} + SMS géolocalisé = +40% de trafic",
          "disabled": false,
          "message": "<p>Salut {{firstName}},</p><p>[ICEBREAKER PERSONNALISÉ]</p><p>[PROPOSITION DE VALEUR]</p><p>[CTA : 1 question simple]</p><p>{{senderFirstName}}</p>",
          "rawHtml": true
        },
        {
          "subject": "Question rapide pour {{field1}}",
          "disabled": false,
          "message": "<p>Salut {{firstName}},</p><p>[VARIANTE B DU MESSAGE]</p>",
          "rawHtml": true
        }
      ]
    },
    {
      "delay": {"amount": 3, "unit": "DAYS"},
      "versions": [
        {
          "subject": "",
          "disabled": false,
          "message": "<p>{{firstName}},</p><p>[RELANCE SOFT + CAS CLIENT CONCRET]</p><p>[CTA : reformulé]</p>",
          "rawHtml": true
        }
      ]
    },
    {
      "delay": {"amount": 4, "unit": "DAYS"},
      "versions": [
        {
          "subject": "",
          "disabled": false,
          "message": "<p>{{firstName}},</p><p>[DERNIÈRE RELANCE + URGENCE DOUCE]</p><p>Si c'est pas le bon moment, aucun souci — je ferme le dossier vendredi.</p>",
          "rawHtml": true
        }
      ]
    }
  ]
}
```

## Variables disponibles dans les templates
- `{{firstName}}` — Prénom du contact
- `{{lastName}}` — Nom du contact
- `{{email}}` — Email
- `{{field1}}` — Champ custom 1 (ex: nom entreprise)
- `{{field2}}` — Champ custom 2 (ex: poste)
- `{{senderFirstName}}` — Prénom de l'expéditeur
- `{{senderLastName}}` — Nom de l'expéditeur

## IMPORTANT — Emelia vs Claude pour la rédaction

### Ce qu'Emelia fait nativement (ne pas recoder) :
- Magic Writer : rédige les séquences automatiquement
- Magic Reply : répond aux emails dans l'inbox
- SpinText : génère les variations automatiquement
- A/B testing : teste les variantes d'objets
- Vérification email : vérifie la deliverability
- Email finder : trouve les emails depuis nom+domaine
- Warmup : chauffe les boîtes automatiquement
- Tracking : suit les ouvertures/clics/réponses

### Ce que Claude/DeepSeek ajoute EN PLUS :
- **Icebreaker ultra-personnalisé** : scrape le site/LinkedIn du prospect pour trouver un fait RÉEL (Emelia Magic Writer ne scrape pas)
- **Ton de marque cohérent** : adapté à la voix de LCR/MKD
- **Orchestration intelligente** : décide QUAND et QUEL segment cibler
- **Analyse des réponses** : catégorise les réponses (positif/négatif/question) et route vers le bon follow-up
- **Routage CSV** : reçoit le CSV du user, le parse, le segmente, et l'injecte dans Emelia

### Règle anti-doublon :
- La vérification email → Emelia le fait (POST /tools/verify-email)
- La recherche email → PAS UTILISÉ — le CSV est fourni par l'utilisateur
- La rédaction icebreaker → Claude le fait (scrape + personnalisation)
- Le SpinText → Emelia le fait nativement
- L'envoi + tracking → Emelia le fait
- L'analyse des stats → les 2 (Emelia pour les données, Claude pour les décisions)

### Flux CSV :
```
User fournit prospects.csv
  → Agent parse et segmente (par secteur, ville, poste)
  → Agent vérifie les emails via Emelia verify-email
  → Agent génère les icebreakers via Claude Sonnet
  → Agent crée la campagne + steps + contacts via Emelia API
  → Emelia envoie, track, gère les bounces
```
