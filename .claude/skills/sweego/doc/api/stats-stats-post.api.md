# A paginated list of stats

Source : https://learn.sweego.io/docs/sweego/stats-stats-post

> A paginated list of stats

A paginated list of stats

**POST** `https://api.sweego.io/stats/`

A paginated list of stats

- **data**: Body content

### Corps de la requête (requis)

Content-Type : `application/json`

**Variante : ModelInStatsEmailInbound**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `end_date` | string (date) |  | Filter : end date, default value : today |
| `start_date` | string (date) |  | Filter : start date, default value : 7 days ago |
| `offset` | integer |  | Filter : get elements from indice — défaut : `0`; minimum : `0` |
| `size` | integer |  | Filter : number of elements — défaut : `50`; minimum : `1`; maximum : `500` |
| `channel` | string |  | Channel used — valeurs : `email_inbound`; défaut : `"email_inbound"` |
| `email_inbound_uuids` | array<string> |  | Email inbound uuid list |

**Variante : ModelInStatsEmail**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `end_date` | string (date) |  | Filter : end date, default value : today |
| `start_date` | string (date) |  | Filter : start date, default value : 7 days ago |
| `offset` | integer |  | Filter : get elements from indice — défaut : `0`; minimum : `0` |
| `size` | integer |  | Filter : number of elements — défaut : `50`; minimum : `1`; maximum : `500` |
| `channel` | string |  | Channel used — valeurs : `email`; défaut : `"email"` |
| `domains` | array<string> |  | From domains used |
| `msp` | array<string> |  | MSP used |

**Variante : ModelInStatsSms**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `end_date` | string (date) |  | Filter : end date, default value : today |
| `start_date` | string (date) |  | Filter : start date, default value : 7 days ago |
| `offset` | integer |  | Filter : get elements from indice — défaut : `0`; minimum : `0` |
| `size` | integer |  | Filter : number of elements — défaut : `50`; minimum : `1`; maximum : `500` |
| `campaign_types` | array<string> |  | Type of sms — défaut : `["market", "transac"]` |
| `channel` | string |  | Channel used — valeurs : `sms`; défaut : `"sms"` |
| `senders` | array<string> |  | Senders used |

Exemple « Email » :
```json
{
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
 "size": "<SIZE>",
 "start_date": "<START DATE>"
}
```

Exemple « SMS » :
```json
{
 "channel": "sms",
 "end_date": "<END DATE>",
 "offset": "<OFFSET>",
 "provider": "sweego",
 "senders": [
  "<SENDERS>"
 ],
 "sms_types": [
  "<SMS_TYPES>"
 ],
 "size": "<SIZE>",
 "start_date": "<START DATE>"
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
