# Update an email inbound domain

Source : https://learn.sweego.io/docs/sweego/put-clients-uuid-client-domains-inbound-uuid-email-inbound

> Server actions: client_email_inbound

Update an email inbound domain

**PUT** `https://api.sweego.io/clients/{uuid_client}/domains/inbound/{uuid_email_inbound}`

Server actions: client_email_inbound

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_email_inbound` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `name` | string |  | maxLength : `255` |
| `webhook_url` | string (uri) |  | minLength : `1`; maxLength : `2083` |

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `id` | integer | oui | minimum : `0`; maximum : `2147483647` |
| `uuid` | string (uuid4) | oui |  |
| `creation_dt` | string (date-time) | oui |  |
| `last_update_dt` | string (date-time) |  |  |
| `name` | string | oui | maxLength : `255` |
| `webhook_url` | string (uri) | oui | minLength : `1`; maxLength : `2083` |
| `subdomain` | string |  | minLength : `1`; maxLength : `63` |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
