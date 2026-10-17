# Convert given template to html format. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/{uuid_template}/html'.

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-templates-uuid-template-html

> Convert given template to html format. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/{uuid_template}/html'.

Convert given template to html format. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/{uuid_template}/html'.

**GET** `https://api.sweego.io/clients/{uuid_client}/templates/{uuid_template}/html`

This endpoint has been deprecated and may be replaced or removed in future versions of the API.

Convert given template to html format. Deprecated : migrated to '/clients/{uuid_client}/channels/email/templates/{uuid_template}/html'.

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
