# API – Delete Blacklist Monitor

> Source : https://docs.hetrixtools.com/api-delete-blacklist-monitor/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2016-10-10, modifié 2018-09-28

API Call Name:

```
v2 Delete Blacklist Monitor
```

API Call:

```
https://api.hetrixtools.com/v2/<API_TOKEN>/blacklist/delete/
```

Post Variables:  
***target*** – the IP address (i.e.: 1.2.3.4), or IP range (i.e.: 1.2.3.4 – 1.2.3.7), or IP block (i.e.: 1.2.3.4/28), or domain name (i.e.: mydomain.com).

Sample PHP code to use this API Call:

```
<?php
$api_key = 'YOURKEY'; // Replace with your API Key

$target = ''; // Fill in the target you wish to delete

$url = 'https://api.hetrixtools.com/v2/'.$api_key.'/blacklist/delete/';
$curl = curl_init($url);
curl_setopt($curl, CURLOPT_RETURNTRANSFER, true);
curl_setopt($curl, CURLOPT_POST, true);
curl_setopt($curl, CURLOPT_POSTFIELDS, ["target" => $target]);
curl_setopt($curl, CURLOPT_SSL_VERIFYPEER, false);
$result = curl_exec($curl);
curl_close($curl);
?>
```

This API Call allows you to delete one or more IPs or a domain name from your blacklist monitors, consuming one (1) API Call from your monthly quota, regardless of how many monitors are removed at once.

You can test out the API Call in our API Explorer:  
<https://hetrixtools.com/dashboard/api-explorer/>

[![screenshot_1](https://docs.hetrixtools.com/wp-content/uploads/2016/10/Screenshot_1-1.png)](https://docs.hetrixtools.com/wp-content/uploads/2016/10/Screenshot_1-1.png)
