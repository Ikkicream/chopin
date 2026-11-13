# Get credentials list for a given client (support filtering)

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-api-credentials-project-type

> Server actions: credentials

Get credentials list for a given client (support filtering)

**GET** `https://api.sweego.io/clients/{uuid_client}/api/credentials/{project_type}`

Server actions: credentials

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `project_type` | string | oui |  |
| `uuid_client` | string (uuid4) | oui |  |
| `enabled` | boolean |  |  |
| `display_name` | string |  |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (CredentialGetListResponse)>

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
