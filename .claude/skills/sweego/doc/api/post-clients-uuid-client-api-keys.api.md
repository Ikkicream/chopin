# Create the api_key with the given info

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-api-keys

> Init server actions: client_api_key

Create the api_key with the given info

**POST** `https://api.sweego.io/clients/{uuid_client}/api/keys`

Init server actions: client_api_key

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `scope` | string | oui |  |
| `enabled` | boolean |  | défaut : `true` |
| `display_name` | string | oui |  |

### Réponses

#### 201 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid` | string (uuid4) | oui |  |
| `api_key` | string | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
