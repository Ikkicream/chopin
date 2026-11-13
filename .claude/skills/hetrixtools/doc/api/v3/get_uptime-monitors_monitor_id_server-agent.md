# GET /uptime-monitors/{monitor_id}/server-agent — Server Agent ID

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /uptime-monitors/{monitor_id}/server-agent`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/server-agent`

## Description

API call used to get an uptime monitor's Server Monitoring Agent ID. This Server ID (SID) is unique for each Server Monitoring Agent.

The SID is a credential that authorizes agent data submissions. Treat it as a secret and grant access to this API call only to integrations that need the credential.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor id, which can be found by running the [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) API. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `agent_id` | string | null |  | The unique server agent monitor ID that is attached to this uptime monitor; returns `null` if no server agent monitor is attached. <a href="https://docs.hetrixtools.com/attach-a-server-monitor-to-any-of-your-uptime-monitors/" target="_blank">Learn more here</a>. |

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
