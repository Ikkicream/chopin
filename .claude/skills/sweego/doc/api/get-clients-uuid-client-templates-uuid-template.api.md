# Get template by uuid. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/{uuid_template}'.

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-templates-uuid-template

> This method retrieves the template in Chamaileon format (our e-mail builder).

Get template by uuid. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/{uuid_template}'.

**GET** `https://api.sweego.io/clients/{uuid_client}/templates/{uuid_template}`

This endpoint has been deprecated and may be replaced or removed in future versions of the API.

This method retrieves the template in Chamaileon format (our e-mail builder).

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
