# Retrieve Webhook by uuid

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-webhooks-webhook-uuid

> Retrieve webhook by uuid

Retrieve Webhook by uuid

**GET** `https://api.sweego.io/clients/{uuid_client}/webhooks/{webhook_uuid}`

Retrieve webhook by uuid

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `webhook_uuid` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `name` | string | oui |  |
| `endpoint_url` | string | oui |  |
| `enabled` | boolean |  | défaut : `true` |
| `uuid` | string (uuid4) | oui |  |
| `last_update_dt` | string (date-time) | oui |  |
| `success_count` | integer | oui |  |
| `fail_count` | integer | oui |  |
| `domains` | array<object (ClientWebhookDomain)> |  |  |
| `domains[].domain` | string | oui |  |
| `domains[].uuid` | string (uuid4) | oui |  |
| `event_types` | array<object> | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
