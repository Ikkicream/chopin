# GET /uptime-monitors — Uptime Monitors

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /uptime-monitors`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/uptime-monitors`

## Description

API call used to get uptime monitors and their details.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `per_page` | query | integer default=20 minimum=1 maximum=200 |  | Number of monitors returned per page. |
| `page` | query | integer default=1 minimum=1 maximum=10000 |  | Which page of the paginated results to return. |
| `id` | query | string |  | Filter results by monitor ID. This will fetch just the monitor with the specified ID and ignore the name, target, and category filters. Other filters, including private_notes_search, still apply. |
| `name` | query | string |  | Filter results by name (accepts partial or full name). |
| `target` | query | string |  | Filter results by monitored target (accepts partial or full target). |
| `category` | query | string |  | Filter results by category (accepts partial or full category name). |
| `private_notes_search` | query | string |  | Filter results by private note content. Matching is case-insensitive, and every space-separated term must occur as a substring in the notes, in any order. For example, `prod db` matches notes containing both `prod` and `db`.  Accepts 1-64 ASCII bytes after trimming leading and trailing spaces. Allowed characters are letters, numbers, spaces, dots (`.`), dashes (`-`), and colons (`:`), with at least one letter or number required. Encode spaces as `%20` or `+`; a literal plus sign (`%2B`) is not supported as a search character. An empty value, a repeated `private_notes_search` parameter, an array value, or another invalid value returns `400`.  Requires both the GET Uptime Monitors and GET Private Notes API-key permissions. Private note text is not included in the response. This filter also applies when `id` is provided, and pagination and `meta.total_filtered` reflect the matching monitors. Recent note changes may take a short time to appear in search results. |
| `type` | query | string enum=['website', 'ping', 'service', 'smtp', 'heartbeat'] |  | Filter results by monitor type. |
| `uptime_status` | query | string enum=['up', 'down'] |  | Filter results by uptime status. |
| `monitor_status` | query | string enum=['active', 'paused', 'disabled', 'maint', 'maint_dnd'] |  | Filter results by monitor status. |
| `order` | query | string enum=['asc', 'desc'] |  | Order results ascending or descending. |
| `order_by` | query | string enum=['name', 'created_at', 'last_check', 'last_status_change', 'uptime_status', 'monitor_status'] |  | Order results by a specific field. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `monitors` | array |  |  |
| `monitors[].id` | string |  | The unique uptime monitor ID. |
| `monitors[].name` | string |  | The uptime monitor's name. |
| `monitors[].type` | string enum ['website', 'ping', 'service', 'smtp', 'heartbeat'] |  | The type of uptime monitor. |
| `monitors[].target` | string | null |  | The monitored target; `null` returned for `heartbeat` uptime monitors. |
| `monitors[].resolve_address` | string |  | The IP address (IPv4 or IPv6) that the monitored target is resolved to by our platform. In the case of the `heartbeat` monitor type, this is the IP address that is sending server agent data towards our platform. |
| `monitors[].resolve_address_info` | object |  | Extra info related to the resolving IP address. |
| `monitors[].resolve_address_info.ASN` | string |  |  |
| `monitors[].resolve_address_info.ISP` | string |  |  |
| `monitors[].resolve_address_info.City` | string |  |  |
| `monitors[].resolve_address_info.Region` | string |  |  |
| `monitors[].resolve_address_info.Country` | string |  |  |
| `monitors[].port` | integer | null |  | The monitored port; `null` returned for `website`, `ping`, and `heartbeat` uptime monitors. |
| `monitors[].keyword` | string | null |  | The keyword to look for on the monitored website; returns `null` non `website` monitor types. |
| `monitors[].category` | string |  | The category name assigned to this uptime monitor. |
| `monitors[].timeout` | integer |  | The number of seconds the monitored target has to respond before considered 'down'. |
| `monitors[].grace` | integer |  | Only for Heartbeat Uptime Monitors. Represents the number of seconds above the timeout before considered 'down'. |
| `monitors[].heartbeat_type` | string enum ['server_agent', 'cron_job'] |  | Only for Heartbeat Uptime Monitors. `server_agent` for monitors fed by the Server Monitoring Agent, `cron_job` for monitors fed by a cron job pinging its heartbeat URL. |
| `monitors[].cron_expression` | string | null |  | Only for Heartbeat Uptime Monitors. The Linux cron expression (5 fields) the heartbeat is expected on when it uses an advanced (cron expression) schedule; `null` for a simple (interval) schedule. With a cron expression schedule, `timeout` returns `0` and the monitor is considered 'down' when no heartbeat arrives within `grace` seconds after a scheduled run. |
| `monitors[].cron_timezone` | string | null |  | Only for Heartbeat Uptime Monitors. The time zone (IANA identifier, e.g. `America/New_York`) used to evaluate `cron_expression`; `null` for a simple (interval) schedule. |
| `monitors[].check_frequency` | integer enum [1, 3, 5, 10] | null |  | The frequency (in minutes) that the uptime monitor is checked at. |
| `monitors[].contact_lists` | array |  | The unique contact list IDs assigned to this uptime monitor. Currently supporting a maximum of one contact list ID per uptime monitor. |
| `monitors[].created_at` | integer |  | Timestamp when the uptime monitor was created. |
| `monitors[].last_check` | integer |  | Timestamp when the uptime monitor was last checked. |
| `monitors[].last_status_change` | integer |  | Timestamp when the uptime monitor's `uptime_status` has changed. |
| `monitors[].uptime_status` | string enum ['up', 'down'] |  | The monitor's current overall uptime status. |
| `monitors[].monitor_status` |  enum ['active', 'paused', 'disabled', 'maint', 'maint_dnd'] |  | The current status of this uptime monitor. - `active` - the normal status, when the monitor is not under maintenance - `paused` - the monitor is paused and not checked at all (currently unavailable, still under development) - `disabled` - the monitor is not checked at all - `maint` - the monitor is under maintenance mode with notifications enabled - `maint_dnd` - the monitor is under maintenance mode without notifications [Learn more here](https://docs.hetrixtools.com/maintenance-mode/). |
| `monitors[].uptime` | string |  | The overall uptime percentage, not including downtimes during maintenance. |
| `monitors[].uptime_incl_maint` | string |  | The overall uptime percentage, including downtimes during maintenance. |
| `monitors[].locations` | array |  | The array of locations that monitor this specific uptime monitor. Possible entries are `new_york`, `san_francisco`, `dallas`, `amsterdam`, `london`, `frankfurt`, `singapore`, `sydney`, `sao_paulo`, `tokyo`, `mumbai`, `moscow`. |
| `monitors[].locations[].new_york` | array |  |  |
| `monitors[].locations[].new_york[].uptime_status` | string enum ['up', 'down'] |  | The last uptime status as observed by this specific location. |
| `monitors[].locations[].new_york[].response_time` | integer |  | The last response time from this specific location in `milliseconds`. |
| `monitors[].locations[].new_york[].last_check` | integer |  | The timestamp of the last checkup from this specific location. |
| `monitors[].ssl_expiration_date` | string | null |  | The SSL expiration date for the monitored hostname; returns `null` if unavailable. |
| `monitors[].ssl_expiration_warn` | boolean |  | Whether or not the SSL expiration warning is enabled. |
| `monitors[].ssl_expiration_warn_days` | integer |  | The number of days before the SSL expiration when the warning is triggered. |
| `monitors[].domain_expiration_date` | string | null |  | The monitored domain's expiration date; returns `null` if unavailable. |
| `monitors[].domain_expiration_warn` | boolean |  | Whether or not the domain expiration warning is enabled. |
| `monitors[].domain_expiration_warn_days` | integer |  | The number of days before the domain expiration when the warning is triggered. |
| `monitors[].nameservers` | array |  | The monitored domain's nameservers; returns `null` if unavailable. |
| `monitors[].nameservers_change_warn` | boolean |  | Whether or not the nameservers change warning is enabled. |
| `monitors[].public_report` | boolean |  | Is `false` if this monitor's uptime report is private. |
| `monitors[].public_target` | boolean |  | Is `false` if this monitor's monitored target is hidden on the monitor's uptime report. |
| `monitors[].max_redirects` | integer | null |  | The maximum number of HTTP redirects the system will follow when monitoring a website; returns `null` for non `website` monitor types. |
| `monitors[].http_method` | string | null |  | The HTTP method used when monitoring a website; returns `null` for non `website` types. |
| `monitors[].accepted_http_codes` | array | null |  | The array of HTTP codes that are considered `healthy` if returned by the monitored website; returns `null` for non `website` types. |
| `monitors[].verify_ssl_certificate` | boolean |  | Is `true` if the monitor will also check the SSL certificate validity of the monitored target (if applicable). |
| `monitors[].verify_ssl_hostname` | boolean |  | Is `true` if the monitor will also check if the SSL certificate matches the monitored hostname (if applicable). |
| `monitors[].number_of_tries` | integer | null |  | The number of tries/retries each monitoring location will perform before changing the monitor's `uptime_status`; returns `null` for the `heartbeat` monitor type. |
| `monitors[].triggering_locations` | integer | null |  | The number of monitoring locations that will decide the `uptime_status`. This value can never be smaller than `50%+1` of the number of monitoring locations. |
| `monitors[].alert_after_minutes` | integer |  | The number of `minutes` after `up`/`down` alerts are dispatched. Any downtime smaller than this time will not generate alerts. [Learn more here](https://docs.hetrixtools.com/alert-only-after-x-minutes-of-downtime/). |
| `monitors[].repeat_alert_times` | integer |  | The number of times a `down` alert will be repeated if the downtime is still ongoing. [Learn more here](https://docs.hetrixtools.com/repeated-alerts/). |
| `monitors[].repeat_alert_frequency` | integer |  | The frequency (`minutes`) at which the repeated alerts are sent out. [Learn more here](https://docs.hetrixtools.com/repeated-alerts/). |
| `monitors[].has_agent` | boolean |  | Is `true` if a Server Monitoring Agent ID (SID) is attached to this uptime monitor; otherwise `false`. This does not indicate whether an agent is installed, online, or sending data. |
| `meta` | object |  |  |
| `meta.total` | integer |  | The total number of uptime monitors available in your account. |
| `meta.total_filtered` | integer |  | The number of uptime monitors found after filtering has been applied. |
| `meta.returned` | integer |  | The number of uptime monitors returned by this API call. |
| `meta.pagination` | object |  |  |
| `meta.pagination.current` | integer |  | The current page number. |
| `meta.pagination.last` | integer |  | The last available page number. |
| `meta.pagination.previous` | integer | null |  | The previous page number; `null` returned if no previous pages available. |
| `meta.pagination.next` | integer | null |  | The next page number; `null` returned if no further pages available. |

```json
{
  "monitors": [
    {
      "id": "e34334dt5t755b034606y54ccabe62e8",
      "name": "Uptime Monitor Name",
      "type": "website",
      "target": "http://demo-website.com",
      "resolve_address": "1.2.3.4",
      "resolve_address_info": {
        "ASN": "AS394303",
        "ISP": "Steadfast",
        "City": "Tampa",
        "Region": "Florida",
        "Country": "US"
      },
      "port": null,
      "keyword": "",
      "category": "My Websites",
      "timeout": 10,
      "check_frequency": 1,
      "contact_lists": [
        "f1da3895ty67b5de605y6grcd3c23f0e"
      ],
      "created_at": 1499315164,
      "last_check": 1641832650,
      "last_status_change": 1641367229,
      "uptime_status": "up",
      "monitor_status": "active",
      "uptime": 99.9588,
      "uptime_incl_maint": 99.9588,
      "locations": {
        "new_york": {
          "uptime_status": "up",
          "response_time": 74,
          "last_check": 1641832627
        },
        "san_francisco": {
          "uptime_status": "up",
          "response_time": 123,
          "last_check": 1641832638
        },
        "amsterdam": {
          "uptime_status": "up",
          "response_time": 227,
          "last_check": 1641832635
        }
      },
      "ssl_expiration_date": "2022-03-06",
      "ssl_expiration_warn": true,
      "ssl_expiration_warn_days": 7,
      "domain_expiration_date": "2022-05-10",
      "domain_expiration_warn": true,
      "domain_expiration_warn_days": 15,
      "nameservers": [
        "adi.ns.cloudflare.com",
        "dave.ns.cloudflare.com"
      ],
      "nameservers_change_warn": true,
      "public_report": true,
      "public_target": true,
      "max_redirects": 5,
      "http_method": "GET",
      "accepted_http_codes": [
        200
      ],
      "verify_ssl_certificate": false,
      "verify_ssl_hostname": false,
      "number_of_tries": 3,
      "triggering_locations": 2,
      "alert_after_minutes": 0,
      "repeat_alert_times": 0,
      "repeat_alert_frequency": 0,
      "has_agent": true
    },
    {
      "id": "c5f60391rt7716fb02753gc1475a0a95",
      "name": "Nightly Backup Cron",
      "type": "heartbeat",
      "target": null,
      "resolve_address": "5.6.7.8",
      "resolve_address_info": {
        "ASN": "AS14061",
        "ISP": "Digital Ocean",
        "City": "Amsterdam",
        "Region": "North Holland",
        "Country": "NL"
      },
      "port": null,
      "keyword": null,
      "category": "Cron Jobs",
      "timeout": 0,
      "grace": 300,
      "heartbeat_type": "cron_job",
      "cron_expression": "30 2 * * *",
      "cron_timezone": "America/New_York",
      "check_frequency": null,
      "contact_lists": [
        "f1da3895ty67b5de605y6grcd3c23f0e"
      ],
      "created_at": 1612345678,
      "last_check": 1641832680,
      "last_status_change": 1641367300,
      "uptime_status": "up",
      "monitor_status": "active",
      "uptime": 99.9975,
      "uptime_incl_maint": 99.9975,
      "locations": null,
      "ssl_expiration_date": null,
      "ssl_expiration_warn": false,
      "ssl_expiration_warn_days": 0,
      "domain_expiration_date": null,
      "domain_expiration_warn": false,
      "domain_expiration_warn_days": 0,
      "nameservers": null,
      "nameservers_change_warn": false,
      "public_report": false,
      "public_target": false,
      "max_redirects": null,
      "http_method": null,
      "accepted_http_codes": null,
      "verify_ssl_certificate": false,
      "verify_ssl_hostname": false,
      "number_of_tries": null,
      "triggering_locations": null,
      "alert_after_minutes": 0,
      "repeat_alert_times": 0,
      "repeat_alert_frequency": 0,
      "has_agent": true
    }
  ],
  "meta": {
    "total": 202,
    "total_filtered": 2,
    "returned": 2,
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


Sécurité : `[{'bearerAuth': []}]`
