# Resend — usage dans une plateforme multi-tenant

Faits vérifiés au 13/10/2026 (docs Resend + types du SDK `resend` 6.32.1).

## Sommaire
1. Ce que Resend partage entre tous vos clients
2. Domaines
3. Envoi
4. Webhooks
5. Clés restreintes et OAuth
6. Plans et limites

---

## 1. Ce que Resend partage entre tous vos clients (un compte = une « team »)

- **Débit** : 10 requêtes/s par team, toutes clés confondues (relevable par le support uniquement).
- **Liste de suppression** : une adresse en bounce ou en plainte chez le client A est bloquée pour le client B.
- **Contacts, désinscriptions, Topics, Segments, page de désinscription** : au niveau de la team.
- **Seuils de compte** : bounces < 4 %, spam < 0,08 % — au-delà, l'envoi du compte peut être suspendu.
- **Données** : stockées aux États-Unis quelle que soit la région d'envoi (à mentionner dans le DPA).
- Pas de sous-comptes ni de création de team par API.

→ Resend porte le **transactionnel** (faible volume, faible risque) ; le marketing des clients va sur SES.
Les Broadcasts / Contacts Resend ne sont pas utilisés pour les clients de la plateforme.

## 2. Domaines

```ts
await resend.domains.create({
  name: "mail.client.com",
  region: "eu-west-1",          // us-east-1 | eu-west-1 | sa-east-1 | ap-northeast-1 — DÉFINITIF
  customReturnPath: "send",     // DÉFINITIF (≤ 63 caractères, commence par une lettre)
  tls: "opportunistic",         // ou "enforced"
  openTracking: false, clickTracking: false,
  trackingSubdomain: "links",   // optionnel, modifiable mais jamais supprimable
});
```
- Réponse : `records[]` (`record`: SPF | DKIM | Receiving | Tracking | TrackingCAA, `name`, `type`,
  `value`, `priority`, `status`). **Toujours afficher ce tableau** : depuis août 2026 le Return-Path
  peut être 2 CNAME (`send`, `rsend`) au lieu de MX + TXT.
- Statuts : `not_started`, `pending`, `verified`, `partially_verified`, `partially_failed`, `failed`
  (records absents après 72 h), `temporary_failure`.
- `resend.domains.verify(id)` est asynchrone : statut repassé à `pending`, puis webhook `domain.updated`
  (il n'existe pas d'événement `domain.verified`).
- Un domaine n'appartient qu'à une team ; procédure de revendication par TXT si déjà pris ailleurs.
- DKIM : TXT `resend._domainkey`, **1024 bits uniquement**.
- Limites de domaines : Free 3, Pro 10, Scale 1 000 (+100 domaines pour 20 $/mois).

## 3. Envoi

```ts
await resend.emails.send(
  { from: "Acme <notifications@mail.client.com>", to: "jean@exemple.fr", replyTo, subject, html, text,
    headers: { /* List-Unsubscribe… pour le marketing */ },
    tags: [{ name: "tenant", value: tenantId }] },        // [A-Za-z0-9_-], 75 tags max
  { idempotencyKey: messageId },                          // 24 h, 256 caractères max
);
```
- `to` : 50 adresses max (la brique en met une). 40 Mo par email. `scheduledAt` jusqu'à 30 jours.
- `resend.batch.send([...], { idempotencyKey })` : 100 emails par appel, sans pièces jointes ; un appel
  compte pour une requête.
- Erreurs 429 : `rate_limit_exceeded` (en-têtes `ratelimit-*`, `retry-after`), `daily_quota_exceeded`,
  `monthly_quota_exceeded`. 409 : `concurrent_idempotent_requests`, `invalid_idempotent_request`.
- Toutes les méthodes du SDK renvoient `{ data, error, headers }` (pas d'exception).
- One-click : à poser soi-même sur `/emails` (`List-Unsubscribe` + `List-Unsubscribe-Post`).

## 4. Webhooks

- Événements email : `email.sent`, `email.scheduled`, `email.delivered`, `email.delivery_delayed`,
  `email.bounced`, `email.complained`, `email.opened`, `email.clicked`, `email.failed`,
  `email.suppressed`, `email.received` ; plus `domain.*`, `contact.*`, `suppression.*`, `topic.*`.
- Charge utile : `{ type, created_at, data: { email_id, from, to[], subject, tags: { clé: valeur }, bounce?: { type: "Permanent"|"Temporary", subType, message } } }`.
- Signature Svix (`svix-id`, `svix-timestamp`, `svix-signature`) sur le corps brut. La brique vérifie
  avec le paquet `svix` (pas besoin de clé d'API) puis parse le corps.
- Au moins une fois, sans ordre garanti : dédoublonner sur `svix-id`, trier sur `created_at`.
- Nouveaux essais : immédiat, 5 s, 5 min, 30 min, 2 h, 5 h, 10 h, 10 h ; endpoint désactivé après échecs répétés.
- Création par API : `resend.webhooks.create({ endpoint, events })` → `signing_secret` (`whsec_…`).
- Endpoints : 1 (Free), 5 (Pro), 10 (Scale) → un seul endpoint, routage par le tag `tenant`.
- Adresses de test : `delivered@resend.dev`, `bounced@resend.dev`, `complained@resend.dev`.

## 5. Clés restreintes et OAuth

- `resend.apiKeys.create({ name, permission: "sending_access", domain_id })` : clé limitée à un domaine,
  à remettre à un client qui envoie depuis son propre code (le jeton n'est affiché qu'une fois).
- Modèle « chaque client a son compte Resend » : OAuth 2.1 + PKCE (portées `emails:send`,
  `full_access`), sans stocker de clé d'API client.

## 6. Plans (transactionnel)

| Plan | Prix / emails par mois | Domaines | Webhooks |
|---|---|---|---|
| Free | 0 $ / 3 000 (100/jour) | 3 | 1 |
| Pro | 20 $ / 50 k ; 35 $ / 100 k | 10 | 5 |
| Scale | 90 $ / 100 k … 1 150 $ / 2,5 M | 1 000 | 10 |

IP dédiée : 30 $/mois (Scale), utile au-delà d'environ 90 000 emails/mois. Rétention des données : 30 jours.
Conseil de warm-up Resend pour un domaine neuf : ~150 emails le 1ᵉʳ jour, ~2 000/jour à J+7 (la brique
applique la règle plus prudente de 300–500/jour la 1ʳᵉ semaine pour le marketing).
