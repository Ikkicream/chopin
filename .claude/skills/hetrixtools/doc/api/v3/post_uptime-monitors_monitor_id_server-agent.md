# POST /uptime-monitors/{monitor_id}/server-agent — Server Agent ID

> Source : https://docs.hetrixtools.com/api/v3/ (opération `POST /uptime-monitors/{monitor_id}/server-agent`) — spec api.yaml?v=170, aspirée le 2026-09-26

`POST https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/server-agent`

## Description

API call used to attach a new Server Monitoring Agent ID to an uptime monitor. This will generate and return a unique Agent ID for the specified monitor, if one is not already attached.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor id, which can be found by running the [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) API. |

## Réponses

### 200 — Agent ID successfully created.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `agent_id` | string |  | The newly created unique server agent monitor ID that is attached to this uptime monitor. |

```json
{
  "agent_id": "9b7e53ddrfc12342r45ed234cfbf07c"
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

### 500 — Internal Server Error - An error occurred on the server.

```json
{
  "status": "internal_server_error",
  "message": "unexpected error occurred"
}
```


Sécurité : `[{'bearerAuth': []}]`
