# Delete the given image

Source : https://learn.sweego.io/docs/sweego/delete-clients-uuid-client-hosting-images-image-name

> Delete the given image

Delete the given image

**DELETE** `https://api.sweego.io/clients/{uuid_client}/hosting/images/{image_name}`

Delete the given image

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `image_name` | string | oui |  |
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
