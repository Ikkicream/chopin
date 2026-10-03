# GET /uptime-monitors/{monitor_id}/server-agent/metrics — Server Agent Metrics

> Source : https://docs.hetrixtools.com/api/v3/ (opération `GET /uptime-monitors/{monitor_id}/server-agent/metrics`) — spec api.yaml?v=170, aspirée le 2026-09-26

`GET https://api.hetrixtools.com/v3/uptime-monitors/{monitor_id}/server-agent/metrics`

## Description

API call used to get an uptime monitor's Server Monitoring Agent metrics, including system and hardware details, disks, network interfaces, services, outgoing pings, custom variables, and metric history. This endpoint is not paginated.

Use the `monitor_id` from the request to identify the uptime monitor. To retrieve the Server Monitoring Agent ID (SID), use [GET - Server Agent ID](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors~1{monitor_id}~1server-agent/get) with an API key allowed to access that endpoint.

Without `from`, `to`, or `interval`, the response contains the latest agent snapshot and up to 60 recent `stats` points from the last hour. In this default response, `meta.history`, `bucket_end`, and `partial` are omitted.

### Historical ranges

Supply `from` and `to` together as Unix timestamps in seconds. Only `stats` is filtered by the requested range; all other sections remain the latest agent snapshot. Supplying only `interval` requests the last hour with history metadata. If both bounds are supplied and `interval` is omitted, the interval is `auto`.

```http
GET /v3/uptime-monitors/{monitor_id}/server-agent/metrics?interval=auto
GET /v3/uptime-monitors/{monitor_id}/server-agent/metrics?from=1789552800&to=1789560000&interval=1h
```

Automatic resolution is selected from the requested duration:

| Duration | Interval |
| --- | --- |
| Up to 72 hours (including 3h and 6h) | `1m` |
| More than 72 hours, up to 30 days (including 7d and 30d) | `1h` |
| More than 30 days (including 6 months) | `1d` |

Minute history is available only within the last 30 calendar days. An automatic minute range starting before that cutoff is promoted to `1h`; an explicit `1m` request starting before the cutoff returns `400`. Hourly and daily history can cover older periods where data exists.

The maximum range is 2,190 days, and a request may select at most 5,000 bucket starts, including buckets with no data. Requests exceeding either limit return `400`; choose a coarser interval or split the range. An explicit interval can be finer than the automatic choice within these limits, for example 180 days at `1h`.

## Paramètres

| Nom | Où | Type | Requis | Description |
|---|---|---|---|---|
| `monitor_id` | path | string | oui | The unique uptime monitor id, which can be found by running the [GET - Uptime Monitors](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get) API. |
| `from` | query | integer minimum=0 maximum=9999999999 |  | Inclusive start of the history range, as a Unix timestamp in seconds. Must be supplied together with to and be strictly earlier than to. Bounds select bucket starts. |
| `to` | query | integer minimum=0 maximum=9999999999 |  | Exclusive end of the history range, as a Unix timestamp in seconds. Must be supplied together with from and must not be in the future. |
| `interval` | query | string enum=['auto', '1m', '1h', '1d'] default=auto |  | History resolution. auto selects the interval from the range and minute-retention rules above. Supplying interval without from/to selects the last hour with history metadata. |

## Réponses

