# v1 Server Stats

> Source : https://docs.hetrixtools.com/api-server-stats/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2020-03-23, modifié 2026-09-16

### [DEPRECATED]

This API Call is now considered deprecated.

Please use the following API Call instead:  
<https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors~1{monitor_id}~1server-agent~1metrics/get>

---

### API Call Name:

```
v1 Server Stats
```

### API Call URL:

```
https://api.hetrixtools.com/v1/<API_TOKEN>/server/stats/<UPTIME_MONITOR_ID>/
```

### API Call Info:

This API Call is used to fetch Server Stats sent by your Monitoring Agent to our platform.

To use this API Call, you need to have the Server Monitoring Agent installed on your server:  
<https://docs.hetrixtools.com/category/server-monitor/>

### API Call Link Variables:

* **<API\_TOKEN>** – your API Key, which you can obtain as explained here:  
  <https://docs.hetrixtools.com/api-key/>
* **<UPTIME\_MONITOR\_ID>** – This will be the Uptime Monitor ID that you wish to fetch the stats for. You can get a list of your Uptime Monitors and their IDs by using the following API Call “v1 List Uptime Monitors”. Test out this API Call in your API Explorer:  
  <https://hetrixtools.com/dashboard/api-explorer/>

### API Call Return Payload:

```
{
	"UptimeMonitorName": "Demo Monitor",
	"AgentID": "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
	"AgentAddTime": 1517315417,
	"AgentLastData": 1584984961,
	"AgentVersion": "1.5.9",
	"AgentType": "Linux",
	"AgentIPAddress": "1.2.3.4",
	"SystemUptime": 14420141,
	"OperatingSystem": "Debian 9.11",
	"Kernel": "4.15.18-21-pve",
	"RebootRequired": false,
	"CPUModel": "Intel(R) Core(TM) i7-8700 CPU @ 3.20GHz",
	"CPUSpeed": 4300,
	"CPUCores": 12,
	"RAM": 65876852,
	"Swap": 0,
	"Disk": 7003889068933,
	"Disks": [
		{
			"Mount": "/",
			"Size": 1005869371392,
			"Used": 763354265949,
			"Available": 242515105443,
			"IORead": 42019,
			"IOWrite": 1428300,
			"Inodes": 62439424,
			"InodesUsed": 65095,
			"RAID": {
				"Type": "RAID1",
				"Health": "Healthy",
				"Persistence": "Superblock is persistent",
				"State": "Active",
				"TotalDrives": 2,
				"ActiveDrives": 2,
				"WorkingDrives": 2,
				"SpareDrives": 0,
				"FailedDrives": 0
			}
		},
		{
			"Mount": "/bak",
			"Size": 5999038128128,
			"Used": 3413452694905,
			"Available": 2585585433223,
			"IORead": 0,
			"IOWrite": 0,
			"Inodes": 586052224,
			"InodesUsed": 780,
			"RAID": null
		},
		{
			"Mount": "/boot",
			"Size": 1039032320,
			"Used": 216118723,
			"Available": 822913597,
			"IORead": 0,
			"IOWrite": 0,
			"Inodes": 65536,
			"InodesUsed": 350,
			"RAID": {
				"Type": "RAID1",
				"Health": "Healthy",
				"Persistence": "Superblock is persistent",
				"State": "Clean",
				"TotalDrives": 2,
				"ActiveDrives": 2,
				"WorkingDrives": 2,
				"SpareDrives": 0,
				"FailedDrives": 0
			}
		},
		{
			"Mount": "/etc/pve",
			"Size": 31457280,
			"Used": 15729,
			"Available": 31441551,
			"IORead": 0,
			"IOWrite": 0,
			"Inodes": 10000,
			"InodesUsed": 24,
			"RAID": null
		}
	],
	"Drives": [
		{
			"Name": "nvme0n1",
			"Type": "NVMe",
			"SMARTTest": "PASSED",
			"PowerOnHours": 6,
			"PowerCycles": 8,
			"UnsafeShutdowns": 1,
			"ErrorCount": 0,
			"ErrorDetails": null
		},
		{
			"Name": "nvme1n1",
			"Type": "NVMe",
			"SMARTTest": "PASSED",
			"PowerOnHours": 6,
			"PowerCycles": 8,
			"UnsafeShutdowns": 1,
			"ErrorCount": 0,
			"ErrorDetails": null
		},
		{
			"Name": "sda",
			"Type": "HDD",
			"SMARTTest": "PASSED",
			"PowerOnHours": 13,
			"PowerCycles": 12,
			"UnsafeShutdowns": 7,
			"ErrorCount": 56,
			"ErrorDetails": {
				"ReallocatedSectorCt": 28,
				"ReallocatedEventCount": 28
			}
		}
	],
	"NetworkInterfaces": [
		{
			"Name": "eno1",
			"NetIn": 534350,
			"NetOut": 71742,
			"IPv4": ["1.1.1.1","2.2.2.2"],
			"IPv6": null
		},
		{
			"Name": "vmbr0",
			"NetIn": 145,
			"NetOut": 152,
			"IPv4": null,
			"IPv6": null
		}
	],
	"Services": [
		{
			"Name": "nginx",
			"Status": "online"
		},
		{
			"Name": "mysql",
			"Status": "online"
		}
	],
	"PortConnections": [
		{
			"Port": 80,
			"Connections": 44
		},
		{
			"Port": 443,
			"Connections": 145
		}
	],
	"Stats": [
		{
			"Minute": 1584984900,
			"CPU": 16.42,
			"IOWait": 0,
			"Steal": 0,
			"User": 10.26,
			"System": 6,
			"Temp": 24.32,
			"Load1": 2.22,
			"Load5": 3.26,
			"Load15": 4.08,
			"RAM": 23.47,
			"Swap": 0,
			"Buffered": 1.73,
			"Cached": 25.84,
			"Disk": 6.86,
			"NetIn": 2679570,
			"NetOut": 497664
		},
		...
		{
			"Minute": 1584981360,
			"CPU": 16,
			"IOWait": 0,
			"Steal": 0,
			"User": 9.95,
			"System": 6.11,
			"Temp": 25.74,
			"Load1": 2.78,
			"Load5": 4.07,
			"Load15": 4.54,
			"RAM": 23.6,
			"Swap": 0,
			"Buffered": 1.73,
			"Cached": 25.84,
			"Disk": 6.86,
			"NetIn": 2661110,
			"NetOut": 477932
		}
	]
}
```

