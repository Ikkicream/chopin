# Send multiple messages asynchronously

Source : https://learn.sweego.io/docs/sweego/send-bulk-email-send-bulk-email-post

> Send a message asynchronously

Send multiple messages asynchronously

**POST** `https://api.sweego.io/send/bulk/email`

Send a message asynchronously

- **data**: Body content

### Corps de la requête (requis)

Content-Type : `application/json`

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
| `recipients` | array<object (ModelRecipientEmailBulk)> | oui | List of recipient — minItems : `1` |
| `recipients[].email` | string (email) | oui |  |
| `recipients[].name` | string |  |  |
| `recipients[].variables` | object (Variables) |  | Variables dictionary applied to current recipient — défaut : `{}` |

Exemple « Email/ template » :
```json
{
 "campaign-id": "<CAMPAIGN ID>",
 "channel": "email",
 "provider": "sweego",
 "recipients": [
  {
   "email": "<RECIPIENT EMAIL 1>",
   "name": "<RECIPIENT NAME 1>",
   "variables": {
    "<VARIABLE NAME 1>": "<VARIABLE VALUE 1>",
    "<VARIABLE NAME 2>": "<VARIABLE VALUE 2>"
   }
  },
  {
   "email": "<RECIPIENT EMAIL 2>",
   "name": "<RECIPIENT NAME 2>",
   "variables": {
    "<VARIABLE NAME 1>": "<VARIABLE VALUE 3>",
    "<VARIABLE NAME 2>": "<VARIABLE VALUE 4>"
   }
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
 "template-id": "<TEMPLATE UUID>"
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
   "email": "<RECIPIENT EMAIL 1>",
   "name": "<RECIPIENT NAME 1>",
   "variables": {
    "<VARIABLE NAME 1>": "<VARIABLE VALUE 1>",
    "<VARIABLE NAME 2>": "<VARIABLE VALUE 2>"
   }
  },
  {
   "email": "<RECIPIENT EMAIL 2>",
   "name": "<RECIPIENT NAME 2>",
   "variables": {
    "<VARIABLE NAME 1>": "<VARIABLE VALUE 3>",
    "<VARIABLE NAME 2>": "<VARIABLE VALUE 4>"
   }
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
   "email": "<RECIPIENT EMAIL 1>",
   "name": "<RECIPIENT NAME 1>",
   "variables": {
    "<VARIABLE NAME 1>": "<VARIABLE VALUE 1>",
    "<VARIABLE NAME 2>": "<VARIABLE VALUE 2>"
   }
  },
  {
   "email": "<RECIPIENT EMAIL 2>",
   "name": "<RECIPIENT NAME 2>",
   "variables": {
    "<VARIABLE NAME 1>": "<VARIABLE VALUE 3>",
    "<VARIABLE NAME 2>": "<VARIABLE VALUE 4>"
   }
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
