# API Emelia — carte vérifiée (2026-06-04)

Établie en testant réellement chaque endpoint (campagne immobilier LCR). Évite de re-tâtonner :
tout ce qui est marqué ❌ a été essayé et N'EXISTE PAS.

Auth (REST et GraphQL) : header `Authorization: <clé API>` — **sans** préfixe `Bearer`.

## REST `https://api.emelia.io`

| Méthode + chemin | Statut | Notes |
|---|---|---|
| `GET /emails/campaigns` | ✅ | liste ; `_id`, `name`, `status` (DRAFT/RUNNING/…) |
| `GET /emails/campaigns/{id}` | ✅ | détail : `schedule`, `provider`, `recipients.contacts` = **IDs Mongo** (pas d'emails) |
| `POST /emails/campaigns` `{name}` | ✅ | création |
| `PATCH /emails/campaigns/{id}/steps` `{steps}` | ✅ | steps = séquence d'emails |
| `POST /emails/campaigns/{id}/start` | ✅ | démarre (DRAFT→RUNNING) |
| `POST /emails/campaign/contacts` `{id, contact}` | ✅ | ⚠️ « campaign » au **singulier**. contact = `{email, firstName, lastName, field1..field4}` |
| `POST /emails/test` `{campaignId, email, step}` | ✅ | BAT (données de test Emelia, pas le vrai contact) |
| `PATCH /emails/campaigns/{id}/settings` | ❌ 404 | n'a JAMAIS existé — le réglage « 8h-18h » de `get_or_create_campaign` ne s'est jamais appliqué |
| `GET /emails/campaigns/{id}/contacts` | ❌ 404 | aucun listing REST des contacts d'une campagne |
| `GET /emails/contacts/{id}` (et variantes) | ❌ 404 | pas de GET contact par id en REST |

## GraphQL `https://graphql.emelia.io/graphql`

Introspection **désactivée**. Doc ancienne : https://docs-old.emelia.io/

Queries vérifiées :
```graphql
query campaign($id: ID!){ campaign(id: $id){
  _id name status createdAt provider startAt estimatedEnd
  schedule{ dailyContact dailyLimit minInterval maxInterval timeZone days start end eventToStopMails }
  recipients{ processing total_count }
}}

# SEUL moyen de résoudre un ID de recipients.contacts en email :
query contact($id: ID!, $campaignId: ID!){ contact(id: $id, campaignId: $campaignId){
  email firstName lastName custom   # custom = {field1..field4}
}}
```

Mutations vérifiées (existence confirmée par probe) :
- `createCampaign`, `startCampaign`, `pauseCampaign(id: ID!)`
- `addContactToCampaignHook`
- `removeOneContactFromCampaign(id: ID!, email: String!)` — retrait par email
- `updateCampaignSettings(id: ID!, data: JSON!)` — **seul** moyen de changer la fenêtre d'envoi

N'existent pas : `updateCampaign`, `updateCampaignSchedule`, `updateSchedule`, `editCampaign`,
`campaignSchedule`, `setCampaignSchedule`, `campaignContacts`.

## Pièges connus

1. **Emelia trim les espaces de bord du champ `firstName`** à l'ingestion (`' Camille'` → `'Camille'`).
   → C'est pour ça que `firstName` porte la salutation complète (`Bonjour Camille` / `Bonjour`)
   et que les templates utilisent `{{firstName}},` sans « Bonjour » littéral.
   Voir `greeting_first_name()` (workflow_emelia_push) + `normalize_greeting()` (email_templates_backend).
2. **Schedule par défaut réel** : 08:00–**17:00**, Europe/Brussels, jours 0-4 (lun-ven),
   dailyContact 35. Hors fenêtre, `start` accepte mais n'envoie rien avant la prochaine fenêtre.
3. `stats` vide ≠ campagne vide : regarder `recipients.contacts` (des contacts peuvent traîner
   depuis d'anciens tests — vérifier AVANT de démarrer une campagne).
4. Les IDs Mongo encodent la date d'ajout : `datetime.fromtimestamp(int(id[:8], 16), tz=UTC)`.
5. Probe sûre d'une mutation inconnue : l'appeler **sans arguments** —
   « Cannot query field » = n'existe pas ; « argument X of type Y! is required » = existe.
   Rejet à la validation = zéro effet de bord.

## Compléments vérifiés (test réel du 2026-06-04, envoi + ouverture confirmés)

- **steps ET schedule ne sont modifiables qu'en PAUSE** : `PATCH .../steps` sur une campagne
  RUNNING -> 400 « Campaign cannot be modified while running ». Séquence : `pauseCampaign` ->
  patch/update -> `POST .../start`.
- **Payload de `updateCampaignSettings`** : `{id, data: {"schedule": {…TOUS les champs…}}}` —
  le schedule complet est requis (dailyContact, dailyLimit, minInterval, maxInterval,
  blacklistUnsub, trackLinks, trackOpens, timeZone, days, start, end, eventToStopMails).
  Les clés à plat (`start`, `sendingHours`…) sont rejetées « is not allowed ».
  ⚠️ La mutation répond OK même hors pause mais N'APPLIQUE RIEN : toujours relire le schedule après.
- **Statut d'envoi par contact** : `contact(id, campaignId){ status lastContacted lastOpen }`
  -> status NOT_CONTACTED / CONTACTED / OPENED / …, timestamps en ms.
- `recipients.processing` = ingestion des contacts en cours.
- **Webhooks : le payload ne contient PAS l'id de campagne**, seulement son NOM en string
  (`{"event":"SENT","campaign":"workflow-lcr-immobilier","contact":{...},"date":...,"step":0}`).
  -> RÉSOLU le 04/06 : le handler `/api/emelia/webhook` résout nom -> _id via
  `list_campaigns` (cache module `_emelia_camp_id_cache`) et stocke `campaign_id` ;
  backfill historique fait. Sans ça, `/api/campaigns/{id}/stats-by-day` ne matchait rien.
  NB : le comptage warmup (`emelia_sent_today_by_sender`) filtre par site_code -> n'était pas impacté.
  Lister les webhooks enregistrés : `GET /webhook` (REST).
