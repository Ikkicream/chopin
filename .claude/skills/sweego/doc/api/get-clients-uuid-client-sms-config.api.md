# Get current SMS sender test config

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-sms-config

> Get sms config

Get current SMS sender test config

**GET** `https://api.sweego.io/clients/{uuid_client}/sms/config`

Get sms config

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `bat_country_code` | string |  | maxLength : `3` |
| `bat_phone_number` | string |  | minLength : `7`; maxLength : `25` |
| `tracking_click_enabled` | boolean | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
