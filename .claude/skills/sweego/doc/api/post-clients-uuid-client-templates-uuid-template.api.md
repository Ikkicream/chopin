# Update template. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/{uuid_template}'.

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-templates-uuid-template

> Update template. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/{uuid_template}'.

Update template. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/{uuid_template}'.

**POST** `https://api.sweego.io/clients/{uuid_client}/templates/{uuid_template}`

This endpoint has been deprecated and may be replaced or removed in future versions of the API.

Update template. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/{uuid_template}'.

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |
| `uuid_template` | string (uuid4) | oui |  |

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
