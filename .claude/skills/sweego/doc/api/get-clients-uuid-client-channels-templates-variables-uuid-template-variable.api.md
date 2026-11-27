# Get template variable by uuid

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-channels-templates-variables-uuid-template-variable

> Get template variable by uuid

Get template variable by uuid

**GET** `https://api.sweego.io/clients/{uuid_client}/channels/templates/variables/{uuid_template_variable}`

Get template variable by uuid

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_template_variable` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `name` | string | oui |  |
| `placeholder` | string | oui |  |
| `uuid` | string (uuid4) | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
