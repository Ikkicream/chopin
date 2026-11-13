# Get Client Template restriction.

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-channels-channel-type-templates-restriction

> Get Client Template restriction.

Get Client Template restriction.

**GET** `https://api.sweego.io/clients/{uuid_client}/channels/{channel_type}/templates/restriction`

Get Client Template restriction.

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `channel_type` | string | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | string |  |  |
| `is_restricted` | boolean | oui |  |
| `max_limit` | integer | oui |  |
| `current_value` | integer | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
