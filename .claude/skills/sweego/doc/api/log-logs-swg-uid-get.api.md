# Retrieve a message by the Sweego UID

Source : https://learn.sweego.io/docs/sweego/log-logs-swg-uid-get

> Get a message by the Sweego UID

Retrieve a message by the Sweego UID

**GET** `https://api.sweego.io/logs/{swg_uid}`

Get a message by the Sweego UID

- **swg_uid**: Sweego uid

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `swg_uid` | string | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

**Variante : ModelOutLogEmailInbound**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `cc` | array<object (ModelRecipientEmail)> | oui |  |
| `cc[].email` | string (email) | oui |  |
| `cc[].name` | string |  |  |
| `channel` | string |  | valeurs : `email_inbound`; défaut : `"email_inbound"` |
| `creation_date` | string (date) | oui |  |
| `creation_dt` | string (date-time) | oui |  |
| `email_inbound_uuid` | string (uuid4) | oui |  |
| `email_from` | object (ModelRecipientEmail) | oui |  |
| `email_from.email` | string (email) | oui |  |
| `email_from.name` | string |  |  |
| `email_to` | array<object (ModelRecipientEmail)> | oui |  |
| `email_to[].email` | string (email) | oui |  |
| `email_to[].name` | string |  |  |
| `headers` | object (Headers) | oui |  |
| `inbound_recipient` | object (ModelRecipientEmail) | oui |  |
| `inbound_recipient.email` | string (email) | oui |  |
| `inbound_recipient.name` | string |  |  |
| `receipt_dt` | string (date-time) | oui |  |
| `status` | string | oui | Enumerate email inbound log : status available — valeurs : `received`, `error`, `forwarded` |
| `status_error` | string |  |  |
| `subject` | string | oui |  |
| `swg_uid` | string | oui |  |

**Variante : ModelOutLogEmail**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `accepted` | string |  |  |
| `bounce_type` | string |  |  |
| `bounced` | string |  |  |
| `campaign_id` | string | oui |  |
| `campaign_tags` | array<string> |  |  |
| `channel` | string |  | valeurs : `email`; défaut : `"email"` |
| `connection_ip` | string (ipvanyaddress) |  | Client IP |
| `deferred` | string |  |  |
| `domain_from` | string |  |  |
| `domain_to` | string |  |  |
| `dry_run` | boolean | oui |  |
| `email_creation` | string (date-time) | oui |  |
| `email_from` | string (email) \| string |  |  |
| `email_last_update` | string (date-time) | oui |  |
| `email_state` | string |  |  |
| `email_to` | string (email) \| string |  |  |
| `headers` | object (Headers) |  |  |
| `last_event_type` | integer | oui |  |
| `msp` | string |  |  |
| `output_ip` | string (ipvanyaddress) |  | IP used by MTA to send email |
| `rejected` | string |  |  |
| `status` | string | oui |  |
| `subject` | string |  |  |
| `swg_uid` | string | oui |  |
| `tracking_click` | array<any> |  |  |
| `tracking_open` | array<any> |  |  |
| `transaction_id` | string |  |  |

**Variante : ModelOutLogSms**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `campaign_id` | string |  |  |
| `campaign_type` | string | oui |  |
| `channel` | string |  | valeurs : `sms`; défaut : `"sms"` |
| `connection_ip` | string (ipvanyaddress) | oui | Client IP |
| `from_` | string | oui |  |
| `is_bat` | boolean | oui |  |
| `last_event_type` | integer | oui |  |
| `message` | string | oui |  |
| `nb_segments` | integer | oui |  |
| `price` | string | oui |  |
| `recipient` | string | oui |  |
| `recipient_region` | string | oui |  |
| `size` | integer | oui |  |
| `sms_creation` | string (date-time) | oui |  |
| `sms_last_update` | string (date-time) | oui |  |
| `status` | string | oui |  |
| `status_desc` | string |  |  |
| `swg_uid` | string | oui |  |
| `tracking_click` | array<any> |  |  |
| `transaction_id` | string |  |  |

**Variante : ModelResponseFail**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `msg` | string | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
