# API Oauth2 (Bearer)

Source : https://learn.sweego.io/docs/auth/bearer_oauth2

> In order to query on API you will need to use Oauth2 Bearer: accesses are requested with `/auth/token` route

In order to query on API you will need to use Oauth2 Bearer: accesses are requested with `/auth/token` route

## Api URL

`https://api.sweego.io`

## Request token

```shell
curl -L 'https://api.sweego.io/auth/token' \
-H 'Content-Type: application/x-www-form-urlencoded' \
-H 'Accept: application/json' \
-d 'client_id=api_client' \
-d 'username=<USER>' \
-d 'password=<PASSWORD>' \
-d 'grant_type=password'
```

## Use token in query

```shell
curl -L 'https://api.sweego.io/<METHOD>' \
-H 'Content-Type: application/x-www-form-urlencoded' \
-H 'Accept: application/json' \
-H 'Authorization: bearer <YOU_BEARER_TOKEN>'
-d '{
  "data_1": "hello",
  "data_2": "bye"
}'
```

## Available routes

Routes linked to configuration and retrieving data supports Oauth2 Bearer authentication.

Route list:

```
- auth/*
- client_api_key/*
- client_credentials/*
- client_domain/*
- client_template_variable/*
- client_template/*
- client_user/*
- client/*
- logs/*
- stats/*
```
