# Get client payment management portal

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-billing-payment-portal

> Get client payment management portal

Get client payment management portal

**GET** `https://api.sweego.io/clients/{uuid_client}/billing/payment/portal`

Get client payment management portal

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `url` | string (uri) | oui | minLength : `1`; maxLength : `2083` |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
