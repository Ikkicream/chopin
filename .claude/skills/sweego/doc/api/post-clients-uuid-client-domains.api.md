# Create the domain with the given info

Source : https://learn.sweego.io/docs/sweego/post-clients-uuid-client-domains

> Init server actions: client_domain

Create the domain with the given info

**POST** `https://api.sweego.io/clients/{uuid_client}/domains`

Init server actions: client_domain

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `domain` | string | oui | minLength : `3`; maxLength : `255` |

### Réponses

#### 201 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `dkim_record` | object (ClientDnsRecord) | oui |  |
| `dkim_record.name` | string | oui |  |
| `dkim_record.type` | string | oui | An enumeration. — valeurs : `unknown`, `A`, `AAAA`, `CNAME`, `TXT`, `SRV`, `TLSA`, `MX`, `NS`, `PTR`, `CAA`, `ALIAS`, `LOC`, `SSHFP`, `HINFO`, `RP`, `URI`, `DS`, `NAPTR`, `DNAME` |
| `dkim_record.data` | string | oui |  |
| `dmarc_record` | object (ClientDnsRecord) | oui |  |
| `dmarc_record.name` | string | oui |  |
| `dmarc_record.type` | string | oui | An enumeration. — valeurs : `unknown`, `A`, `AAAA`, `CNAME`, `TXT`, `SRV`, `TLSA`, `MX`, `NS`, `PTR`, `CAA`, `ALIAS`, `LOC`, `SSHFP`, `HINFO`, `RP`, `URI`, `DS`, `NAPTR`, `DNAME` |
| `dmarc_record.data` | string | oui |  |
| `domain_record` | object (ClientDnsRecord) | oui |  |
| `domain_record.name` | string | oui |  |
| `domain_record.type` | string | oui | An enumeration. — valeurs : `unknown`, `A`, `AAAA`, `CNAME`, `TXT`, `SRV`, `TLSA`, `MX`, `NS`, `PTR`, `CAA`, `ALIAS`, `LOC`, `SSHFP`, `HINFO`, `RP`, `URI`, `DS`, `NAPTR`, `DNAME` |
| `domain_record.data` | string | oui |  |
| `inbound_record_list` | array<object (ClientDnsRecord)> | oui |  |
| `inbound_record_list[].name` | string | oui |  |
| `inbound_record_list[].type` | string | oui | An enumeration. — valeurs : `unknown`, `A`, `AAAA`, `CNAME`, `TXT`, `SRV`, `TLSA`, `MX`, `NS`, `PTR`, `CAA`, `ALIAS`, `LOC`, `SSHFP`, `HINFO`, `RP`, `URI`, `DS`, `NAPTR`, `DNAME` |
| `inbound_record_list[].data` | string | oui |  |
| `tracking_record` | object (ClientDnsRecord) | oui |  |
| `tracking_record.name` | string | oui |  |
| `tracking_record.type` | string | oui | An enumeration. — valeurs : `unknown`, `A`, `AAAA`, `CNAME`, `TXT`, `SRV`, `TLSA`, `MX`, `NS`, `PTR`, `CAA`, `ALIAS`, `LOC`, `SSHFP`, `HINFO`, `RP`, `URI`, `DS`, `NAPTR`, `DNAME` |
| `tracking_record.data` | string | oui |  |
| `domain` | string | oui | minLength : `3`; maxLength : `255` |
| `uuid` | string (uuid4) | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
