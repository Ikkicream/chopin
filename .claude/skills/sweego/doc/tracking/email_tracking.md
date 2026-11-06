# Email Tracking

Source : https://learn.sweego.io/docs/tracking/email_tracking

> Setup

# Email Tracking

## Setup

### Verify Domain

First, ensure your domain is verified on Sweego.

You can verify your domain by visiting [Sweego's Domain Management](https://app.sweego.io/home/domains).

![Tracking Add Domain](undefined)

### Enable Tracking

Enable **Email click-through tracking** and **Email open tracking** if you want to track opens and clicks.

You'll need to add a new DNS record in your DNS zone. The status will show as **verified** once your DNS zone is properly configured.

![Tracking Enable Domain](undefined)

---

## Sending a Tracked Email

Once tracking is enabled, send an email and Sweego will automatically rewrite your links to track interactions.

The tracking domain is derived from your sending domain: if you send from `sub.domain.com`, the tracking URLs will use `t.sub.domain.com`.

### Standard Links

Any link in your email HTML is automatically rewritten to route through Sweego's tracking infrastructure:

```html
<!-- Original -->
<a href="https://my_domain.com">Visit our website</a>

<!-- Rewritten by Sweego -->
<a href="https://t.my_domain.com/t/c/?i=<ENCODED_ID>&u=<URL_ENCODED>">Visit our website</a>
```

### Unsubscribe Links

To identify unsubscribe link clicks separately from regular clicks, add the `data-url-type="unsub"` attribute to your unsubscribe anchor tag:

```html
<!-- Standard link — tracked as a regular click -->
<a href="https://my_domain.com">Visit our website</a>

<!-- Unsubscribe link — tracked as an unsubscribe click -->
<a href="https://unsub.my_domain.com/unsubscribe" data-url-type="unsub">Unsubscribe</a>
```

Sweego detects this attribute and rewrites the URL differently, using `/t/u/` instead of `/t/c/` in the tracking path:

| Link type | Tracking URL pattern |
| --- | --- |
| Regular click | `https://t.<sending_domain>/t/c/?i=<ENCODED_ID>&u=<URL_ENCODED>` |
| Unsubscribe click | `https://t.<sending_domain>/t/u/?i=<ENCODED_ID>&u=<URL_ENCODED>` |

This distinction allows you to differentiate between engagement clicks and unsubscribe intent in your logs and future webhook events.

### Full Example

Input passed to Sweego (sending domain: `send.example.com`):

```html
<html>
  <body>
    <p>Hi,</p>
    <p>This is my new message with Sweego.</p>
    <p>More details: <a href="https://send.example.com">our website</a></p>
    <a href="https://unsub.example.com/unsubscribe" data-url-type="unsub">Unsubscribe</a>
  </body>
</html>
```

What is actually delivered in the email (links rewritten, tracking pixel injected):

```html
<html>
  <body>
    <p>Hi,</p>
    <p>This is my new message with Sweego.</p>
    <p>More details:
      <a href="https://t.send.example.com/t/c/?i=<ENCODED_ID>&u=https%3A%2F%2Fsend.example.com">
        our website
      </a>
    </p>
    <a data-url-type="unsub"
       href="https://t.send.example.com/t/u/?i=<ENCODED_ID>&u=https%3A%2F%2Funsub.example.com%2Funsubscribe">
      Unsubscribe
    </a>
    <!-- Tracking pixel (1x1 image) injected automatically -->
    <img alt="" height="1" src="https://t.send.example.com/t/o/?i=<ENCODED_ID>" width="1" />
  </body>
</html>
```

---

## API Request Example

```json
{
    "campaign-id": "42",
    "channel": "email",
    "provider": "sweego",
    "reply_to": {
        "email": "xxxx@xxx.com",
        "name": "My_Name"
    },
    "recipients": [
        { "email": "yyyy@yyyyy.com" }
    ],
    "from": {
        "name": "My From email",
        "email": "contact@send.example.com"
    },
    "subject": "My message subject",
    "message-html": "<html><body><p>Hi,</p><p>This is my new message with Sweego.</p><p>More details: <a href='https://send.example.com'>our website</a></p><a href='https://unsub.example.com/unsubscribe' data-url-type='unsub'>Unsubscribe</a></body></html>",
    "campaign-type": "transac",
    "campaign-tags": ["tag1", "tag2", "tag3"],
    "dry-run": false,
    "headers": {
        "Ref-1": "643524"
    }
}
```

---

## Viewing Tracking Logs

After a few minutes (time required for data integrity checks), tracking events are available in your logs:

👉 [https://app.sweego.io/logs/email](https://app.sweego.io/logs/email)

### Available Statuses

| Status | Description |
| --- | --- |
| `opened-proxy` | Email opened via a proxy or email security scanner |
| `opened-human` | Email opened by a human recipient |
| `clicked-proxy` | Link clicked by a proxy or bot |
| `clicked-human` | Link clicked by a human recipient |
| `clicked-unsub` | Unsubscribe link clicked (requires `data-url-type="unsub"`) |

> **Note:** Webhook support for `clicked-unsub` events is coming soon. In the meantime, these events are visible in your logs.
