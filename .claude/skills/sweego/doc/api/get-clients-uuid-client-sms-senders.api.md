# Get sms sender shortname list for a given client

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-sms-senders

> Get list of sms sender shortname

Get sms sender shortname list for a given client

**GET** `https://api.sweego.io/clients/{uuid_client}/sms/senders`

Get list of sms sender shortname

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (ClientSmsSenderShortNameResponse)>

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
