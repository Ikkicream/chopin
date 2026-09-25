# Get email inbound info

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-domains-inbound-uuid-email-inbound

> Init server actions: client_domain

Get email inbound info

**GET** `https://api.sweego.io/clients/{uuid_client}/domains/inbound/{uuid_email_inbound}`

Init server actions: client_domain

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_email_inbound` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `secret_key` | string | oui |  |
| `verified` | boolean | oui |  |
| `domain` | string | oui |  |
| `uuid_domain` | string (uuid4) | oui |  |
| `id` | integer | oui | minimum : `0`; maximum : `2147483647` |
| `uuid` | string (uuid4) | oui |  |
| `creation_dt` | string (date-time) | oui |  |
| `last_update_dt` | string (date-time) |  |  |
| `name` | string | oui | maxLength : `255` |
| `webhook_url` | string (uri) | oui | minLength : `1`; maxLength : `2083` |
| `subdomain` | string |  | minLength : `1`; maxLength : `63` |
| `event_number` | integer |  | défaut : `666` |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
