# GET /account/api/scope — API Scope

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /account/api/scope`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/account/api/scope`

## Description

API call used to get the scope of the API key making the request: the API calls it is allowed to perform and, when it has been limited to specific assets, which assets.

An API key's scope is configured from your dashboard, see [API Scope](https://docs.hetrixtools.com/api-key-scope/). This endpoint can be called with any API key, regardless of the API calls or assets that key has been limited to, so it can always be used to find out what the key is allowed to do.

- `access` is `full` when the API key has not been limited to specific API calls, meaning it can perform any API call, or `restricted` when it has.
- `api_calls` lists the API calls a `restricted` key is allowed to perform, by the names used when configuring the API key's access in your dashboard. It is empty for a key with `full` access.
- `assets` is `null` unless the API key has been limited to specific assets, in which case it holds the type of those assets and their IDs. Only assets that still exist are listed. Their names and details are available through the corresponding list endpoint, when the key is allowed to use it.

This endpoint is not paginated.

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `access` | string enum ['full', 'restricted'] | oui | Whether the API key can perform any API call (`full`) or only the ones listed in `api_calls` (`restricted`). |
| `api_calls` | array | oui | The names of the API calls the key is allowed to perform, as used when configuring the API key's access in your dashboard. Empty when `access` is `full`. |
| `assets` | object | null | oui | The assets the API key is limited to, or `null` when it is not limited to specific assets. |
| `assets.type` | string enum ['uptime_monitors', 'blacklist_monitors', 'contact_lists', 'status_pages'] | oui | The type of the assets the API key is limited to. |
| `assets.ids` | array | oui | The IDs of the assets the API key is limited to, as returned in the `id` field of the corresponding list endpoint. Assets deleted since the key was configured are not listed. |

_restricted_ :

```json
{
  "access": "restricted",
  "api_calls": [
    "v3 Uptime Monitors",
    "v3 Uptime Report",
    "v3 Downtimes"
  ],
  "assets": {
    "type": "uptime_monitors",
    "ids": [
      "0123456789abcdef0123456789abcdef",
      "123456789abcdef0123456789abcdef0"
    ]
  }
}
```

_full_ :

```json
{
  "access": "full",
  "api_calls": [],
  "assets": null
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
