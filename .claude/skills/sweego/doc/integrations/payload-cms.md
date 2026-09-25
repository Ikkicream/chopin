# Payload CMS Integration

Source : https://learn.sweego.io/docs/integrations/payload-cms

> Send emails from your Payload CMS application using the Sweego email adapter by Zapal Tech

# Payload CMS Integration

[Payload CMS](https://payloadcms.com/) is a modern, code-first headless CMS built with TypeScript and Node.js. The [`@zapal/payload-email-sweego`](https://github.com/zapal-tech/payload-email-sweego) adapter — developed by [Zapal Tech](https://www.zapal.tech/) — allows you to route all Payload transactional emails through the Sweego REST API.

## Prerequisites

Before starting, make sure you have:

- A Payload CMS project (v2 or higher)

- A Sweego account with an active API key

- Node.js and pnpm installed

You can find how to configure your Sweego API key in [our guide](/docs/auth/api_keys).

## Installation

Install the adapter in your Payload project:

```bash
pnpm add @zapal/payload-email-sweego
```

## Configuration

### Step 1: Set your API key

Add your Sweego API key to your environment variables:

```bash
# .env
SWEEGO_API_KEY=your_api_key_here
```

### Step 2: Configure the adapter in Payload

Import and configure the `sweegoAdapter` in your Payload config file:

```typescript
// payload.config.ts
import { buildConfig } from 'payload/config'
import { sweegoAdapter } from '@zapal/payload-email-sweego'

export default buildConfig({
  email: sweegoAdapter({
    defaultFromAddress: 'hello@yourdomain.com',
    defaultFromName: 'Your App Name',
    apiKey: process.env.SWEEGO_API_KEY || '',
  }),
  // ... rest of your Payload config
})
```

That's all the configuration needed. Payload will now route all system emails (password resets, user invitations, etc.) through Sweego.

## How it works

Payload CMS has a native email abstraction layer that any adapter can implement. The `sweegoAdapter` hooks into this layer and translates Payload's email requests into calls to the [Sweego `/send` API endpoint](/docs/sweego/send-send-post), using your API key for authentication.

Make sure the domain used in `defaultFromAddress` is [verified in your Sweego account](/docs/emails/set_up_a_domain). Emails sent from an unverified domain may be rejected.

## Troubleshooting

### Emails not being sent

- Verify that `SWEEGO_API_KEY` is correctly set in your environment

- Check that your sender domain is verified in Sweego

- Review your Payload server logs for error details

### Authentication errors

- Ensure your API key is active and has not expired

- Check that you are passing the key to the adapter via `process.env` and not hardcoding it

## Additional Resources

- [`@zapal/payload-email-sweego` on GitHub](https://github.com/zapal-tech/payload-email-sweego)

- [Zapal Tech](https://www.zapal.tech/)

- [Payload CMS Documentation](https://payloadcms.com/docs)

- [Sweego Dashboard](https://app.sweego.io)
