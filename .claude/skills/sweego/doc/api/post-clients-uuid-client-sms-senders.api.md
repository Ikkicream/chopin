# Create a sms sender shortname

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-sms-senders

> Create a new sms sender shortname

Create a sms sender shortname

**POST** `https://api.sweego.io/clients/{uuid_client}/sms/senders`

Create a new sms sender shortname

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `short_name` | string | oui | minLength : `3`; maxLength : `11`; pattern : `[a-z0-9A-Z]+` |

### Réponses

#### 201 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `short_name` | string |  | minLength : `3`; maxLength : `11`; pattern : `[a-z0-9A-Z]+` |
| `short_name_state` | integer |  | Enum representing the state of validation of a shortname — valeurs : `0`, `1`, `2`, `3` |
| `client_sms_sender_id` | integer |  | minimum : `0`; maximum : `2147483647` |
| `id` | integer |  | minimum : `0`; maximum : `2147483647` |
| `uuid` | string (uuid4) |  |  |
| `creation_dt` | string (date-time) |  |  |
| `last_update_dt` | string (date-time) |  |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
