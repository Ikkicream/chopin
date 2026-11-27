# Create token

Source : https://learn.sweego.io/docs/sweego/post-auth-token

> Create a token / refresh_token that can be used to access protected methods.

Create token

**POST** `https://api.sweego.io/auth/token`

Create a token / refresh_token that can be used to access protected methods.

Args:
request: request received
response: response returned to the caller
background_tasks: background task manager
oauth2_request_form: input model respecting oauth2 RFC

Returns:
Union [ SuccessResponse, ErrorResponse ]: Oauth2 compliant success response if authenticated successfully, otherwise oauth2 compliant error response.

Raises:
InvalidClientException: When client_id is not found or invalid credentials

### Corps de la requête (requis)

Content-Type : `application/x-www-form-urlencoded`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `client_id` | string |  |  |
| `client_secret` | string |  |  |
| `scope` | string |  |  |
| `refresh_token` | string (password) |  |  |
| `username` | string |  |  |
| `password` | string (password) |  |  |
| `subject_token` | string (password) |  |  |
| `subject_token_type` | string |  |  |
| `subject_issuer` | string |  |  |
| `requested_token_type` | string |  |  |
| `tenant` | string |  |  |
| `grant_type` | string | oui | pattern : `^(?:password|refresh_token|urn:ietf:params:oauth:grant-type:token-exchange)$` |

### Réponses

#### 200 — Successful Response

**Variante : SuccessResponse**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `access_token` | string | oui |  |
| `expires_in` | integer | oui |  |
| `refresh_token` | string | oui |  |
| `refresh_expires_in` | integer | oui |  |
| `token_type` | string | oui |  |
| `scope` | array<string> | oui |  |
| `sweego_client_id` | string | oui |  |
| `sweego_user_id` | string | oui |  |
| `sweego_user_mail` | string (email) |  |  |

**Variante : ErrorResponse**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `error` | string | oui | An enumeration. — valeurs : `invalid_request`, `invalid_client`, `invalid_grant`, `invalid_scope`, `unauthorized_client`, `unsupported_grant_type` |
| `error_description` | string | oui |  |
| `error_uri` | string |  |  |

#### 400 — Bad Request

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `error` | string |  | An enumeration. — valeurs : `invalid_request`, `invalid_client`, `invalid_grant`, `invalid_scope`, `unauthorized_client`, `unsupported_grant_type`; défaut : `"invalid_request"` |
| `error_description` | string | oui |  |
| `error_uri` | string |  |  |

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
