# GET /blacklist-monitors — Blacklist Monitors

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /blacklist-monitors`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/blacklist-monitors`

## Description

API call used to get blacklist monitors and their details.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `per_page` | query | integer default=20 minimum=1 maximum=1024 |  | Number of monitors returned per page. |
| `page` | query | integer default=1 minimum=1 maximum=10000 |  | Which page of the paginated results to return. |
| `name` | query | string |  | Filter results by name (accepts partial or full name). |
| `exact_name` | query | boolean |  | If set to `true`, the `name` filter will perform an exact match on the monitored name; all other filters will be ignored. |
| `target` | query | string |  | Filter results by monitored target (accepts partial or full target). |
| `exact_target` | query | boolean |  | If set to `true`, the `target` filter will perform an exact match on the monitored target; all other filters will be ignored. |
| `cidr` | query | integer minimum=21 maximum=32 |  | If specified, the `target` filter will be treated as a CIDR range with the specified prefix length and will match all IPs within that range. |
| `type` | query | string enum=['ipv4', 'domain'] |  | Filter results by monitor type. |
| `listed` | query | boolean |  | Filter results by listed status. |
| `order` | query | string enum=['asc', 'desc'] |  | Order results ascending or descending. |
| `order_by` | query | string enum=['name', 'target', 'listed', 'created_at', 'last_check'] |  | Order results by a specific field. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `monitors` | array |  |  |
| `monitors[].id` | string |  | The unique blacklist monitor ID. |
| `monitors[].name` | string |  | The blacklist monitor's name. |
| `monitors[].type` | string enum ['ipv4', 'domain'] |  | The type of blacklist monitor. |
| `monitors[].target` | string |  | The monitored target. |
| `monitors[].rdns` | string | null |  | The reverse DNS for the monitored target, if it exists; otherwise `null`. |
| `monitors[].report_id` | string |  | The unique blacklist report ID for this blacklist monitor.   Can be used to form the non white-label report URL: `https://hetrixtools.com/report/blacklist/{report_id}/`   And the white-label report URL: `https://yourdomain.com/report/blacklist/{report_id}/` |
| `monitors[].status` | string enum ['active', 'disabled', 'processing'] |  | The current status of this blacklist monitor. |
| `monitors[].contact_lists` | array |  | The unique contact list IDs assigned to this blacklist monitor. Currently supporting a maximum of one contact list ID per blacklist monitor. |
| `monitors[].listed` | array |  | The array of blacklists that have listed the monitored target. |
| `monitors[].listed[].rbl` | string |  | The RBL name. |
| `monitors[].listed[].delist` | string |  | The delist URL for this RBL. |
| `monitors[].created_at` | integer |  | Timestamp when the blacklist monitor was created. |
| `monitors[].last_check` | integer |  | Timestamp when the blacklist monitor was last checked. |
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
