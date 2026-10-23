# DELETE /uptime-monitors/{monitor_id}/server-agent — Server Agent ID

> Source : https://docs.hetrixtools.com/api/v3/ (opération `DELETE /uptime-monitors/{monitor_id}/server-agent`) — spec api.yaml?v=170, aspirée le 2026-09-26

`DELETE https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/server-agent`

## Description

API call used to detach (delete) the Server Monitoring Agent ID from an uptime monitor. This will remove the attached server agent from the monitor and delete all of the collected server metrics.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor id, which can be found by running the [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) API. |

## Réponses

### 200 — Server Agent successfully removed.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `message` | string |  |  |

```json
{
  "message": "server agent removed"
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
