# Get client quotas

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-billing-quotas

> Get client quotas

Get client quotas

**GET** `https://api.sweego.io/clients/{uuid_client}/billing/quotas`

Get client quotas

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `email` | object (ChannelConsumptionQuota) | oui |  |
| `email.consumed` | integer | oui |  |
| `email.quota` | integer | oui |  |
| `email.burst_quota` | integer |  |  |
| `email.period` | string | oui | An enumeration. — valeurs : `day`, `month`, `year` |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
