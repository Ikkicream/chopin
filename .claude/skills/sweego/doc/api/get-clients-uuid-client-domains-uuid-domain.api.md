# Get domain info for a given client

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-domains-uuid-domain

> Init server actions: client_domain

Get domain info for a given client

**GET** `https://api.sweego.io/clients/{uuid_client}/domains/{uuid_domain}`

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
| `is_verified` | boolean | oui |  |
| `tracking_open_enabled` | boolean | oui |  |
| `tracking_click_enabled` | boolean | oui |  |
| `dkim_record` | object (ClientDnsRecordIsVerified) | oui |  |
| `dkim_record.name` | string | oui |  |
| `dkim_record.type` | string | oui | An enumeration. — valeurs : `unknown`, `A`, `AAAA`, `CNAME`, `TXT`, `SRV`, `TLSA`, `MX`, `NS`, `PTR`, `CAA`, `ALIAS`, `LOC`, `SSHFP`, `HINFO`, `RP`, `URI`, `DS`, `NAPTR`, `DNAME` |
| `dkim_record.data` | string | oui |  |
| `dkim_record.verified` | boolean | oui |  |
| `dkim_record.uuid` | string (uuid4) |  |  |
| `dmarc_record` | object (ClientDnsRecordIsVerified) | oui |  |
| `dmarc_record.name` | string | oui |  |
| `dmarc_record.type` | string | oui | An enumeration. — valeurs : `unknown`, `A`, `AAAA`, `CNAME`, `TXT`, `SRV`, `TLSA`, `MX`, `NS`, `PTR`, `CAA`, `ALIAS`, `LOC`, `SSHFP`, `HINFO`, `RP`, `URI`, `DS`, `NAPTR`, `DNAME` |
| `dmarc_record.data` | string | oui |  |
| `dmarc_record.verified` | boolean | oui |  |
| `dmarc_record.uuid` | string (uuid4) |  |  |
| `domain_record` | object (ClientDnsRecordIsVerified) | oui |  |
| `domain_record.name` | string | oui |  |
| `domain_record.type` | string | oui | An enumeration. — valeurs : `unknown`, `A`, `AAAA`, `CNAME`, `TXT`, `SRV`, `TLSA`, `MX`, `NS`, `PTR`, `CAA`, `ALIAS`, `LOC`, `SSHFP`, `HINFO`, `RP`, `URI`, `DS`, `NAPTR`, `DNAME` |
| `domain_record.data` | string | oui |  |
| `domain_record.verified` | boolean | oui |  |
| `domain_record.uuid` | string (uuid4) |  |  |
| `inbound_record_list` | array<object (ClientDnsRecordIsVerified)> | oui |  |
| `inbound_record_list[].name` | string | oui |  |
| `inbound_record_list[].type` | string | oui | An enumeration. — valeurs : `unknown`, `A`, `AAAA`, `CNAME`, `TXT`, `SRV`, `TLSA`, `MX`, `NS`, `PTR`, `CAA`, `ALIAS`, `LOC`, `SSHFP`, `HINFO`, `RP`, `URI`, `DS`, `NAPTR`, `DNAME` |
| `inbound_record_list[].data` | string | oui |  |
| `inbound_record_list[].verified` | boolean | oui |  |
| `inbound_record_list[].uuid` | string (uuid4) |  |  |
| `tracking_record` | object (ClientDnsRecordIsVerified) | oui |  |
| `tracking_record.name` | string | oui |  |
| `tracking_record.type` | string | oui | An enumeration. — valeurs : `unknown`, `A`, `AAAA`, `CNAME`, `TXT`, `SRV`, `TLSA`, `MX`, `NS`, `PTR`, `CAA`, `ALIAS`, `LOC`, `SSHFP`, `HINFO`, `RP`, `URI`, `DS`, `NAPTR`, `DNAME` |
| `tracking_record.data` | string | oui |  |
| `tracking_record.verified` | boolean | oui |  |
| `tracking_record.uuid` | string (uuid4) |  |  |
| `domain` | string | oui | minLength : `3`; maxLength : `255` |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
