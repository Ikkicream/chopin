# Linux Server Monitoring Agent (v2) – API Endpoint Documentation

> Source : https://docs.hetrixtools.com/linux-server-monitoring-agent-v2-api-endpoint-documentation/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2026-02-05, modifié 2026-02-05

## **Endpoint**

`https://sm.hetrixtools.net/v2/`

**Method:** POST

---

## Request body format

The request body is **form-style** (not JSON directly). It contains **one key**:

j = a **gzip-compressed JSON**, then **base64**, then “URL-prepped” (only / and + are escaped).

So the raw POST body looks like:

`j=<ENCODED_PAYLOAD>`

There are no other fields posted.

---

## **Encoding steps for j**

Given the JSON string payload (described below), the agent performs:

1. **Gzip compress** the JSON bytes
2. **Base64 encode** the gzip output
3. Remove any spaces (usually none)
4. Replace:
   * / with %2F
   * + with %2B
5. POST as: j=<result>

Note: This is *not* full URL-encoding. Only / and + are replaced (because they break form posting if left raw in this context).

---

## **JSON payload schema (before gzip/base64)**

The agent constructs a JSON object with the following keys (all values are sent as **strings**, even when numeric):

```
{
  "version": "2.3.8",
  "SID": "...",
  "agent": "0",
  "user": "...",
  "os": "...",
  "kernel": "...",
  "hostname": "...",
  "time": "...",
  "reqreboot": "...",
  "uptime": "...",
  "cpumodel": "...",
  "cpusockets": "...",
  "cpucores": "...",
  "cputhreads": "...",
  "cpuspeed": "...",
  "cpu": "...",
  "wa": "...",
  "st": "...",
  "us": "...",
  "sy": "...",
  "load1": "...",
  "load5": "...",
  "load15": "...",
  "ramsize": "...",
  "ram": "...",
  "ramswapsize": "...",
  "ramswap": "...",
  "rambuff": "...",
  "ramcache": "...",
  "disks": "...",
  "inodes": "...",
  "iops": "...",
  "raid": "...",
  "zp": "...",
  "dh": "...",
  "nics": "...",
  "ipv4": "...",
  "ipv6": "...",
  "conn": "...",
  "temp": "...",
  "serv": "...",
  "cust": "...",
  "oping": "...",
  "rps1": "...",
  "rps2": "..."
}
```

---

## Field meanings (high-level)

