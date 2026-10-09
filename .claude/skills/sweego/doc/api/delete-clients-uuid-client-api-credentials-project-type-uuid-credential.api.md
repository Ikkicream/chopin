# Delete the credentials with the given UUID

Source : https://learn.sweego.io/docs/sweego/delete-clients-uuid-client-api-credentials-project-type-uuid-credential

> Server actions: credentials

Delete the credentials with the given UUID

**DELETE** `https://api.sweego.io/clients/{uuid_client}/api/credentials/{project_type}/{uuid_credential}`

Server actions: credentials

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_credential` | string (uuid4) | oui |  |
| `project_type` | string | oui |  |
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
