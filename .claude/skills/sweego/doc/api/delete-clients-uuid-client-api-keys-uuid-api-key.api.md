# Delete the api_key with the given ID

Source : https://learn.sweego.io/docs/sweego/delete-clients-uuid-client-api-keys-uuid-api-key

> Init server actions: client_api_key

Delete the api_key with the given ID

**DELETE** `https://api.sweego.io/clients/{uuid_client}/api/keys/{uuid_api_key}`

Init server actions: client_api_key

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_api_key` | string (uuid4) | oui |  |
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
