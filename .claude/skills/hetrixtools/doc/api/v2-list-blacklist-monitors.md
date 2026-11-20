# v2 List Blacklist Monitors

> Source : https://docs.hetrixtools.com/v2-list-blacklist-monitors/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2017-02-07, modifié 2018-09-28

API Call Name:

```
v2 List Blacklist Monitors
```

API Call:

```
https://api.hetrixtools.com/v2/<API_TOKEN>/blacklist/monitors/<PAGE>/<PER_PAGE>/
```

Description:

* This API Call will list all of your Blacklist Monitors.
* Unlike its predecessor ‘v1 List Blacklist Monitors’ [deprecated], the ‘v2 List Blacklist Monitors’ API Call also includes the RBLs on which the monitors are blacklisted.

Understanding the API Call variables:

* **<API\_TOKEN>** – Your API Access Token.
* **<PAGE>** – the current page number you are viewing (default 0).
* **<PER\_PAGE>** – number of items to show per page (default 30, max 1024).
