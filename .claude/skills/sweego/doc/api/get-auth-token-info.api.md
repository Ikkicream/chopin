# Get token info

Source : https://learn.sweego.io/docs/sweego/get-auth-token-info

> Get token info

Get token info

**GET** `https://api.sweego.io/auth/token/info`

Get token info

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `exp` | string (date-time) | oui |  |
| `iat` | string (date-time) | oui |  |
| `typ` | string | oui |  |
| `eml` | string |  |  |
| `rqac` | array<string> |  |  |

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
