# GET /uptime-monitors/{monitor_id}/location-fail-log — Location Fail Log

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /uptime-monitors/{monitor_id}/location-fail-log`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/location-fail-log`

## Description

API call used to get an uptime monitor's Location Fail Log.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor id, which can be found by running the [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) API. |
| `timestamp` | query | integer |  | The timestamp when to start scanning for log entries. If no timestamp is provided, the scanning will start at the current timestamp. |
| `minutes` | query | integer default=10 minimum=1 maximum=100 |  | The number of minutes containing log entries to get. Minutes without log entries are not counted/considered, and each minute may contain multiple log entries.   *Example:* A value of `10` will scan through the logs, in a descending order starting from the `timestamp`, until it finds 10 different minutes containing log entries. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `entries` | array |  |  |
| `entries[].timestamp` | integer |  | Timestamp at which this error has been encountered by the monitoring node. |
| `entries[].location` | string |  | The location and the specific monitoring node from that location that has logged in the error. |
| `entries[].data` | string |  | The exact error that has been encountered by the monitoring node. |
| `meta` | object |  |  |
| `meta.returned` | integer |  | The number of log entries that have been returned by this API call. |
| `meta.start_timestamp` | integer |  | The timestamp from which scanning for log entries began. |
| `meta.end_timestamp` | integer |  | The timestamp until which scanning for log entries has run down to. |
| `meta.next_page_timestamp` | integer | null |  | The timestamp you'll need to put in this API's `timestamp` optional query parameter in order to get the next page of entries; returns `null` if there are no next pages of log entries. |

```json
{
  "entries": [
    {
      "timestamp": 1641909671,
      "location": "London 6",
      "data": "Error 28: Connection timed out after 10001 milliseconds (10001ms)"
    },
    {
      "timestamp": 1641588609,
      "location": "Amsterdam 1",
      "data": "Error 28: Connection timed out after 10001 milliseconds (10001ms)"
    }
  ],
  "meta": {
    "returned": 2,
    "start_timestamp": 1641926870,
    "end_timestamp": 1641588600,
    "next_page_timestamp": 1641588599
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


Sécurité : `[{'bearerAuth': []}]`
