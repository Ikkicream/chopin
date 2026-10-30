# Using the API Relay

> Source : https://docs.hetrixtools.com/using-the-api-relay/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2018-06-14, modifié 2018-09-28

If you or your server are having issues accessing our API endpoint (api.hetrixtools.com), it could be due to CloudFlare blocking your IP address.

This can sometimes happen if your IP address has a poor or bad reputation.

In such cases, you can use our API via the relay, which allows you to access the API via a third party server, outside of CloudFlare’s scope.

Getting started is very simple, and it only takes replacing our API link with the relay link.

Replace:

```
https://api.hetrixtools.com/
```

With:

```
https://relay.hetrixtools.com/api/
```

So for instance, the ‘v1 API Status’ call link is:

```
https://api.hetrixtools.com/v1/<API_TOKEN>/status/
```

And using the relay, the above link would become:

```
https://relay.hetrixtools.com/api/v1/<API_TOKEN>/status/
```

And that’s all there is to using our API Relay.
