# OpenID connect callback

Source : https://learn.sweego.io/docs/sweego/get-auth-oidc-provider-id-callback

> Oidc callback route called by external provider at the end of the authentication flow

OpenID connect callback

**GET** `https://api.sweego.io/auth/oidc/{provider_id}/callback`

Oidc callback route called by external provider at the end of the authentication flow

Args:
request: Fastapi automatic args
background_tasks: Background tasks
provider_id: for which provider the flow should be init
state: openid state
session_uuid: (cookie) identify the current oidc login session
code: [on success] openid code
error: [on failure] error string
scope: openid scope (provided only for Google)
authuser: openid authuser (provided only for Google)
prompt: openid prompt (provided only for Google)

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `provider_id` | string | oui |  |
| `state` | string | oui |  |
| `code` | string |  |  |
| `error` | string |  |  |
| `error_description` | string |  |  |
| `scope` | string |  |  |
| `authuser` | integer |  |  |
| `prompt` | string |  |  |
| `session_uuid` | string (uuid4) | oui |  |

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
