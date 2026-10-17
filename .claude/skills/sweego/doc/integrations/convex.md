# Convex Component

Source : https://learn.sweego.io/docs/integrations/convex

> Send transactional email and SMS from Convex using the Sweego component

# Convex Component

The [Sweego Convex component](https://www.convex.dev/components/christian-ek/sweego) lets you send transactional **email and SMS** through Sweego directly from your [Convex](https://www.convex.dev/) backend, with durable workpool delivery, per-recipient webhook tracking, and HMAC-verified events.

It is an open-source community project developed by [Christian Ek](https://github.com/christian-ek) and published on npm as `@christian-ek/sweego`.

## Prerequisites

Before starting, make sure you have:

- A Convex project ([quickstart](https://docs.convex.dev/quickstart))

- A Sweego account with an active API key

- A verified sending domain (or sender) in Sweego

- A Sweego webhook and its signing secret (for delivery tracking)

You can find how to create your Sweego API key in [our guide](/docs/auth/api_keys).

## Installation

Install the component package:

```bash
npm install @christian-ek/sweego
```

## Configuration

### Step 1: Set environment variables

Set your Sweego API key and webhook secret in your Convex deployment:

```bash
npx convex env set SWEEGO_API_KEY swg_xxxxxxxx
npx convex env set SWEEGO_WEBHOOK_SECRET <secret>
```

The webhook secret is provided when you create a webhook in the Sweego dashboard.

### Step 2: Register the component

Add the component in `convex/convex.config.ts`:

```typescript
import { defineApp } from "convex/server";
import sweego from "@christian-ek/sweego/convex.config";

const app = defineApp();
app.use(sweego);

export default app;
```

### Step 3: Initialize the client

Create a Sweego instance in `convex/sweego.ts`:

```typescript
import { components } from "./_generated/api";
import { Sweego } from "@christian-ek/sweego";

export const sweego = new Sweego(components.sweego, {});
```

## Sending Email

```typescript
import { internalMutation } from "./_generated/server";
import { sweego } from "./sweego";

export const sendWelcome = internalMutation({
  handler: async (ctx) => {
    await sweego.sendEmail(ctx, {
      from: "Acme <hello@yourdomain.com>",
      to: "user@example.com",
      subject: "Welcome!",
      text: "Welcome to Acme!",
      html: "<h1>Welcome to Acme</h1>",
    });
  },
});
```

## Sending SMS

```typescript
await sweego.sendSms(ctx, {
  to: "+33600000000",
  region: "FR",
  campaignType: "transac",
  senderId: "Acme",
  text: "Your code is 123456",
});
```

## Features

- **Email and SMS** sending from Convex

- **Durable delivery** via a Convex workpool (automatic retries)

- **Bulk email** with template support and per-recipient personalization

- **SMS** with regional configuration and cost estimation

- **Per-recipient webhook tracking** with HMAC-verified events

## Additional Resources

- [Sweego component on Convex](https://www.convex.dev/components/christian-ek/sweego)

- [Source repository](https://github.com/christian-ek/sweego)

- [Sweego API Documentation](https://learn.sweego.io)
