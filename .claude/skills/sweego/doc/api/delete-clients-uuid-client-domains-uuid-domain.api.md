# Delete the domain with the given ID

Source : https://learn.sweego.io/docs/sweego/delete-clients-uuid-client-domains-uuid-domain

> Init server actions: client_domain

Delete the domain with the given ID

**DELETE** `https://api.sweego.io/clients/{uuid_client}/domains/{uuid_domain}`

Init server actions: client_domain

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_domain` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 204 — Successful Response

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
