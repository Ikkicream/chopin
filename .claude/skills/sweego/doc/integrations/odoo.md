# Odoo Connectors

Source : https://learn.sweego.io/docs/integrations/odoo

> Send emails and SMS from Odoo through Sweego with the Mangono Sweego connectors

# Odoo Connectors

Two connectors let you use Sweego as the email and SMS provider of your [Odoo](https://www.odoo.com/) instance:

- **[Mangono Sweego Mail](https://apps.odoo.com/apps/modules/19.0/mangono_sweego_mail)** (`mangono_sweego_mail`) — routes outgoing Odoo emails through the Sweego SMTP relay, tracks delivery with webhooks, and brings customer replies back into the right Odoo document.

- **[Mangono Sweego SMS](https://apps.odoo.com/apps/modules/19.0/mangono_sweego_sms)** (`mangono_sweego_sms`) — sends Odoo SMS through the Sweego API instead of Odoo's IAP service.

Both are open-source community modules (AGPL-3) published by [Mangono](https://mangono.fr/connecteurs-odoo/sweego.html) on the Odoo Apps Store. They are available for **Odoo 18.0 and 19.0**, and work on Odoo Online, Odoo.sh and On-Premise deployments.

You can install either one independently, or both if you send emails and SMS from Odoo.

## Prerequisites

Before starting, make sure you have:

- An Odoo 18.0 or 19.0 instance with administrator access

- A Sweego account with an active **API key** and your **Client ID** (also called Client UUID)

- For email: a [verified sending domain](/docs/emails/set_up_a_domain) and a [SMTP access](/docs/auth/smtp)

- For SMS: a [configured SMS channel](/docs/sms/set_up_sms_channel) and a [sender ID](/docs/sms/what_is_a_senderid)

You can find how to create your Sweego API credentials in [our guide](/docs/auth/api_keys).

## Installation

Install the connector you need from the Odoo Apps Store:

- [Mangono Sweego Mail](https://apps.odoo.com/apps/modules/19.0/mangono_sweego_mail) — depends on the **Discuss** (`mail`) app

- [Mangono Sweego SMS](https://apps.odoo.com/apps/modules/19.0/mangono_sweego_sms) — depends on the **SMS** (`sms`) and **Discuss** (`mail`) apps

Both modules rely on a shared base module (`mangono_sweego_base`) that holds the Sweego credentials, so it is installed as a dependency.

Once installed, enter your Sweego **API key** and **Client ID** in the Sweego settings. Both connectors read the credentials from there, so you only enter them once. In a multi-company database, the credentials can be set per company.

## Email

### Configuration

- Go to **Settings > Technical > Outgoing Mail Servers** and create (or edit) a server.

- Select the **Mangono Sweego SMTP** authentication mode. The module fills in the Sweego SMTP host, port and encryption for you.

- Enter the credentials of your Sweego [SMTP access](/docs/auth/smtp).

- Test the connection, then send a test message from Odoo.

In a multi-company database, you can declare one outgoing server per company, each with its own sending domain.

### Delivery tracking

The connector uses Sweego [webhooks](/docs/webhooks/setup) to keep Odoo in sync with the real delivery status. Create two webhooks in your Sweego dashboard pointing to your Odoo instance:

| Purpose | Endpoint | Events |
| --- | --- | --- |
| Outbound tracking | `https://your-odoo-instance/sweego/webhook/outbound` | `email_sent`, `delivered` |
| Inbound replies | `https://your-odoo-instance/sweego/webhook/inbound` | `email_inbound` |

- Messages stay in the Odoo mail queue until Sweego confirms the delivery, instead of being marked as sent as soon as they leave Odoo.

- Sweego [failure events](/docs/webhooks/email_events) are mapped to Odoo's native failure categories, so bounces and rejections show up on the record like any other Odoo delivery error.

- Webhook payloads are verified with their [HMAC-SHA256 signature](/docs/webhooks/webhook_signature), so only genuine Sweego calls are accepted.

- A scheduled action reconciles the statuses if a webhook is ever missed.

### Inbound replies

With [inbound email](/docs/inbound/setup_inbound) enabled, replies from your customers are routed back to the Odoo document they came from (sales order, invoice, helpdesk ticket…) using a signed token embedded in the `Reply-To` address. The connector also detects mail loops to avoid endless auto-reply exchanges.

## SMS

### Configuration

- Go to **Settings > General Settings > SMS**.

- Select **Sweego** as the SMS provider.

- Optionally set the **sender ID** and the **campaign type** (`transactional` or `marketing`).

The provider is chosen per company: in a multi-company database, each company can independently use Sweego or keep Odoo's IAP service. The module plugs into Odoo's native SMS mechanism (`SmsApiBase`), so no third-party OCA module is required, and it stays compatible with `sms_twilio`.

Your remaining Sweego SMS credits are displayed in the General Settings.

Local numbers without an international prefix are sent with the `FR` region code. Store recipient numbers in international format (`+33…`) if your audience is not French.

### Error handling

When a send fails, the SMS is kept in Odoo with an explicit failure type — such as `missing_api_key`, `http_error` or `server_error` — and Sweego errors are mapped to Odoo's native SMS failure categories, so you can retry from the standard Odoo interface.

## Additional Resources

- [Sweego connectors for Odoo (Mangono)](https://mangono.fr/connecteurs-odoo/sweego.html)

- [Mangono Sweego Mail on Odoo Apps](https://apps.odoo.com/apps/modules/19.0/mangono_sweego_mail)

- [Mangono Sweego SMS on Odoo Apps](https://apps.odoo.com/apps/modules/19.0/mangono_sweego_sms)

- [Sweego API Documentation](https://learn.sweego.io)
