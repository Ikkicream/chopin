# DELETE /uptime-monitors/{monitor_id}/private-notes — Private Notes

> Source : https://docs.hetrixtools.com/api/v3/ (opération `DELETE /uptime-monitors/{monitor_id}/private-notes`) — spec api.yaml?v=170, aspirée le 2026-09-26

`DELETE https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/private-notes`

## Description

API call used to clear an uptime monitor's private notes. No request body is required. Clearing notes that are already empty also succeeds.

Requires the DELETE Private Notes API-key permission. The response confirms the update without returning note text. If a concurrent edit is detected during the request, `409` is returned without changing the notes; the request can then be retried.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor id, which can be found by running the [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) API. |

## Réponses

### 200 — Private notes successfully cleared.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `status` | string enum ['success'] |  |  |
| `message` | string |  |  |

```json
{
  "status": "success",
  "message": "private notes cleared"
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
