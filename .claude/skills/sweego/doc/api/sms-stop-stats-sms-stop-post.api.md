# All sms stop stats

Source : https://learn.sweego.io/docs/sweego/sms-stop-stats-sms-stop-post

> A paginated list of sms stop stats

All sms stop stats

**POST** `https://api.sweego.io/stats/sms/stop`

A paginated list of sms stop stats

- **data**: Body content

### Corps de la requête

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `end_date` | string (date) |  | Filter : end date, default value : today |
| `start_date` | string (date) |  | Filter : start date, default value : 7 days ago |
| `senders` | array<string> |  | Senders used |

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
