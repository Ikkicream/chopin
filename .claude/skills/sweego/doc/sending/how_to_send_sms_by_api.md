# How to Send an SMS by API

Source : https://learn.sweego.io/docs/sending/how_to_send_sms_by_api

> Sweego allows you to send SMS via API using the /send endpoint. Unlike email, there is no separate bulk endpoint for SMS: the /send endpoint natively supports multiple recipients in a single call.

Sweego allows you to send SMS via API using the `/send` endpoint. Unlike email, there is no separate bulk endpoint for SMS: the `/send` endpoint natively supports multiple recipients in a single call.

## Prerequisites for sending your first SMS

Before sending, you have to create an API Access and optionally configure a SenderID.

### Create an API Access

You can follow our guide to [create an API Key](https://learn.sweego.io/docs/auth/api_keys)

### TLS

All API calls must be made over HTTPS (TLS). Requests over plain HTTP will be rejected.

### About SenderID

**SenderID is optional** when you have only one configured. If no SenderID is specified, a short number will be automatically assigned based on your campaign type (transactional or marketing).

**Best practice:** Even if you have only one SenderID configured, we **strongly recommend always specifying it** in your API calls. This ensures your integration won't require code changes if you add more SenderIDs later.

You can configure one or more custom SenderIDs in your [Sweego account settings](https://app.sweego.io).

---

## The `/send` endpoint for SMS

The `/send` endpoint is the single method for sending SMS with Sweego. It handles everything from a simple one-recipient message to a multi-recipient campaign with personalization.

### Key characteristics

**Multiple recipients in one call:**

- You can pass multiple recipients in the `recipients` array

- Each recipient receives an independent SMS — they do not see each other

- Variables are shared across all recipients (root-level), so they receive the same personalized content

**Template or inline message:**

- You can either pass the message directly via `message-txt`, or reference a saved template via `template-id`

- Only one of these two fields must be set

**BAT mode:**

- The `bat` (Bon À Tirer) flag sends the SMS as a test: it **does** count against your quota, but bypasses certain marketing restrictions (e.g. it allows sending on Sundays)

- Intended for integration testing and QA only — must not be used to circumvent sending rules in production

### Body parameters

| Field | Description | Format | Obligation |
| --- | --- | --- | --- |
| bat | BAT mode — SMS is sent as a test, counts against quota but bypasses certain marketing restrictions (e.g. Sunday sending) | bool | Optional — default: `false` |
| campaign-id | Custom campaign identifier for your own tracking | string | Optional |
| campaign-type | Type of campaign | string — `transac` or `market` | **Mandatory** |
| channel | Channel to use | string — must be `sms` | **Mandatory** — default: `sms` |
| message-txt | Message content in plain text | string | Optional — required if `template-id` is not set |
| provider | Provider to use | string | **Mandatory** |
| recipients | One or more recipient objects | array of objects: `{ num: string, region: string }` | **Mandatory** |
| sender-id | SenderID to use for sending | string | Strongly recommended. Mandatory if you have multiple SenderIDs configured |
| shorten-urls | Shorten URLs present in the message | bool | Optional — default: `true` |
| shorten-with-protocol | Include protocol (`https://`) in shortened URLs | bool | Optional — default: `true` |
| template-id | ID of a saved template | string | Optional — required if `message-txt` is not set |
| variables | Key-value pairs to replace placeholders in the template or message | object | Optional |

---

## Example 1: Send a simple SMS

### Prerequisites

- [Create an API key](https://learn.sweego.io/docs/auth/api_keys)

### Sending SMS

`{"key": "[object Object]"}`

**[cURL]**

```shell
curl --location 'https://api.sweego.io/send' \
--header 'Content-Type: application/json' \
--header 'Api-Key: <API_KEY>' \
--data-raw '{
    "channel": "sms",
    "provider": "sweego",
    "campaign-type": "transac",
    "sender-id": "<SENDER_ID>",
    "recipients": [
        { "num": "<PHONE_NUMBER>", "region": "FR" }
    ],
    "message-txt": "Hello, this is a test message from Sweego."
}'
```

**[Python]**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests

payload = {
    "channel": "sms",
    "provider": "sweego",
    "campaign-type": "transac",
    "sender-id": "<SENDER_ID>",
    "recipients": [
        {"num": "<PHONE_NUMBER>", "region": "FR"}
    ],
    "message-txt": "Hello, this is a test message from Sweego.",
}

URL = "https://api.sweego.io/send"
headers = {
    "Api-Key": "<API_KEY>",
    "Content-Type": "application/json",
}

TIMEOUT = 10
response = requests.post(URL, json=payload, headers=headers, timeout=TIMEOUT)

if response.status_code == 200:
    print("The request was successful. JSON Response:")
    print(response.json())
else:
    print(f"The request failed with status code {response.status_code}. JSON Response:")
    print(response.json())
```

**[Go]**

```go
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

func main() {
	payload := map[string]interface{}{
		"channel":       "sms",
		"provider":      "sweego",
		"campaign-type": "transac",
		"sender-id":     "<SENDER_ID>",
		"recipients": []map[string]string{
			{"num": "<PHONE_NUMBER>", "region": "FR"},
		},
		"message-txt": "Hello, this is a test message from Sweego.",
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}

	req, _ := http.NewRequest("POST", "https://api.sweego.io/send", bytes.NewBuffer(jsonData))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Api-Key", "<API_KEY>")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("Status Code: %d\nResponse: %s\n", resp.StatusCode, string(body))
}
```

**[Node.js]**

```javascript
const fetch = require('node-fetch');

const payload = {
    channel: "sms",
    provider: "sweego",
    "campaign-type": "transac",
    "sender-id": "<SENDER_ID>",
    recipients: [{ num: "<PHONE_NUMBER>", region: "FR" }],
    "message-txt": "Hello, this is a test message from Sweego."
};

fetch('https://api.sweego.io/send', {
    method: 'POST',
    headers: {
        'Api-Key': '<API_KEY>',
        'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
})
    .then(res => res.json())
    .then(data => console.log(data))
    .catch(err => console.error(err));
```

**[PHP]**

```php
<?php

$payload = [
    'channel'       => 'sms',
    'provider'      => 'sweego',
    'campaign-type' => 'transac',
    'sender-id'     => '<SENDER_ID>',
    'recipients'    => [
        ['num' => '<PHONE_NUMBER>', 'region' => 'FR']
    ],
    'message-txt'   => 'Hello, this is a test message from Sweego.'
];

$ch = curl_init('https://api.sweego.io/send');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Api-Key: <API_KEY>',
    'Content-Type: application/json'
]);

$response = curl_exec($ch);
$statusCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

echo "Status: $statusCode\n";
echo "Response: $response\n";
?>
```

**[Ruby]**

```ruby
require 'net/http'
require 'json'
require 'uri'

payload = {
  channel: 'sms',
  provider: 'sweego',
  'campaign-type': 'transac',
  'sender-id': '<SENDER_ID>',
  recipients: [
    { num: '<PHONE_NUMBER>', region: 'FR' }
  ],
  'message-txt': 'Hello, this is a test message from Sweego.'
}

uri = URI('https://api.sweego.io/send')
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = true

request = Net::HTTP::Post.new(uri.path, {
  'Api-Key'      => '<API_KEY>',
  'Content-Type' => 'application/json'
})
request.body = payload.to_json

response = http.request(request)
puts "Status: #{response.code}"
puts "Response: #{response.body}"
```

**[C#]**

```csharp
using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

class Program
{
    static async Task Main()
    {
        var payload = new
        {
            channel = "sms",
            provider = "sweego",
            campaignType = "transac",
            senderId = "<SENDER_ID>",
            recipients = new[]
            {
                new { num = "<PHONE_NUMBER>", region = "FR" }
            },
            messageTxt = "Hello, this is a test message from Sweego."
        };

        using var client = new HttpClient();
        client.DefaultRequestHeaders.Add("Api-Key", "<API_KEY>");

        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");

        var response = await client.PostAsync("https://api.sweego.io/send", content);
        var responseBody = await response.Content.ReadAsStringAsync();

        Console.WriteLine($"Status: {response.StatusCode}");
        Console.WriteLine($"Response: {responseBody}");
    }
}
```

**[Java]**

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class SendSms {
    public static void main(String[] args) throws Exception {
        String json = """
        {
            "channel": "sms",
            "provider": "sweego",
            "campaign-type": "transac",
            "sender-id": "<SENDER_ID>",
            "recipients": [
                { "num": "<PHONE_NUMBER>", "region": "FR" }
            ],
            "message-txt": "Hello, this is a test message from Sweego."
        }
        """;

        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.sweego.io/send"))
            .header("Api-Key", "<API_KEY>")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(json))
            .build();

        HttpResponse<String> response = client.send(request,
            HttpResponse.BodyHandlers.ofString());

        System.out.println("Status: " + response.statusCode());
        System.out.println("Response: " + response.body());
    }
}
```

The `sender-id` parameter is optional if you have only one SenderID configured. However, we strongly recommend always including it to future-proof your integration.

---

## Example 2: Send an SMS with a template and variables

### Prerequisites

- [Create an API key](https://learn.sweego.io/docs/auth/api_keys)

- [Create a template in the app](https://learn.sweego.io/docs/templates/create)

Your `<TEMPLATE_ID>` can be retrieved at [https://app.sweego.io/templates](https://app.sweego.io/templates).

In this example, the template contains a `{{ name }}` variable.

### Sending SMS

`{"key": "[object Object]"}`

**[cURL]**

```shell
curl --location 'https://api.sweego.io/send' \
--header 'Content-Type: application/json' \
--header 'Api-Key: <API_KEY>' \
--data-raw '{
    "channel": "sms",
    "provider": "sweego",
    "campaign-type": "transac",
    "sender-id": "<SENDER_ID>",
    "recipients": [
        { "num": "<PHONE_NUMBER>", "region": "FR" }
    ],
    "template-id": "<TEMPLATE_ID>",
    "variables": {
        "name": "Alice"
    }
}'
```

**[Python]**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests

payload = {
    "channel": "sms",
    "provider": "sweego",
    "campaign-type": "transac",
    "sender-id": "<SENDER_ID>",
    "recipients": [
        {"num": "<PHONE_NUMBER>", "region": "FR"}
    ],
    "template-id": "<TEMPLATE_ID>",
    "variables": {
        "name": "Alice"
    },
}

URL = "https://api.sweego.io/send"
headers = {
    "Api-Key": "<API_KEY>",
    "Content-Type": "application/json",
}

TIMEOUT = 10
response = requests.post(URL, json=payload, headers=headers, timeout=TIMEOUT)

if response.status_code == 200:
    print("The request was successful. JSON Response:")
    print(response.json())
else:
    print(f"The request failed with status code {response.status_code}. JSON Response:")
    print(response.json())
```

**[Go]**

```go
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

func main() {
	payload := map[string]interface{}{
		"channel":       "sms",
		"provider":      "sweego",
		"campaign-type": "transac",
		"sender-id":     "<SENDER_ID>",
		"recipients": []map[string]string{
			{"num": "<PHONE_NUMBER>", "region": "FR"},
		},
		"template-id": "<TEMPLATE_ID>",
		"variables": map[string]string{
			"name": "Alice",
		},
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}

	req, _ := http.NewRequest("POST", "https://api.sweego.io/send", bytes.NewBuffer(jsonData))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Api-Key", "<API_KEY>")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("Status Code: %d\nResponse: %s\n", resp.StatusCode, string(body))
}
```

**[Node.js]**

```javascript
const fetch = require('node-fetch');

const payload = {
    channel: "sms",
    provider: "sweego",
    "campaign-type": "transac",
    "sender-id": "<SENDER_ID>",
    recipients: [{ num: "<PHONE_NUMBER>", region: "FR" }],
    "template-id": "<TEMPLATE_ID>",
    variables: { name: "Alice" }
};

fetch('https://api.sweego.io/send', {
    method: 'POST',
    headers: {
        'Api-Key': '<API_KEY>',
        'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
})
    .then(res => res.json())
    .then(data => console.log(data))
    .catch(err => console.error(err));
```

**[PHP]**

```php
<?php

$payload = [
    'channel'       => 'sms',
    'provider'      => 'sweego',
    'campaign-type' => 'transac',
    'sender-id'     => '<SENDER_ID>',
    'recipients'    => [
        ['num' => '<PHONE_NUMBER>', 'region' => 'FR']
    ],
    'template-id'   => '<TEMPLATE_ID>',
    'variables'     => [
        'name' => 'Alice'
    ]
];

$ch = curl_init('https://api.sweego.io/send');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Api-Key: <API_KEY>',
    'Content-Type: application/json'
]);

$response = curl_exec($ch);
$statusCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

echo "Status: $statusCode\n";
echo "Response: $response\n";
?>
```

**[Ruby]**

```ruby
require 'net/http'
require 'json'
require 'uri'

payload = {
  channel: 'sms',
  provider: 'sweego',
  'campaign-type': 'transac',
  'sender-id': '<SENDER_ID>',
  recipients: [
    { num: '<PHONE_NUMBER>', region: 'FR' }
  ],
  'template-id': '<TEMPLATE_ID>',
  variables: {
    name: 'Alice'
  }
}

uri = URI('https://api.sweego.io/send')
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = true

request = Net::HTTP::Post.new(uri.path, {
  'Api-Key'      => '<API_KEY>',
  'Content-Type' => 'application/json'
})
request.body = payload.to_json

response = http.request(request)
puts "Status: #{response.code}"
puts "Response: #{response.body}"
```

**[C#]**

```csharp
using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Collections.Generic;
using System.Threading.Tasks;

class Program
{
    static async Task Main()
    {
        var payload = new
        {
            channel = "sms",
            provider = "sweego",
            campaignType = "transac",
            senderId = "<SENDER_ID>",
            recipients = new[]
            {
                new { num = "<PHONE_NUMBER>", region = "FR" }
            },
            templateId = "<TEMPLATE_ID>",
            variables = new Dictionary<string, string>
            {
                { "name", "Alice" }
            }
        };

        using var client = new HttpClient();
        client.DefaultRequestHeaders.Add("Api-Key", "<API_KEY>");

        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");

        var response = await client.PostAsync("https://api.sweego.io/send", content);
        var responseBody = await response.Content.ReadAsStringAsync();

        Console.WriteLine($"Status: {response.StatusCode}");
        Console.WriteLine($"Response: {responseBody}");
    }
}
```

**[Java]**

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class SendSmsTemplate {
    public static void main(String[] args) throws Exception {
        String json = """
        {
            "channel": "sms",
            "provider": "sweego",
            "campaign-type": "transac",
            "sender-id": "<SENDER_ID>",
            "recipients": [
                { "num": "<PHONE_NUMBER>", "region": "FR" }
            ],
            "template-id": "<TEMPLATE_ID>",
            "variables": {
                "name": "Alice"
            }
        }
        """;

        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.sweego.io/send"))
            .header("Api-Key", "<API_KEY>")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(json))
            .build();

        HttpResponse<String> response = client.send(request,
            HttpResponse.BodyHandlers.ofString());

        System.out.println("Status: " + response.statusCode());
        System.out.println("Response: " + response.body());
    }
}
```

When using `variables` with multiple recipients, all recipients receive the same variable values. If you need each recipient to receive different personalized content, you must make one API call per recipient.

---

## Example 3: Send an SMS to multiple recipients

The `/send` endpoint accepts multiple recipients in a single call. Each recipient receives an independent SMS.

`{"key": "[object Object]"}`

**[cURL]**

```shell
curl --location 'https://api.sweego.io/send' \
--header 'Content-Type: application/json' \
--header 'Api-Key: <API_KEY>' \
--data-raw '{
    "channel": "sms",
    "provider": "sweego",
    "campaign-type": "market",
    "sender-id": "<SENDER_ID>",
    "recipients": [
        { "num": "<PHONE_NUMBER_1>", "region": "FR" },
        { "num": "<PHONE_NUMBER_2>", "region": "FR" },
        { "num": "<PHONE_NUMBER_3>", "region": "BE" }
    ],
    "message-txt": "Our summer sale starts today. Visit sweego.io to discover our offers."
}'
```

**[Python]**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests

payload = {
    "channel": "sms",
    "provider": "sweego",
    "campaign-type": "market",
    "sender-id": "<SENDER_ID>",
    "recipients": [
        {"num": "<PHONE_NUMBER_1>", "region": "FR"},
        {"num": "<PHONE_NUMBER_2>", "region": "FR"},
        {"num": "<PHONE_NUMBER_3>", "region": "BE"},
    ],
    "message-txt": "Our summer sale starts today. Visit sweego.io to discover our offers.",
}

URL = "https://api.sweego.io/send"
headers = {
    "Api-Key": "<API_KEY>",
    "Content-Type": "application/json",
}

TIMEOUT = 10
response = requests.post(URL, json=payload, headers=headers, timeout=TIMEOUT)

if response.status_code == 200:
    print("The request was successful. JSON Response:")
    print(response.json())
else:
    print(f"The request failed with status code {response.status_code}. JSON Response:")
    print(response.json())
```

**[Go]**

```go
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

func main() {
	payload := map[string]interface{}{
		"channel":       "sms",
		"provider":      "sweego",
		"campaign-type": "market",
		"sender-id":     "<SENDER_ID>",
		"recipients": []map[string]string{
			{"num": "<PHONE_NUMBER_1>", "region": "FR"},
			{"num": "<PHONE_NUMBER_2>", "region": "FR"},
			{"num": "<PHONE_NUMBER_3>", "region": "BE"},
		},
		"message-txt": "Our summer sale starts today. Visit sweego.io to discover our offers.",
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}

	req, _ := http.NewRequest("POST", "https://api.sweego.io/send", bytes.NewBuffer(jsonData))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Api-Key", "<API_KEY>")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("Status Code: %d\nResponse: %s\n", resp.StatusCode, string(body))
}
```

**[Node.js]**

```javascript
const fetch = require('node-fetch');

const payload = {
    channel: "sms",
    provider: "sweego",
    "campaign-type": "market",
    "sender-id": "<SENDER_ID>",
    recipients: [
        { num: "<PHONE_NUMBER_1>", region: "FR" },
        { num: "<PHONE_NUMBER_2>", region: "FR" },
        { num: "<PHONE_NUMBER_3>", region: "BE" }
    ],
    "message-txt": "Our summer sale starts today. Visit sweego.io to discover our offers."
};

fetch('https://api.sweego.io/send', {
    method: 'POST',
    headers: {
        'Api-Key': '<API_KEY>',
        'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
})
    .then(res => res.json())
    .then(data => console.log(data))
    .catch(err => console.error(err));
```

**[PHP]**

```php
<?php

$payload = [
    'channel'       => 'sms',
    'provider'      => 'sweego',
    'campaign-type' => 'market',
    'sender-id'     => '<SENDER_ID>',
    'recipients'    => [
        ['num' => '<PHONE_NUMBER_1>', 'region' => 'FR'],
        ['num' => '<PHONE_NUMBER_2>', 'region' => 'FR'],
        ['num' => '<PHONE_NUMBER_3>', 'region' => 'BE'],
    ],
    'message-txt'   => 'Our summer sale starts today. Visit sweego.io to discover our offers.'
];

$ch = curl_init('https://api.sweego.io/send');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Api-Key: <API_KEY>',
    'Content-Type: application/json'
]);

$response = curl_exec($ch);
$statusCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

echo "Status: $statusCode\n";
echo "Response: $response\n";
?>
```

**[Ruby]**

```ruby
require 'net/http'
require 'json'
require 'uri'

payload = {
  channel: 'sms',
  provider: 'sweego',
  'campaign-type': 'market',
  'sender-id': '<SENDER_ID>',
  recipients: [
    { num: '<PHONE_NUMBER_1>', region: 'FR' },
    { num: '<PHONE_NUMBER_2>', region: 'FR' },
    { num: '<PHONE_NUMBER_3>', region: 'BE' }
  ],
  'message-txt': 'Our summer sale starts today. Visit sweego.io to discover our offers.'
}

uri = URI('https://api.sweego.io/send')
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = true

request = Net::HTTP::Post.new(uri.path, {
  'Api-Key'      => '<API_KEY>',
  'Content-Type' => 'application/json'
})
request.body = payload.to_json

response = http.request(request)
puts "Status: #{response.code}"
puts "Response: #{response.body}"
```

**[C#]**

```csharp
using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

class Program
{
    static async Task Main()
    {
        var payload = new
        {
            channel = "sms",
            provider = "sweego",
            campaignType = "market",
            senderId = "<SENDER_ID>",
            recipients = new[]
            {
                new { num = "<PHONE_NUMBER_1>", region = "FR" },
                new { num = "<PHONE_NUMBER_2>", region = "FR" },
                new { num = "<PHONE_NUMBER_3>", region = "BE" }
            },
            messageTxt = "Our summer sale starts today. Visit sweego.io to discover our offers."
        };

        using var client = new HttpClient();
        client.DefaultRequestHeaders.Add("Api-Key", "<API_KEY>");

        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");

        var response = await client.PostAsync("https://api.sweego.io/send", content);
        var responseBody = await response.Content.ReadAsStringAsync();

        Console.WriteLine($"Status: {response.StatusCode}");
        Console.WriteLine($"Response: {responseBody}");
    }
}
```

**[Java]**

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class SendSmsMultiple {
    public static void main(String[] args) throws Exception {
        String json = """
        {
            "channel": "sms",
            "provider": "sweego",
            "campaign-type": "market",
            "sender-id": "<SENDER_ID>",
            "recipients": [
                { "num": "<PHONE_NUMBER_1>", "region": "FR" },
                { "num": "<PHONE_NUMBER_2>", "region": "FR" },
                { "num": "<PHONE_NUMBER_3>", "region": "BE" }
            ],
            "message-txt": "Our summer sale starts today. Visit sweego.io to discover our offers."
        }
        """;

        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.sweego.io/send"))
            .header("Api-Key", "<API_KEY>")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(json))
            .build();

        HttpResponse<String> response = client.send(request,
            HttpResponse.BodyHandlers.ofString());

        System.out.println("Status: " + response.statusCode());
        System.out.println("Response: " + response.body());
    }
}
```

---

## Sending SMS to the US and Canada

Sending SMS to the United States and Canada requires a **Toll Free Number (TFN)**.

### Prerequisites

- **Contact support** to request a Toll Free Number

- **Complete the verification form** required by US/Canadian authorities

- **Wait for approval** before starting to send to these destinations

### How it works

- Each TFN is unique per customer

- The TFN acts as a SenderID in your API calls

- You must specify your TFN in the `sender-id` parameter when sending to US/CA destinations

### Example

`{"key": "[object Object]"}`

**[cURL]**

```shell
curl --location 'https://api.sweego.io/send' \
--header 'Content-Type: application/json' \
--header 'Api-Key: <API_KEY>' \
--data-raw '{
    "channel": "sms",
    "provider": "sweego",
    "campaign-type": "transac",
    "sender-id": "<YOUR_TFN>",
    "recipients": [
        { "num": "+1234567890", "region": "US" }
    ],
    "message-txt": "Hello, this is a test message from Sweego."
}'
```

**[Python]**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests

payload = {
    "channel": "sms",
    "provider": "sweego",
    "campaign-type": "transac",
    "sender-id": "<YOUR_TFN>",
    "recipients": [
        {"num": "+1234567890", "region": "US"}
    ],
    "message-txt": "Hello, this is a test message from Sweego.",
}

URL = "https://api.sweego.io/send"
headers = {
    "Api-Key": "<API_KEY>",
    "Content-Type": "application/json",
}

TIMEOUT = 10
response = requests.post(URL, json=payload, headers=headers, timeout=TIMEOUT)

if response.status_code == 200:
    print("The request was successful. JSON Response:")
    print(response.json())
else:
    print(f"The request failed with status code {response.status_code}. JSON Response:")
    print(response.json())
```

**[Go]**

```go
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

func main() {
	payload := map[string]interface{}{
		"channel":       "sms",
		"provider":      "sweego",
		"campaign-type": "transac",
		"sender-id":     "<YOUR_TFN>",
		"recipients": []map[string]string{
			{"num": "+1234567890", "region": "US"},
		},
		"message-txt": "Hello, this is a test message from Sweego.",
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}

	req, _ := http.NewRequest("POST", "https://api.sweego.io/send", bytes.NewBuffer(jsonData))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Api-Key", "<API_KEY>")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("Status Code: %d\nResponse: %s\n", resp.StatusCode, string(body))
}
```

**[Node.js]**

```javascript
const fetch = require('node-fetch');

const payload = {
    channel: "sms",
    provider: "sweego",
    "campaign-type": "transac",
    "sender-id": "<YOUR_TFN>",
    recipients: [{ num: "+1234567890", region: "US" }],
    "message-txt": "Hello, this is a test message from Sweego."
};

fetch('https://api.sweego.io/send', {
    method: 'POST',
    headers: {
        'Api-Key': '<API_KEY>',
        'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
})
    .then(res => res.json())
    .then(data => console.log(data))
    .catch(err => console.error(err));
```

**[PHP]**

```php
<?php

$payload = [
    'channel'       => 'sms',
    'provider'      => 'sweego',
    'campaign-type' => 'transac',
    'sender-id'     => '<YOUR_TFN>',
    'recipients'    => [
        ['num' => '+1234567890', 'region' => 'US']
    ],
    'message-txt'   => 'Hello, this is a test message from Sweego.'
];

$ch = curl_init('https://api.sweego.io/send');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Api-Key: <API_KEY>',
    'Content-Type: application/json'
]);

$response = curl_exec($ch);
$statusCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

echo "Status: $statusCode\n";
echo "Response: $response\n";
?>
```

**[Ruby]**

```ruby
require 'net/http'
require 'json'
require 'uri'

payload = {
  channel: 'sms',
  provider: 'sweego',
  'campaign-type': 'transac',
  'sender-id': '<YOUR_TFN>',
  recipients: [
    { num: '+1234567890', region: 'US' }
  ],
  'message-txt': 'Hello, this is a test message from Sweego.'
}

uri = URI('https://api.sweego.io/send')
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = true

request = Net::HTTP::Post.new(uri.path, {
  'Api-Key'      => '<API_KEY>',
  'Content-Type' => 'application/json'
})
request.body = payload.to_json

response = http.request(request)
puts "Status: #{response.code}"
puts "Response: #{response.body}"
```

**[C#]**

```csharp
using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

class Program
{
    static async Task Main()
    {
        var payload = new
        {
            channel = "sms",
            provider = "sweego",
            campaignType = "transac",
            senderId = "<YOUR_TFN>",
            recipients = new[]
            {
                new { num = "+1234567890", region = "US" }
            },
            messageTxt = "Hello, this is a test message from Sweego."
        };

        using var client = new HttpClient();
        client.DefaultRequestHeaders.Add("Api-Key", "<API_KEY>");

        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");

        var response = await client.PostAsync("https://api.sweego.io/send", content);
        var responseBody = await response.Content.ReadAsStringAsync();

        Console.WriteLine($"Status: {response.StatusCode}");
        Console.WriteLine($"Response: {responseBody}");
    }
}
```

**[Java]**

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class SendSmsUs {
    public static void main(String[] args) throws Exception {
        String json = """
        {
            "channel": "sms",
            "provider": "sweego",
            "campaign-type": "transac",
            "sender-id": "<YOUR_TFN>",
            "recipients": [
                { "num": "+1234567890", "region": "US" }
            ],
            "message-txt": "Hello, this is a test message from Sweego."
        }
        """;

        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.sweego.io/send"))
            .header("Api-Key", "<API_KEY>")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(json))
            .build();

        HttpResponse<String> response = client.send(request,
            HttpResponse.BodyHandlers.ofString());

        System.out.println("Status: " + response.statusCode());
        System.out.println("Response: " + response.body());
    }
}
```

For comprehensive information about sending SMS to the US and Canada, including TFN registration and compliance requirements, refer to our [dedicated US/Canada SMS guide](/docs/sms/us_canada_and_nanp_countries).

---

## API Response

All successful calls to `/send` return the following JSON structure:

```json
{
  "credit_left": "string",
  "channel": "string",
  "provider": "string",
  "swg_uids": {},
  "transaction_id": "string"
}
```

| Field | Description |
| --- | --- |
| credit_left | Remaining SMS credit on your account after this send |
| channel | Channel used for the send (always `sms` here) |
| provider | Provider used for the send |
| swg_uids | Map of recipient numbers to their unique Sweego message IDs, used for tracking and webhook correlation |
| transaction_id | Unique identifier for this API call |

---

For the complete API specification:

- [/send endpoint documentation](https://learn.sweego.io/docs/sweego/send-send-post)
