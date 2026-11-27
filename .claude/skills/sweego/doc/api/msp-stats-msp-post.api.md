# All email msp stats

Source : https://learn.sweego.io/docs/sweego/msp-stats-msp-post

> A paginated list of msp stats

All email msp stats

**POST** `https://api.sweego.io/stats/msp`

This endpoint has been deprecated and may be replaced or removed in future versions of the API.

A paginated list of msp stats

- **data**: Body content

### Corps de la requête

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `end_date` | string (date) |  | Filter : end date, default value : today |
| `start_date` | string (date) |  | Filter : start date, default value : 7 days ago |
| `domains` | array<string> |  | From domains used |
| `msp` | array<string> |  | MSP used |

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `campaign_tags` | array<string> |  |  |
| `campaign_types` | array<string> |  |  |
| `channel` | string |  | Enum class representing a channel type — valeurs : `email`, `sms`, `email_inbound` |
| `channels` | array<string> |  |  |
| `client_id` | string |  |  |
| `error` | array<string> |  |  |
| `msg` | string |  |  |
| `msps` | array<string> |  |  |
| `nb_page` | integer |  |  |
| `nb_result` | integer |  |  |
| `nb_result_without_offset` | integer |  |  |
| `result` | Result |  |  |
| `senders` | array<string> |  |  |
| `state` | boolean | oui |  |
| `status` | array<string> |  |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
