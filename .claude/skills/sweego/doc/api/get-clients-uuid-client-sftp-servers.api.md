# Retrieve user information by ID

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-sftp-servers

> Init server actions: client_sftp

Retrieve user information by ID

**GET** `https://api.sweego.io/clients/{uuid_client}/sftp/servers`

Init server actions: client_sftp

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (ClientSftp)>

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
