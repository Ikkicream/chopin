# Sending SMS to US, Canada and NANP Countries

Source : https://learn.sweego.io/docs/sms/us_canada_and_nanp_countries

> Sending SMS to the United States, Canada, and other NANP (North American Numbering Plan) countries requires a Toll Free Number (TFN) and registration with US/Canadian authorities.

Sending SMS to the United States, Canada, and other NANP (North American Numbering Plan) countries requires a **Toll Free Number (TFN)** and registration with US/Canadian authorities.

## NANP Countries Coverage

The following countries and territories are part of the NANP zone and share the same requirements for SMS sending:

**North America:**

- United States (US)

- Canada (CA)

**Caribbean:**

- Anguilla (AI)

- Antigua and Barbuda (AG)

- Bahamas (BS)

- Barbados (BB)

- Bermuda (BM)

- British Virgin Islands (VG)

- Cayman Islands (KY)

- Dominica (DM)

- Dominican Republic (DO)

- Grenada (GD)

- Jamaica (JM)

- Montserrat (MS)

- Puerto Rico (PR)

- Saint Kitts and Nevis (KN)

- Saint Lucia (LC)

- Saint Vincent and the Grenadines (VC)

- Trinidad and Tobago (TT)

- Turks and Caicos Islands (TC)

- US Virgin Islands (VI)

**Pacific:**

- Guam (GU)

- Northern Mariana Islands (MP)

- American Samoa (AS)

All these destinations use the **+1** country code and require a verified Toll Free Number.

## Why a Toll Free Number?

US and Canadian telecom regulations require all SMS senders to these destinations to use registered and verified phone numbers. A Toll Free Number (TFN) ensures:

- **Compliance** with local regulations

- **Better deliverability** to recipients

- **Trust** from carriers and end-users

- **Protection** against spam filtering

## Registration Process

### Step 1: Request a Toll Free Number

**Contact our support team** to order your TFN.

- **Delivery time:** Approximately 1 week

- **Unique:** Each TFN is unique per customer

### Step 2: Complete the Registration Form

Once you receive your TFN, you must complete the **registration form** required by US/Canadian authorities.

> 📋 **Registration form:** [Link will be provided]

This form collects information about:

- Your business details

- Use case for SMS sending

- Expected volume

- Opt-in/opt-out procedures

### Step 3: Sweego Handles Registration

We take care of submitting your registration to the authorities.

- **No additional fees:** Registration is included at no extra cost

- **Processing time:** 1-2 weeks for approval

- **Updates:** We'll keep you informed throughout the process

### Step 4: Start Sending

Once your TFN is approved, you can begin sending SMS to NANP destinations.

## Pricing

Toll Free Number subscription:

| Billing Period | Price | Renewal |
| --- | --- | --- |
| Monthly | €1.25/month | Auto-renewal |
| Yearly | €12/year | Auto-renewal |
| Setup Fee | €75 (one-time) | No renewal |

> **Note:** SMS sending costs are separate and billed according to your Sweego credit.

## How to Send SMS with Your TFN

Once your TFN is approved, you must specify it in the `sender-id` parameter of your API calls.

### Example

`{"key": "[object Object]"}`

**[cURL]**

```shell
curl -L -X POST \
  --header 'Api-Key: <API_KEY>' \
  --header 'Content-Type: application/json' \
  --location 'https://api.sweego.io/send' \
  --data-raw '{
    "channel": "sms",
    "provider": "sweego",
    "recipients": [
        { "num": "+1234567890", "region": "US" }
    ],
    "message-txt": "Your message content",
    "campaign-type": "transac",
    "sender-id": "YOUR_TFN"
}'
```

**[Python]**