### API Call Return Payload Variables:

We’ll go through some variables that are not so self-explanatory and describe them a little bit further.

* **AgentID** – this is the Unique Server ID (SID) that your Server Agent uses to send data to our platform.
* **AgentAddTime** – the Unix timestamp when the Server Agent was installed.
* **AgentLastData** – the Unix timestamp when the Server Agent data was last received by our platform.
* **AgentIPAddress** – the IP address that your server used to send the data to our platform.
* **SystemUptime** – number of seconds that your server has been powered on (just as running “cat /proc/uptime ” on your server).
* **RebootRequired** – whether or not your server requires a reboot in order to finish installing updates. For more info about this, please see:  
  <https://docs.hetrixtools.com/reboot-required-warning/>
* **RAM**, **Swap** – values are in bytes.
* **Disk** – represents the total disk(s) size on your server; value is in bytes.
* **Disks** – contains data for the detected system mount points.
* **RAID** – contains data of the detected Software RAID setups on your system. However, additional steps must be taken to enable these metrics:  
  <https://docs.hetrixtools.com/software-raid-monitoring/>
* **Drives** – contains health data of detected drives. However, additional steps must be taken to enable these metrics:   
  <https://docs.hetrixtools.com/hdd-ssd-nvme-drive-health-monitor/>
* NetworkInterfaces – contains data of the detected network interfaces on your system.
* **Services** – contains the service status of your monitored services. Please see the following article on how to monitor services with your Server Agent:  
  <https://docs.hetrixtools.com/service-monitoring/>
* **PortConnections** – contains the ports and number of connections towards those ports, if you’ve enabled ‘Port Connection Monitoring’ during your Agent Setup.
* **Stats** – contains the last 60 recorded minutes, each record containing the **CPU**, **IOWait**, **RAM**, **Swap**, **Disk** (represented in usage percent), and NetIn, NetOut (represented in bytes) for that particular minute. The Minute value for each of these records represents the Unix timestamp of the minute for which the data belongs, not the timestamp when the data has been registered into our system.

### Stats payload breakdown:

* **CPU** – represents the overall CPU usage, reported as a percentage.
* **IOWait**, **Steal**, **User**, **System** – are CPU usage values broken down into subcategories, reported as percentages.
* **Temp** – represents the CPU temperature and is reported in degrees Celsius.
* **Load1**, **Load5**, **Load15** – represent the CPU Load for 1, 5, 15 minutes, as reported by Linux.
* **RAM** – represents the overall RAM usage in percentage.
* **Swap**, **Buffered**, **Cached** – represent the RAM usage breakdown, reported as percentages.
* **Disk** – represents the overall Disk usage as a percentage.
* **NetIn**, **NetOut** – represent the network incoming and network outgoing traffic, in bytes.

### Please Note:

* Everything in the returned payload represents the current/latest recorded data, except the **Stats** part, which also contains historical data, as explained above.
