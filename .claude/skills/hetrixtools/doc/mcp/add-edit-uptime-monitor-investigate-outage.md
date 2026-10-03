# Add/edit uptime monitor & investigate outage

> Source : https://docs.hetrixtools.com/add-edit-uptime-monitor-investigate-outage/  
> Aspiré le 2026-09-26 (WordPress REST, contenu intégral) — publié 2026-09-21, modifié 2026-09-22

In the example below, we’re asking Claude to add a new Uptime Monitor with a given keyword for it to look for, as part of our [Keyword Monitoring](https://docs.hetrixtools.com/how-to-set-up-keyword-monitoring/).

Then, once the Uptime Monitor is detected as online/healthy, we’ll ask it to change that monitored keyword to a missing one, thus causing an outage for our monitor.

The AI is asked to investigate the outage, and it correctly provides all of the info, including the links to the captured [WebSnapshot](https://docs.hetrixtools.com/uptime-monitoring-websnapshots/), which contain the captured page HTML content and screenshot from during the outage.

[![](https://docs.hetrixtools.com/wp-content/uploads/2026/09/43653243-450x1024.png)](https://docs.hetrixtools.com/wp-content/uploads/2026/09/43653243.png)
