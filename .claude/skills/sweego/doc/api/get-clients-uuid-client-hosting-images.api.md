# Get image list

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-hosting-images

> Get image list

Get image list

**GET** `https://api.sweego.io/clients/{uuid_client}/hosting/images`

Get image list

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |
| `order` | string |  |  |
| `page` | integer |  |  |
| `page_size` | integer |  |  |
| `search` | string |  |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (ClientImageResponse)>

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
