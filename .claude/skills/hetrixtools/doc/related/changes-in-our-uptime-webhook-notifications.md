# Changes in our Uptime Webhook Notifications

> Source : https://docs.hetrixtools.com/changes-in-our-uptime-webhook-notifications/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2020-09-22, modifié 2021-05-24

*[July 2, 2017]*

We’re slightly modifying the way our Uptime Webhook notifications work, please make the proper adjustments to your Webhook script.

You can find the new Webhook documentation here:  
<https://docs.hetrixtools.com/uptime-monitoring-webhook-notifications/>

The changes you’d need to make to your Webhook script are very minimal.

*If this is how your current capture method looks like:*

<?php  
$monitor\_id = $\_POST[‘monitor\_id’];  
$monitor\_name = $\_POST[‘monitor\_name’];  
$monitor\_target = $\_POST[‘monitor\_target’];  
$monitor\_type = $\_POST[‘monitor\_type’];  
$monitor\_category = $\_POST[‘monitor\_category’];  
$monitor\_status = $\_POST[‘monitor\_status’];

// The rest of your script here

?>

*Just modify it like so, to capture the new Webhook data:*

<?php  
// Get the JSON data  
$json = file\_get\_contents(‘php://input’);  
// Decode the JSON data into an array  
$array = json\_decode($json,true);  
// Grab variables from the array  
$monitor\_id = $array[‘monitor\_id’];  
$monitor\_name = $array[‘monitor\_name’];  
$monitor\_target = $array[‘monitor\_target’];  
$monitor\_type = $array[‘monitor\_type’];  
$monitor\_category = $array[‘monitor\_category’];  
$monitor\_status = $array[‘monitor\_status’];

// The rest of your script here

?>

Other than that, the rest of your Webhook script should function just the same.

Currently, both the old and the new methods are working, so your Webhook script can capture either one.

The old method will be discontinued on 7 July 2017, after which point your Webhook script will not be notified with the old format anymore.

For further support you can always open a ticket on our website.
