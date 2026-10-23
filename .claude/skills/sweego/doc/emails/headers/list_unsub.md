# List-unsub headers

Source : https://learn.sweego.io/docs/emails/headers/list_unsub

> The List-Unsubscribe header is an optional email header you can add to your messages. Depending on the mailbox

The `List-Unsubscribe` header is an optional email header you can add to your messages. Depending on the mailbox
provider, it makes an "unsubscribe" button appear next to your message, so a recipient can stop receiving your
emails without having to look for an unsubscribe link inside the content.

It is defined by two RFCs:

- [RFC 2369](https://www.rfc-editor.org/rfc/rfc2369) — the `List-Unsubscribe` header itself (a `mailto:` and/or an `https://` URI)

- [RFC 8058](https://www.rfc-editor.org/rfc/rfc8058) — the "one-click" variant, which adds a `List-Unsubscribe-Post` header

More info on the subject: [List unsubscribe](https://www.badsender.com/en/2021/04/26/all-knowing-or-almost-all-knowing-about-the-list-unsubscribe/)

Sweego only **manages** the `mailto` flavour of `List-Unsubscribe`: unsubscribe requests sent to a `mailto`
address hosted by Sweego are collected, stored, and given back to you (webhook event + daily CSV on your SFTP).

The `one-click` flavour is accepted and sent out correctly, but the HTTPS endpoint is yours: Sweego does not host
it and does not record anything from it. See [One-click method](#one-click-method).

## Setting the header

### Providing your own header

You can provide your own `List-Unsubscribe` header. When you do, **Sweego leaves it untouched**: the value you
send is the value that ends up in the outgoing message. We do not rewrite it, do not append anything to it, and do
not replace it with ours.

There are two equivalent ways to set it.

**With the `list-unsub` object (API):**

```json
{
    "list-unsub": {
        "method": "mailto",
        "value": "<mailto:list-unsub@your-domain.com>"
    }
}
```

| Field | Description | Type | Required |
| --- | --- | --- | --- |
| `method` | `mailto` or `one-click`. Defaults to `mailto` when omitted | string | Optional |
| `value` | The header value, in the format expected by the chosen `method` | string | Required |

**With the raw headers (SMTP, or the `headers` object in the API):**

```
List-Unsubscribe: <mailto:list-unsub@your-domain.com>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

```json
{
    "headers": {
        "List-Unsubscribe": "<mailto:list-unsub@your-domain.com>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"
    }
}
```

When `List-Unsubscribe` is found in the headers, it is pulled out of them and turned into the equivalent
`list-unsub` object — so both forms behave the same way. `List-Unsubscribe-Post: List-Unsubscribe=One-Click`
selects the `one-click` method; without it, the method is `mailto`.

- If you send **both** a `list-unsub` object and a `List-Unsubscribe` header, the `list-unsub` object wins and the
  header is *not* extracted. It is then treated as a regular custom header and gets the `X-` prefix
  (`X-List-Unsubscribe`), which is almost certainly not what you want — pick one form, not both.

- The two list-unsubscribe headers do not count against your 5 [custom headers](/docs/emails/headers/custom_headers):
  they are removed from `headers` before that limit is checked. Sending more than 7 entries in `headers` skips the
  extraction entirely, and the same `X-` prefixing happens.

### Format

The expected `value` depends on the method, and is validated on the fly — a malformed value is rejected with a
`422`.

#### `mailto` method

```
<mailto:EMAIL>
```

Example:

```json
{
    "list-unsub": {
        "method": "mailto",
        "value": "<mailto:list-unsub@your-domain.com?subject=Unsubscribe-yourclient-summer2024-02aa11bb>"
    }
}
```

The optional query part (`?subject=...`, `?body=...`) is preserved as-is.

#### `one-click` method

```
<mailto:EMAIL>,<URL>
```

Example:

```json
{
    "list-unsub": {
        "method": "one-click",
        "value": "<mailto:list-unsub@your-domain.com>,<https://your-domain.com/unsubscribe?id=42>"
    }
}
```

With `one-click`, Sweego adds the companion header required by RFC 8058 to the outgoing message:

```
List-Unsubscribe: <mailto:list-unsub@your-domain.com>, <https://your-domain.com/unsubscribe?id=42>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

The mailbox provider may then call **your** URL with an HTTP `POST` when the recipient clicks the unsubscribe
button. That endpoint is entirely on your side: it must exist, answer without requiring any user interaction, and
record the unsubscribe in your own database. Sweego is not involved in that exchange and will not report those
unsubscribes back to you — only the `mailto` part goes through Sweego.

## Sweego-managed unsubscribes (`mailto` only)

For each of your sending domains, Sweego provisions a dedicated `list-unsub@<your-sending-domain>` mailbox. When a
mailbox provider (or a recipient) sends an unsubscribe request to that address, Sweego:

- receives the message on that mailbox,

- parses it to identify the client, the campaign and the message it refers to,

- stores the unsubscribe request,

- dispatches a `List-unsubscribe` [webhook event](/docs/webhooks/email_events),

- includes it in the daily `list-unsub.YYYY-MM-DD.csv` file on your [SFTP access](/docs/logs/email/list_unsubscribe).

The identifiers are read from the **subject** of the unsubscribe email, which must follow this pattern:

```
Unsubscribe-<client_name>-<campaign_id>-<message_id>
```

This is why the `mailto` value carries a `?subject=` query part. If you build the `mailto` yourself with a
different address or a subject that does not follow this pattern, the unsubscribe request is delivered but cannot
be attached to a message — it will not show up in your webhooks or in your CSV export.

Anything else (an HTTPS one-click endpoint of your own, a `mailto` pointing to one of your own mailboxes, an
unsubscribe link inside the email body) is passed through but never collected by Sweego.

---

##### Related

🔗 [Custom headers](/docs/emails/headers/custom_headers)

🔗 [List unsubscribe logs](/docs/logs/email/list_unsubscribe)

🔗 [Email events (webhooks)](/docs/webhooks/email_events)