* **Identity/metadata**
  + `version`: agent version string
  + `SID`: Server ID ([how to find](https://docs.hetrixtools.com/where-do-i-find-the-sid-server-monitor-id/))
  + `agent`: constant `"0"` in this script
  + `user`: `whoami`
  + `os`, `kernel`, `hostname`
  + `time`: epoch timestamp (seconds)
  + `reqreboot`: `1`/`0`, whether or not the server requires a reboot
  + `uptime`: seconds since boot
* **CPU**
  + `cpumodel`, `cpusockets`, `cpucores`, `cputhreads`, `cpuspeed`
  + `cpu`, `wa`, `st`, `us`, `sy` (CPU stats/percentages)
  + `load1`, `load5`, `load15`
* **RAM**
  + `ramsize` (MB), `ram` (% used)
  + `ramswapsize` (MB), `ramswap` (% used)
  + `rambuff`, `ramcache` (MB)
* **Storage, networking, services (these are *encoded blobs*)**
  + `disks`, `inodes`, `iops`, `raid`, `zp`, `dh`, `nics`, `ipv4`, `ipv6`, `conn`, `temp`, `serv`, `cust`, `oping`

Those “blob” fields are the tricky ones. Details below.

---


## “Blob” fields: exact formats

### **Common rules**

Many of these values are assembled as a semicolon-separated list of “records”, then **base64 encoded** with whitespace/newlines removed.

When you implement this yourself:

* Build the raw string exactly as described (including commas/semicolons)
* Then base64 encode it
* Strip all `\n`, `\r`, `\t`, and spaces from the base64 output

---

### `disks` (base64)

**Raw format (before base64):**  
Repeated records separated by `;`

Each record:

```
<mount_point>,<filesystem_type>,<total_bytes>,<used_bytes>,<available_bytes>;
```

Then, base64 encode the entire concatenated string (and strip whitespace/newlines).

---

### `inodes` (already base64’d in the script)

This is built from `df -i` style output.

**Raw format (before base64):**  
Each record:

```
<mount_point>,<inodes_used>,<inodes_free>,<inodes_used_percent>;
```

Then base64 encode the entire string.

---

### `iops` (base64)

**Raw format (before base64):**  
Each record:

```
<disk_or_mount>,<reads_per_sec>,<writes_per_sec>;
```

Then base64 encode the entire string.

---

### `raid` (base64)

This is a semicolon record list describing the RAID state.

**Raw format (before base64):**  
Varies based on discovered RAID devices, but each record is generally:

```
<mount_point>,<raid_device>,<mdadm_or_details>;
```

Then base64 encode.

Practical note: If you’re doing your own implementation, expect this field to be empty unless you mirror the RAID detection logic closely as seen in the HetrixTools Linux Server Monitoring Agent.

---

### `zp` (ZFS pools) (base64)

If ZFS is detected, the agent stores the zpool status text.

**Raw format (before base64):**  
Each record:

```
<mount_point>,<pool_name>,<zpool_status_text>;
```

Then base64 encode the entire `zp` string.

---

### `nics` (base64)

**Raw format (before base64):**  
Each record:

```
<iface>,<rx_bytes>,<tx_bytes>;
```

Then base64 encode.

---

### `ipv4` / `ipv6` (base64)

These are separate fields.

**Raw format (before base64):**  
Each record:

```
<iface>,<comma_separated_ip_list>;
```

Then base64 encode.

Examples (raw):

```
eth0,203.0.113.10,10.0.0.5;
```

---

### `conn` (base64)

This is “connections per port” from listening sockets.

**Raw format (before base64):**  
Each record:

```
<port>,<count>;
```

Then base64 encode.

---

## `temp` (base64)

Temperature sensors (when detected).

**Raw format (before base64):**  
Each record:

```
<sensor_name>,<temp_value>;
```

Then base64 encode.

---

## `serv` (services) (NOT base64 in the script)

This is a semicolon-separated list.

**Raw format (as sent):**  
Each record:

```
<service_name>,<status>;
```

Where status is:

* `1` = running/OK
* `0` = not running/failed

Example:

```
nginx,1;mysql,1;redis,0;
```

---

## `cust` (custom vars) (base64)

If a custom variables file is configured, the agent sends:

* `cust` = **base64 of the entire file content** (then stripped of whitespace/newlines)

So if you implement it:

* Read the custom vars file as-is
* Base64 encode the whole content
* Strip whitespace/newlines

---

### `oping` (base64)

If enabled, the agent reads a `ping.txt` output file and sends:

* `oping` = **base64 of the entire `ping.txt` (with blank lines removed)**

Implementation rules:

* Remove empty lines
* Remove `\n` from the content (agent flattens it)
* Base64 encode
* Strip whitespace/newlines

---

### `dh` (drive health) — the “entire output” field (IMPORTANT)

This is the most nested one.

#### `dh` final encoding (outer layer)

The final `dh` JSON field is:

* `dh` = **base64 of the entire DH record list**

#### DH record list format (before the outer base64)

Each drive produces a record like:

```
<type>,<device_id>,<DHealth>,<Model>,<Serial>;
```

* Records separated by `;`
* `<type>`:
  + `1` = SATA/SAS (smartctl path)
  + `2` = NVMe (nvme-cli path)

#### `DHealth` is itself base64 of FULL COMMAND OUTPUT

Inside each record, `<DHealth>` is not plain text. It’s:

* **base64 of the concatenation of:**
  1. `smartctl -H <device>`
  2. a newline
  3. `smartctl -A <device>`

So for a normal disk (example `/dev/sda`), you must produce *exactly*:

```
smartctl -H /dev/sda
smartctl -A /dev/sda
```

Then join them with a literal newline between outputs:

```
<output of smartctl -H /dev/sda>\n<output of smartctl -A /dev/sda>
```

Then:

* base64 encode that entire combined text
* strip whitespace/newlines from the base64 output
* put that base64 string in the DH record as `<DHealth>`

#### RAID controller variants

If `smartctl -A <device>` doesn’t show attributes, the agent tries:

* MegaRAID scanned IDs: `smartctl -A -d <megaraid_id> <device>` and `smartctl -H -d <megaraid_id> <device>`
* HP Smart Array / cciss variants: `smartctl -A -d cciss,<N> <device>` and `smartctl -H -d cciss,<N> <device>`

If you’re implementing outside Linux, you either need equivalent logic or accept that `dh` might be empty/partial.

### NVMe (`type=2`)

For NVMe, the “health output” is:

* `nvme smart-log <device>`
* (optionally prefixed with `smartctl -H <base_device>` + newline, if smartctl exists)

Then base64 encode that combined output exactly as done above.

---

## Minimal “how to reproduce the POST” example (bash)

This shows the *shape* of the request; you still need to populate the JSON fields correctly.

```
json='{"version":"2.3.8","SID":"YOUR_SID","agent":"0","user":"root", ... }'

# gzip -> base64 (single line) -> escape / and +
j="$(printf '%s' "$json" \
  | gzip -c -f \
  | base64 -w 0 \
  | sed 's/ //g' \
  | sed 's/\//%2F/g' \
  | sed 's/+/%2B/g')"

# POST as a file (matching the agent style)
printf 'j=%s' "$j" > post_body.txt
wget -qO- --post-file=post_body.txt https://sm.hetrixtools.net/v2/
```

---

## Notes/caveats (important if you’re writing new implementations)

* The endpoint expects **exactly the `j=` payload**, not raw JSON.
* Several fields (disks, nics, dh, etc.) are not structured JSON; they are **custom-delimited strings**, often **base64 encoded**.
* `dh` includes **entire command outputs** (smartctl/nvme), base64’d, and then the whole list is base64’d again.
