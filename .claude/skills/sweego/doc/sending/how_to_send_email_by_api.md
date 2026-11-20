# How to Send an Email by API

Source : https://learn.sweego.io/docs/sending/how_to_send_email_by_api

> Sweego offers two methods to send emails via API: /send for individual emails and /send/bulk/email for bulk sending with personalization.

Sweego offers two methods to send emails via API: `/send` for individual emails and `/send/bulk/email` for bulk sending with personalization.

## Prerequisites for sending your first email

Before sending you have to configure your sub-domain and create API access.

### Configure and verify a Subdomain

A best practice in deliverability for sending email is to use a subdomain rather than the domain name directly.

Utilizing a subdomain separates the sender reputation of your core domain from email marketing activities especially but it could be useful to protect you from being sent by mistake, for example.

With that you can easily separate your sending by using dedicated subdomain for marketing or transactional parts.

You can follow our guide to setup your domain in Sweego.

```
You have to verify the good configuration of your subdomain before sending. A subdomain not verified can't send email.
```

The verification has two functions:

- Sub-domain verification allows us to ensure that the user has sufficient rights with the domain name owner to add records.

- The records created are used for authentication (SPF & DKIM) and bounce management.

You can read our article if you want to know more about email authentication.

### Create an API Access

You can follow our guide to [create an API Key](https://learn.sweego.io/docs/auth/api_keys)

---

## Which method should I use?

### Use `/send` when you need to:

- Send a single email to one recipient

- Send one email with CC/BCC recipients

- Send the same message to multiple recipients who should see each other (like a group email)

- Use variables with a single recipient only

### Use `/send/bulk/email` when you need to:

- Send personalized emails to multiple recipients (minimum 2 recipients)

- Each recipient receives their own email with unique variables

- Recipients don't see each other's addresses

- High-volume sending with individualization

---

## Method 1: `/send` - Individual and Group Emails

The `/send` endpoint is designed for individual emails or group emails where recipients can see each other.

### Key characteristics

**Recipients visibility:**

- When sending to multiple recipients in the `recipients` field, all addresses are visible in the "To:" field

- Each recipient sees the other recipients' email addresses (standard email behavior)

**CC and BCC support:**

- CC and BCC recipients are supported

- Each CC/BCC email is sent individually with a unique `swg_uid` for proper tracking

- This differs from SMTP where only the "To" recipient can be tracked

**Variable personalization:**

- Variables are only supported with **a single recipient** in the "To" field

- If you use variables with one recipient and CC/BCC, the CC/BCC recipients will see the personalized content intended for the "To" recipient

- **Multi-recipient + variables**: Not supported. If you need personalized content for each recipient, use `/send/bulk/email` instead

- **Recipients see each other**: All "To" recipients see each other's addresses. For privacy, use `/send/bulk/email`

### Body parameters

| Field | Description | Format | Obligation |
| --- | --- | --- | --- |
| attachments | Attachment (file) to include in the email | array of dict (filename: string, content: base64 string) | Optional |
| campaign-id | Campaign ID | string | Optional |
| campaign-tags | Tags to set in mail header (ex : x-campaign-tags:"a-tag") (limited to 5) | list of strings (regex: ^[A-Za-z0-9-]20$) | Optional |
| campaign-type | Type of Email with limited choice (e.g., "x-campaign-type: ... ") | string | Optional (transac / newsletter / market) |
| channel | The channel that you want to use | string | Mandatory |
| dry-run | Active Dry-Run mode, no email will really be sent | bool | Optional |
| from | The name and email or number of the From | mixed | Mandatory (dictionary: email, name) |
| headers | List of custom headers to include (limited to 5) | dict (name:str, value:str) | Optional |
| list-unsub | Set list-unsubscribe header, with one-click management. Default method value: mailto | dict (method:str, value:str) | Optional |
| message-html | Message in HTML format | string | Optional |
| message-txt | Message in txt format | string | Optional |
| provider | The provider that you want to use | string | Mandatory |
| recipients | One or more recipient address | mixed | Mandatory (list of dict with email:str, name:str optional) |
| reply-to | The name and email to uses when someone reply to your email | dict (email: str, name: optional str) | Optional |
| subject | Email subject | string | Mandatory |
| template-id | Id of the template | string | Optional  (if used, need to exist) |
| variables | Variables used to replace the placeholders in the template. Only works with a single recipient. | object with key-value pairs | Optional (single recipient only) |

### Example 1: Send a simple email

#### Prerequisites

- [Create and verify your domain or subdomain](#configure-and-verify-a-subdomain)

- [Create an API key](#create-an-api-access)

#### Sending email

`{"key": "[object Object]"}`

**[Curl]**

```shell
curl --location 'https://api.sweego.io/send' \
--header 'Content-Type: application/json' \
--header 'Api-Key: <API_KEY>' \
--data-raw '{
    "channel": "email",
    "provider": "sweego",
    "recipients": [
        { "email": "<EMAIL_TO>" }
    ],
    "from": {
        "name": "MY NAME",
        "email": "<EMAIL_FROM>"
    },
    "subject": "Email subject",
    "message-txt": "Email body"
}'
```

**[Python]**

```py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests

payload = {
    "channel": "email",
    "provider": "sweego",
    "recipients": [{"email": "<EMAIL_TO>"}],
    "from": {"name": "<EMAIL_CONTACT_NAME>", "email": "<EMAIL_FROM>"},
    "subject": "Email subject",
    "message-txt": "Email body",
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
		"channel":  "email",
		"provider": "sweego",
		"recipients": []map[string]string{
			{"email": "<EMAIL_TO>"},
		},
		"from": map[string]string{
			"name":  "<EMAIL_CONTACT_NAME>",
			"email": "<EMAIL_FROM>",
		},
		"subject":     "Email subject",
		"message-txt": "Email body",
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
    channel: "email",
    provider: "sweego",
    recipients: [{ email: "<EMAIL_TO>" }],
    from: { name: "<EMAIL_CONTACT_NAME>", email: "<EMAIL_FROM>" },
    subject: "Email subject",
    "message-txt": "Email body"
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
.then(data => console.log('Success:', data))
.catch(err => console.error('Error:', err));
```

**[PHP]**

```php
<?php
$payload = [
    "channel" => "email",
    "provider" => "sweego",
    "recipients" => [
        ["email" => "<EMAIL_TO>"]
    ],
    "from" => [
        "name" => "<EMAIL_CONTACT_NAME>",
        "email" => "<EMAIL_FROM>"
    ],
    "subject" => "Email subject",
    "message-txt" => "Email body"
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
  channel: "email",
  provider: "sweego",
  recipients: [{ email: "<EMAIL_TO>" }],
  from: { name: "<EMAIL_CONTACT_NAME>", email: "<EMAIL_FROM>" },
  subject: "Email subject",
  "message-txt": "Email body"
}

uri = URI('https://api.sweego.io/send')
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = true

request = Net::HTTP::Post.new(uri.path, {
  'Api-Key' => '<API_KEY>',
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
            channel = "email",
            provider = "sweego",
            recipients = new[] { new { email = "<EMAIL_TO>" } },
            from = new { name = "<EMAIL_CONTACT_NAME>", email = "<EMAIL_FROM>" },
            subject = "Email subject",
            messageTxt = "Email body"
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
import org.json.JSONObject;
import org.json.JSONArray;

public class SendEmail {
    public static void main(String[] args) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("channel", "email");
        payload.put("provider", "sweego");
        
        JSONArray recipients = new JSONArray();
        recipients.put(new JSONObject().put("email", "<EMAIL_TO>"));
        payload.put("recipients", recipients);
        
        JSONObject from = new JSONObject();
        from.put("name", "<EMAIL_CONTACT_NAME>");
        from.put("email", "<EMAIL_FROM>");
        payload.put("from", from);
        
        payload.put("subject", "Email subject");
        payload.put("message-txt", "Email body");

        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.sweego.io/send"))
            .header("Api-Key", "<API_KEY>")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(payload.toString()))
            .build();

        HttpResponse<String> response = client.send(request, 
            HttpResponse.BodyHandlers.ofString());
        
        System.out.println("Status: " + response.statusCode());
        System.out.println("Response: " + response.body());
    }
}
```

### Example 2: Send to multiple recipients (group email)

When you specify multiple addresses in the recipients field, Sweego sends a single email with all recipients visible in the "To:" field. Each recipient can see the email addresses of the other recipients.

`{"key": "[object Object]"}`

**[Curl]**

```shell
curl --location 'https://api.sweego.io/send' \
--header 'Content-Type: application/json' \
--header 'Api-Key: <API_KEY>' \
--data-raw '{
  "channel": "email",
  "provider": "sweego",
  "recipients": [
    {"email": "<EMAIL1_TO>", "name": "Alice"},
    {"email": "<EMAIL2_TO>", "name": "Bob"}
  ],
  "from": {
    "name": "MY NAME",
    "email": "<EMAIL_FROM>"
  },
  "subject": "Email subject",
  "message-txt": "Email body"
}'
```

**[Python]**

```py
import requests

payload = {
    "channel": "email",
    "provider": "sweego",
    "recipients": [
        {"email": "<EMAIL1_TO>", "name": "Alice"},
        {"email": "<EMAIL2_TO>", "name": "Bob"}
    ],
    "from": {"name": "MY NAME", "email": "<EMAIL_FROM>"},
    "subject": "Email subject",
    "message-txt": "Email body",
}

URL = "https://api.sweego.io/send"
headers = {"Api-Key": "<API_KEY>", "Content-Type": "application/json"}

response = requests.post(URL, json=payload, headers=headers, timeout=10)
print(f"Status: {response.status_code}")
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
		"channel":  "email",
		"provider": "sweego",
		"recipients": []map[string]string{
			{"email": "<EMAIL1_TO>", "name": "Alice"},
			{"email": "<EMAIL2_TO>", "name": "Bob"},
		},
		"from": map[string]string{
			"name":  "MY NAME",
			"email": "<EMAIL_FROM>",
		},
		"subject":     "Email subject",
		"message-txt": "Email body",
	}

	jsonData, _ := json.Marshal(payload)
	req, _ := http.NewRequest("POST", "https://api.sweego.io/send", bytes.NewBuffer(jsonData))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Api-Key", "<API_KEY>")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, _ := client.Do(req)
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("Status: %d\nResponse: %s\n", resp.StatusCode, string(body))
}
```

**[Node.js]**

```javascript
const fetch = require('node-fetch');

const payload = {
    channel: "email",
    provider: "sweego",
    recipients: [
        { email: "<EMAIL1_TO>", name: "Alice" },
        { email: "<EMAIL2_TO>", name: "Bob" }
    ],
    from: { name: "MY NAME", email: "<EMAIL_FROM>" },
    subject: "Email subject",
    "message-txt": "Email body"
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
.then(data => console.log('Success:', data))
.catch(err => console.error('Error:', err));
```

**[PHP]**

```php
<?php
$payload = [
    "channel" => "email",
    "provider" => "sweego",
    "recipients" => [
        ["email" => "<EMAIL1_TO>", "name" => "Alice"],
        ["email" => "<EMAIL2_TO>", "name" => "Bob"]
    ],
    "from" => [
        "name" => "MY NAME",
        "email" => "<EMAIL_FROM>"
    ],
    "subject" => "Email subject",
    "message-txt" => "Email body"
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
curl_close($ch);
echo $response;
?>
```

**[Ruby]**

```ruby
require 'net/http'
require 'json'

payload = {
  channel: "email",
  provider: "sweego",
  recipients: [
    { email: "<EMAIL1_TO>", name: "Alice" },
    { email: "<EMAIL2_TO>", name: "Bob" }
  ],
  from: { name: "MY NAME", email: "<EMAIL_FROM>" },
  subject: "Email subject",
  "message-txt": "Email body"
}

uri = URI('https://api.sweego.io/send')
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = true
request = Net::HTTP::Post.new(uri.path)
request['Api-Key'] = '<API_KEY>'
request['Content-Type'] = 'application/json'
request.body = payload.to_json

response = http.request(request)
puts response.body
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
            channel = "email",
            provider = "sweego",
            recipients = new[]
            {
                new { email = "<EMAIL1_TO>", name = "Alice" },
                new { email = "<EMAIL2_TO>", name = "Bob" }
            },
            from = new { name = "MY NAME", email = "<EMAIL_FROM>" },
            subject = "Email subject",
            messageTxt = "Email body"
        };

        using var client = new HttpClient();
        client.DefaultRequestHeaders.Add("Api-Key", "<API_KEY>");
        
        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        
        var response = await client.PostAsync("https://api.sweego.io/send", content);
        Console.WriteLine(await response.Content.ReadAsStringAsync());
    }
}
```

**[Java]**

```java
import java.net.URI;
import java.net.http.*;
import org.json.*;

public class SendMultipleRecipients {
    public static void main(String[] args) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("channel", "email");
        payload.put("provider", "sweego");
        
        JSONArray recipients = new JSONArray();
        recipients.put(new JSONObject()
            .put("email", "<EMAIL1_TO>")
            .put("name", "Alice"));
        recipients.put(new JSONObject()
            .put("email", "<EMAIL2_TO>")
            .put("name", "Bob"));
        payload.put("recipients", recipients);
        
        payload.put("from", new JSONObject()
            .put("name", "MY NAME")
            .put("email", "<EMAIL_FROM>"));
        payload.put("subject", "Email subject");
        payload.put("message-txt", "Email body");

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.sweego.io/send"))
            .header("Api-Key", "<API_KEY>")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(payload.toString()))
            .build();

        HttpResponse<String> response = HttpClient.newHttpClient()
            .send(request, HttpResponse.BodyHandlers.ofString());
        System.out.println(response.body());
    }
}
```

In this example, Alice and Bob will receive the same email and will see each other's addresses.

If you want to send individualized emails where each recipient only sees their own address, or if you need per-recipient personalization, use the **`/send/bulk/email`** endpoint instead.

### Example 3: Send with CC/BCC

`{"key": "[object Object]"}`

**[Curl]**

```shell
curl --location 'https://api.sweego.io/send' \
--header 'Content-Type: application/json' \
--header 'Api-Key: <API_KEY>' \
--data-raw '{
  "channel": "email",
  "provider": "sweego",
  "recipients": [
    {"email": "<EMAIL_TO>", "name": "Main Recipient"}
  ],
  "cc": [
    {"email": "<EMAIL_CC>", "name": "CC Recipient"}
  ],
  "bcc": [
    {"email": "<EMAIL_BCC>", "name": "BCC Recipient"}
  ],
  "from": {
    "name": "MY NAME",
    "email": "<EMAIL_FROM>"
  },
  "subject": "Email subject",
  "message-txt": "Email body"
}'
```

**[Python]**

```py
import requests

payload = {
    "channel": "email",
    "provider": "sweego",
    "recipients": [{"email": "<EMAIL_TO>", "name": "Main Recipient"}],
    "cc": [{"email": "<EMAIL_CC>", "name": "CC Recipient"}],
    "bcc": [{"email": "<EMAIL_BCC>", "name": "BCC Recipient"}],
    "from": {"name": "MY NAME", "email": "<EMAIL_FROM>"},
    "subject": "Email subject",
    "message-txt": "Email body",
}

URL = "https://api.sweego.io/send"
headers = {"Api-Key": "<API_KEY>", "Content-Type": "application/json"}

response = requests.post(URL, json=payload, headers=headers, timeout=10)
print(f"Status: {response.status_code}")
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
		"channel":  "email",
		"provider": "sweego",
		"recipients": []map[string]string{
			{"email": "<EMAIL_TO>", "name": "Main Recipient"},
		},
		"cc": []map[string]string{
			{"email": "<EMAIL_CC>", "name": "CC Recipient"},
		},
		"bcc": []map[string]string{
			{"email": "<EMAIL_BCC>", "name": "BCC Recipient"},
		},
		"from": map[string]string{
			"name":  "MY NAME",
			"email": "<EMAIL_FROM>",
		},
		"subject":     "Email subject",
		"message-txt": "Email body",
	}

	jsonData, _ := json.Marshal(payload)
	req, _ := http.NewRequest("POST", "https://api.sweego.io/send", bytes.NewBuffer(jsonData))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Api-Key", "<API_KEY>")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, _ := client.Do(req)
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("Status: %d\nResponse: %s\n", resp.StatusCode, string(body))
}
```

**[Node.js]**

```javascript
const fetch = require('node-fetch');

const payload = {
    channel: "email",
    provider: "sweego",
    recipients: [{ email: "<EMAIL_TO>", name: "Main Recipient" }],
    cc: [{ email: "<EMAIL_CC>", name: "CC Recipient" }],
    bcc: [{ email: "<EMAIL_BCC>", name: "BCC Recipient" }],
    from: { name: "MY NAME", email: "<EMAIL_FROM>" },
    subject: "Email subject",
    "message-txt": "Email body"
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
    "channel" => "email",
    "provider" => "sweego",
    "recipients" => [
        ["email" => "<EMAIL_TO>", "name" => "Main Recipient"]
    ],
    "cc" => [
        ["email" => "<EMAIL_CC>", "name" => "CC Recipient"]
    ],
    "bcc" => [
        ["email" => "<EMAIL_BCC>", "name" => "BCC Recipient"]
    ],
    "from" => [
        "name" => "MY NAME",
        "email" => "<EMAIL_FROM>"
    ],
    "subject" => "Email subject",
    "message-txt" => "Email body"
];

$ch = curl_init('https://api.sweego.io/send');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Api-Key: <API_KEY>',
    'Content-Type: application/json'
]);

echo curl_exec($ch);
curl_close($ch);
?>
```

**[Ruby]**

```ruby
require 'net/http'
require 'json'

payload = {
  channel: "email",
  provider: "sweego",
  recipients: [{ email: "<EMAIL_TO>", name: "Main Recipient" }],
  cc: [{ email: "<EMAIL_CC>", name: "CC Recipient" }],
  bcc: [{ email: "<EMAIL_BCC>", name: "BCC Recipient" }],
  from: { name: "MY NAME", email: "<EMAIL_FROM>" },
  subject: "Email subject",
  "message-txt": "Email body"
}

uri = URI('https://api.sweego.io/send')
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = true
request = Net::HTTP::Post.new(uri.path)
request['Api-Key'] = '<API_KEY>'
request['Content-Type'] = 'application/json'
request.body = payload.to_json

puts http.request(request).body
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
            channel = "email",
            provider = "sweego",
            recipients = new[] { new { email = "<EMAIL_TO>", name = "Main Recipient" } },
            cc = new[] { new { email = "<EMAIL_CC>", name = "CC Recipient" } },
            bcc = new[] { new { email = "<EMAIL_BCC>", name = "BCC Recipient" } },
            from = new { name = "MY NAME", email = "<EMAIL_FROM>" },
            subject = "Email subject",
            messageTxt = "Email body"
        };

        using var client = new HttpClient();
        client.DefaultRequestHeaders.Add("Api-Key", "<API_KEY>");
        
        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        
        var response = await client.PostAsync("https://api.sweego.io/send", content);
        Console.WriteLine(await response.Content.ReadAsStringAsync());
    }
}
```

**[Java]**

```java
import java.net.URI;
import java.net.http.*;
import org.json.*;

public class SendWithCCBCC {
    public static void main(String[] args) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("channel", "email");
        payload.put("provider", "sweego");
        
        payload.put("recipients", new JSONArray()
            .put(new JSONObject()
                .put("email", "<EMAIL_TO>")
                .put("name", "Main Recipient")));
        
        payload.put("cc", new JSONArray()
            .put(new JSONObject()
                .put("email", "<EMAIL_CC>")
                .put("name", "CC Recipient")));
                
        payload.put("bcc", new JSONArray()
            .put(new JSONObject()
                .put("email", "<EMAIL_BCC>")
                .put("name", "BCC Recipient")));
        
        payload.put("from", new JSONObject()
            .put("name", "MY NAME")
            .put("email", "<EMAIL_FROM>"));
        payload.put("subject", "Email subject");
        payload.put("message-txt", "Email body");

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.sweego.io/send"))
            .header("Api-Key", "<API_KEY>")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(payload.toString()))
            .build();

        System.out.println(HttpClient.newHttpClient()
            .send(request, HttpResponse.BodyHandlers.ofString()).body());
    }
}
```

Unlike SMTP, each CC and BCC recipient receives a separate email with its own unique `swg_uid`, enabling proper tracking for all recipients.

### Example 4: Send with template and variables (single recipient only)

#### Prerequisites

- [Create and verify your domain or subdomain](#configure-and-verify-a-subdomain)

- [Create an API key](#create-an-api-access)

#### Sending email

First, [create a template on our App](https://learn.sweego.io/docs/templates/create).

The `<TEMPLATE_ID>` can be retrieved at [https://app.sweego.io/templates](https://app.sweego.io/templates)

If you have defined a variable `{{ name }}` in your template:

`{"key": "[object Object]"}`

**[Curl]**

```shell
curl --location 'https://api.sweego.io/send' \
--header 'Content-Type: application/json' \
--header 'Api-Key: <API_KEY>' \
--data-raw '{
    "template-id": "<TEMPLATE_ID>",
    "channel": "email",
    "provider": "sweego",
    "recipients": [
        { "email": "<EMAIL_TO>" }
    ],
    "from": {
        "name": "Your name",
        "email": "<EMAIL_FROM>"
    },
    "subject": "Email subject",
    "variables": {
        "name": "John Doe"
    }
}'
```

**[Python]**

```py
import requests

payload = {
    "template-id": "<TEMPLATE_ID>",
    "channel": "email",
    "provider": "sweego",
    "recipients": [{"email": "<EMAIL_TO>"}],
    "from": {"name": "Your name", "email": "<EMAIL_FROM>"},
    "subject": "Email subject",
    "variables": {"name": "John Doe"},
}

URL = "https://api.sweego.io/send"
headers = {"Api-Key": "<API_KEY>", "Content-Type": "application/json"}

response = requests.post(URL, json=payload, headers=headers, timeout=10)
print(f"Status: {response.status_code}")
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
		"template-id": "<TEMPLATE_ID>",
		"channel":     "email",
		"provider":    "sweego",
		"recipients": []map[string]string{
			{"email": "<EMAIL_TO>"},
		},
		"from": map[string]string{
			"name":  "Your name",
			"email": "<EMAIL_FROM>",
		},
		"subject": "Email subject",
		"variables": map[string]string{
			"name": "John Doe",
		},
	}

	jsonData, _ := json.Marshal(payload)
	req, _ := http.NewRequest("POST", "https://api.sweego.io/send", bytes.NewBuffer(jsonData))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Api-Key", "<API_KEY>")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, _ := client.Do(req)
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("Status: %d\nResponse: %s\n", resp.StatusCode, string(body))
}
```

**[Node.js]**

```javascript
const fetch = require('node-fetch');

const payload = {
    "template-id": "<TEMPLATE_ID>",
    channel: "email",
    provider: "sweego",
    recipients: [{ email: "<EMAIL_TO>" }],
    from: { name: "Your name", email: "<EMAIL_FROM>" },
    subject: "Email subject",
    variables: { name: "John Doe" }
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
    "template-id" => "<TEMPLATE_ID>",
    "channel" => "email",
    "provider" => "sweego",
    "recipients" => [
        ["email" => "<EMAIL_TO>"]
    ],
    "from" => [
        "name" => "Your name",
        "email" => "<EMAIL_FROM>"
    ],
    "subject" => "Email subject",
    "variables" => [
        "name" => "John Doe"
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

echo curl_exec($ch);
curl_close($ch);
?>
```

**[Ruby]**

```ruby
require 'net/http'
require 'json'

payload = {
  "template-id": "<TEMPLATE_ID>",
  channel: "email",
  provider: "sweego",
  recipients: [{ email: "<EMAIL_TO>" }],
  from: { name: "Your name", email: "<EMAIL_FROM>" },
  subject: "Email subject",
  variables: { name: "John Doe" }
}

uri = URI('https://api.sweego.io/send')
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = true
request = Net::HTTP::Post.new(uri.path)
request['Api-Key'] = '<API_KEY>'
request['Content-Type'] = 'application/json'
request.body = payload.to_json

puts http.request(request).body
```

**[C#]**

```csharp
using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Collections.Generic;

class Program
{
    static async Task Main()
    {
        var payload = new
        {
            templateId = "<TEMPLATE_ID>",
            channel = "email",
            provider = "sweego",
            recipients = new[] { new { email = "<EMAIL_TO>" } },
            from = new { name = "Your name", email = "<EMAIL_FROM>" },
            subject = "Email subject",
            variables = new Dictionary<string, string> { { "name", "John Doe" } }
        };

        using var client = new HttpClient();
        client.DefaultRequestHeaders.Add("Api-Key", "<API_KEY>");
        
        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        
        var response = await client.PostAsync("https://api.sweego.io/send", content);
        Console.WriteLine(await response.Content.ReadAsStringAsync());
    }
}
```

**[Java]**

```java
import java.net.URI;
import java.net.http.*;
import org.json.*;

public class SendWithTemplate {
    public static void main(String[] args) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("template-id", "<TEMPLATE_ID>");
        payload.put("channel", "email");
        payload.put("provider", "sweego");
        
        payload.put("recipients", new JSONArray()
            .put(new JSONObject().put("email", "<EMAIL_TO>")));
        
        payload.put("from", new JSONObject()
            .put("name", "Your name")
            .put("email", "<EMAIL_FROM>"));
        payload.put("subject", "Email subject");
        payload.put("variables", new JSONObject().put("name", "John Doe"));

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.sweego.io/send"))
            .header("Api-Key", "<API_KEY>")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(payload.toString()))
            .build();

        System.out.println(HttpClient.newHttpClient()
            .send(request, HttpResponse.BodyHandlers.ofString()).body());
    }
}
```

If you add CC or BCC recipients to this request, they will see the personalized content intended for the main recipient (with "name" = "John Doe").

### Example 5: Send with attachment

#### Prerequisites

- [Create and verify your domain or subdomain](#configure-and-verify-a-subdomain)

- [Create an API key](#create-an-api-access)

#### Sending email

`{"key": "[object Object]"}`

**[Curl]**

```shell
curl --location 'https://api.sweego.io/send' \
--header 'Content-Type: application/json' \
--header 'Api-Key: <API_KEY>' \
--data-raw '{
    "channel": "email",
    "provider": "sweego",
    "recipients": [
        { "email": "<EMAIL_TO>" }
    ],
    "from": {
        "name": "MY NAME",
        "email": "<EMAIL_FROM>"
    },
    "subject": "Email subject",
    "message-txt": "Email body",
    "attachments": [
        {
            "filename": "<YOUR_FILE>",
            "content": "Y29udGVudQo="
        }
    ]
}'
```

**[Python]**

```py
#!/usr/bin/python3
"""
This script encodes a file to a base64 string and sends an email with an attachment
through a specified API endpoint.

Usage:
    python send_email_with_attachment.py --api-key <API_KEY> --recipients <EMAILS> 
    --from-name <SENDER_NAME> --from-email <SENDER_EMAIL> --subject <SUBJECT> 
    --message-txt <MESSAGE_TEXT> --attachment-file <FILE_PATH>
"""

import argparse
import base64
import requests

def encode_file_to_base64(filepath):
    """Encode a file to a base64 string."""
    with open(filepath, "rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")

def main():
    parser = argparse.ArgumentParser(description="Send an email with attachment using API.")
    parser.add_argument("--api-key", required=True, help="API Key for authentication")
    parser.add_argument("--recipients", required=True, help="Recipient email")
    parser.add_argument("--from-name", required=True, help="Sender name")
    parser.add_argument("--from-email", required=True, help="Sender email")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--message-txt", required=True, help="Email message text")
    parser.add_argument("--attachment-file", required=True, help="Path to the attachment file")

    args = parser.parse_args()

    body = {
        "channel": "email",
        "provider": "sweego",
        "recipients": [{"email": args.recipients}],
        "from": {"name": args.from_name, "email": args.from_email},
        "subject": args.subject,
        "message-txt": args.message_txt,
        "attachments": [
            {
                "filename": args.attachment_file.split("/")[-1],
                "content": encode_file_to_base64(args.attachment_file),
            }
        ],
    }

    headers = {"Api-Key": args.api_key, "Content-Type": "application/json"}
    response = requests.post("https://api.sweego.io/send", headers=headers, json=body, timeout=10)

    print("Status Code:", response.status_code)
    print("Response Body:", response.text)

if __name__ == "__main__":
    main()
```

**[Go]**

```go
package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"time"
)

func encodeFileToBase64(filepath string) (string, error) {
	data, err := os.ReadFile(filepath)
	if err != nil {
		return "", err
	}
	return base64.StdEncoding.EncodeToString(data), nil
}

func main() {
	apiKey := flag.String("api-key", "", "API Key for authentication")
	recipients := flag.String("recipients", "", "Recipient email")
	fromName := flag.String("from-name", "", "Sender name")
	fromEmail := flag.String("from-email", "", "Sender email")
	subject := flag.String("subject", "", "Email subject")
	messageTxt := flag.String("message-txt", "", "Email message text")
	attachmentFile := flag.String("attachment-file", "", "Path to the attachment file")
	flag.Parse()

	content, err := encodeFileToBase64(*attachmentFile)
	if err != nil {
		fmt.Printf("Error encoding file: %v\n", err)
		return
	}

	payload := map[string]interface{}{
		"channel":  "email",
		"provider": "sweego",
		"recipients": []map[string]string{
			{"email": *recipients},
		},
		"from": map[string]string{
			"name":  *fromName,
			"email": *fromEmail,
		},
		"subject":     *subject,
		"message-txt": *messageTxt,
		"attachments": []map[string]string{
			{
				"filename": filepath.Base(*attachmentFile),
				"content":  content,
			},
		},
	}

	jsonData, _ := json.Marshal(payload)
	req, _ := http.NewRequest("POST", "https://api.sweego.io/send", bytes.NewBuffer(jsonData))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Api-Key", *apiKey)

	client := &http.Client{Timeout: 10 * time.Second}
	resp, _ := client.Do(req)
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("Status Code: %d\nResponse Body: %s\n", resp.StatusCode, string(body))
}
```

**[Node.js]**

```javascript
const fs = require('fs');
const fetch = require('node-fetch');

// Read and encode file to base64
const fileBuffer = fs.readFileSync('<ATTACHMENT_FILE_PATH>');
const base64Content = fileBuffer.toString('base64');

const payload = {
    channel: "email",
    provider: "sweego",
    recipients: [{ email: "<EMAIL_TO>" }],
    from: { name: "MY NAME", email: "<EMAIL_FROM>" },
    subject: "Email subject",
    "message-txt": "Email body",
    attachments: [{
        filename: "<YOUR_FILE>",
        content: base64Content
    }]
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
$filePath = '<ATTACHMENT_FILE_PATH>';
$fileContent = base64_encode(file_get_contents($filePath));

$payload = [
    "channel" => "email",
    "provider" => "sweego",
    "recipients" => [
        ["email" => "<EMAIL_TO>"]
    ],
    "from" => [
        "name" => "MY NAME",
        "email" => "<EMAIL_FROM>"
    ],
    "subject" => "Email subject",
    "message-txt" => "Email body",
    "attachments" => [
        [
            "filename" => basename($filePath),
            "content" => $fileContent
        ]
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

echo curl_exec($ch);
curl_close($ch);
?>
```

**[Ruby]**

```ruby
require 'net/http'
require 'json'
require 'base64'

file_path = '<ATTACHMENT_FILE_PATH>'
file_content = Base64.strict_encode64(File.read(file_path))

payload = {
  channel: "email",
  provider: "sweego",
  recipients: [{ email: "<EMAIL_TO>" }],
  from: { name: "MY NAME", email: "<EMAIL_FROM>" },
  subject: "Email subject",
  "message-txt": "Email body",
  attachments: [{
    filename: File.basename(file_path),
    content: file_content
  }]
}

uri = URI('https://api.sweego.io/send')
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = true
request = Net::HTTP::Post.new(uri.path)
request['Api-Key'] = '<API_KEY>'
request['Content-Type'] = 'application/json'
request.body = payload.to_json

puts http.request(request).body
```

**[C#]**

```csharp
using System;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

class Program
{
    static async Task Main()
    {
        var filePath = "<ATTACHMENT_FILE_PATH>";
        var fileBytes = File.ReadAllBytes(filePath);
        var base64Content = Convert.ToBase64String(fileBytes);

        var payload = new
        {
            channel = "email",
            provider = "sweego",
            recipients = new[] { new { email = "<EMAIL_TO>" } },
            from = new { name = "MY NAME", email = "<EMAIL_FROM>" },
            subject = "Email subject",
            messageTxt = "Email body",
            attachments = new[]
            {
                new
                {
                    filename = Path.GetFileName(filePath),
                    content = base64Content
                }
            }
        };

        using var client = new HttpClient();
        client.DefaultRequestHeaders.Add("Api-Key", "<API_KEY>");
        
        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        
        var response = await client.PostAsync("https://api.sweego.io/send", content);
        Console.WriteLine(await response.Content.ReadAsStringAsync());
    }
}
```

**[Java]**

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.util.Base64;
import org.json.*;

public class SendWithAttachment {
    public static void main(String[] args) throws Exception {
        String filePath = "<ATTACHMENT_FILE_PATH>";
        byte[] fileBytes = Files.readAllBytes(Paths.get(filePath));
        String base64Content = Base64.getEncoder().encodeToString(fileBytes);

        JSONObject payload = new JSONObject();
        payload.put("channel", "email");
        payload.put("provider", "sweego");
        
        payload.put("recipients", new JSONArray()
            .put(new JSONObject().put("email", "<EMAIL_TO>")));
        
        payload.put("from", new JSONObject()
            .put("name", "MY NAME")
            .put("email", "<EMAIL_FROM>"));
        payload.put("subject", "Email subject");
        payload.put("message-txt", "Email body");
        
        payload.put("attachments", new JSONArray()
            .put(new JSONObject()
                .put("filename", Paths.get(filePath).getFileName().toString())
                .put("content", base64Content)));

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.sweego.io/send"))
            .header("Api-Key", "<API_KEY>")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(payload.toString()))
            .build();

        System.out.println(HttpClient.newHttpClient()
            .send(request, HttpResponse.BodyHandlers.ofString()).body());
    }
}
```

---

## Method 2: `/send/bulk/email` - Bulk Sending with Personalization

The `/send/bulk/email` endpoint is designed for sending individualized emails to multiple recipients at scale.

### Key characteristics

**Minimum recipients:**

- Requires at least 2 recipients

- Each recipient receives a separate, personalized email

**Privacy:**

- Recipients do not see each other's addresses

- Each email is sent individually

**Personalization:**

- Full support for per-recipient variables

- Each recipient can have unique content

**Limitations:**

- CC and BCC are not supported

- Designed for bulk sending scenarios

### Body parameters

| Field | Description | Format | Obligation |
| --- | --- | --- | --- |
| attachments | Attachment (file) to include in the email | array of dict (filename: string, content: base64 string, content_id: optional string, disposition: optional string) | Optional |
| campaign-id | Campaign ID | string | Optional |
| campaign-tags | Tags to set in mail header (limited to 5) | list of strings (regex: ^[A-Za-z0-9-]20$) | Optional |
| campaign-type | Type of Email with limited choice | string | Optional (transac / newsletter / market) |
| channel | The channel that you want to use | string | Mandatory |
| compress_style | Compress CSS styles in HTML | bool | Optional |
| dry-run | Active Dry-Run mode, no email will really be sent | bool | Optional |
| expires | Expiration date for the email | datetime | Optional |
| force_inline_style | Force inline CSS styles | bool | Optional |
| from | The name and email of the sender | dict | Mandatory (dictionary: email, name) |
| headers | List of custom headers to include (limited to 5) | dict (name:str, value:str) | Optional |
| list-unsub | Set list-unsubscribe header, with one-click management | dict (method:str, value:str) | Optional |
| message-html | Message in HTML format | string | Optional |
| message-txt | Message in txt format | string | Optional |
| provider | The provider that you want to use | string | Mandatory |
| recipients | Minimum 2 recipient addresses. Each recipient can have their own variables inside the object | list | Mandatory (list of dict with: email:str, name:str optional, variables:dict optional) |
| reply-to | The name and email to use when someone replies | dict (email: str, name: optional str) | Optional |
| subject | Email subject | string | Mandatory |
| template-id | Id of the template | string | Optional  (if used, must exist) |

### When to use `/send/bulk/email`

✅ Use this endpoint when:

- You need to send to 2+ recipients with personalized content

- Recipients should NOT see each other (privacy)

- You need different variables for each recipient

- You're doing newsletter or marketing campaigns

❌ Don't use this endpoint for:

- Single recipient emails (use `/send`)

- Emails that need CC/BCC (use `/send`)

- Group emails where recipients should see each other (use `/send`)

### Example: Bulk send with per-recipient variables

`{"key": "[object Object]"}`

**[Curl]**

```shell
curl --location 'https://api.sweego.io/send/bulk/email' \
--header 'Content-Type: application/json' \
--header 'Api-Key: <API_KEY>' \
--data-raw '{
    "template-id": "<TEMPLATE_ID>",
    "channel": "email",
    "provider": "sweego",
    "recipients": [
        {
            "email": "<EMAIL1_TO>",
            "name": "Alice",
            "variables": {
                "name": "Alice",
                "custom_field": "value_for_alice"
            }
        },
        {
            "email": "<EMAIL2_TO>",
            "name": "Bob",
            "variables": {
                "name": "Bob",
                "custom_field": "value_for_bob"
            }
        }
    ],
    "from": {
        "name": "Your name",
        "email": "<EMAIL_FROM>"
    },
    "subject": "Email subject"
}'
```

**[Python]**

```py
import requests

payload = {
    "template-id": "<TEMPLATE_ID>",
    "channel": "email",
    "provider": "sweego",
    "recipients": [
        {
            "email": "<EMAIL1_TO>",
            "name": "Alice",
            "variables": {
                "name": "Alice",
                "custom_field": "value_for_alice"
            }
        },
        {
            "email": "<EMAIL2_TO>",
            "name": "Bob",
            "variables": {
                "name": "Bob",
                "custom_field": "value_for_bob"
            }
        }
    ],
    "from": {"name": "Your name", "email": "<EMAIL_FROM>"},
    "subject": "Email subject",
}

URL = "https://api.sweego.io/send/bulk/email"
headers = {"Api-Key": "<API_KEY>", "Content-Type": "application/json"}

response = requests.post(URL, json=payload, headers=headers, timeout=10)
print(f"Status: {response.status_code}")
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
		"template-id": "<TEMPLATE_ID>",
		"channel":     "email",
		"provider":    "sweego",
		"recipients": []map[string]interface{}{
			{
				"email": "<EMAIL1_TO>",
				"name":  "Alice",
				"variables": map[string]string{
					"name":         "Alice",
					"custom_field": "value_for_alice",
				},
			},
			{
				"email": "<EMAIL2_TO>",
				"name":  "Bob",
				"variables": map[string]string{
					"name":         "Bob",
					"custom_field": "value_for_bob",
				},
			},
		},
		"from": map[string]string{
			"name":  "Your name",
			"email": "<EMAIL_FROM>",
		},
		"subject": "Email subject",
	}

	jsonData, _ := json.Marshal(payload)
	req, _ := http.NewRequest("POST", "https://api.sweego.io/send/bulk/email", bytes.NewBuffer(jsonData))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Api-Key", "<API_KEY>")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, _ := client.Do(req)
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("Status: %d\nResponse: %s\n", resp.StatusCode, string(body))
}
```

**[Node.js]**

```javascript
const fetch = require('node-fetch');

const payload = {
    "template-id": "<TEMPLATE_ID>",
    channel: "email",
    provider: "sweego",
    recipients: [
        {
            email: "<EMAIL1_TO>",
            name: "Alice",
            variables: {
                name: "Alice",
                custom_field: "value_for_alice"
            }
        },
        {
            email: "<EMAIL2_TO>",
            name: "Bob",
            variables: {
                name: "Bob",
                custom_field: "value_for_bob"
            }
        }
    ],
    from: { name: "Your name", email: "<EMAIL_FROM>" },
    subject: "Email subject"
};

fetch('https://api.sweego.io/send/bulk/email', {
    method: 'POST',
    headers: {
        'Api-Key': '<API_KEY>',
        'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
})
.then(res => res.json())
.then(data => console.log('Success:', data))
.catch(err => console.error('Error:', err));
```

**[PHP]**

```php
<?php
$payload = [
    "template-id" => "<TEMPLATE_ID>",
    "channel" => "email",
    "provider" => "sweego",
    "recipients" => [
        [
            "email" => "<EMAIL1_TO>",
            "name" => "Alice",
            "variables" => [
                "name" => "Alice",
                "custom_field" => "value_for_alice"
            ]
        ],
        [
            "email" => "<EMAIL2_TO>",
            "name" => "Bob",
            "variables" => [
                "name" => "Bob",
                "custom_field" => "value_for_bob"
            ]
        ]
    ],
    "from" => [
        "name" => "Your name",
        "email" => "<EMAIL_FROM>"
    ],
    "subject" => "Email subject"
];

$ch = curl_init('https://api.sweego.io/send/bulk/email');
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
  "template-id": "<TEMPLATE_ID>",
  channel: "email",
  provider: "sweego",
  recipients: [
    {
      email: "<EMAIL1_TO>",
      name: "Alice",
      variables: {
        name: "Alice",
        custom_field: "value_for_alice"
      }
    },
    {
      email: "<EMAIL2_TO>",
      name: "Bob",
      variables: {
        name: "Bob",
        custom_field: "value_for_bob"
      }
    }
  ],
  from: { name: "Your name", email: "<EMAIL_FROM>" },
  subject: "Email subject"
}

uri = URI('https://api.sweego.io/send/bulk/email')
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = true

request = Net::HTTP::Post.new(uri.path, {
  'Api-Key' => '<API_KEY>',
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
using System.Collections.Generic;

class Program
{
    static async Task Main()
    {
        var payload = new
        {
            templateId = "<TEMPLATE_ID>",
            channel = "email",
            provider = "sweego",
            recipients = new[]
            {
                new
                {
                    email = "<EMAIL1_TO>",
                    name = "Alice",
                    variables = new Dictionary<string, string>
                    {
                        { "name", "Alice" },
                        { "custom_field", "value_for_alice" }
                    }
                },
                new
                {
                    email = "<EMAIL2_TO>",
                    name = "Bob",
                    variables = new Dictionary<string, string>
                    {
                        { "name", "Bob" },
                        { "custom_field", "value_for_bob" }
                    }
                }
            },
            from = new { name = "Your name", email = "<EMAIL_FROM>" },
            subject = "Email subject"
        };

        using var client = new HttpClient();
        client.DefaultRequestHeaders.Add("Api-Key", "<API_KEY>");
        
        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        
        var response = await client.PostAsync("https://api.sweego.io/send/bulk/email", content);
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
import org.json.JSONObject;
import org.json.JSONArray;

public class SendBulkEmail {
    public static void main(String[] args) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("template-id", "<TEMPLATE_ID>");
        payload.put("channel", "email");
        payload.put("provider", "sweego");
        
        JSONArray recipients = new JSONArray();
        
        JSONObject recipient1 = new JSONObject();
        recipient1.put("email", "<EMAIL1_TO>");
        recipient1.put("name", "Alice");
        JSONObject vars1 = new JSONObject();
        vars1.put("name", "Alice");
        vars1.put("custom_field", "value_for_alice");
        recipient1.put("variables", vars1);
        recipients.put(recipient1);
        
        JSONObject recipient2 = new JSONObject();
        recipient2.put("email", "<EMAIL2_TO>");
        recipient2.put("name", "Bob");
        JSONObject vars2 = new JSONObject();
        vars2.put("name", "Bob");
        vars2.put("custom_field", "value_for_bob");
        recipient2.put("variables", vars2);
        recipients.put(recipient2);
        
        payload.put("recipients", recipients);
        
        JSONObject from = new JSONObject();
        from.put("name", "Your name");
        from.put("email", "<EMAIL_FROM>");
        payload.put("from", from);
        
        payload.put("subject", "Email subject");

        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.sweego.io/send/bulk/email"))
            .header("Api-Key", "<API_KEY>")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(payload.toString()))
            .build();

        HttpResponse<String> response = client.send(request, 
            HttpResponse.BodyHandlers.ofString());
        
        System.out.println("Status: " + response.statusCode());
        System.out.println("Response: " + response.body());
    }
}
```

In this example:

- Alice receives an email with `{{ name }}` = "Alice" and `{{ custom_field }}` = "value_for_alice"

- Bob receives an email with `{{ name }}` = "Bob" and `{{ custom_field }}` = "value_for_bob"

- Neither sees the other's email address

In the bulk method, each recipient object contains its own `variables` object. This is different from the `/send` method where variables are at the root level.

---

## Comparison Table

| Feature | `/send` | `/send/bulk/email` |
| --- | --- | --- |
| Minimum recipients | 1 | 2 |
| Maximum recipients | Unlimited | Unlimited |
| CC/BCC support | ✅ Yes | ❌ No |
| Recipients see each other | ✅ Yes (in To field) | ❌ No (separate emails) |
| Variables with single recipient | ✅ Yes | ✅ Yes |
| Variables with multiple recipients | ❌ No | ✅ Yes (per recipient) |
| Tracking for CC/BCC | ✅ Yes (unique swg_uid) | N/A |
| Use case | Individual, group emails, transactional with CC | Bulk, newsletters, marketing with personalization |

---

## Full API Reference

For complete API specifications and additional parameters:

- [/send endpoint documentation](https://learn.sweego.io/docs/sweego/send-send-post)

- [/send/bulk/email endpoint documentation](https://learn.sweego.io/docs/sweego/send-bulk-email-send-bulk-email-post)
