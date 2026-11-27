# GET /contact-lists — Contact Lists

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /contact-lists`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/contact-lists`

## Description

API call used to get contact lists and their details.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `per_page` | query | integer default=20 minimum=1 maximum=200 |  | Number of monitors returned per page. |
| `page` | query | integer default=1 minimum=1 maximum=10000 |  | Which page of the paginated results to return. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `contact_lists` | array |  |  |
| `contact_lists[].id` | string |  | The unique contact list ID. |
| `contact_lists[].name` | string |  | The contact list's name. |
| `contact_lists[].default` | boolean |  | Whether or not this is the default contact list. |
| `contact_lists[].email` | array |  | Emails in this contact list. |
| `contact_lists[].phone_sms` | array |  | SMS numbers in this contact list. |
| `contact_lists[].telegram` | array |  | Telegram usernames in this contact list. |
| `contact_lists[].pushbullet` | array |  | Pushbullet usernames in this contact list. |
| `contact_lists[].pushover` | object |  |  |
| `contact_lists[].pushover.key` | string |  | The Pushover API key. |
| `contact_lists[].pushover.priority` | integer |  | The Pushover priority. |
| `contact_lists[].twitter` | array |  | \[DEPRECATED\] Twitter usernames in this contact list. |
| `contact_lists[].slack` | object |  |  |
| `contact_lists[].slack.webhook` | string |  | The Slack webhook URL. |
| `contact_lists[].slack.target` | string |  | The Slack target channel. |
| `contact_lists[].slack.hide_target` | boolean |  | Whether or not to hide the monitored target in the notification. |
| `contact_lists[].discord` | object |  |  |
| `contact_lists[].discord.webhook` | string |  | The Discord webhook URL. |
| `contact_lists[].discord.target` | string |  | The Discord target channel. |
| `contact_lists[].discord.hide_target` | boolean |  | Whether or not to hide the monitored target in the notification. |
| `contact_lists[].mattermost_rocketchat` | object |  |  |
| `contact_lists[].mattermost_rocketchat.webhook` | string |  | The Mattermost/Rocket.Chat webhook URL. |
| `contact_lists[].mattermost_rocketchat.target` | string |  | The Mattermost/Rocket.Chat target channel. |
| `contact_lists[].mattermost_rocketchat.hide_target` | boolean |  | Whether or not to hide the monitored target in the notification. |
| `contact_lists[].microsoft_teams` | object |  |  |
| `contact_lists[].microsoft_teams.webhook` | string |  | The Microsoft Teams webhook URL. |
| `contact_lists[].pagerduty` | object |  |  |
| `contact_lists[].pagerduty.key` | string |  | The PagerDuty API key. |
| `contact_lists[].opsgenie` | object |  |  |
| `contact_lists[].opsgenie.key` | string |  | The OpsGenie API key. |
| `contact_lists[].opsgenie.priority` | string |  | The OpsGenie priority. |
| `contact_lists[].victorops` | object |  |  |
| `contact_lists[].victorops.key` | string |  | The VictorOps API key. |
| `contact_lists[].victorops.route` | string |  | The VictorOps route. |
| `contact_lists[].victorops.priority` | string |  | The VictorOps priority. |
| `contact_lists[].webhook` | object |  |  |
| `contact_lists[].webhook.url` | string |  | The Webhook URL. |
| `contact_lists[].webhook.authentication` | string |  | The Webhook authentication method. |
| `contact_lists[].dnd` | array |  |  |
| `contact_lists[].dnd[].day` | string |  | The day of the week. |
| `contact_lists[].dnd[].hour` | string |  | The hour of the day. |
| `meta` | object |  |  |
| `meta.total` | integer |  | The total number of contact lists found. |
| `meta.returned` | integer |  | The number of contact lists returned in this response. |
| `meta.pagination` | object |  |  |
| `meta.pagination.current` | integer |  | The current page number. |
| `meta.pagination.last` | integer |  | The last available page number. |
| `meta.pagination.previous` | integer | null |  | The previous page number; `null` returned if no previous pages available. |
| `meta.pagination.next` | integer | null |  | The next page number; `null` returned if no further pages available. |

### 400 — Bad Request - API request is invalid or not properly formatted.

```json
{
  "status": "bad_request",
  "message": "invalid endpoint"
}
```

### 401 — Unauthorized - Missing or invalid authentication API key (bearer token).

```json
{
  "status": "unauthorized",
  "message": "invalid authorization"
}
```

### 403 — Forbidden - Your API key does not have access to perform this request.

```json
{
  "status": "forbidden",
  "message": "api key not allowed to perform this action"
}
```

### 429 — Rate Limited - You are performing API requests too frequently.

```json
{
  "status": "too_many_requests",
  "message": "user api rate limit exceeded"
}
```


Sécurité : `[{'bearerAuth': []}]`
