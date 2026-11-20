# Jooosi Mail Integration

Source : https://learn.sweego.io/docs/integrations/jooosi-mail

> Send WordPress emails through Sweego using the Jooosi Mail plugin

# Jooosi Mail Integration

[Jooosi Mail](https://wordpress.org/plugins/jooosi-mail/) is a modern email sending plugin for WordPress. It intercepts the standard `wp_mail()` function and routes your outgoing emails through the provider of your choice. It supports 40+ providers, including **Sweego** — over both **API** and **SMTP**, with webhook feedback for delivery tracking.

## Prerequisites

Before starting, make sure you have:

- A WordPress website with admin access (WordPress 7.0 or higher, PHP 8.3 or higher)

- A Sweego account with an active API key

- A verified sending domain (or sender) in Sweego

You can find how to create your Sweego API key in [our guide](/docs/auth/api_keys).

## Installation

Install Jooosi Mail like any other WordPress plugin:

- In your WordPress admin panel, go to **Plugins > Add New**

- Search for **Jooosi Mail**, then click **Install Now** and **Activate**

Alternatively, upload the plugin files to the `/wp-content/plugins/jooosi-mail` directory and activate it from the **Plugins** menu.

## Configuration

- In your WordPress admin panel, open **Jooosi Mail**

- Add a new **sending connection** and select **Sweego** as the provider

- Choose the connection type:
  
  
  
  - **API** — paste your Sweego API key
  
  - **SMTP** — use your Sweego SMTP credentials

- Set your **From email** and **From name** (the sender must be authorized in Sweego)

- Save the connection and send a **test email** to confirm delivery

If the test fails, verify that:

- Your API key (or SMTP credentials) are correct and active

- Your sender email address / domain is verified in Sweego

- Your WordPress server can make outbound HTTPS requests

## Features

- **Multiple providers** — Sweego and 40+ other services, over API or SMTP

- **Provider failover** — automatically fall back to another connection if a send fails

- **Queue-based delivery** — outgoing emails are queued and processed with Action Scheduler

- **Email logging** — track sent, queued, and failed messages from the WordPress admin

- **Webhook feedback** — receive delivery status back into WordPress

- **WP-CLI support** — manage the plugin from the command line

## Additional Resources

- [Jooosi Mail on WordPress.org](https://wordpress.org/plugins/jooosi-mail/)

- [Sweego API Documentation](https://learn.sweego.io)

- [Sweego Dashboard](https://app.sweego.io)
