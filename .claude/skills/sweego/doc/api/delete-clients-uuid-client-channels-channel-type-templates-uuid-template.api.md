# Delete template

Source : https://learn.sweego.io/docs/sweego/delete-clients-uuid-client-channels-channel-type-templates-uuid-template

> Delete template

Delete template

**DELETE** `https://api.sweego.io/clients/{uuid_client}/channels/{channel_type}/templates/{uuid_template}`

Delete template

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `channel_type` | string | oui |  |
| `uuid_template` | string (uuid4) | oui |  |
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
