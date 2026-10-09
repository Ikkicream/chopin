# Get client current payment method

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-billing-payment-current

> Get client current payment method

Get client current payment method

**GET** `https://api.sweego.io/clients/{uuid_client}/billing/payment/current`

Get client current payment method

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `id` | string | oui |  |
| `type` | string | oui | An enumeration. — valeurs : `card`, `direct_debit`, `direct_debit_ach`, `direct_debit_bacs`, `transfer`, `transfer_automated`, `external` |
| `last_4_digits` | string |  |  |
| `expiration_date` | string |  |  |
| `brand` | string |  |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
