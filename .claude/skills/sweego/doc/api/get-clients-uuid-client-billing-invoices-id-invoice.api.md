# Get client invoice

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-billing-invoices-id-invoice

> Get client invoice

Get client invoice

**GET** `https://api.sweego.io/clients/{uuid_client}/billing/invoices/{id_invoice}`

Get client invoice

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `id_invoice` | string | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : {}

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
