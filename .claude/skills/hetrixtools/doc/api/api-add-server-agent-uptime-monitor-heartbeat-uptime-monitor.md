# API – Add Server Agent Uptime Monitor (Heartbeat Uptime Monitor)

> Source : https://docs.hetrixtools.com/api-add-server-agent-uptime-monitor-heartbeat-uptime-monitor/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2021-01-30, modifié 2025-12-16

API Call Name:

```
v2 Add Uptime Monitor
```

API Call:

```
https://api.hetrixtools.com/v2/<API_TOKEN>/uptime/add/
```

Create a POST request to the API link with a JSON payload built as instructed below.

```
{
   "Type":9,
   "Name":"",
   "Timeout":300,
   "Grace":60,
   "ContactList":"",
   "Category":"",
   "AlertAfter":"",
   "RepeatTimes":"",
   "RepeatEvery":"",
   "Public":false,
   "ShowTarget":true,
   "INFOPub":false,
   "CPUPub":false,
   "RAMPub":false,
   "DISKPub":false,
   "NETPub":false
}
```

* **Type** – Monitor Type 9 for Server Agent Monitor.
* **Name** – Monitor Name. *Accepted: a-z, A-Z, 0-9, spaces, dots, dashes.*
* **Timeout** – Time interval, in seconds, our platform will expect to receive heartbeat signals from your server. *Accepted: 60, 120, 180, 240, 300, 600, 900, 1800, 3600.* *Suggested: 300.*
* **Grace** – Time, in seconds, after the Timeout has been reached before marking your monitor as DOWN. *Accepted: 60, 120, 180, 240, 300, 600, 900, 1800, 3600.*
* **ContactList** – [Optional] Contact List ID, leave empty for none.
* **Category** – [Optional] Category for this monitor, leave empty for none.
* **AlertAfter** – [Optional] Alert only after X minutes, leave empty to disable. *Accepted: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 30, 40, 50, 60 [must be multiple of Frequency].*
* **RepeatTimes** – [Optional] Repeat alert X times, leave empty to disable. *Accepted: 0-30.*
* **RepeatEvery** – [Optional] Repeat alert every X minutes, leave empty to disable. *Accepted: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 30, 40, 50, 60 [must be multiple of Frequency].*
* **Public** – Make this monitor’s Uptime Report public. *Accepted: true, false.*
* **ShowTarget** – Make the monitored target public on the Uptime Report page. *Accepted: true, false.*
* **INFOPub** – Make the Server Monitoring ‘Server Info’ section public on the Uptime Report page. *Accepted: true, false.*
* **CPUPub** – Make the Server Monitoring ‘CPU Usage’ section public on the Uptime Report page. *Accepted: true, false.*
* **RAMPub** – Make the Server Monitoring ‘RAM Usage’ section public on the Uptime Report page. *Accepted: true, false.*
* **DISKPub** – Make the Server Monitoring ‘Disk Usage’ section public on the Uptime Report page. *Accepted: true, false.*
* **NETPub** – Make the Server Monitoring ‘Network Usage’ section public on the Uptime Report page. *Accepted: true, false.*

#### Example PHP Code

```
<?php

// Your API Key
$api_key = '';

// Add Uptime Monitor
$api_call = 'https://api.hetrixtools.com/v2/'.$api_key.'/uptime/add/';

// Common Variables
$common = array(
    'Type'              => 9,
    'Name'              => 'Demo Monitor',
    'Timeout'           => 300,
    'Grace'             => 60,
    'ContactList'       => '',
    'Category'          => '',
    'AlertAfter'        => '',
    'RepeatTimes'       => '',
    'RepeatEvery'       => '',
    'Public'            => false,
    'ShowTarget'        => false,
    'INFOPub'           => false,
    'CPUPub'            => false,
    'RAMPub'            => false,
    'DISKPub'           => false,
    'NETPub'            => false,
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
   "error_message":"maximum number of monitors has been reached"
}
```

#### Example Success Output

```
{
   "status":"SUCCESS",
   "monitor_id":"xyz",
   "server_id":"abc",
   "action":"deleted"
}
```

* **monitor\_id** – is the Monitor ID (MID) of the newly added Uptime Monitor. Use this ID in future API Calls to modify/delete this Uptime Monitor.
* **server\_id** – is the [Server ID (SID)](https://docs.hetrixtools.com/where-do-i-find-the-sid-server-monitor-id/) that is to be used in the Server Monitoring Agent in order to send Agent Data towards our platform. Do not make this ID public.
