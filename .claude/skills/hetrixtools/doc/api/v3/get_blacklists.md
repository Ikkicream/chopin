# GET /blacklists — Blacklists

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /blacklists`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/blacklists`

## Description

API call used to get the list of blacklists (RBLs) checked by our platform.

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `ipv4` | array |  |  |
| `ipv4[].id` | string |  | The unique identifier for the RBL entry. |
| `ipv4[].rbl` | string |  | The RBL (Real-time Blackhole List) name. |
| `ipv4[].optional` | boolean |  | Whether the RBL is optional (opt-in). |
| `ipv4[].ignored` | boolean |  | Whether the RBL is ignored. |
| `domains` | array |  |  |
| `domains[].id` | string |  | The unique identifier for the RBL entry. |
| `domains[].rbl` | string |  | The RBL (Real-time Blackhole List) name. |
| `domains[].optional` | boolean |  | Whether the RBL is optional (opt-in). |
| `domains[].ignored` | boolean |  | Whether the RBL is ignored. |

```json
{
  "ipv4": [
    {
      "id": "hostkarma.junkemailfilter.com",
      "rbl": "hostkarma.junkemailfilter.com",
      "optional": false,
      "ignored": false
    },
    {
      "id": "invaluement_sip",
      "rbl": "invaluement SIP",
      "optional": false,
      "ignored": false
    },
    {
      "id": "invaluement_sip_24",
      "rbl": "invaluement SIP/24",
      "optional": false,
      "ignored": false
    },
    {
      "id": "nordspam",
      "rbl": "NordSpam",
      "optional": false,
      "ignored": false
    },
    {
      "id": "ips.backscatterer.org",
      "rbl": "ips.backscatterer.org",
      "optional": false,
      "ignored": false
    }
  ],
  "domains": [
    {
      "id": "dnsbl.spfbl.net",
      "rbl": "dnsbl.spfbl.net",
      "optional": false,
      "ignored": false
    },
    {
      "id": "phishtank",
      "rbl": "PhishTank",
      "optional": false,
      "ignored": false
    },
    {
      "id": "nordspam",
      "rbl": "NordSpam",
      "optional": false,
      "ignored": false
    },
    {
      "id": "hostkarma.junkemailfilter.com",
      "rbl": "hostkarma.junkemailfilter.com",
      "optional": false,
      "ignored": false
    },
    {
      "id": "invaluement_uri",
      "rbl": "invaluement URI",
      "optional": false,
      "ignored": false
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

### 429 — Rate Limited - You are performing API requests too frequently.

```json
{
  "status": "too_many_requests",
  "message": "user api rate limit exceeded"
}
```


Sécurité : `[{'bearerAuth': []}]`
