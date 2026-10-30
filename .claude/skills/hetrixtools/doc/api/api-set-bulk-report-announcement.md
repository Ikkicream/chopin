# v2 Set Bulk Report Announcement

> Source : https://docs.hetrixtools.com/api-set-bulk-report-announcement/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2019-03-15, modifié 2020-04-11

### API Call Name:

```
v2 Set Bulk Report Announcement
```

### API Call URL:

```
https://api.hetrixtools.com/v2/<API_TOKEN>/announcement/<BULK_REP_ID>/set/
```

### API Call Info:

In order to set or modify the Announcement on any of your Bulk Reports, you will need to post a JSON payload to the API link posted above.

This JSON payload should look like this:

```
{  
   "Title":"Test Title",
   "Body":"Test Body.\\nThis is a new line.\\nAnd another new line.",
   "Color":"danger",
   "Affected":[  
      "monitorID1",
      "monitorID2"
   ]
}
```

In the example above, each field represents:

* “Title” will be the title of your announcement (cannot be empty).
* “Body” will be the announcement message (can be empty, can contain multiple lines separated by the new line character “\n”.
* “Color” can be either: none, success, info, warning, or danger.
* “Affected” is an array of monitor IDs that are affected by this announcement (can be empty).

Below you can find a PHP example of how you could go about using this API Call:

```
$api = 'YOUR_API_KEY';
$bulk_id = 'BULK_REPORT_ID';

$url = 'https://api.hetrixtools.com/v2/'.$api.'/announcement/'.$bulk_id.'/set/';

$post = array(
        'Title'     => 'Test Title',
        'Body'      => 'Test Body.\nThis is a new line.\nAnd another new line.',
        'Color'     => 'danger',
        'Affected'  => array(
                'monitorID1',
                'monitorID2',
            ),
    );
$post = json_encode($post);

// POST
$ch = curl_init();
curl_setopt($ch, CURLOPT_AUTOREFERER, TRUE);
curl_setopt($ch, CURLOPT_HTTPHEADER, array('Content-Type: application/json'));
curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
curl_setopt($ch, CURLOPT_URL, $url);
curl_setopt($ch, CURLOPT_FOLLOWLOCATION, TRUE);
curl_setopt($ch, CURLOPT_TIMEOUT, 10);
curl_setopt($ch, CURLOPT_POST, 1);
curl_setopt($ch, CURLOPT_POSTFIELDS, $post);
$data = curl_exec($ch);
curl_close($ch);
```

Notes:

* To find out your Bulk Report ID, access your Bulk Report in your browser and locate the unique ID in the URL.
* To find out your monitor IDs, for the Affected monitors, look into using the following API Calls: ‘v2 List Blacklist Monitors’ (for Blacklist Monitors) or ‘v1 List Uptime Monitors’ (for Uptime Monitors).
* If no announcement is previously set, this API Call will set an announcement on your Bulk Report. If an announcement was previously set, this API Call will overwrite the old announcement with the new one.
