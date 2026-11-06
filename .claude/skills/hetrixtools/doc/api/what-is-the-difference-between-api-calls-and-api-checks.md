# What is the difference between API Calls and API Checks?

> Source : https://docs.hetrixtools.com/what-is-the-difference-between-api-calls-and-api-checks/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2017-06-14, modifié 2018-07-27

### **API Calls**

Represents the number of maximum API Calls your account can do per month. Every time you do a request on our API, using your [API Key](https://docs.hetrixtools.com/api-key/), one API Call is being used from your monthly quota. Each package has a different number of monthly API Calls included.

To find out your remaining API Calls for the current month, go to our [API Explorer](https://hetrixtools.com/dashboard/api-explorer/) and run the “v1 API Status” API Call. The “API\_Status” section is what you should be looking at:

[![](https://docs.hetrixtools.com/wp-content/uploads/2017/06/z1-2.png)](https://docs.hetrixtools.com/wp-content/uploads/2017/06/z1-2.png)

* *Max\_API\_Calls* – represents the number of monthly maximum API Calls that your account can make.
* *Remaining\_API\_Calls* – represents the number of API Calls that you have left for the current month.

### **API Checks** (also referred to as [Blacklist Check Credits](https://docs.hetrixtools.com/blacklist-check-credits/) in our documentation)

Represents the number of maximum Blacklist Checks that you can perform via the API. For more info on our Blacklist Check API, please see the following [article](https://docs.hetrixtools.com/blacklist-check-api/). Just as with API Calls, every package has a monthly quota of API Checks that can be performed.

To find out your remaining API Checks for the current month, go to our [API Explorer](https://hetrixtools.com/dashboard/api-explorer/) and run the “v1 API Status” API Call. And you will be looking at the “API\_Blacklist\_Check\_Status” part of the results:

[![](https://docs.hetrixtools.com/wp-content/uploads/2017/06/z4.png)](https://docs.hetrixtools.com/wp-content/uploads/2017/06/z4.png)

* *Monthly\_API\_Checks\_From\_Package* – is the number of API Checks that you receive every month from your Blacklist Monitor package. These are non transferable from one month to another. This amount varies based on which Blacklist Monitoring package you currently have. For more info, check our [Blacklist Monitoring Pricing](https://hetrixtools.com/pricing/blacklist-monitor/).
* *Spent\_API\_Checks\_This\_Month* – is the number of API Checks that you have spent out of your “*Monthly\_API\_Checks\_From\_Package”.*
* *Extra\_API\_Checks\_Available* – is the number of extra API Checks that you have purchased. These will remain in your account until used, and are always consumed after you run out of “*Monthly\_API\_Checks\_From\_Package”.*For more info regarding the API Blacklist Check credits system, see our [documentation](https://docs.hetrixtools.com/blacklist-check-credits/).
* *Total\_API\_Checks\_Left* – represents the remaining API Checks that you can perform this month. [Formula: *Monthly\_API\_Checks\_From\_Package* – *Spent\_API\_Checks\_This\_Month* + *Extra\_API\_Checks\_Available*].

**Notes:**

* API Calls usage gets reset on the 1st of every month.
* The monthly API Checks received from your Blacklist Monitor package are awarded on the 1st of every month.