```python
import requests

url = "https://api.sweego.io/send"

headers = {
    "Api-Key": "<API_KEY>",
    "Content-Type": "application/json"
}

payload = {
    "channel": "sms",
    "provider": "sweego",
    "recipients": [
        {"num": "+1234567890", "region": "US"}
    ],
    "message-txt": "Your message content",
    "campaign-type": "transac",
    "sender-id": "YOUR_TFN"
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
)

func main() {
    url := "https://api.sweego.io/send"

    payload := map[string]interface{}{
        "channel":       "sms",
        "provider":      "sweego",
        "recipients": []map[string]string{
            {"num": "+1234567890", "region": "US"},
        },
        "message-txt":   "Your message content",
        "campaign-type": "transac",
        "sender-id":     "YOUR_TFN",
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

const data = JSON.stringify({
    channel: 'sms',
    provider: 'sweego',
    recipients: [
        { num: '+1234567890', region: 'US' }
    ],
    'message-txt': 'Your message content',
    'campaign-type': 'transac',
    'sender-id': 'YOUR_TFN'
});

const options = {
    hostname: 'api.sweego.io',
    path: '/send',
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

$url = 'https://api.sweego.io/send';

$data = [
    'channel' => 'sms',
    'provider' => 'sweego',
    'recipients' => [
        ['num' => '+1234567890', 'region' => 'US']
    ],
    'message-txt' => 'Your message content',
    'campaign-type' => 'transac',
    'sender-id' => 'YOUR_TFN'
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

uri = URI('https://api.sweego.io/send')

payload = {
  channel: 'sms',
  provider: 'sweego',
  recipients: [
    { num: '+1234567890', region: 'US' }
  ],
  'message-txt': 'Your message content',
  'campaign-type': 'transac',
  'sender-id': 'YOUR_TFN'
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
        var url = "https://api.sweego.io/send";

        var payload = new
        {
            channel = "sms",
            provider = "sweego",
            recipients = new[]
            {
                new { num = "+1234567890", region = "US" }
            },
            message_txt = "Your message content",
            campaign_type = "transac",
            sender_id = "YOUR_TFN"
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

public class SendSMS {
    public static void main(String[] args) throws Exception {
        String url = "https://api.sweego.io/send";

        String json = """
        {
            "channel": "sms",
            "provider": "sweego",
            "recipients": [
                {"num": "+1234567890", "region": "US"}
            ],
            "message-txt": "Your message content",
            "campaign-type": "transac",
            "sender-id": "YOUR_TFN"
        }
        """;

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

## Best Practices

### Compliance Requirements

- **Opt-in:** Ensure recipients have explicitly opted in to receive SMS

- **Opt-out:** For transactional SMS, provide a clear way to unsubscribe (e.g., "Reply STOP to unsubscribe"). For marketing SMS, Sweego automatically adds the STOP message.

- **Content:** Avoid spam or misleading content

- **Identification:** Clearly identify your business in messages

### Message Content Guidelines

- Keep messages concise and relevant

- Include your business name

- Provide value to recipients

- Respect quiet hours (8 AM - 9 PM local time)

### Volume Considerations

- Start with lower volumes to establish sender reputation

- Gradually increase sending volume

- Monitor delivery rates and feedback

## FAQ

**Q: Can I use my TFN for other countries?**

A: No, TFNs are specifically for NANP countries. For other destinations, use regular SenderIDs.

**Q: How long does TFN approval take?**

A: Typically 1-2 weeks after form submission, but it can vary based on authority workload.

**Q: Can I have multiple TFNs?**

A: No, each customer can only have one TFN.

**Q: What happens if my registration is rejected?**

A: We'll notify you of the reasons and help you resubmit with corrected information.

**Q: Are there message volume limits?**

A: Initial volumes may be limited. As you establish sender reputation, limits can be increased.

**Q: Can I cancel my TFN subscription?**

A: Yes, contact support to cancel. Note that cancellation takes effect at the end of your billing period.

**Q: Do I need to add "STOP" to my marketing messages?**

A: No, for marketing SMS (`campaign-type: "market"`), Sweego automatically adds the opt-out message. For transactional SMS, you should include it in your message content if needed.
