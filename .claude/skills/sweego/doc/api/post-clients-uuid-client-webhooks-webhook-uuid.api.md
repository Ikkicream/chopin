# Update Client Webhook

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-webhooks-webhook-uuid

> Update client webhook

Update Client Webhook

**POST** `https://api.sweego.io/clients/{uuid_client}/webhooks/{webhook_uuid}`

Update client webhook

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `webhook_uuid` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `name` | string |  |  |
| `endpoint_url` | string |  |  |
| `enabled` | boolean |  |  |
| `email` | object (ClientWebhookUpdateChannelEmail) |  |  |
| `email.events` | object (ClientWebhookEventUpdate) |  |  |
| `email.events.delete` | array<integer> |  |  |
| `email.events.add` | array<integer> |  |  |
| `email.domains` | object (ClientWebhookDomainUpdate) |  |  |
| `email.domains.delete` | array<string (uuid4)> |  |  |
| `email.domains.add` | array<string (uuid4)> |  |  |
| `sms` | object (ClientWebhookUpdateChannelBase) |  |  |
| `sms.events` | object (ClientWebhookEventUpdate) |  |  |
| `sms.events.delete` | array<integer> |  |  |
| `sms.events.add` | array<integer> |  |  |

### Réponses

#### 204 — Successful Response

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
