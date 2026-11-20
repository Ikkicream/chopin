# Update Client Webhook Status

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-webhooks-webhook-uuid-enabled

> Update client webhook status

Update Client Webhook Status

**POST** `https://api.sweego.io/clients/{uuid_client}/webhooks/{webhook_uuid}/enabled`

Update client webhook status

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `webhook_uuid` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `enabled` | boolean | oui |  |

### Réponses

#### 204 — Successful Response

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
