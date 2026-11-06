# Check email inbound dns records

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-domains-inbound-uuid-email-inbound-check

> Verify DNS record regarding email inbound

Check email inbound dns records

**POST** `https://api.sweego.io/clients/{uuid_client}/domains/inbound/{uuid_email_inbound}/check`

Verify DNS record regarding email inbound

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_email_inbound` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid` | string (uuid4) |  |  |
| `verified` | boolean | oui |  |
| `error_string` | string | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
