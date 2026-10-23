# Get Client Template restriction. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/restriction'.

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-templates-restriction

> Get Client Template restriction. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/restriction'.

Get Client Template restriction. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/restriction'.

**GET** `https://api.sweego.io/clients/{uuid_client}/templates/restriction`

This endpoint has been deprecated and may be replaced or removed in future versions of the API.

Get Client Template restriction. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/restriction'.

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
