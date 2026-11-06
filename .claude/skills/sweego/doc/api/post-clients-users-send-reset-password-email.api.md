# Send a mail to this user with instructions to reset his password

Source : https://learn.sweego.io/docs/sweego/post-clients-users-send-reset-password-email

> Alias for server actions : user

Send a mail to this user with instructions to reset his password

**POST** `https://api.sweego.io/clients/users/send-reset-password-email`

Alias for server actions : user

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `email` | string (email) | oui |  |

### Réponses

#### 204 — Successful Response

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
