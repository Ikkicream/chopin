# Send Email

Source : https://learn.sweego.io/docs/sdk/python/python-send-email

> Below is a complete example to send emal with sweego including api key authentication

# Send email with package

Below is a complete example to send emal with sweego including api key authentication

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os;
import sys;

from pprint import pprint;

from sweego.configuration import Configuration as ApiConfig;
from sweego.api.auth_api import AuthApi;
from sweego.api_client import ApiClient;
from sweego.rest import ApiException;
from sweego.api.send_api import SendApi;
from sweego.models.model_in_send_email import ModelInSendEmail as EmailModel;
from sweego.models.model_out_send import ModelOutSend;

from sweego_api import AuthApi;

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
    api_key: str = '<API_KEY>'

    try:
        # Assign key to api-key header
        api_client.default_headers [ 'Api-Key' ] = api_key;

        
        send_api: SendApi = SendApi (
            api_client = api_client
        );
        

        uuid_client = '<UUID_CLIENT>';

        email: EmailModel = EmailModel (
            campaign_id = "<CAMPAIGN_ID>",
            campaign_tags = [
                "<CAMPAIGN-TAG-1>",
                "<CAMPAIGN-TAG-2>"
            ],
            campaign_type = "transac", # ['market', 'newsletter', 'transac']
            var_from = {
                "email": "<EMAIL>",
                "name": "<NAME>"
            },
            message_txt = "<MESSAGE_txt>", #message_html is also available
            provider = "sweego",
            recipients = [
                {
                    "email": "<EMAIL>",
                    "name": "<NAME>"
                }
            ],
            subject = "<SUBJECT>",
            channel = "email"
        )
        
        res: ModelOutSend = send_api.send_send_post (
            model_in_send_email = email
        );
        
        pprint ( res );

    except ApiException as err:
        print (
            "Exception when querying : {err}".format (
                err = err
            ),
            file = sys.stderr
        );
```

#### Related

🔗 [More details about Email Sending](/docs/sending/how_to_send_email_by_api)

🔗 [API Reference](/docs/sweego/send-send-post)
