# Get client credit

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-billing-credits-credit-type

> Get client current payment method

Get client credit

**GET** `https://api.sweego.io/clients/{uuid_client}/billing/credits/{credit_type}`

Get client current payment method

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `credit_type` | string | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `type` | string | oui | An enumeration. — valeurs : `sms` |
| `amount` | number | oui |  |
| `termination_date` | string (date) |  |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
