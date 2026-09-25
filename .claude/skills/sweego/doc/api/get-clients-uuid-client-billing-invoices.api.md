# Get client invoices

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-billing-invoices

> Get client invoices

Get client invoices

**GET** `https://api.sweego.io/clients/{uuid_client}/billing/invoices`

Get client invoices

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (ClientBillingInvoice)>

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
