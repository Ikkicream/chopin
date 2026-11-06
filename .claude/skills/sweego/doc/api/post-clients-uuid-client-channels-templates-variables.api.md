# Add template variable

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-channels-templates-variables

> Add template variable

Add template variable

**POST** `https://api.sweego.io/clients/{uuid_client}/channels/templates/variables`

Add template variable

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `name` | string | oui |  |

### Réponses

#### 201 — Successful Response

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
