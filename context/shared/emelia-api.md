# Emelia.io — API Reference complète

## Remplace Mailnjoy/Salesforge dans notre architecture
Emelia = cold email + LinkedIn automation + email finder + warmup, tout-en-un.
On l'utilise pour les skills : swarm-cold-email, swarm-campaign, swarm-outreach (LinkedIn).

## Auth
- **Base URL** : `https://api.emelia.io`
- **Auth** : Header `Authorization: <API_KEY>`
- **API Key** : disponible sur https://app.emelia.io/settings/api
- **Format** : REST, JSON

## Credential à ajouter au .env
```
EMELIA_API_KEY=   # ← À FOURNIR (depuis app.emelia.io/settings/api)
```

---

## EMAIL CAMPAIGNS (20 endpoints)

### Gestion campagnes
| Method | Endpoint | Description |
|---|---|---|
| POST | `/emails/campaigns` | Créer une campagne (body: `{name}`) |
| GET | `/emails/campaigns` | Lister toutes les campagnes |
| GET | `/emails/campaigns/:campaignId` | Détails d'une campagne |
| PATCH | `/emails/campaigns/:campaignId/settings` | Modifier les paramètres globaux |
| PATCH | `/emails/campaigns/:campaignId/providers` | Modifier les providers email |
| PATCH | `/emails/campaigns/:campaignId/name` | Renommer |
| PATCH | `/emails/campaigns/:campaignId/steps` | **Configurer les séquences d'emails** |
| POST | `/emails/campaigns/:campaignId/start` | Démarrer la campagne |
| POST | `/emails/campaigns/:campaignId/pause` | Mettre en pause |
| GET | `/emails/campaigns/:campaignId/statistics` | Statistiques (ouvertures, clics, réponses) |
| GET | `/emails/campaigns/:campaignId/activities` | Activités de la campagne |
| POST | `/emails/campaigns/:campaignId/test` | Envoyer un email test |

### Gestion contacts
| Method | Endpoint | Description |
|---|---|---|
| POST | `/emails/campaign/contacts` | **Ajouter un contact** (body: `{id, contact}`) |
| GET | `/emails/campaigns/:campaignId/contacts` | Lister les contacts |
| DEL | `/emails/campaigns/:campaignId/contacts/:contactId` | Supprimer un contact |
| POST | `/emails/campaigns/:campaignId/list` | Ajouter contacts en masse depuis une liste |
| PATCH | `/emails/contacts/:contactId/custom-field` | Modifier un champ custom |
| POST | `/emails/reply` | Répondre à une réponse Emelia |

### Blacklist
| Method | Endpoint | Description |
|---|---|---|
| POST | `/emails/blacklist` | Ajouter à la blacklist |
| DEL | `/emails/blacklist/:email` | Retirer de la blacklist |

---

## LINKEDIN CAMPAIGNS (12 endpoints)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/linkedin/campaign/contacts` | Ajouter un contact LinkedIn |
| GET | `/linkedin/campaigns/:id/contacts` | Lister contacts LinkedIn |
| DEL | `/linkedin/campaigns/:id/contacts/:contactId` | Supprimer contact |
| POST | `/linkedin/campaigns/:id/list` | Ajouter depuis une liste |
| POST | `/linkedin/campaigns` | Créer une campagne LinkedIn |
| GET | `/linkedin/campaigns` | Lister campagnes LinkedIn |
| PATCH | `/linkedin/campaigns/:id/settings` | Modifier paramètres |
| PATCH | `/linkedin/campaigns/:id/name` | Renommer |
| PATCH | `/linkedin/campaigns/:id/steps` | **Configurer les steps LinkedIn** |
| PATCH | `/linkedin/contacts/:id/custom-field` | Modifier champ custom |
| GET | `/linkedin/campaigns/:id/activities` | Activités |
| GET | `/linkedin/campaigns/:id/statistics` | Statistiques |

---

## ADVANCED CAMPAIGNS (11 endpoints) — Email + LinkedIn combinés

| Method | Endpoint | Description |
|---|---|---|
| POST | `/advanced/campaign/contacts` | Ajouter contact (multicanal) |
| GET | `/advanced/campaigns/:id/contacts` | Lister contacts |
| DEL | `/advanced/campaigns/:id/contacts/:contactId` | Supprimer |
| POST | `/advanced/campaigns/:id/list` | Ajouter depuis liste |
| PATCH | `/advanced/contacts/:id/custom-field` | Modifier champ custom |
| POST | `/advanced/campaigns` | Créer campagne avancée |
| GET | `/advanced/campaigns` | Lister campagnes |
| GET | `/advanced/campaigns/:id/activities` | Activités |
| GET | `/advanced/campaigns/:id/pending-tasks` | **Tâches manuelles en attente** |
| POST | `/advanced/campaigns/:id/tasks/:taskId/status` | Valider/rejeter une tâche |
| GET | `/advanced/campaigns/:id/statistics` | Statistiques |

---

## TOOLS (6 endpoints)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/tools/find-email` | **Trouver l'email d'un contact** (nom + domaine) |
| GET | `/tools/find-email/:jobId` | Résultat de la recherche email |
| POST | `/tools/find-phone` | **Trouver le téléphone d'un contact** |
| GET | `/tools/find-phone/:jobId` | Résultat de la recherche tel |
| POST | `/tools/verify-email` | **Vérifier un email** (deliverability) |
| GET | `/tools/verify-email/:jobId` | Résultat de la vérification |

