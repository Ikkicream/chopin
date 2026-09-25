# A paginated list of message records for multiple channels

Source : https://learn.sweego.io/docs/sweego/logs-all-logs-all-post

> A paginated list of message records for all channels

A paginated list of message records for multiple channels

**POST** `https://api.sweego.io/logs/all`

A paginated list of message records for all channels

- **data**: Body content

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `end_date` | string (date) |  | Filter : end date, default value : today |
| `start_date` | string (date) |  | Filter : start date, default value : 7 days ago |
| `offset` | integer |  | Filter : get elements from indice — défaut : `0`; minimum : `0` |
| `size` | integer |  | Filter : number of elements — défaut : `50`; minimum : `1`; maximum : `500` |
| `channel` | array<string> |  | Channels to search messages — défaut : `["email", "sms"]` |
| `search_word` | string |  | Value to search on swg_uid & recipients |
| `senders` | array<string> |  | Email from domains or Sms sender ids |
| `status` | array<string> |  | Message status |
| `transaction_id` | string (uuid4) |  | Transaction id |

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
