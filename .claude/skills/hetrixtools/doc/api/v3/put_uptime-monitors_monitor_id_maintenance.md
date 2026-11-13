# PUT /uptime-monitors/{monitor_id}/maintenance — Maintenance Mode

> Source : https://docs.hetrixtools.com/api/v3/ (opération `PUT /uptime-monitors/{monitor_id}/maintenance`) — spec api.yaml?v=170, aspirée le 2026-09-26

`PUT https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/maintenance`

## Description

Enable or disable maintenance mode for an uptime monitor, or switch between maintenance with and without notifications.

Use [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) to find the monitor ID.

| enabled | with_notifications | Resulting monitor_status |
| --- | --- | --- |
| `false` | Either value | `active` |
| `true` | `false` or omitted | `maint_dnd` (maintenance without notifications) |
| `true` | `true` | `maint` (maintenance with notifications) |

Repeating the same request is supported. Switching between maintenance modes preserves the current maintenance start time. Paused or disabled monitors cannot be changed through this endpoint and return `409`.

When a monitor is already down, entering maintenance splits its ongoing normal downtime at the maintenance start time. The earlier portion remains normal downtime; the later portion counts as maintenance. Repeated requests and notification-mode switches do not create additional downtime segments. Enabling maintenance while a monitor is up does not create a downtime event.

Disabling maintenance during an ongoing outage does not split that outage again: its existing maintenance portion continues to count as maintenance until the monitor recovers.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor ID. |

## Corps de la requête

Content-Type : `application/json`

| Champ | Type | Requis | Description |
|---|---|---|---|
| `enabled` |  | oui | Enable maintenance with true, or disable it with false. Integer 0/1 and strings "0"/"1" are also accepted. Strings "true"/"false", null, and other values are rejected. |
| `with_notifications` |  |  | Allow notifications during maintenance. Defaults to false when omitted, including when switching from maintenance with notifications. Accepts the same values as enabled. When enabled is false, this value is still validated and the response returns with_notifications as false. |

Exemple « enable_without_notifications » :

```json
{
  "enabled": true
}
```

Exemple « enable_with_notifications » :

```json
{
  "enabled": true,
  "with_notifications": true
}
```

Exemple « disable » :

```json
{
  "enabled": false
}
```

## Réponses

### 200 — Maintenance state successfully applied, or the monitor was already in the requested state. Responses include Cache-Control no-store.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `monitor_id` | string | oui | The canonical monitor ID. |
| `enabled` | boolean | oui | Whether maintenance is enabled. |
| `with_notifications` | boolean | oui | Whether maintenance with notifications is enabled. Always false when maintenance is disabled. |
| `monitor_status` | string enum ['active', 'maint', 'maint_dnd'] | oui |  |

_maintenance_without_notifications_ :

```json
{
  "monitor_id": "0123456789abcdef0123456789abcdef",
  "enabled": true,
  "with_notifications": false,
  "monitor_status": "maint_dnd"
}
```

_maintenance_with_notifications_ :

```json
{
  "monitor_id": "0123456789abcdef0123456789abcdef",
  "enabled": true,
  "with_notifications": true,
  "monitor_status": "maint"
}
```

_maintenance_disabled_ :

```json
{
  "monitor_id": "0123456789abcdef0123456789abcdef",
  "enabled": false,
  "with_notifications": false,
  "monitor_status": "active"
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

### 404 — Not Found - The resource you have requested was not found.

```json
{
  "status": "not_found",
  "message": "error message"
}
```

### 409 — Conflict - The request could not be completed due to a conflict with the current state of the resource.

```json
{
  "status": "conflict",
  "message": "resource already exists or is in an invalid state"
}
```

### 429 — Rate Limited - You are performing API requests too frequently.

```json
{
  "status": "too_many_requests",
  "message": "user api rate limit exceeded"
}
```

### 503 — Service Unavailable - A temporary server error prevented the request from completing.

```json
{
  "status": "service_unavailable",
  "message": "temporary server error, please retry"
}
```


Sécurité : `[{'bearerAuth': []}]`
