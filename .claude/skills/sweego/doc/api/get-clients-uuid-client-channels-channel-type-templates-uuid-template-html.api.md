# Convert given template to html format. Only available for 'email' channel.

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-channels-channel-type-templates-uuid-template-html

> Convert given template to html format. Only available for 'email' channel.

Convert given template to html format. Only available for 'email' channel.

**GET** `https://api.sweego.io/clients/{uuid_client}/channels/{channel_type}/templates/{uuid_template}/html`

Convert given template to html format. Only available for 'email' channel.

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
| `template` | string | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
