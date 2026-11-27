# Check manually a domain and returns it's verified status

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-domains-uuid-domain-check

> Init server actions: client_domain

Check manually a domain and returns it's verified status

**POST** `https://api.sweego.io/clients/{uuid_client}/domains/{uuid_domain}/check`

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
| `spf_record` | object (ClientVerifiedRecord) | oui |  |
| `spf_record.uuid` | string (uuid4) |  |  |
| `spf_record.verified` | boolean | oui |  |
| `spf_record.error_string` | string | oui |  |
| `dkim_record` | object (ClientVerifiedRecord) | oui |  |
| `dkim_record.uuid` | string (uuid4) |  |  |
| `dkim_record.verified` | boolean | oui |  |
| `dkim_record.error_string` | string | oui |  |
| `dmarc_record` | object (ClientVerifiedRecord) |  |  |
| `dmarc_record.uuid` | string (uuid4) |  |  |
| `dmarc_record.verified` | boolean | oui |  |
| `dmarc_record.error_string` | string | oui |  |
| `inbound_record_list` | array<object (ClientVerifiedRecord)> |  |  |
| `inbound_record_list[].uuid` | string (uuid4) |  |  |
| `inbound_record_list[].verified` | boolean | oui |  |
| `inbound_record_list[].error_string` | string | oui |  |
| `tracking_record` | object (ClientVerifiedRecord) |  |  |
| `tracking_record.uuid` | string (uuid4) |  |  |
| `tracking_record.verified` | boolean | oui |  |
| `tracking_record.error_string` | string | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
