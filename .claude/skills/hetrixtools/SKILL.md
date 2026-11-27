---
name: hetrixtools
description: Base de connaissance HetrixTools (monitoring d'uptime, agent serveur CPU/RAM/disque, blacklists, webhooks, MCP) — doc officielle API v1/v2/v3 et MCP en local + synthèse pour afficher des badges OK/KO par service sur la home Genesis/Cheffer. À lire AVANT tout code, appel ou affirmation touchant HetrixTools (api.hetrixtools.com, HETRIXTOOLS_API_KEY, agent serveur, webhook d'alerte, statut UP/DOWN des services).
---

# HetrixTools — base de connaissance

Doc aspirée le **2026-09-26** depuis https://docs.hetrixtools.com (API WordPress REST = contenu intégral des
pages, pas un résumé) + la **spec OpenAPI officielle v3** (`api.yaml?v=170`) + les pages de tarifs publiques.
**Aucun appel authentifié n'a été fait** : pas de clé sur le serveur au moment de l'écriture.

| Où | Quoi |
| --- | --- |
| `doc/api/*.md` | Les 19 pages de la catégorie « 15 API » + 4 pages API rangées ailleurs (scope des clés, API calls vs checks, agent v2, Moscou→Varsovie) |
| `doc/api/v3/INDEX.md` | Les **32 opérations v3** (méthode, chemin, fichier) ; `_intro.md` = codes HTTP, limites, auth |
| `doc/api/v3/<methode>_<chemin>.md` | Chaque opération : paramètres, corps, champs de réponse (tableau), exemples JSON, erreurs |
| `doc/api/v3/api.yaml` | La spec OpenAPI brute (source de vérité, 5 376 lignes) |
| `doc/mcp/*.md` | Les 10 pages de la catégorie « 16 MCP » (4 cas d'usage + 6 exemples) |
| `doc/related/*.md` | Webhooks (uptime, agent serveur, blacklist, jeton d'auth), IP des sondes, Location Fail Log, Network Diagnostics, upgrade |
| `doc/tarifs/*.md` | Grilles publiques Uptime Monitor et Blacklist Monitor (✓/✗ reconstitués depuis le HTML) |
| `ui/status-badge.md` | Composant badge 21st.dev (code réel + adaptation Cheffer) ; `ui/preview.png`, `ui/source/` |
| `outils/` | Scripts de ré-aspiration (voir en bas) |

**Règle** : on cite le fichier `doc/...` pour toute affirmation. Si la doc ne dit rien, on écrit
« non documenté » et on le vérifie avec un appel en lecture une fois la clé posée — jamais de supposition.

---

## 1. Vue d'ensemble

HetrixTools teste des cibles depuis 12 villes (New York, San Francisco, Dallas, Amsterdam, Londres, Francfort,
Singapour, Sydney, São Paulo, Tokyo, Mumbai, Varsovie). Un **uptime monitor** peut être de type
`website` (HTTP, mot-clé, codes acceptés, SSL), `ping`, `service` (port TCP), `smtp` ou `heartbeat`
(agent serveur ou tâche cron qui « pingue »). Un agent serveur (Linux/Windows/macOS/PHP) s'attache à un
uptime monitor et remonte CPU, RAM, disque, réseau, services, RAID, santé des disques, chaque minute.

Trois générations d'API coexistent (`doc/api/understanding-our-apis.md`) :

| | v3 (à utiliser) | v1 / v2 (anciennes) |
| --- | --- | --- |
| Style | REST, `https://api.hetrixtools.com/v3/...` | URL avec la clé dedans : `https://api.hetrixtools.com/v1/<API_TOKEN>/...` |
| Auth | en-tête `Authorization: Bearer <clé>` | clé dans le chemin (fuite dans les logs !) |
| Quota | **pas de plafond mensuel**, limite par minute | **plafond mensuel selon l'offre** + 120 req/min toutes v1/v2 confondues |
| Doc | Redoc https://docs.hetrixtools.com/api/v3/ | pages `doc/api/*.md` + API Explorer (tableau de bord, connecté) |

➡️ **Pour Genesis/Cheffer : v3 uniquement.** v1/v2 seulement pour ce que v3 n'a pas (création/suppression
d'uptime monitor, blacklist add/edit/delete, blacklist check à la demande).

## 2. Authentification

- Clé créée dans le tableau de bord : https://hetrixtools.com/dashboard/account/api/ (`doc/api/api-key.md`).
  Plusieurs clés possibles (nombre selon l'offre), régénérables, annotables, compteur d'appels mensuel par clé.
- v3 : `curl -H "Authorization: Bearer $HETRIXTOOLS_API_KEY" https://api.hetrixtools.com/v3/ping`
  → `{"status":"ok","message":"pong"}` (`doc/api/v3/get_ping.md`).
- **Où la ranger** : `HETRIXTOOLS_API_KEY=` dans `/home/autoblog/genesis/.env` (absente au 2026-09-26 —
  ne pas l'inventer, Camille la crée). Ne jamais la mettre dans genesis-ui côté navigateur, ni en `NEXT_PUBLIC_*`.
- **Scope** (`doc/api/api-key-scope.md`) : une clé est « Full Access » par défaut. La restreindre à des appels
  précis ET à des assets précis (ex. 5 uptime monitors). Pour la home : une clé dédiée limitée à
  `v3 GET Uptime Monitors`, `v3 GET Uptime Report`, `v3 GET Downtimes`, `v3 GET Server Agent Metrics`
  (lecture seule). `GET /v3/account/api/scope` marche avec n'importe quelle clé et dit ce qu'elle peut faire.
- Relais si Cloudflare bloque notre IP : remplacer `https://api.hetrixtools.com/` par
  `https://relay.hetrixtools.com/api/` (`doc/api/using-the-api-relay.md`).

## 3. Limites de débit et quota

Source : `doc/api/v3/_intro.md`, `doc/api/understanding-api-limits.md`, `doc/tarifs/pricing-uptime-monitor.md`.

- **v3** : deux limites, **par utilisateur** (par minute ou par heure) et **par endpoint** (certains endpoints).
  Dépassement → `429 {"status":"too_many_requests","message":"user api rate limit exceeded"}`.
  En-têtes à lire à chaque réponse : `ratelimit-limit-user`, `ratelimit-remaining-user`, `ratelimit-reset-user`
  (et `-endpoint`). **Le chiffre exact n'est publié nulle part** : les exemples montrent 200 (user) et 100
  (endpoint), ce ne sont que des exemples. → Lire les en-têtes au premier appel et noter la vraie valeur ici.
- **v1/v2** : 120 req/min toutes confondues + plafond mensuel : Free 1 000, **Professional 10 000**,
  Business 20 000, Enterprise 50 000 (remis à zéro le 1er du mois). `GET /v3/account/limits` donne
  `api_v1_v2.usage/limit`.
- Blacklist check à la demande : crédits séparés (« API Checks »), 1 crédit par check non caché,
  résultat caché 30 min, extra à 6 $ / 1 000 (`doc/api/blacklist-check-credits.md`).

## 4. Ce que couvre l'offre à 9,95 $/mois

Il y a **deux** offres à 9,95 $ : « Professional » (Uptime Monitor) et « Personal » (Blacklist Monitor).
Pour du monitoring d'uptime/serveurs, c'est **Uptime Monitor — Professional** (`doc/tarifs/pricing-uptime-monitor.md`) :

| Élément | Professional 9,95 $/mois | (Free, pour comparer) |
| --- | --- | --- |
| Uptime monitors | **30** | 15 |
| Server monitors (agent) | **30** (1 agent par uptime monitor, inclus sans surcoût) | 15 |
| Fréquence de test | **1 minute** | 1 minute |
| Emplacements de test | **6 au choix sur 12** | 4 |
| Historique des rapports | illimité | illimité |
| API v3 | ✓, sans plafond mensuel | ✓ |
| API v1/v2 | 10 000 appels/mois | 1 000 |
| Webhooks, Telegram, Slack, Discord, e-mail… | ✓ | ✓ |
| Destinataires e-mail multiples | ✓ | ✗ (son propre e-mail seulement) |
| SMS/appel inclus | 25 crédits/mois (puis 0,10 $) | ✗ |
| Sous-comptes | 1 | ✗ |
| Journal d'activité | 30 jours | 15 jours |
| Status pages publiques | illimitées ; marque blanche partielle, 5 domaines | idem, 3 domaines |
| Exigence d'activité | aucune | ✗ (le Free exige de l'activité) |

Annuel = « 2 mois offerts ». Monitors supplémentaires achetables au même tarif unitaire.

## 5. Endpoints utiles pour savoir si un service est UP/DOWN

Tous en `GET https://api.hetrixtools.com/v3...` avec `Authorization: Bearer`. Détails : `doc/api/v3/`.

| Besoin | Endpoint | Champs clés |
| --- | --- | --- |
| **Liste + statut de tous les moniteurs** (1 appel) | `/uptime-monitors?per_page=200` | `uptime_status` (`up`/`down`), `monitor_status` (`active`/`paused`/`disabled`/`maint`/`maint_dnd`), `last_check`, `last_status_change` (= « depuis quand »), `uptime` (%), `locations.<ville>.{uptime_status,response_time ms,last_check}`, `ssl_expiration_date`, `domain_expiration_date`, `has_agent` |
| Filtrer | mêmes, `?uptime_status=down`, `?monitor_status=active`, `?type=website`, `?name=`, `?category=`, `?id=` | |
| Uptime 1–30 jours + temps de réponse | `/uptime-monitors/{id}/report?days=30` (ou `month=YYYY-MM`, `timezone=+02:00`, `hourly_stats=true`) | `data.<jour>.uptime.percentage`, `data.<jour>.response_time.<ville>` (moyenne ms), `summary.uptime.percentage`, `summary.uptime.downtimes`, `history.<mois>` |
| Pannes (dernier incident) | `/uptime-monitors/{id}/downtimes?start_after=<ts>&per_page=200` | `id`, `start`, `end`, `maintenance` |
| Pourquoi ça a planté | `/uptime-monitors/{id}/location-fail-log?minutes=10` | `entries[].{timestamp, location "London 6", data "Error 28: Connection timed out…"}` |
| Ping + MTR de la panne | `/uptime-monitors/{id}/network-diagnostics?downtime_id=` | `entries[].{location, ping, mtr}` (texte HTML-échappé) |
| Capture de la page en panne | `/uptime-monitors/{id}/web-snapshot?downtime_id=` | `web_snapshot.{http_code, screenshot_url, content_url}` ou `null` |
| **Serveur : CPU, RAM, disque** | `/uptime-monitors/{id}/server-agent/metrics` | `meta.last_updated` (dernier envoi de l'agent), `system.{os,uptime,reboot_required}`, `disk.disks[].usage_percent`, `services[].status`, `stats[]` (60 derniers points, du plus récent au plus ancien : `cpu`, `ram`, `disk`, `load_1`, `iowait`, `net_in/out`) ; historique `?from=&to=&interval=1m/1h/1d` |
| Processus | `/uptime-monitors/{id}/server-agent/processes` | |
| Seuils d'alerte agent | `/uptime-monitors/{id}/server-agent/warning-policies` (GET/PUT) | `cpu_usage_warn`, `ram_usage_warn`, `agent_data_warn`… |
| Blacklists (IP/domaines d'envoi) | `/blacklist-monitors?listed=true`, `/blacklist-monitors/{id}/report` | `listed[].{rbl, delist}`, `last_check` |
| Compte | `/account/limits`, `/account/api/scope`, `/account/activity-log` | usage vs limite des moniteurs, SMS, v1/v2 |
| Maintenance | `PUT /uptime-monitors/{id}/maintenance {"enabled":true}`, `GET/POST/DELETE /schedule-maintenance` | `monitor_status` → `maint_dnd` / `maint` |

Exemple de réponse de `GET /v3/uptime-monitors` (extrait de la spec) :

```json
{
  "monitors": [{
    "id": "e34334dt5t755b034606y54ccabe62e8", "name": "Uptime Monitor Name", "type": "website",
    "target": "http://demo-website.com", "category": "My Websites", "check_frequency": 1,
    "last_check": 1641832650, "last_status_change": 1641367229,
    "uptime_status": "up", "monitor_status": "active", "uptime": 99.9588, "uptime_incl_maint": 99.9588,
    "locations": {
      "new_york": {"uptime_status": "up", "response_time": 74, "last_check": 1641832627},
      "amsterdam": {"uptime_status": "up", "response_time": 227, "last_check": 1641832635}
    },
    "ssl_expiration_date": "2022-03-06", "domain_expiration_date": "2022-05-10", "has_agent": true
  }],
  "meta": {"total": 202, "total_filtered": 2, "returned": 2,
           "pagination": {"current": 1, "last": 1, "previous": null, "next": null}}
}
```

Rapport (`/report`) : `{"timezone":"UTC+02:00","data":{"2025-02-24":{"uptime":{"percentage":81.9444,"downtimes":3,…},"response_time":{"frankfurt":131.74}}},"summary":{…},"history":{"2025-02":{…}}}`.

v1/v2 (hors v3) : `v2 Add Uptime Monitor` `POST /v2/<clé>/uptime/add/`, `v2 Delete Uptime Monitor`,
`v2 Uptime Maintenance Mode`, `v2 Add/Edit/Delete Blacklist Monitor`, `v2 Blacklist Check IPv4/Domain`,
`v1 Get Server Agent ID` — voir `doc/api/`. « v1 List Uptime Monitors », « v1 Uptime Report »,
« v1 API Status » ne sont décrits que dans l'API Explorer (connecté) : non aspirés.

## 6. Codes d'erreur

v3 (`doc/api/v3/_intro.md`) — corps `{"status": "<code>", "message": "..."}` :

| HTTP | `status` | Sens |
| --- | --- | --- |
| 200 | — | OK |
| 204 | — | OK mais rien à renvoyer |
| 400 | `bad_request` | requête invalide (`"invalid endpoint"`, paramètre hors bornes, `downtime_id` d'un autre moniteur…) |
| 401 | `unauthorized` | clé absente/invalide (`"invalid authorization"`) — **aussi renvoyé pour un chemin v3 inexistant** |
| 403 | `forbidden` | la clé n'a pas le droit (scope) |
| 404 | `not_found` | ressource inconnue |
| 409 | `conflict` | ex. maintenance sur un moniteur `paused`/`disabled` |
| 429 | `too_many_requests` | limite de débit |
| 5xx | `internal_server_error` / `service_unavailable` | réessayer plus tard |

v1/v2 : HTTP 200 avec `{"status":"ERROR","error_message":"..."}` (ex. `monitor id does not exist`,
`maximum number of monitors has been reached`, `no blacklist check credits`) ; succès `{"status":"SUCCESS",…}`.

## 7. Webhooks et alertes

Les alertes se branchent sur une **Contact List** (e-mail, SMS, appel, Telegram, Slack, Discord, Teams,
Google Chat, PagerDuty, Opsgenie, ntfy, Pushover, Jira, webhook…). Webhook (`doc/related/`) :

- **Uptime** — POST JSON à chaque changement d'état :
  ```json
  {"monitor_id":"…32 car.","monitor_name":"Test Monitor Label","monitor_target":"http://this-is-a-test.com/",
   "monitor_type":"website","monitor_category":"Test Category","monitor_status":"offline","timestamp":1499666192,
   "monitor_errors":{"New York":"http code 403","Dallas":"timeout","Tokyo":"keyword not found"}}
  ```
  `monitor_status` = `online` / `offline` ; `monitor_type` = `website`, `ping`, `service[port]`, `smtp[port]` ;
  `monitor_errors` seulement si `offline` (website : `timeout`, `keyword not found`, `http code XXX` ;
  ping/service : `timeout` ; smtp : `connection failed`, `ssl failed`, `auth failed`).
- **Agent serveur** — `resource_usage.resource_type` = `cpu`/`ram`/`disk`/`network_inbound`/`network_outbound`
  (avec `current_usage`, `average_usage`, `average_minutes` en chaînes) ou `agent` (`"error":"no data"`),
  `drive health`, `raid`, `service` (`error` = liste des services tombés).
- **Blacklist** — voir `doc/related/blacklist-monitoring-webhook-notifications.md`.
- **Authentification** : jeton optionnel configuré avec l'URL → reçu en `Authorization: Bearer <token>`.
- **IP d'émission** : celles de Cloudflare (https://www.cloudflare.com/ips/), pas une liste HetrixTools.

## 8. Serveur MCP

Ce que dit la doc publique (`doc/mcp/`, pages publiées du 21 au 25/09/2026) : HetrixTools a un **MCP officiel**
(affiché « HetrixTools - 0.5.0 integration » dans Claude), utilisé depuis **Claude, ChatGPT Codex et Grok**.
Il s'authentifie par **une clé API HetrixTools** (la capture « Review Account Activity » parle de « la clé
notée "MCP" ») et **respecte le scope de la clé** : une clé restreinte limite l'IA.

Capacités vues dans les cas d'usage (liste **déduite des captures**, les noms d'outils ne sont pas publiés) :
lister les moniteurs et leur statut, pannes + Location Fail Log + Network Diagnostics (MTR) + Web Snapshot,
métriques de l'agent (OS, CPU, RAM, disque, services), journal d'activité, notes privées (étiquetage),
mode maintenance et maintenances planifiées, **ajout/modification d'uptime monitor**.

**Non documenté publiquement : l'URL du serveur MCP et la procédure de branchement.** Aucune page de
docs.hetrixtools.com ne les donne ; hetrixtools.com/mcp répond 403 aux robots ; `https://api.hetrixtools.com/v3/mcp`
répond 401 mais comme n'importe quel chemin v3 inexistant (donc rien de prouvé). Probablement indiqué dans
le tableau de bord une fois connecté (page API Keys). Quand Camille aura l'URL :

```bash
# Modèle Claude Code — URL À CONFIRMER dans le tableau de bord, en-tête supposé identique à l'API v3
claude mcp add --transport http hetrixtools <URL_MCP_OFFICIELLE> \
  --header "Authorization: Bearer ${HETRIXTOOLS_API_KEY}"
claude mcp list
```

Recommandation : une **clé dédiée « MCP »**, en lecture seule au départ (les exemples officiels montrent l'IA
planifier des maintenances et modifier des moniteurs toute seule).

Alternatives trouvées, **à ne pas utiliser sans audit** :
- `github.com/khrns-r/hetrixmcp` : MCP communautaire Python/FastMCP, stdio, 20 outils sur l'API v3
  (`list_uptime_monitors`, `get_uptime_report`, `list_downtimes`, `get_location_fail_log`, `get_server_agent`…),
  variable `HETRIXTOOLS_API_TOKEN` ; créé le 14/07/2026, 0 étoile.
- Vinkius (`edge.vinkius.com/<token>/mcp`) : **proxy tiers** — la clé transiterait chez eux. Non.

## 9. Pièges

1. **`api.hetrixtools.com` est derrière Cloudflare** : une IP à mauvaise réputation peut être bloquée → relais
   `relay.hetrixtools.com/api/`.
2. **Chemin v3 inconnu = 401, pas 404** : une faute de frappe dans l'URL ressemble à une clé invalide.
3. **Deux formats d'erreur** : v3 `{"status":"forbidden","message":…}` avec le vrai code HTTP ; v1/v2
   `{"status":"ERROR","error_message":…}` en HTTP 200. La page « API Key Scope » montre même le format v1
   pour une clé restreinte : tester les deux.
4. **v1/v2 met la clé dans l'URL** → elle finit dans les logs (PM2, nginx, Sentry). Préférer v3.
5. **Types trompeurs dans la spec** : `uptime` déclaré `string` mais l'exemple est un nombre ; `locations`
   déclaré « array » mais c'est un **objet indexé par ville** ; la description liste encore `moscow`
   (remplacé par `warsaw` en 2022, changement non rétrocompatible). Parser défensivement (`Number()`, clés inconnues tolérées).
6. **`locations` vaut `null`** pour les heartbeat (agent/cron) et `check_frequency` aussi.
7. **`uptime_status` est l'état global** ; une ville peut être `down` pendant que le global est `up`
   (le basculement exige `triggering_locations` villes, ≥ 50 %+1). Ne pas afficher KO sur une seule ville.
8. **Maintenance ≠ OK** : `monitor_status` `maint`/`maint_dnd` avec `uptime_status` `down` possible.
   Deux pourcentages : `uptime` (hors maintenance) et `uptime_incl_maint`.
9. **`has_agent=true` ne prouve pas que l'agent tourne** : regarder `meta.last_updated` des métriques
   (agent muet = plus de données, pas forcément une panne).
10. **`/report?days=1` = le jour calendaire en cours** dans le fuseau demandé (défaut UTC), pas 24 h
    glissantes. Pour Paris, passer `timezone=+02:00` (été) / `+01:00` (hiver).
11. **Ordre de `/downtimes` non documenté**, ni la valeur de `end` pour une panne en cours : filtrer avec
    `start_after` puis trier soi-même par `start` ; vérifier le cas « en cours » sur un vrai appel.
12. **Historique minute de l'agent limité à 30 jours** ; `interval=1m` explicite au-delà → 400 ; buckets en
    fuseau `America/New_York`.
13. **Les URL de Web Snapshot expirent chaque jour** (clé d'accès quotidienne) : ne pas les stocker.
14. **Sondes HetrixTools et verrou d'origine Cheffer** : Cheffer n'accepte que Cloudflare à l'origine
    (voir mémoire `reference_securite_cheffer`). Surveiller le **nom de domaine** (via Cloudflare), jamais l'IP
    d'origine ; si le WAF/Bot Fight bloque les sondes, autoriser leurs IP (`ips.hetrixtools.com`,
    `doc/related/uptime-monitoring-ip-addresses.md`). Idem pour le webhook entrant : il arrive depuis des IP Cloudflare.
15. **Blacklist check API** : jusqu'à 5 min de traitement ; tant que ce n'est pas fini, réponse
    `"blacklist check in progress"` (rappeler sans consommer de crédit).
16. **Deux offres à 9,95 $** (Uptime « Professional » vs Blacklist « Personal ») : vérifier laquelle est prise.
17. Contrainte de nommage des moniteurs (v2 add) : `a-z A-Z 0-9`, espaces, points, tirets — pas d'accents.

## 10. Pour la home Genesis/Cheffer (badges OK/KO + carte de détail)

**Architecture recommandée : tout côté serveur, avec cache.** La clé reste dans `genesis/.env` ; un job du
backend (API 8080 / service Genesis) interroge HetrixTools et écrit un instantané ; genesis-ui lit une route
interne (`/api/status` par ex.) qui sert ce cache. Le navigateur ne voit **jamais** la clé ni `api.hetrixtools.com`.

| Donnée de la carte | Appel | Fréquence |
| --- | --- | --- |
| Badge OK/KO, « depuis quand », temps de réponse par ville, dernier test | `GET /v3/uptime-monitors?per_page=200` (1 seul appel pour tous) | **toutes les 60 s** (= fréquence de test ; plus souvent ne sert à rien) |
| Uptime 24 h / 7 j / 30 j | `GET /v3/uptime-monitors/{id}/report?days=30&timezone=+02:00` → 30 j = `summary`, 7 j = moyenne des 7 derniers `data.<jour>`, « 24 h » = jour en cours (ou moyenne aujourd'hui+hier) | toutes les 15 min, par moniteur |
| Dernier incident (début, durée, en maintenance ?) | `GET /v3/uptime-monitors/{id}/downtimes?start_after=<now-30j>&per_page=200` → max(`start`) | toutes les 5–15 min, **et** tout de suite quand le badge passe `down` → `up` |
| Cause (au clic seulement) | `location-fail-log`, `network-diagnostics?downtime_id=`, `web-snapshot?downtime_id=` | à la demande, cachées 10 min |
| Santé serveur (CPU/RAM/disque, agent vivant) | `GET /v3/uptime-monitors/{id}/server-agent/metrics` (sans paramètre = dernier état + 60 min) | toutes les 1–5 min pour les monitors `has_agent` |
| Emplacements testés | champ `locations` de la liste (clés = villes actives) | avec la liste |

Budget : avec N moniteurs (≤ 30 sur Professional) ≈ 1/min (liste) + N/15 (rapports) + N/10 (pannes)
+ A/2 (agents) ⇒ ~10 req/min pour 30 moniteurs, loin des exemples de limite (200/min) — **mais la vraie limite
n'est pas publiée** : lire `ratelimit-remaining-user` à chaque réponse, espacer si < 20 %, et sur `429`
attendre `ratelimit-reset-user`. Jamais de v1/v2 en boucle (10 000/mois = 1 appel toutes les 4,5 min).

Règle d'affichage (badge `ui/status-badge.md`) :
- `monitor_status` ∈ {`maint`,`maint_dnd`} → **orange « Maintenance »** ;
- `paused`/`disabled`, ou cache plus vieux que 3 min, ou API en erreur → **gris « Pas de données »**
  (ne jamais afficher un vert périmé) ;
- sinon `uptime_status` `up` → **vert**, `down` → **rouge « KO depuis <now − last_status_change> »**.

Temps réel (option) : webhook de Contact List → route du backend Genesis (jeton Bearer vérifié, IP Cloudflare)
qui met à jour le cache immédiatement et peut relayer sur le canal Telegram existant ; le sondage 60 s reste le
filet de sécurité (webhook perdu = rattrapé à la minute suivante).

## 11. Rafraîchir cette doc

`outils/` contient les scripts utilisés (Python, `markdownify` + `beautifulsoup4` + `pyyaml` dans un venv) :
- `conv.py` : posts WordPress (`/wp-json/wp/v2/posts?categories=17|477|478|480&per_page=100`) → `doc/api`, `doc/mcp`, `doc/related` ;
- `oa.py` : `api.yaml` → `doc/api/v3/*.md` + `INDEX.md` + `_intro.md` (récupérer d'abord
  `https://docs.hetrixtools.com/api/v3/api.yaml?v=<n>`, le `v` est dans `https://docs.hetrixtools.com/api/v3/`) ;
- `tbl.py` : page de tarifs → tableau Markdown.
Catégories WordPress : 17 = API, 477 = MCP, 478 = MCP cas d'usage, 480 = MCP exemples, 22 = Contact Lists (webhooks).
