# API – Add Website/Ping/Service/SMTP Uptime Monitor

> Source : https://docs.hetrixtools.com/api-add-website-ping-service-smtp-uptime-monitor/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2021-04-23, modifié 2026-01-23

API Call Name:

```
v2 Add Uptime Monitor
```

API Call:

```
https://api.hetrixtools.com/v2/<API_TOKEN>/uptime/add/
```

Create a POST request to the API link with a JSON payload built as instructed below.

### General JSON body

You can use the body below when adding any type of Uptime Monitor. Please note that some variables are not needed/ignored for certain Uptime Monitor types.

```
{
   "MID":"",
   "Type":"",
   "Name":"",
   "Target":"",
   "Timeout":10,
   "Frequency":1,
   "FailsBeforeAlert":3,
   "FailedLocations":"",
   "ContactList":"",
   "Category":"",
   "AlertAfter":"",
   "RepeatTimes":"",
   "RepeatEvery":"",
   "Public":false,
   "ShowTarget":true,
   "VerSSLCert":false,
   "VerSSLHost":false,
   "Locations":{
      "nyc":false,
      "sfo":false,
      "dal":false,
      "ams":true,
      "lon":false,
      "fra":false,
      "sgp":false,
      "syd":false,
      "sao":false,
      "tok":false,
      "mba":true,
      "waw":false
   }
}
```

* **MID** – Monitor ID to edit or delete. Needed when editing or deleting a monitor. Ignored when adding a monitor.
* **Type** – Monitor Type. *Accepted: 1 – Website, 2 – Ping/Service, 3 – SMTP, 9 – Server Agent Monitor.*
* **Name** – Monitor Name. *Accepted: a-z, A-Z, 0-9, spaces, dots, dashes.*
* **Target** – Link for Website Uptime Monitors, IP/Hostname for Ping/Service/SMTP. | Ignored for Server Agent Monitor
* **Timeout** – Timeout. *Accepted: 3, 5, 10, [15 is available just for the website type]. Suggested: 10. | Values accepted for Server Agent Monitor: 60, 120, 180, 240, 300, 600, 900, 1800, 3600.* *Suggested: 300.*
* **Frequency** – Checkup frequency (minutes). *Accepted: 1, 3, 5, 10. Suggested: 1.* | Ignored for Server Agent Monitor.
* **FailsBeforeAlert** – Failed tries before issuing an alert. *Accepted: 1-3. Suggested: 3.* | Ignored for Server Agent Monitor.
* **FailedLocations** – [Optional] Failed locations before issuing alert. *Accepted: 2-12. Suggested: 50%+1 of number of monitored locations. Leave empty for auto.* | Ignored for Server Agent Monitor.
* **ContactList** – [Optional] Contact List ID, leave empty for none.
* **Category** – [Optional] Category for this monitor, leave empty for none.
* **AlertAfter** – [Optional] Alert only after X minutes, leave empty to disable. *Accepted: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 30, 40, 50, 60 [must be multiple of Frequency].*
* **RepeatTimes** – [Optional] Repeat alert X times, leave empty to disable. *Accepted: 0-30.*
* **RepeatEvery** – [Optional] Repeat alert every X minutes, leave empty to disable. *Accepted: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 30, 40, 50, 60 [must be multiple of Frequency].*
* **Public** – Privacy for this monitor’s Uptime Report. *Accepted: true, false.*
* **ShowTarget** – Whether or not to show the monitored target in the uptime report. *Accepted: true, false.*
* **VerSSLCert** – Whether or not to verify the SSL certificate of the monitored target. *Accepted: true, false.* | Ignored for Server Agent Monitor.
* **VerSSLHost** – Whether or not to verify the SSL host of the monitored target. *Accepted: true, false.* | Ignored for Server Agent Monitor.

For any Uptime Monitor type other than Server Agent Monitor, you’ll also need to add the Locations array to the JSON payload:

