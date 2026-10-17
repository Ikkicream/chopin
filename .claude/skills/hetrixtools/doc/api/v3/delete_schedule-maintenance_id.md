# DELETE /schedule-maintenance/{id} — Schedule Maintenance

> Source : https://docs.hetrixtools.com/api/v3/ (opération `DELETE /schedule-maintenance/{id}`) — spec api.yaml?v=170, aspirée le 2026-09-26

`DELETE https://api.hetrixtools.com/v3/schedule-maintenance/{id}`

## Description

API call used to delete an existing scheduled maintenance.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `id` | path | string | oui | The unique schedule maintenance ID. |

## Réponses

### 200 — Successful Response.

_(pas de schéma détaillé)_

```json
{
  "status": "success",
  "message": "scheduled maintenance removed"
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
