# Delete Client Webhook

Source : https://learn.sweego.io/docs/sweego/delete-clients-uuid-client-webhooks-webhook-uuid

> Delete client webhook

Delete Client Webhook

**DELETE** `https://api.sweego.io/clients/{uuid_client}/webhooks/{webhook_uuid}`

Delete client webhook

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `webhook_uuid` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 204 — Successful Response

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
