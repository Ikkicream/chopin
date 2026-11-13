# Understanding our APIs

> Source : https://docs.hetrixtools.com/understanding-our-apis/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2024-05-14, modifié 2024-05-14

We currently offer three API versions: v1, v2, and v3.

## v3

The v3 API is a RESTful API and it’s our latest API version, where we aim to gradually port over all other API calls from v1/v2.

The v3 documentation can be found here:

* <https://docs.hetrixtools.com/api/v3/>

#### Limits

Limits for the v3 API are per user per API call per minute. With every API call performed, you can see the limits in the headers as explained here:

* <https://docs.hetrixtools.com/api/v3/#section/Introduction/Rate-Limiting>

These limits are currently the same for all of our users. However, for our Enterprise customers we can adjust the limits to fit their needs.

## v1/v2

Our v1/v2 APIs are non-RESTful APIs, which have been developed earlier on during the lifetime of our platform.

You can find all of these APIs in our API Explorer:

* <https://hetrixtools.com/dashboard/api-explorer/>

#### Limits

The limits for v1/v2 APIs are per user per month, and they are specific for each free/paid plan that you are currently on.

You can view each plan’s limits on our pricing pages:

* <https://hetrixtools.com/pricing/uptime-monitor/>
* <https://hetrixtools.com/pricing/blacklist-monitor/>

[![](https://docs.hetrixtools.com/wp-content/uploads/2024/05/image-1024x60.png)](https://docs.hetrixtools.com/wp-content/uploads/2024/05/image.png)

If you need higher v1/v2 monthly limits, we can accommodate this on a case-by-case request; be sure to reach out to our support and explain your use case.

#### Exceptions

The only exceptions from the v1/v2 monthly API calls limits explained above are the Blacklist Check APIs:

* <https://docs.hetrixtools.com/blacklist-check-api/>

The Blacklist Check APIs don’t consume v1/v2 monthly API calls; they function on a credits-based system, as explained here:

* <https://docs.hetrixtools.com/blacklist-check-credits/>

You can read more about the difference between v1/v2 API Calls and the Blacklist Check APIs here:

* <https://docs.hetrixtools.com/what-is-the-difference-between-api-calls-and-api-checks/>
