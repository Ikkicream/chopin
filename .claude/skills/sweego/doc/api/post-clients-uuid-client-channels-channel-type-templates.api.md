# Add template

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-channels-channel-type-templates

> Add template

Add template

**POST** `https://api.sweego.io/clients/{uuid_client}/channels/{channel_type}/templates`

Add template

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `channel_type` | string | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `name` | string | oui |  |
| `template` | string | oui |  |
| `uuid_sms_sender_short_name` | string (uuid4) |  |  |

### Réponses

#### 201 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `name` | string | oui |  |
| `template` | string | oui |  |
| `uuid` | string (uuid4) | oui |  |
| `uuid_sms_sender_short_name` | string (uuid4) |  |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
