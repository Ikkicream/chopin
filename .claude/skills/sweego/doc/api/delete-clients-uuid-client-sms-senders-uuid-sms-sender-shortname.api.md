# Delete a given sms sender shortname

Source : https://learn.sweego.io/docs/sweego/delete-clients-uuid-client-sms-senders-uuid-sms-sender-shortname

> Delete sms sender shortname

Delete a given sms sender shortname

**DELETE** `https://api.sweego.io/clients/{uuid_client}/sms/senders/{uuid_sms_sender_shortname}`

Delete sms sender shortname

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_sms_sender_shortname` | string (uuid4) | oui |  |
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
