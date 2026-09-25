# How to

Source : https://learn.sweego.io/docs/sdk/python/python-how-to

> Authentication

## Authentication

Below are example on how to use authentication with provided sdk

### Bearer Token

#### Retrieve access token

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
from typing import List;
from pprint import pprint;

from sweego.configuration import Configuration as ApiConfig;
from sweego.api.auth_api import AuthApi;
from sweego.api_client import ApiClient;
from sweego.rest import ApiException;
from sweego import ResponseCreateTokenAuthTokenPost;

# Define api host
configuration = ApiConfig (
    host = "https://api.sweego.io"
);

# Enter a context with an instance of the API client
with ApiClient ( configuration ) as api_client:
    # Create an instance of the API class
    api_instance: AuthApi = AuthApi (
        api_client = api_client
    );

    # Define base auth requirements
    grant_type: str = 'password'
    username: str = '<USERNAME>'
    password: str = '<PASSWORD>'
    client_id: str = 'front_web'

    try:
        # Query auth token
        api_response: ResponseCreateTokenAuthTokenPost = api_instance.create_token_auth_token_post (
            grant_type = grant_type,
            username = username,
            password = password,
            client_id = client_id
        );
        
        print ( "Auth response:\n" );
        pprint (
            object = api_response.actual_instance,
            indent = 4
        );
        print ( "\n--------------------\n" );

        # Assign bearer token to authorization header
        api_client.default_headers [ 'Authorization' ] = "Bearer {bearer}".format (
            bearer = api_response.actual_instance.access_token
        );

    except ApiException as err:
        print (
            "Exception when querying : {err}".format (
                err = err
            ),
            file = sys.stderr
        );
```

#### Refresh token

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
from typing import List;
from pprint import pprint;

from sweego.configuration import Configuration as ApiConfig;
from sweego.api.auth_api import AuthApi;
from sweego.api_client import ApiClient;
from sweego.rest import ApiException;
from sweego import ResponseCreateTokenAuthTokenPost;

# Define api host
configuration = ApiConfig (
    host = "https://api.sweego.io"
);

# Enter a context with an instance of the API client
with ApiClient ( configuration ) as api_client:
    # Create an instance of the API class
    api_instance: AuthApi = AuthApi (
        api_client = api_client
    );

    # Define base auth requirements
    grant_type: str = 'refresh_token'
    refresh_token = '<REFRESH_TOKEN>'
    client_id: str = 'front_web'

    try:
        # Query auth token
        api_response: ResponseCreateTokenAuthTokenPost = api_instance.create_token_auth_token_post (
            grant_type = grant_type,
            refresh_token = refresh_token
            client_id = client_id
        );
        
        print ( "Auth response:\n" );
        pprint (
            object = api_response.actual_instance,
            indent = 4
        );
        print ( "\n--------------------\n" );

        # Assign bearer token to api client authorization header
        api_client.default_headers [ 'Authorization' ] = "Bearer {bearer}".format (
            bearer = api_response.actual_instance.access_token
        );

    except ApiException as err:
        print (
            "Exception when querying : {err}".format (
                err = err
            ),
            file = sys.stderr
        );
```

### API Key

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os;
import sys;

from typing import List;
from pprint import pprint;

from sweego.configuration import Configuration as ApiConfig;
from sweego.api.auth_api import AuthApi;
from sweego.api_client import ApiClient;
from sweego.rest import ApiException;
from sweego.models.client_webhook import ClientWebhook as ClientWebhookModel;
from sweego.api.webhook_api import WebhookApi;

# Define api host
configuration = ApiConfig (
    host = "https://api.sweego.io"
);

# Enter a context with an instance of the API client
with ApiClient ( configuration ) as api_client:
    # Create an instance of the API class
    api_instance: AuthApi = AuthApi (
        api_client = api_client
    );

    # Define api key to use
    api_key: str = '<API_KEY>';

    try:
        # Assign key to api client header
        api_client.default_headers [ 'Api-Key' ] = api_key;

        # Every api is in nana object -> check lib
    except ApiException as err:
        print (
            "Exception when querying : {err}".format (
                err = err
            ),
            file = sys.stderr
        );
```

## Endpoints principles

Every endpoint on the base API will be translated as a unique api object.
To be able to use  these api objec you will need to initiate them using the api_client defined above ([create api client](/docs/sdk/python/python-how-to#authentication))

For example, if you want to use ["/webhooks" endpoint](/docs/sweego/get-webhooks-clients-uuid-client-webhooks-get) :

```python
# Following an auth
from sweego.models.client_webhook import ClientWebhook as ClientWebhookModel;
from sweego.api.webhook_api import WebhookApi;

try:
    # Create a Webhook API instance
    webhook_api: WebhookApi = WebhookApi (
        api_client = api_client
    );

    # Query client wehooks list
    client_webhooks: List [ ClientWebhookModel ] = webhook_api.get_webhooks_clients_uuid_client_webhooks_get (
        uuid_client = api_response.actual_instance.sweego_client_id
    );

    # Print Result
    for webhook in client_webhooks:
        pprint (
            object = webhook.dict(),
            indent = 4
        );

except ApiException as err:
    print (
        "Exception when querying : {err}".format (
            err = err
        ),
        file = sys.stderr
    );
```

Every API object is located in `sweego.api` namespace

## Error Handling

sweego.exceptions contains a set of specific exceptions class
