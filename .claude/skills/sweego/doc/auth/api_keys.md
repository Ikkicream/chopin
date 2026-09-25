# API keys

Source : https://learn.sweego.io/docs/auth/api_keys

> In order to query on client api you will need api keys.

In order to query on client api you will need api keys.

These can be found in your Sweego portal:
Either from Home > Email > Continue to credentials,
Or from the drop-down menu on the upper right hand corner of the application > Credentials.

## Create key

To create your API key access, click on "Create API Key".

![domain](undefined)

## Assign to domain

Give your API Key a name and assign the domain(s) you will be using it with.
By default, your API Key will have access to all your domains. You can restrict access to one or several domains using the “Restrict to a domain” field.

![domain](undefined)

## Retrieve key

Make sure to save your API Key value as soon as you create it! For security reasons, we can’t show it to you again on the platform.

![domain](undefined)

## Api URL

`https://api.sweego.io`

## Use

Don't forget to add `Api-Key` in your authorization header before your key.

```shell
curl -L 'https://api.sweego.io/<METHOD>' \
-H 'Content-Type: application/json' \
-H 'Api-Key: <YOUR_API_KEY>' \
-d '{
  "data_1": "hello",
  "data_2": "bye"
}'
```

## Available routes

### with auth

All API routes support API-Key authentication.

Route list:

```
- client/*
- logs/*
- send/*
- stats/*
```

*Note: *`auth/*`* remaining routes do not supports API-Key auth because they are only needed for bearer token usage.*

*Note: *`client/user/*`* some special routes restricted by access token sent by mail.*
P
