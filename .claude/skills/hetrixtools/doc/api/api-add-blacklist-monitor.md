# API – Add Blacklist Monitor

> Source : https://docs.hetrixtools.com/api-add-blacklist-monitor/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2016-10-10, modifié 2018-09-26

API Call Name:

```
v2 Add Blacklist Monitor
```

API Call:

```
https://api.hetrixtools.com/v2/<API_TOKEN>/blacklist/add/
```

Post Variables:  
***target*** – the IP address (i.e.: 1.2.3.4), or IP range (i.e.: 1.2.3.4 – 1.2.3.7), or IP block (i.e.: 1.2.3.4/28), or domain name (i.e.: mydomain.com)  
***label*** – the label for the added monitor(s)  
***contact*** – the contact list ID for the added monitor(s). You can fetch your contact list IDs by using the API Call ‘v1 List Contact Lists’

Sample PHP code to use this API Call:

```
<?php
$api_key = 'YOURKEY'; // Replace with your API Key

$target = ''; // Fill in the target you wish to add
$label = ''; // Optionally add a label for this monitor
$contact = ''; // Fill in the contact list id

$url = 'https://api.hetrixtools.com/v2/'.$api_key.'/blacklist/add/';
$curl = curl_init($url);
curl_setopt($curl, CURLOPT_RETURNTRANSFER, true);
curl_setopt($curl, CURLOPT_POST, true);
curl_setopt($curl, CURLOPT_POSTFIELDS, ["target" => $target, "label" => $label, "contact" => $contact]);
curl_setopt($curl, CURLOPT_SSL_VERIFYPEER, false);
$result = curl_exec($curl);
curl_close($curl);
?>
```

Using this API Call, you can easily add one or more blacklist monitors at once into your account, and will consume one (1) API Call from your monthly quota, regardless of how many IPs you add at once.

You can test out the API Call in our API Explorer:  
<https://hetrixtools.com/dashboard/api-explorer/>

[![screenshot_1](https://docs.hetrixtools.com/wp-content/uploads/2016/10/Screenshot_1.png)](https://docs.hetrixtools.com/wp-content/uploads/2016/10/Screenshot_1.png)

The monitors are added instantly and start being checked right away, just like if you would add them via our interface in your dashboard.

[![screenshot_2](https://docs.hetrixtools.com/wp-content/uploads/2016/10/Screenshot_2.png)](https://docs.hetrixtools.com/wp-content/uploads/2016/10/Screenshot_2.png)
