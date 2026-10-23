# Webhook Signature Validation

Source : https://learn.sweego.io/docs/webhooks/webhook_signature

> Introduction

## Introduction

To ensure security and verify that webhook requests truly come from Sweego and haven't been altered, all webhooks are signed using HMAC-SHA256 signatures.

This allows you to verify the authenticity and integrity of each webhook request by recalculating the signature using your secret key and comparing it with the signature provided in the headers.

## HTTP Headers

Each webhook request includes the following headers:

- `webhook-id`: Unique identifier for this webhook request

- `webhook-timestamp`: Unix timestamp when the webhook was sent

- `webhook-signature`: HMAC-SHA256 signature (base64-encoded)

## Signature Format

The signature is calculated using the following format:

```
{webhook-id}.{webhook-timestamp}.{body}
```

Where:

- `{webhook-id}` is the value from the `webhook-id` header

- `{webhook-timestamp}` is the value from the `webhook-timestamp` header

- `{body}` is the raw JSON body of the request (exactly as received)

## Important Notes

- **Use the raw body**: The body must be used exactly as received - do not parse and re-serialize the JSON, as this may change whitespace or field ordering.

- **Secret format**: Your webhook secret is provided as a 64-character string. Decode it using base64 decoding before using it as the HMAC key.

- **Signature encoding**: The computed signature should be base64-encoded before comparison.

## Code Examples

`{"key": "[object Object]"}`

**[Python]**

```python
import hmac
import hashlib
import base64

def validate_webhook_signature(webhook_id, webhook_timestamp, webhook_signature, body, secret):
    """
    Validate Sweego webhook signature
    
    Args:
        webhook_id: Value from 'webhook-id' header
        webhook_timestamp: Value from 'webhook-timestamp' header
        webhook_signature: Value from 'webhook-signature' header
        body: Raw request body (string)
        secret: Your webhook secret (64-character string)
    
    Returns:
        bool: True if signature is valid, False otherwise
    """
    # Format content to sign
    content_to_sign = f"{webhook_id}.{webhook_timestamp}.{body}".encode('utf-8')
    
    # Decode secret using base64
    secret_bytes = base64.b64decode(secret)
    
    # Compute HMAC-SHA256
    digest = hmac.new(
        key=secret_bytes,
        msg=content_to_sign,
        digestmod=hashlib.sha256
    ).digest()
    
    # Encode to base64
    computed_signature = base64.b64encode(digest).decode('utf-8')
    
    # Compare signatures (timing-safe comparison)
    return hmac.compare_digest(computed_signature, webhook_signature)

# Example: Validate a webhook
webhook_id = "237e3736c687425d9ea8665216bcfe8a"
webhook_timestamp = "1769696506"
webhook_signature = "J16rH/6ynqqlA+oJKd4emRdDpxgdK6c85BBiwMSeFrY="
body = '{"event_type":"email_inbound","timestamp":"2026-01-29T14:21:46.729251+00:00"...}'
secret = "YOUR_SECRET_HERE"

if validate_webhook_signature(webhook_id, webhook_timestamp, webhook_signature, body, secret):
    print("✅ Webhook signature is valid")
    # Process the webhook
else:
    print("❌ Invalid signature")
```

**[Python + Flask]**

```python
import hmac
import hashlib
import base64
from flask import Flask, request

app = Flask(__name__)

def validate_webhook_signature(webhook_id, webhook_timestamp, webhook_signature, body, secret):
    """Validate Sweego webhook signature"""
    content_to_sign = f"{webhook_id}.{webhook_timestamp}.{body}".encode('utf-8')
    secret_bytes = base64.b64decode(secret)
    digest = hmac.new(secret_bytes, content_to_sign, hashlib.sha256).digest()
    computed_signature = base64.b64encode(digest).decode('utf-8')
    return hmac.compare_digest(computed_signature, webhook_signature)

@app.route('/webhook/sweego', methods=['POST'])
def handle_webhook():
    # Get headers
    webhook_id = request.headers.get('webhook-id')
    webhook_timestamp = request.headers.get('webhook-timestamp')
    webhook_signature = request.headers.get('webhook-signature')
    
    # Get raw body
    body = request.get_data(as_text=True)
    
    # Your webhook secret
    secret = "YOUR_SECRET_HERE"
    
    # Validate signature
    if not validate_webhook_signature(webhook_id, webhook_timestamp, webhook_signature, body, secret):
        return 'Invalid signature', 401
    
    # Process webhook
    data = request.get_json()
    print(f"Received webhook: {data.get('event_type')}")
    
    return 'OK', 200

if __name__ == '__main__':
    app.run(port=8080)
```

