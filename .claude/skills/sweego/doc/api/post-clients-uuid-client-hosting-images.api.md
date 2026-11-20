# Upload an image from base64 or from an URL

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-hosting-images

> Wrapper: scaleway

Upload an image from base64 or from an URL

**POST** `https://api.sweego.io/clients/{uuid_client}/hosting/images`

Wrapper: scaleway

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `image` | string (binary) |  |  |
| `url` | string (uri) |  | minLength : `1`; maxLength : `2083` |
| `name` | string | oui |  |

### Réponses

#### 201 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `name` | string | oui |  |
| `src` | string (uri) | oui | minLength : `1`; maxLength : `2083` |
| `_id` | string | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
