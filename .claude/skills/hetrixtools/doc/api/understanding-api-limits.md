# Understanding API Limits

> Source : https://docs.hetrixtools.com/understanding-api-limits/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2025-02-26, modifié 2025-02-26

### v3 API endpoints

These are part of our latest API generation, and their documentation can be found here:  
<https://docs.hetrixtools.com/api/v3/>

The v3 API endpoints don’t have monthly caps, but each endpoint has rate-limiting. Each API response will contain headers with details about these rate limits and the time they’ll reset. You can find the full documentation about the v3 rate-limiting here:  
<https://docs.hetrixtools.com/api/v3/#section/Introduction/Rate-Limiting>

### v1 and v2 API endpoints

These are the APIs that you can find in our [**API Explorer**](https://hetrixtools.com/dashboard/api-explorer/) and represent our older API generations.

Their limits are as follows:

* 120 requests per minute for all v1/v2 endpoints combined
* max monthly requests based on your current plan

To check how many monthly API requests you currently have and how many you have left, you’ll need to run the `v1 API Status` API call (found in our [**API Explorer**](https://hetrixtools.com/dashboard/api-explorer/)). From its results, you can look at the following:

* `Max_API_Calls` – this represents your total monthly maximum v1/v2 API calls and is based on your current Blacklist and Uptime Monitoring plans (each plan contains a number of monthly API calls, which you can see on our pricing pages).
* `Remaining_API_Calls` – represents the number of monthly v1/v2 API calls you have left for the current month. These always reset on the 1st of every month.

If you’re performing Blacklist Checks via our API with the following 2 API calls:  
`v2 Blacklist Check IPv4 IP Address`  
`v2 Blacklist Check Domain/Hostname`  
these work on a credits system, as described here:  
<https://docs.hetrixtools.com/blacklist-check-credits/>
