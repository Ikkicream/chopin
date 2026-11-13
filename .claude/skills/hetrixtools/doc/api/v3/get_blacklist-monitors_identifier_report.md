# GET /blacklist-monitors/{identifier}/report — Blacklist Report

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /blacklist-monitors/{identifier}/report`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/blacklist-monitors/{identifier}/report`

## Description

API call used to get the blacklist report for a specific blacklist monitor.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `identifier` | path | string | oui | The blacklist monitor identifier; can be the 32 characters long monitor ID, the IP address or the hostname of the blacklist monitor. |
| `date` | query | string |  | Report date in `YYYY-MM-DD` format. Defaults to the current date. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `id` | string |  | The unique blacklist monitor ID. |
| `name` | string |  | The blacklist monitor's name. |
| `type` | string enum ['ipv4', 'domain'] |  | The type of blacklist monitor. |
| `target` | string |  | The monitored target. |
| `report_id` | string |  | The unique blacklist report ID for this blacklist monitor. Can be used to form the non white-label report URL: `https://hetrixtools.com/report/blacklist/{report_id}/` and the white-label report URL: `https://yourdomain.com/report/blacklist/{report_id}/`. |
| `listed` | array |  | The array of blacklists that have listed the monitored target on the requested date. |
| `listed[].rbl` | string |  | The RBL name. |
| `listed[].delist` | string |  | The delist URL for this RBL. |

```json
{
  "id": "3f1b14944123c3878d9a372d54c3e003",
  "name": "my-monitor",
  "type": "ipv4",
  "target": "203.0.113.1",
  "report_id": "abcdef1234567890abcdef1234567890",
  "listed": [
    {
      "rbl": "all.spamrats.com",
      "delist": "http://www.spamrats.com/lookup.php?ip=203.0.113.1"
    },
    {
      "rbl": "b.barracudacentral.org",
      "delist": "http://www.barracudacentral.org/rbl/removal-request/203.0.113.1"
    },
    {
      "rbl": "zen.spamhaus.org",
      "delist": "https://check.spamhaus.org/results/?query=203.0.113.1"
    }
  ]
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
