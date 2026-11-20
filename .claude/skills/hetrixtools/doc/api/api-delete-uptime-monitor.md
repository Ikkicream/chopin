# API – Delete Uptime Monitor

> Source : https://docs.hetrixtools.com/api-delete-uptime-monitor/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2021-01-30, modifié 2021-04-23

API Call Name:

```
v2 Delete Uptime Monitor
```

API Call:

```
https://api.hetrixtools.com/v2/<API_TOKEN>/uptime/delete/
```

Create a POST request to the API link with a JSON payload built as instructed below.

```
{
   "MID":""
}
```

* **MID** – 32 characters long string representing the Uptime Monitor ID that you wish to delete. You can get your monitors’ IDs by using the API Call `v1 List Uptime Monitors`

#### Example PHP Code

```
<?php

// Your API Key
$api_key = '';

// Delete Uptime Monitor
$api_call = 'https://api.hetrixtools.com/v2/'.$api_key.'/uptime/delete/';

// Common Variables
$common = array(
    'MID'               => ''
);

// Prepare JSON
$post = json_encode($post);

// Make the API Call
$ch = curl_init();
curl_setopt($ch, CURLOPT_AUTOREFERER, TRUE);
curl_setopt($ch, CURLOPT_HTTPHEADER, array('Content-Type: application/json'));
curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
curl_setopt($ch, CURLOPT_URL, $api_call);
curl_setopt($ch, CURLOPT_FOLLOWLOCATION, TRUE);
curl_setopt($ch, CURLOPT_TIMEOUT, 10);
curl_setopt($ch, CURLOPT_POST, 1);
curl_setopt($ch, CURLOPT_POSTFIELDS, $post);
$data = curl_exec($ch);
curl_close($ch);

// Return the data
echo $data;

?>
```

#### Example Error Output

```
{
   "status":"ERROR",
   "error_message":"monitor id does not exist"
}
```

#### Example Success Output

```
{
   "status":"SUCCESS",
   "monitor_id":"xyz",
   "action":"deleted"
}
```

---

A ‘proof of concept’ PHP script can be found here:  
<https://gist.github.com/hetrixtools/3789e032af9224be2cdf49e557a7d484>
