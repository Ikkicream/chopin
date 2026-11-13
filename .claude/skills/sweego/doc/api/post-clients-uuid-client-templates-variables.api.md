# Add template variable. Deprecated : migrated to '/clients/{uuid_client}/channels/templates/variables'.

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-templates-variables

> Add template variable. Deprecated : migrated to '/clients/{uuid_client}/channels/templates/variables'.

Add template variable. Deprecated : migrated to '/clients/{uuid_client}/channels/templates/variables'.

**POST** `https://api.sweego.io/clients/{uuid_client}/templates/variables`

Add template variable. Deprecated : migrated to '/clients/{uuid_client}/channels/templates/variables'.

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

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
