# Init credit workflow

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-billing-credits-credit-type

> Get client current payment method

Init credit workflow

**POST** `https://api.sweego.io/clients/{uuid_client}/billing/credits/{credit_type}`

Get client current payment method

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `credit_type` | string | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `amount` | integer | oui |  |

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `payment_url` | string (uri) | oui | minLength : `1`; maxLength : `2083` |
| `invoice_id` | string | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
