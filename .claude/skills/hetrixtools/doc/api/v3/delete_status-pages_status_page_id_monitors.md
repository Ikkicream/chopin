# DELETE /status-pages/{status_page_id}/monitors — Status Pages - Monitors

> Source : https://docs.hetrixtools.com/api/v3/ (opération `DELETE /status-pages/{status_page_id}/monitors`) — spec api.yaml?v=170, aspirée le 2026-09-26

`DELETE https://api.hetrixtools.com/v3/status-pages/{status_page_id}/monitors`

## Description

API call used to remove monitors from a status page.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `status_page_id` | path | string | oui | The unique status page id, which can be found in the URL of each status page, in your [HetrixTools account](https://hetrixtools.com/dashboard/status-pages/). Example: `https://hetrixtools.com/r/{status_page_id}/` |

## Corps de la requête

Content-Type : `application/json`

_(pas de schéma détaillé)_

## Réponses

### 200 — Successful Response.

_(pas de schéma détaillé)_

```json
{
  "status": "success",
  "message": "x monitor(s) removed from status page"
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
