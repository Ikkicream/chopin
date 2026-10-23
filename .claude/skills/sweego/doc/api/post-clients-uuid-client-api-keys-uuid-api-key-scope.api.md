# Enable / disable the given api key

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-api-keys-uuid-api-key-scope

> Init server actions: client_api_key

Enable / disable the given api key

**POST** `https://api.sweego.io/clients/{uuid_client}/api/keys/{uuid_api_key}/scope`

Init server actions: client_api_key

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_api_key` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `scope` | string | oui |  |

### Réponses

#### 204 — Successful Response

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
