# Update client SMS test config

Source : https://learn.sweego.io/docs/sweego/put-clients-uuid-client-sms-config

> Update sms test number config

Update client SMS test config

**PUT** `https://api.sweego.io/clients/{uuid_client}/sms/config`

Update sms test number config

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `phone_number` | string |  |  |
| `country_code` | string |  | maxLength : `3` |
| `tracking_click_enabled` | boolean |  |  |

### Réponses

#### 204 — Successful Response

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
