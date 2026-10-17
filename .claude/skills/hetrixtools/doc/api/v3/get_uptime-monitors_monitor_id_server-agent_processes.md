# GET /uptime-monitors/{monitor_id}/server-agent/processes — Running Processes

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /uptime-monitors/{monitor_id}/server-agent/processes`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/server-agent/processes`

## Description

API call used to get the latest running processes snapshot collected by an uptime monitor's Server Monitoring Agent.

The [View Running Processes](https://docs.hetrixtools.com/view-running-processes/) option must be enabled on the Server Monitoring Agent in order for this data to be collected. The snapshot is refreshed with every agent data post, and this API call will return a `404` response if no recent running processes data is found for the specified monitor.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor id, which can be found by running the [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) API. |
| `per_page` | query | integer default=20 minimum=1 maximum=200 |  | Number of processes returned per page. |
| `page` | query | integer default=1 minimum=1 maximum=10000 |  | Which page of the paginated results to return. |
| `order_by` | query | string enum=['cpu', 'ram'] default=cpu |  | Which usage metric to order the processes by. |
| `order` | query | string enum=['desc', 'asc'] default=desc |  | The direction to order the processes in. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `processes` | array |  |  |
| `processes[].pid` | integer |  | The process ID. |
| `processes[].ppid` | integer |  | The parent process ID. |
| `processes[].uid` | integer |  | The user ID of the process owner. |
| `processes[].user` | string |  | The username of the process owner. |
| `processes[].elapsed` | integer |  | The number of seconds the process has been running for. |
| `processes[].cpu` | number |  | The CPU usage (percent) of the process, normalized by the number of CPU cores. |
| `processes[].ram` | number |  | The RAM usage (percent) of the process. |
| `processes[].process` | string |  | The process name. |
| `processes[].command` | string |  | The full command the process has been started with. |
| `meta` | object |  |  |
| `meta.total` | integer |  | The total number of running processes in the latest snapshot. |
| `meta.returned` | integer |  | The number of processes returned by the API call. |
| `meta.last_updated` | integer |  | The timestamp when the running processes snapshot was last updated. |
| `meta.pagination` | object |  |  |
| `meta.pagination.current` | integer |  | The current page number. |
| `meta.pagination.last` | integer |  | The last available page number. |
| `meta.pagination.previous` | integer | null |  | The previous page number; `null` returned if no previous pages available. |
| `meta.pagination.next` | integer | null |  | The next page number; `null` returned if no further pages available. |

```json
{
  "processes": [
    {
      "pid": 1863,
      "ppid": 1,
      "uid": 112,
      "user": "mysql",
      "elapsed": 172800,
      "cpu": 25.75,
      "ram": 17.3,
      "process": "mysqld",
      "command": "/usr/sbin/mysqld"
    },
    {
      "pid": 850,
      "ppid": 1,
      "uid": 0,
      "user": "root",
      "elapsed": 172811,
      "cpu": 1.2,
      "ram": 2.5,
      "process": "fail2ban-server",
      "command": "/usr/bin/python3 /usr/bin/fail2ban-server -xf start"
    }
  ],
  "meta": {
    "total": 132,
    "returned": 2,
    "last_updated": 1641909671,
    "pagination": {
      "current": 1,
      "last": 66,
      "previous": null,
      "next": 2
    }
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


Sécurité : `[{'bearerAuth': []}]`