**[Go]**

```go
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"io"
	"net/http"
)

func validateWebhookSignature(webhookID, webhookTimestamp, webhookSignature, body, secret string) bool {
	// Decode secret from base64
	secretBytes, err := base64.StdEncoding.DecodeString(secret)
	if err != nil {
		fmt.Printf("Error decoding secret: %v\n", err)
		return false
	}
	
	// Format content to sign
	content := fmt.Sprintf("%s.%s.%s", webhookID, webhookTimestamp, body)
	
	// Compute HMAC-SHA256
	h := hmac.New(sha256.New, secretBytes)
	h.Write([]byte(content))
	digest := h.Sum(nil)
	
	// Encode to base64
	computedSignature := base64.StdEncoding.EncodeToString(digest)
	
	// Compare signatures (constant-time comparison)
	return hmac.Equal([]byte(computedSignature), []byte(webhookSignature))
}

func webhookHandler(w http.ResponseWriter, r *http.Request) {
	// Get headers
	webhookID := r.Header.Get("webhook-id")
	webhookTimestamp := r.Header.Get("webhook-timestamp")
	webhookSignature := r.Header.Get("webhook-signature")
	
	// Read raw body
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Failed to read body", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()
	
	// Your webhook secret
	secret := "YOUR_SECRET_HERE"
	
	// Validate signature
	if !validateWebhookSignature(webhookID, webhookTimestamp, webhookSignature, string(body), secret) {
		http.Error(w, "Invalid signature", http.StatusUnauthorized)
		return
	}
	
	// Process webhook
	fmt.Println("Webhook validated successfully")
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}

func main() {
	http.HandleFunc("/webhook/sweego", webhookHandler)
	fmt.Println("Server listening on :8080")
	http.ListenAndServe(":8080", nil)
}
```

**[Node.js]**

```javascript
const crypto = require('crypto');
const express = require('express');

/**
 * Validate Sweego webhook signature
 */
function validateWebhookSignature(webhookId, webhookTimestamp, webhookSignature, body, secret) {
    // Decode secret from base64
    const secretBytes = Buffer.from(secret, 'base64');
    
    // Format content to sign
    const content = `${webhookId}.${webhookTimestamp}.${body}`;
    
    // Compute HMAC-SHA256
    const hmac = crypto.createHmac('sha256', secretBytes);
    hmac.update(content);
    const digest = hmac.digest();
    
    // Encode to base64
    const computedSignature = digest.toString('base64');
    
    // Compare signatures (timing-safe comparison)
    return crypto.timingSafeEqual(
        Buffer.from(computedSignature),
        Buffer.from(webhookSignature)
    );
}

const app = express();

// Important: Use express.text() to get raw body
app.post('/webhook/sweego', express.text({type: 'application/json'}), (req, res) => {
    // Get headers
    const webhookId = req.headers['webhook-id'];
    const webhookTimestamp = req.headers['webhook-timestamp'];
    const webhookSignature = req.headers['webhook-signature'];
    
    // Get raw body (as string)
    const body = req.body;
    
    // Your webhook secret
    const secret = 'YOUR_SECRET_HERE';
    
    // Validate signature
    if (!validateWebhookSignature(webhookId, webhookTimestamp, webhookSignature, body, secret)) {
        return res.status(401).send('Invalid signature');
    }
    
    // Process webhook
    const data = JSON.parse(body);
    console.log(`Received webhook: ${data.event_type}`);
    
    res.status(200).send('OK');
});

app.listen(3000, () => {
    console.log('Server listening on port 3000');
});
```

**[PHP]**

