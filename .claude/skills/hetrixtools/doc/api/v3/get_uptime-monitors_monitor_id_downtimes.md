# GET /uptime-monitors/{monitor_id}/downtimes — Downtimes

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /uptime-monitors/{monitor_id}/downtimes`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/downtimes`

## Description

API call used to get an uptime monitor's Downtimes.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor id, which can be found by running the [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) API. |
| `per_page` | query | integer default=20 minimum=1 maximum=200 |  | Number of monitors returned per page. |
| `page` | query | integer default=1 minimum=1 maximum=10000 |  | Which page of the paginated results to return. |
| `start_before` | query | integer |  | Filter the downtime entries to only those that have started before the specified timestamp. *Example:* A value of `1641832650` will fetch downtimes that started at and before the timestamp `1641832650`. |
| `start_after` | query | integer |  | The timestamp after which to start scanning for downtime entries.   *Example:* A value of `1641832650` will fetch downtimes that started at and after the timestamp `1641832650`. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `downtimes` | array |  |  |
| `downtimes[].id` | string |  | The unique downtime id. |
| `downtimes[].start` | integer |  | The timestamp when the downtime started. |
| `downtimes[].end` | integer |  | The timestamp when the downtime ended. |
| `downtimes[].maintenance` | boolean |  | Whether the downtime happened during a maintenance window or not. |
| `meta` | object |  |  |
| `meta.total` | integer |  | The total number of downtimes for the uptime monitor. |
| `meta.total_filtered` | integer |  | The number of downtimes filtered by the API call. |
| `meta.returned` | integer |  | The number of downtimes returned by the API call. |
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
