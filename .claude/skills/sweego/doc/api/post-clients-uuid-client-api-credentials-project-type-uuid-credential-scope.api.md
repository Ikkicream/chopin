# Update the credential scope

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-api-credentials-project-type-uuid-credential-scope

> Server actions: credentials

Update the credential scope

**POST** `https://api.sweego.io/clients/{uuid_client}/api/credentials/{project_type}/{uuid_credential}/scope`

Server actions: credentials

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_credential` | string (uuid4) | oui |  |
| `project_type` | string | oui |  |
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
