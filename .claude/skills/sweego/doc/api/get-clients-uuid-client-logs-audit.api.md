# Get action log list for a given client (support filtering)

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-logs-audit

> Init server actions: client_domain

Get action log list for a given client (support filtering)

**GET** `https://api.sweego.io/clients/{uuid_client}/logs/audit`

Init server actions: client_domain

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |
| `start_date` | string (date) | oui |  |
| `end_date` | string (date) |  |  |
| `size` | integer |  |  |
| `offset` | integer |  |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `total_results` | integer | oui |  |
| `data` | array<object (ClientAuditLog)> | oui |  |
| `data[].resource_type_id` | integer | oui | An enumeration. — valeurs : `1`, `2`, `3`, `4`, `5`, `6`, `7`, `8`, `9`, `10`, `11`, `12`, `13` |
| `data[].action_id` | integer | oui | An enumeration. — valeurs : `1`, `2`, `3` |
| `data[].user_uuid` | string (uuid4) |  |  |
| `data[].ip_address` | string |  |  |
| `data[].data` | object (Data) |  | défaut : `{}` |
| `data[].log_dt` | string (date-time) | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
