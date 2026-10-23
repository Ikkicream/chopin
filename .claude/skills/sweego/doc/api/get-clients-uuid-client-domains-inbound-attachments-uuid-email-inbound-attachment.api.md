# Download email inbound attachment

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-domains-inbound-attachments-uuid-email-inbound-attachment

> Download email inbound attachment

Download email inbound attachment

**GET** `https://api.sweego.io/clients/{uuid_client}/domains/inbound/attachments/{uuid_email_inbound_attachment}`

Download email inbound attachment

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_email_inbound_attachment` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

Type : {}

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
