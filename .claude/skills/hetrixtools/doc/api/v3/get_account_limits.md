# GET /account/limits — Account Limits

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /account/limits`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/account/limits`

## Description

API call used to get the current usage and limits for your HetrixTools account.
This endpoint is not paginated.

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `uptime` | object |  |  |
| `uptime.monitors` | object |  |  |
| `uptime.monitors.usage` | integer |  | The current number of uptime monitors in use. |
| `uptime.monitors.limit` | integer |  | The maximum number of uptime monitors allowed. |
| `blacklist` | object |  |  |
| `blacklist.monitors` | object |  |  |
| `blacklist.monitors.usage` | integer |  | The current number of blacklist monitors in use. |
| `blacklist.monitors.limit` | integer |  | The maximum number of blacklist monitors allowed. |
| `blacklist.api_check_credits` | object |  |  |
| `blacklist.api_check_credits.usage` | integer |  | The number of blacklist API checks used this month (plan + extra credits). |
| `blacklist.api_check_credits.limit` | integer |  | The total number of blacklist API checks available this month (plan + extra credits). |
| `blacklist.api_check_credits.details` | object |  |  |
| `blacklist.api_check_credits.details.monthly_from_plans` | integer |  | The number of monthly blacklist API checks included in your plan(s). |
| `blacklist.api_check_credits.details.extra_credits` | integer |  | Extra purchased blacklist API check credits. |
| `sub_accounts` | object |  |  |
| `sub_accounts.usage` | integer |  | The current number of sub-accounts and pending invites. |
| `sub_accounts.limit` | integer |  | The maximum number of sub-accounts allowed. |
| `sms_credits` | object |  |  |
| `sms_credits.usage` | integer |  | The number of SMS credits used this month (plan + extra credits). |
| `sms_credits.limit` | integer |  | The total number of SMS credits available this month (plan + extra credits). |
| `sms_credits.details` | object |  |  |
| `sms_credits.details.monthly_from_plans` | integer |  | The number of monthly SMS credits included in your plan(s). |
| `sms_credits.details.extra_credits` | integer |  | Extra purchased SMS credits. |
| `account_credit` | object |  |  |
| `account_credit.balance` | number (float) |  | The current prepaid account credit balance. |
| `api_v1_v2` | object |  |  |
| `api_v1_v2.usage` | integer |  | The number of v1/v2 API calls used this month. |
| `api_v1_v2.limit` | integer |  | The maximum number of v1/v2 API calls allowed per month. |

```json
{
  "uptime": {
    "monitors": {
      "usage": 12,
      "limit": 50
    }
  },
  "blacklist": {
    "monitors": {
      "usage": 3,
      "limit": 20
    },
    "api_check_credits": {
      "usage": 40,
      "limit": 100,
      "details": {
        "monthly_from_plans": 100,
        "extra_credits": 0
      }
    }
  },
  "sub_accounts": {
    "usage": 1,
    "limit": 5
  },
  "sms_credits": {
    "usage": 2,
    "limit": 50,
    "details": {
      "monthly_from_plans": 50,
      "extra_credits": 0
    }
  },
  "account_credit": {
    "balance": 12.5
  },
  "api_v1_v2": {
    "usage": 300,
    "limit": 1000
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
