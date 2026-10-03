# PUT /uptime-monitors/{monitor_id}/private-notes — Private Notes

> Source : https://docs.hetrixtools.com/api/v3/ (opération `PUT /uptime-monitors/{monitor_id}/private-notes`) — spec api.yaml?v=170, aspirée le 2026-09-26

`PUT https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/private-notes`

## Description

API call used to replace an uptime monitor's private notes with the supplied text. Whitespace and newlines are preserved. Send an empty string to clear the notes.

The supplied text must not exceed 1024 UTF-8 bytes. Requests exceeding this limit return `400` without changing the notes.

Requires the PUT Private Notes API-key permission. The response confirms the update without returning note text. If a concurrent edit is detected during the request, `409` is returned without changing the notes; the request can then be retried.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor id, which can be found by running the [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) API. |

## Corps de la requête

Content-Type : `application/json`

| Champ | Type | Requis | Description |
|---|---|---|---|
| `private_notes` | string | oui | Replacement text, limited to 1024 UTF-8 bytes, not characters. An empty string clears the notes. |

Exemple :

```json
{
  "private_notes": "Production database\nOwner: operations"
}
```

## Réponses

### 200 — Private notes successfully updated. When an empty string is supplied, the message is "private notes cleared".

| Champ | Type | Requis | Description |
|---|---|---|---|
| `status` | string enum ['success'] |  |  |
| `message` | string |  |  |

```json
{
  "status": "success",
  "message": "private notes updated"
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
