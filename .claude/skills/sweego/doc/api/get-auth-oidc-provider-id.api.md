# Init sign-in / sign-up flow to authenticates through external provider via OpenID connect.

Source : https://learn.sweego.io/docs/sweego/get-auth-oidc-provider-id

> Init OpenID Connect authentication workflow

Init sign-in / sign-up flow to authenticates through external provider via OpenID connect.

**GET** `https://api.sweego.io/auth/oidc/{provider_id}`

Init OpenID Connect authentication workflow

Args:
request: Fastapi automatic args
provider_id: for which provider the workflow should be init

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `provider_id` | string | oui |  |

**Body**

### Réponses

#### 307 — Successful Response

#### 401 — Unauthorized

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `error` | string |  | An enumeration. — valeurs : `invalid_request`, `invalid_client`, `invalid_grant`, `invalid_scope`, `unauthorized_client`, `unsupported_grant_type`; défaut : `"invalid_client"` |
| `error_description` | string | oui |  |
| `error_uri` | string |  |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
