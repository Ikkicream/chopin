# Schedule maintenance based on emails

> Source : https://docs.hetrixtools.com/schedule-maintenance-based-on-emails/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2026-09-21, modifié 2026-09-21

## The Problem

We sometimes get these emails, as in the example below, from different hosting providers that we work with, announcing a scheduled maintenance.

[![](https://docs.hetrixtools.com/wp-content/uploads/2026/09/32423363.png)](https://docs.hetrixtools.com/wp-content/uploads/2026/09/32423363.png)

Now, these are non-critical servers in our infrastructure, so we don’t mind the occasional interruptions, but we don’t want to be notified of these outages either.

A manual solution would be to look up all these nodes in our HetrixTools dashboard and [schedule maintenance windows](https://docs.hetrixtools.com/schedule-maintenance/) for each one. Not so time-efficient.

## The MCP Solution

Just ask your favorite AI to do it for you.

[![](https://docs.hetrixtools.com/wp-content/uploads/2026/09/2353453-668x1024.png)](https://docs.hetrixtools.com/wp-content/uploads/2026/09/2353453.png)

Not only did it find all affected monitors in the first go, but it also found the 8 IPv6 untagged uptime monitors as well.

It also made all the right decisions without being told to, such as scheduling the [maintenance mode](https://docs.hetrixtools.com/maintenance-mode/) without notifications, and 30 minutes should be more than enough for a VM reboot.
