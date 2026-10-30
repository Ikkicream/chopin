# Uptime Monitoring Webhook Notifications

> Source : https://docs.hetrixtools.com/uptime-monitoring-webhook-notifications/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2016-07-13, modifié 2025-05-27

Assign a webhook URL to any of your contact lists so that you can receive Uptime Monitoring notifications in real-time, directly to your platform.

[![](https://docs.hetrixtools.com/wp-content/uploads/2016/07/z1-1.png)](https://docs.hetrixtools.com/wp-content/uploads/2016/07/z1-1.png)

Our system will post JSON data to your Webhook script. Here’s an example:

```
{  
   "monitor_id":"ThisWillBeTheMonitorID32CharLong",
   "monitor_name":"Test Monitor Label",
   "monitor_target":"http:\/\/this-is-a-test.com\/",
   "monitor_type":"website",
   "monitor_category":"Test Category",
   "monitor_status":"offline",
   "timestamp":1499666192,
   "monitor_errors":{  
      "New York":"http code 403",
      "San Francisco":"http code 403",
      "Dallas":"timeout",
      "Amsterdam":"http code 403",
      "London":"http code 403",
      "Frankfurt":"http code 403",
      "Singapore":"timeout",
      "Sydney":"http code 403",
      "Sao Paulo":"http code 403",
      "Tokyo":"keyword not found",
      "Mumbai":"http code 403",
      "Moscow":"keyword not found"
   }
}
```

Here’s a PHP code example that you could use to capture these variables in your Webhook script:  
`<?php  
 // Get the JSON data  
 $json = file_get_contents('php://input');  
 // Decode the JSON data into an array  
 $array = json_decode($json,true);  
 // Grab variables from the array  
 $monitor_id = $array['monitor_id'];  
 $monitor_name = $array['monitor_name'];  
 $monitor_target = $array['monitor_target'];  
 $monitor_type = $array['monitor_type'];  
 $monitor_category = $array['monitor_category'];  
 $monitor_status = $array['monitor_status'];  
 $monitor_errors = $array['monitor_errors'];  
 $timestamp = $array['timestamp'];  
 ?>`

These are the variables you should receive:  
***monitor\_id***  
 ***monitor\_name***  
 ***monitor\_target***  
 ***monitor\_type*** – can be: ‘website’, ‘ping’, ‘service[X]’, ‘smtp[X]’ (where X is the monitored port)  
 ***monitor\_category***  
 ***monitor\_status*** – can either be *online* or *offline  
**timestamp*** – is the UNIX timestamp at which the event occurred  
 ***monitor\_errors*** – contains an array with each location’s error message

List of all of the possible ***monitor\_errors***:

* for website uptime monitors:  
  – timeout  
  – keyword not found  
  – http code XXX [example: http code 403]
* for ping/service uptime monitors:  
  – timeout
* for smtp uptime monitors:  
  – connection failed  
  – ssl failed  
  – auth failed

\*Please note that ***monitor\_errors*** is only transmitted when the ***monitor\_status*** is *offline*.

You can find the ***monitor\_id***of any of your uptime monitors by simply accessing their uptime report. The ***monitor\_id***will be in the URL:

[![Screenshot_2](https://docs.hetrixtools.com/wp-content/uploads/2016/07/Screenshot_2-6.png)](https://docs.hetrixtools.com/wp-content/uploads/2016/07/Screenshot_2-6.png)

Once you have captured the variables, you can use them however you wish with your own code.

Make sure to sanitize the captured data before using it.

If you wish to restrict access to your webhook script, here are the IP addresses that will send out our webhook notifications: ****<https://www.cloudflare.com/ips/>****
