# Moscow Relocation API/Webhook Changes

> Source : https://docs.hetrixtools.com/moscow-relocation-api-webhook-changes/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2022-02-28, modifié 2022-02-28

*[February 28, 2022]*

## The changes below will take effect on March 10, 2022.

#### These changes only affect you if you’re using our Uptime Monitoring API or Uptime Monitoring Webhooks.

1). [Add/Edit Uptime Monitor API](https://docs.hetrixtools.com/api-add-website-ping-service-smtp-uptime-monitor/):

* The `msw` variable name will be replaced with `waw`
* The change is backwards compatible, meaning that if our system will still receive the `msw` variable, it will convert it into `waw` automatically on our end

2). “v1 List Uptime Monitors” and “v1 Uptime Report” API calls:

* All instances of the `Moscow` variable will be replaced with the `Warsaw` variable.
* Example:  
   Old:  

  ```
  "Response_Time": {
      "New_York": "34",
      "Amsterdam": "511",
      "Moscow": "396"
  },
  ```

    
   New:  

  ```
  "Response_Time": {
      "New_York": "34",
      "Amsterdam": "511",
      "Warsaw": "396"
  },
  ```
* This change is not backwards compatible

3). [“v3 GET Uptime Monitors” – API](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors/get):

* The `moscow` variable will be replaced with the `warsaw` variable
* This change is not bawdwards compatible

4). [“v3 GET Location Fail Log” – API](https://docs.hetrixtools.com/api/v3/#/paths/~1uptime-monitors~1{monitor_id}~1location-fail-log/get):

* All all instances of the keyword “Moscow” from our [Location Fail Log](https://docs.hetrixtools.com/location-fail-log/) will be replaced with the keyword “Warsaw”
* This change is not bawdwards compatible
