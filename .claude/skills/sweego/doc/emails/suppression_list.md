# Suppression List

Source : https://learn.sweego.io/docs/emails/suppression_list

> Sweego automatically blocks sends to invalid addresses to protect your sender reputation.

# Suppression List

Sweego includes a built-in **Suppression List** that protects your sender reputation. When a delivery fails with a *user unknown* hardbounce (the recipient does not exist), the email address is automatically added to the Suppression List for **90 days**.

During that period, any new send to that address is blocked by Sweego **before any delivery attempt to the remote server**. This prevents repeated bounce errors that would damage your reputation with mailbox providers (Gmail, Microsoft, Orange, etc.).

## Why it matters

Repeatedly sending emails to non-existent addresses is one of the strongest negative signals for mailbox providers. Above a certain hardbounce threshold, your legitimate emails may be flagged as spam or blocked entirely. The Suppression List acts as an automatic safety net to prevent this.

## How it works

- You send an email through Sweego (API or SMTP).

- The remote server responds with a permanent *user unknown* error.

- Sweego adds the address to the Suppression List with a 90-day retention period.

- Any subsequent send to that address is blocked for 90 days, without contacting the remote server.

- After 90 days, the address is automatically removed. If it is still invalid, the cycle starts again on the next send attempt.

## Identifying suppressed emails in your logs

When an email is blocked by the Suppression List, you will see an entry like this in your delivery logs:

```
Mar 31 23:00:12 prod-mta-xxx zone-mta: Mar 31 23:00:12 info Queue
19d462032470007092.001 DROP[suppressed] Recipient localpart@domain.com
was found from suppression list
```

Key indicators:

- **`DROP[suppressed]`** — the email was blocked before delivery.

- **`was found from suppression list`** — confirms the block is due to the Suppression List, not another rule.

## Viewing the Suppression List

Viewing your Suppression List from the dashboard or via the API is not yet available. This feature is planned for a future release of Sweego.
