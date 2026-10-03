# Get sms countries list for a given client

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-sms-countries

> Init server actions: client_sms_country

Get sms countries list for a given client

**GET** `https://api.sweego.io/clients/{uuid_client}/sms/countries`

Init server actions: client_sms_country

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (ClientSmsCountry)>

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
