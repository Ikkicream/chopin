# Send verify email to given client

Source : https://learn.sweego.io/docs/sweego/post-clients-users-send-verify-email

> Alias for server actions : user

Send verify email to given client

**POST** `https://api.sweego.io/clients/users/send-verify-email`

Alias for server actions : user

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `email` | string (email) | oui |  |

### Réponses

#### 204 — Successful Response

#### 410 — Email already verified, no further action required.

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
