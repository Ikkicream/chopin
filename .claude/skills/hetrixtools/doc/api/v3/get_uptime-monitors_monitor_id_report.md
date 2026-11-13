# GET /uptime-monitors/{monitor_id}/report — Uptime Report

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /uptime-monitors/{monitor_id}/report`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/report`

## Description

API call used to get the uptime report for a specific uptime monitor.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor ID. |
| `days` | query | integer default=7 minimum=1 maximum=30 |  | Number of recent days to display (1-30). Defaults to 7. |
| `month` | query | string |  | The month to display the uptime report for, in YYYY-MM format. If specified, `days` has no effect. |
| `timezone` | query | string |  | The timezone used for the report (e.g., +02:00 or -5:30). Defaults to +00:00 (UTC). |
| `hourly_stats` | query | boolean default=False |  | Whether to include hourly stats for website uptime monitors. Defaults to false. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `timezone` | string |  | The timezone used in the report. |
| `data` | object |  |  |
| `data.<clé>.uptime` | object |  |  |
| `data.<clé>.uptime.percentage` | number (float) |  | Uptime percentage excluding maintenance. |
| `data.<clé>.uptime.percentage_incl_maint` | number (float) |  | Uptime percentage including maintenance. |
| `data.<clé>.uptime.downtimes` | integer |  | Number of recorded downtimes. |
| `data.<clé>.uptime.downtimes_incl_maint` | integer |  | Number of recorded downtimes including maintenance. |
| `data.<clé>.response_time` | object |  |  |
| `data.<clé>.hourly_stats` | object |  | Hourly stats for website uptime monitors. |
| `summary` | object |  |  |
| `summary.uptime` | object |  |  |
| `summary.uptime.percentage` | number (float) |  | Overall uptime percentage. |
| `summary.uptime.percentage_incl_maint` | number (float) |  | Overall uptime percentage including maintenance. |
| `summary.uptime.downtimes` | integer |  | Total number of downtimes recorded. |
| `summary.uptime.downtimes_incl_maint` | integer |  | Total number of downtimes including maintenance. |
| `summary.response_time` | object |  |  |
| `history` | object |  | Historical uptime data for all available months. |
| `history.<clé>.uptime` | object |  |  |
| `history.<clé>.uptime.percentage` | number (float) |  | Uptime percentage for that month. |
| `history.<clé>.uptime.percentage_incl_maint` | number (float) |  | Uptime percentage including maintenance for that month. |

```json
{
  "timezone": "UTC+02:00",
  "data": {
    "2025-02-24": {
      "uptime": {
        "percentage": 81.9444,
        "percentage_incl_maint": 81.9444,
        "downtimes": 3,
        "downtimes_incl_maint": 3
      },
      "response_time": {
        "frankfurt": 131.74,
        "singapore": 586.48
      },
      "hourly_stats": {
        "00": {
          "frankfurt": {
            "dns_lookup": 8.51,
            "tcp_connect": 15.31,
            "tls_connect": 86.8,
            "ttfb": 28.61,
            "download": 0.14,
            "total": 139.37
          },
          "singapore": {
            "dns_lookup": 3.13,
            "tcp_connect": 189.97,
            "tls_connect": 211.13,
            "ttfb": 196.84,
            "download": 0.21,
            "total": 601.28
          }
        }
      }
    }
  },
  "summary": {
    "uptime": {
      "percentage": 81.9444,
      "percentage_incl_maint": 81.9444,
      "downtimes": 3,
      "downtimes_incl_maint": 3
    },
    "response_time": {
      "frankfurt": 131.74,
      "singapore": 586.48
    }
  },
  "history": {
    "2025-02": {
      "uptime": {
        "percentage": 79.0377,
        "percentage_incl_maint": 79.0377
      }
    },
    "2025-01": {
      "uptime": {
        "percentage": 91.9758,
        "percentage_incl_maint": 91.9758
      }
    },
    "2024-12": {
      "uptime": {
        "percentage": 81.1895,
        "percentage_incl_maint": 81.1895
      }
    },
    "2024-11": {
      "uptime": {
        "percentage": 74.1898,
        "percentage_incl_maint": 74.1898
      }
    },
    "2024-10": {
      "uptime": {
        "percentage": 95.7348,
        "percentage_incl_maint": 95.7348
      }
    },
    "2024-09": {
      "uptime": {
        "percentage": 99.9051,
        "percentage_incl_maint": 99.9051
      }
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
