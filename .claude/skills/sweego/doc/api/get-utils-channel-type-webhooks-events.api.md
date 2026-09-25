# Retrieve available webhooks by channel id

Source : https://learn.sweego.io/docs/sweego/get-utils-channel-type-webhooks-events

> Retrieve available webhooks by channel id

Retrieve available webhooks by channel id

**GET** `https://api.sweego.io/utils/{channel_type}/webhooks/events`

Retrieve available webhooks by channel id

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `channel_type` | WebhookChannelType | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (WebhookEventType)>

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
