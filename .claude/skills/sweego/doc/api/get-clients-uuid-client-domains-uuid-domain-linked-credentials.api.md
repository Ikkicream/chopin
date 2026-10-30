# Get list of credentials and api key that have this domain as 'restriction'

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-domains-uuid-domain-linked-credentials

> Init server actions: client_domain

Get list of credentials and api key that have this domain as 'restriction'

**GET** `https://api.sweego.io/clients/{uuid_client}/domains/{uuid_domain}/linked-credentials`

Init server actions: client_domain

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_domain` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `linked_credentials_list` | array<object (AssociatedCredential)> | oui |  |
| `linked_credentials_list[].uuid` | string (uuid4) | oui |  |
| `linked_credentials_list[].display_name` | string | oui |  |
| `linked_credentials_list[].project_type` | string | oui | An enumeration. — valeurs : `api_key`, `billing`, `client_account`, `credentials`, `domain`, `email_inbound_logs`, `email_inbound_stats`, `logs`, `sftp`, `stats`, `template`, `user`, `webhook`, `discord`, `mail`, `slack`, `sms`, `smtp`, `telegram` |
| `linked_api_key_list` | array<object (AssociatedApiKey)> | oui |  |
| `linked_api_key_list[].uuid` | string (uuid4) | oui |  |
| `linked_api_key_list[].display_name` | string | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
