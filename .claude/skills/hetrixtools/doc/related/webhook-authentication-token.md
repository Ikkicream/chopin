# Webhook Authentication Token

> Source : https://docs.hetrixtools.com/webhook-authentication-token/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2022-05-13, modifié 2022-05-13

Here’s how to configure and use the authentication token that you may optionally configure along with our notification webhooks.

The webhook authentication token is configured in the same place where you configure the webhook notification URL in your [Contact Lists](https://docs.hetrixtools.com/create-a-contact-list/).

[![](https://docs.hetrixtools.com/wp-content/uploads/2022/05/image.png)](https://docs.hetrixtools.com/wp-content/uploads/2022/05/image.png)

This token will be sent in the `Authorization` header along with every webhook payload, in the following format:

`Authorization: Bearer <token>`

Your webhook script can then use this token in order to authenticate the incoming webhook.
