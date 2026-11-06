# GET /account/activity-log — Activity Log

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /account/activity-log`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/account/activity-log`

## Description

API call used to get the [Activity Log](https://docs.hetrixtools.com/activity-log/).

Entries are returned newest first, within your account's plan retention period. Recent activity may take a short time to appear.

Use `exclude_browsing` to hide navigation activity and `search` to filter the results. No matches returns HTTP 200 with an empty `entries` array.

The `info` field contains free-form details intended for human review. Its structure is not part of the stable API contract; clients should display it generically and should not depend on specific properties or text for automated processing.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `per_page` | query | integer default=20 minimum=1 maximum=200 |  | Number of activity entries returned per page. Invalid values fall back to 20. |
| `page` | query | integer default=1 minimum=1 maximum=10000 |  | Which page of the paginated results to return. Invalid values fall back to 1. A page beyond the available results returns an empty entries array. |
| `exclude_browsing` | query | integer enum=[0, 1] default=0 |  | Set to 1 to exclude navigation activity, or 0 to include it. Other values return HTTP 400. |
| `search` | query | string default= |  | Space-separated search terms. Every term must match at least one of the following: a date prefix, an exact sub-account ID, an exact IP address, or part of the action text or extra details.  Accepts letters, numbers, spaces, colons, dots, and dashes, with a maximum of 128 bytes after trimming and 10 terms. Encode spaces as `%20`. Invalid searches return HTTP 400; an empty search applies no search filter. |

## Réponses

### 200 — Successful Response.

- en-tête `Cache-Control` : Activity Log responses must not be cached.
| Champ | Type | Requis | Description |
|---|---|---|---|
| `entries` | array | oui | Activity entries for the requested page, ordered newest first. Empty when no matching entries are available on that page. |
| `entries[].timestamp` | integer (int64) | oui | When the activity occurred, as a Unix timestamp in seconds. |
| `entries[].type` | integer enum [0, 1] | oui | Activity type: 0 for an action, 1 for browsing or navigation. |
| `entries[].account` | object | oui | The account that owns the activity entry. |
| `entries[].account.id` | string | oui | The account's unique ID. |
| `entries[].account.name` | string | oui | The account's display name. |
| `entries[].sub_account` | object | null | oui | The sub-account that performed the activity, or null when performed by the main account. Deleted sub-accounts retain their ID and have an empty name. |
| `entries[].sub_account.id` | string | oui | The sub-account's unique ID. |
| `entries[].sub_account.name` | string | oui | The sub-account's display name, or an empty string if unavailable. |
| `entries[].ip` | string | oui | The IP address as displayed in the dashboard. IPv6 addresses use a normalized /64 prefix; local activity without a recorded IP returns local. Demo-account IPs are obfuscated. |
| `entries[].action` | string | oui | A human-readable description of the activity. |
| `entries[].info` |  | oui | Additional details intended for human review. May contain an object, array, string, or `null` when no details are available.  Its contents and structure vary by activity and may change over time. Field names, nesting, and value types are not part of the stable API contract. Clients should display this field generically and should not depend on specific properties or text for automated processing. Response examples are illustrative and do not define a schema for this field. |
| `meta` | object | oui |  |
| `meta.total` | integer | oui | The total number of visible entries within the retention period, before applying search or browsing filters. |
| `meta.total_filtered` | integer | oui | The total number of visible entries after applying search and browsing filters. |
| `meta.returned` | integer | oui | The number of entries returned in this response. |
| `meta.retention_days` | integer | oui | The Activity Log retention period, in days, available to this account. |
| `meta.pagination` | object | oui |  |
| `meta.pagination.current` | integer | oui | The current page number. |
| `meta.pagination.last` | integer | oui | The last available page number after filtering, or 0 when there are no matching entries. |
| `meta.pagination.previous` | integer | null | oui | The previous available page number, or null on the first page or when there are no matching entries. |
| `meta.pagination.next` | integer | null | oui | The next page number, or null when no further pages are available. |

```json
{
  "entries": [
    {
      "timestamp": 1789732800,
      "type": 0,
      "account": {
        "id": "0123456789abcdef0123456789abcdef",
        "name": "Example Account"
      },
      "sub_account": {
        "id": "fedcba9876543210fedcba9876543210",
        "name": "Team Member"
      },
      "ip": "2001:db8:1234:5678::/64",
      "action": "Updated uptime monitor.",
      "info": {
        "Keyword": "ready"
      }
    },
    {
      "timestamp": 1789732740,
      "type": 1,
      "account": {
        "id": "0123456789abcdef0123456789abcdef",
        "name": "Example Account"
      },
      "sub_account": null,
      "ip": "192.0.2.10",
      "action": "Accessed dashboard.",
      "info": null
    }
  ],
  "meta": {
    "total": 2,
    "total_filtered": 2,
    "returned": 2,
    "retention_days": 30,
    "pagination": {
      "current": 1,
      "last": 1,
      "previous": null,
      "next": null
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