```php
<?php

/**
 * Validate Sweego webhook signature
 */
function validateWebhookSignature($webhookId, $webhookTimestamp, $webhookSignature, $body, $secret) {
    // Decode secret from base64
    $secretBytes = base64_decode($secret);
    
    // Format content to sign
    $content = "{$webhookId}.{$webhookTimestamp}.{$body}";
    
    // Compute HMAC-SHA256
    $digest = hash_hmac('sha256', $content, $secretBytes, true);
    
    // Encode to base64
    $computedSignature = base64_encode($digest);
    
    // Compare signatures (timing-safe comparison)
    return hash_equals($computedSignature, $webhookSignature);
}

// Get headers
$webhookId = $_SERVER['HTTP_WEBHOOK_ID'];
$webhookTimestamp = $_SERVER['HTTP_WEBHOOK_TIMESTAMP'];
$webhookSignature = $_SERVER['HTTP_WEBHOOK_SIGNATURE'];

// Get raw body
$body = file_get_contents('php://input');

// Your webhook secret
$secret = 'YOUR_SECRET_HERE';

// Validate signature
if (!validateWebhookSignature($webhookId, $webhookTimestamp, $webhookSignature, $body, $secret)) {
    http_response_code(401);
    echo 'Invalid signature';
    exit;
}

// Process webhook
$data = json_decode($body, true);
echo "Received webhook: " . $data['event_type'];

http_response_code(200);
echo 'OK';
?>
```

**[Ruby]**

```ruby
require 'openssl'
require 'base64'
require 'sinatra'
require 'json'

# Validate Sweego webhook signature
def validate_webhook_signature(webhook_id, webhook_timestamp, webhook_signature, body, secret)
  # Decode secret from base64
  secret_bytes = Base64.decode64(secret)
  
  # Format content to sign
  content = "#{webhook_id}.#{webhook_timestamp}.#{body}"
  
  # Compute HMAC-SHA256
  digest = OpenSSL::HMAC.digest('sha256', secret_bytes, content)
  
  # Encode to base64
  computed_signature = Base64.strict_encode64(digest)
  
  # Compare signatures (timing-safe comparison)
  Rack::Utils.secure_compare(computed_signature, webhook_signature)
end

# Webhook endpoint
post '/webhook/sweego' do
  # Get headers
  webhook_id = request.env['HTTP_WEBHOOK_ID']
  webhook_timestamp = request.env['HTTP_WEBHOOK_TIMESTAMP']
  webhook_signature = request.env['HTTP_WEBHOOK_SIGNATURE']
  
  # Get raw body
  request.body.rewind
  body = request.body.read
  
  # Your webhook secret
  secret = 'YOUR_SECRET_HERE'
  
  # Validate signature
  unless validate_webhook_signature(webhook_id, webhook_timestamp, webhook_signature, body, secret)
    halt 401, 'Invalid signature'
  end
  
  # Process webhook
  data = JSON.parse(body)
  puts "Received webhook: #{data['event_type']}"
  
  status 200
  'OK'
end
```

