# Email events

Source : https://learn.sweego.io/docs/webhooks/email_events

> Webhook gives you the power to monitor events by assigning event types to url endpoints

Webhook gives you the power to monitor events by assigning event types to url endpoints

It is necessary to have at least one event

## Events

### Email

- Sent

- Delivered

- Soft Bounce

- Hard Bounce

- List-unsubscribe

- Spam-complaints

- Proxy open (tracking)

- Human open (tracking)

- Click (tracking)

In addition to these events, you will at least need to specify at least one domain (you can also plug the webhook to multiple domains)

On webhook settings page, you will be able to see trigger sending detail (success / failures)
![webhook_count](undefined)

## Delivery delay

Most email webhook events are delivered **instantly**.

The following tracking events have a delay of up to **10 minutes** before being dispatched, due to the ETL processing pipeline that ensures data consistency:

- Proxy open

- Human open

- Click

If you have any questions about these events, don't hesitate to get in touch with us!

---

#### Related

🔗 [More details about Statistics & Events](/docs/statistics)
