# Get api_key

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-api-keys-uuid-api-key

> Init server actions: client_api_key

Get api_key

**GET** `https://api.sweego.io/clients/{uuid_client}/api/keys/{uuid_api_key}`

Init server actions: client_api_key

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_api_key` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid` | string (uuid4) | oui |  |
| `display_name` | string | oui |  |
| `enabled` | boolean | oui |  |
| `creation_date` | string (date-time) | oui |  |
| `scope` | string | oui |  |
| `restricted_domain_list` | array<string (uuid4)> | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
