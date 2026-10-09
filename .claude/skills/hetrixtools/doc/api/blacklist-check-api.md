# Blacklist Check API

> Source : https://docs.hetrixtools.com/blacklist-check-api/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2016-08-10, modifié 2019-01-19

API Call Names:

```
v2 Blacklist Check IPv4 IP Address
v2 Blacklist Check Domain/Hostname
```

API Calls:

```
https://api.hetrixtools.com/v2/<API_TOKEN>/blacklist-check/ipv4/<IP_ADDRESS>/
https://api.hetrixtools.com/v2/<API_TOKEN>/blacklist-check/domain/<DOMAIN>/
```

If you haven’t already, you can give it a go in our API Explorer: <https://hetrixtools.com/dashboard/api-explorer/>

[![Screenshot_1](https://docs.hetrixtools.com/wp-content/uploads/2016/08/Screenshot_1-3.png)](https://docs.hetrixtools.com/wp-content/uploads/2016/08/Screenshot_1-3.png)

These API Calls will perform a blacklist check for one IPv4 IP address or domain/hostname, on-demand, when initiated.

In the example below, we’re going to blacklist check an IP address via the API.

Let’s begin by introducing an IP address to be checked, and pressing the “Go” button.

[![Screenshot_1](https://docs.hetrixtools.com/wp-content/uploads/2016/08/Screenshot_1-4.png)](https://docs.hetrixtools.com/wp-content/uploads/2016/08/Screenshot_1-4.png)

[![Screenshot_2](https://docs.hetrixtools.com/wp-content/uploads/2016/08/Screenshot_2-3.png)](https://docs.hetrixtools.com/wp-content/uploads/2016/08/Screenshot_2-3.png)

It can take up to 5 minutes for the results to load, as our system performs real time blacklist checks against all available RBLs.

The processing time can vary based on the current overall load of our Blacklist Monitoring queue. The API Blacklist Checks getting the highest priority possible.

It is advisable to take into consideration that the results can take up to 5 minutes to load, so be sure to allow this time in your application, so it will not time out.

However, once the API Call has been initiated, you can close the connection if you do not wish for your application to wait on it. The API Call will keep processing quietly in the background on our platform, and you can check up on its status using the same exact API Call. If the blacklist check of your API Call is still in progress, you will receive an error, like this:

```
{
	"status": "ERROR",
	"error_message": "blacklist check in progress for this ipv4"
}
```

This means that the API Call blacklist check is still in progress. You can repeat the same API Call until the results are displayed. This action will not count towards your monthly max API Calls limit, nor will it consume any Blacklist Check Credits.

Whether you let the initial API Call load up or you check up on it with subsequent identical API Calls, when our system finishes the blacklist check, this API Call will display the results, which will look like this:

```
{
	"status": "SUCCESS",
	"api_calls_left": 69989,
	"blacklist_check_credits_left": 3,
	"blacklisted_count": 10,
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
			"rbl": "dnsbl.sorbs.net",
			"delist": "http://www.sorbs.net/lookup.shtml?68.63.21.24"
		},
		{
			"rbl": "dul.dnsbl.sorbs.net",
			"delist": "http://www.sorbs.net/lookup.shtml?68.63.21.24"
		},
		{
			"rbl": "dul.pacifier.net",
			"delist": "http://www.stopspam.org/index.php"
		},
		{
			"rbl": "dyn.nszones.com",
			"delist": "http://db.nszones.com/dyn.ip?68.63.21.24"
		},
		{
			"rbl": "pbl.spamhaus.org",
			"delist": "https://www.spamhaus.org/query/ip/68.63.21.24"
		},
		{
			"rbl": "safe.dnsbl.sorbs.net",
			"delist": "http://www.sorbs.net/lookup.shtml?68.63.21.24"
		},
		{
			"rbl": "zen.spamhaus.org",
			"delist": "https://www.spamhaus.org/query/ip/68.63.21.24"
		},
		{
			"rbl": "bad.psky.me",
			"delist": "http://psky.me/check/?ip=68.63.21.24"
		}
	],
	"links": {
		"report_link": "https://hetrixtools.com/report/blacklist/2efb7eef954d06a3e4f15c559434bcdc/",
		"whitelabel_report_link": "http://status.hetrixtools.com/report/blacklist/2efb7eef954d06a3e4f15c559434bcdc/",
		"api_report_link": "https://api.hetrixtools.com/v1/6c87e0318e63ae0fbcfb66f3fe3ac355/blacklist/report/68.63.21.24/",
		"api_blacklist_check_link": "https://api.hetrixtools.com/v2/6c87e0318e63ae0fbcfb66f3fe3ac355/blacklist-check/ipv4/68.63.21.24/"
	}
}
```

These results will be cached, for this API Call, for 30 minutes. This means that the results for this IP address are cached for 30 minutes as well. You cannot initiate another blacklist check for the same IP address within these 30 minutes, since the cached results will come up when you initiate the API Call. Fetching the cached results will not cost you any Blacklist Check Credits, but it will cost you an API Call towards your monthly max API Calls. Once the 30 minutes are up, the cache will expire and if you initiate the same API Call after that, it will begin the cycle all over again, doing a real-time blacklist check and then caching those results for the next 30 minutes. If you wish to modify the cache time for these results for your account, please open a support ticket.

Each blacklist check API Call, which doesn’t fetch cached results, will initiate a real-time blacklist check from our platform, and will consume one Blacklist Check Credit from your account. We’ll provide further info on how Blacklist Check Credits work in a different documentation article.

The blacklist check API Call and its results will behave differently depending on whether or not you already have the blacklist check IP added in your blacklist monitors. So, we’ll describe each case scenario below:

**a) if the blacklist check IP is not already added in your blacklist monitors:**

* the API Call will temporarily add the checked IP address into your account
* the IP address will follow all the rules any of your Blacklist Monitors would, i.e.: [Ignored RBLs](https://docs.hetrixtools.com/ignore-a-blacklist/)
* the IP address will be queued for checkup
* the blacklist check is performed without our algorithm which takes into account previous history data of the IP address in order to provide more accurate results ([find more info here](https://docs.hetrixtools.com/blacklist-check-vs-blacklist-monitor/))
* once the blacklist check is finished, the IP address is removed from your account, leaving behind just the API Call results and the generated blacklist report (links for the report are found in the API Call result)
* the API Call results will be cached as explained above, for 30 minutes, while the blacklist report will remain in your account for X days based on your package history retention time
* the blacklist report is private by default, but you can make it public from the report page (link to report provided in the API Call result)
* if you wish to have all of your API generated blacklist reports public, you can do so from your [Account Settings](https://hetrixtools.com/dashboard/account/settings/#blacklist-monitor), look for ‘Blacklist Check API reports Public’ (this is needed if you wish to use the white label reports generated via the API, as white label reports need to be public)

**b) if the blacklist check IP is already added in your blacklist monitors:**

* if the IP address monitor has been automatically checked within the last 30 minutes, the API Call will fetch and cache those results, disregarding everything else that follows in point **b)**
* the API Call will initiate an on-demand blacklist check on your IP address monitor
* the IP address will follow all the rules any of your Blacklist Monitors would, i.e.: [Ignored RBLs](https://docs.hetrixtools.com/ignore-a-blacklist/)
* the IP address will be queued for checkup
* the blacklist check is performed using our algorithm which takes into account your previous history data of the IP address in order to provide more accurate results ([find more info here](https://docs.hetrixtools.com/blacklist-check-vs-blacklist-monitor/))
* once the blacklist check is finished, the IP address is kept in your blacklist monitors list, to be automatically checked again after X hours (based on your package). The blacklist report associated with this IP address will also be updated to contain the new data
* the API Call results are cached for 30 minutes, as explained above
* the generated blacklist report will actually be the same report as your monitored IP address report, with updated data, so it will follow the privacy settings you currently have for this blacklist monitor

Every blacklist check API Call result will also contain your remaining Blacklist Check Credits, so your application can always know how many more checks it can perform, or you can even configure it to warn you when your credit gets low.

If your Blacklist Check Credit runts out, you will receive an error result:

```
{
	"status": "ERROR",
	"error_message": "no blacklist check credits"
}
```

You can find more info on how Blacklist Check Credits work here:  
<https://docs.hetrixtools.com/blacklist-check-credits/>
