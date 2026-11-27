# Send a message asynchronously

Source : https://learn.sweego.io/docs/sweego/send-send-post

> Send a message asynchronously

Send a message asynchronously

**POST** `https://api.sweego.io/send`

Send a message asynchronously

- **data**: Body content

### Corps de la requête (requis)

Content-Type : `application/json`

**Variante : ModelInSendEmail**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `attachments` | array<object (ModelAttachmentEmail)> |  |  |
| `attachments[].content` | string | oui |  |
| `attachments[].content_id` | string |  |  |
| `attachments[].disposition` | string |  | valeurs : `attachment`, `inline`; défaut : `"attachment"` |
| `attachments[].filename` | string | oui |  |
| `attachments[].is_related` | boolean |  | défaut : `false` |
| `campaign-id` | string |  | Custom campaign ID |
| `campaign-tags` | array<string> |  | Tags to add to your email (5 max), each tag length must be between 1 & 20 and must contains only theses characters [A-Za-z0-9-] — motif : `^[A-Za-z0-9-]{1,20}$` |
| `campaign-type` | string |  | Type of campaign — valeurs : `market`, `newsletter`, `transac` |
| `channel` | string |  | Mandatory. Channel to use — valeurs : `email`; défaut : `"email"` |
| `compress_style` | boolean |  | Compress / minify non-inline style tag (only applies when message-html is given) — défaut : `false` |
| `dry-run` | boolean |  | Dry run mode (no message sent) — défaut : `false` |
| `expires` | string (date-time) \| string |  | Define the 'Expires' header that indicates the time at which a message loses its validity. Could either be a date string in iso8601 format (ex: "2024-07-26T19:30:00+02:00" ) OR a time delta string (ex: "X day(s)\|month(s)\|year(s)") |
| `from` | object (From) | oui | From description |
| `from.email` | string (email) | oui |  |
| `from.name` | string |  |  |
| `force_inline_style` | boolean |  | Extract CSS content from style tag and move it to inline CSS (only applies when message-html is given) — défaut : `false` |
| `headers` | object (Headers) |  | Headers to add to your email (5 max) |
| `list-unsub` | object (List-Unsub) |  | List unsubscribe header method & value, format :<br/>mailto: \<mailto:EMAIL\><br/>one-click: \<mailto:EMAIL\>,\<URL\> |
| `list-unsub.method` | string |  | valeurs : `one-click`, `mailto`; défaut : `"mailto"` |
| `list-unsub.value` | string | oui |  |
| `message-html` | string |  | Message provided in html format. At least one of message_txt / message_html / template_id must be set. But only one between message_html & template_id |
| `message-txt` | string |  | Message provided in text format. At least one of message_txt / message_html / template_id must be set. But only one between message_html & template_id |
| `provider` | string | oui | Provider to use |
| `reply-to` | object (Reply-To) |  | Reply to |
| `reply-to.email` | string (email) | oui |  |
| `reply-to.name` | string |  |  |
| `subject` | string | oui | Email subject |
| `tracking_open` | boolean |  | False to disable email open tracking — défaut : `true` |
| `template-id` | string |  | ID of a saved template. At least one of message_txt / message_html / template_id must be set. But only one between message_html & template_id |
| `bcc` | array<object (ModelRecipientEmail)> |  | List of blind carbon copy recipient |
| `bcc[].email` | string (email) | oui |  |
| `bcc[].name` | string |  |  |
| `cc` | array<object (ModelRecipientEmail)> |  | List of carbon copy recipient |
| `cc[].email` | string (email) | oui |  |
| `cc[].name` | string |  |  |
| `recipients` | array<object (ModelRecipientEmail)> | oui | List of recipient — minItems : `1` |
| `recipients[].email` | string (email) | oui |  |
| `recipients[].name` | string |  |  |
| `variables` | object (Variables) |  | Variables dictionary to uses with template (ignored otherwise) — défaut : `{}` |

