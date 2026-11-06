# Create a conversational flow with Inbound Routing

Source : https://learn.sweego.io/docs/inbound/conversational_flow

> When you send transactional emails via the Sweego API and use Inbound Routing to receive replies, you need to be able to identify which reply corresponds to which sent email.

When you send transactional emails via the Sweego API and use Inbound Routing to receive replies, you need to be able to identify which reply corresponds to which sent email.

## Recommended solution: Unique Reply-To address

The most reliable method to link replies to original emails is to use a **unique Reply-To address** for each transaction.

### How it works

```
From: support@yourdomain.com
Reply-To: transaction-<unique-identifier>@yourdomain.com
```

When the recipient replies, their response will be sent to the unique address, which you can identify in the Inbound webhook.

### Implementation

#### 1. Generate a unique identifier

Generate a unique identifier for each transaction (UUID, hash, encoded ID, etc.):

`{"key": "[object Object]"}`

**[Python]**

```python
import uuid

# Example with UUID
unique_id = str(uuid.uuid4())
reply_to = f"transaction-{unique_id}@yourdomain.com"

# Example with encoded ID
transaction_id = 12345
import base64
encoded_id = base64.urlsafe_b64encode(str(transaction_id).encode()).decode()
reply_to = f"tx-{encoded_id}@yourdomain.com"
```

**[Node.js]**

```javascript
const crypto = require('crypto');

// Example with UUID
const { v4: uuidv4 } = require('uuid');
const uniqueId = uuidv4();
const replyTo = `transaction-${uniqueId}@yourdomain.com`;

// Example with encoded ID
const transactionId = 12345;
const encodedId = Buffer.from(transactionId.toString()).toString('base64url');
const replyTo = `tx-${encodedId}@yourdomain.com`;
```

**[PHP]**

```php
<?php

// Example with UUID
$uniqueId = bin2hex(random_bytes(16));
$replyTo = "transaction-{$uniqueId}@yourdomain.com";

// Example with encoded ID
$transactionId = 12345;
$encodedId = rtrim(strtr(base64_encode($transactionId), '+/', '-_'), '=');
$replyTo = "tx-{$encodedId}@yourdomain.com";
?>
```

**[Go]**

```go
package main

import (
    "encoding/base64"
    "fmt"
    "github.com/google/uuid"
    "strconv"
)

func main() {
    // Example with UUID
    uniqueId := uuid.New().String()
    replyTo := fmt.Sprintf("transaction-%s@yourdomain.com", uniqueId)

    // Example with encoded ID
    transactionId := 12345
    encodedId := base64.URLEncoding.EncodeToString([]byte(strconv.Itoa(transactionId)))
    replyTo = fmt.Sprintf("tx-%s@yourdomain.com", encodedId)
}
```

**[Ruby]**

```ruby
require 'securerandom'
require 'base64'

# Example with UUID
unique_id = SecureRandom.uuid
reply_to = "transaction-#{unique_id}@yourdomain.com"

# Example with encoded ID
transaction_id = 12345
encoded_id = Base64.urlsafe_encode64(transaction_id.to_s)
reply_to = "tx-#{encoded_id}@yourdomain.com"
```

