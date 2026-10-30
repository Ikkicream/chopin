# Retrieve user information by ID

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-mta-servers

> Init server actions: mta_client_server

Retrieve user information by ID

**GET** `https://api.sweego.io/clients/{uuid_client}/mta/servers`

Init server actions: mta_client_server

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (ClientMta)>

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