**Variante : ModelInSendSms**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `bat` | boolean |  | BAT mode — défaut : `false` |
| `campaign-id` | string |  | Custom campaign ID |
| `campaign-type` | string | oui | An enumeration. — valeurs : `market`, `transac` |
| `channel` | string |  | Mandatory. Channel to use — valeurs : `sms`; défaut : `"sms"` |
| `message-txt` | string |  | Message provided in text format. Only one of message_txt & template_id must be set |
| `provider` | string | oui | Provider to use |
| `recipients` | array<object (ModelRecipientSms)> | oui | List of recipient — minItems : `1` |
| `recipients[].converted_num` | string |  |  |
| `recipients[].num` | string | oui |  |
| `recipients[].region` | string | oui | valeurs : `AC`, `AD`, `AE`, `AF`, `AG`, `AI`, `AL`, `AM`, `AO`, `AR`, `AS`, `AT`, `AU`, `AW`, `AX`, `AZ`, `BA`, `BB`, `BD`, `BE`, `BF`, `BG`, `BH`, `BI`, `BJ`, `BL`, `BM`, `BN`, `BO`, `BQ`, `BR`, `BS`, `BT`, `BW`, `BY`, `BZ`, `CA`, `CC`, `CD`, `CF`, `CG`, `CH`, `CI`, `CK`, `CL`, `CM`, `CO`, `CR`, `CU`, `CV`, `CW`, `CX`, `CY`, `CZ`, `DE`, `DJ`, `DK`, `DM`, `DO`, `DZ`, `EC`, `EE`, `EG`, `EH`, `ER`, `ES`, `ET`, `FI`, `FJ`, `FK`, `FM`, `FO`, `FR`, `GA`, `GB`, `GD`, `GE`, `GF`, `GG`, `GH`, `GI`, `GL`, `GM`, `GN`, `GP`, `GQ`, `GR`, `GT`, `GU`, `GW`, `GY`, `HK`, `HN`, `HR`, `HT`, `HU`, `ID`, `IE`, `IL`, `IM`, `IN`, `IO`, `IQ`, `IR`, `IS`, `IT`, `JE`, `JM`, `JO`, `JP`, `KE`, `KG`, `KH`, `KI`, `KM`, `KN`, `KP`, `KR`, `KW`, `KY`, `KZ`, `LA`, `LB`, `LC`, `LI`, `LK`, `LR`, `LS`, `LT`, `LU`, `LV`, `LY`, `MA`, `MC`, `MD`, `ME`, `MF`, `MG`, `MH`, `MK`, `ML`, `MM`, `MN`, `MO`, `MP`, `MQ`, `MR`, `MS`, `MT`, `MU`, `MV`, `MW`, `MX`, `MY`, `MZ`, `NA`, `NC`, `NE`, `NF`, `NG`, `NI`, `NL`, `NO`, `NP`, `NR`, `NU`, `NZ`, `OM`, `PA`, `PE`, `PF`, `PG`, `PH`, `PK`, `PL`, `PM`, `PR`, `PS`, `PT`, `PW`, `PY`, `QA`, `RE`, `RO`, `RS`, `RU`, `RW`, `SA`, `SB`, `SC`, `SD`, `SE`, `SG`, `SH`, `SI`, `SJ`, `SK`, `SL`, `SM`, `SN`, `SO`, `SR`, `SS`, `ST`, `SV`, `SX`, `SY`, `SZ`, `TA`, `TC`, `TD`, `TG`, `TH`, `TJ`, `TK`, `TL`, `TM`, `TN`, `TO`, `TR`, `TT`, `TV`, `TZ`, `UA`, `UG`, `US`, `UY`, `UZ`, `VA`, `VC`, `VE`, `VG`, `VI`, `VN`, `VU`, `WF`, `WS`, `XK`, `YE`, `YT`, `ZA`, `ZM`, `ZW`, `OTHER` |
| `sender-id` | string |  | Sender id to use |
| `shorten-urls` | boolean |  | True to shorten urls — défaut : `true` |
| `shorten-with-protocol` | boolean |  | Add protocol to shortened urls — défaut : `true` |
| `template-id` | string |  | ID of a saved template. Only one of message_txt & template_id must be set |
| `variables` | object (Variables) |  | Variables dictionary to uses with template (ignored otherwise) |

Exemple « Email/ template » :
```json
{
 "campaign-id": "<CAMPAIGN ID>",
 "channel": "email",
 "provider": "sweego",
 "recipients": [
  {
   "email": "<RECIPIENT EMAIL>",
   "name": "<RECIPIENT NAME>"
  }
 ],
 "from": {
  "email": "<EMAIL FROM>",
  "name": "<NAME FROM>"
 },
 "list-unsub": {
  "method": "mailto",
  "value": "<mailto: <EMAIL>>"
 },
 "reply-to": {
  "email": "<REPLY TO EMAIL>",
  "name": "<REPLY TO NAME>"
 },
 "subject": "<EMAIL SUBJECT>",
 "template-id": "<TEMPLATE UUID>",
 "variables": {
  "<VARIABLE NAME 1>": "<VARIABLE VALUE 1>",
  "<VARIABLE NAME 2>": "<VARIABLE VALUE 2>"
 }
}
```

Exemple « Email/ text message » :
```json
{
 "campaign-id": "<CAMPAIGN ID>",
 "channel": "email",
 "provider": "sweego",
 "recipients": [
  {
   "email": "<RECIPIENT EMAIL>",
   "name": "<RECIPIENT NAME>"
  }
 ],
 "from": {
  "email": "<EMAIL FROM>",
  "name": "<NAME FROM>"
 },
 "list-unsub": {
  "method": "one-click",
  "value": "<mailto: <EMAIL>>,<URL>"
 },
 "subject": "<EMAIL SUBJECT>",
 "message-txt": "<EMAIL TEXT>"
}
```

Exemple « Email/ HTML message » :
```json
{
 "campaign-id": "<CAMPAIGN ID>",
 "channel": "email",
 "provider": "sweego",
 "recipients": [
  {
   "email": "<RECIPIENT EMAIL>",
   "name": "<RECIPIENT NAME>"
  }
 ],
 "from": {
  "email": "<EMAIL FROM>",
  "name": "<NAME FROM>"
 },
 "subject": "<EMAIL SUBJECT>",
 "message-html": "<EMAIL IN HTML FORMAT>"
}
```

Exemple « SMS/ text message » :
```json
{
 "bat": "(true|false)",
 "campaign-id": "<CAMPAIGN ID>",
 "campaign-type": "(market|transac)",
 "channel": "sms",
 "message-txt": "<SMS TEXT>",
 "provider": "sweego",
 "recipients": [
  {
   "num": "0123456789",
   "region": "fr"
  }
 ],
 "sender-id": "<SMS SENDER ID>"
}
```

Exemple « SMS/ template » :
```json
{
 "bat": "(true|false)",
 "campaign-id": "<CAMPAIGN ID>",
 "campaign-type": "(market|transac)",
 "channel": "sms",
 "template-id": "<TEMPLATE UUID>",
 "variables": {
  "<VARIABLE NAME 1>": "<VARIABLE VALUE 1>",
  "<VARIABLE NAME 2>": "<VARIABLE VALUE 2>"
 },
 "provider": "sweego",
 "recipients": [
  {
   "num": "0123456789",
   "region": "fr"
  }
 ]
}
```

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `credit_left` | string |  |  |
| `channel` | string | oui |  |
| `provider` | string | oui |  |
| `swg_uids` | object (Swg Uids) | oui |  |
| `transaction_id` | string (uuid4) | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
