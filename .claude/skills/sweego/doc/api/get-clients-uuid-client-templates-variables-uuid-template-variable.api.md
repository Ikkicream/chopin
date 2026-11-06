# Get template variable by uuid. Deprecated : migrated to '/clients/{uuid_client}/channels/templates/variables/{uuid_template_variable}'.

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-templates-variables-uuid-template-variable

> Get template variable by uuid. Deprecated : migrated to '/clients/{uuid_client}/channels/templates/variables/{uuid_template_variable}'.

Get template variable by uuid. Deprecated : migrated to '/clients/{uuid_client}/channels/templates/variables/{uuid_template_variable}'.

**GET** `https://api.sweego.io/clients/{uuid_client}/templates/variables/{uuid_template_variable}`

Get template variable by uuid. Deprecated : migrated to '/clients/{uuid_client}/channels/templates/variables/{uuid_template_variable}'.

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |
| `uuid_template_variable` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 308 — Successful Response

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
