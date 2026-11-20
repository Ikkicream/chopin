# API Uptime Monitor Maintenance Mode

> Source : https://docs.hetrixtools.com/api-uptime-monitor-maintenance-mode/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2017-01-22, modifié 2021-06-09

API Call Name:

```
v2 Uptime Maintenance Mode
```

API Call:

```
https://api.hetrixtools.com/v2/<API_TOKEN>/maintenance/<UPTIME_MONITOR_ID>/<MAINTENANCE_MODE>/
```

Understanding the variables:

* **<API\_TOKEN>**– Your API Access Token.
* **<UPTIME\_MONITOR\_ID>**– You can find the ID of any of your Uptime Monitors by using the API Call ‘v1 List Uptime Monitors’. It is listed for every uptime monitor as ‘ID’.
* **<MAINTENANCE\_MODE>**– The type of maintenance. Accepted values (numbers): 1, 2, or 3.
  + 1 – no maintenance mode (normal) – use this to exit maintenance mode
  + 2 – maintenance mode with notifications
  + 3 – maintenance mode without notifications

Using this API Call you can easily program your website or platform to put any of your uptime monitors in or out of maintenance mode.

Test out this API Call in our API Explorer:  
<https://hetrixtools.com/dashboard/api-explorer/>

[![](https://docs.hetrixtools.com/wp-content/uploads/2017/01/Screenshot_1-4.png)](https://docs.hetrixtools.com/wp-content/uploads/2017/01/Screenshot_1-4.png)