---

## EMAIL PROVIDERS (5 endpoints)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/providers` | Lister les providers email configurés |
| POST | `/providers` | Ajouter un nouveau provider |
| GET | `/providers/warmups` | Lister les warmups actifs |
| POST | `/providers/:id/warmup/enable` | Activer le warmup |
| POST | `/providers/:id/warmup/disable` | Désactiver le warmup |

---

## WEBHOOKS (4 endpoints)
Pour recevoir les événements en temps réel (ouvertures, clics, réponses, bounces).

---

## LINKEDIN SCRAPPER (13 endpoints)
Pour scraper les profils LinkedIn et enrichir les contacts.

---

## FORMAT DES STEPS (séquences email)

```json
{
  "steps": [
    {
      "delay": {
        "amount": 0,
        "unit": "MINUTES"
      },
      "versions": [
        {
          "subject": "Objet email variante A",
          "disabled": false,
          "message": "<p>Corps de l'email HTML</p>",
          "rawHtml": true,
          "attachments": []
        },
        {
          "subject": "Objet email variante B (A/B test)",
          "disabled": false,
          "message": "<p>Corps alternatif</p>",
          "rawHtml": true,
          "attachments": []
        }
      ]
    },
    {
      "delay": {
        "amount": 3,
        "unit": "DAYS"
      },
      "versions": [
        {
          "subject": "Relance — {{firstName}}",
          "disabled": false,
          "message": "<p>Email de relance J+3</p>",
          "rawHtml": true
        }
      ]
    },
    {
      "delay": {
        "amount": 7,
        "unit": "DAYS"
      },
      "versions": [
        {
          "subject": "Dernière relance",
          "disabled": false,
          "message": "<p>Email final J+7</p>",
          "rawHtml": true
        }
      ]
    }
  ]
}
```

## FORMAT CONTACT

```json
{
  "id": "campaign_id",
  "contact": {
    "email": "prospect@entreprise.com",
    "firstName": "Jean",
    "lastName": "Dupont",
    "field1": "Valeur custom 1 (ex: entreprise)",
    "field2": "Valeur custom 2 (ex: poste)"
  }
}
```

---

## WORKFLOW COLD EMAIL AVEC EMELIA

### Flux complet piloté par l'agent Genesis :

```
1. Créer la campagne
   POST /emails/campaigns {name: "LCR — SMS PME Ile-de-France — Mai 2026"}
   → Récupérer campaignId

2. Configurer les steps (séquence 3 emails)
   PATCH /emails/campaigns/:campaignId/steps
   → Email 1 (J+0): icebreaker personnalisé + CTA
   → Email 2 (J+3): relance soft + cas client
   → Email 3 (J+7): dernière relance urgence douce
   → Variantes A/B sur l'objet de l'email 1

3. Configurer les providers
   PATCH /emails/campaigns/:campaignId/providers
   → Sélectionner le provider email configuré dans Emelia

4. Pour chaque prospect du CSV :
   a. Vérifier l'email
      POST /tools/verify-email {email: "prospect@..."}
      → Si bounce probable → skip
   b. Générer l'icebreaker personnalisé (Claude Sonnet)
   c. Ajouter le contact
      POST /emails/campaign/contacts {id: campaignId, contact: {...}}

5. Démarrer la campagne
   POST /emails/campaigns/:campaignId/start

6. Monitoring quotidien
   GET /emails/campaigns/:campaignId/statistics
   → Ouvertures, clics, réponses, bounces
   → Si bounce > 5% → POST .../pause
   → Rapport dans le dashboard

7. Traiter les réponses
   GET /emails/campaigns/:campaignId/activities
   → Réponses positives → alerte Telegram
   → POST /emails/reply pour répondre automatiquement (optionnel)
```

### Bonus : LinkedIn + Email (Advanced Campaign)
Emelia supporte les campagnes multicanal :
1. Email J+0 → si pas d'ouverture → LinkedIn J+3 → Email relance J+5
2. Tout dans une seule campagne Advanced

---

## CE QUE EMELIA REMPLACE DANS NOTRE ARCHITECTURE

| Avant (plan initial) | Maintenant (Emelia) |
|---|---|
| Salesforge MCP | ❌ Plus besoin — Emelia API directe |
| Mailnjoy MCP | ❌ Plus besoin — Emelia API directe |
| Resend (newsletter) | ✅ Garde pour newsletter broadcast, OU utilise Emelia |
| Zernio (LinkedIn) | ❌ Plus besoin — Emelia LinkedIn campaigns |
| Recherche email manuelle | ❌ Plus besoin — Emelia email finder |
| Vérification email | ❌ Plus besoin — Emelia verify-email |
| Warmup | ❌ Plus besoin — Emelia warmup intégré |

### Emelia = 1 seul outil pour :
- Cold email 1-to-1 personnalisé
- Séquences multi-steps avec A/B test
- LinkedIn automation (messages, invitations)
- Campagnes multicanal (email + LinkedIn)
- Email finder + phone finder
- Email verification
- Warmup automatique
- Webhooks pour tracking temps réel