### 200 — Successful Response.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `agent` | object | oui | The latest agent details. |
| `agent.version` | string | null |  | The installed agent version; null when unavailable. |
| `agent.type` | string enum ['linux', 'php', 'windows', 'macos', 'unknown'] |  | The agent type. |
| `agent.ip_address` | string | null |  | The IPv4 or IPv6 address recorded for the latest agent data post; null when unavailable. |
| `agent.date_added` | integer (int64) |  | The Unix timestamp in seconds when the agent was added. |
| `system` | object | oui |  |
| `system.hostname` | string | null |  | The server hostname; null when unavailable. |
| `system.operating_system` | string | null |  | The operating system; null when unavailable. |
| `system.kernel` | string | null |  | The kernel version; null when unavailable. |
| `system.uptime` | integer (int64) |  | The system uptime in seconds. |
| `system.reboot_required` | boolean |  | Whether the agent reports that a reboot is required. |
| `cpu` | object | oui |  |
| `cpu.model` | string | null |  | The CPU model; null when unavailable. |
| `cpu.speed` | integer (int64) |  | The CPU clock speed in MHz; 0 when unavailable. |
| `cpu.sockets` | integer (int64) |  | The number of CPU sockets. |
| `cpu.cores` | integer (int64) |  | The number of physical CPU cores. |
| `cpu.threads` | integer (int64) |  | The number of logical CPU threads. |
| `memory` | object | oui |  |
| `memory.ram_size` | integer (int64) |  | The total RAM size in bytes. |
| `memory.swap_size` | integer (int64) |  | The total swap size in bytes. |
| `disk` | object | oui |  |
| `disk.total_size` | integer (int64) |  | The approximate total disk size in bytes. |
| `disk.disks` | array |  | The latest filesystem metrics, ordered by mount point; an empty array when unavailable. |
| `disk.disks[].mount` | string |  | The filesystem mount point. |
| `disk.disks[].size` | integer (int64) |  | The filesystem capacity in bytes. |
| `disk.disks[].used` | integer (int64) |  | The used space in bytes, calculated from the reported usage percentage. |
| `disk.disks[].available` | integer (int64) |  | The remaining space in bytes, calculated as size minus used. |
| `disk.disks[].usage_percent` | number |  | The filesystem usage percentage. |
| `disk.disks[].io_read` | integer (int64) |  | The disk read rate in bytes per second. |
| `disk.disks[].io_write` | integer (int64) |  | The disk write rate in bytes per second. |
| `disk.disks[].inodes` | integer (int64) |  | The total number of inodes. |
| `disk.disks[].inodes_used` | integer (int64) |  | The number of used inodes. |
| `disk.disks[].raid` | object | null |  | Software RAID or ZFS information for this mount; null when unavailable. |
| `disk.disks[].raid.type` | string |  | The RAID level or ZFS pool type. |
| `disk.disks[].raid.zfs` | boolean |  | Whether this is a ZFS pool. |
| `disk.disks[].raid.health` | string enum ['healthy', 'warning', 'danger', 'unknown'] |  | The reported array health. |
| `disk.disks[].raid.state` | string |  | The reported array state, including rebuild progress when available. |
| `disk.disks[].raid.persistence` | string | null |  | The software RAID superblock persistence status; null for ZFS pools. |
| `disk.disks[].raid.total_drives` | integer (int64) |  | The total number of drives in the array. |
| `disk.disks[].raid.active_drives` | integer (int64) |  | The number of active drives. |
| `disk.disks[].raid.working_drives` | integer (int64) |  | The number of working drives. |
| `disk.disks[].raid.spare_drives` | integer (int64) |  | The number of spare drives. |
| `disk.disks[].raid.failed_drives` | integer (int64) |  | The number of failed drives. |
| `disk.drives` | array |  | The latest drive health metrics, ordered by drive name; an empty array when unavailable. |
| `disk.drives[].name` | string |  | The drive device name. |
| `disk.drives[].type` | string enum ['hdd', 'ssd', 'nvme', 'unknown'] |  | The drive type. |
| `disk.drives[].model` | string |  | The drive model. |
| `disk.drives[].serial` | string |  | The drive serial number. |
| `disk.drives[].smart_test` | string |  | The reported SMART status, such as PASSED, FAILED, or UNSUPPORTED. |
| `disk.drives[].wearout_percent` | number |  | The reported drive wear percentage. |
| `disk.drives[].power_on_hours` | integer (int64) |  | The number of hours the drive has been powered on. |
| `disk.drives[].power_cycles` | integer (int64) |  | The number of power cycles. |
| `disk.drives[].unsafe_shutdowns` | integer (int64) |  | The number of unsafe shutdowns. |
| `disk.drives[].error_count` | integer (int64) |  | The total reported error count. |
| `disk.drives[].error_details` |  |  | Error counts keyed by the reported error name; an empty array when no details are available. |
| `network_interfaces` | array | oui | The latest network interface metrics, ordered by interface name; an empty array when unavailable. |
| `network_interfaces[].name` | string |  | The network interface name. |
| `network_interfaces[].net_in` | integer (int64) |  | The incoming network rate in bytes per second. |
| `network_interfaces[].net_out` | integer (int64) |  | The outgoing network rate in bytes per second. |
| `network_interfaces[].ipv4` | array |  | The reported IPv4 addresses. |
| `network_interfaces[].ipv6` | array |  | The reported IPv6 addresses. |
| `services` | array | oui | The latest monitored service statuses; an empty array when none are available. |
| `services[].name` | string |  | The monitored service name. |
| `services[].status` | string enum ['online', 'offline'] |  | The reported service status. |
| `port_connections` | array | oui | The latest connection counts, ordered by port; an empty array when unavailable. |
| `port_connections[].port` | integer (int64) |  | The monitored port number. |
| `port_connections[].connections` | integer (int64) |  | The number of connections on this port. |
| `outgoing_pings` | array | oui | The latest outgoing ping results, ordered by name; an empty array when unavailable. |
| `outgoing_pings[].name` | string |  | The configured outgoing ping name. |
| `outgoing_pings[].target` | string |  | The target hostname or IP address. |
| `outgoing_pings[].port` | integer | null (int64) |  | The target port; null for an ICMP ping without a port. |
| `outgoing_pings[].packet_loss_percent` | number |  | The packet loss percentage. |
| `outgoing_pings[].response_time` | number |  | The response time in milliseconds. |
| `custom_variables` | array | oui | The latest custom variable values, ordered by name; an empty array when unavailable. |
| `custom_variables[].name` | string |  | The custom variable name. |
| `custom_variables[].value` | integer (int64) |  | The reported custom variable value. |
| `stats` | array | oui | Server metric samples or aggregates, ordered newest first. Missing historical fields are null; recorded zeros are preserved. Missing buckets are omitted. An empty array means no data is available for the selected window. |
| `stats[].timestamp` | integer (int64) | oui | The Unix timestamp in seconds for this sample or bucket start. |
| `stats[].bucket_end` | integer (int64) |  | The exclusive bucket-end Unix timestamp in seconds. Present only when history parameters are supplied; it may be later than to. |
| `stats[].partial` | boolean |  | Whether the bucket is still in progress at request time. Present only when history parameters are supplied. |
| `stats[].cpu` | number | null | oui | CPU usage percentage. |
| `stats[].iowait` | number | null | oui | CPU time spent waiting for I/O, as a percentage. |
| `stats[].steal` | number | null | oui | CPU steal time percentage. |
| `stats[].user` | number | null | oui | CPU time spent in user space, as a percentage. |
| `stats[].system` | number | null | oui | CPU time spent in kernel space, as a percentage. |
| `stats[].cpu_temp` | number | null | oui | CPU temperature in degrees Celsius. |
| `stats[].load_1` | number | null | oui | The 1-minute system load average. |
| `stats[].load_5` | number | null | oui | The 5-minute system load average. |
| `stats[].load_15` | number | null | oui | The 15-minute system load average. |
| `stats[].ram` | number | null | oui | RAM usage percentage. |
| `stats[].swap` | number | null | oui | Swap usage percentage. |
| `stats[].buffered` | number | null | oui | The percentage of RAM used for buffers. |
| `stats[].cached` | number | null | oui | The percentage of RAM used for cache. |
| `stats[].disk` | number | null | oui | Overall disk usage percentage. |
| `stats[].net_in` | integer | null (int64) | oui | The incoming network rate in bytes per second, across monitored interfaces. Hourly and daily values are average rates, rounded to whole bytes per second. |
| `stats[].net_out` | integer | null (int64) | oui | The outgoing network rate in bytes per second, across monitored interfaces. Hourly and daily values are average rates, rounded to whole bytes per second. |
| `meta` | object | oui |  |
| `meta.last_updated` | integer (int64) | oui | The Unix timestamp in seconds of the latest agent data post, regardless of the requested history range. |
| `meta.history` | object |  | Present only when from/to or interval is supplied. On a cached response, these values describe the original cached request window. |
| `meta.history.from` | integer (int64) |  | The inclusive requested start, or the default last-hour start, as a Unix timestamp in seconds. |
| `meta.history.to` | integer (int64) |  | The exclusive requested end, or the default request time, as a Unix timestamp in seconds. |
| `meta.history.interval` | string enum ['1m', '1h', '1d'] |  | The selected interval after automatic resolution and retention rules. |
| `meta.history.requested_interval` | string enum ['auto', '1m', '1h', '1d'] |  | The supplied interval, or auto when omitted. |
| `meta.history.resolution_reason` | string enum ['requested', 'duration', 'minute_retention'] |  | Why this interval was selected: requested for an explicit interval, duration for automatic selection, or minute_retention when an automatic minute range was promoted to hourly. |
| `meta.history.minute_available_from` | integer (int64) |  | The request-time cutoff for minute history: 30 calendar days earlier in America/New_York. Data availability is not guaranteed for every bucket after this cutoff. |
| `meta.history.unavailable_periods` | array |  | Periods omitted because the repeated fall-back hour cannot be distinguished. This is not a list of all data gaps. |
| `meta.history.unavailable_periods[].from` | integer (int64) |  | The inclusive Unix timestamp in seconds for the unavailable part of the requested range. |
| `meta.history.unavailable_periods[].to` | integer (int64) |  | The exclusive Unix timestamp in seconds for the unavailable part of the requested range. |
| `meta.history.unavailable_periods[].reason` | string enum ['ambiguous_storage_time'] |  | The reason this period was omitted. |
| `meta.history.aggregation` | string enum ['sample', 'mean'] |  | sample for minute points; mean for hourly and daily points. |
| `meta.history.bucket_timezone` | string enum ['America/New_York'] |  | The timezone used to define calendar buckets. |
| `meta.history.returned` | integer (int64) |  | The number of points in stats. |
| `meta.history.first_timestamp` | integer | null (int64) |  | The earliest returned bucket start, as a Unix timestamp in seconds; null when stats is empty. |
| `meta.history.last_timestamp` | integer | null (int64) |  | The latest returned bucket start, as a Unix timestamp in seconds; null when stats is empty. |

