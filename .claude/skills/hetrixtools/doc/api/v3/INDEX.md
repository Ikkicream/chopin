# HetrixTools API v3 — index des endpoints

> Source : https://docs.hetrixtools.com/api/v3/ (spec : https://docs.hetrixtools.com/api/v3/api.yaml?v=170)  
> Généré le 2026-09-26 depuis la spec OpenAPI officielle (fichier brut : `api.yaml`).

Base URL : `https://api.hetrixtools.com/v3/` — Auth : `Authorization: Bearer <API_KEY>`

| Méthode | Chemin | Titre | Fichier |
|---|---|---|---|
| GET | `/ping` | Ping | `get_ping.md` |
| GET | `/account/api/scope` | API Scope | `get_account_api_scope.md` |
| GET | `/account/limits` | Account Limits | `get_account_limits.md` |
| GET | `/account/activity-log` | Activity Log | `get_account_activity-log.md` |
| GET | `/contact-lists` | Contact Lists | `get_contact-lists.md` |
| GET | `/blacklists` | Blacklists | `get_blacklists.md` |
| GET | `/blacklist-monitors` | Blacklist Monitors | `get_blacklist-monitors.md` |
| GET | `/blacklist-monitors/{identifier}/report` | Blacklist Report | `get_blacklist-monitors_identifier_report.md` |
| GET | `/uptime-monitors` | Uptime Monitors | `get_uptime-monitors.md` |
| GET | `/uptime-monitors/{monitor_id}/report` | Uptime Report | `get_uptime-monitors_monitor_id_report.md` |
| GET | `/uptime-monitors/{monitor_id}/downtimes` | Downtimes | `get_uptime-monitors_monitor_id_downtimes.md` |
| GET | `/uptime-monitors/{monitor_id}/location-fail-log` | Location Fail Log | `get_uptime-monitors_monitor_id_location-fail-log.md` |
| GET | `/uptime-monitors/{monitor_id}/network-diagnostics` | Network Diagnostics | `get_uptime-monitors_monitor_id_network-diagnostics.md` |
| GET | `/uptime-monitors/{monitor_id}/web-snapshot` | Web Snapshot | `get_uptime-monitors_monitor_id_web-snapshot.md` |
| GET | `/uptime-monitors/{monitor_id}/private-notes` | Private Notes | `get_uptime-monitors_monitor_id_private-notes.md` |
| POST | `/uptime-monitors/{monitor_id}/private-notes` | Private Notes | `post_uptime-monitors_monitor_id_private-notes.md` |
| PUT | `/uptime-monitors/{monitor_id}/private-notes` | Private Notes | `put_uptime-monitors_monitor_id_private-notes.md` |
| DELETE | `/uptime-monitors/{monitor_id}/private-notes` | Private Notes | `delete_uptime-monitors_monitor_id_private-notes.md` |
| GET | `/uptime-monitors/{monitor_id}/server-agent` | Server Agent ID | `get_uptime-monitors_monitor_id_server-agent.md` |
| POST | `/uptime-monitors/{monitor_id}/server-agent` | Server Agent ID | `post_uptime-monitors_monitor_id_server-agent.md` |
| DELETE | `/uptime-monitors/{monitor_id}/server-agent` | Server Agent ID | `delete_uptime-monitors_monitor_id_server-agent.md` |
| GET | `/uptime-monitors/{monitor_id}/server-agent/metrics` | Server Agent Metrics | `get_uptime-monitors_monitor_id_server-agent_metrics.md` |
| GET | `/uptime-monitors/{monitor_id}/server-agent/processes` | Running Processes | `get_uptime-monitors_monitor_id_server-agent_processes.md` |
| GET | `/uptime-monitors/{monitor_id}/server-agent/warning-policies` | Warning Policies | `get_uptime-monitors_monitor_id_server-agent_warning-policies.md` |
| PUT | `/uptime-monitors/{monitor_id}/server-agent/warning-policies` | Warning Policies | `put_uptime-monitors_monitor_id_server-agent_warning-policies.md` |
| GET | `/status-pages` | Status Pages | `get_status-pages.md` |
| POST | `/status-pages/{status_page_id}/monitors` | Status Pages - Monitors | `post_status-pages_status_page_id_monitors.md` |
| DELETE | `/status-pages/{status_page_id}/monitors` | Status Pages - Monitors | `delete_status-pages_status_page_id_monitors.md` |
| PUT | `/uptime-monitors/{monitor_id}/maintenance` | Maintenance Mode | `put_uptime-monitors_monitor_id_maintenance.md` |
| GET | `/schedule-maintenance` | Schedule Maintenance | `get_schedule-maintenance.md` |
| POST | `/schedule-maintenance` | Schedule Maintenance | `post_schedule-maintenance.md` |
| DELETE | `/schedule-maintenance/{id}` | Schedule Maintenance | `delete_schedule-maintenance_id.md` |

Voir aussi `_intro.md` (codes HTTP, limites de débit, auth).