* **nyc** – New York. *Accepted: true, false.* | Ignored for Server Agent Monitor.
* **sfo** – San Francisco. *Accepted: true, false.* | Ignored for Server Agent Monitor.
* **dal** – Dallas. *Accepted: true, false.* | Ignored for Server Agent Monitor.
* **ams** – Amsterdam. *Accepted: true, false.* | Ignored for Server Agent Monitor.
* **lon** – London. *Accepted: true, false.* | Ignored for Server Agent Monitor.
* **fra** – Frankfurt. *Accepted: true, false.* | Ignored for Server Agent Monitor.
* **sgp** – Singapore. *Accepted: true, false.* | Ignored for Server Agent Monitor.
* **syd** – Sydney. *Accepted: true, false.* | Ignored for Server Agent Monitor.
* **sao** – Sao Paulo. *Accepted: true, false.* | Ignored for Server Agent Monitor.
* **tok** – Tokyo. *Accepted: true, false.* | Ignored for Server Agent Monitor.
* **mba** – Mumbai. *Accepted: true, false.* | Ignored for Server Agent Monitor.
* **waw** – Warsaw. *Accepted: true, false.* | Ignored for Server Agent Monitor.

### Type-specific JSON additions

You’ll need to add the following to your JSON body, based on the type of Uptime Monitor that you’re adding.

#### Website Uptime Monitor

```
{
   "Method":"HEAD",
   "Keyword":"",
   "HTTPCodes":"200",
   "MaxRedirects":"5",
   "SSLExpiryReminder":"0",
   "DomainExpiryReminder":"0",
   "NSChangeAlert":"0"
}
```

* **Method** – [Optional] Either `GET` or `HEAD` as the desired HTTP method used to access your website.
* **Keyword** – [Optional] Keyword to look for on the monitored website, leave empty for none. *Max length: 128.*
* **HTTPCodes** – [Optional] Specify the accepted HTTP codes (separated by a comma). Your website will be considered online if any of these HTTP codes are returned.
* **MaxRedirects** – Maximum number of redirects to follow. *Accepted: 0-10.*
* **SSLExpiryReminder** – [Optional] The number of days to be warned before SSL Certificate Expiration. Allowed values: 0 (off), 1, 2, 3, 5, 10, 15, 30.
* **DomainExpiryReminder** – [Optional] The number of days to be warned before Domain Expiration. Allowed values: 0 (off), 1, 2, 3, 5, 10, 15, 30.
* **NSChangeAlert** – [Optional] Turn on (1) or off (0) the Nameservers Change detection alerts system.

#### Ping/Service Uptime Monitor

```
{
   "Port":"",
   "DomainExpiryReminder":"0",
   "NSChangeAlert":"0"
}
```

* **Port** – [Optional] Port to be monitored, leave empty for PING. *Accepted: 0-65535.*
* **DomainExpiryReminder** – [Optional] The number of days to be warned before Domain Expiration. Allowed values: 0 (off), 1, 2, 3, 5, 10, 15, 30.
* **NSChangeAlert** – [Optional] Turn on (1) or off (0) the Nameservers Change detection alerts system.

#### SMTP Uptime Monitor

```
{
   "Port":"",
   "CheckAuth":false,
   "SMTPUser":"",
   "SMTPPass":"",
   "DomainExpiryReminder":"0",
   "NSChangeAlert":"0"
}
```

* **Port** – SMTP Port to be monitored. *Accepted: 0-65535.*
* **CheckAuth** – Whether or not to check the SMTP authentication functionality. *Accepted: true, false.*
* **SMTPUser** – If CheckAuth is set to true, provide the SMTP Username.
* **SMTPPass** – If CheckAuth is set to true, provide the SMTP Password.
* **DomainExpiryReminder** – [Optional] The number of days to be warned before Domain Expiration. Allowed values: 0 (off), 1, 2, 3, 5, 10, 15, 30.
* **NSChangeAlert** – [Optional] Turn on (1) or off (0) the Nameservers Change detection alerts system.

#### Server Agent Monitor

```
{
   "INFOPub":false,
   "CPUPub":false,
   "RAMPub":false,
   "DISKPub":false,
   "NETPub":false
}
```

* **INFOPub** – Make the Server Monitoring ‘Server Info’ section public on the Uptime Report page. *Accepted: true, false.*
* **CPUPub** – Make the Server Monitoring ‘CPU Usage’ section public on the Uptime Report page. *Accepted: true, false.*
* **RAMPub** – Make the Server Monitoring ‘RAM Usage’ section public on the Uptime Report page. *Accepted: true, false.*
* **DISKPub** – Make the Server Monitoring ‘Disk Usage’ section public on the Uptime Report page. *Accepted: true, false.*
* **NETPub** – Make the Server Monitoring ‘Network Usage’ section public on the Uptime Report page. *Accepted: true, false.*

---

A ‘proof of concept’ PHP script can be found here:   
<https://gist.github.com/hetrixtools/3789e032af9224be2cdf49e557a7d484>
