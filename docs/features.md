# Features — Genesis UI (carte des pages)

> Arborescence complète de l'interface Next.js, avec chemin URL, rôle, APIs consommées et connexions
> entre pages. Mettre à jour quand une page est ajoutée, renommée ou supprimée.
> Dernière mise à jour : 2026-06-24

---

## Structure générale

```
/login                      → authentification
/onboarding                 → première connexion
/dashboard                  → aperçu global (multi-sites, placeholder)
/view                       → vue multi-sites côte à côte
/costs                      → coûts LLM (DeepSeek/Anthropic)
/campaigns                  → builder de campagnes cross-canal (global)
/versions                   → historique git + sauvegardes DuckDB
/security                   → 2FA TOTP, sessions actives
/admin/logs                 → logs audit (actions utilisateurs)
/admin/users                → gestion comptes
/site/[code]/               → (redirige vers /site/[code]/dashboard)
/site/[code]/dashboard      → tableau de bord par site
/site/[code]/vision         → métriques workflow (funnel scrape→push)
/site/[code]/scrapper       → lancer scrapes Serper + Basile
/site/[code]/acquisition    → CRM contacts (cold_email → lead → client)
/site/[code]/cold-email     → templates cold email (3 étapes Emelia)
/site/[code]/newsletters    → messages newsletters + campagnes masse Sweego
/site/[code]/campaigns      → campagnes Emelia auto (secteur × dept × quota)
/site/[code]/cleanup        → nettoyage pool Mailnjoy (vérif. délivrabilité)
/site/[code]/seo            → métriques SEO (GA4 + GSC + Ahrefs)
/site/[code]/seo-strategy   → recommandations SEO (agent DeepSeek)
/site/[code]/tag            → générateur UTM par canal
/site/[code]/articles       → queue éditoriale (brief → écriture → publish)
/site/[code]/agents         → crons IA (brief_agent, content_agent…)
/site/[code]/setup          → config site (API keys, logo, Mailnjoy)
/site/[code]/templates      → ⚠️ REDIRECT vers /cold-email (alias obsolète)
```

**[code]** = `lcr` (leclientroi.com) ou `mkd` (mkdgroupe.com)

---

## Pages globales (hors site)

### `/login`
Auth JWT + TOTP. POST `/api/auth/login` → cookie `session`.

### `/onboarding`
Wizard première connexion (mot de passe initial).

### `/dashboard`
Shell vide — placeholder multi-sites. Redirige généralement vers `/site/lcr/dashboard`.

### `/view`
Vue multi-sites côte à côte. Consomme `/api/sites` + `/api/sites/{site}/seo/dashboard`.

### `/costs`
Historique et agrégats des coûts LLM. Graphique ligne quotidien.
- API : GET `/api/costs` (filtre site, action, date)

