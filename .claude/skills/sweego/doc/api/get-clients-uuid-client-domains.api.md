# Get domain list for a given client (support filtering)

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-domains

> Init server actions: client_domain

Get domain list for a given client (support filtering)

**GET** `https://api.sweego.io/clients/{uuid_client}/domains`

Init server actions: client_domain

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |
| `is_verified` | boolean |  |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (ClientDomain)>

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
