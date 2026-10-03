# Blacklist Monitoring Webhook Notifications

> Source : https://docs.hetrixtools.com/blacklist-monitoring-webhook-notifications/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2017-03-06, modifié 2021-07-17

With Blacklist Monitoring webhook notifications, you can receive JSON data posted to your webhook URL when changes are detected in your Blacklist Monitors.

Assign your webhook URL to any of your Contact Lists, as shown below:

[![](https://docs.hetrixtools.com/wp-content/uploads/2016/07/z1-1.png)](https://docs.hetrixtools.com/wp-content/uploads/2016/07/z1-1.png)

*(Please note that as of right now, the “Send test notification” button will only send out an Uptime Monitoring webhook notification. You can read more about the webhook [here](https://docs.hetrixtools.com/uptime-monitoring-webhook-notifications/). This means you cannot test Blacklist Monitoring webhooks using this feature.)*

Once you’ve set up your webhook URL in your Contact List, whenever this Contact List is to be notified of changes in your Blacklist Monitors, it will post JSON formatted data to your webhook URL. You can find such an example below (containing two items, i.e., data from two monitors):

```
[
   {
      "monitor": "98.88.89.102",
      "label": "some label",
      "blacklisted_before": "7",
      "blacklisted_now": "6",
      "blacklisted_on": [
         {
            "rbl": "bl.nszones.com",
            "delist": "http://www.nszones.com/contact.shtml"
         },
         {
            "rbl": "bl.score.senderscore.com",
            "delist": "https://www.senderscore.org/blacklistlookup/"
         },
         {
            "rbl": "cidr.bl.mcafee.com",
            "delist": "https://kc.mcafee.com/corporate/index?page=content&id=KB53783"
         },
         {
            "rbl": "dyn.nszones.com",
            "delist": "http://db.nszones.com/dyn.ip?98.88.89.102"
         },
         {
            "rbl": "pbl.spamhaus.org",
            "delist": "https://www.spamhaus.org/query/ip/98.88.89.102"
         },
         {
            "rbl": "zen.spamhaus.org",
            "delist": "https://www.spamhaus.org/query/ip/98.88.89.102"
         }
      ],
      "links": {
         "report_link": "https://hetrixtools.com/report/blacklist/c855b5712bd63a3c8153690b56d5385e/",
         "whitelabel_report_link": "http://status.hetrixtools.com/report/blacklist/c855b5712bd63a3c8153690b56d5385e/"
      }
   },
   {
      "monitor": "190.129.206.24",
      "label": "another label",
      "blacklisted_before": "2",
      "blacklisted_now": "0",
      "blacklisted_on": null,
      "links": {
         "report_link": "https://hetrixtools.com/report/blacklist/4255d1931a5c5547a0fce88e6cdff008/",
         "whitelabel_report_link": "http://status.hetrixtools.com/report/blacklist/4255d1931a5c5547a0fce88e6cdff008/"
      }
   }
]
```

Items in the JSON data will stack up to 100 times. If there are more than 100 changes detected simultaneously, our system will post multiple chunks of data, each containing a maximum of 100 items per chunk.

We’ve determined that chunks can reach up to 512 KB of data from our tests, so make sure that your webhook script can handle such sizes and that it will not timeout.

You should also ensure that your webhook script is prepared and “knows” how to handle multiple consecutive posts at once for cases where our system has more than 100 items to notify you about and will have to send multiple chunks of data at once.

Please note that the webhook notifications will follow the contact list and account settings rules, for instance (but not limited to):  
– [Blacklist monitor change notification threshold](https://docs.hetrixtools.com/blacklist-monitor-change-notification-threshold/)  
– [Stack blacklist monitor notifications for X hours](https://docs.hetrixtools.com/stack-blacklist-monitor-notifications-for-x-hours/)  
– [Do Not Disturb Schedule](https://docs.hetrixtools.com/do-not-disturb-schedule/)

This means that, unlike the Uptime Monitoring webhook notifications, which trigger instantly, the Blacklist Monitoring webhook notifications will stack up and are sent out every X hours, as per your account settings (minimum setting every 1 hour).

**Which IP(s) will this data be posted from?**

**Cloudflare IPs: <https://www.cloudflare.com/ips/>**

*(useful if you’ll want to restrict access to your webhook script)*

**How to capture this data?**

The webhook script should be quite simple. Here’s a PHP example of how you can capture the posted data from our system:  
 `<?php  
 // Get the JSON data  
 $json = file_get_contents('php://input');  
 // Decode the JSON data into an array  
 $array = json_decode($json,true);  
 ?>`

Once you have captured the JSON data and converted it into an array, you can handle and manage it however you wish.

**What to expect when monitoring a big number of IPs/Domains?**

If you’re monitoring tens/hundreds of thousands of IPs or Domains, you should design your webhook script to be able to handle cases where big blocks of IPs get delisted or blacklisted at once, which means that a lot of data will be posted from our system to your webhook URL at the same time.

In such cases, we’d recommend storing all of the data locally in your environment and then process it separately via other scripts. This way, the webhook script would only handle receiving the data and not processing it simultaneously. If your webhook script is handling both data receiving and data processing, when receiving a lot of chunks, it may take a long time to load and process that data, which may cause our system to timeout when posting some chunks of data. Please note that if our system encounters timeouts on your webhook URL, it will retry sending the data a few more times before giving up.
