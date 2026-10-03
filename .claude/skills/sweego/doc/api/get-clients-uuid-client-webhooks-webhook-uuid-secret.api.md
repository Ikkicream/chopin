# Get signature secret key for a webhook

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-webhooks-webhook-uuid-secret

> Update client webhook status

Get signature secret key for a webhook

**GET** `https://api.sweego.io/clients/{uuid_client}/webhooks/{webhook_uuid}/secret`

Update client webhook status

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
| `secret_key` | string | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
