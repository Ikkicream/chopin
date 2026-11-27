# Add an email inbound domain

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-domains-inbound

> Server actions: client_billing

Add an email inbound domain

**POST** `https://api.sweego.io/clients/{uuid_client}/domains/inbound`

Server actions: client_billing

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `name` | string | oui | maxLength : `255` |
| `webhook_url` | string (uri) | oui | minLength : `1`; maxLength : `2083` |
| `subdomain` | string |  | minLength : `1`; maxLength : `63` |
| `uuid_domain` | string (uuid4) | oui |  |

### Réponses

#### 201 — Successful Response

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
