# Get template variable list (supports filtering). Deprecated : migrated to '/clients/{uuid_client}/channels/templates/variables.

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-channels-channel-type-templates-variables

> Get template variable list (supports filtering). Deprecated : migrated to '/clients/{uuid_client}/channels/templates/variables.

Get template variable list (supports filtering). Deprecated : migrated to '/clients/{uuid_client}/channels/templates/variables.

**GET** `https://api.sweego.io/clients/{uuid_client}/channels/{channel_type}/templates/variables`

Get template variable list (supports filtering). Deprecated : migrated to '/clients/{uuid_client}/channels/templates/variables.

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
