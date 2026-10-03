# GET /status-pages — Status Pages

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /status-pages`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/status-pages`

## Description

API call used to get a list of all your status pages.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `page` | query | integer minimum=1 |  | The page number that you want to retrieve. |
| `per_page` | query | integer minimum=1 maximum=100 |  | The number of status pages that you want to retrieve per page. |
| `name` | query | string |  | The name of the status page that you want to retrieve. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `status_pages` | array |  |  |
| `status_pages[].id` | string |  | The unique identifier for this status page. |
| `status_pages[].name` | string |  | The name of this status page. |
| `status_pages[].type` | string enum ['blacklist', 'uptime'] |  | The type of this status page.   - `blacklist` - a status page containing blacklist monitors. - `uptime` - a status page containing uptime monitors. |
| `status_pages[].monitors` | array |  | The array of monitors that are on this status page. |
| `status_pages[].password_protected` | boolean |  | Defines whether or not this status page is password protected. |
| `status_pages[].announcement_type` | string enum ['none', 'positive', 'info', 'warning', 'critical'] |  | The type of announcement that is displayed on this status page. |
| `status_pages[].announcement_title` | string |  | The title of the announcement that is displayed on this status page. |
| `status_pages[].announcement_body` | string |  | The body of the announcement that is displayed on this status page. |
| `status_pages[].announcement_affected` | array |  | The array of monitors that are affected by the announcement that is displayed on this status page. |
| `status_pages[].twitter_feed` | boolean |  | Defines whether or not the Twitter feed is displayed on this status page. |
| `status_pages[].twitter_user` | string |  | The Twitter username's profile feed that is displayed on this status page. |
| `status_pages[].twitter_pos` | string enum ['right', 'left'] |  | The position of the Twitter feed on this status page. |
| `meta` | object |  |  |
| `meta.total` | integer |  | The total number of uptime monitors available in your account. |
| `meta.total_filtered` | integer |  | The number of uptime monitors found after filtering has been applied. |
| `meta.returned` | integer |  | The number of uptime monitors returned by this API call. |
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
