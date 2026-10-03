# Get template by uuid

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-channels-channel-type-templates-uuid-template

> This method retrieves the template in Chamaileon format (our e-mail builder).

Get template by uuid

**GET** `https://api.sweego.io/clients/{uuid_client}/channels/{channel_type}/templates/{uuid_template}`

This method retrieves the template in Chamaileon format (our e-mail builder).

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `channel_type` | string | oui |  |
| `uuid_template` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

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
