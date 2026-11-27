# Third-Party Integrations

Source : https://learn.sweego.io/docs/integrations

> Tools and platforms that integrate with Sweego

# Third-Party Integrations

Sweego integrates with various third-party tools and platforms to enhance your email workflow.

## Development Frameworks

### Symfony Mailer & Notifier

Official Symfony components for emails and SMS.

- **Type**: PHP Framework Integration

- **Use Case**: Symfony applications

- [View Documentation](/docs/integrations/symfony-mailer)

### Payload CMS

Send emails from your Payload CMS application using the Sweego REST API.

- **Type**: Node.js / TypeScript CMS Integration

- **Maintainer**: [Zapal Tech](https://www.zapal.tech/) (community)

- **Use Case**: Transactional emails for Payload CMS (password resets, invitations, notifications)

- [View Documentation](/docs/integrations/payload-cms)

### sendr (Gleam)

Send emails from your Gleam applications through Sweego with the community `sendr` library.

- **Type**: Gleam Library

- **Maintainer**: [schutm](https://www.wommm.nl/cv/) (community)

- **Use Case**: Unified email sending from Gleam apps

- [View Documentation](/docs/integrations/sendr-gleam)

## Backend Platforms

### Convex

Send transactional email and SMS from your Convex backend with durable delivery and webhook tracking.

- **Type**: Convex Component

- **Maintainer**: [Christian Ek](https://github.com/christian-ek) (community)

- **Use Case**: Transactional email and SMS from Convex applications

- [View Documentation](/docs/integrations/convex)

## Odoo

### Mangono Sweego Mail

Send your Odoo emails through the Sweego SMTP relay, with delivery tracking and inbound replies routed back to the right Odoo document.

- **Type**: Odoo Module (18.0, 19.0)

- **Maintainer**: [Mangono](https://mangono.fr/connecteurs-odoo/sweego.html) (community)

- **Use Case**: Transactional emails from Odoo, multi-company sending, reply handling

- [View Documentation](/docs/integrations/odoo#email)

### Mangono Sweego SMS

Send your Odoo SMS through the Sweego API instead of Odoo's IAP service.

- **Type**: Odoo Module (18.0, 19.0)

- **Maintainer**: [Mangono](https://mangono.fr/connecteurs-odoo/sweego.html) (community)

- **Use Case**: Transactional and marketing SMS from Odoo, per-company provider selection

- [View Documentation](/docs/integrations/odoo#sms)

## WordPress

### Post SMTP

Send emails from your WordPress site using Sweego.

- **Type**: WordPress Plugin

- **Use Case**: Transactional emails for WordPress

- [View Documentation](/docs/integrations/postsmtp-wordpress)

### Jooosi Mail

Route your WordPress emails through Sweego (API or SMTP) with the Jooosi Mail plugin.

- **Type**: WordPress Plugin

- **Maintainer**: Sua (community)

- **Use Case**: Transactional emails for WordPress, with provider failover and logging

- [View Documentation](/docs/integrations/jooosi-mail)

## Infrastructure as Code

### Terraform Provider

Manage your Sweego domains as code using the community Terraform provider.

- **Type**: Terraform Provider

- **Maintainer**: [j6s](https://github.com/j6s) (community)

- **Use Case**: Automated domain provisioning and DNS record management

- [View Documentation](/docs/integrations/terraform)

## Monitoring & Alerting

### Mailfox

Get instant notifications when your transactional emails fail to deliver.

- **Type**: Email Monitoring & Alerting

- **Use Case**: Real-time failure notifications

- [Setup Guide](https://www.mailfox.dev/guides/sweego/)

- **Features**:
  
  
  
  - Real-time webhook notifications for failed emails
  
  - No-code setup via webhooks
  
  - Immediate alerts for delivery issues
  
  - Works alongside your existing Sweego webhooks

### SenderAudit

Pull your Sweego sending statistics into SenderAudit to follow them alongside your deliverability and DMARC monitoring.

- **Type**: Deliverability Monitoring

- **Use Case**: Centralized view of sending performance and domain reputation

- [SenderAudit](https://senderaudit.com/)

- **Features**:
  
  
  
  - Sweego sending statistics imported into SenderAudit
  
  - Sending performance reviewed next to authentication and blocklist checks
  
  - DMARC and TLS-RPT aggregate report monitoring for your sending domains

---

**Built an integration with Sweego?**

We'd love to feature it here. [Contact our team](https://www.sweego.io/contact-us) to discuss listing your integration.
