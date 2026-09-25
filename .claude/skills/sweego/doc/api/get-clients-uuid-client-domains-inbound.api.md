# Get email inbound list

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-domains-inbound

> Init server actions: client_domain

Get email inbound list

**GET** `https://api.sweego.io/clients/{uuid_client}/domains/inbound`

Init server actions: client_domain

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (ClientEmailInboundGetBrief)>

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
