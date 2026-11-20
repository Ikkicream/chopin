# Get credential information

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-api-credentials-project-type-uuid-credentials

> Server actions: credentials

Get credential information

**GET** `https://api.sweego.io/clients/{uuid_client}/api/credentials/{project_type}/{uuid_credentials}`

Server actions: credentials

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_credentials` | string (uuid4) | oui |  |
| `project_type` | string | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `scope` | string | oui |  |
| `enabled` | boolean |  | défaut : `true` |
| `display_name` | string | oui | maxLength : `50` |
| `uuid` | string (uuid4) | oui |  |
| `creation_date` | string (date-time) | oui |  |
| `username` | string | oui |  |
| `restricted_domain_list` | array<string (uuid4)> | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
