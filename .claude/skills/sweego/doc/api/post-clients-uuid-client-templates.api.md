# Add template. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates'.

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-templates

> Add template. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates'.

Add template. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates'.

**POST** `https://api.sweego.io/clients/{uuid_client}/templates`

This endpoint has been deprecated and may be replaced or removed in future versions of the API.

Add template. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates'.

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
