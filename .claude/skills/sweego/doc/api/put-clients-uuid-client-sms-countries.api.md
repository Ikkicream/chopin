# Update sms countries list for a given client

Source : https://learn.sweego.io/docs/sweego/put-clients-uuid-client-sms-countries

> Init server actions: client_sms_country

Update sms countries list for a given client

**PUT** `https://api.sweego.io/clients/{uuid_client}/sms/countries`

Init server actions: client_sms_country

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `country_list` | array<object (ClientSmsCountry)> | oui | minItems : `1` |
| `country_list[].country_ident` | string | oui | minLength : `2`; maxLength : `2`; pattern : `[a-zA-Z]{2}` |

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
