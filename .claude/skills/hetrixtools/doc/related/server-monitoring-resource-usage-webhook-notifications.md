# Server Monitoring Resource Usage Webhook Notifications

> Source : https://docs.hetrixtools.com/server-monitoring-resource-usage-webhook-notifications/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2017-07-02, modifié 2025-03-27

In order to receive Server Monitoring Resource Usage webhook notifications, you will need to have the following:

* An Uptime Monitor that has a contact list with Webhooks enabled:  
  – <https://docs.hetrixtools.com/uptime-monitoring-webhook-notifications/>
* Attach a Server Monitor to this Uptime Monitor, and install the Server Agent on your VPS or Dedicated Server:  
  – <https://docs.hetrixtools.com/install-the-hetrixtools-server-monitor-agent/>
* Configure resource usage warnings for this Server Monitor:  
  – <https://docs.hetrixtools.com/set-resource-usage-warnings/>

Once you’ve got all of that configured, whenever you receive Resource Usage alerts, your Webhook URL will receive JSON format data, as well.

General payload parameters:

***`monitor_id`*** – your monitor’s unique ID (can be found in the link of your monitor’s uptime report);  
***`monitor_name`*** – the label of your uptime monitor;  
***`timestamp`***– is the Unix time stamp at which the event occurred;

---

Example of a resource usage webhook notification:

```
{  
   "monitor_id":"ThisWillBeTheMonitorID32CharLong",
   "monitor_name":"Test Monitor Label",
   "timestamp":1499666613,
   "resource_usage":{  
      "resource_type":"cpu",
      "current_usage":"24.60",
      "average_usage":"25.29",
      "average_minutes":"3"
   }
}
```

Parameters:  
***`resource_type`*** – describes which resource type this notification is about; possible values:   
 – *`cpu`*  
 – *`ram`*  
 – *`disk`*  
 – *`network_inbound`*  
 – *`network_outbound`*  
***`current_usage`*** – the current usage (percent) for this server monitor (i.e.: the usage taken the same minute the notification is sent out);  
***`average_usage`*** – the average usage (percent) over ***`average_minutes`*** minutes (based on your resource usage warning configuration).

---

Example of an ‘agent data not sent’ Webhook notification:

```
{  
   "monitor_id":"ThisWillBeTheMonitorID32CharLong",
   "monitor_name":"Test Monitor Label",
   "timestamp":1499666613,
   "resource_usage":{  
      "resource_type":"agent",
      "error":"no data"
   }
}
```

Parameters:  
***`resource_type`*** – describes which resource type this notification is about; possible values:   
– *`agent`* – for server agent data not received notifications  
– *`drive health`* – for drive health related notifications  
– *`raid`* – for RAID related notifications  
– *`service`* – for when any monitored services go down  
***`error`*** – the error that had triggered this webhook notification; possible values:  
– *`no data`* – no data received from the server agent (applies to ***`resource_type`***: *`agent`*)  
– *`increased errors`* – for when drive errors are above the defined threshold (applies to ***`resource_type`***: **`drive health`**)  
– *`increased wearout`* – for when drive wearout is above the defined threshold (applies to ***resource\_type***: **`drive health`**)  
– *`smart test`* – for when drive drive SMART test fails (applies to ***`resource_type`***: **`drive health`**)  
– *`raid issues`* – for RAID detected issues (applies to ***`resource_type`***: ***`raid`***)  
– *`<array of services>`* – the services that are detected down (applies to ***`resource_type`***: ****`service`****), example: `["mysql","nginx","ssh"]`. This array can contain multiple services at once if there is more than one service detected as down.