_latest_ :

```json
{
  "agent": {
    "version": "2.4.2",
    "type": "linux",
    "ip_address": "192.0.2.10",
    "date_added": 1757952000
  },
  "system": {
    "hostname": "web-01",
    "operating_system": "Ubuntu 24.04 LTS",
    "kernel": "6.8.0-60-generic",
    "uptime": 172800,
    "reboot_required": false
  },
  "cpu": {
    "model": "Intel Xeon",
    "speed": 2400,
    "sockets": 1,
    "cores": 4,
    "threads": 8
  },
  "memory": {
    "ram_size": 17179869184,
    "swap_size": 2147483648
  },
  "disk": {
    "total_size": 107374182400,
    "disks": [
      {
        "mount": "/",
        "size": 107374182400,
        "used": 34896609280,
        "available": 72477573120,
        "usage_percent": 32.5,
        "io_read": 1048576,
        "io_write": 262144,
        "inodes": 6553600,
        "inodes_used": 524288,
        "raid": null
      }
    ],
    "drives": [
      {
        "name": "/dev/sda",
        "type": "ssd",
        "model": "Example SSD",
        "serial": "EXAMPLE123",
        "smart_test": "PASSED",
        "wearout_percent": 3,
        "power_on_hours": 2400,
        "power_cycles": 12,
        "unsafe_shutdowns": 0,
        "error_count": 0,
        "error_details": []
      }
    ]
  },
  "network_interfaces": [
    {
      "name": "eth0",
      "net_in": 524288,
      "net_out": 131072,
      "ipv4": [
        "192.0.2.10"
      ],
      "ipv6": [
        "2001:db8::10"
      ]
    }
  ],
  "services": [
    {
      "name": "nginx",
      "status": "online"
    }
  ],
  "port_connections": [
    {
      "port": 443,
      "connections": 12
    }
  ],
  "outgoing_pings": [
    {
      "name": "gateway",
      "target": "192.0.2.1",
      "port": null,
      "packet_loss_percent": 0,
      "response_time": 0.25
    }
  ],
  "custom_variables": [
    {
      "name": "queue_depth",
      "value": 3
    }
  ],
  "stats": [
    {
      "timestamp": 1789563180,
      "cpu": 12.5,
      "iowait": 0.25,
      "steal": 0,
      "user": 8.5,
      "system": 4,
      "cpu_temp": 42,
      "load_1": 0.35,
      "load_5": 0.42,
      "load_15": 0.5,
      "ram": 45.5,
      "swap": 0,
      "buffered": 2.1,
      "cached": 18.4,
      "disk": 32.5,
      "net_in": 524288,
      "net_out": 131072
    }
  ],
  "meta": {
    "last_updated": 1789563240
  }
}
```

