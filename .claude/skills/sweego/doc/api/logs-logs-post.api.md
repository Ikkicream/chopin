# A paginated list of message records for a channel

Source : https://learn.sweego.io/docs/sweego/logs-logs-post

> A paginated list of Message records

A paginated list of message records for a channel

**POST** `https://api.sweego.io/logs/`

A paginated list of Message records

- **data**: Body content

### Corps de la requête (requis)

Content-Type : `application/json`

**Variante : ModelInLogsEmailInbound**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `end_date` | string (date) |  | Filter : end date, default value : today |
| `start_date` | string (date) |  | Filter : start date, default value : 7 days ago |
| `offset` | integer |  | Filter : get elements from indice — défaut : `0`; minimum : `0` |
| `size` | integer |  | Filter : number of elements — défaut : `50`; minimum : `1`; maximum : `500` |
| `channel` | string |  | Channel to use — valeurs : `email_inbound`; défaut : `"email_inbound"` |
| `email_inbound_uuids` | array<string (uuid4)> |  | List of inbound domain |
| `search_word` | string |  | Value to search on swg_uid / from / to |
| `status` | array<string> |  | Email inbound status |

**Variante : ModelInLogsEmail**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `end_date` | string (date) |  | Filter : end date, default value : today |
| `start_date` | string (date) |  | Filter : start date, default value : 7 days ago |
| `offset` | integer |  | Filter : get elements from indice — défaut : `0`; minimum : `0` |
| `size` | integer |  | Filter : number of elements — défaut : `50`; minimum : `1`; maximum : `500` |
| `campaign-tags` | array<string> |  | Tags added in your emails — motif : `^[A-Za-z0-9-]{1,20}$` |
| `campaign-type` | string |  | Type of campaign — valeurs : `default`, `market`, `newsletter`, `transac`, `welcome` |
| `channel` | string |  | Channel to use — valeurs : `email`; défaut : `"email"` |
| `domains` | array<string> |  | From domains used |
| `msp` | array<string> |  | MSP used |
| `search_word` | string |  | Value to search on swg_uid & emails recipients |
| `status` | array<string> |  | Email status |
| `transaction_id` | string (uuid4) |  | Transaction id |

**Variante : ModelInLogsSms**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `end_date` | string (date) |  | Filter : end date, default value : today |
| `start_date` | string (date) |  | Filter : start date, default value : 7 days ago |
| `offset` | integer |  | Filter : get elements from indice — défaut : `0`; minimum : `0` |
| `size` | integer |  | Filter : number of elements — défaut : `50`; minimum : `1`; maximum : `500` |
| `campaign-type` | string |  | Type of sms — valeurs : `market`, `transac` |
| `channel` | string |  | Channel to use — valeurs : `sms`; défaut : `"sms"` |
| `search_word` | string |  | Value to search on sms recipients |
| `senders` | array<string> |  | Senders used |
| `status` | array<string> |  | SMS status |
| `transaction_id` | string (uuid4) |  | Transaction id |

Exemple « Email » :
```json
{
 "campaign-tags": [
  "<CAMPAIGN TAGS>"
 ],
 "campaign-type": [
  "<CAMPAIGN TYPES>"
 ],
 "channel": "email",
 "domains": [
  "<DOMAINS FROM>"
 ],
 "end_date": "<END DATE>",
 "msp": [
  "<MSP>"
 ],
 "offset": "<OFFSET>",
 "provider": "sweego",
 "search_word": "<SEARCH WORD>",
 "size": "<SIZE>",
 "start_date": "<START DATE>",
 "status": [
  "<STATUS>"
 ],
 "transaction_id": "<TRANSACTION ID>"
}
```

Exemple « SMS » :
```json
{
 "campaign-type": [
  "<CAMPAIGN TYPES>"
 ],
 "channel": "sms",
 "end_date": "<END DATE>",
 "offset": "<OFFSET>",
 "provider": "sweego",
 "search_word": "<SEARCH WORD>",
 "sender_ids": [
  "<SENDER IDS>"
 ],
 "size": "<SIZE>",
 "start_date": "<START DATE>",
 "status": [
  "<STATUS>"
 ],
 "transaction_id": "<TRANSACTION ID>"
}
```

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
