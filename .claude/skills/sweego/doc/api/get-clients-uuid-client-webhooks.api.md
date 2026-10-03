# Retrieve Client Setup Webhooks

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-webhooks

> Retrieve all webhooks

Retrieve Client Setup Webhooks

**GET** `https://api.sweego.io/clients/{uuid_client}/webhooks`

Retrieve all webhooks

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (ClientWebhookResponse)>

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
