# GET /uptime-monitors/{monitor_id}/network-diagnostics — Network Diagnostics

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /uptime-monitors/{monitor_id}/network-diagnostics`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/network-diagnostics`

## Description

API call used to get an uptime monitor's Network Diagnostics for a specific downtime. Each entry contains the Ping and MTR output captured by a monitoring node.

This endpoint is not paginated. If no diagnostics are available, `entries` is an empty array and `meta.returned` is `0`.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor id, which can be found by running the [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) API. |
| `downtime_id` | query | string | oui | The unique downtime id, which can be found by running the [GET - Downtimes](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors~1{monitor_id}~1downtimes/get) API for this monitor.  The downtime must belong to the specified monitor. Missing, malformed, unknown, or mismatched downtime ids return `400`. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `entries` | array | oui | The available diagnostics, with one entry per monitoring node. Empty when no diagnostics are available. |
| `entries[].location` | string | oui | The location and the specific monitoring node that captured the diagnostics. |
| `entries[].ping` | string | oui | Multiline, HTML-escaped Ping output. Returns an empty string when no Ping output is available for this node. |
| `entries[].mtr` | string | oui | Multiline, HTML-escaped MTR output. Returns an empty string when no MTR output is available for this node. |
| `meta` | object | oui |  |
| `meta.returned` | integer | oui | The number of diagnostic entries returned by this API call. |

_available_ :

```json
{
  "entries": [
    {
      "location": "London 6",
      "ping": "PING example.com (192.0.2.1) 56(84) bytes of data.\n--- example.com ping statistics ---\n5 packets transmitted, 0 received, 100% packet loss",
      "mtr": "HOST: London 6       Loss%   Snt   Last   Avg  Best  Wrst StDev\n  1.    192.0.2.1    100.0     5    0.0   0.0   0.0   0.0   0.0"
    }
  ],
  "meta": {
    "returned": 1
  }
}
```

_unavailable_ :

```json
{
  "entries": [],
  "meta": {
    "returned": 0
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

### 503 — Service Unavailable - A temporary server error prevented the request from completing.

```json
{
  "status": "service_unavailable",
  "message": "temporary server error, please retry"
}
```


Sécurité : `[{'bearerAuth': []}]`
