# Update template

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-channels-channel-type-templates-uuid-template

> Update template

Update template

**POST** `https://api.sweego.io/clients/{uuid_client}/channels/{channel_type}/templates/{uuid_template}`

Update template

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `channel_type` | string | oui |  |
| `uuid_template` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `name` | string |  |  |
| `template` | string |  |  |
| `template_type` | string |  | Enum that represents all channels that can have templates  — valeurs : `email`, `sms` |
| `client_sms_sender_short_name_id` | integer |  | minimum : `0`; maximum : `2147483647` |
| `uuid_sms_sender_short_name` | string (uuid4) |  |  |

### Réponses

#### 204 — Successful Response

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