**[C#]**

```csharp
using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Mvc;

public class WebhookController : ControllerBase
{
    /// <summary>
    /// Validate Sweego webhook signature
    /// </summary>
    private bool ValidateWebhookSignature(
        string webhookId, 
        string webhookTimestamp, 
        string webhookSignature, 
        string body, 
        string secret)
    {
        // Decode secret from base64
        byte[] secretBytes = Convert.FromBase64String(secret);
        
        // Format content to sign
        string content = $"{webhookId}.{webhookTimestamp}.{body}";
        byte[] contentBytes = Encoding.UTF8.GetBytes(content);
        
        // Compute HMAC-SHA256
        using (var hmac = new HMACSHA256(secretBytes))
        {
            byte[] digest = hmac.ComputeHash(contentBytes);
            
            // Encode to base64
            string computedSignature = Convert.ToBase64String(digest);
            
            // Compare signatures (timing-safe comparison)
            return CryptographicOperations.FixedTimeEquals(
                Encoding.UTF8.GetBytes(computedSignature),
                Encoding.UTF8.GetBytes(webhookSignature)
            );
        }
    }
    
    [HttpPost("webhook/sweego")]
    public async Task<IActionResult> HandleWebhook()
    {
        // Get headers
        string webhookId = Request.Headers["webhook-id"];
        string webhookTimestamp = Request.Headers["webhook-timestamp"];
        string webhookSignature = Request.Headers["webhook-signature"];
        
        // Read raw body
        using (StreamReader reader = new StreamReader(Request.Body, Encoding.UTF8))
        {
            string body = await reader.ReadToEndAsync();
            
            // Your webhook secret
            string secret = "YOUR_SECRET_HERE";
            
            // Validate signature
            if (!ValidateWebhookSignature(webhookId, webhookTimestamp, webhookSignature, body, secret))
            {
                return Unauthorized("Invalid signature");
            }
            
            // Process webhook
            Console.WriteLine($"Webhook validated successfully");
            
            return Ok("OK");
        }
    }
}
```

**[Java]**

```java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.ResponseEntity;

@RestController
public class WebhookController {
    
    /**
     * Validate Sweego webhook signature
     */
    private boolean validateWebhookSignature(
            String webhookId,
            String webhookTimestamp,
            String webhookSignature,
            String body,
            String secret) {
        
        try {
            // Decode secret from base64
            byte[] secretBytes = Base64.getDecoder().decode(secret);
            
            // Format content to sign
            String content = webhookId + "." + webhookTimestamp + "." + body;
            byte[] contentBytes = content.getBytes(StandardCharsets.UTF_8);
            
            // Compute HMAC-SHA256
            Mac mac = Mac.getInstance("HmacSHA256");
            SecretKeySpec secretKey = new SecretKeySpec(secretBytes, "HmacSHA256");
            mac.init(secretKey);
            byte[] digest = mac.doFinal(contentBytes);
            
            // Encode to base64
            String computedSignature = Base64.getEncoder().encodeToString(digest);
            
            // Compare signatures (timing-safe comparison)
            return MessageDigest.isEqual(
                computedSignature.getBytes(StandardCharsets.UTF_8),
                webhookSignature.getBytes(StandardCharsets.UTF_8)
            );
            
        } catch (Exception e) {
            System.err.println("Error validating signature: " + e.getMessage());
            return false;
        }
    }
    
    @PostMapping("/webhook/sweego")
    public ResponseEntity<String> handleWebhook(
            @RequestHeader("webhook-id") String webhookId,
            @RequestHeader("webhook-timestamp") String webhookTimestamp,
            @RequestHeader("webhook-signature") String webhookSignature,
            @RequestBody String body) {
        
        // Your webhook secret
        String secret = "YOUR_SECRET_HERE";
        
        // Validate signature
        if (!validateWebhookSignature(webhookId, webhookTimestamp, webhookSignature, body, secret)) {
            return ResponseEntity.status(401).body("Invalid signature");
        }
        
        // Process webhook
        System.out.println("Webhook validated successfully");
        
        return ResponseEntity.ok("OK");
    }
}
```

## Troubleshooting

### Signature validation fails

If signature validation is failing:

- **Check the secret**: Ensure you're using the correct webhook secret from your Sweego dashboard

- **Verify the body**: Make sure you're using the raw request body without any modifications:
  
  
  
  
  ```python
  # ❌ Wrong - parsing changes the body
  data = json.loads(body)
  body = json.dumps(data)
  
  # ✅ Correct - use raw body
  body = request.get_data(as_text=True)
  ```

- **Check header names**: Header names are case-insensitive in HTTP, but ensure you're reading:
  
  
  
  
  
  - `webhook-id` (or `Webhook-Id`)
  
  - `webhook-timestamp` (or `Webhook-Timestamp`)
  
  - `webhook-signature` (or `Webhook-Signature`)

- **Verify content format**: The content must be formatted exactly as:
  
  
  
  
  ```
  {id}.{timestamp}.{body}
  ```
  
  
  
  
  With no extra spaces or characters.

- **Secret decoding**: Ensure you're decoding the secret using base64 before using it as the HMAC key.

### Need help?

If you're still having issues, contact Sweego support with:

- The `webhook-id` from a failed request

- Your implementation language

- Whether you can see the webhook in your Sweego dashboard
