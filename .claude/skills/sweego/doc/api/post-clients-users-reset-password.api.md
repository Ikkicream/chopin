# Reset user (given in token itself) password with action-token given in email

Source : https://learn.sweego.io/docs/sweego/post-clients-users-reset-password

> Alias for server actions : user

Reset user (given in token itself) password with action-token given in email

**POST** `https://api.sweego.io/clients/users/reset-password`

Alias for server actions : user

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `password` | string (password) | oui |  |

### Réponses

#### 204 — Successful Response

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
