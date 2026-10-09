# Get template list (supports filtering)

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-channels-channel-type-templates

> Get template list (supports filtering)

Get template list (supports filtering)

**GET** `https://api.sweego.io/clients/{uuid_client}/channels/{channel_type}/templates`

Get template list (supports filtering)

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `channel_type` | string | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (ClientTemplateResponse)>

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
