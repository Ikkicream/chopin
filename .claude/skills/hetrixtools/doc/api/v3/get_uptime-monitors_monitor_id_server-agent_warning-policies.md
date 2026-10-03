# GET /uptime-monitors/{monitor_id}/server-agent/warning-policies — Warning Policies

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /uptime-monitors/{monitor_id}/server-agent/warning-policies`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/server-agent/warning-policies`

## Description

API call used to get an uptime monitor's Server Agent warning policies.

Each warning policy can have its own Contact List (`contact_list`), overwriting the uptime monitor's Contact List. Warning policies without such an overwrite return `null` and send their notifications to the uptime monitor's Contact List.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor id, which can be found by running the [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) API. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `agent_data_warn` | object |  | Issue warnings when the server monitoring agent hasn't sent data. |
| `agent_data_warn.enabled` | boolean |  | Defines whether or not this policy is enabled. |
| `agent_data_warn.threshold` | integer enum [3, 5, 10, 15, 30, 60] |  | The number of consecutive minutes without agent data received required to trigger a warning. |
| `agent_data_warn.warn_frequency` | integer enum [5, 10, 15, 30, 60, 180, 360, 720, 1440] |  | The minimum number of minutes between each issued warning. |
| `agent_data_warn.contact_list` | string | null |  | The Contact List that this warning's notifications are sent to, overwriting the uptime monitor's Contact List.   - `null` - no overwrite is set, this warning's notifications are sent to the uptime monitor's Contact List - `none` - this warning's notifications are muted - a contact list ID - this warning's notifications are sent to this contact list, which can be found by running the [GET - Contact Lists](https://docs.hetrixtools.com/api/v3/#/paths/~1contact-lists/get) API |
| `cpu_usage_warn` | object |  | Issue warnings when cpu usage reaches a threshold. |
| `cpu_usage_warn.enabled` | boolean |  | Defines whether or not this policy is enabled. |
| `cpu_usage_warn.threshold` | integer |  | The usage (percent) at which and over which a warning is issued. |
| `cpu_usage_warn.time_frame` | integer enum [1, 3, 5, 10, 15, 30, 60] |  | The last `X` minutes over which the usage average is calculated. |
| `cpu_usage_warn.warn_frequency` | integer enum [5, 10, 15, 30, 60, 180, 360, 720, 1440] |  | The minimum number of minutes between each issued warning. |
| `cpu_usage_warn.contact_list` | string | null |  | The Contact List that this warning's notifications are sent to, overwriting the uptime monitor's Contact List.   - `null` - no overwrite is set, this warning's notifications are sent to the uptime monitor's Contact List - `none` - this warning's notifications are muted - a contact list ID - this warning's notifications are sent to this contact list, which can be found by running the [GET - Contact Lists](https://docs.hetrixtools.com/api/v3/#/paths/~1contact-lists/get) API |
| `iowait_usage_warn` | object |  | Issue warnings when iowait usage reaches a threshold. |
| `iowait_usage_warn.enabled` | boolean |  | Defines whether or not this policy is enabled. |
| `iowait_usage_warn.threshold` | integer |  | The usage (percent) at which and over which a warning is issued. |
| `iowait_usage_warn.time_frame` | integer enum [1, 3, 5, 10, 15, 30, 60] |  | The last `X` minutes over which the usage average is calculated. |
| `iowait_usage_warn.warn_frequency` | integer enum [5, 10, 15, 30, 60, 180, 360, 720, 1440] |  | The minimum number of minutes between each issued warning. |
| `iowait_usage_warn.contact_list` | string | null |  | The Contact List that this warning's notifications are sent to, overwriting the uptime monitor's Contact List.   - `null` - no overwrite is set, this warning's notifications are sent to the uptime monitor's Contact List - `none` - this warning's notifications are muted - a contact list ID - this warning's notifications are sent to this contact list, which can be found by running the [GET - Contact Lists](https://docs.hetrixtools.com/api/v3/#/paths/~1contact-lists/get) API |
| `ram_usage_warn` | object |  | Issue warnings when ram usage reaches a threshold. |
| `ram_usage_warn.enabled` | boolean |  | Defines whether or not this policy is enabled. |
| `ram_usage_warn.threshold` | integer |  | The usage (percent) at which and over which a warning is issued. |
| `ram_usage_warn.time_frame` | integer enum [1, 3, 5, 10, 15, 30, 60] |  | The last `X` minutes over which the usage average is calculated. |
| `ram_usage_warn.warn_frequency` | integer enum [5, 10, 15, 30, 60, 180, 360, 720, 1440] |  | The minimum number of minutes between each issued warning. |
| `ram_usage_warn.contact_list` | string | null |  | The Contact List that this warning's notifications are sent to, overwriting the uptime monitor's Contact List.   - `null` - no overwrite is set, this warning's notifications are sent to the uptime monitor's Contact List - `none` - this warning's notifications are muted - a contact list ID - this warning's notifications are sent to this contact list, which can be found by running the [GET - Contact Lists](https://docs.hetrixtools.com/api/v3/#/paths/~1contact-lists/get) API |
| `swap_usage_warn` | object |  | Issue warnings when swap usage reaches a threshold. |
| `swap_usage_warn.enabled` | boolean |  | Defines whether or not this policy is enabled. |
| `swap_usage_warn.threshold` | integer |  | The usage (percent) at which and over which a warning is issued. |
| `swap_usage_warn.time_frame` | integer enum [1, 3, 5, 10, 15, 30, 60] |  | The last `X` minutes over which the usage average is calculated. |
| `swap_usage_warn.warn_frequency` | integer enum [5, 10, 15, 30, 60, 180, 360, 720, 1440] |  | The minimum number of minutes between each issued warning. |
| `swap_usage_warn.contact_list` | string | null |  | The Contact List that this warning's notifications are sent to, overwriting the uptime monitor's Contact List.   - `null` - no overwrite is set, this warning's notifications are sent to the uptime monitor's Contact List - `none` - this warning's notifications are muted - a contact list ID - this warning's notifications are sent to this contact list, which can be found by running the [GET - Contact Lists](https://docs.hetrixtools.com/api/v3/#/paths/~1contact-lists/get) API |
| `disk_usage_warn` | object |  | Issue warnings when disk usage reaches a threshold. |
| `disk_usage_warn.enabled` | boolean |  | Defines whether or not this policy is enabled. |
| `disk_usage_warn.threshold` | integer |  | The usage (percent) at which and over which a warning is issued. |
| `disk_usage_warn.time_frame` | integer enum [1, 3, 5, 10, 15, 30, 60] |  | The last `X` minutes over which the usage average is calculated. |
| `disk_usage_warn.warn_frequency` | integer enum [5, 10, 15, 30, 60, 180, 360, 720, 1440] |  | The minimum number of minutes between each issued warning. |
| `disk_usage_warn.contact_list` | string | null |  | The Contact List that this warning's notifications are sent to, overwriting the uptime monitor's Contact List.   - `null` - no overwrite is set, this warning's notifications are sent to the uptime monitor's Contact List - `none` - this warning's notifications are muted - a contact list ID - this warning's notifications are sent to this contact list, which can be found by running the [GET - Contact Lists](https://docs.hetrixtools.com/api/v3/#/paths/~1contact-lists/get) API |
| `disk_usage_warn.warn_disks` | array |  | The array of disks that can generate usage warnings. |
| `disk_usage_warn.warn_disks[].id` | string |  | The unique identifier for this disk. |
| `disk_usage_warn.warn_disks[].enabled` | boolean |  | Defines whether or not this disk generates usage warnings. |
| `disk_usage_warn.warn_disks[].mount` | string |  | This disk's mount point on the system. |
| `raid_warn` | object |  | Issue warnings RAID status is not completely healthy. |
| `raid_warn.enabled` | boolean |  | Defines whether or not this policy is enabled. |
| `raid_warn.warn_type` | string enum ['not_ideal', 'critical'] |  | The severity of the encountered RAID status at which a warning is issued.   - `not_ideal` - includes statuses such as: `check`, `recover`, `resync` - `critical` - includes statuses such as: `degraded`, `failed` |
| `raid_warn.warn_frequency` | integer enum [5, 10, 15, 30, 60, 180, 360, 720, 1440] |  | The minimum number of minutes between each issued warning. |
| `raid_warn.contact_list` | string | null |  | The Contact List that this warning's notifications are sent to, overwriting the uptime monitor's Contact List.   - `null` - no overwrite is set, this warning's notifications are sent to the uptime monitor's Contact List - `none` - this warning's notifications are muted - a contact list ID - this warning's notifications are sent to this contact list, which can be found by running the [GET - Contact Lists](https://docs.hetrixtools.com/api/v3/#/paths/~1contact-lists/get) API |
| `drive_errors_warn` | object |  | Issue warnings when drive errors reach a threshold. |
| `drive_errors_warn.enabled` | boolean |  | Defines whether or not this policy is enabled. |
| `drive_errors_warn.threshold` | integer |  | The number of errors at which and over which a warning is issued. |
| `drive_errors_warn.warn_frequency` | integer enum [5, 10, 15, 30, 60, 180, 360, 720, 1440] |  | The minimum number of minutes between each issued warning. |
| `drive_errors_warn.contact_list` | string | null |  | The Contact List that this warning's notifications are sent to, overwriting the uptime monitor's Contact List.   - `null` - no overwrite is set, this warning's notifications are sent to the uptime monitor's Contact List - `none` - this warning's notifications are muted - a contact list ID - this warning's notifications are sent to this contact list, which can be found by running the [GET - Contact Lists](https://docs.hetrixtools.com/api/v3/#/paths/~1contact-lists/get) API |
| `drive_wearout_warn` | object |  | Issue warnings when drive wearout reaches a threshold. |
| `drive_wearout_warn.enabled` | boolean |  | Defines whether or not this policy is enabled. |
| `drive_wearout_warn.threshold` | integer |  | The wearout (percent) at which and over which a warning is issued. |
| `drive_wearout_warn.warn_frequency` | integer enum [5, 10, 15, 30, 60, 180, 360, 720, 1440] |  | The minimum number of minutes between each issued warning. |
| `drive_wearout_warn.contact_list` | string | null |  | The Contact List that this warning's notifications are sent to, overwriting the uptime monitor's Contact List.   - `null` - no overwrite is set, this warning's notifications are sent to the uptime monitor's Contact List - `none` - this warning's notifications are muted - a contact list ID - this warning's notifications are sent to this contact list, which can be found by running the [GET - Contact Lists](https://docs.hetrixtools.com/api/v3/#/paths/~1contact-lists/get) API |
| `drive_smart_warn` | object |  | Issue warnings when S.M.A.R.T. test fails. |
| `drive_smart_warn.enabled` | boolean |  | Defines whether or not this policy is enabled. |
| `drive_smart_warn.warn_frequency` | integer enum [5, 10, 15, 30, 60, 180, 360, 720, 1440] |  | The minimum number of minutes between each issued warning. |
| `drive_smart_warn.contact_list` | string | null |  | The Contact List that this warning's notifications are sent to, overwriting the uptime monitor's Contact List.   - `null` - no overwrite is set, this warning's notifications are sent to the uptime monitor's Contact List - `none` - this warning's notifications are muted - a contact list ID - this warning's notifications are sent to this contact list, which can be found by running the [GET - Contact Lists](https://docs.hetrixtools.com/api/v3/#/paths/~1contact-lists/get) API |
| `network_in_warn` | object |  | Issue warnings when inbound usage reaches a threshold. |
| `network_in_warn.enabled` | boolean |  | Defines whether or not this policy is enabled. |
| `network_in_warn.threshold` | integer |  | The threshold at which and over which a warning is issued. |
| `network_in_warn.threshold_type` | string enum ['kbps', 'mbps', 'gbps'] |  | The threshold's measuring unit.   Example: if `threshold` is set to `10` and `threshold_type` is set to `mbps`, that means the warning threshold is 10Mbps. |
| `network_in_warn.time_frame` | integer enum [1, 3, 5, 10, 15, 30, 60] |  | The last `X` minutes over which the usage average is calculated. |
| `network_in_warn.warn_frequency` | integer enum [5, 10, 15, 30, 60, 180, 360, 720, 1440] |  | The minimum number of minutes between each issued warning. |
| `network_in_warn.contact_list` | string | null |  | The Contact List that this warning's notifications are sent to, overwriting the uptime monitor's Contact List.   - `null` - no overwrite is set, this warning's notifications are sent to the uptime monitor's Contact List - `none` - this warning's notifications are muted - a contact list ID - this warning's notifications are sent to this contact list, which can be found by running the [GET - Contact Lists](https://docs.hetrixtools.com/api/v3/#/paths/~1contact-lists/get) API |
| `network_in_warn.warn_nics` | array |  | The array of network interfaces that can generate usage warnings. |
| `network_in_warn.warn_nics[].id` | string |  | The unique identifier for this network interface. |
| `network_in_warn.warn_nics[].enabled` | boolean |  | Defines whether or not this network interface generates usage warnings. |
| `network_in_warn.warn_nics[].name` | string |  | The network interface name. |
| `network_out_warn` | object |  | Issue warnings when outbound usage reaches a threshold. |
| `network_out_warn.enabled` | boolean |  | Defines whether or not this policy is enabled. |
| `network_out_warn.threshold` | integer |  | The threshold at which and over which a warning is issued. |
| `network_out_warn.threshold_type` | string enum ['kbps', 'mbps', 'gbps'] |  | The threshold's measuring unit.   Example: if `threshold` is set to `10` and `threshold_type` is set to `mbps`, that means the warning threshold is 10Mbps. |
| `network_out_warn.time_frame` | integer enum [1, 3, 5, 10, 15, 30, 60] |  | The last `X` minutes over which the usage average is calculated. |
| `network_out_warn.warn_frequency` | integer enum [5, 10, 15, 30, 60, 180, 360, 720, 1440] |  | The minimum number of minutes between each issued warning. |
| `network_out_warn.contact_list` | string | null |  | The Contact List that this warning's notifications are sent to, overwriting the uptime monitor's Contact List.   - `null` - no overwrite is set, this warning's notifications are sent to the uptime monitor's Contact List - `none` - this warning's notifications are muted - a contact list ID - this warning's notifications are sent to this contact list, which can be found by running the [GET - Contact Lists](https://docs.hetrixtools.com/api/v3/#/paths/~1contact-lists/get) API |
| `network_out_warn.warn_nics` | array |  | The array of network interfaces that can generate usage warnings. |
| `network_out_warn.warn_nics[].id` | string |  | The unique identifier for this network interface. |
| `network_out_warn.warn_nics[].enabled` | boolean |  | Defines whether or not this network interface generates usage warnings. |
| `network_out_warn.warn_nics[].name` | string |  | The network interface name. |
| `services_warn` | object |  | Issue warnings when a service goes down. |
| `services_warn.enabled` | boolean |  | Defines whether or not this policy is enabled. |
| `services_warn.warn_frequency` | integer enum [5, 10, 15, 30, 60, 180, 360, 720, 1440] |  | The minimum number of minutes between each issued warning. |
| `services_warn.contact_list` | string | null |  | The Contact List that this warning's notifications are sent to, overwriting the uptime monitor's Contact List.   - `null` - no overwrite is set, this warning's notifications are sent to the uptime monitor's Contact List - `none` - this warning's notifications are muted - a contact list ID - this warning's notifications are sent to this contact list, which can be found by running the [GET - Contact Lists](https://docs.hetrixtools.com/api/v3/#/paths/~1contact-lists/get) API |
| `services_warn.warn_services` | array |  | The array of services that can generate warnings. |
| `services_warn.warn_services[].id` | string |  | The unique identifier for this service. |
| `services_warn.warn_services[].enabled` | boolean |  | Defines whether or not this service generates warnings. |
| `services_warn.warn_services[].name` | string |  | The service name. |

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
