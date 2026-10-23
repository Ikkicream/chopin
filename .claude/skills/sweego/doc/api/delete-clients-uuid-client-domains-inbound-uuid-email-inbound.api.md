# Delete a given email inbound

Source : https://learn.sweego.io/docs/sweego/delete-clients-uuid-client-domains-inbound-uuid-email-inbound

> Init server actions: client_domain

Delete a given email inbound

**DELETE** `https://api.sweego.io/clients/{uuid_client}/domains/inbound/{uuid_email_inbound}`

Init server actions: client_domain

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_email_inbound` | string (uuid4) | oui |  |
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
