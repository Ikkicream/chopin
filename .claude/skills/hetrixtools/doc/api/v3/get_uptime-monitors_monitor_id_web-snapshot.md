# GET /uptime-monitors/{monitor_id}/web-snapshot — Web Snapshot

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /uptime-monitors/{monitor_id}/web-snapshot`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/web-snapshot`

## Description

API call used to get an uptime monitor's Web Snapshot for a specific downtime.

A downtime may not have a Web Snapshot. If no usable snapshot is available, including when capture is pending or has failed, the endpoint returns `200` with `web_snapshot` set to `null`.

The screenshot and content URLs include a daily access key; request this endpoint again when you need fresh URLs.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor id, which can be found by running the [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) API. |
| `downtime_id` | query | string | oui | The unique downtime id, which can be found by running the [GET - Downtimes](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors~1{monitor_id}~1downtimes/get) API for this monitor.  The downtime must belong to the specified monitor. Missing, malformed, unknown, or mismatched downtime ids return `400`. |

## Réponses

### 200 — Successful Response. Returns a snapshot object or null when no snapshot is available.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `web_snapshot` | object | null | oui | The available Web Snapshot, or `null` when no usable snapshot is available for this downtime. At least one of the screenshot or content URLs is non-null when this object is returned. |
| `web_snapshot.captured_at` | integer | null (int64) | oui | Unix timestamp in seconds when the snapshot was captured, or `null` when the capture time is unavailable. |
| `web_snapshot.http_code` | integer | oui | The HTTP status code captured from the monitored website. |
| `web_snapshot.screenshot_url` | string | null (uri) | oui | The HTTPS URL of the captured screenshot on `ws.hetrix.io`, including its access key. Returns `null` when no screenshot is available. |
| `web_snapshot.content_url` | string | null (uri) | oui | The HTTPS URL of the captured page content on `ws.hetrix.io`, including its access key. Returns `null` when no content file is available. |

_available_ :

```json
{
  "web_snapshot": {
    "captured_at": 1641909671,
    "http_code": 503,
    "screenshot_url": "https://ws.hetrix.io/example.png?k=0123456789abcdef0123456789abcdef01234567",
    "content_url": "https://ws.hetrix.io/example.txt?k=0123456789abcdef0123456789abcdef01234567"
  }
}
```

_unavailable_ :

```json
{
  "web_snapshot": null
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