### `/campaigns`
Builder de campagnes Emelia cross-canal. Éditeur email (sujet + body HTML/texte), configuration
séquence (délais, jours d'envoi), choix secteur et listes.
- API : `/api/campaigns/*`, `/api/emelia/*`

### `/versions`
Historique git (commits + tags) + liste des sauvegardes DuckDB disponibles.
- API : GET `/api/versions`

### `/security`
Gestion 2FA TOTP (QR code + vérification), liste des sessions actives, révocation.
- API : `/api/auth/totp/*`, `/api/auth/sessions`

### `/admin/logs`
Journal d'audit des actions utilisateurs (par site, par action).
- API : GET `/api/admin/logs`

### `/admin/users`
CRUD comptes (email, rôle, reset mot de passe).
- API : `/api/admin/users/*`

---

## Pages par site `/site/[code]/`

### `/site/[code]/dashboard` — Tableau de bord
**Rôle :** vue synthétique : pipeline CRM (funnel cold_email → lead → client), derniers contacts
pushés, alertes crédits (`<ConnectorAlerts />`), métriques rapides.

**APIs :**
- GET `/api/sites/{site}/acquisition/stats` — compteurs par état
- GET `/api/sites/{site}/emelia/stats` — envois Emelia du jour
- GET `/api/sites/{site}/god-mode/state` — état workflow

**Connexions :** → Acquisition, → Vision, → Cold-email

---

### `/site/[code]/vision` — Vision workflow
**Rôle :** métriques end-to-end du pipeline : scrape → qualification → push Emelia → CRM.
Graphique funnel (Recharts BarChart), compteurs du jour/mois/total.

**APIs :**
- GET `/api/sites/{site}/god-mode/state`
- GET `/api/sites/{site}/god-mode/campaigns`

**Connexions :** → Scrapper (si scraping à lancer), → Campaigns (campagnes actives)

---

### `/site/[code]/scrapper` — Scrapper Serper + Basile
**Rôle :** lancer des scrapes de prospects par secteur × région. Double source : Serper (Google
Places) + Basile (registre entreprises). Cible configurable (défaut 100 contacts). Logs temps réel.

**APIs :**
- POST `/api/sites/{site}/autoscrape/start` — `{sector, region, target_contacts}`
- GET `/api/sites/{site}/autoscrape/status` — progression + compteurs Serper/Basile
- GET `/api/sites/{site}/god-mode/state` — état scrappe_pending

**Connexions :** → Cleanup (vérifier les contacts scrapés), → Campaigns (pousser vers Emelia)

---

### `/site/[code]/acquisition` — CRM Acquisition
**Rôle :** liste paginée de tous les contacts avec filtres (état, secteur, source), fiche détail
(sheet latérale), changement manuel d'état, import CSV, blacklist, export.

**États possibles :** `cold_email` → `prm` → `lead` → `crm` | `blacklisted`

**APIs :**
- GET `/api/sites/{site}/acquisition` — liste (filtre, offset, limit)
- PATCH `/api/sites/{site}/acquisition/{id}` — changer état
- DELETE `/api/sites/{site}/acquisition/{id}` — supprimer / blacklist
- POST `/api/sites/{site}/acquisition/import` — import CSV

**Connexions :** → Cold-email (via séquences Emelia), → Newsletters (masse Sweego)

---

### `/site/[code]/cold-email` — Templates Cold Email
**Rôle :** éditeur des templates cold email par secteur (3 étapes : 1er email, Relance 1, Relance 2).
Chaque template a sujet + body HTML (avec variables `{{firstName}}`, `{{field1}}`).
Verrouillage/déverrouillage, génération IA (DeepSeek).

**APIs :**
- GET `/api/sites/{site}/god-mode/templates` — liste par secteur
- PATCH `/api/sites/{site}/god-mode/templates/{id}` — sauvegarder
- POST `/api/sites/{site}/god-mode/templates/{id}/generate` — générer via IA
- POST `/api/sites/{site}/god-mode/templates/{id}/lock` / `unlock`

**Connexions :** → Campaigns (les templates alimentent les séquences Emelia)

---

### `/site/[code]/newsletters` — Newsletters + Campagnes Sweego
**Rôle :** CRUD des messages newsletters (éditeur HTML riche), prévisualisation desktop/mobile,
lint HTML. **Section masse** : lancer des campagnes Sweego sur un segment de contacts, avec BAT
préalable, simulation (dry-run) et envoi réel. Historique des campagnes Sweego.

**Types d'envoi :**
- Newsletter HTML standard (archivage)
- Masse Sweego : POST `/api/sites/{site}/mass-campaigns/create` (réel) ou `dry_run=true` (simuler)
- BAT Sweego : POST `/api/sites/{site}/mass-campaigns/bat` → `camille@leclientroi.com`

**APIs :**
- GET/POST/PATCH/DELETE `/api/sites/{site}/messages` — CRUD messages
- GET `/api/sites/{site}/mass-campaigns` — historique campagnes Sweego
- POST `/api/sites/{site}/mass-campaigns/create` — lancer campagne
- POST `/api/sites/{site}/mass-campaigns/bat` — envoyer BAT

**Connexions :** → Acquisition (source des contacts masse), → Tag (UTM sweego)

---

### `/site/[code]/campaigns` — Campagnes Emelia automatiques
**Rôle :** CRUD des campagnes cold email automatiques (secteur × département × quota quotidien).
Chaque campagne a un état (active/paused/stopped), un historique de runs, une liaison Emelia.

**APIs :**
- GET/POST/DELETE `/api/sites/{site}/god-mode/campaigns`
- POST `/api/sites/{site}/god-mode/campaigns/{id}/start` / `pause` / `stop`

**Connexions :** → Cold-email (templates), → Acquisition (contacts pushés)

---

### `/site/[code]/cleanup` — Nettoyage Mailnjoy
**Rôle :** vérifier la délivrabilité des contacts en `scrappe_pending` via Mailnjoy. Affiche les
contacts non vérifiés / obsolètes, lance la vérification par lot, supprime les invalides.

**APIs :**
- GET `/api/sites/{site}/god-mode/cleanup/counts`
- POST `/api/sites/{site}/god-mode/cleanup/run`
- DELETE `/api/sites/{site}/god-mode/cleanup/stale`

**Connexions :** → Scrapper (alimente scrappe_pending), → Campaigns (contacts validés → push)

---

### `/site/[code]/seo` — Analyse SEO
**Rôle :** dashboard SEO complet : sessions GA4 (graphique aire quotidien), clics GSC,
métriques Ahrefs (DR, keywords, trafic organique), répartition par canal, top keywords.

**APIs :**
- GET `/api/sites/{site}/seo/dashboard` — agrégé GA4 + GSC + Ahrefs
- GET `/api/seo-ahrefs/{site}` — métriques Ahrefs

**Connexions :** → SEO Strategy (recommandations issues de l'analyse), → Tag (UTM par canal)

---

### `/site/[code]/seo-strategy` — Stratégie SEO
**Rôle :** recommandations SEO générées par l'agent DeepSeek à partir de l'audit Ahrefs mensuel.
Liste priorisée (keyword, URL cible, action, impact, effort). Accepter / rejeter / relancer.

**APIs :**
- GET `/api/seo-strategy/{site}`
- POST `/api/seo-strategy/{id}/accept` / `reject` / `implement`
- POST `/api/sites/{site}/competitor-analysis`
- GET `/api/seo-ahrefs/{site}`

**Connexions :** → Articles (créer un article sur un keyword recommandé), → SEO (voir les métriques)

---

### `/site/[code]/tag` — Plan de taggage UTM
**Rôle :** générateur d'URLs taguées par canal. Saisir une page de destination + nom de campagne,
obtenir l'URL avec `utm_source` / `utm_medium` / `utm_campaign` pour chaque canal.

**Canaux disponibles :**
| Canal | utm_source | utm_medium |
|---|---|---|
| SMS | sms | sms |
| Newsletter | newsletter | email |
| Cold-email Emelia | coldemail | email |
| Masse Sweego | sweego | email |
| Cold-email Maildoso | maildoso | email |
| Pub Meta | facebook | paid_social |
| Partenaire | partenaire | referral |

**APIs :** GET `/api/sites/{site}/seo/dashboard` (pour afficher le % Direct si > 40%)

**Connexions :** → SEO (mesurer l'impact des canaux), → Newsletters (liens UTM sweego)

---

### `/site/[code]/articles` — Articles éditoriaux
**Rôle :** queue des articles (brief → écriture → révision → publication WordPress). Éditeur
Markdown + preview HTML. Upload image (génération alt automatique). Validation avant publish.

**APIs :**
- GET/POST/PATCH `/api/editorial/{site}/articles`
- POST `/api/editorial/{site}/articles/{id}/generate`
- POST `/api/editorial/{site}/articles/{id}/publish`

**Connexions :** → SEO Strategy (les recommandations peuvent créer des articles)

---

### `/site/[code]/agents` — Agents IA
**Rôle :** liste des crons IA avec leur état, dernière exécution, log. Lancer manuellement.

**Agents listés :**
- `brief_agent` — propose des sujets d'articles (lun + jeu 8h)
- `content_agent` — écrit + publie un article (mer/jeu 10h)
- `seo_strategy_agent` — génère recommandations SEO (lun 7h)
- `briefing` — rapport Telegram matinal (7h)
- `linkedin_agent` — post LinkedIn (10h UTC)
- `ahrefs_daily` — métriques Ahrefs (6h)
- `workflow_runner` — scrape → qualify → push (6h30 lun-ven)

**APIs :**
- GET `/api/sites/{site}/agents`
- POST `/api/sites/{site}/agents/{name}/run`

**Connexions :** → Articles (articles générés), → SEO Strategy (recommandations), → Vision (workflow)

---

### `/site/[code]/setup` — Configuration site
**Rôle :** configuration par site : nom, logo, clés API (Emelia, Ahrefs…), config Mailnjoy (seuil
délivrabilité), secteurs activés, modules activés/désactivés.

**APIs :**
- GET/PATCH `/api/sites/{site}/config`
- GET/POST `/api/sites/{site}/api-keys`
- GET/PATCH `/api/sites/{site}/mailnjoy-config`

**Connexions :** → toutes les pages (les clés API conditionnent toutes les fonctions)

---

## Composants sidebar permanents

### `<CreditsWidget />`
Affiché en bas de sidebar. Refresh toutes les 60 s.

| Indicateur | Source | Seuil alerte |
|---|---|---|
| DeepSeek | `/api/deepseek/usage` | < 1 € |
| Ahrefs | `/api/ahrefs/usage` | > 80% quota |
| Mailnjoy | `/api/mailnjoy/credits` | < 100 crédits |
| Serper | `/api/serper/usage` | < 500 crédits |
| Basile | `/api/basile/usage` | > 80% quota |
| Emelia | `/api/emelia/credits` | < 50 crédits |
| Sweego | `/api/sweego/stats` | — (affiché = nb emails envoyés) |

### `<ConnectorAlerts />`
Bannières rouges/oranges si un connecteur est épuisé ou bas. Masquables. Refresh 60 s.

---

## Navigation sidebar (groupes)

```
Général
  └── Tableau de bord    /site/[code]/dashboard

Stratégie
  ├── Analyse SEO        /site/[code]/seo
  ├── Plan de taggage    /site/[code]/tag
  ├── Stratégie SEO      /site/[code]/seo-strategy
  └── Agents IA          /site/[code]/agents

Contenu
  └── Articles           /site/[code]/articles

Commercial
  ├── Vision             /site/[code]/vision
  ├── Scrapper           /site/[code]/scrapper
  ├── Acquisition        /site/[code]/acquisition
  ├── Newsletters        /site/[code]/newsletters
  ├── Campagnes          /site/[code]/campaigns
  └── Nettoyage          /site/[code]/cleanup

Admin
  └── Setup & API        /site/[code]/setup

Admin global (hors site)
  ├── Vue multi-sites    /view
  ├── Coûts LLM          /costs
  ├── Logs système       /admin/logs
  ├── Utilisateurs       /admin/users
  └── Sécurité           /security
```

---

## Pages manquantes / à construire

| Page | Statut |
|---|---|
| Cold-email Maildoso (séquenceur) | ⏳ Disponible ~2026-07-07 (warmup en cours) |
| Stats unifiées (Emelia + Sweego + Maildoso) | Non commencé |
| Click→lead Sweego (UTM → acquisition) | Non commencé |
| Click→lead Maildoso (IMAP reply) | Non commencé |

---

## Voir aussi
- `ARCHITECTURE.md` — catalogue des 49 modules backend + schéma DB
- `STATE.md` — source de vérité de reprise de session
- `docs/platforms-api.md` — auth + endpoints Emelia, Sweego, Maildoso
- `docs/infrastructure.md` — domaines, DNS, MTA, boîtes Maildoso
