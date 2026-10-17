# Setup

Source : https://learn.sweego.io/docs/webhooks/setup

> To start using webhooks, you will have to set it up!

To start using webhooks, you will have to set it up!

For now, we provide webhook subscription for email sending.

Before getting started, be sure to have endpoints to plug webhooks!

If you just want to test our system, you can freely get one with these sites:

- [webhook.site](https://webhook.site) (Also available as an [open source project](https://docs.webhook.site/open-source.html))

- [Beeceptor](https://beeceptor.com/)

- [Webhook Relay](https://webhookrelay.com/)

- [hook0](https://github.com/hook0/hook0) (open source project)

- ...

Be careful as you can get a limitation on how much data you will be able to receive on some websites.

To access your webhooks, go to your personal settings:

![webhook_settings](undefined)

![webhook_in_settings](undefined)

Click on "Add new webhook"

![webhook_add](undefined)

Give a name to you webhook, add your endpoint and select the desired [events](/docs/webhooks/events) to subscribe.

![webhook_event](undefined)

Attach one or more domains to your webhook.
If you don't specify any domain restriction, your webhook will trigger on all your verified domains.

![webhook_domain](undefined)

In order to receive events, be sure to enable it :

![webhook_activate](undefined)
