# POST /schedule-maintenance — Schedule Maintenance

> Source : https://docs.hetrixtools.com/api/v3/ (opération `POST /schedule-maintenance`) — spec api.yaml?v=170, aspirée le 2026-09-26

`POST https://api.hetrixtools.com/v3/schedule-maintenance`

## Description

API call used to create a new schedule maintenance for a monitor.

## Corps de la requête

Content-Type : `application/json`

| Champ | Type | Requis | Description |
|---|---|---|---|
| `monitor_id` | string | oui | The monitor ID to schedule maintenance for. |
| `start` | string (date-time) | oui | Maintenance start time as string (YYYY-MM-DD HH:MM). |
| `end` | string (date-time) | oui | Maintenance end time as string (YYYY-MM-DD HH:MM). |
| `timezone` | string | oui | Timezone of the maintenance window. |
| `with_notifications` | boolean |  | Whether notifications are enabled for this maintenance. |
| `recurring_time` | integer |  | Recurring interval value. In set, along with `recurring_time_type`, the maintenance will be recurring. |
| `recurring_time_type` | string |  | Recurring interval type (hour, day, week, month, year). If set, along with `recurring_time`, the maintenance will be recurring. |

Exemple :

```json
{
  "monitor_id": "e34334dt5t755b034606y54ccabe62e8",
  "start": "2025-06-06 10:00",
  "end": "2025-06-06 12:00",
  "timezone": "America/New_York",
  "with_notifications": true,
  "recurring": false,
  "recurring_time": 0,
  "recurring_time_type": ""
}
```

## Réponses

### 201 — Created

| Champ | Type | Requis | Description |
|---|---|---|---|
| `id` | string |  |  |
| `monitor_id` | string |  |  |
| `start` | string |  |  |
| `end` | string |  |  |
| `timezone` | string |  |  |
| `with_notifications` | boolean |  |  |
| `recurring` | boolean |  |  |
| `recurring_time` | integer |  |  |
| `recurring_time_type` | string |  |  |

```json
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
