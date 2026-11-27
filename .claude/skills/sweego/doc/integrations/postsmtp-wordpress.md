# Post SMTP Integration

Source : https://learn.sweego.io/docs/integrations/postsmtp-wordpress

> Configure Sweego as your email provider in WordPress using Post SMTP plugin

# Post SMTP Integration

Post SMTP is one of the most popular WordPress email plugins with over 400,000 active installations. Sweego is fully integrated with Post SMTP, allowing you to configure it as your transactional email provider directly from your WordPress admin panel.

## Prerequisites

Before starting, make sure you have:

- A WordPress website with admin access

- A Sweego account with an active API key

- The Post SMTP plugin installed (version 3.8.0 or higher)

You can find how to configure your Sweego API key in [our guide](/docs/auth/api_keys).

## Configuration Guide

### Step 1: Choose Sweego as Your Mailer

- In your WordPress admin panel, go to **Post SMTP > Setup Wizard**

- On the "Choose your SMTP Mailer" screen, select **Sweego** from the available providers

- Click **Continue**

![Choose Sweego in Post SMTP](undefined)

### Step 2: Configure Mailer Settings

- **From Email**: Enter the email address you want to use as sender (e.g., `hello@domain.io`)

- **From Name**: Enter the sender name that will appear in emails (e.g., `John Doe`)

- **API Key**: Paste your Sweego API key from your dashboard

You can optionally enable the toggle switches to prevent other plugins or themes from overriding these settings.

![Configure Sweego settings](undefined)

- Click **Save and Continue**

### Step 3: Send a Test Email

- Enter a **recipient email address** where you want to receive the test email

- Click **Send Test Email**

- Post SMTP will attempt to send a test message through Sweego

If everything is configured correctly, you'll see a success message:

**Your message was delivered (252 ms) to the SMTP server! Congratulations :)**

![Test email success](undefined)

If the test fails, verify that:

- Your API key is correct and active

- Your sender email address is verified in Sweego

- Your WordPress server can make outbound HTTPS requests

- Click **Finish**

### Step 4: Configuration Complete

Your WordPress is now configured to send all emails through Sweego.

![Configuration complete](undefined)

## Post SMTP Features

### Dashboard Overview

The Post SMTP dashboard provides at-a-glance statistics:

- **Total Emails**: Number of emails sent during the selected period

- **Successful Emails**: Successfully delivered messages

- **Failed Emails**: Messages that encountered delivery issues

- **Recent Logs**: Quick view of the latest email activity

![Post SMTP Dashboard](undefined)

### Email Logs

Post SMTP maintains detailed logs of all emails sent from your WordPress:

- **Subject**: Email subject line

- **Sent To**: Recipient email address

- **Delivery Time**: Timestamp of when the email was sent

- **Status**: Delivery status (Success/Failed)

- **Actions**: View full details, resend, view transcript, or delete

![Post SMTP Logs](undefined)

The logs page allows you to:

- Filter by date range

- Search by subject or recipient

- Filter by status (All logs, Success, Failed)

- Export logs for analysis

- Resend failed emails with one click

- View detailed error messages for failed deliveries

### Mobile Application

Monitor your emails on the go with the Post SMTP mobile app (available on Android and iOS):

- View recent emails

- Check delivery status

- Get push notifications for errors

## Additional Resources

- [Post SMTP Official Documentation](https://postmansmtp.com/docs/)

- [Post SMTP WordPress Plugin](https://wordpress.org/plugins/post-smtp/)

- [Sweego API Documentation](https://docs.sweego.io)

- [Sweego Dashboard](https://app.sweego.io)
