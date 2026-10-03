# Get api_key list for a given client (support filtering)

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-api-keys

> Init server actions: client_api_key

Get api_key list for a given client (support filtering)

**GET** `https://api.sweego.io/clients/{uuid_client}/api/keys`

Init server actions: client_api_key

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |
| `client_id` | integer |  |  |
| `api_key_hash` | string |  |  |
| `id` | integer |  |  |
| `creation_dt` | string (date-time) |  |  |
| `last_update_dt` | string (date-time) |  |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (ApiKeyListResponse)>

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
