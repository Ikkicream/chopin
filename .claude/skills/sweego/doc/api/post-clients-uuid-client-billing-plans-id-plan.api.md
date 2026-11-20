# Init subscription workflow, returns URL to uses for payment

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-billing-plans-id-plan

> Get client plan

Init subscription workflow, returns URL to uses for payment

**POST** `https://api.sweego.io/clients/{uuid_client}/billing/plans/{id_plan}`

Get client plan

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `id_plan` | string | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `coupon` | string |  |  |

### Réponses

#### 201 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `payment_url` | string (uri) |  | minLength : `1`; maxLength : `2083` |
| `created_at` | string (date-time) | oui |  |
| `renew_automatically` | boolean | oui |  |
| `starts_at` | string (date-time) | oui |  |
| `renews_at` | string (date-time) |  |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
