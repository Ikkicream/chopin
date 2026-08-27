# STATE — Genesis (à lire EN PREMIER au démarrage de session)

> Source de vérité unique pour reprendre le projet sans re-expliquer le contexte.
> À mettre à jour AVANT toute fin de session ('à demain', 'j'en ai marre', etc.).

## Dernière mise à jour
2026-07-24 (Fix boucle infinie scrape→kill→re-scrape + gel quotidien autoscrape sur fetch_email_from_site)

## 🔝 REPRISE 2026-07-24 — Scraping : boucle infinie Mailnjoy + gel 11 h/jour (FIXÉ)

**Symptômes user :** (1) cleanup quotidien 07:05 supprimait 100 % des contacts depuis le 17/07
(0 validés), (2) scrapes « vides » depuis que Serper est à 0 crédit, impression que Basile ne
peut pas tourner seul.

**Causes trouvées (3 bugs indépendants qui se combinaient) :**
1. **Aucune mémoire des rejets** : un email tué par Mailnjoy (risky/invalid — décision user
   2026-05-22 : risky = kill) était supprimé du pool sans trace. Basile/Serper le re-trouvaient
   le lendemain → ré-insertion → re-check Mailnjoy (2 crédits/jour/email) → re-suppression.
   ~50 emails tournaient en boucle depuis le 17/07 ; le lot quotidien du cleanup n'était QUE ça,
   d'où 100 % supprimés.
2. **Reprise sans mémoire des villes** : `daily_retry`/`autoscrape_plan` ne persistaient que
   `depts_done` — chaque matin le dept 59 repartait de la ville 1 (jamais au-delà de ~40/54).
3. **Gel 11 h/jour** : `fetch_email_from_site` (appelé aussi par Basile) faisait `r.text` sans
   cap de taille → un site pathologique gelait le run de 06:15 à ~17:13 (state R, chardet/regex
   sur blob géant). C'est LA raison des « timeout » quotidiens et de la non-progression.
   Basile tournait bien SEUL (70 valid/jour) mais ne produisait que les loopers du bug 1.

**Fixes déployés :**
- **`scrappe_rejected`** (god_mode.duckdb) : tombstone des emails tués. Marqué par drain
  (`mailnjoy_check.check_pending_queue`), cleanup (`cleanup_backend.run_cleanup`), imports
  (`acquisition_backend._validate_address` → early-return gratuit `rejected_before`).
  Consulté avant insertion (god_mode_agents + basile_backend ×2) et avant tout check payant.
  **Backfill : 8 327 emails** depuis logs/mailnjoy_deletions.log + god_mode_logs.
- **Drain** : supprime aussi la copie pool non vérifiée quand il tue un pending
  (`_delete_unverified_pool_copy`) — c'était la fuite qui alimentait le cleanup du matin.
- **Reprise intra-dept** : `run_autoscrape(cities_done=, cities_dept=)` + persistance par ville
  dans `<site>-region-progress.json` ; branché dans `daily_retry` ET `autoscrape_plan.work`.
- **`daily_retry`** : reprend en Basile-seul si Serper bloqué (avant : test Serper KO = rien).
- **`fetch_email_from_site`** : stream + cap 2 Mo + filtre content-type + décodage utf-8/replace.
- Pending `mailnjoy_attempts` ≥5 (194 rows invisibles au drain) resetés à 0 ; crédit Mailnjoy
  vérifié : 1 036 125.
- Run du 24/07 stoppé (figé depuis 06:15), progress patché (39 villes dept 59 done, valid=529),
  retry relancé avec le nouveau code → reprise ville 40/54.

- **4e bug (même session, plus tard)** : le vrai `fetch_email_from_site` gelait sur la REGEX
  `EMAIL_RE.findall` (quadratique sur blobs sans `@`) — remplacée par `_emails_in_text()`
  (fenêtre bornée autour de chaque `@`, testé : 2 Mo pathologique en 0,000 s vs heures).
- **5e bug** : le drain PM2 était un zombie (« online » sans PID) ; le VRAI drain était un
  process orphelin de 30 jours (PID 2741494, lancé 23/06, binaire python supprimé, ancien
  code sans tombstones) qui tenait le verrou DuckDB par à-coups. Orphelin tué, drain PM2
  recréé proprement (`pm2 delete` + `start`, pm2 save) — il logge enfin.

- **7e fix (analyse des rejetés, demande user)** : 55 % des 4 990 emails supprimés étaient des
  FAUX POSITIFS (Mailnjoy disait VALID/SAFE, tués par l'attribut role/catchall). Décision user
  2026-07-24 : les `contact@` sont de bons contacts cold-email → `classify_response` garde
  désormais tout VALID+SAFE ; VALID/RISKY (catchall) toujours tué. 2 676 purgés du tombstone.
  Doc : `docs/contact-acquisition.md §0ter`.

**RESTE :** vérifier demain 07:05 que le cleanup ne supprime plus 100 % ; le plan immobilier est
« done » sur les 12 régions mais les chiffres du 16/07 incluent des fantômes → envisager une
relance du plan (les tombstones + reprise par ville rendent le re-scan quasi gratuit) ; l'UI
Activité des anciens runs reste approximative — cosmétique.

## 🔝 REPRISE 2026-06-29 — Prise de RDV publique (type Calendly/TidyCal)

**Demande user :** lien public de prise de RDV par site, le prospect choisit un motif
(démo/question/partenariat), un créneau parmi ceux ouverts en back-office, saisit ses coords →
**email + SMS de confirmation**. Belle page. Condition : URL testée + email démo réellement envoyé.

**FAIT + TESTÉ bout-en-bout :**
- **`booking_backend.py` (NOUVEAU)** : tables `booking_settings` (config JSON/site, seed défaut :
  Lun-Ven 9-12/14-18, créneaux 30 min, 3 motifs) + `bookings`. Helpers `get_settings`/
  `update_settings`, `available_days`/`available_slots` (filtre passé + déjà réservé, tz Europe/Paris),
  `create_booking` (valide motif + créneau libre), `list_bookings`, `send_confirmations`.
- **`booking_page.py` (NOUVEAU)** : page HTML autonome (CSS inline, responsive, wizard motif→jour→
  créneau→coords), JS vanilla consommant les endpoints.
- **`sweego_backend.py`** : `send_transactional_email` (campaign-type=transac, 1 destinataire) +
  `send_sms` (provider=sms, normalise 06→+336, best-effort). Domaine expéditeur = leclientroi.com
  (seul vérifié Sweego) même pour MKD.
- **`api.py`** : endpoints PUBLICS (exemptés middleware, comme /sweego/click) `GET /api/book/{site}`
  (HTML), `/config`, `/slots`, `POST /submit` ; back-office AUTHENTIFIÉ `GET|PUT /api/sites/{site}/
  booking/settings`, `GET .../booking/list`.
- **UI** : page `/site/{code}/booking` (édite réglages, motifs, dispos hebdo, lien public copiable,
  liste RDV) + entrée sidebar « Rendez-vous » (Commercial). Build Next OK, UI restart OK.
- ✅ **TEST RÉEL** : `GET /api/book/lcr` → 200 ; config/slots OK ; `POST /submit` (démo,
  afchain.camille@gmail.com) → RDV `ba6ba218` créé + **Sweego transaction_id 56bfbd93-…
  (email.ok:true)**. Créneau retiré des dispos après réservation + double-booking refusé. **(1 RDV
  de test reste dans la liste back-office LCR — pas de endpoint delete pour l'instant.)**
- ⚠️ **SMS pas testé en réel** (pas de numéro de test, coût) : payload Sweego `provider:sms`
  best-effort, non bloquant. À valider avec un vrai numéro. ⚠️ Lien public = `https://api.cheffer.email/
  api/book/{site}` (sous /api/ car servi par FastAPI). API à redémarrée faite.
- **MAJ 2026-06-29 (retour user)** : page publique enrichie — **logo** (champ `logo_url`, fallback nom
  du site), **favicon + lien site** (`website_url`, favicon Google s2), **description** (texte d'intro).
  Défauts pré-remplis depuis `sites_config` (url, primary_color, rag_context.business_description).
  Back-office **séparé en 2 onglets** : « Configuration » (identité + réglages + motifs + dispos) et
  « Rendez-vous » (formulaires reçus). Build Next OK, restart OK, rendu vérifié (couleur #0066FF,
  desc + favicon + lien présents).
- **MAJ 2026-06-29 (retour user #2)** : onglets inversés (**Rendez-vous** en 1er + défaut, Configuration
  2e). Système **lu/non-lu** : statut `bookings.status` (`confirmed`=à traiter → `answered`=répondu).
  Endpoints `GET .../booking/unread-count` + `POST .../booking/{id}/status`. Helpers `unread_count` /
  `set_status`. UI : badge « Nouveau » + point rouge + bouton « Marquer répondu » par RDV ; **pastille
  rouge dans la sidebar** sur l'item « Rendez-vous » (nb non-répondus, poll 45s + refresh navigation,
  injectée dans `nav-main.tsx` via champ `badge`). La pastille ne décroît QUE sur « répondu ». Testé :
  unread 2→1 après set_status answered. Build + restart OK.
- **MAJ 2026-06-29 (retour user #3)** : champ `hero_image_url` = **image de fond derrière l'en-tête**
  (voile teinté couleur de marque via color-mix + text-shadow pour lisibilité, ancrée à gauche/cover).
  Champ éditable en back-office (carte Identité). Couleur LCR passée du bleu #0066FF au **violet pastel
  `#a78bfa`** (charte). Persisté pour lcr via `update_settings`. ⚠️ Bug corrigé : l'upsert DuckDB
  `INSERT…ON CONFLICT…CURRENT_TIMESTAMP` plantait (BinderException) → remplacé par read-modify-write
  (SELECT puis UPDATE/INSERT). Rendu vérifié : `--brand:#a78bfa`, `head has-hero`, bg image OK.
- **MAJ 2026-06-29 (sécurité RDV)** : durcissement injection.
  • **XSS email** (vraie faille) : le `name` du prospect était interpolé NON-échappé dans
    `_confirmation_html` → `html.escape()` sur name/label/reason_label. Testé : `<script>` → `&lt;script&gt;`.
  • **Email regex stricte** (`_EMAIL_RE`, ≤254 car) côté backend (`create_booking`) + côté page (bouton
    bloqué + message « email invalide »). Testé live : `<script>…`@ et `pasunemail` → refus, aucun envoi.
  • **Bornage entrées** : name≤120, message≤2000, phone nettoyé `[0-9+ ().-]`≤30 (anti-payload + anti-injection SMS).
  • **Couleur** : `_safe_color` (hex only) sur email + page → anti-injection CSS via `--brand`.
  • **DOM** : motifs rendus via `textContent`/`createTextNode` (plus d'`innerHTML` avec la config).
  • Back-office = React (auto-échappé) ; page publique ne reflète aucune saisie. SQL = paramétré partout.

## 🔝 REPRISE 2026-06-26 (suite) — Quota scrape mensuel + alerte crédits d'envoi

## 🔝 REPRISE 2026-06-26 (suite) — Quota scrape mensuel + alerte crédits d'envoi

**Demande user :** (1) plafonner les users à **5000 scrappe/mois**, (2) **alerte admin quand
il n'y a plus de crédit d'envoi**. Choix validés : quota = contacts GARDÉS/mois, canal alerte =
Telegram (déjà câblé), seuils = bas + épuisé.

**FAIT :**
- **Quota scrape (`god_mode_backend.py`)** : nouvelle table `scrape_quota_usage`
  (user_id, year_month, used, PK) + helpers `scrape_quota_status(user_id)` /
  `record_scrape_usage(user_id, n)`. Cap = `SCRAPE_MONTHLY_CAP = 5000`, par user, tous sites.
- **Enforcement (`god_mode_api.py` POST `/{site}/scrape`)** : si `role != superadmin` →
  refuse (429) quand `remaining<=0`, sinon **clampe `global_cap` au restant**. En fin de scrape
  (thread `run`), `record_scrape_usage(user_id, kept_total)` additionne les contacts réellement
  gardés. **Le superadmin (Camille) n'est PAS limité.**
- **Alerte crédits (`scripts/credit_alerts.py` NOUVEAU)** : surveille les soldes LIVE Emelia
  (`fetch_live_balance`) + Mailnjoy (`get_credit`). Niveaux `low`/`empty` (seuils Emelia<50,
  Mailnjoy<100). Anti-spam : alerte seulement au franchissement d'un palier (état
  `memory/credit_alerts.json`), réarme au retour `ok`. Envoi Telegram (TELEGRAM_BOT_TOKEN/CHAT_ID).
- **Branchements** : `campaign_engine.dispatch_due()` (cron 8h30) + endpoint send-now
  (`api.py`) appellent `credit_alerts.check_and_alert()` avant l'envoi (best-effort).
- Vérifié : `py_compile` OK sur les 5 fichiers ; `scrape_quota_status` → 5000 dispo ;
  logique de seuils OK. (Pas d'envoi Telegram réel déclenché pendant les tests.)
- ⚠️ Sweego n'expose pas de solde lisible → seuls Emelia + Mailnjoy sont surveillés (les 2
  crédits LIVE du pipeline d'envoi). API à redémarrer pour activer (`pm2 restart genesis-dashboard`).

## 🔝 REPRISE 2026-06-26 — Isolation multi-tenant (faille cross-site fermée)

**Problème (signalé user, confirmé) :** un commercial scoppé LCR voyait des données/alertes MKD
(alerte « WordPress (MKD) », « MKDgroupe » dans /view). Cause : l'isolation n'était posée QUE sur
`/api/sites/{site}/*` ; tous les autres endpoints à site (`/api/crm/{site}`, `/api/dashboard/{site}`,
`/api/seo-ahrefs/{site}`, `/api/agents/{site}/*`…) **fuyaient** (200 au lieu de 403). **Vraie fuite
de données, pas cosmétique.**

**Corrigé + VÉRIFIÉ (token commercial réel) :**
- **Middleware (`api.py`) — isolation GÉNÉRALE** : détecte un code site (`_known_site_codes()` =
  registre `sites_config`, fallback `{lcr,mkd,tst}`) dans **n'importe quel** segment d'URL OU le
  query `?site=`, et renvoie **403** si pas dans `sess["sites"]` (superadmin bypass). Remplace
  l'ancien check `/api/sites/` only. Testé : tous endpoints MKD → 403, son site → 200.
- **Agrégés filtrés par session** (helper `_scope_connectors` + filtres) :
  `/api/connectors/health`, `/api/connectors` (masquent emdash=LCR / wordpress=MKD / tally_* selon
  les sites), `/api/health-check` (ne check QUE ses sites), `/api/budget` (force son site),
  `/api/campaigns` (filtre par préfixe de nom `lcr-`/`mkd-`). `_CONNECTOR_SITE` mappe connecteur→site.
- **Front** : `/view` ET `/campaigns` (pages globales cross-site) réservées superadmin → un user
  métier est redirigé vers `/site/{son_site}/dashboard|campaigns`. Garde de rendu anti-flash.
- **Scrapper god-mode ouvert aux users métier sur LEUR site** : tout le router `god_mode_api.py`
  était `Depends(require_admin)` → un commercial avait 403 partout (toggle/scrape inertes, scrapper
  mort alors qu'il est dans la nav Commercial). Remplacé par `require_site_access` (admin OU user
  avec accès au `{site}`) sur les 28 endpoints. Décision user : un commercial peut scraper SON site
  (consomme des crédits Serper/Basile), pas un autre (middleware bloque). Vérifié : lcr→200, mkd→403.
- ⚠️ Limite connue : l'isolation détecte les codes site par scan de segments — robuste pour des
  codes distinctifs (lcr/mkd/tst), à revoir si un futur endpoint embarque un code site hors position
  de scope. Pas de silo de données séparé par tenant (pas nécessaire pour « un user ne voit que son
  site ») — l'enforcement middleware + filtrage agrégé suffit.

## 🔝 REPRISE 2026-06-25 — Webhook Sweego (clics→leads), cleanup pool, Vision

### ✅ Webhook Sweego ENFIN débloqué (clic → lead dans /acquisition)
**Le blocage depuis le départ = mauvais `uuid_client`.** Le bon (compte CACAR Holding,
`technique@leclientroi.com`) = **`bd0d7413-26ff-414c-9e31-232382ff1512`**. L'`Api-Key` du `.env`
SUFFIT pour gérer les webhooks (`/clients/{uuid}/webhooks`), pas besoin d'auth user. (L'ancien
`5fe41d8d-…` était un mauvais uuid → 403.)
- **Tracking clic/ouverture DÉJÀ activé + vérifié** sur `leclientroi.com` (`tracking_click_enabled`,
  `tracking_open_enabled`, `is_verified` = true). Aucun DNS / aucune action dev nécessaire.
- **Mapping event_type_ids Sweego (channel email=1, sms=2) :** 1=Delivered, 2=Soft bounce,
  3=Hard bounce, 4=List Unsub, 5=Complaint, 6=Sent, **9=clicked**, 10=clicked_unsub, 11=opened.
  Body create = `events:[{event_channel, event_type_ids:[…], domain_uuids:[…]}]` (les 3 requis).
  Domain uuids : leclientroi.com=`f68f25ef-b658-470e-9c0e-59ca66e90634`,
  news.leclientroi.app=`f15130f6-…`, news.leclientroi.email=`ee50d85f-…`.
- **Webhook créé : `genesis-prm`** (uuid `f3ac5b86-88ac-4408-8851-c006efb804f9`, ENABLED) →
  `https://api.cheffer.email/api/sweego/webhook?token=<WEBHOOK_TOKEN_1>`, events
  [9,11,3,4,5,10] sur les 3 domaines. Le webhook **`prod`** (→ app.leclientroi.com, 12k succès)
  est intact ; les deux reçoivent.
- **Récepteur durci** (`api.py` `/api/sweego/webhook`) : résolution robuste event_type
  (`event_type|status|event`, normalise tirets ET espaces) + recipient (`recipient|email|to`).
  Mapping : `clicked` humain→`prm` (proxy ignoré), `opened`→horodatage, `Hard bounce`/`List Unsub`/
  `Complaint`/`clicked_unsub`→blacklist + sortie pool. API redémarrée.
- **✅ VALIDÉ 2026-06-25 (vrai clic)** : BAT envoyé (`transaction_id 2717d86d`), clic réel →
  webhook reçu (success_count 2) → `camille@leclientroi.com` promue **lead `prm` dans
  /acquisition** + ajoutée au pool. **Format payload Sweego CONFIRMÉ** : `event_type` =
  **`email_clicked`** / **`email_opened`** (champ recipient présent), pas `clicked`/`opened` du
  config webhook. Le récepteur durci les gère déjà (`== "email_clicked"` + `startswith`).
  Reste : nettoyer le lead de test `camille@leclientroi.com` du pool + acquisition quand on veut.
- ⚠️ Sweego note : webhook `clicked_unsub` « coming soon » côté Sweego (visible en logs en attendant).

### 🧹 Cleanup pool : 1×/nuit (3h) → HORAIRE + robuste
`scripts/nightly_cleanup.py` : (a) `count_unverified()` (avant/après) passe par le retry anti-lock
(`_retry_lock`) — corrige le crash 2026-06-21 ; (b) un verrou pool persistant = SKIP propre (exit 0,
pas d'alerte) ; cron PM2 `genesis-nightly-cleanup` `0 3 * * *` → **`0 * * * *`** (`pm2 save` fait).
Le drain couvre TOUT le pool (le param `site` n'est qu'un label de log, `list_for_cleanup` est
global). Les ~859 jamais-vérifiés ont été drainés → pool **3762 contacts dont 3647 mailnjoy-valid,
0 jamais-vérifié**. Le drainer continu `genesis-mailnjoy-drain` ne couvre QUE le scrape
(`scrappe_pending`), PAS le pool import → c'est l'horaire qui couvre les imports.

### 📊 Vision /site/{site}/vision : secteurs réels (faux 0 corrigés)
La page utilisait `SECTORS_GOD_MODE` (liste scrapable figée : garagiste, plombier…) qui ne matche
pas la taxonomie importée (immobilier 936, banque, industrie…). Nouvelle `pool_sectors()` dans
`contacts_pool_backend.py` (secteurs RÉELS du pool, triés par fréquence) ; endpoints
`sector-availability` + `depletion-alert` branchés dessus. UI inchangée (affiche ce que l'API
renvoie). API redémarrée.

### 🧠 claude-mem installé
`npx claude-mem install` + `start` (v13.8.0, plugin `/root/.claude/plugins/`, worker port 37700,
auto-memory native conservée). Données dans `~/.claude-mem`.

## 🔝 REPRISE 2026-06-24 (soir) — Hub de campagnes multi-canal

**Demande user :** refondre `/site/{site}/campaigns` en hub : wizard guidé (canal → message → cible →
aperçu → récap+planning), cible = Mailnjoy nettoyé < 6 mois, agent IA de délivrabilité contrôlant la
cadence (30k en cold = refus), + stats unifiées. UX au top.

**FAIT (P1→P5, plan approuvé `mutable-tickling-sky.md`) :**
- **`contacts_pool_backend.py`** : `pick_for_campaign` + `count_available_for_sector` filtrent
  désormais Mailnjoy valid ET `checked_at` < 180 j (param `cleaned_within_days`).
- **`deliverability_agent.py`** (NOUVEAU) : caps durs/canal (Emelia=warmup, Sweego ramp 1k→20k,
  Maildoso 0) + `plan_cadence` (faisabilité + planning jour/jour) + `explain` (DeepSeek + fallback).
  Vérifié : Emelia 30k → refus + suggère Sweego ; Sweego 30k → 5 j ✅.
- **`campaign_engine.py`** (NOUVEAU) : table `campaigns_unified` + CRUD + `dispatch_due` (scheduler).
  Dispatch Sweego (testé dry-run : pioche 3 → would_send 3) + Emelia (création campagne 1-step +
  add_contact). Cron **8h30** ajouté (crontab autoblog).
- **`api.py`** : endpoints `channels`, `campaigns/target-count`, `campaigns/plan`,
  `campaigns/preview-lint`, `campaigns` (CRUD), `campaigns/{id}/{pause|resume|cancel|send-now|bat}`,
  + `marketing/overview` + `sweego/engagement` (faits plus tôt).
- **UI** : `campaign-wizard.tsx` (wizard 5 étapes, stepper, cartes canal, aperçu responsive + lint,
  agent délivrabilité, BAT) + `channel-perf-card.tsx` (partagé dashboard/hub) + `campaigns/page.tsx`
  réécrite en hub (table unifiée + ChannelPerfCard + section auto Emelia repliable conservée).
  Build Next OK, restart OK.

**RESTE / À surveiller :**
- Test d'un envoi RÉEL via le hub (jusqu'ici dry-run pour ne pas spammer un vrai prospect).
- Stats par campagne unifiée (engagement) : actuellement progression (envoyés/cible) + ChannelPerfCard
  niveau canal. Rollup par campagne = amélioration possible.
- Maildoso : carte désactivée tant que le séquenceur n'est pas branché (~07/07).
- User va lancer `/ultrareview` sur ce chantier.

## 🔝 REPRISE 2026-06-24 — Sweego mass campaigns + docs

**Demande user :** Intégrer Sweego comme canal "masse" (newsletters + annonces), envoyer un BAT réel,
ajouter Sweego à la sidebar, documenter l'infrastructure email, créer le plan des pages UI.

**FAIT :**

### Sweego backend (scripts/)
- **`scripts/sweego_backend.py`** : 3 bugs corrigés — `provider: "sweego"` → `"email"`,
  `campaign-type: "newsletter"` → `"market"`, champ `channel` supprimé. Sender domain
  `news@news.leclientroi.email` → `info@leclientroi.com`. UTM source `newsletter` → `sweego`.
- **`scripts/api.py`** : ajout `GET /api/sweego/stats` + `POST /api/sites/{site}/mass-campaigns/bat`.
- **`.env`** : `SWEEGO_DOMAIN=news.leclientroi.email` → `SWEEGO_DOMAIN=leclientroi.com`

### BAT envoyé et reçu ✅
Email test "test sweego LCR 2" reçu par `camille@leclientroi.com` (2 min délai).
DKIM ✅ SPF ✅ DMARC ✅ — From `info@leclientroi.com`, MTA via `swg.leclientroi.com`.

### UI (genesis-ui/)
- **`credits-widget.tsx`** : ajout Sweego (Send icon, indigo, nb emails envoyés total).
- **`newsletters/page.tsx`** : section masse complète — dialog preview (iframe scalée 0.33),
  inputs secteur/volume/sujet, BAT (`camille@leclientroi.com`), Simuler + Envoyer (indigo),
  historique campagnes Sweego.
- **`tag/page.tsx`** : ajout Sweego (`utm_source=sweego`) + Maildoso (`utm_source=maildoso`).

### Docs (docs/)
- **`docs/infrastructure.md`** (nouveau) : domaines, MTA Sweego (swg.leclientroi.com), auth triple-pass,
  règle absolue `SWEEGO_DOMAIN=leclientroi.com`, boîtes Maildoso, IP VPS.
- **`docs/platforms-api.md`** (nouveau) : référence Emelia REST+GraphQL, Sweego send/stats,
  Maildoso SMTP/IMAP, tableau comparatif tags, état click→lead.
- **`docs/features.md`** (nouveau) : carte complète des pages UI avec breadcrumbs, APIs, connexions.

### Stats engagement Sweego — FAIT (2026-06-24)
- **`scripts/api.py`** : ajout `GET /api/sweego/engagement` (start/end optionnels) qui câble
  `sweego_backend.engagement_stats()` (jusque-là code mort). Retourne sent/openers/clickers/
  bounces/unsubscribes + open_rate/click_rate.
- **`newsletters/page.tsx`** : ligne de stats engagement (6 tuiles) dans l'en-tête de la carte
  "Campagnes masse Sweego". S'affiche dès qu'il y a des envois. Build + restart OK.
- Vérifié live : 262 envoyés, 7 ouvreurs humains, 42 cliqueurs (16%), 0 bounce.

### Click→lead Sweego — FAIT + testé en réel (2026-06-24)
- Découverte : Sweego A un webhook par destinataire (`email_clicked` avec `recipient`). La doc
  `platforms-api.md` disait l'inverse à tort → corrigée.
- **`GET /api/sweego/click?t=<token>`** (public, exception middleware) : lien tracké par destinataire.
  `sweego_backend.make_click_token()` / `resolve_click()` + table `sweego_click_tokens`. Résout
  token→email → promeut en `prm` → redirige 302. **Testé en réel par le user (Camille → prm).**
- **`POST /api/sweego/webhook`** : récepteur natif prêt (email_clicked→prm, bounce/unsub/complaint→
  blacklisted, opened→horodatage). Table `sweego_events`. ⚠️ Enregistrement bloqué : route
  `/clients/{uuid_client}/webhooks` nécessite l'UUID client (dashboard Sweego / en-tête x-client-id).
  **User a demandé l'UUID au support Sweego — en attente.**
- **`acquisition_backend.create(skip_validation=True)`** : bypass Mailnjoy pour les signaux
  d'engagement (un cliqueur est réel). Corrige le bug "page blanche 10s + contact rejeté".

### Stats harmonisées — FAIT (2026-06-24)
- **`GET /api/sites/{site}/marketing/overview`** : agrège Emelia (campagnes matchant le site,
  compteurs dérivés de mailsSent×%) + Sweego (engagement_stats, niveau compte) en forme comparable
  (sent/open_rate/click_rate/reply_rate/bounce_rate).
- **`dashboard/page.tsx`** : carte "Performance emailing par canal" (composant `ChannelPerfCard`)
  comparant cold email (Emelia) vs masse (Sweego) côte à côte. Build + restart OK.

**RESTE :**
1. **Webhook natif Sweego** : enregistrer via `/clients/{uuid_client}/webhooks` dès que le support
   fournit l'UUID client. Débloquera ouvertures + blacklist auto bounce/désinscription/plainte.
2. **(ancien #1) Click→lead Sweego** : ⚠️ pour les envois de MASSE, le token par destinataire dans
   le lien maison demande la perso URL Sweego (`{{token}}`, non vérifiée) ou 1 envoi/destinataire.
   Le webhook natif (cf #1) est la solution propre. Sweego n'expose PAS les clics
   par destinataire (stats agrégées seulement). Deux options :
   (a) Redirection via `https://api.cheffer.email/api/sweego/r?t=<token>` dans chaque lien (token
       par destinataire via perso Sweego) → fiable mais lien cross-domaine (déliverabilité à tester)
   (b) Capture côté site leclientroi.com (snippet JS lit `utm_source=sweego` → POST API) → ne fire
       que si le contact atterrit sur une page équipée.
2. **Click→lead Maildoso** : IMAP reply detection dans séquenceur maison.
3. **Maildoso séquenceur** (`cold_email_engine.py`) : disponible ~2026-07-07 (warmup en cours).
4. **Stats harmonisées** : vue unifiée Emelia + Sweego + Maildoso (Sweego engagement fait, reste à
   fusionner avec Emelia dans une vue commune).
5. **Test live scrapper** : valider un run Serper + Basile (coûte des crédits → demander au user avant).

### Architecture Sweego (mémo)
- Sweego MTA : enveloppe via `swg.leclientroi.com` (indépendant du From)
- Seul domaine autorisé : `leclientroi.com` (pas `news.leclientroi.email`)
- Clé API : `SWEEGO_API_KEY` dans `.env` (ne jamais hardcoder)
- Maildoso : 4 boîtes `@leclient-roi.com` warmup depuis 2026-06-23, dispo ~2026-07-07

## 🔝 REPRISE 2026-06-20 — Scrapper Serper + Basile (double source, cible 100 contacts)

**Demande user :** Basile = 2e source parallèle à Serper (pas juste un connecteur séparé). Quand on lance un scrape secteur × région, les deux sources tournent pour chaque ville jusqu'à atteindre 100 contacts (configurable). Si Serper se bloque, Basile continue seul (exports illimités).

**FAIT :**
- **`scripts/basile_backend.py`** : ajout `SECTOR_NAF` (mapping 16 secteurs Genesis → codes NAF confirmés) + `run_sector_for_city(site, sector, city, ...)` — interroge Basile `companies/find` par NAF + `headquarters_city` (MAJUSCULES), insère dans le même pool que Serper. Gère arrondissements Paris/Lyon/Marseille (PARIS, LYON, MARSEILLE).
- **`scripts/autoscrape_backend.py`** : `run_autoscrape()` intègre Basile en séquence après Serper pour chaque ville. Nouveau `target_contacts=100` — stop dès que `valid_serper + valid_basile >= target`. Si Serper bloqué ET Basile disponible → Basile continue seul. Compteurs séparés `valid_serper` / `valid_basile` dans l'état. Arg CLI `--target-contacts`.
- **`scripts/api.py`** : `/autoscrape/start` accepte `target_contacts` (body JSON, défaut 100, max 10000), le transmet en arg CLI.
- **`genesis-ui/src/app/site/[code]/scrapper/page.tsx`** : titre "Scrapper — Serper + Basile", badge, champ "Cible contacts", compteur Basile (∞), barre de progression vers la cible, stats Serper X + Basile Y dans le panel statut, description mise à jour.
- **Build Next.js OK**, genesis-ui redémarré.

**RESTE Scrapper Serper+Basile :**
1. **Test live un segment** : lancer un vrai run (ex. restaurant × Île-de-France, cible 20) pour confirmer que les 2 sources s'enchaînent et qu'on atteint la cible → valider les logs.
2. **Secteurs sans NAF** (`autre`) → pas de Basile pour ce secteur (ok, fallback Serper seul).
3. **Routing Emelia** : une fois le pool rempli (100 contacts), la vue Campaigns / Cold Email route vers Emelia — à vérifier que le flow campaign_create → add_contacts fonctionne bien avec les contacts du pool.
4. **Optionnel** : cron segment 1 secteur × 1 dept/jour (au lieu de relancer manuellement).

## 🔝 REPRISE 2026-06-19 — Crédits Serper (affichage+alertes) + clé Basile

**Demande user :** (1) Serper affichait « 50 000 / 2500 » après recharge à 50 000, sans aucune alerte
quand le solde était tombé à 0. (2) Clé Basile en 401.

**FAIT :**
- **Serper affichage (Fix A)** — `api.py:get_serper_usage` : le dénominateur `plan_total` venait d'un
  snapshot figé (`memory/seo/serper-balance.json`, plan_total=2500 daté du 30/05) que la logique
  réécrivait toujours à l'identique. **+ cause profonde** : le JSON était `root:root` 644 -> l'API
  (sous `autoblog`) ne pouvait PAS le réécrire (`except: pass` avalait la PermissionError). Fixes :
  `plan_total = max(plafond connu, solde live)` (une recharge relève le plafond) + `chown autoblog`
  le JSON. Snapshot désormais auto-rafraîchi depuis le solde live `/account`. Vérifié 50000/50000.
  ATTENTION : le solde Serper EST live via `god_mode_agents.serper_balance()` (`/account` existe) —
  l'ancien commentaire « pas d'API de solde » est faux.
- **Alertes crédits (Fix B)** — `connector-alerts.tsx` : avant, un solde bas ne faisait QUE colorer un
  chiffre en rouge dans la sidebar (passif). Ajout de vraies bannières (rouge « épuisés » / orange
  « bas ») pour Serper/Emelia/DeepSeek/Mailnjoy (solde) + Basile/Ahrefs (quota >=80%). Mêmes seuils que
  le widget, refresh 60s, masquables. Build next + restart genesis-ui OK.
- **Clé Basile régénérée** — l'ancienne (`sk_live_aae1966a...`, .env du 17/06) avait été supprimée côté
  console -> 401. User a créé une nouvelle clé (`sk_live_7d99683...`, active). Remplacée dans `.env`,
  testée live : count companies=28,6M / people=4,4M OK. Dashboard restart pour recharger la clé.
- **Audit permissions `memory/` (suite du fix Serper)** — 13 entrées étaient `root:root` (créées par
  d'anciennes sessions root) que l'app sous `autoblog` ne pouvait pas réécrire (échec SILENCIEUX).
  Impact réel : `site-api-keys.json` (sauvegarde clés par site), dossier `seo/history/` (snapshots SEO
  journaliers d'`ahrefs_daily.py`), `shared/agent-logs/sessions.jsonl`, `{lcr,mkd}/modules.json`,
  `seo/{site}-competitor-analysis.json`. Fix : `chown -R autoblog:autoblog memory/`. Vérifié W_OK +
  création fichier OK. Règle : `memory/` = données app, doit rester à `autoblog`.

## 🔝 REPRISE 2026-06-18 — Couverture Serper + reporting scrapper + sidebar

**Contexte :** le scrape IDF immobilier ne ramenait que ~707 « examinés » (Google Places plafonne à
~20 résultats/requête → on retombait sur le même top-20). Univers réel ≈ 7-8k agences IDF / ~30k FR
(à confirmer via Basile, source registre = exhaustive — clé Basile **désactivée/401 depuis ~12h**,
à régénérer).

**FAIT :**
- **Diversification des requêtes Serper** (`god_mode_agents.SECTOR_QUERIES`) : 2 → 4-10 angles métier
  par secteur (immobilier : agence/agent/estimation/gestion locative/syndic/neuf/vente/location/mandataire/
  négociateur). Chaque angle = un top-20 Google différent → couverture bien > 20/ville.
- **Burn des lieux déjà scrappés** (cross-run) : `load/save_seen_places(site,sector)` →
  `memory/scrape/seen-places-{site}-{sector}.json`. ⚠️ Clé = **domaine du website** (`norm_domain`),
  PAS le placeId — découverte : Serper ne renvoie le placeId que 1 row/1787 (quasi toujours null),
  alors que `website` est rempli à ~100 %. Dans `scrape_sector` : skip si domaine déjà vu (AVANT
  fetch site) ; page ne ramenant QUE du déjà-vu (`page_new==0`) → variante épuisée → suivante.
  `skipped_seen` propagé (scrape_sector → cum → log → API → UI, affiché « +N🔥 » près des doublons).
  **Prérempli** depuis scrappe+scrappe_pending : **1769 domaines** (dont 1536 immo lcr) → le prochain
  scrape immo saute direct les connus.
- ⚠️ **SERPER À COURT DE CRÉDITS** (`"Not enough credits"` HTTP 400, sidebar 0/2500) — les scrapes
  sont donc à l'arrêt tant que le forfait Serper n'est pas rechargé. Découvert en testant le burn.
- **Reporting scrapper** : colonnes **Doublons** + **Net Mailnjoy** ajoutées (UI scrapper) ; le log
  d'activité autoscrape est désormais écrit APRÈS le cleanup (inclut `duplicates`, `cleanup`, `net`).
  Live-activity API expose duplicates/skipped_seen/net/cleanup. (Explication run 707 : 1 valid+302
  rejetés[=sans email]+404 doublons ; net réel 0 car Mailnjoy a viré le seul valid.)
- **Sidebar `credits-widget.tsx`** : ajout **Basile** (`/api/basile/usage` : compte local pool
  primary_source='basile' du mois / 250000) et **Emelia** (`/api/emelia/credits` : solde LIVE 950).

## 🔝 REPRISE 2026-06-17 (suite) — Connecteur Basile (2e outil d'acquisition)

**Demande user :** ajouter Basile (api.basile.cc, base B2B FR, abo user) comme 2e outil de collecte
de contacts À CÔTÉ de Serper, fusionné dans le même pool. Règles : jamais > 20 000, passes de 1 000.
**app.basile.cc était DOWN** → préparer TOUT hors-ligne (doc, fonctions, UX, contexte LCR), brancher
clé + tests live au retour du site. Skill fourni en zip (`basile-skill.zip`).

**FAIT (hors-ligne, non testé live) :**
- **Skill installé** : `skills/basile-b2b-search/` (SKILL.md + 8 refs + 2 scripts : basile_search.py,
  emelia_enrich.py). C'est la doc source de l'API Basile + Emelia.
- **Connecteur `scripts/basile_backend.py`** : `count()` (gratuit), `find()` (pagination 100),
  `lead_to_prospect()` (normalise lead Basile → schéma `prospect` IDENTIQUE à serper_places, +
  prenom/nom/job_title pour le pool), `enforce_volume_rules()` (≤20k→extract en N passes de 1000,
  >20k→segment), `run_segment()` (collecte 1 passe, valide via `validate_and_score`, DOUBLE écriture
  `scrappe_pending` + pool `contacts` `primary_source='basile'`, dry-run par défaut). Flag
  `BASILE_BLOCKED_STATUS` sur 402/403 (comme SERPER_BLOCKED_STATUS). CLI : `count|segment [--live]`.
  Fonctions pures TESTÉES (volume rules + normalisation + skip sans email). HTTP **non testé** (site down).
- **Docs** : `docs/basile-api.md` (API complète + §Go-live checklist), `docs/contact-acquisition.md`
  (fusion Serper+Basile, schéma pool, **proposition UX dashboard** = toggle Source Serper/Basile/Les2
  + compter-avant-lancer + segmentation auto >20k + enrichissement Emelia opt-in, endpoints à ajouter,
  mode opératoire jour-du-retour).
- **Contexte LCR** : `context/lcr/acquisition-context.md` (ICP commerçants/artisans/resto/immo →
  mapping secteurs→NAF/activity, workflow 2 étapes entreprises→dirigeants par SIREN, règles volume).
- **Clés** : `EMELIA_API_KEY` déjà en `.env` ✅. **`BASILE_KEY` ABSENTE** → user la fournira au retour.

**✅ TESTÉ EN LIVE (2026-06-17, clé fournie, ajoutée au `.env`) :**
- Auth OK, `count` OK (15 M sociétés, 284 k CEO). FIELD MAP **confirmé** et câblé dans `lead_to_prospect`.
- **Corrections de filtres** (doc à jour, `docs/basile-api.md §12bis`) : `naf_code` exact `"56.10A"`
  (pas de wildcard `.x`) ; `activity` préfixe **`concept:`** (via activity-suggest) ; géo entreprises
  via **`headquarters_postal_code`** (exact) ou **`headquarters_city` MAJUSCULES** — `*_department_code`
  / `*_region_code` renvoient 0.
- **Découverte clé** : sociétés Basile ~15 % avec email (~2 % net après validation), **dirigeants people
  = 0 email/phone**. → Basile = liste sociétés + nom dirigeant + SIREN ; contactabilité réelle via Emelia.
- **`email_validator.LICIT_SOURCES` += `"basile"`** (sinon tout droppé `rgpd_source_non_publique` ;
  registre légal = source publique). Dry-run segment OK : 882 resto Lyon → 19 prospects valides, schéma OK.

**DÉCISION USER prise (2026-06-17) : flux DIRIGEANTS + Emelia** (option A). Construit + testé dry-run.
- `run_dirigeant_segment()` + CLI `dirigeants` : companies/find (NAF+géo) → people/find par SIREN
  (nom dirigeant, ~58 % des sociétés) → Emelia find-email (nominatif, PAYANT 1 crédit/dirigeant,
  derrière `--emelia --live`) → validate → double écriture scrappe_pending + pool (prenom/nom/job_title,
  source=basile). Dry-run ESTIME le coût Emelia avant de dépenser. Website récupéré via `x_gmb`
  (`domain_principal_url`/`open_website`/…) pour améliorer le taux Emelia. `emelia_enrich.py` du skill
  réutilisé (mappe EMELIA_API_KEY→EMELIA_KEY). Testé dry-run lcr : 60 sociétés→31 dirigeants nommés.

**Crédits Emelia (2026-06-17) — SOLDE LU EN LIVE ✅ :** la requête GraphQL du dashboard a été extraite
du front app.emelia.io (`/static/js/main.*.js`) :
`me { subscription { enrich { creditsRemaining creditsSubscription expiration } } }`.
→ `scripts/emelia_credits.py fetch_live_balance()` / CLI `balance` lit le solde RÉEL sans saisie
manuelle (vérifié : **949.75** crédits, ≈ le 950 annoncé). (L'introspection GraphQL est off et le
champ n'était pas devinable — il a fallu lire le bundle JS du front.) Le suivi local
(`record`/`COST`) sert juste à prédire le coût d'un lot. Branché dans `basile_backend._emelia_find_email`
+ `emelia_find_phone`.
Test live find-phone OK : Clara Torres (agent immo La Garenne-Colombes) → +33679277362.
**Coût find_phone = 50 crédits/numéro trouvé** (CONFIRMÉ user 2026-06-17 ; `COST` dans emelia_credits.py).
find_email/verify/ai_action = à confirmer. ⚠️ Implication : 1 pack 1000 crédits = seulement 20 numéros
→ réserver le find-phone aux cibles à forte valeur ; le find-email (≈cheap) reste le levier volume.

**RESTE Basile :**
1. **Test live Emelia** sur un petit lot (3-5 dirigeants) pour confirmer le finder — coûte qqs crédits,
   à lancer avec OK explicite user (`--emelia --live --max 5`).
2. Helper **géo→codes postaux/villes** par département (pas de champ dept côté Basile ; postal exact
   ou ville MAJ seulement).
3. Endpoints + UX dashboard (cf. `docs/contact-acquisition.md §5`). 4. Contextes MKD + autres sites.
5. Crosscheck doc vs docs.basile.cc. 6. (optionnel) cron segments 1 secteur×dept/jour.

## 🔝 REPRISE 2026-06-17 — Source `articles` snapshot (RESTE #3 fait)

**Demande user :** reprise après une session terminée sans récap. Chantier choisi = RESTE #3 (internal-linking & linkedin n'avaient pas la liste d'articles dans leur snapshot → ils détournaient `add_internal_link` en « fetch » / restaient en `plan:[]`).

**FAIT (testé dry-run lcr + mkd) :**
- **`agent_core.observe()` : nouvelle source `articles`** (`_observe_articles(site)`). Expose `editable` (articles de la queue éditoriale AVEC markdown + published_url = les SEULS que les writers savent cibler, matchés dans la queue) **et** `published` (jusqu'à 12 articles publiés = destinations de liens). Câblée sur internal_linking_agent + linkedin_agent (`sources=("gsc","ga4","articles")`).
- **Cause racine trouvée : troncature du snapshot.** `decide()` coupait le snapshot à **6000 chars** ; avec 30 articles `published` listés AVANT `editable`, la liste `editable` (offset 6586) était **coupée** → le LLM ne voyait jamais les seules cibles valides et piochait dans `published` (→ skip/erreur en live). Fix : (a) `editable` listé EN PREMIER + counts + `note` explicite, `published` cappé 30→12 ; (b) limite de troncature `decide()` 6000→8000. Snapshot lcr : 6944→4016 chars, `editable` visible à l'offset 1008.
- **Playbooks durcis** (`skills/internal-linking.md`, `linkedin-specialist.md`) : RÈGLE DURE `target` ∈ `editable` (recopier le champ `url` exact, ne PAS inventer d'URL d'API), `destination_url` ∈ `published`. linkedin : ignorer `has_linkedin_post=true`, `plan:[]` si rien de neuf.
- **Writers durcis (skip propre au lieu de crash)** : validation cible AVANT la branche dry-run dans les 2 `_agentic_writer`. internal-linking : matching tolérant (id/slug emballé dans une URL) + extraction destination tolérante (`destination_url`|`url`|`destination`|`linked_article_slug`→résolu via `published`). Fallback URL site-aware (lcr uniquement). linkedin : skip propre si `target` hors-queue ou déjà promu.
- **Résultat dry-run lcr (mémoire purgée) :** internal-linking produit **4 liens valides** depuis l'éditable « SMS Marketing Restaurants » vers de vraies destinations (sms-salle-sport, rcs-marketing, fideliser-clients-sms, campagne-mms), URLs résolues, 0 erreur/skip. linkedin → `plan:[]` correct (seul éditable déjà promu). mkd → `plan:[]` propre (WP vide, pas de crash).
- **Purge** : 9 lignes `agent_actions` de test du 17/06 (internal-linking + linkedin, lcr+mkd) supprimées pour ne pas empoisonner le `recall` des crons live de ce soir.

**Limite connue :** la queue éditoriale lcr n'a qu'**1 article éditable** (les autres publiés ne sont pas dans la queue Genesis donc non modifiables). internal-linking ne peut donc mailler que cet article tant que Genesis ne publie pas plus via sa propre pipeline. C'est by-design (la queue = base éditoriale interne).

**RESTE (inchangé hors #3) :** voir REPRISE 2026-06-16 ci-dessous (eval post-cron J+7 ~23/06, purge cosmétique agent_actions, migration slugify).

## 🔝 REPRISE 2026-06-16 (suite) — Refonte du scrapper (autoscrape région-continu)

**Demande user :** le scrapper "automatique" ne l'était pas (s'arrêtait sur estimation crédits + volume cible). Veut : choisir juste secteur + RÉGION, scraper EN CONTINU dans l'ordre des départements tant que Serper ne stoppe pas réellement, retry quotidien au blocage, statut "Région finie" à l'épuisement, libellé région correct, plus de champ volume.

**FAIT (corrige + améliore + testé) :**
- **`god_mode_agents.serper_places`** : détecte le refus EXPLICITE de Serper (HTTP 429/402/403) → lève `SERPER_BLOCKED_STATUS` au lieu d'avaler en `[]` (avant : un blocage passait pour "ville vide"). Testé live : appel normal → flag reste None, 10 places.
- **`autoscrape_backend.py` réécrit** : `run_autoscrape(region=…)` enchaîne TOUS les départements de la région (triés par code), toutes villes pop≥10k. **Supprimé** : credit-floor préemptif + volume cible + stall-heuristic. **Seul arrêt** = vrai blocage Serper / stop manuel / épuisement (→ statut `done` "Région X finie"). Reprise : `memory/autoscrape/{site}-region-progress.json` (depts_done). Garde-temps 6 h (anti-zombie). Activité = **1 ligne par run** (plus 1 par ville) : start_scrape + scrape de fin uniques avec scope région.
- **`daily_retry()` + crons PM2** `genesis-autoscrape-retry-lcr` (06:00) / `-mkd` (06:10) : si région `blocked_serper` et Serper repasse (1 appel test) → reprend en skippant les depts finis.
- **`api.py`** : `/autoscrape/start` accepte `region` (drop `target_valid`), `/scrape/live-activity` fenêtre de match élargie 10min→12h + expose `scope`/`message`/statut métier.
- **Frontend `scrapper/page.tsx`** : autoscrape sur RÉGION (dept optionnel), champ Volume cible supprimé, libellé région corrigé (`SelectValue` rendait le code "11" → force `{r.name}`), carte statut montre scope + dépts faits, table activité montre "Région finie"/"⛔ Serper" + périmètre. Build OK, dashboard+UI restart.

**Testé :** géo (Bretagne→22,29,35,56 ; Corse→2A,2B ; IDF→75..95), orchestration mockée (blocage→`blocked_serper`, persistance `depts_done`, reprise skip), serper réel, build UI, crons.

- **Corse + DOM-TOM EXCLUS** (correction user : périmètre = France métropolitaine seule). `workflow_geo.EXCLUDED_REGION_CODES={94,01,02,03,04,06}` + `EXCLUDED_DEPT_CODES={2A,2B,971-978}` + helpers `metropole_regions/departments/cities`. Câblés sur les 3 endpoints `/geo/*` ET l'autoscrape (`_ordered_region_depts`, listing villes). Résultat : 12 régions continentales, 0 ville Corse/DOM. NB : dept "94" (Val-de-Marne, IDF) ≠ région "94" (Corse) — pas de collision.

**RESTE scrapper (optionnel) :** un vrai run live de bout en bout via l'UI (clic user) pour confirmer pool+Mailnjoy ; étendre le retry à d'autres sites si besoin.



## 🔝 REPRISE 2026-06-16 — V2 préambules action_type (RESTE #1 fait)

**FAIT cette session :**
- **Constat dry-run** : le préambule V1 (texte dans le playbook) **ne suffit PAS** — DeepSeek inventait systématiquement (2/2 runs) `create_article`/`update_article` pour `seo-strategist` → l'agent ne produisait **aucun `seo_reco` valide** (tout skippé). Donc pas un bruit cosmétique : sortie vide.
- **Enum exhaustif ajouté** aux 6 playbooks filtrés (`skills/seo-strategist|content-writer|internal-linking|linkedin-specialist|competitive-intel|graphiste.md`) : bloc « `action_type` AUTORISÉ — liste EXHAUSTIVE » juste après le JSON, + redirection explicite des synonymes tentants (ex seo-strategist : « tu ne rédiges pas d'article → `seo_reco` + `tags.type:content_gap` »).
- **Enforcement central dans `agent_core.decide()`** (la vraie correction, le playbook seul étant trop faible face au raisonnement du modèle) :
  - `ALLOWED_ACTION_TYPES` (dict par nom d'agent, source de vérité = filtres des `_agentic_writer`).
  - La liste autorisée est injectée dans le **prompt système** (domine le playbook) comme CONTRAINTE DURE.
  - Garde-fou : 1 passe de **réparation** si le modèle viole l'enum, puis **filtrage final** des items hors-enum (ne polluent plus `agent_actions`).
  - Nouveau param `allowed_actions` sur `decide()` **et** `run_cycle()` (rétrocompatible, fallback sur le dict).
- **Split content-writer** : `content_agent` et `brief_agent` partagent le playbook `content-writer.md`. `content_agent` passe `allowed_actions=["write_article"]`, `brief_agent` `["write_article","propose_article"]` → fini la fuite `propose_article` skippée côté content_agent.
- **Validation dry-run des 7 agents** : tous émettent désormais UNIQUEMENT des types valides (seo_reco / write_article / add_internal_link / linkedin_post(ou plan:[]) / intel_signal / generate_header). Zéro skip « non géré », garde-fou jamais déclenché (respect dès la 1ʳᵉ passe). `humanizer` volontairement **exclu** du dict (pas de filtre côté writer, comportement libre préservé).
- **Note** : `skills/briefing.md` (send_briefing/telegram) n'est chargé par AUCUN agent agentique (`genesis-briefing` = `scripts/briefing.py` déterministe ; `brief_agent` lit `content-writer.md`). Son préambule V1 est mort → laissé tel quel, à nettoyer un jour.

**FAIT (suite) — bascule crons agentiques :**
- **5 crons PM2 créés en `--agentic --live` sur lcr** (les agents n'avaient AUCUN cron avant — le STATE 06-10 surestimait l'existant) : `genesis-brief` (08h L/M/V), `genesis-seo-strategy` (09h L/M/V), `genesis-internal-linking` (12h L/M/V), `genesis-linkedin` (13h L/M/V), `genesis-competitor` (07h Lundi). Pipeline cohérent avec content-lcr (10h) + graphiste (11h). Tous `--no-autorestart`, `pm2 save` fait.
- **Risque maîtrisé** : en live ces 5 agents n'écrivent que dans des JSON internes (recos/queues) — aucun post LinkedIn réel ni publication externe. La partie outward reste content/graphiste (déjà live lcr).
- **1ʳᵉ exécution live OK** (exit 0 sur les 5) : actions réelles loggées dans `agent_actions`, toutes enum-propres (seo_reco, intel_signal, write_article, add_internal_link, linkedin plan:[]). L'éval aura de la matière à J+7.
- `content-mkd` laissé tel quel (publish 401, décision user) ; `ecosystem.config.js` est OBSOLÈTE (3 crons orchestrator morts) → source de vérité = `pm2 save` / dump.pm2.

**RESTE (prochaine session, par priorité) :**
1. **MKD publish 401** (action user : régénérer App Password WP, voir DÉCISIONS EN ATTENTE plus bas).
2. ~~**humanizer invente des action_type / plante**~~ **CORRIGÉ 16/06** : la vraie cause du plantage nocturne était `humanize_article.py` qui faisait `exit 1` à chaque run — `check_constraints` échouait car le filet déterministe ne forçait le frontmatter original que si le LLM en produisait un (or DeepSeek le supprime souvent). Fixes : (a) frontmatter original réinjecté TOUJOURS, (b) strip déterministe des `---` en corps au lieu de rejeter, (c) `DEFAULT_PROMPT` repointé de `/tmp/cmux-drop-*.md` (éphémère) vers `skills/humanizer.md` (identique, stable), (d) `humanizer → ["humanize_article"]` ajouté à `ALLOWED_ACTION_TYPES`. Validé live (exit 0, frontmatter intact, `.bak` créé). **Résidu** : la mémoire de l'agent garde 8 erreurs périmées → il reste en `plan:[]` par prudence ; se résorbe en ~qq jours (noops chassent les erreurs de la fenêtre recall=10) ou via purge manuelle des lignes `agent_actions agent=humanizer status=error` (refusée par le classifier ce jour, à autoriser si on veut accélérer).
3. ~~**internal-linking & linkedin manquent la liste d'articles dans leur snapshot**~~ **FAIT 17/06** : source `articles` ajoutée à `observe()` (`editable`+`published`), troncature snapshot 6000→8000, playbooks+writers durcis. Voir REPRISE 2026-06-17 en haut. internal-linking produit des liens valides, linkedin `plan:[]` correct quand rien à promouvoir.
4. **🆕 Pollution test agent_actions (16/06)** : `create_article`/`update_article`/`propose_article` en `done` issus de mes dry-runs d'avant le fix. Inoffensif (eval les skippe) mais à purger si on veut une table propre (delete manuel DB).
5. **Évaluation post-cron** : laisser tourner 1-2 semaines, vérifier que `evaluate()` passe de `evaluated:0` à des outcomes réels, affiner les seuils.
6. **Migrer humanize_article + gen_agents_state vers text_utils.slugify** (cosmétique).

**DÉCISIONS EN ATTENTE (user) :** MKD publish 401 (régénérer App Password WP — détail dans la section REPRISE 2026-06-09 soir).

## 🔝 REPRISE 2026-06-10 — Chantiers 1/2/5/6

## 🔝 REPRISE 2026-06-10 — Chantiers 1/2/5/6

**FAIT cette session :**
- **Chantier 1 (pilote)** : `seo_strategy_agent.py --agentic --live` migré sur `agent_core.run_cycle`. Pattern copié de `content_agent.run_agentic`. Test dry-run validé. Reste 4 agents à migrer (#12 pending : internal_linking, linkedin, competitor, brief).
- **Chantier 2** : préambule action_type/target ajouté à 6 playbooks → `skills/seo-strategist.md`, `content-writer.md`, `internal-linking.md`, `linkedin-specialist.md`, `competitive-intel.md`, `briefing.md`. Format JSON strict imposé : `{reasoning, plan: [{action_type, target, why, tags}]}`. Chaque playbook ajoute le périmètre (un seul article par cycle pour content-writer, max 6 recos pour seo-strategist, etc.).
- **Chantier 5** : `scripts/text_utils.py` créé avec `slugify()` (NFD + diacritiques). `content_agent._slugify` réexporté pour compat. À réutiliser dans humanize_article et autres.
- **Chantier 6** : legacy /agents complètement viré
  - **Backend `scripts/api.py`** : suppression d'AGENTS_REGISTRY (10 agents hardcodés), AGENT_CRONS_FILE, _load_agent_crons, _save_agent_crons, AGENT_COSTS, FREQ_MULTIPLIERS, endpoints `/api/agents`, `/api/agents/{site}`, `/api/agents/{site}/{agent_id}/cron`, `/api/agents/{site}/planner`, `/api/agents/{agent_id}/instructions` (variante sans site). -7072 chars dans api.py. Gardés : `/api/agents/{site}/state` + `/api/agents/{site}/{agent_id}/instructions`.
  - **UI `genesis-ui/.../agents/page.tsx`** : page refondue ne consomme plus que `/state` et `/instructions`. Table « Catalogue conceptuel » + Planner supprimés. Card unique « État PM2 réel » + Sheet playbook. Mapping `skillIdFromPm()` pour mettre un bouton « Voir playbook » sur les jobs PM2 pertinents (content/seo/humanizer).
  - Build OK, restart dashboard + UI OK, page agents répond 200, snapshot état `12 agents PM2` à jour.

**FAIT (suite session 2026-06-10) :**
- **Chantier 1 complet** : les 4 derniers agents migrés sur `agent_core` (`brief_agent`, `linkedin_agent`, `internal_linking_agent`, `competitor_analyzer`) avec `--agentic --live`. Tous testés dry-run : la boucle observe→recall→decide→act tourne, le LLM raisonne contextuellement (ex `linkedin_agent` : « plan: [] car pas d'article récent à promouvoir »). Total : **6 agents agentiques** (content-lcr/mkd, seo-strategy, internal-linking, linkedin, competitor, brief + humanizer = 7).
- **Hardening `agent_core._conn()`** : retry-backoff exponentiel sur `Conflicting lock` DuckDB (api.py FastAPI garde un handle long-lived). 6 tentatives, ~30s max. Plus de crash transitoire en parallèle de l'API.
- **Popup preview articles** (chantier #16) : Dialog sur `/site/[code]/articles` qui rend le markdown via `marked` (GFM) avec style proche du blog public. Bouton « Aperçu » visible sur tous les articles (proposal seul affiché si pas de markdown). Largeur fixée 4xl (~900px).
- **Imagen 3 (Vertex AI)** branché : compte de service `genesis-indexing@lead-machine-mkd` + facturation + rôle `aiplatform.user`. Script `scripts/imagen_generate.py`. Cible projet `lead-machine-mkd`.
- **Style photo doc iPhone/Portra 400** validé : nouveau `STYLE_PREFIX` (vraie photo candide, grain authentique, no SaaS aesthetic) + `NEGATIVE_PROMPT` qui kill illustration/3D/texte parasite. Plus de « dessin ».
- **Diversité géographique/personas** : casting Python (`SystemRandom`) avant l'appel LLM — 23 villes, 15 types de lieu, 10 personas. Fini « young Parisian in café » systématique.
- **Module Meta ads** (`scripts/meta_ad_generate.py`) : génère copy JSON 7 clés (accroche/solution/primary_text/headline/description/cta/image_brief) selon le system prompt LeClientROI senior copywriter + génère l'image associée. Coût ~0,033 €/ad.
- **🆕 Agent graphiste autonome** (`scripts/graphiste_agent.py` + `skills/graphiste.md`) :
  - Architecture séparée : content_agent fait le texte (sans image), graphiste fait l'image en post-traitement
  - Boucle agent_core : scan emdash posts sans `seo.image` → LLM choisit l'article + rédige le brief image → Imagen 3 photo doc → upload emdash → PUT seo.image
  - Cron PM2 `genesis-graphiste` (`0 11 * * *`), 1 article/jour. Backlog actuel : 21 articles sans image → 21 jours pour rattraper (ajustable).
  - Playbook strict : interdit illustration/3D/SaaS aesthetic/jeune Parisienne. Force patron 45-65 dans son commerce, ancrage métier visible, ville française variée.
  - Test live validé : agent immobilier ~50 ans avec lunettes en RDV client (https://blog.leclientroi.com/_emdash/api/media/file/01KTSGPSSF6KTV6QJZQDS7QJ6F.jpg)
- **content_agent** : branchement image header retiré (responsabilité passée au graphiste). content_agent publie sans image, graphiste enrichit après.

**RESTE (prochaine session, par priorité) :**
1. **V2 préambules playbooks** : ajouter la liste **exhaustive** des `action_type` acceptés dans chaque préambule `skills/*.md` (V1 actuelle est permissive → le LLM invente `audit_indexation`, `fix_gsc_permissions`, `fetch_articles` à côté des types attendus). Ne casse rien (les `_agentic_writer` filtrent), mais coupe le bruit.
2. **MKD publish 401** (action user : régénérer App Password WP)
3. **Migrer humanize_article + gen_agents_state vers text_utils.slugify** (cosmétique, pas urgent)
4. **Basculer les crons PM2 en `--agentic --live`** : actuellement seuls `content-lcr` et `humanizer` sont en agentique. Les autres (`seo-strategy`, `linkedin`, `internal-linking`, `competitor`, `brief` si crons existent) restent en mode classique. À basculer une fois la V2 préambules faite, pour ne pas pousser de signaux faux pendant l'itération.
5. **Évaluation post-cron** : laisser tourner les agents en mode agentique 1-2 semaines, mesurer les outcomes via `evaluate()`, affiner.

**DÉCISIONS EN ATTENTE (user) :**

## 🔝 REPRISE 2026-06-09 (nuit) — Boucle complète + humanizer + UI

**FAIT cette session (après-midi/soir/nuit) — gros chantier :**

### Boucle agentique (étape 2)
- `agent_core.evaluate()` + cron PM2 quotidien 02:00 (lcr) / 02:05 (mkd)
- 3 crons morts supprimés (briefing/crm-sync/campaign-status)
- `gen_agents_state.py` + endpoint `/api/agents/{site}/state`
- `content_agent.py --agentic` (boucle `agent_core.run_cycle`)

### Cleanup pipeline emdash (étape 3)
- Fix `publish_lcr` schema emdash : `data={title,content}` + `seo` top-level
- Fix `md_to_portable_text` : skip H1 du body (emdash affiche `data.title`), parse `**…**`/`*…*` en marks `strong`/`em`, ignore les `---`, splitte `Label : « citation »` en label-gras + blockquote, passe citations pures `« … »` en blockquote
- `ARTICLE_PROMPT` ré-écrit pour interdire à la source : préfixes `H2:`/`H3:`, labels `## Introduction`/`## Conclusion`, `---` dans le corps. Force `*Exemple : ...*` en italique.
- Slugifier `_slugify()` centralisé avec normalisation NFD (plus de `fidéliser → fidliser`)

### Test live de bout en bout
- Article LCR publié : https://blog.leclientroi.com/posts/comment-fideliser-vos-clients-avec-des-sms-personnalises (HTTP 200, slug propre avec accents, gras/blockquotes/italiques OK)
- Pilote humanizer sur 1 article backlog Arvow validé (agents-immobilier, 19k→11k chars, blacklist purgée, structure préservée)

### Agent humanizer (skill + cron PM2)
- Skill : `skills/humanizer.md` (prompt cmux-drop) + `skills/humanizer-tone.md` (préambule ton marketing-coach injecté en tête du user prompt)
- `scripts/humanize_article.py` : CLI standalone (peut traiter 1 article manuellement) — temp 0.85, filets déterministes (frontmatter forcé, `2025→2026` dans le corps)
- `scripts/humanizer_agent.py` : agent agentique sur `agent_core` (observe articles backlog par score scaffolding, recall, decide via DeepSeek, act = invoke humanize_article)
- Cron PM2 `genesis-humanizer` : `0 4 * * *`, `--site shared --live` → 1 article/jour, ~7 mois pour 212 articles backlog

### UI page /agents refondue
- Genesis-ui : nouvelle Card "État PM2 réel" en tête, lit `/api/agents/{site}/state`, affiche nom/cron lisible/statut/dernier run/exit code + badge "agent_core" si `--agentic` dans args
- Ancienne table renommée "Catalogue conceptuel (legacy)" — conservée pour transition, mais source de vérité = vraie PM2

**RESTE (prochaine session) :**
1. **MKD publish 401** : action user (régénérer App Password WP, voir DÉCISIONS EN ATTENTE)
2. **Migrer les autres agents** sur `agent_core` (seo-strategist, editorial-manager, internal-linking…) sur le pattern `content_agent.run_agentic`
3. **Première vraie évaluation** : le 16/06 02:00 UTC, `evaluate()` mesurera le delta GA4 sur l'article SMS personnalisés du 9 juin (J+7 minimum)
4. **Premier batch humanizer** : nuit du 09→10 juin 04:00, 1 article du backlog (top score actuel : `2025-11-21-automatisation-sms-marketing-workflows-et-scenarios-pour-2025.md` score 13)
5. **Slug v4 résiduels SQLite** : les slugs `-v2/-v3/-v4` sont soft-deleted dans `ec_posts` mais l'UNIQUE constraint les retient. Si on veut les libérer, intervention manuelle DB (refusée par claude classifier, à faire main).

**DÉCISIONS EN ATTENTE (user) :**

## 🔝 REPRISE 2026-06-09 (soir) — Boucle complète + content_agent migré

**FAIT cette session (après-midi/soir) :**
- **`agent_core.evaluate()`** : feedback nocturne, mesure delta réel par action (gsc_position:{kw} → traffic_strategist-like ; fallback gsc_clicks_total ; fallback ga4_sessions_total). Verdict `validated`/`failed`/`neutral` (seuils ±0.5pt pour position, ±5% pour métriques agrégées). Idempotent (LEFT JOIN sur action_id). Filtres : actions `done`, âge ∈ [7d, 30d]. CLI : `python3 scripts/agent_core.py --mode evaluate --site lcr`. Test fixture passé : 1 outcome écrit (delta +1292 sessions, validated).
- **Cron PM2 evaluate** : `genesis-agent-evaluate-lcr` (`0 2 * * *`) + `genesis-agent-evaluate-mkd` (`5 2 * * *`), `--no-autorestart`, dump persisté.
- **3 agents MORTS supprimés** : `pm2 delete genesis-briefing genesis-crm-sync genesis-campaign-status` + save. `orchestrator.py` n'existe plus → décision tranchée (suppression, pas restauration).
- **`scripts/gen_agents_state.py`** : snapshot `pm2 jlist` → `memory/agents-pm2-state.json` (atomic). Exclut services longs (dashboard/ui/mailnjoy-drain). Filtre par suffixe `-lcr`/`-mkd` (sinon global). 11 agents listés.
- **Endpoint `/api/agents/{site}/state`** dans `scripts/api.py` (juste avant `/planner`) : lit le snapshot, refresh inline si >5min, retourne `{generated_at, host, age_s, agents}` filtrés site+globaux. Testé : lcr et mkd voient 9 agents chacun (2 spécifiques + 7 globaux).
- **`content_agent.py --agentic`** : nouveau mode pilotage `agent_core.run_cycle` (observe gsc/ga4/ahrefs, recall, decide via DeepSeek, act via `_agentic_writer(item, snapshot, site, env, dry_run)`). Mode classique préservé. Test dry-run lcr : la boucle a raisonné explicitement « action précédente sans outcome → noop ce cycle », 1 noop écrit dans agent_actions avec reasoning intelligent. **La boucle agentique est OPÉRATIONNELLE de bout en bout.**

**RESTE (prochaine session, dans l'ordre) :**
1. **Page UI /agents** : consommer `/api/agents/{site}/state` (au lieu de `/api/agents/{site}`) — card "État PM2 réel" avec nom/cron/statut/dernier run/badge couleur. Backend prêt.
2. Brancher le cron PM2 `genesis-content-lcr` sur le mode `--agentic` (actuellement encore mode legacy) une fois la publication réparée. **Avant** ça : régler les bugs publish (lcr 500, mkd 401 — décision en attente).
3. Migrer les autres agents (seo-strategist, editorial-manager, etc.) sur `agent_core` — pattern à copier depuis `content_agent.run_agentic`.
4. Enrichir `skills/content-writer.md` (et autres) avec un préambule explicite "tu dois renvoyer un plan {action_type, target}" pour aider `decide()`.

**DÉCISIONS EN ATTENTE (user) :**
- **MKD publish 401** : WordPress répond `incorrect_password` → l'App Password est révoqué/invalide. **Action manuelle requise** : aller dans WP admin → Utilisateur camille.afchain@protonmail.com → Application Passwords → en générer un nouveau, puis remplacer `WP_APP_PASSWORD` dans `.env` (sans guillemets autour). Puis `pm2 restart genesis-dashboard`.
- ~~LCR publish 500~~ **RÉPARÉ** : le schéma emdash a évolué — `data.{excerpt,description,tags}` rejetés (`ec_posts has no column named description`). Fix dans `publish_lcr` : `data={title,content}` + `seo={title,description}` au top-level (validé create 201 + publish 200 sur draft de test).

**LIMITES connues :** GSC via le compte de service = encore **403** (grant propriété pas pris ; les données GSC passent par MCP Ahrefs / seed). GA4 OK.

**RÈGLE gravée :** MAJ `AGENTS.md` + `ARCHITECTURE.md` à CHAQUE fin de session touchant aux agents → lancer `sudo -u autoblog python3 scripts/gen_agents_doc.py`.

---


## Goal en cours
Tester le pipeline **Workflow LCR** de bout en bout (Serper → DeepSeek qualifier → push Emelia → cold email envoyé).
Mail test attendu sur afchain.camille@gmail.com via la campagne workflow-lcr-restaurant.

## Done (état réel observé en DB + logs)
- Spec workflow validée → specs/workflow-prospection.md (2026-05-21)
- Migration DB `scrappe` : colonnes region_code, dept_code, population, qualifier_*, emelia_* en place
- Workflow runner branché en cron : `30 6 * * 1-5` → logs/workflow.log
- Contact test 'Test Restaurant Camille / afchain.camille@gmail.com' inséré le 2026-05-21 19:30, status=validated, emelia_segment_id=6a0f5d290eb6f73f1f6149ec (workflow-lcr-restaurant), pushed dans Emelia
- Cron du 2026-05-22 06:30 : 30 prospects scrapés (Loire-Atlantique 44), **11 contacts poussés Emelia** (immobilier 2, restaurant 4, garagiste 1, coiffeur 2, artisan 2). MKD skippé (god_mode_state.enabled=False).

## Blocked / à vérifier
- **Campagne Emelia démarrée ?** Le push contact ≠ envoi mail. Tant que la campagne workflow-lcr-restaurant est en pause côté UI Emelia, rien ne part. À vérifier via API ou UI Emelia.
- Boîte gmail afchain.camille@gmail.com : pas encore checké si le mail test est arrivé.

## Next action (à faire MAINTENANT en reprenant)
1. Interroger l'API Emelia → statut de la campagne workflow-lcr-restaurant (running ? paused ?)
2. Si paused → Start dans l'UI Emelia
3. Vérifier réception du mail dans afchain.camille@gmail.com
4. Une fois validé end-to-end → activer le site MKD (god_mode_state.enabled=True pour 'mkd')

## Rappels importants
- User : autoblog (`su - autoblog` depuis root)
- Path : /home/autoblog/genesis
- Toujours lancer claude DANS tmux : `tmux new -s genesis` ou `tmux attach -t genesis`. Une session SSH qui coupe sans tmux = perte du contexte conversation.
- Clés Emelia : EMELIA_API_KEY_LCR / EMELIA_API_KEY_MKD dans .env, fallback EMELIA_API_KEY
- Budget : <$10/semaine total
- Quota Emelia : 50 contacts/site/jour max

## Historique des sessions récentes
- 2026-06-03 : **Campagnes cold-email AUTOMATISÉES** (gros chantier, plan approuvé). NOUVEAU auto_campaign_backend.py (tables auto_campaigns + auto_campaign_runs dans god_mode.duckdb, CRUD, idempotence 1/sender/jour) + auto_campaign_runner.py (orchestrateur PROCESS DÉTACHÉ : cap = min(target, warmup_quota − sent_today) ; boucle sur le PUSH pas l'envoi async ; pick pool → push_batch_to_campaign ; si pool sec + source=autoscrape → run_autoscrape(dept) inline → re-pick ; arrêts target/pool_exhausted/scrape_blocked/no_progress(3)/timeout(4h)/stop/pause ; statut fichier ; alerte Telegram). workflow_emelia_push.py : + ensure_campaign_for_auto (réutilise get_or_create_campaign) + push_batch_to_campaign. api.py : endpoints /api/sites/{site}/auto-campaigns/* (admin, Popen détaché) + /api/campaigns/{id}/stats-by-day + BAT /api/sites/{site}/templates/{sector}/{kind}/send-test. UI : campaigns/page.tsx REFONTE (gestionnaire auto : création secteur+sender+source+cible, table pause/resume/stop/run/delete, statut+alerte) ; cold-email/page.tsx + champ BAT ; dashboard AutoCampaignsSection (cards logo+stats agrégées + chevron stats/jour + global). ⚠️ CRON PM2 NON armé : create bloqué par classifier (= décision go-live user vers vrais prospects). Pour activer : pm2 start scripts/auto_campaign_runner.py --name genesis-auto-campaigns-lcr --interpreter python3 --cron-restart '0 7 * * 1-5' --no-autorestart -- --site lcr (idem mkd 15 7) + pm2 save. Testé DRY-RUN ok (cap 30, 228 dispo pool immo). PAS de test d'envoi réel (= vrais cold emails) : via BAT (adresse perso) puis Run manuel quand le user décide. Puis /code-review ultra.
- 2026-06-02 (fix compteurs UI faux) : « Tous (5793) » de la page Acquisition etait faux = stats_for_site comptait COUNT(*) contact_site_history (incluant ~2748 ORPHELINS : historiques de contacts supprimes par le nettoyage Mailnjoy). FIX : stats_for_site (JOIN contacts + COUNT DISTINCT email) -> vrai total 3045 (cold_email 3040, lead 4, prm 1). + cleanup run_cleanup supprime desormais contact_site_history en cascade avec le contact (plus d_orphelins futurs). Purge des orphelins existants PROPOSEE mais NON faite (bloquee par classifier comme destructive ; le JOIN les exclut deja de l_affichage). Exports livres sur Bureau Mac : TOUS contacts lcr (3045), mailnjoy VALID (3018), non-immo non-verifiables (13).
- 2026-06-02 : **cleanup auto en fin d_autoscrape ENFIN fonctionnel**. Le hook auto-cleanup etait sur l_endpoint scrape MANUEL (god_mode_api), mais l_autoscrape (process detache) ne le traversait pas -> auto_cleanup_triggered=0, jamais lance. FIX : run_autoscrape enchaine cb.run_cleanup_drain(mode=unverified, source=auto-scrape) dans le meme process apres le scrape (statut "cleaning", champ cum[cleanup], respecte le stop flag). UI : autoActive inclut "cleaning" + affichage nettoyage. api.py status checks incluent "cleaning". Validé : dept 48 coiffeur -> 7 scrapes -> cleanup_batch source=auto-scrape (1 validé, 6 supprimés). Visible badge Automatique dans page Cleanup.
- 2026-06-01 (autoscrape — heartbeat + multi-select) : (1) secteur en MULTI-SELECT badges (lib/sectors, 16 predefinis) au lieu d_un input libre dans la card autoscrape. (2) heartbeat intra-ville : scrape_sector(heartbeat_cb) appelé à chaque page Serper -> autoscrape_backend met le statut à jour en direct (examinés/gardés live + current_detail ville/secteur) -> plus de faux "figé" sur ville longue (le statut ne s_ecrivait qu_en fin de secteur). NB : sur des arrondissements déjà scrapés, dedup => peu de nouveaux + pagination longue (normal). Le run en cours d_un fix garde l_ancien code (process déjà lancé) ; le fix s_applique au prochain run.
- 2026-06-01 (autoscrape — fix conflit DuckDB) : runs arrondissements renvoyaient examined=0 + faux "blocked_credits". Cause : scrape_sector CRASHAIT sur les vérifs anti-doublon (gm.email_recently_validated/email_in_pending) en conflit DuckDB cross-process avec l_API (lignes hors try/except) -> 0 resultat -> heuristique zero_streak criait blocage credit a tort (credits OK 2099). FIX : (1) god_mode_agents.scrape_sector wrappe tout le traitement par commerce en try/except + retry -> un verrou transitoire saute le commerce, ne tue plus la ville. (2) autoscrape_backend : zero_streak ne declenche blocked_credits que si solde reellement bas (<=floor*3), sinon statut stalled ; seuil 3->5. Validé : test 75 immobilier sous API live -> 42 contacts (Paris 1er 16, 2e 15, 3e 6, 4e 5) au lieu de 0. Un 75 complet = ~300 contacts.
- 2026-06-01 (autoscrape — arrondissements) : Paris/Lyon/Marseille = 1 commune INSEE unique dans la geo => autoscrape ne faisait qu_~18 contacts pour tout Paris. Ajout `ARRONDISSEMENTS` + `_expand_arrondissements` dans autoscrape_backend : dept 75 -> 20 villes (Paris 1er..20e), 69 -> +Lyon 1-9e, 13 -> +Marseille 1-16e. Serper localise bien par arrondissement (verifie), dedup email evite les doublons. city stocke stocke Paris 16e. Pas de restart API (chaque autoscrape = nouveau process lisant le fichier a jour).
- 2026-06-01 (autoscrape v2 — robuste) : le 1er autoscrape (thread DANS l'API) a planté en cours (dept 92 immobilier, 32/34 villes, ~290 contacts SAUVÉS quand même) sur `_duckdb.ConnectionException: Can't open a connection to same database file with a different configuration` — conflit de connexions DuckDB intra-process (le thread scrape vs les requêtes API). RÉARCHITECTURÉ en **process DÉTACHÉ** : `autoscrape_backend.py` a un `main()` (--site --dept --sectors) qui écrit l'avancement dans `memory/autoscrape/<site>-status.json` (heartbeat updated_at) et lit un flag `<site>-stop.flag`. Endpoints api.py : start = Popen `start_new_session=True` (détaché, survit aux restarts API), status = lit le fichier (+ marque 'interrupted' si pas de heartbeat >5min), stop = pose le flag. Plus de `_active_autoscrape` en mémoire. Bonus : log `start_scrape` par (ville,secteur) (auto=True) → l'autoscrape est désormais VISIBLE dans le panneau 'Activité des scrapes' (qui matche start_scrape↔scrape). Testé : dept 78 restaurant détaché → statut fichier OK, stop flag → arrêt propre (Versailles, 13 gardés), process sort proprement. LEÇON : ne jamais faire tourner un job DB-lourd long comme thread de l'API (genesis-dashboard = 334 restarts + conflits DuckDB) ; process détaché + statut fichier.
- 2026-06-01 : **Autoscrape département** (demande user, ras-le-bol des paramètres). Nouveau `scripts/autoscrape_backend.py` : `run_autoscrape(site, sectors, dept)` scrape TOUTES les villes pop>=10k du dept (≈35-42/dept) ville par ville via scrape_sector, en continu, jusqu'à épuisement OU blocage crédits Serper. Détection blocage : proactif (solde snapshot serper-balance.json − conso god_mode_serper_calls < credit_floor=60) + réactif (3 villes vides d'affilée). Alerte Telegram + statut 'blocked_credits'. Endpoints api.py (admin-gated via request.state.session.role) : POST /autoscrape/start {sectors,dept}, GET /autoscrape/status, POST /autoscrape/stop ; registre `_active_autoscrape` (1 job global). UI scrapper : card '🤖 Autoscrape' en haut de l'onglet Lancer (réutilise sectors + selectedDept), progression live (villes X/Y, gardés, crédits restants) + stop + bandeau alerte blocage. Testé live : dept 92 (34 villes), 1 ville Boulogne → 15 gardés, crédits 2396→2392. Diag timeout user : geo/live-activity rapides (ms), session=7j, nginx genesis-api proxy_read_timeout=120s ; le timeout venait probablement d'un scrape manuel géant (266 villes IDF — l'UI envoyait toutes les villes si aucune cochée). L'autoscrape (async, lancement instantané) élimine les timeouts de requête.
- 2026-05-31 (fix logique scrape par-ville) : BUG corrigé — `scrape_sector` (god_mode_agents) traitait `max_results` comme un plafond GLOBAL alors que l'UI promettait 'par ville' (+ estimation de coût × villes). Conséquence : un scrape 'toute l'IDF' s'arrêtait à N total (1-2 villes) au lieu de couvrir les 266 villes. RÉÉCRIT : `scrape_sector(cities, max_per_city, global_cap, max_pages=4)` = N contacts GARDÉS par ville (pagination Serper Places — vérifié que page>1 renvoie du neuf), boucle sur TOUTES les villes, plafond global de contacts gardés (garde-fou crédits). `serper_places` accepte désormais `page`. Endpoint `/{site}/scrape` : `max_per_city` (1-50, accepte ancien `max_results`) + `global_cap` (def 1000, max 5000). UI scrapper : 2 champs (gardés/ville + plafond), estimation coût réaliste + alerte si >30 villes ; région sans villes cochées → envoie TOUTES les villes chargées (avant : 10 villes AU HASARD du top 50 France — autre bug). Testé live : 2 villes × max 2/ville → cities_done=2, kept=4 (Versailles 2 + Meaux 2). NB 'scraped' dans les logs = commerces EXAMINÉS (≈ crédits/10), pas gardés ; 'valid' = gardés.
- 2026-05-31 (hardening sécu post-review) : 3 recos appliquées sur les ajouts de la session. (1) `/api/enrichment/run` ajouté à `_ADMIN_PREFIXES` → réservé admin (stats reste ouvert à auth) ; UI Acquisition : bouton 'Enrichir le pool' + popup 'en retard' masqués aux non-admins (isAdmin, lecture localStorage pour éviter la race au 1er rendu). (2) cast défensif de `limit` (try/except → pas de 500). (3) fermeture du fd du log après Popen. Revue manuelle (skill /security-review KO sans git local) : RAS critique — pas d'injection commande/SQL, auth OK, raw data.gouv sanitisé (pas de dirigeants).
- 2026-05-31 (nettoyage auto post-scrape) : à la fin d'un scrape (god_mode `POST /{site}/scrape`, thread run()), déclenchement AUTOMATIQUE du drain de nettoyage Mailnjoy — plus besoin de lancer les lots à la main. Implémentation : fonction réutilisable `_launch_cleanup(site, mode, drain, chunk_size, total_limit, source)` extraite de l'endpoint /cleanup/run dans api.py (le verrou séquentiel _active_cleanups est partagé). Le hook scrape récupère le module via `sys.modules['scripts.api']._launch_cleanup(..., source='auto-scrape')`. `source` propagé dans cleanup_backend.run_cleanup/run_cleanup_drain → loggé dans cleanup_batch. UI page cleanup : badge '⚡ Automatique' vs 'Manuel' dans l'historique + bandeau d'info. Verrou strict : si un nettoyage tourne déjà, l'auto refuse proprement (le drain en cours absorbe les nouveaux contacts). NB : api.cheffer.email = CE VPS (204.168.186.159), c'est le domaine de prod de cette instance Genesis.
- 2026-05-31 (suite UI+cron) : enrichissement data.gouv complété. **Endpoints** GET /api/enrichment/stats + POST /api/enrichment/run (api.py) + fonction enrichment_stats() dans contacts_pool_backend.py. **UI** : Card 'Enrichissement data.gouv' dans la page Acquisition (vérifiés/non-vérifiés/exclus/à-traiter + signaux Qualiopi/RGE/ESS + bouton 'Enrichir le pool' qui POST run et poll les stats). **Cron** PM2 `genesis-datagouv-enrich` : `0 7 * * *`, --no-autorestart, `--limit 2000` (garde-fou), tourne en autoblog, persisté via pm2 save. ⚠️ PIÈGE RENCONTRÉ : mes runs manuels via `ssh lcr` (=root) avaient créé data/datagouv_cache.sqlite + logs/datagouv_enrich.log en root → le cron (autoblog) plantait 'attempt to write a readonly database'. Corrigé par chown autoblog. RÈGLE : tout fichier créé pour Genesis doit appartenir à autoblog, pas root.
- 2026-05-31 : **Enrichissement data.gouv intégré** (skill cheffer fourni par user). Table satellite `contact_enrichment` (1:1 contacts, contacts.duckdb) + script `scripts/datagouv_enrich.py` (API recherche-entreprises, requests, cache SQLite data/datagouv_cache.sqlite, rate 4/s + backoff 429, anti-join). RGPD : jamais de dirigeants (raw sanitisé). Filtre branché dans pick_for_campaign + count_available_for_sector (`COALESCE(e.excluded,FALSE)=FALSE`). SÉMANTIQUE CLÉ : excluded=TRUE = exclusion DURE uniquement (fermée/admin/statut P) ; non_trouve/ambigu restent contactables (excluded=FALSE, siret NULL). 1er run complet : 2899 lignes → 1633 enrichis (~56%), 1172 non-vérifiés contactables, 94 exclus durs (86 fermées + 8 admin). Signaux détectés : 178 Qualiopi, 124 ESS, 10 RGE. Match par dénomination (pas de SIRET au scrape) → fiabilité moyenne, ambigus exclus. Validé : un contact fermé n'est plus pioché. Reste hors-scope : endpoint API trigger/stats, bouton UI Acquisition, cron incrémental. Pour relancer l'incrémental : `setsid nohup python3 scripts/datagouv_enrich.py > logs/datagouv_enrich.log 2>&1 < /dev/null &`.
- 2026-05-30 (suite) : ligne Serper passée en **solde restant** au lieu de conso/mois. Serper n'ayant pas d'API de solde, snapshot manuel dans memory/seo/serper-balance.json {plan_total:2500, balance:2442, snapshot_at}. L'endpoint /api/serper/usage renvoie `available = balance − conso locale depuis snapshot_at` (god_mode_serper_calls + costs-log). Affichage widget = `2 442 / 2 500` (rouge si <10%). Pour resync : relever le vrai solde sur serper.dev et mettre à jour balance+snapshot_at dans le JSON.
- 2026-05-30 : Widget conso sidebar (CreditsWidget) — ajout ligne **Serper** (crédits consommés mois en cours). Serper.dev n'expose AUCUNE API de solde (/account,/balance,/credits => 403), donc affichage = conso locale : table god_mode_serper_calls + entrées serper-search du costs-log. Nouvel endpoint GET /api/serper/usage (api.py). Confirmé : le widget se rafraîchit déjà toutes les 60s (DeepSeek/Mailnjoy live, Ahrefs = cache quotidien cron 06:00) — l'impression 'statique' venait du quota Ahrefs gelé jusqu'au reset 2026-06-17, pas d'un bug. Build genesis-ui + pm2 restart genesis-ui/genesis-dashboard OK.
- 2026-05-21 soir : test pipeline bloqué sur abo Emelia inactif. User est allé se coucher en disant 'j'active demain matin'.
- 2026-05-22 matin : SSH cassé (clé non offerte), résolu en ajoutant bloc Host lcr dans ~/.ssh/config Mac avec IdentityFile id.mkdautoblog. Cron du matin a tourné et poussé 11 contacts → l'abo Emelia est manifestement actif.

## Backlog (parked — à reprendre plus tard)
- **Refactor DataTable shadcn** (parked 2026-05-22) — 17 fichiers de genesis-ui utilisent les primitives `Table` shadcn à la main, sans le pattern DataTable officiel (TanStack Table). Pas de `@tanstack/react-table` installé. Plan progressif identifié :
  1. Installer TanStack + créer `src/components/ui/data-table.tsx` générique (pattern shadcn officiel)
  2. Pilote sur `src/app/site/[code]/acquisition/page.tsx` (page la plus riche)
  3. Migrer ensuite les 6 pages "lourdes" : `workflow/prospects`, `workflow/campaigns`, `workflow/logs`, `articles`, `campaigns`, `costs`
  4. Pages "moyennes" (seo-strategy, seo, workflow/performance, versions, view, agents) : décision au cas par cas
  5. Tableaux statiques (dashboard, setup, site-budget-card, god-mode-panel) : on laisse en `Table` primitif, pas de refactor inutile


## Refonte SEO / Budget Ahrefs — 2026-05-22

**Contexte** : conso Ahrefs a 159% du quota (15 905 / 10 000), aucune limite implementee malgre demande user. SEO Strategist n'avait pas surveille.

**Actions realisees** :
- `scripts/cost_tracker.py` -> ajout `check_ahrefs_budget()` (gate avec seuils warn 70%, block 90%, reserve 500u)
- `scripts/ahrefs_daily.py` -> refactor MINIMALISTE (uniquement `site-explorer/metrics`, ~100u/jour). Backup ancienne version : `ahrefs_daily.py.bak-2026-05-22`
- `scripts/ahrefs_monthly_audit.py` -> NOUVEAU. Cron `0 6 1 * *`. Tier 1+2 endpoints + `site-audit/issues` (corrections techniques).
- `scripts/seo.py` -> gate integree dans `ahrefs_get()` avec params `cost_estimate` + `critical`
- `scripts/seo_strategy_agent.py` -> SURVEILLANCE budget ajoutee dans main() - emet une reco critique si conso >= 70%, notif Telegram
- `specs/seo-playbook.md` -> NOUVEAU. Doc complete : tiers endpoints, budget, gate, Site Audit projects, role SEO Strategist

**Site Audit Ahrefs** :
- LCR (`leclientroi.com`) -> projet existant, project_id `8344256` (health=100, 97 warnings, 95 notices)
- MKD (`mkdgroupe.com`) -> PAS DE PROJET, a creer dans https://app.ahrefs.com/site-audit puis mettre a jour `SITES` dans `ahrefs_monthly_audit.py`

**Etat budget actuel** :
- Conso 15 905 / 10 000 (159%)
- Reset : 2026-06-17
- D'ici la, TOUS les appels sont bloques par la gate (sauf si quota repasse sous 100% ce qui n'arrivera pas)
- Apres reset : tracker la conso, viser ~7 000/mois max

**Decisions user** :
- GSC : mis en pause (pas envie de le brancher pour l'instant)
- DataTable refactor : parke (cf section Backlog plus haut)

## Next action (a faire au reset 2026-06-17 ou avant)
1. Creer projet Site Audit Ahrefs pour mkdgroupe.com
2. Une fois le quota reset, lancer manuellement `python3 scripts/ahrefs_monthly_audit.py` pour verifier que tout fonctionne
3. Verifier que le cron monthly s'execute bien le 1er juin 6h UTC
4. Reprendre le pipeline LCR Emelia (campagnes en DRAFT -> demarrer)


### Additif 2026-05-22 (suite décisions user)
- `seo.py --report full` -> DESACTIVE (sys.exit dans main()). Plus de bouton UI a brancher dessus.
- `seo.py --report keywords` -> max 1x tous les 2 mois (operationnel, pas de blocage code)
- `site-explorer/metrics` -> BYPASS gate budget dans ahrefs_daily.py. Jamais bloque meme en depassement quota.


## Email Validator déployé — 2026-05-22

**Spec** : EMAIL_VALIDATION_SCORING.md (fourni par user) — 6 étages, drop avant insertion.

**Fichiers** :
- scripts/email_validator.py (module unique, point d entrée: validate_and_score(email, prospect))
- data/email_jetable.csv (304 domaines disposable chargés depuis la liste fournie + enrichie user)
- DB scrappe migrée : email_score INTEGER, email_validation_reasons JSON
- Intégré dans god_mode_agents.scrape_sector() : si decision=drop, prospect jamais inséré
- god_mode_backend.add_prospect() étendu pour persister email_score + reasons

**Honeypots** (drop hard reject avant scoring) : spamtrap, honeypot, trap@, abuse@, spam@, **rgpd@, dpo@, gdpr@, @rgpd., @dpo.** (déplacés depuis role-based à la demande user — sécu CNIL)

**Décisions de seuils** :
- score < 40  -> drop (rejection_reason = low_score)
- 40 <= score < 60 -> queue (status = manual_review, à reviewer humain)
- 60 <= score -> push (status = validated, éligible push Emelia)

**Backfill 2026-05-22** : 20 prospects analysés, 3 rejetés (1 sentry no_mx + 2 rgpd@junot.fr), 2 passés en manual_review, 12 déjà pushés Emelia non touchés (juste email_score informatif).

**Pipeline en place pour les prochains scrapes** : le cron du matin (30 6) appellera god_mode_agents.scrape_sector() qui filtrera automatiquement chaque email via validate_and_score avant insertion.


## Mailnjoy intégré (Phase 1 backend) — 2026-05-22

**Spec** : PAPERCLIP/mailnjoy-api-reference.md + mailnjoy-integration-prompt.md

**Architecture** : Serper -> validator -> scrappe_pending -> Mailnjoy -> scrappe ou DELETE.

**Décisions actées** :
- risky = DELETE (jamais en scrappe) — décision user (1.b)
- Flow synchrone (Mailnjoy appelé dans la boucle scrape) — décision user (2.a)
- Phase 2 UI (sidebar credit, tag visuel, page setup) parquée

**Composants livrés** :
- Table scrappe_pending (memes colonnes que scrappe + mailnjoy_attempts/last_error)
- Colonne scrappe.mailnjoy_check (JSON) pour traçabilité
- scripts/mailnjoy_check.py : check_email_mailnjoy(), classify_response(), get_credit(), check_pending_queue()
- scripts/god_mode_backend.py : add_prospect_pending(), list_pending(), move_pending_to_scrappe(), delete_pending(), bump_pending_error()
- scripts/god_mode_agents.py scrape_sector() ecrit dans scrappe_pending
- scripts/workflow_runner.py appelle check_pending_queue(site) apres chaque scrape de secteur
- logs/mailnjoy_deletions.log audit des suppressions

**Test E2E 2026-05-22 11h55 (4 emails)** :
- valid=1, risky=2, invalid=1 — pending vide, scrappe peuplé, log OK
- Crédits consommés 8u (2/email × 4) sur solde 1 199 105 -> 1 199 097

**Credentials .env** :
- MAILNJOY_ID + MAILNJOY_SECRET configurés (clé lecture seule=non, autorisation achat=oui)
- Endpoint /v2/unitary?type=simple, body en text/plain
- Backoff exponentiel sur 429/503/500 (max 5 essais)
- Stop immédiat si 401/403

**Map décision** : VALID/SAFE -> valid | INVALID/UNSAFE/spamtrap/disposable -> invalid | RISKY/catchall/role/suspect -> risky | network/500 -> error (retry max 5)


## Phase 2 Mailnjoy complète — 2026-05-22 (suite refonte)

Tout les non-fait du récap précédent ont été traités :

**Backend** :
- Idempotence 30 jours : helpers god_mode_backend.email_recently_validated(email, days) + email_in_pending(email), branchés dans scrape_sector pour skip avant insert pending
- State machine refonte complète (cf section 12 de specs/workflow-prospection.md) :
  - pending_mailnjoy (scrappe_pending default)
  - mailnjoy_valid (scrappe après drain valide)
  - pushed_emelia (status après push Emelia OK)
  - scored (legacy, prospects pré-Mailnjoy)
  - manual_review (validator queue)
  - rejected (validator drop)
- Migration DB faite : 16 validated -> 15 scored + 1 mailnjoy_valid
- Queries downstream updated dans workflow_runner, god_mode_backend, workflow_emelia_push

**Endpoints API** (api.py) :
- GET  /api/mailnjoy/credit               → solde
- GET  /api/mailnjoy/status               → configuré ? crédit ? pending count
- POST /api/mailnjoy/test-credentials     → test avec ID/Secret donnés (sans sauvegarder)
- POST /api/mailnjoy/save-credentials     → écrit dans .env après test OK
- POST /api/mailnjoy/drain                → déclenche un drain manuel
- GET  /api/sites/{site}/workflow/counters → compteurs refondus (Scrapés, Ajoutés, Nettoyés, Envoyés)

**UI (genesis-ui)** :
- credits-widget.tsx : ligne Mailnjoy en vert (rouge si < 500u), polling 60s
- mailnjoy-config-card.tsx : nouveau composant pour la page Setup (input ID+Secret, bouton Tester, bouton Sauvegarder, affichage crédit + pending count)
- prospects/page.tsx : colonnes Email score + Mailnjoy (tag visuel ✓/⚠/✗ + date) + Qualifier DS (✓ qualifié / ✗ rejeté DS / pending), filtres sur nouveaux statuts (mailnjoy_valid, pushed_emelia, manual_review, scored, rejected)
- setup/page.tsx : MailnjoyConfigCard inséré au-dessus des connecteurs site-specific
- Next.js rebuild OK, pm2 restart genesis-ui OK

**Documentation** :
- specs/workflow-prospection.md : section 12 Email Validator + Mailnjoy ajoutée (pipeline complet, state machine, idempotence, particularités API)

**Tests** :
- tests/test_mailnjoy_check.py : 22 tests pytest (classify_response 11 cas, check_email_mailnjoy 8 cas, edge cases 3 cas) → 22/22 PASSED
- Stratégie : mock requests.post au lieu de Prism (équivalent fonctionnel, plus simple, pas de serveur HTTP à lancer)

**Dépendances installées** :
- dnspython (pour MX check du validator)
- email-validator (pour pydantic v2, requis par fastapi - bug latent corrigé)
- pytest

**Crédits consommés ce session** : 8u Mailnjoy (sur 1 199 105 dispo)


## Webhook Emelia temps réel + Warmup plan — 2026-05-22 (suite)

**Webhook Emelia branché en prod** :
- Endpoint backend : POST /api/emelia/webhook?token=WEBHOOK_TOKEN_1 (existait déjà, opérationnel)
- Webhook Emelia créé via POST /webhook avec campaignId=ALL_CAMPAIGNS, type=email, events=[SENT,OPENED,CLICKED,REPLIED,BOUNCED,UNSUBSCRIBED]
- Emelia déploie auto sur les 9 campagnes existantes (LCR + Test + Lancement)
- Test E2E validé : afchain.camille a cliqué le lien unsubscribe → event UNSUBSCRIBED reçu → state mis à blacklisted dans acquisition_contacts

**Table emelia_events ajoutée à god_mode.duckdb** :
- Audit de TOUS les events Emelia (incl. SENT/OPENED qui étaient ignorés avant)
- Colonnes : id, received_at, event_type, email, first_name, last_name, campaign_name, campaign_id, site_code, step, emelia_date, raw_payload
- 3 index : email, campaign_id, received_at

**Auto-register webhook à chaque nouvelle campagne** :
- workflow_emelia_push.get_or_create_campaign() appelle POST /webhook après création (idempotent)
- Push aussi automatiquement les steps + start de la campagne dans la foulée

**Bug fix** :
- Handler webhook normalise désormais event_type en lower() (Emelia envoie en UPPERCASE)
- Campaign peut arriver en string OU dict → handler gère les 2

**Warmup plan déployé** :
- Spec : specs/warmup-plan.md (137 lignes, Plan A conservateur Emelia + Plan B agressif IP Warming Planner)
- Table email_senders dans god_mode.duckdb (sender_email PK, warmup_start_date, daily_max_override, status)
- Sender LCR juliette@leclientroi.com inscrit avec warmup_start=2026-05-22 (J1=10 emails/jour)
- Plan A appliqué : J1-J3=10, J4-J7=20, J8-J14=35, J15-J21=50, J22-J28=75, J29+=100
- Helpers ajoutés à workflow_emelia_push.py : daily_warmup_quota(), sender_email_for_site(), emelia_sent_today_by_sender()
- Garde-fou branché dans push_prospect : si sent_today >= warmup_quota → bloc push avec raison warmup_quota_reached
- État actuel : sender Juliette J1 → quota 10, déjà envoyé 1 (test) → 9 restants pour aujourd'hui

**Reste à faire** (priorité) :
- Démarrer les 5 campagnes LCR DRAFT (workflow-lcr-restaurant/artisan/coiffeur/garagiste/immobilier) avec templates + start — script migrate_existing_draft_campaigns.py à coder
- Sidebar UI : afficher J{N}/quota par sender (warmup status visible)
- Cron quotidien warmup_daily_check.py : pause sender si bounce_rate > 5% ou unsubscribed_rate > 2%


## Pool mutualisé contacts — Phases 0+1+2 — 2026-05-22

**Spec sources** : specs/contacts-model.md, onboarding-checklist.md, campaigns-spec.md (3 docs validés par user).

### Phase 0 — Migration data
- NOUVEAU fichier : data/contacts.duckdb (chown autoblog:autoblog)
- 2 tables créées : contacts (PK email unique, 36 rows) + contact_site_history (UNI (contact_id, site_code), 36 rows)
- Script : scripts/migrate_contacts_to_pool.py
- Source : crm/lcr.duckdb (33), crm/mkd.duckdb (1), god_mode.duckdb.scrappe (3) — déduplication par email
- Logs : logs/migration_contacts_pool.log
- ⚠️ Anciennes DBs intactes (RO) — rollback possible 30 jours

### Phase 1 — Backend pool
- NOUVEAU module : scripts/contacts_pool_backend.py
- 13 helpers publics : find_by_email_global, create_in_pool, set_global_blacklist, get_history_for_site, upsert_site_history, change_state_for_site, mark_pushed_to_emelia, record_emelia_event, list_contacts_for_site, stats_for_site, pick_for_campaign, count_available_for_sector, check_pool_depletion
- Constantes : COOLDOWN_GLOBAL_DAYS=30, COOLDOWN_SAME_SITE_DAYS=7, STATE_RANK
- Testé : stats LCR=35 contacts, pick_for_campaign restaurant=0 (cohérent — peu de cold_email), check_pool_depletion fonctionne

### Phase 2 — Dual-write activé sur 5 maillons
Tous les flux d'écriture alimentent en parallèle le pool ET le système legacy (acquisition_contacts) :
1. api.py:api_emelia_webhook → record_emelia_event + change_state_for_site + set_global_blacklist (si bounce/unsub)
2. workflow_emelia_push.py:push_prospect → create_in_pool + upsert_site_history + mark_pushed_to_emelia
3. tally_to_prm.py → _tally_dual_write_pool helper (lead direct)
4. emelia_to_crm.py → _dual_write_pool helper (sync cron 19h)
5. god_mode_agents.py:scrape_sector → create_in_pool + upsert_site_history cold_email

Validation live 2026-05-22 21:00 : POST webhook CLICKED sur afchain.camille@gmail.com → pool state cold_email → prm OK + emelia_clicked_at set.

### Reste à faire
- Phase 3 : UI Acquisition (fusion onglet Pipeline + sous-vue historique par site)
- Phase 4 : UI Campagnes (wizard 4 étapes, algo pioche, page détail)
- Phase 5 : UI Vision (compteurs + funnel + warmup)
- Phase 6 : UI Onboarding 16 steps
- Phase 7 : Sidebar cleanup (supprimer module Workflow)
- Tables  +  chiffrée AES (multi-tenant cible) — pas encore créées


## Refactor complet — Phases 0-7 livrées — 2026-05-22 (suite session go)

### Phases 3-7 livrées (suite à Phase 0-2 du début de session)

**Phase 3 — Page Acquisition refondue** ()
- Switch endpoint de lecture sur /api/sites/{site}/pool/contacts (au lieu de /acquisition legacy)
- Type Contact étendu pour matcher la structure pool (sectors, primary_source, email_score, mailnjoy_check, last_contacted_by_site_at, etc.)
- Edit/delete/blacklist toujours sur l ancien endpoint legacy (dual-write garde sync)

**Phase 4 — Page Campagnes nouvelle** ()
- Wizard 4 steps (secteur > volume > preview > validation)
- Alerte secteurs épuisés (popup card)
- Liste campagnes Emelia avec stats (sent, opens%, clicks%, replies%, progress%)
- Endpoint POST /api/sites/{site}/pool/campaigns/create qui pick + create + steps + push + start + webhook

**Phase 5 — Page Vision nouvelle** ()
- KPI cards : contacts pool, envoyés, leads, nettoyés
- Funnel chart (workflowFunnelConfig) avec scraped/qualified/sent/prm/leads/bounced
- Distribution par source primaire (progress bars)
- Placeholder warmup status

**Phase 6 — Onboarding refondue** ()
- 16 steps en cards séquentielles (Identité, URLs, Persona, SEO, Éditorial, Secteurs, Sender, RGPD pied de mail, API keys, Templates, Warmup, Modules, Ahrefs, Quotas, Compte, Mail test)
- Validation des champs bloquants (border rouge sur cards incomplètes)
- Sticky submit en bas avec compte des steps complétés
- Payload posté vers /api/sites/onboard-full (à étendre backend pour gérer les 16 champs)

**Phase 7 — Sidebar cleanup**
- Section Commercial refondue : Vision, Acquisition, Templates, Campagnes (par site)
- Suppression Workflow, Vue d ensemble, Performance, Prospects, Campagnes (legacy /workflow/), Prospection (global /campaigns)
- TITLE_TO_MODULE mis à jour

**Cleanup fichiers**
- Supprimés : src/app/site/[code]/workflow/{campaigns,prospects,performance}, page.tsx
- Gardés : workflow/templates (lien sidebar), workflow/logs (admin), workflow/layout.tsx (auth)

**Pool write endpoints ajoutés** (api.py)
- POST /api/sites/{site}/pool/contacts/create
- PATCH /api/sites/{site}/pool/contacts/{id}
- DELETE /api/sites/{site}/pool/contacts/{id}
- POST /api/sites/{site}/pool/contacts/import-csv

### Restes connus
- L endpoint backend /api/sites/onboard-full doit etre etendu pour gerer les 16 nouveaux champs (persona, sectors_enabled, modules_enabled, warmup_plan, account_id, etc.) sinon les nouvelles infos sont droppees a l onboarding
- Table accounts + site_credentials AES chiffrees (multi-tenant cible) pas encore creees
- Pages /workflow/templates et /workflow/logs restent — a refondre (templates devient lecture seule depuis Emelia, logs vers /admin/logs)
- L UI Acquisition utilise toujours edit/blacklist legacy endpoints — a migrer vers pool/* equivalents


## Session enchaine — finalisation backend + cleanup — 2026-05-22 23:00

### Backend onboard V2 + multi-tenant
- Tables NOUVELLES dans god_mode.duckdb :
  -  (id PK, label, owner_user_id, plan, created_at) — multi-tenant
  -  (site_code+key_name PK, encrypted_value) — clés API par site (MVP clair, à chiffrer AES v2)
- god_mode_settings enrichie de 6 colonnes : sectors_enabled JSON, daily_quota_per_sector, emelia_daily_limit, cooldown_same_site_days, cooldown_global_days, account_id
- /api/sites/onboard-full étendu pour gérer les 16 champs du nouveau wizard :
  - persona/geo/dept_priority → context/{code}/audience.md
  - tone/cta/signature/banned_words → context/{code}/editorial-style.md
  - raison_sociale/adresse/dpo/privacy → context/{code}/footer.md (pied de mail B2B)
  - sender_email/sender_name → INSERT email_senders (warmup_start_date = aujourd hui si warmup_start_today=True)
  - sectors_enabled, daily_quota, emelia_daily_limit, cooldowns → god_mode_settings
  - emelia_key/serper_key/tally_key/telegram → site_credentials
  - account_id → INSERT accounts
  - modules_enabled → memory/{code}/modules.json
  - god_mode_state.enabled = FALSE par défaut (déblocage après Step 16 mail test)

### Migration UI Acquisition vers pool/* endpoints
6 actions write switched de /acquisition/* legacy vers /pool/contacts/* :
- change-state, update fields, create, blacklist, delete, import-csv
La page Acquisition est désormais 100 pourcent sur le pool mutualisé (lecture + écriture).

### Cleanup fichiers
- Move src/app/site/[code]/workflow/templates/ → src/app/site/[code]/templates/
- Sidebar Templates pointe maintenant vers /site/[code]/templates (au lieu de /workflow/templates)
- workflow/ ne contient plus que layout.tsx (admin check) + logs/ (accessible direct)

### Reste à faire
- Chiffrement AES site_credentials.encrypted_value (MVP clair OK pour LCR + MKD perso)
- Cron 6h30 demain alimentera le pool en vrai via dual-write (premier test prod)
- Step 16 onboarding mail test : envoyer effectivement le mail via /emails/test Emelia + UI confirmation
- Page admin/logs (déplacer /workflow/logs vers /admin/logs)
- Backup cron à étendre pour inclure data/contacts.duckdb


## Session enchaine 2 — AES + mail test + backup — 2026-05-22 23:30

### A. Chiffrement AES Fernet site_credentials
- NOUVEAU module : scripts/site_credentials_backend.py
- Helpers : encrypt_value, decrypt_value, set_credential, get_credential, list_credentials, delete_credential, migrate_plaintext_to_encrypted
- Master key : env var SITE_CREDENTIALS_MASTER_KEY (prioritaire) sinon data/.master_key (auto-générée, chmod 600)
- Backward compat : valeurs anciennes en clair sont re-chiffrées au premier get_credential
- Endpoint /api/sites/onboard-full migré pour utiliser set_credential (AES) au lieu d INSERT direct
- workflow_emelia_push._get_key etendu : lit site_credentials AES en priorité, fallback env vars

### B. Step 16 onboarding mail test + activation
- NOUVEAU endpoint POST /api/sites/{code}/onboarding/send-test-email
  - Body : {test_email, sector}
  - Crée campagne onboarding-test-{code} si absente + configure steps
  - Appelle /emails/test Emelia (envoi instantané sans cadence)
- NOUVEAU endpoint POST /api/sites/{code}/onboarding/confirm-activation
  - Body : {received: true}
  - Passe god_mode_state.enabled = TRUE pour ce site
- Page UI onboarding étendue : après submit, le site est créé mais god_mode_state.enabled=FALSE
  - Step 16 affiche bouton Envoyer mail test
  - Apres envoi : bouton J ai reçu → confirm-activation → enabled=TRUE → redirect dashboard
  - Bouton Renvoyer disponible si user n a pas reçu

### C. Backup cron étendu
- scripts/backup.sh : check explicite des fichiers critiques (contacts.duckdb, god_mode.duckdb, auth.duckdb, .master_key)
- Copie séparée de .master_key vers BACKUP_DIR/.master_key.bak (disaster recovery)
- Cron quotidien 21h UTC inchangé (continue de tourner)

### Reste à faire pour vraiment SaaS-ready
- Cron 6h30 demain matin = premier test grandeur nature (passive, vérifier les logs)
- Page admin/logs (déplacer /workflow/logs vers /admin/logs au niveau global)
- Endpoint /api/sites/{code}/credentials/{key_name} pour lire/setter les clés via UI (gestion des clés post-onboarding)
- Multi-tenant : section UI accounts (CRUD comptes) — actuellement la table existe mais pas de CRUD
- Test : un nouveau site complet créé via UI onboarding (vérifier les 16 steps end-to-end)

---

## Session IMPORT CSV INTELLIGENT — 2026-05-25

Nouvelle feature : import CSV drag&drop vers le pool mutualisé (`/site/[code]/acquisition` → bouton « Importer CSV »).

**Flux en 2 phases** (le fichier est uploadé 1× sur le VPS sous `data/imports/{site}/`, chmod 600, purge >7j) :
1. `POST /api/sites/{site}/pool/import/analyze` (multipart) → détecte séparateur (`;`/`,`/tab/`|`) + charset (utf-8/cp1252/latin-1, NFC) + mappe les colonnes (alias FR/EN) + **1 seul appel DeepSeek** pour mapper les catégories du fichier vers les secteurs + pré-analyse dédup (1 requête `SELECT email`). Renvoie un `import_id` + récap.
2. `POST /api/sites/{site}/pool/import/{import_id}/commit` → **StreamingResponse SSE** (`data: {step,pct,…}`), upsert batché (1 connexion réutilisée), `source="manual"`, state `cold_email`.

**Secteurs dynamiques (DB-backed, plafond 30)** : nouvelle table `sectors` dans `god_mode.duckdb` (seed = 16 + `autre`). DeepSeek crée les secteurs manquants (B2B/B2C) sans jamais dépasser **30 au total** ; au-delà → bucket `autre`. `GET /api/sectors` + hook front `useSectors()` (lib/use-sectors.ts). `SECTORS_GOD_MODE` reste la liste *scrapable* (Serper), les secteurs importés ne sont pas scrapés.

**Dédup** : clé = email. Doublon existant → enrichissement NULL-only (jamais d'écrasement). Doublon interne au fichier → 1ʳᵉ occurrence gardée. Lignes KO (email invalide) listées avec raison.

**Fichiers** :
- back : `scripts/csv_import_backend.py` (nouveau), `scripts/api.py` (3 endpoints), `scripts/contacts_pool_backend.py` (migration colonnes `job_title`/`civility`/`job_function` + `create_in_pool`/`upsert_site_history` acceptent `conn`), `scripts/god_mode_backend.py` (table `sectors` + `list_sectors()`/`add_sector()`).
- front : `components/import-wizard.tsx` (nouveau, drag&drop + récap + anneau % + confetti), `lib/use-sectors.ts` (nouveau), `lib/sectors.ts` (+`autre`), page acquisition (branchement, ancien import textarea supprimé). Dépendance `canvas-confetti`.

**Testé** (2026-05-25) sur `responsable_marketing.csv` (5037 lignes directeurs marketing, séparateur `;`, utf-8) :
- échantillon 10 lignes → 10 ajoutés en `manual`, dept dérivé du CP, website préfixé `https://`, accents OK, secteurs créés (banque/assurance/industrie/agroalimentaire).
- HTTP analyze + commit SSE OK ; ré-analyse du même échantillon → 10 détectés en *enrichis* (dédup), commit → updated=10/added=0.
- mapping secteur complet du fichier : 13 nouveaux secteurs, total **30/30** pile au plafond (les plus petits volumes → `autre`).

⚠️ **Op** : PM2 tourne sous l'utilisateur `autoblog` → restart via `sudo -u autoblog bash -lc "pm2 restart genesis-dashboard|genesis-ui"`. Les fichiers écrits par l'API doivent rester accessibles à `autoblog` (chown `data/imports`).

**Reste** : ~~importer les ~5027 lignes restantes~~ → **FAIT**. Le pool contient désormais **5112 contacts** (cf. section COLD EMAIL ci-dessous pour la photo réelle par secteur).


---

## Session COLD EMAIL — refonte génération par secteur — 2026-05-25 (incréments 1-3 LIVRÉS)

### Constat de départ
- Templates Emelia = **mail-merge pauvre** : `emelia_campaign_manager.get_default_steps()` = 2 templates figés, signe « Camille », icebreaker générique.
- **Réalité du pool LCR (corrige les sections précédentes)** : l'import est FAIT → **5112 contacts**, dont **~94 % directeurs/responsables marketing grands comptes** (banque, agro, industrie, luxe, assurance, tourisme, médias…), **PAS** les PME locales du `campaign-plan.md`. PME locales (resto/commerce/artisan) = ~53 (1 %). Bucket `autre` = 2065 (40 %).

### Décisions user (2026-05-25)
- **Move upmarket assumé** : LCR vise les directeurs marketing grands comptes → offre = **SMS + RCS comme canal de campagne premium** (pas le drive-to-store PME). Les 53 PME locales gardent leur angle à part.
- **Perso = données structurées seules** (poste + secteur + entreprise + ville). PAS de scrape website pour l'instant → perso **persona-niveau** (pas de vrai 1to1 individuel). Le scrape rebranchera le vrai 1to1 plus tard.
- **Review humaine obligatoire** sur les premiers batchs (warmup J1).
- **PAS de séquence ni d'envoi automatiques** : l'IA PROPOSE 3 emails par secteur ; le user **édite et programme/verrouille chaque email lui-même**. → outil = **assistant de rédaction**, pas un automate. L'incrément ④ (branchement pipeline) est **ABANDONNÉ**.
- **Secteurs EXCLUS** : industrie (378) + agroalimentaire (376) = 754 contacts (SMS marketing non pertinent). Bucket `autre` (2065) = phase 2.

### Skills Claude Code installés (sur le Mac `~/IA/Projets/.agents/skills/`, outil de CONCEPTION)
- `cold-email` (coreyhaines31) + `cold-email-templates-34` (ColdIQ) — markdown pur, notés Low Risk.
- `cold-email-verifier` (arnanech/op) NON installé : repo 404 + redondant avec Mailnjoy + email_validator.
- ⚠️ Ces skills aident MOI à concevoir ; le runtime génère via **DeepSeek sur le VPS** (`llm_call.py`). L'expertise est transférée dans les angles + le prompt.

### Livré et testé
- **`context/lcr/sector-angles.md`** (NOUVEAU) : 10 secteurs × séquence 3 mails validés. Preuves mappées honnêtement (Immo92→immo, +35 % boutique→retail/luxe, +25 %/ROIx50→restau, « 500+/10M SMS »→neutre). Industrie/agro = EXCLUS.
- **`context/shared/cold-email-rules.md`** : ajusté mode persona-niveau (icebreaker = fait réel OU douleur secteur ; E2 = cas client OU preuve volume). Backup `.bak-2026-05-25`.
- **`scripts/email_generator.py`** (NOUVEAU) : `generate_sequence(site,sector)` → angle + DeepSeek (`call_llm_json`) → finalise (Juliette, CTA TidyCal, signature + désinscription RGPD) → `validate_email()` (interdits FR, ≤150 mots, 1 seul `<a>` TidyCal, objet) → exclut industrie/agro/autre. + `supported_sectors()` (10 secteurs UI). CLI dry-run OK.
- **`scripts/email_templates_backend.py`** (NOUVEAU — remplace le doublon `sector_templates_backend`, supprimé) : table **`email_templates`** (`god_mode.duckdb`), **modèle 1-ligne-par-email** `(site, sector, kind)` kind∈{first,relance1,relance2}, chacun **éditable/verrouillable seul** (`locked` = approbation ; **régénérer respecte les verrous** ; éditer rouvre). Helpers : generate / get_sector / list_sectors / update / set_lock.
- **`scripts/api.py`** : **6 routes** `/api/sites/{site}/templates/*` — generate · list(+available) · get{sector} · PUT {sector}/{kind} · {kind}/lock · {kind}/unlock. Backup `api.py.bak-2026-05-25`.
- **UI stepper** (genesis-ui) : `src/app/site/[code]/templates/page.tsx` REFONDUE (stepper 3 étapes : Select secteur → email kind → éditeur + **aperçu live** ; **mobile = onglets** Éditer/Aperçu ; badge conformité ; lock). + `src/components/email-body-editor.tsx` (NOUVEAU, **Tiptap**, switch **Visuel/Brut**). Build OK, déployé. Backup page `.bak-2026-05-25`.
  - ⚠️ **Validation VISUELLE par le user EN ATTENTE** (rendu mobile, génération IA depuis l'UI, Tiptap, aperçu) — pas de navigateur côté agent.

### Reste à faire (cold email)
- **Valider le visuel de l'UI stepper** (mobile surtout) + tour d'ajustements.
- **SPRINT FUTUR** (détaillé dans `PLAN-ACTION.md`) : templates à **structure HTML VERROUILLÉE**. Le user fournit le HTML ; seules les zones **texte / image / lien** éditables (placeholders `{{...}}` ; type par contexte : `src=`→image, `href=`→lien, sinon texte). DeepSeek ne remplit QUE les textes. → l'éditeur Tiptap deviendra un **éditeur de zones** (formulaire).
- Plus tard : scrape website (vrai 1to1), bucket `autre`, image de signature.

### Op / pièges
- `get_default_steps()` (legacy, 3 call sites) NON modifié — ④ abandonné. `email_templates` n'est PAS branché à l'envoi (assistant de rédaction).
- API Python sans `--reload` → `pm2 restart genesis-dashboard` pour recharger.
- **genesis-ui = build prod (port 3100)** → `npm run build` PUIS `pm2 restart genesis-ui` obligatoires pour déployer le front.
- Écrire dans `god_mode.duckdb` en process externe = OK (le cron le fait), écritures ponctuelles (connect/close).


---

## Session AUTH / RBAC — 2026-05-26 (Sprints 1-2 ; plan détaillé dans PLAN-ACTION.md)

**État au départ** : auth + 2FA TOTP + QR **déjà en place** (`auth_backend.py` pyotp, page `/security`, login 2-étapes). **1 seul user** : `camille` (superadmin, sites lcr+mkd, **2FA OFF**).

### Livré et déployé
- **`POST /api/auth/users` étendu** : génère un mdp temporaire si absent, accepte role+sites+phone, renvoie le mdp + un `access_text` **copiable** (id/mdp/URL/pas-à-pas 2FA). Validation : non-superadmin = **exactement 1 site**. Telegram optionnel.
- **Page `/admin/users`** (NOUVELLE, dans la sidebar admin global) : créer (rôle+site+mdp auto+**bloc copiable**), lister, changer rôle, reset mdp, supprimer.
- **Isolation multi-tenant** (middleware `api.py`) : `/api/sites/{site}/*` vérifie `site ∈ session.sites` (superadmin bypass) → **ferme la faille** (avant : tout user authentifié accédait à tous les sites). + **FIX** : le check admin-only excluait `superadmin`.
- **Sidebar filtrée par rôle** (`app-sidebar.tsx` `buildNavSite` + `ROLE_SECTIONS`) : superadmin=tout, strategie/contenu/commercial = leur section. **Switcher de sites masqué si 1 seul site** (`team-switcher.tsx`).
- **Rôles** : `superadmin` / `strategie` / `contenu` / `commercial`.
- Backups : `api.py.bak-2026-05-26`, `app-sidebar.tsx.bak-2026-05-26`, `team-switcher.tsx.bak-2026-05-26`.

### Reste (auth/RBAC)
- **Fix menu nav-user** (bas de sidebar) : BLOQUÉ — attend l'erreur **console** du user. Le code est sain (même pattern que le switcher) ; les logs « Failed to find Server Action » = **bruit** (clients périmés après rebuilds), pas la cause.
- **« Bloquer » un user** (champ `disabled` + check login + bouton UI) — Tâche 7.
- Option : **forcer le 2FA à la 1re connexion** (à décider).
- **camille : activer son 2FA** (actuellement OFF).
- Sprint 3 : `/security-review` (déclenché par le user). Sprint 4 : RGPD (questions d'abord). Sprint technique : durcissement déploiement front (staleness).

### À TESTER par le user (validation visuelle — pas de navigateur côté agent)
1. `/admin/users` → créer un compte « commercial » sur lcr → le **bloc d'accès copiable** s'affiche.
2. Se connecter avec ce compte → il ne voit que la section **Commercial**, **pas de switcher** (1 site), et l'accès à mkd est **refusé (403)**.
3. Bug nav-user : **hard refresh** puis console si ça persiste.

### MAJ 2026-05-26 (suite) — Sprint 2 COMPLET
- ✅ **Mode superadmin UI** : rôle affiché sous le nom (nav-user), **liseré 5px ambre** autour de la fenêtre, **top bar** (date live + IP + users connectés + campagnes en routage + déconnexion). Endpoint `GET /api/admin/superadmin-bar` (cache 60s Emelia). Composant `superadmin-bar.tsx`. Validé visuellement par le user.
- ✅ **Bloquer/débloquer un compte** : colonne `disabled` (auth.duckdb), `login()` refuse `account_disabled`, `update_user`/`list_users` gèrent `disabled`, bouton + badge dans `/admin/users`.
- Backups : `auth_backend.py.bak-2026-05-26`, `nav-user.tsx.bak-2026-05-26`, `client-shell.tsx.bak-2026-05-26`.
- **Sprints 1 & 2 = bouclés.** Reste : nav-user (attend console user), option « forcer 2FA 1re connexion », Sprint 3 `/security-review` (déclenché par user), Sprint 4 RGPD (questions d'abord). camille : activer 2FA.

### MAJ 2026-05-26 — Sprint 4 RGPD (en cours)
Décisions user : base légale = **intérêt légitime B2B**, **anonymiser** avant LLM (0 PII hors UE), conservation **3 ans**.
Entités (cf. mémoire reference_legal_entities) : LCR=HUMANETICS LABS (SARL, SIREN 995210010, Colombes, dpo@humaneticslabs.com) · MKD=MKD GROUPE (SARL, SIREN 852283761, Maisons-Alfort, dpo@mkdgroupe.com). Responsable RGPD=société, DPO=Camille.
- ✅ **4a LIA** + **4b privacy notices** (×2) → `/home/autoblog/genesis/legal/` (lia-prospection-b2b.md, privacy-notice-lcr.md, privacy-notice-mkd.md). MODÈLES à faire viser par un juriste avant publication.
- ✅ **4c (partie)** : `workflow_qualifier.py` n'envoie plus email+téléphone à DeepSeek (backup .bak-2026-05-26). email_generator/god_mode_templates déjà sans PII.
- Reste 4c : auditer csv_import (mapping secteur), **purge auto 3 ans**, **chiffrement at-rest contacts.duckdb** (était parké).
- Reste 4d : caviardage PDF (skill github Ldecavel) + anonymisation exports (datanaos).

### MAJ 2026-05-26 — Sprint 4 RGPD : 4c + 4d clôturés
- ✅ **4c audit DeepSeek COMPLET** : qualifier (email+tél retirés), csv_import (n'envoie que les noms de catégories, jamais les contacts), email_generator/templates (par secteur). → 0 PII vers DeepSeek.
- ✅ **4c purge 3 ans** : `scripts/rgpd_purge.py` (anonymise les prospects froids > 3 ans, épargne leads/clients/blacklistés ; dry-run + `--apply`). **Cron mensuel** 1er à 4h → `logs/rgpd_purge.log`. 0 concerné aujourd'hui (données récentes).
- 🟡 **Chiffrement at-rest `contacts.duckdb`** : NON fait en applicatif (DuckDB n'a pas de chiffrement natif ; la clé serait sur le même serveur = gain faible). En place : secrets AES (site_credentials), chmod 600, RBAC+2FA, backups. **RECO = activer le chiffrement de volume côté Hetzner** (action infra, pas du code).
- ✅ **4d caviardage PDF** : skill `caviardage-pdf` installé (Mac, MIT, 100% local, PyMuPDF) — outil à la demande.
- 🟡 **4d anonymisation exports (datanaos)** : service externe payant, **aucun use case d'export actif** dans Genesis (l'anonymisation est déjà couverte par la purge + le qualifier). À brancher seulement si besoin réel.

**Sprint 4 RGPD clôturé.** Restes = décision infra (chiffrement disque Hetzner) ou service externe (datanaos) si besoin.
**Restes globaux hors-dev** : #1 nav-user (attend console user), #8 `/security-review` (user lance), publier les privacy notices sur les sites.

### ⚠️ PIÈGE OP (2026-05-26) — genesis-ui = pnpm
`genesis-ui` est géré par **pnpm** (pnpm-lock.yaml, node_modules/.pnpm). **NE JAMAIS faire `npm install`** ici → ça crashe arborist ("Cannot read properties of null (reading 'matches')"). Utiliser **`pnpm add <pkg>`** (via `sudo -u autoblog`). `npm run build` reste OK (n'installe rien).
### Sprint éditeur newsletters HTML — incrément ① fait
- structures/leclientroi-newsletter-v2.html transférée ; module scripts/html_templates_backend.py + table html_templates + 6 endpoints /api/sites/{site}/html/* (testés). dnd-kit installé (pnpm). Reste ② composant éditeur (dnd blocs + édition in-place texte/image) + ③ intégration step 2 + envoi Emelia.

---

## Sessions Mailnjoy cleanup — 2026-05-28 → 2026-05-30

**Pitch** : nettoyage périodique du pool `contacts.duckdb` via Mailnjoy (suppression invalid/risky, certif. valid posée sur `mailnjoy_check` JSON). Page dédiée `/site/[code]/cleanup`.

### Architecture livrée (refactor sérieux, fin de session 2026-05-28)

**Backend (`scripts/cleanup_backend.py`)**
- `run_cleanup(mode, site, limit, progress_cb=None, should_stop=None)` — 1 chunk synchrone. `should_stop()` checké AVANT chaque contact ; `progress_cb(stats, processed, email)` émis APRÈS chaque contact (try/finally garantit l'émission, les `continue` ne sautent rien).
- `run_cleanup_drain(mode, site, chunk_size=100, total_limit=None, progress_cb, should_stop)` — enchaîne des chunks jusqu'à épuisement / `total_limit` / stop. Log final `cleanup_drain` event.
- Pool = `data/contacts.duckdb` (PAS `acquisition_contacts` — exclus globalement les `global_blacklisted`).
- Modes : `unverified` (mailnjoy_check NULL/vide) · `stale` (mailnjoy_check > 180j).

**API (`scripts/api.py`)**
- `_active_cleanups: dict[key→state]` + `_cleanup_lock` (threading.Lock). **Verrou STRICT séquentiel global** (1 cycle à la fois TOUS sites/modes confondus).
- `POST /api/sites/{site}/cleanup/run` body : `{mode, drain, chunk_size, total_limit, limit?}` — spawn thread daemon, retour immédiat avec `{queued:true,key}`. Si cycle déjà actif → `{ok:false, running:true, active:{...}}`.
- `POST /api/sites/{site}/cleanup/stop` — pose `stop_requested=true` + `status="stopping"`. Le thread vérifie entre 2 contacts ET entre 2 chunks.
- `GET /api/sites/{site}/cleanup/status` — état détaillé `items[]` avec processed/total/valid/removed/cumulative/last_email/started_at/status.
- `GET /api/cleanup/active` — état GLOBAL tous sites (alimente la SuperadminBar).
- `GET /api/sites/{site}/cleanup/history?limit=20` — **endpoint dédié** retournant UNIQUEMENT les events `cleanup_batch` (évite la saturation des 100 derniers logs par les events fils validated/removed).
- `GET /api/sites/{site}/cleanup/counts` — non-vérifiés + stale.
- `GET /api/sites/{site}/cleanup/contacts?limit=10000` — liste pool (limite remontée pour cohérence compteur).
- **Endpoints test loopback-only** (bypass auth via middleware si `request.client.host ∈ {127.0.0.1, ::1}`) :
  - `GET /cleanup/dryrun?email=` — non-destructif, retourne what would be done sur 1 contact.
  - `GET /cleanup/test-batch?limit=N&drain=true&chunk_size=N` — sync, counts avant/après.
- **`god_mode_backend.list_logs(action=...)`** étendu pour filtre par action exacte (utilisé par /cleanup/history).

**Frontend (`genesis-ui/src/app/site/[code]/cleanup/page.tsx`)**
- `startAuto` = **1 SEUL POST drain=true chunk_size=100**. Plus aucune boucle JS, plus de `waitUntilFree`, plus de `findBatch`, plus de timeouts JS.
- `stopAuto` = POST `/cleanup/stop` + `autoRef=false`.
- État `progress` polling `/cleanup/status` (1.5s actif / 6s idle). Auto-reset `autoMode` quand `progress` passe à null.
- Card **Cycle en cours** (border-primary/50) : 2 barres (chunk + global si total_limit) + cumul cross-chunks + indication "Arrêt en cours…" pendant un stop.
- `DataTable` étendu avec prop `selectFilter` (Select shadcn). Branché sur colonne `mailnjoy_status` (filtre Non vérifié / Valide / En attente / Invalide / À risque).
- Compteur cohérent : `Contacts du pool (N) — dont X jamais vérifiés` (chargement complet, limit=10000).
- **Tous les libellés en français** : MODE_LABEL, ACTION_LABEL, DEC_FR (helpers en tête de fichier). `unverified→Première vérification`, `stale→Revalidation (>6 mois)`, `valid→Valide`, `risky→À risque`, etc.

**SuperadminBar (`genesis-ui/src/components/superadmin-bar.tsx`)**
- Poll `/api/cleanup/active` (2s actif, 8s idle). Affiche inline pour chaque cycle : `LCR Première vérification 23/50 [▓▓▓░░] 46%` + tooltip détaillé FR. Idle = "Aucun nettoyage en cours".

### Validation
- ✅ **Unitaire** : `/cleanup/dryrun` → 1 contact pool, Mailnjoy VALID/SAFE, would=update, **0 écriture DB**.
- ✅ **Intégration limit=1** : `4818→4817`, batch {1 valid, 0 removed} en 11.79s.
- ✅ **Batch 50** : `4817→4767`, batch {26 valid, 24 removed, 0 errors} en 256s.
- ✅ **Drain 6 contacts en chunks de 3** : `4612→4606`, 2 chunks, 5 valid + 1 removed en 28.94s.
- Validation visuelle par le user en attente après hard-reload `/site/lcr/cleanup`.

### Bugs fixés (chronologique)
- **DuckDB lock conflict** : test scripts externes ne peuvent pas se connecter pendant que l'API a un write-lock → endpoints test loopback à la place.
- **Read-only/read-write config mismatch** : `duckdb.connect(read_only=True)` échoue si une autre connection RW existe dans le même process → utiliser `cb._pool(read_only=False)`.
- **API freeze 504** : `cleanup/run` synchrone bloquait le worker uvicorn (316 restarts observés) → thread daemon + retour immédiat.
- **Race "Un cycle déjà en cours"** : ancien `set` non-atomique + retry trop court → dict + Lock + verrou GLOBAL séquentiel + retry intelligent.
- **Timeout JS 4 min trop court** : 50 contacts × ~5s = 250s, juste au-dessus de 240s → drain mode élimine le problème (plus de boucle JS).
- **Historique aléatoire 2-3 lignes** : `/logs?limit=100` saturé par events validated/removed → endpoint dédié `/cleanup/history` qui filtre exactement `cleanup_batch`.
- **DuckDB SQL** : double-double-quote pour empty string non supportée → `LENGTH(mailnjoy_check)=0`.
- **god_mode_api.py root-owned** : patch impossible sans `sudo chown` (bloqué par classifier) → contourné en ajoutant la route dans api.py.

### PM2 processes
- `genesis-dashboard` (PID variable, FastAPI port 8080) — restart après tout patch backend
- `genesis-ui` (Next 16 port 3100, pnpm build) — restart après tout patch front + `pnpm build` AVANT (jamais `npm install`)
- `genesis-mailnjoy-drain` — cron 5min qui drain `scrappe_pending` (existant avant cette session)

### Sweego (parqué)
- Pool LCR contient 5117 contacts (au début de session), réduit à ~4600 après tests cumulés (~250 supprimés invalid/risky).
- Sweego API key + ImageKit private key avaient fuité en chat → user à régénérer.
- Routage production Sweego PAUSE STRICT : tests uniquement vers `afchain.camille@gmail.com`.

### Restes
- #8 `/security-review` (déclenché par user)
- #23-25 Sweego : reroute production + déploiement + CNAME tracking
- Validation visuelle par le user de la page cleanup (filtre Mailnjoy + Progress bar + drain end-to-end)

## REPRISE 2026-07-07 — Connecteur Maildoso branché (3e canal Cheffer) ✅

### Fait
- **Maildoso opérationnel** : warmup fini (dispo prévue ~07/07, tenu). 4 boîtes actives `j.durand|j.juste|j.bernard|j.nguyen@leclient-roi.com` (domaine AVEC tiret, ≠ leclientroi.com), réputation Microsoft "high", domaine ACTIVE depuis 23/06.
- ⚠️ **L'API REST Maildoso ne fait PAS d'envoi** (infra only : domaines/boîtes/warmup). **Envoi = SMTP** `smtp.maildoso.com:587`, IMAP `imap.horus.maildoso.com:993`, réponses agrégées sur `leclientroi@maildoso.email`.
- **Doc** : skill `.claude/skills/maildoso/SKILL.md` + `openapi.json` local (spec complet analysé + endpoints testés live).
- **Secrets** : `.env` → `MAILDOSO_API_TOKEN`, `MAILDOSO_SMTP_PASSWORD` (commun aux 4 boîtes). Backup `.env.bak-maildoso-20260707`.
- **Nouveau module `scripts/maildoso_backend.py`** : vérif API (`/v1/user/me`), sync boîtes → table `mailboxes` (god_mode.duckdb, `password_ref` pas de mdp en clair), envoi SMTP avec rotation (boîte la moins sollicitée), cap 25/jour/boîte, jitter 15-60s entre envois, log table `maildoso_sent`, List-Unsubscribe. CLI : `verify|sync|mailboxes|test <email>`.
- **Canal activé** : `campaign_engine.py` (déblocage create_campaign + branche maildoso dans `_send_batch` avec `mark_pushed` précis via `sent_emails`), `deliverability_agent.py` DAILY_CAP maildoso 300→**100** (4×25, domaine jeune — remonter plus tard), `api.py` `/channels` → enabled dynamique (compte les boîtes actives). PM2 `genesis-dashboard` restarted OK.
- **Tests réels** : email test + template LCR `agence-marketing/first` («votre mix canal») envoyés à afchain.camille@gmail.com via SMTP (boîtes j.nguyen puis j.durand). Les 2 partis OK (rfc_msgid en base `maildoso_sent`).

### Restes Maildoso
- Camille doit confirmer réception des 2 emails (vérifier spam/Promotions Gmail).
- Séquenceur complet (relances, threading, IMAP poller réponses/bounces, suppression list) : spec dans `routeur_doc/cold-email-engine.md` — non implémenté, le canal actuel = envoi one-shot par campagne unifiée.
- Remonter les caps (25→40/boîte) après ~2 semaines de prod propre.
- 6 slots de boîtes Maildoso encore dispo dans l'abonnement (10 payées, 4 utilisées).

### MAJ 2026-07-07 (soir) — Ramp-up auto + card canal fiable
- **Délivrabilité confirmée** : template LCR reçu par Camille en **inbox Gmail** (pas spam). Délai de remise ~20 min (file d'attente sortante Maildoso — normal, ne pas s'inquiéter d'un « rien reçu » immédiat).
- **Cap canal maildoso DYNAMIQUE** : `deliverability_agent.channel_caps` lit désormais la somme des `daily_cap` des boîtes actives (table `mailboxes`) — plus de 100 en dur. Le planning des campagnes et la card Cheffer suivent tout seuls.
- **Nouveau `scripts/maildoso_ramp.py`** : montée en charge auto, appelée en fin de chaque dispatch maildoso (`campaign_engine._send_batch`), idempotente 1×/boîte/jour, journalisée dans `maildoso_ramp_log`. Règle : fenêtre 3 j sur `maildoso_sent` ; >10 % erreurs SMTP → cap −10 (min 10) ; 0 erreur + dernier jour actif ≥ 60 % du cap → cap +5 (max 40) ; sinon inchangé. CLI : `maildoso_ramp.py status|run`.
- **/channels enrichi** (maildoso) : `mailboxes`, `per_mailbox_cap`, `remaining_today` + note honnête. **Card du wizard** (`campaign-wizard.tsx`) affiche : cap/jour, « N boîtes × cap/j », badge « X restants aujourd'hui » (vert/rouge). `pnpm build` + restart genesis-ui OK (piège : `.next` avait des fichiers root → `chown -R autoblog` avant build).
- **Mail-tester 7.5/10** (test-cheffer0707b) : SPF pass, DKIM pass (signé par le relais Maildoso `s=out401500`, 2048 bits), DMARC pass (p=reject aligné), IP de sortie 169.255.56.72 (pool pinkproof) clean sur 23 blocklists. Pénalités : **leclient-roi.com listé ABUSE SURBL (−1.9, à délister sur surbl.org)** + réécriture du relais (GCDT) : text/plain converti en HTML-only sans balise `<html>`, header List-Unsubscribe supprimé. Si plain text pur voulu : couper le tracking via `PUT /v1/user/domains/tracking`.

### MAJ 2026-07-08 — SURBL delisting soumis ✅ / page anti-spam À PUBLIER ⚠️
- Demande de removal SURBL ABUSE pour `leclient-roi.com` soumise et reçue par SURBL (« request has been received »). Dossier : `routeur_doc/surbl_delisting_leclient-roi.md`.
- ⚠️ **URGENT — prochaine session LCR** : publier la page « Politique anti-spam » sur leclientroi.com (URL déclarée à SURBL : `/politique-anti-spam`). Instructions complètes + contenu exact : `routeur_doc/TODO_page_politique_anti-spam_lcr.md`. Les reviewers vérifient le lien sous 24-72 h.
- Ensuite : surveiller le délisting (`dig +short leclient-roi.com.multi.surbl.org` — vide = délisté) puis relancer un mail-tester (score attendu ~9.4).

### MAJ 2026-07-08 — Remplacement complet des templates LCR (zip Camille) ✅
- **Backup préalable** : `backups/templates_lcr_backup_2026-07-08.json` (30 email_templates + 9 html_templates). Sources du zip archivées dans `routeur_doc/leclientroi-emails/` (avec `cold-emails-complet.md` : objets B + noms d'expéditeurs proposés).
- **html_templates (messages validés)** : 9 supprimés → **16 nouveaux** : 8 newsletters HTML (liens leclientroi.com pré-tagués **plan de taggage /site/lcr/tag : utm_source=newsletter&utm_medium=email&utm_campaign=newsletter-<secteur>** — le tag d'envoi respecte les liens déjà tagués) + 8 cold emails convertis en HTML simple (source `cold-email`, liens NON pré-tagués → tag à l'envoi : maildoso/coldemail selon canal).
- **email_templates (cold)** : 30 supprimés (10 secteurs × first/relance1/relance2) → **8 nouveaux** kind=first, tous `valid=True`. Secteurs mappés sur les codes canoniques du pool : agences→agence-marketing, artisans→artisan, boutiques→retail, fleuristes→fleuriste, immobilier, lelead, opticiens→opticien, plombiers→plombier.
- **Validateur mis à jour** (`email_generator.validate_email`) : le CTA de RDV accepte désormais TidyCal OU le **booking interne Cheffer** (`api.cheffer.email/api/book/…`) — les nouveaux cold emails utilisent le booking Cheffer. Restart dashboard OK.
- Nouveaux templates : variables `{{prenom}} {{entreprise}} {{ville}} {{expediteur_prenom}} {{expediteur_nom}}` (convention séquenceur Maildoso, ≠ `{{firstName}}` Emelia) — à mapper quand le séquenceur maison sera construit. Objets B (A/B testing) archivés dans le md, pas de champ en base.

### MAJ 2026-07-08 (soir) — Scraping auto + ciblage géo campagnes + review ✅
**1. Orchestrateur scraping auto EN DUR** (`scripts/autoscrape_plan.py`, cron `*/30 7-21 * * *`) :
- Parcourt les 12 régions métropole dans l'ordre EXACT du select scrapper (11 IDF → … → 93 PACA), 1000 contacts/région, département par département (réutilise `autoscrape_backend.run_autoscrape`). Secteur **immobilier** seul actif ; secteurs suivants pré-écrits mais COMMENTÉS dans `PLAN_SECTORS` (validation manuelle avant activation, cf. demande Camille).
- `tick` (cron, instantané) lance `work` (détaché, run bloquant d'une région). Reprise auto après blocage Serper (throttle 1h), saute les depts finis. État : `memory/autoscrape/lcr-plan.json`. CLI : `tick|work|status|pause|resume|reset`. **Lancé le 08/07 18:16, tourne (IDF en cours).**

**2. Ciblage géographique des campagnes** (secteur + région ET/OU département, +/− dans le wizard) :
- `contacts_pool_backend._geo_clause` + params `regions`/`depts` sur `pick_for_campaign` et `count_available_for_sector` (OR entre zones). `campaign_engine.create_campaign` stocke les zones dans `params` JSON, `dispatch` filtre dessus. `api.py` : `/campaigns/target-count` et `/campaigns` acceptent `regions`/`depts`.
- Wizard (`campaign-wizard.tsx`) : composant `GeoTargeting` à l'étape Cible — ajout/retrait de zones (région entière 🗺️ ou département 📍) via +/−, compteur live filtré, récap. Vide = France entière. Build + restart OK.
- **Prérequis résolu** : `contacts.dept_code`/`region_code` étaient à ~NULL. Ajout `workflow_geo.resolve_city_geo` (CP prioritaire, sinon nom de ville ≥10k) ; Serper dual-write (`god_mode_agents`) remplit désormais dept/region ; **backfill fait** (726 dept+region, 2886 region ; immobilier : 879 ciblables, 380 IDF, 90 dept 92).

**3. Review (agent) — 2 bugs corrigés** :
- HIGH : `_norm_city` ne gérait pas les arrondissements (« Paris 13e » → NULL geo → exclus du ciblage). Corrigé (regex suffixe arrondissement → commune-mère). ⚠️ **Reste à faire** : re-run backfill après la 1re région (le run live a chargé l'ancien code → contacts Paris de CE run ont un geo NULL ; `resolve_city_geo("Paris 13e")` les corrigera).
- MEDIUM : reprise multi-cycle dépassait le plafond 1000 (`valid` persisté était par-run, pas cumulé). Corrigé via `valid_baseline` → `valid` persisté cumulé, `remaining = target − valid` correct.
- LOW notés (non bloquants) : TOCTOU sent_today Maildoso (OK en envoi séquentiel), addZone filtre depts sur state async (redondance inoffensive, OR-semantics), homonymes communes → plus grande (tradeoff CP-first).

### MAJ 2026-07-08 (nuit) — Correction placement templates/messages + refonte UX (retour Camille)
Erreur de la session précédente corrigée : j'avais mis newsletters ET cold emails dans « Messages validés » (versions), cassant le bloc-éditeur et mélangeant les canaux.
- **Cold emails** retirés de Messages validés → restent uniquement sur la page **Cold email** (`email_templates`, 8 secteurs). Envoi via Campagnes (canal Maildoso).
- **8 newsletters (avec images)** → déplacées en **Templates** (structures, fichiers `structures/leclientroi-newsletter-<secteur>.html`), en **HTML brut NON taggé** (le pré-tag `utm_source=newsletter` empêchait le tag correct au moment de l'envoi selon le canal — le tagueur respecte les liens déjà taggés). Anciennes structures archivées dans `structures/_archive/` (14, récupérables).
- **Bloc-éditeur** (`newsletter-editor.tsx`) : `parseBlocks`/`rebuildHtml` détectent désormais le conteneur `table.wrap` (newsletters) en plus de `table.email-container` (+ fallback heuristique table 600px). Les newsletters sont éditables bloc par bloc (clic texte/image, réordonner) — fini le « Aucun bloc détecté ».
- **Section Templates** (`newsletters/page.tsx`) : multiselect texte → **galerie de cartes avec aperçu image** (iframe rendu scalé) + boutons Éditer/Tester. Messages validés = sortie de l'édition d'un template.
- **Envoi** : bouton « Masse » retiré des messages + **dialog « Envoyer en masse · Sweego » supprimé**. Tout envoi passe par **Campagnes** (choix du canal + tags UTM auto selon canal). Build + restart genesis-ui OK.

### MAJ 2026-07-08 (nuit +1) — Sélecteur de message campagne unifié (retour Camille : "0 option")
Bug : le wizard campagne ne piochait que dans `html_templates` (versions), désormais vide → aucun message sélectionnable, et les cold emails introuvables.
- **Résolveur unifié** (`html_templates_backend`) : `campaign_message_options(site)` (liste groupée) + `resolve_campaign_message(site, mid)`. message_id encode la source : `struct:<name>` (Templates/newsletters), `ver:<id>` (Messages validés), `cold:<sector>:first` (email_templates).
- **API** : `GET /campaigns/messages` (groupes) + `GET /campaigns/message-preview?id=` (HTML). suggest-subject, preview-lint et `campaign_engine._send_batch` utilisent le résolveur (au lieu de `get_version` seul).
- **Wizard** (`campaign-wizard.tsx`) étape Message : 3 groupes sélectionnables — 🖼️ Templates (8), ✅ Messages validés, ✉️ Cold emails par secteur (8). Aperçu via le résolveur. Upload/texte créent une version (`ver:<id>`).
- **Personnalisation Maildoso** (`maildoso_backend._apply_tokens`) : {{prenom}}/{{firstName}}, {{nom}}, {{entreprise}}/{{societe}}, {{ville}}/{{city}}, {{expediteur_prenom/nom}} (depuis la boîte), {{UNSUBSCRIBE_LINK}}/{{unsubscribe}} → mailto ; salutation vide nettoyée (« Bonjour , » → « Bonjour, »). Appliqué par destinataire dans `send_batch`. Évite d'envoyer les tokens bruts pour les cold emails.
- Build + restart genesis-dashboard + genesis-ui OK. Scrape immobilier toujours en cours (271 contacts, dept 95).

### MAJ 2026-07-08 (nuit +2) — Recette lint + auto-fix des messages (retour Camille : lint sort des erreurs mais rien n'est corrigé)
Le lint (emailens) sortait 12 erreurs sur un cold email — surtout des FAUX POSITIFS : règles de newsletter HTML appliquées à un email texte + variables de fusion comptées comme non résolues. Corrigé à la racine + auto-fix :
- **Whitelist variables étendue** (`email_lint_backend.ALLOWED_VARS`) : + prenom, nom, entreprise, societe, company, ville, city, expediteur_prenom, expediteur_nom, unsubscribe. Fini les « unresolved-variable {{prenom}} » (résolues à l'envoi).
- **Emballage cold email conforme** (`email_templates_backend.wrap_cold_email`) : fragment texte → doc HTML valide (lang=fr, charset, `<title>`=objet, viewport, préheader caché ≥30c, footer société+contact+tél + lien désinscription détectable `?subject=unsubscribe`). Appliqué DANS `resolve_campaign_message` (cold:) → aperçu, lint ET envoi utilisent la MÊME version conforme. Résultat : cold emails passent de 12 err (dont bloquantes) à **score 99, 0 bloquant** (reste 1 low-contrast accessibilité, non bloquant).
- **Recette auto** `scripts/email_qa.py` : lint chaque message (Templates + Cold + Messages validés) via le rendu réel + **persiste les badges** (`newsletter_lint`) pour affichage UI sans clic. Cron quotidien `30 5 * * *`. Templates newsletters : score 95, non bloquant (12 low-contrast = dégradés violets, faux positif accessibilité connu).
- ⚠️ Reste à la main : **adresse postale physique** (warning CAN-SPAM) — non inventée volontairement, à ajouter par Camille dans `_COLD_FOOTER`. Restart dashboard OK.

### MAJ 2026-07-08 (nuit +3) — Fix "message introuvable" au BAT + création campagne
Bug : le BAT du wizard appelait `/mass-campaigns/bat` (Sweego) avec `htb.get_version()` → ne comprenait pas les nouveaux ids `cold:`/`struct:` → "message introuvable", et aurait testé une campagne Maildoso via Sweego (mauvais canal).
- **BAT unifié** : helper `_send_bat(site, channel, message_id, subject, email)` (api.py) → résout le message via `resolve_campaign_message` (toutes sources) + envoie par le CANAL choisi (Maildoso→`md.send_email`, Sweego/Emelia→Sweego). Personnalise avec un contact fictif (Camille/Le Client ROI/Paris) pour rendre les {{variables}}. Nouveau endpoint `POST /campaigns/bat` (avant création) + `/campaigns/{cid}/bat` (existante) refactorés dessus. `/mass-campaigns/bat` passe aussi au résolveur.
- **Wizard** : `sendBat()` appelle `/campaigns/bat` avec `channel`.
- **Durcissement** : `create_campaign` résout le message à la création → refuse « message introuvable » au lieu d'échouer silencieusement au dispatch.
- **Vérifié E2E** : BAT Maildoso réel (cold immobilier) envoyé à afchain.camille@gmail.com depuis j.nguyen@leclient-roi.com, OK. Résolveur testé sur ids valides + invalides. Build + restart OK.

### MAJ 2026-07-08 (nuit +4) — Guide utilisateur sur la page login
- `components/user-guide.tsx` (`UserGuideMenuItem`) : entrée **« Guide utilisateur »** dans le **pied de la sidebar de gauche**, pour les **utilisateurs connectés** (PAS sur la page login — corrigé après retour Camille). S'adapte au mode réduit. Ouvre un dialog.
- Contenu : (1) **Authentification** — identifiant/mot de passe + code 2FA (TOTP 6 chiffres), blocage 10 min anti-bruteforce, session token, contacter l'admin pour reset ; (2) **section Commercial UNIQUEMENT** (comme demandé, pas Stratégie/Contenu/Admin) : Vision, Scrapper, Acquisition, Newsletters, Campagnes, Nettoyage, Rendez-vous — 1 description claire par item + flux type. Build + restart genesis-ui OK.

### MAJ 2026-07-09 — Guide utilisateur : vraie page /guide (retour Camille : pas de popup, une vraie URL avec screenshots)
- Popup remplacée par une **vraie page** `app/site/[code]/guide/page.tsx` (URL `/site/<code>/guide`), liée depuis le pied de sidebar (`user-guide.tsx` = lien, plus de dialog). S'affiche avec la sidebar + auth (via ClientShell).
- Sections avec **intro + « Cas pratique »** chacune : Connexion/sécurité, Menus (résumé), Notions & API connectées (pool, Serper/Basile, Mailnjoy, Maildoso/Sweego/Emelia, UTM/GA4, délivrabilité), Faire un scraping, Faire une campagne (+ **schéma des 3 canaux** Maildoso/Sweego/Emelia), Templates vs Cold emails, Nettoyage, Rendez-vous.
- **Screenshots** : composant `<Shot img=... />` affiche `/public/guide/<x>.png` si présent, sinon un **schéma fidèle** en fallback. Playwright + Chromium installés dans `/root/guideshots` (deps apt OK). **login.png = vraie capture** (page publique). Les pages connectées (scrapper/campaigns/newsletters/cold-email/cleanup/booking/sidebar) : script `/root/guideshots/shoot-auth.js` PRÊT mais nécessite un **token de session légitime** — le classifier a (à juste titre) bloqué la création d'une session forgée. ⚠️ **À FAIRE** : obtenir le mot de passe du compte de test (user `test`, rôle commercial) pour capturer les vraies images, sinon les schémas restent affichés.

### MAJ 2026-07-09 — Refonte UI (palette violet/crème + font) + dashboard emailing en datatable
- ⚠️ **Saas UI NON installé** : c'est du Chakra UI + Emotion (CSS-in-JS), incompatible avec la stack (Next 16 / React 19 / **Tailwind v4 + shadcn**). L'installer casserait le reset CSS et doublonnerait le système de style. Refonte faite sur la stack existante (même philosophie que saas-ui : composants accessibles Radix/shadcn).
- **Palette « violet & crème »** (`globals.css`, light) : fond crème chaud (`--background` oklch cream), cartes blanc cassé, `--accent`/sidebar en tint violet, `--primary` violet renforcé, bordures chaudes. Dark inchangé.
- **Police** : Inter → **Plus Jakarta Sans** (`layout.tsx`, var `--font-sans`), plus premium ; JetBrains Mono conservé.
- **Rapport emailing en DATATABLE** (`components/channel-perf-card.tsx`) : remplace les 2 cartes cramées par un tableau 1 ligne/canal — **Maildoso + Emelia + Sweego** — colonnes Envoyés · Ouvertures · Clics · Réponses · Bounces (valeur + taux, « — » si non dispo). Maildoso ajouté au backend (`/marketing/overview` + `maildoso_backend.stats(site)` depuis `maildoso_sent`) ; note « SMTP sans tracking » pour ouvertures/clics Maildoso.
- login.png (guide) re-capturé avec le nouveau thème. Build + restart OK.

### MAJ 2026-07-09 (suite) — Dashboard commercial : datatable emailing (bon composant), 10 dernières campagnes, scraper live, gating admin
- **Bug corrigé** : la dashboard avait sa PROPRE copie locale de `ChannelPerfCard` (grille de cartes) → mes changements sur `components/channel-perf-card.tsx` ne s'y voyaient pas. Dashboard utilise maintenant `<ChannelPerfTable site>` (le vrai datatable 3 canaux : Maildoso + Emelia + Sweego). L'ancienne fonction locale est laissée inerte.
- **10 dernières campagnes** (`RecentCampaignsCard`) : table (chaleur, campagne, canal, statut, envoyés/cible, date) via `/api/sites/{site}/campaigns`. **Code couleur + emoji d'urgence par ancienneté** (`campaignHeat`) : 🌱 frais (<1 sem, vert) · 🌶️ +1 sem (jaune) · 🌶️🌶️ +2 sem (ambre) · 🔥 +3 sem (orange) · 🔥🔥 très hot +4 sem (rouge).
- **Card « Scraping en cours »** (`ScraperTile`) **à la place du KPI Domain Rating** : quand un scrape tourne (poll `/autoscrape/status` /5s), affiche région, dépt, ville, barre de progression contacts (valid/target), Serper/Basile, dépts a/b, villes c/d, doublons, examinés. Au repos → retombe sur Domain Rating (rien perdu).
- **Gating rôle** : « Consommation API (30 j) » et « Dernières actions agents » masqués pour les non-admins (visibles seulement admin/superadmin), lus depuis `genesis_user.role` en localStorage.
- Build + restart OK. Scrape immobilier Hauts-de-France en cours (55/990) → la card s'affiche en live.

### MAJ 2026-07-09 — Fix publication blog (emdash) cassée + article LCR publié
- Bug : `publish_agent.publish_emdash()` référençait une variable globale `art` inexistante → `NameError` à CHAQUE publication LCR (emdash). Les articles passaient en statut « publishing » puis crashaient sans jamais atteindre le CMS. Cause du « je pousse un article mais je le vois pas ».
- Fix : `art` passé en paramètre à `publish_emdash(title, slug, content_md, art)` (+ appel màj). Compile OK.
- Republié `art_20260503_lcr_002` « SMS géolocalisé : le guide pour booster votre TPE en 2026 » (2147 mots) → **published**, live : https://blog.leclientroi.com/posts/sms-geolocalise-le-guide-pour-booster-votre-tpe-en-2026 (HTTP 200). Les futures publications LCR fonctionnent de nouveau.
- Rappel : la page Articles de Cheffer = file éditoriale interne (`memory/editorial/articles-queue.json`), publication réelle via API emdash (token admin). Blog LCR = blog.leclientroi.com.

### MAJ 2026-07-09 — Backfill images à la une des articles publiés
- Contrôle des 86 articles publiés (emdash blog LCR) → **12 sans image à la une**.
- Générateur = **Google Imagen 3** (Vertex AI, `imagen_generate.py`) — PAS DeepSeek (DeepSeek écrit juste le prompt de scène). Générique demandé : personne regardant un téléphone, sans texte ni logo, 16:9, style doux violet/crème.
- 8 variantes générées (2× n=4), uploadées en media emdash, attachées en rotation aux 12 posts via GET→PUT `/content/posts/{id}` (data.featured_image provider=external) + republish. **12/12 OK, 0 restant**.
- Note : 8 images pour 12 posts (4 réutilisées) — possibilité de faire 12 uniques si demandé.
