# v1 Get Server Agent ID (SID)

> Source : https://docs.hetrixtools.com/v1-get-agentid/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2020-04-11, modifié 2023-03-29

### API Call Name:

```
v1 Get Server Agent ID
```

### API Call URL:

```
https://api.hetrixtools.com/v1/<API_TOKEN>/get/agentid/<UPTIME_MONITOR_ID>/
```

### API Call Info:

This API Call is used to get (or generate) the unique Server Agent ID attached to an Uptime Monitor.

If there is no Server Agent ID attached to the Uptime Monitor that you are requesting it for, a new one will be generated during the API Call.

The Server Agent ID is used by the [Server Agent](https://docs.hetrixtools.com/category/server-monitor/), installed on your server, in order to send data to our platform. Each Server Agent uses a unique Server Agent ID.

### API Call Link Variables:

* **<API\_TOKEN>** – your API Key, which you can obtain as explained here:  
  <https://docs.hetrixtools.com/api-key/>
* **<UPTIME\_MONITOR\_ID>** – this will be the Uptime Monitor ID that you wish to fetch the stats for. You can get a list of your Uptime Monitors, and their IDs by using the following API Call “v1 List Uptime Monitors”. Test out this API Call in your API Explorer:  
  <https://hetrixtools.com/dashboard/api-explorer/>

### API Call Return Payload:

```
{
	"AgentID": "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
	"Status": "old"
}
```

### API Call Return Payload Variables:

* **AgentID** (SID) – will be the unique Server Agent ID that is attached to this Uptime Monitor (that you’ve requested the API Call for)
* **Status** – will either be “*new*” or “*old*“. If this value is “*new*” it means that this Uptime Monitor had no Server Agent ID attached to it, and a new one has just been generated using this API Call; if this value is “*old*” it means that this Uptime Monitor already had a Server Agent ID attached to it.
