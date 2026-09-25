# Delete template variable

Source : https://learn.sweego.io/docs/sweego/delete-clients-uuid-client-channels-templates-variables-uuid-template-variable

> Delete template variable

Delete template variable

**DELETE** `https://api.sweego.io/clients/{uuid_client}/channels/templates/variables/{uuid_template_variable}`

Delete template variable

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_template_variable` | string (uuid4) | oui |  |
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
