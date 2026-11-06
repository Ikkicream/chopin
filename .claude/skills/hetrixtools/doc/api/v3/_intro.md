# HetrixTools API v3 — introduction (Redoc)

> Source : https://docs.hetrixtools.com/api/v3/ (spec : https://docs.hetrixtools.com/api/v3/api.yaml?v=170)

# Introduction
The HetrixTools v3 API is a REST API which you can use to programmatically perform different CRUD (create, retrieve, update, delete) operations on your HetrixTools account.

## Request Methods

|Method|Usage|
|--- |--- |
|GET|Used to retrieve information as a JSON object.|
|POST|Used to create a new object.|
|PUT|Used to update an existing object.|
|DELETE|Used to delete an existing object.|

## HTTP Statuses

|Code|Meaning|
|--- |--- |
|200|Successful Request - object(s) returned.|
|204|No Content - the request was performed successfully, but there was no content found/returned.|
|400|Bad Request - the API request is invalid or formatted wrong.|
|401|Unauthorized - invalid authorization method, missing or invalid bearer token.|
|403|Forbidden - the specified API key (bearer token) does not have access to perform the requested action. [Learn how to configure your API key's scope](https://docs.hetrixtools.com/api-key-scope/).|
|404|Not Found - the resource you have requested was not found.|
|429|Rate Limited - you are performing API requests too frequently.|
|5xx|Server Error - our API server either encountered an internal error or is unable to serve your API request at this time.|

## Rate Limiting
Our API has two types of rate limiting:
 - Per user - your account can only perform a maximum number of API calls per minute or per hour, based on your pricing plan.
 - Per endpoint - some endpoints may have their own rate limiting, which is not affected by the user's pricing plan.
 
If you ever hit any of the rate limits, you will receive the `429` HTTP response code.

### User Response Headers
```
ratelimit-limit-user: 200
ratelimit-remaining-user: 199
ratelimit-reset-user: 1640005680
```

### Endpoint Response Headers
```
ratelimit-limit-endpoint: 100
ratelimit-remaining-endpoint: 99
ratelimit-reset-endpoint: 1640005680
```

### Response Headers Explained
- **ratelimit-limit-{user/endpoint}** - the maximum limit of API calls that can be performed
- **ratelimit-remaining-{user/endpoint}** - the remaining number of API calls that can be performed until the reset time
- **ratelimit-reset-{user/endpoint}** - the time when the two values listed above will reset

### Rate Limiting Sample Response
```
429 Too Many Requests
{
  "status": "too_many_requests",
  "message": "user api rate limit exceeded"
}
```


## Authentification (securitySchemes.bearerAuth)

## Getting The API Key (Bearer Token)
This can be obtained from your HetrixTools account at the following link: [https://hetrixtools.com/dashboard/account/api/](https://hetrixtools.com/dashboard/account/api/)

## Using The API Key (Bearer Token)
Include your API Key (Bearer Token) in the `Authorization` header with all of your API requests, as shown in the example below.
```
curl -X GET -H "Authorization: Bearer {BEARER_TOKEN}" "https://api.hetrixtools.com/v3/{ENDPOINT}"
```

## Réponses d'erreur communes (components.responses)

### NoContentMsg

No Content - API request returned no content.

### BadRequestError

Bad Request - API request is invalid or not properly formatted.

```json
{
  "status": "bad_request",
  "message": "invalid endpoint"
}
```

### UnauthorizedError

Unauthorized - Missing or invalid authentication API key (bearer token).

```json
{
  "status": "unauthorized",
  "message": "invalid authorization"
}
```

### ForbiddenError

Forbidden - Your API key does not have access to perform this request.

```json
{
  "status": "forbidden",
  "message": "api key not allowed to perform this action"
}
```

### ConflictError

Conflict - The request could not be completed due to a conflict with the current state of the resource.

```json
{
  "status": "conflict",
  "message": "resource already exists or is in an invalid state"
}
```

### NotFoundError

Not Found - The resource you have requested was not found.

```json
{
  "status": "not_found",
  "message": "error message"
}
```

### RateLimitedError

Rate Limited - You are performing API requests too frequently.

```json
{
  "status": "too_many_requests",
  "message": "user api rate limit exceeded"
}
```

### InternalServerError

Internal Server Error - An error occurred on the server.

```json
{
  "status": "internal_server_error",
  "message": "unexpected error occurred"
}
```

### ServiceUnavailableError

Service Unavailable - A temporary server error prevented the request from completing.

```json
{
  "status": "service_unavailable",
  "message": "temporary server error, please retry"
}
```