**[C#]**

```csharp
using System;
using System.Text;

// Example with UUID
string uniqueId = Guid.NewGuid().ToString();
string replyTo = $"transaction-{uniqueId}@yourdomain.com";

// Example with encoded ID
int transactionId = 12345;
string encodedId = Convert.ToBase64String(Encoding.UTF8.GetBytes(transactionId.ToString()))
    .Replace("+", "-").Replace("/", "_").TrimEnd('=');
string replyTo = $"tx-{encodedId}@yourdomain.com";
```

**[Java]**

```java
import java.util.UUID;
import java.util.Base64;

// Example with UUID
String uniqueId = UUID.randomUUID().toString();
String replyTo = "transaction-" + uniqueId + "@yourdomain.com";

// Example with encoded ID
int transactionId = 12345;
String encodedId = Base64.getUrlEncoder()
    .withoutPadding()
    .encodeToString(String.valueOf(transactionId).getBytes());
String replyTo = "tx-" + encodedId + "@yourdomain.com";
```

#### 2. Send via Sweego API

`{"key": "[object Object]"}`

**[cURL]**

```shell
curl -L -X POST \
  --header 'Api-Key: <API_KEY>' \
  --header 'Content-Type: application/json' \
  --location 'https://api.sweego.io/v1/email/send' \
  --data-raw '{
    "to": [
      {
        "email": "customer@example.com",
        "name": "John Doe"
      }
    ],
    "from": {
      "email": "support@yourdomain.com",
      "name": "Support"
    },
    "replyTo": [
      {
        "email": "transaction-a1b2c3d4-e5f6-7890-abcd-ef1234567890@yourdomain.com"
      }
    ],
    "subject": "Order confirmation",
    "html": "<p>Hello,</p><p>Your order has been confirmed.</p>"
  }'
```

**[Python]**

```python
import requests
import uuid

url = "https://api.sweego.io/v1/email/send"

# Generate unique Reply-To
unique_id = str(uuid.uuid4())
reply_to_email = f"transaction-{unique_id}@yourdomain.com"

headers = {
    "Api-Key": "<API_KEY>",
    "Content-Type": "application/json"
}

payload = {
    "to": [
        {
            "email": "customer@example.com",
            "name": "John Doe"
        }
    ],
    "from": {
        "email": "support@yourdomain.com",
        "name": "Support"
    },
    "replyTo": [
        {
            "email": reply_to_email
        }
    ],
    "subject": "Order confirmation",
    "html": "<p>Hello,</p><p>Your order has been confirmed.</p>"
}

response = requests.post(url, headers=headers, json=payload)
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
    "github.com/google/uuid"
)

func main() {
    url := "https://api.sweego.io/v1/email/send"

    // Generate unique Reply-To
    uniqueId := uuid.New().String()
    replyToEmail := fmt.Sprintf("transaction-%s@yourdomain.com", uniqueId)

    payload := map[string]interface{}{
        "to": []map[string]string{
            {"email": "customer@example.com", "name": "John Doe"},
        },
        "from": map[string]string{
            "email": "support@yourdomain.com",
            "name": "Support",
        },
        "replyTo": []map[string]string{
            {"email": replyToEmail},
        },
        "subject": "Order confirmation",
        "html": "<p>Hello,</p><p>Your order has been confirmed.</p>",
    }

    jsonData, _ := json.Marshal(payload)

    req, _ := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
    req.Header.Set("Api-Key", "<API_KEY>")
    req.Header.Set("Content-Type", "application/json")

    client := &http.Client{}
    resp, err := client.Do(req)
    if err != nil {
        panic(err)
    }
    defer resp.Body.Close()

    body, _ := io.ReadAll(resp.Body)
    fmt.Println(string(body))
}
```

**[Node.js]**

```javascript
const https = require('https');
const { v4: uuidv4 } = require('uuid');

// Generate unique Reply-To
const uniqueId = uuidv4();
const replyToEmail = `transaction-${uniqueId}@yourdomain.com`;

const data = JSON.stringify({
    to: [
        { email: 'customer@example.com', name: 'John Doe' }
    ],
    from: {
        email: 'support@yourdomain.com',
        name: 'Support'
    },
    replyTo: [
        { email: replyToEmail }
    ],
    subject: 'Order confirmation',
    html: '<p>Hello,</p><p>Your order has been confirmed.</p>'
});

const options = {
    hostname: 'api.sweego.io',
    path: '/v1/email/send',
    method: 'POST',
    headers: {
        'Api-Key': '<API_KEY>',
        'Content-Type': 'application/json',
        'Content-Length': data.length
    }
};

const req = https.request(options, (res) => {
    let body = '';
    res.on('data', (chunk) => body += chunk);
    res.on('end', () => console.log(body));
});

req.on('error', (error) => console.error(error));
req.write(data);
req.end();
```

**[PHP]**

```php
<?php

$url = 'https://api.sweego.io/v1/email/send';

// Generate unique Reply-To
$uniqueId = bin2hex(random_bytes(16));
$replyToEmail = "transaction-{$uniqueId}@yourdomain.com";

$data = [
    'to' => [
        [
            'email' => 'customer@example.com',
            'name' => 'John Doe'
        ]
    ],
    'from' => [
        'email' => 'support@yourdomain.com',
        'name' => 'Support'
    ],
    'replyTo' => [
        ['email' => $replyToEmail]
    ],
    'subject' => 'Order confirmation',
    'html' => '<p>Hello,</p><p>Your order has been confirmed.</p>'
];

$options = [
    'http' => [
        'header' => [
            'Api-Key: <API_KEY>',
            'Content-Type: application/json'
        ],
        'method' => 'POST',
        'content' => json_encode($data)
    ]
];

$context = stream_context_create($options);
$response = file_get_contents($url, false, $context);

echo $response;
?>
```

**[Ruby]**

```ruby
require 'net/http'
require 'json'
require 'uri'
require 'securerandom'

uri = URI('https://api.sweego.io/v1/email/send')

# Generate unique Reply-To
unique_id = SecureRandom.uuid
reply_to_email = "transaction-#{unique_id}@yourdomain.com"

payload = {
  to: [
    { email: 'customer@example.com', name: 'John Doe' }
  ],
  from: {
    email: 'support@yourdomain.com',
    name: 'Support'
  },
  replyTo: [
    { email: reply_to_email }
  ],
  subject: 'Order confirmation',
  html: '<p>Hello,</p><p>Your order has been confirmed.</p>'
}

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
using System.Threading.Tasks;
using Newtonsoft.Json;

class Program
{
    static async Task Main()
    {
        var url = "https://api.sweego.io/v1/email/send";

        // Generate unique Reply-To
        var uniqueId = Guid.NewGuid().ToString();
        var replyToEmail = $"transaction-{uniqueId}@yourdomain.com";

        var payload = new
        {
            to = new[]
            {
                new { email = "customer@example.com", name = "John Doe" }
            },
            from = new
            {
                email = "support@yourdomain.com",
                name = "Support"
            },
            replyTo = new[]
            {
                new { email = replyToEmail }
            },
            subject = "Order confirmation",
            html = "<p>Hello,</p><p>Your order has been confirmed.</p>"
        };

        using var client = new HttpClient();
        client.DefaultRequestHeaders.Add("Api-Key", "<API_KEY>");

        var json = JsonConvert.SerializeObject(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");

        var response = await client.PostAsync(url, content);
        var result = await response.Content.ReadAsStringAsync();

        Console.WriteLine(result);
    }
}
```

**[Java]**

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.UUID;

public class SendEmail {
    public static void main(String[] args) throws Exception {
        String url = "https://api.sweego.io/v1/email/send";

        // Generate unique Reply-To
        String uniqueId = UUID.randomUUID().toString();
        String replyToEmail = "transaction-" + uniqueId + "@yourdomain.com";

        String json = String.format("""
        {
            "to": [
                {"email": "customer@example.com", "name": "John Doe"}
            ],
            "from": {
                "email": "support@yourdomain.com",
                "name": "Support"
            },
            "replyTo": [
                {"email": "%s"}
            ],
            "subject": "Order confirmation",
            "html": "<p>Hello,</p><p>Your order has been confirmed.</p>"
        }
        """, replyToEmail);

        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("Api-Key", "<API_KEY>")
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();

        HttpResponse<String> response = client.send(request, 
                HttpResponse.BodyHandlers.ofString());

        System.out.println(response.body());
    }
}
```

#### 3. Receive the Inbound webhook

**Inbound Routing configuration:**

- **Domain**: `yourdomain.com`

- **Catchall**: Sweego automatically configures a catchall that captures all emails sent to `*@yourdomain.com`

- **Webhook URL**: `https://your-app.com/webhooks/inbound`

> **Note:** Inbound Routing works with a catchall by default. This means any email sent to any address on your configured domain will be captured and forwarded to your webhook.

**Webhook payload example:**

```json
{
  "event_type": "email_inbound",
  "timestamp": "2026-02-17T17:21:36.835507+00:00",
  "swg_uid": "04-27732983-0018-4c16-ab14-f7f399ae05c6",
  "from_": {
    "email": "customer@example.com",
    "name": "John Doe"
  },
  "to": [
    {
      "email": "transaction-a1b2c3d4-e5f6-7890-abcd-ef1234567890@yourdomain.com",
      "name": ""
    }
  ],
  "cc": [],
  "headers": {
    "in-reply-to": "<1739812896.42.7c3a91f4@yourdomain.com>"
  },
  "text": "Thank you for the confirmation. I have a question...\n",
  "html": "<div dir=\"ltr\">Thank you for the confirmation. I have a question...</div>\n",
  "subject": "Re: Order confirmation",
  "inbound_domain": "yourdomain.com",
  "attachments": [],
  "channel": "email",
  "event_id": "77f8f85d-ed1a-4946-b3af-40edf71a820f",
  "transaction_id": null
}
```

#### 4. Extract the unique identifier from the webhook

`{"key": "[object Object]"}`

**[Python]**

```python
from flask import Flask, request
import re

app = Flask(__name__)

@app.route('/webhooks/inbound', methods=['POST'])
def handle_inbound():
    payload = request.json
    
    # Check event type
    if payload['event_type'] != 'email_inbound':
        return {'status': 'ignored'}, 200
    
    # Get recipient address
    to_email = payload['to'][0]['email']
    
    # Extract unique identifier
    # Pattern: transaction-{uuid}@yourdomain.com
    match = re.match(r'transaction-([A-Za-z0-9_-]+)@', to_email)
    
    if match:
        unique_id = match.group(1)
        
        # Use unique_id to find your original transaction
        # and process the reply
        
    return {'status': 'ok'}, 200
```

**[Node.js]**

```javascript
const express = require('express');
const app = express();

app.use(express.json());

app.post('/webhooks/inbound', (req, res) => {
    const payload = req.body;
    
    // Check event type
    if (payload.event_type !== 'email_inbound') {
        return res.status(200).json({ status: 'ignored' });
    }
    
    // Get recipient address
    const toEmail = payload.to[0].email;
    
    // Extract unique identifier
    // Pattern: transaction-{uuid}@yourdomain.com
    const match = toEmail.match(/transaction-([A-Za-z0-9_-]+)@/);
    
    if (match) {
        const uniqueId = match[1];
        
        // Use uniqueId to find your original transaction
        // and process the reply
    }
    
    res.status(200).json({ status: 'ok' });
});

app.listen(3000);
```

**[PHP]**

```php
<?php

$payload = json_decode(file_get_contents('php://input'), true);

// Check event type
if ($payload['event_type'] !== 'email_inbound') {
    http_response_code(200);
    echo json_encode(['status' => 'ignored']);
    exit;
}

// Get recipient address
$toEmail = $payload['to'][0]['email'];

// Extract unique identifier
// Pattern: transaction-{uuid}@yourdomain.com
if (preg_match('/transaction-([A-Za-z0-9_-]+)@/', $toEmail, $matches)) {
    $uniqueId = $matches[1];
    
    // Use $uniqueId to find your original transaction
    // and process the reply
}

http_response_code(200);
echo json_encode(['status' => 'ok']);
?>
```

**[Go]**

```go
package main

import (
    "encoding/json"
    "net/http"
    "regexp"
)

type InboundPayload struct {
    EventType string `json:"event_type"`
    To []struct {
        Email string `json:"email"`
        Name  string `json:"name"`
    } `json:"to"`
    // Add other fields as needed
}

func handleInbound(w http.ResponseWriter, r *http.Request) {
    var payload InboundPayload
    json.NewDecoder(r.Body).Decode(&payload)
    
    // Check event type
    if payload.EventType != "email_inbound" {
        json.NewEncoder(w).Encode(map[string]string{"status": "ignored"})
        return
    }
    
    // Get recipient address
    toEmail := payload.To[0].Email
    
    // Extract unique identifier
    re := regexp.MustCompile(`transaction-([A-Za-z0-9_-]+)@`)
    matches := re.FindStringSubmatch(toEmail)
    
    if len(matches) > 1 {
        uniqueId := matches[1]
        
        // Use uniqueId to find your original transaction
        // and process the reply
    }
    
    json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func main() {
    http.HandleFunc("/webhooks/inbound", handleInbound)
    http.ListenAndServe(":8080", nil)
}
```

**[Ruby]**

```ruby
require 'sinatra'
require 'json'

post '/webhooks/inbound' do
  payload = JSON.parse(request.body.read)
  
  # Check event type
  if payload['event_type'] != 'email_inbound'
    return { status: 'ignored' }.to_json
  end
  
  # Get recipient address
  to_email = payload['to'][0]['email']
  
  # Extract unique identifier
  # Pattern: transaction-{uuid}@yourdomain.com
  match = to_email.match(/transaction-([A-Za-z0-9_-]+)@/)
  
  if match
    unique_id = match[1]
    
    # Use unique_id to find your original transaction
    # and process the reply
  end
  
  { status: 'ok' }.to_json
end
```

**[C#]**

```csharp
using Microsoft.AspNetCore.Mvc;
using System.Text.RegularExpressions;

[ApiController]
[Route("webhooks")]
public class InboundController : ControllerBase
{
    [HttpPost("inbound")]
    public IActionResult HandleInbound([FromBody] InboundPayload payload)
    {
        // Check event type
        if (payload.EventType != "email_inbound")
        {
            return Ok(new { status = "ignored" });
        }
        
        // Get recipient address
        var toEmail = payload.To[0].Email;
        
        // Extract unique identifier
        var match = Regex.Match(toEmail, @"transaction-([A-Za-z0-9_-]+)@");
        
        if (match.Success)
        {
            var uniqueId = match.Groups[1].Value;
            
            // Use uniqueId to find your original transaction
            // and process the reply
        }
        
        return Ok(new { status = "ok" });
    }
}
```

**[Java]**

```java
import org.springframework.web.bind.annotation.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@RestController
@RequestMapping("/webhooks")
public class InboundController {
    
    @PostMapping("/inbound")
    public Map<String, String> handleInbound(@RequestBody InboundPayload payload) {
        
        // Check event type
        if (!"email_inbound".equals(payload.getEventType())) {
            return Map.of("status", "ignored");
        }
        
        // Get recipient address
        String toEmail = payload.getTo().get(0).getEmail();
        
        // Extract unique identifier
        Pattern pattern = Pattern.compile("transaction-([A-Za-z0-9_-]+)@");
        Matcher matcher = pattern.matcher(toEmail);
        
        if (matcher.find()) {
            String uniqueId = matcher.group(1);
            
            // Use uniqueId to find your original transaction
            // and process the reply
        }
        
        return Map.of("status", "ok");
    }
}
```

## Best practices

### Identifier format

Choose a format that suits your needs. The extraction examples above use the `transaction-` prefix: if you pick another one, adapt the pattern accordingly.

- **UUID**: `transaction-a1b2c3d4-e5f6-7890-abcd-ef1234567890@domain.com`
  
  
  
  
  
  - Advantage: impossible to guess
  
  - Disadvantage: long

- **Encoded ID**: `tx-MTIzNDU@domain.com`
  
  
  
  
  
  - Advantage: shorter
  
  - Disadvantage: can be decoded (not secret)

- **Hash**: `conv-7a8b9c0d1e2f@domain.com`
  
  
  
  
  
  - Advantage: irreversible
  
  - Disadvantage: requires a lookup table

### Dedicated subdomain

For better organization, use a subdomain:

```
reply-to.yourdomain.com
```

Configuration:

- **Inbound Catchall**: `*@reply-to.yourdomain.com`

- **Addresses**: `transaction-{id}@reply-to.yourdomain.com`

### Validation

Verify that the extracted address is valid before processing the message to prevent spam or unsolicited emails.

### Handling attachments

The Inbound webhook includes an `attachments` array. Plan for processing if your use case requires it:

```json
"attachments": [
  {
    "filename": "document.pdf",
    "content_type": "application/pdf",
    "size": 12345,
    "url": "https://..."
  }
]
```

## Inbound webhook structure

Here are the fields available in the webhook payload:

| Field | Type | Description |
| --- | --- | --- |
| `event_type` | string | Always `"email_inbound"` |
| `timestamp` | string | Receipt date/time (ISO 8601) |
| `swg_uid` | string | Sweego unique identifier for the received email |
| `event_id` | string | Unique identifier for the webhook event |
| `from_` | object | Sender (`email`, `name`) |
| `to` | array | Recipient(s) (`email`, `name`) |
| `cc` | array | Copy(ies) |
| `subject` | string | Email subject |
| `text` | string | Plain text content |
| `html` | string | HTML content |
| `inbound_domain` | string | Domain on which the email was received |
| `headers` | object | Subset of the received message's headers, keys lowercased. Not every header is exposed: `message-id`, `references` and `date` are not included yet. |
| `attachments` | array | List of attachments |
| `channel` | string | Always `"email"` |
| `transaction_id` | null | Always `null` for Inbound |

## Inbound Routing configuration

### Prerequisites

- **DNS**: Configure MX records for your domain

- **Webhook**: HTTPS endpoint with valid certificate

### Configuration in Sweego

- Go to **Inbound Routing** in your dashboard

- Add your domain (e.g., `yourdomain.com`)

- Enter your webhook URL

- Test with the simulation tool

> **Note:** The catchall is configured automatically by Sweego. All emails sent to `*@yourdomain.com` will be captured and forwarded to your webhook.
