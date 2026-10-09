# Create the credentials with the given info

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-api-credentials-project-type

> Server actions: credentials

Create the credentials with the given info

**POST** `https://api.sweego.io/clients/{uuid_client}/api/credentials/{project_type}`

Server actions: credentials

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `project_type` | string | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `scope` | string | oui |  |
| `enabled` | boolean |  | défaut : `true` |
| `display_name` | string | oui | maxLength : `50` |

### Réponses

#### 201 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `enabled` | boolean |  | défaut : `true` |
| `display_name` | string | oui | maxLength : `50` |
| `uuid` | string (uuid4) | oui |  |
| `username` | string | oui |  |
| `password` | string | oui |  |
| `scope` | string | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
