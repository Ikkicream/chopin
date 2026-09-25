# Get user for a given client

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-users-uuid-user

> Alias for server actions : user

Get user for a given client

**GET** `https://api.sweego.io/clients/{uuid_client}/users/{uuid_user}`

Alias for server actions : user

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_user` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `first_name` | string |  | minLength : `1` |
| `last_name` | string |  | minLength : `1` |
| `job_title` | string |  | minLength : `1` |
| `phone_number` | string |  | minLength : `1` |
| `is_verified` | boolean | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
