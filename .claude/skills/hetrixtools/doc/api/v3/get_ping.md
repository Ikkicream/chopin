# GET /ping — Ping

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /ping`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/ping`

## Description

API call used to check that the API is available and functioning as expected.

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `status` | string enum ['ok'] | oui | Always `ok` on a successful response. |
| `message` | string enum ['pong'] | oui | Always `pong` on a successful response. |

```json
{
  "status": "ok",
  "message": "pong"
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

### 503 — Service Unavailable - The API is temporarily unavailable; retry shortly.

```json
{
  "status": "service_unavailable",
  "message": "service temporarily unavailable"
}
```


Sécurité : `[{'bearerAuth': []}]`
