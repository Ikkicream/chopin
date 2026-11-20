# GET /uptime-monitors/{monitor_id}/private-notes — Private Notes

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /uptime-monitors/{monitor_id}/private-notes`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/private-notes`

## Description

API call used to get an uptime monitor's private notes. Returns the stored text, preserving whitespace and newlines, or an empty string when no notes are set.

Requires the GET Private Notes API-key permission. Private notes are only returned by this dedicated endpoint and are not included in GET Uptime Monitors responses.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor id, which can be found by running the [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) API. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `private_notes` | string |  | The monitor's private notes, up to 1024 UTF-8 bytes. Returns an empty string when no notes are set. |

```json
{
  "private_notes": "Production database\nOwner: operations"
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