_history_ :

```json
{
  "agent": {
    "version": "2.4.2",
    "type": "linux",
    "ip_address": "192.0.2.10",
    "date_added": 1757952000
  },
  "system": {
    "hostname": "web-01",
    "operating_system": "Ubuntu 24.04 LTS",
    "kernel": "6.8.0-60-generic",
    "uptime": 172800,
    "reboot_required": false
  },
  "cpu": {
    "model": "Intel Xeon",
    "speed": 2400,
    "sockets": 1,
    "cores": 4,
    "threads": 8
  },
  "memory": {
    "ram_size": 17179869184,
    "swap_size": 2147483648
  },
  "disk": {
    "total_size": 107374182400,
    "disks": [
      {
        "mount": "/",
        "size": 107374182400,
        "used": 34896609280,
        "available": 72477573120,
        "usage_percent": 32.5,
        "io_read": 1048576,
        "io_write": 262144,
        "inodes": 6553600,
        "inodes_used": 524288,
        "raid": null
      }
    ],
    "drives": [
      {
        "name": "/dev/sda",
        "type": "ssd",
        "model": "Example SSD",
        "serial": "EXAMPLE123",
        "smart_test": "PASSED",
        "wearout_percent": 3,
        "power_on_hours": 2400,
        "power_cycles": 12,
        "unsafe_shutdowns": 0,
        "error_count": 0,
        "error_details": []
      }
    ]
  },
  "network_interfaces": [
    {
      "name": "eth0",
      "net_in": 524288,
      "net_out": 131072,
      "ipv4": [
        "192.0.2.10"
      ],
      "ipv6": [
        "2001:db8::10"
      ]
    }
  ],
  "services": [
    {
      "name": "nginx",
      "status": "online"
    }
  ],
  "port_connections": [
    {
      "port": 443,
      "connections": 12
    }
  ],
  "outgoing_pings": [
    {
      "name": "gateway",
      "target": "192.0.2.1",
      "port": null,
      "packet_loss_percent": 0,
      "response_time": 0.25
    }
  ],
  "custom_variables": [
    {
      "name": "queue_depth",
      "value": 3
    }
  ],
  "stats": [
    {
      "timestamp": 1789556400,
      "bucket_end": 1789560000,
      "partial": false,
      "cpu": 12.5,
      "iowait": 0.25,
      "steal": 0,
      "user": 8.5,
      "system": 4,
      "cpu_temp": 42,
      "load_1": 0.35,
      "load_5": 0.42,
      "load_15": 0.5,
      "ram": 45.5,
      "swap": 0,
      "buffered": 2.1,
      "cached": 18.4,
      "disk": 32.5,
      "net_in": 524288,
      "net_out": 131072
    },
    {
      "timestamp": 1789552800,
      "bucket_end": 1789556400,
      "partial": false,
      "cpu": 10.5,
      "iowait": 0.25,
      "steal": 0,
      "user": 7.5,
      "system": 3,
      "cpu_temp": 42,
      "load_1": 0.35,
      "load_5": 0.42,
      "load_15": 0.5,
      "ram": 45.5,
      "swap": 0,
      "buffered": 2.1,
      "cached": 18.4,
      "disk": 32.5,
      "net_in": 524288,
      "net_out": 131072
    }
  ],
  "meta": {
    "last_updated": 1789563240,
    "history": {
      "from": 1789552800,
      "to": 1789560000,
      "interval": "1h",
      "requested_interval": "1h",
      "resolution_reason": "requested",
      "minute_available_from": 1786971240,
      "unavailable_periods": [],
      "aggregation": "mean",
      "bucket_timezone": "America/New_York",
      "returned": 2,
      "first_timestamp": 1789552800,
      "last_timestamp": 1789556400
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

### 503 — Service Unavailable - History storage could not be read. Retry the request later.

```json
{
  "status": "service_unavailable",
  "message": "temporary history storage error, please retry"
}
```


Sécurité : `[{'bearerAuth': []}]`
