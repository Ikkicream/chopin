# API – Edit Blacklist Monitor

> Source : https://docs.hetrixtools.com/api-edit-blacklist-monitor/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2016-10-10, modifié 2018-09-28

API Call Name:

```
v2 Edit Blacklist Monitor
```

API Call:

```
https://api.hetrixtools.com/v2/<API_TOKEN>/blacklist/edit/
```

Post Variables:  
***target*** – the IP address (i.e.: 1.2.3.4), or IP range (i.e.: 1.2.3.4 – 1.2.3.7), or IP block (i.e.: 1.2.3.4/28), or domain name (i.e.: mydomain.com).  
***label*** – the new label for the monitor(s). Can be left empty to remove the label from the targeted monitors.  
***contact*** – the new contact list ID for the monitor(s). You can fetch your contact list IDs by using the API Call ‘v1 List Contact Lists’. Can be left empty to keep current contact list.

Sample PHP code to use this API Call:

```
<?php
$api_key = 'YOURKEY'; // Replace with your API Key

$target = ''; // Fill in the target you wish to edit
$label = ''; // Optionally modify the label
$contact = ''; // Optionally change the contact list id

$url = 'https://api.hetrixtools.com/v2/'.$api_key.'/blacklist/edit/';
$curl = curl_init($url);
curl_setopt($curl, CURLOPT_RETURNTRANSFER, true);
curl_setopt($curl, CURLOPT_POST, true);
curl_setopt($curl, CURLOPT_POSTFIELDS, ["target" => $target, "label" => $label, "contact" => $contact]);
curl_setopt($curl, CURLOPT_SSL_VERIFYPEER, false);
$result = curl_exec($curl);
curl_close($curl);
?>
```

This API Call allows you to modify one or more blacklist monitors at a time, changing their label and/or contact list. It will consume one (1) API Call, regardless of how many monitors you edit at once.

Leave ‘contact’ empty if you wish to keep the current contact list for the targeted monitors.

Leave ‘label’ empty if you wish to remove the current label from the targeted monitors.

You can test out the API Call in our API Explorer:  
<https://hetrixtools.com/dashboard/api-explorer/>

[![screenshot_3](https://docs.hetrixtools.com/wp-content/uploads/2016/10/Screenshot_3.png)](https://docs.hetrixtools.com/wp-content/uploads/2016/10/Screenshot_3.png)

[![screenshot_4](https://docs.hetrixtools.com/wp-content/uploads/2016/10/Screenshot_4.png)](https://docs.hetrixtools.com/wp-content/uploads/2016/10/Screenshot_4.png)

You can obviously only edit monitors that are already added in your account.
