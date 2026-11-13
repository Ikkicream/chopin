# Create Client Webhook

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-webhooks

> Create client webhook

Create Client Webhook

**POST** `https://api.sweego.io/clients/{uuid_client}/webhooks`

Create client webhook

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `name` | string | oui |  |
| `endpoint_url` | string | oui |  |
| `enabled` | boolean |  | défaut : `true` |
| `events` | array<object (ClientWebhookCreateEmail) \| object (ClientWebhookEventCreateBase)> | oui | minItems : `1` |

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `name` | string | oui |  |
| `endpoint_url` | string | oui |  |
| `enabled` | boolean |  | défaut : `true` |
| `uuid` | string (uuid4) | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
