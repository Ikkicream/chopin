# Update a user

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-users-uuid-user

> Alias for server actions : user

Update a user

**POST** `https://api.sweego.io/clients/{uuid_client}/users/{uuid_user}`

Alias for server actions : user

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_user` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `first_name` | string |  | minLength : `1` |
| `last_name` | string |  | minLength : `1` |
| `job_title` | string |  | minLength : `1` |
| `phone_number` | string |  | minLength : `1` |

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `first_name` | string |  | minLength : `1` |
| `last_name` | string |  | minLength : `1` |
| `job_title` | string |  | minLength : `1` |
| `phone_number` | string |  | minLength : `1` |
| `is_verified` | boolean | oui |  |
| `onboarded` | boolean | oui |  |

#### 409 — You can't edit this property once the onboarding process is completed.

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
