# GET /schedule-maintenance — Schedule Maintenance

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /schedule-maintenance`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/schedule-maintenance`

## Description

API call used to list all scheduled maintenance windows.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `per_page` | query | integer default=20 minimum=1 maximum=200 |  | Number of maintenance windows returned per page. |
| `page` | query | integer default=1 minimum=1 maximum=10000 |  | Which page of the paginated results to return. |
| `monitor_id` | query | string |  | Optional. Filter by uptime monitor ID. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `scheduled_maintenances` | array |  |  |
| `scheduled_maintenances[].id` | string |  | The unique schedule maintenance ID. |
| `scheduled_maintenances[].monitor_id` | string |  | The ID of the monitor under maintenance. |
| `scheduled_maintenances[].start` | string (date-time) |  | Maintenance start time as string (YYYY-MM-DD HH:MM). |
| `scheduled_maintenances[].end` | string (date-time) |  | Maintenance end time as string (YYYY-MM-DD HH:MM). |
| `scheduled_maintenances[].timezone` | string |  | Timezone of the maintenance window. |
| `scheduled_maintenances[].with_notifications` | boolean |  | Whether notifications are enabled for this maintenance. |
| `scheduled_maintenances[].recurring` | boolean |  | Whether this maintenance is recurring. |
| `scheduled_maintenances[].recurring_time` | integer |  | Recurring interval value. |
| `scheduled_maintenances[].recurring_time_type` | string |  | Recurring interval type (hour, day, week, month, year). |
| `meta` | object |  |  |
| `meta.total` | integer |  | Total number of scheduled maintenance windows. |
| `meta.total_filtered` | integer |  | Total number of filtered scheduled maintenance windows. |
| `meta.returned` | integer |  | Number of scheduled maintenance windows returned in this response. |
| `meta.pagination` | object |  |  |
| `meta.pagination.current` | integer |  |  |
| `meta.pagination.last` | integer |  |  |
| `meta.pagination.previous` | integer | null |  |  |
| `meta.pagination.next` | integer | null |  |  |

```json
{
  "scheduled_maintenances": [
    {
      "id": "abc123def456ghi789jkl012mno345pq",
      "monitor_id": "e34334dt5t755b034606y54ccabe62e8",
      "start": "2025-06-06 10:00",
      "end": "2025-06-06 12:00",
      "timezone": "America/New_York",
      "with_notifications": true,
      "recurring": false,
      "recurring_time": 0,
      "recurring_time_type": ""
    }
  ],
  "meta": {
    "total": 1,
    "total_filtered": 1,
    "returned": 1,
    "pagination": {
      "current": 1,
      "last": 1,
      "previous": null,
      "next": null
    }
  }
}
```

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
