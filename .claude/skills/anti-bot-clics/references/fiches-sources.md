# Fiches sources — qualification des clics email (cahier § 6, § 7, § 8)

> Recherche du 26/09/2026. Une fiche par source, au format du § 8, puis une note /50
> (10 critères × 5 : Pertinence, Fiabilité, Maintenabilité, Couverture B2B, Faux positifs,
> Explicabilité, Vie privée, Intégration, Tests, Valeur pratique).
> Code lu via raw.githubusercontent.com / api.github.com (lecture seule). Les données Mass Email
> citées (cas BNP) ont été lues en **lecture seule** (`SET SESSION READ ONLY`) le 26/09/2026.

---

## Livrable A — Inventaire (tableau de synthèse)

| # | Source | Type | Activité | Licence | Règles trouvées | Note /50 | Décision |
|---|---|---|---|---|---|---:|---|
| 1 | MicrosoftDocs customer-insights `bot-protection.md` | doc officielle | commit 02/09/2026 | CC-BY-4.0 | page intermédiaire, pas de filtre sur les ouvertures | 30 | retenir partiellement (principe) |
| 2 | Mautic issue #16263 | issue | 14/06 → 15/09/2026, ouverte | — | rafale d'IP distinctes (≥ 3 IP / 30 s) ; échec des 3 signaux historiques | 41 | **retenir** |
| 2b | msoukhomlinov/IntellectITBotFilterBundle (lié à #16263) | dépôt | 14/09/2026 | GPL-3.0 | décorateur rafale IP + honeypot caché + ASN pour affichage seulement | 38 | retenir partiellement (règle, pas le code GPL) |
| 2c | mautic/mautic `BotRatioHelper.php` (7.x) | code | actif | GPL-3.0 | délai < 2 s + IP liste + UA liste, 2 sur 3 | 22 | documenter seulement (contre-exemple) |
| 3 | alm-000/slack-crm-automation | dépôt | 14/06/2026, 0 ★ | MIT | UA listes larges, préfixes IP cloud géants, délai < 5 s, MPP < 30 s | 17 | **écarter** (sauf journal `is_bot`+`bot_reason`) |
| 4 | GoPhish issue #1607 | issue | 2019 → 02/2025 | — | JS de confirmation ; limites : les scanners exécutent le JS ; ASN | 27 | documenter seulement |
| 5 | atc0005/safelinks | dépôt | 17/09/2026 | MIT | format `https://<dc>.safelinks.protection.outlook.com/?url=…&data=…&sdata=…&reserved=0` | 24 | documenter seulement |
| 6 | polarityio/proofpoint-url-decoder | dépôt | **introuvable (404)** | — | — | — | remplacé par 6b |
| 6b | cardi/proofpoint-url-decoder | dépôt | 02/07/2024 | CC0 | formats urldefense v1/v2/v3 | 22 | documenter seulement |
| 7 | Gist OVlasiuk (urldec.py) | gist | 13/06/2025 | GPL v3 (en-tête) | regex Proofpoint v1-v3 + Safe Links | 19 | documenter seulement |
| 8 | Gist NeutralKaon (CLI decoder) | gist | 09/04/2025 | GPL v3 | regex Safe Links + Proofpoint | 18 | documenter seulement |
| 9 | Ghost issue #30388 | issue | 31/08 → 09/09/2026, PR #30625 | MIT | exclure tout événement `client-info.bot` (Mailgun) | 31 | retenir partiellement (principe « verdict ESP = signal ») |
| 10 | jdavidbakr/mail-tracker #255 + README | issue + dépôt | 03/2025 ; dépôt 07/09/2026 | MIT | UA exacts / regex bot ; écouteur `skip` | 18 | écarter (règles) / documenter |
| 11 | GitHub topic `email-analytics` | index | 09/2026 | — | aucun projet utile (trackers de pixel) | 8 | écarter |
| 12 | shamanic-technologies/instantly-service #773 | issue (trouvée § 6.2) | 11/09/2026 | — | **paire désinscription + lien ±60 s**, HEAD, UA MSIE 8/Trident (Safe Links), Chrome non réduit, fenêtre de décision 60 s, recalcul | 40 | **retenir** |
| 13 | MediumMasala/click-tracker-email | dépôt (trouvé § 6.2) | 25/06/2026 | aucune | UA par familles + `Sec-Purpose: prefetch` → 204 + interstitiel JS | 29 | retenir partiellement (idées, pas le code) |
| 14 | fusion-ai-uk/links-fusionagency-solutions | dépôt (trouvé § 6.2) | 2026 | **privée / commerciale** | `client_kind` via `Sec-Fetch-*`, grappes écho/répétition 10 s, IP en HMAC | 30 | documenter seulement (idées) |
| 15 | 00destruct0/kb4-bot-click-prevention | doc GitHub | 07/02/2026 | MIT | liste d'IP manuelle (KnowBe4) | 10 | écarter (simulation de phishing, IP figées) |
| D1 | Microsoft Learn — Safe Links (en + fr) | doc officielle | 22/05/2026 | — | réécriture, scan avant remise, scan au clic, mode API sans réécriture | 40 | **retenir** (faits) |
| D2 | Microsoft Learn — Safe Links policies | doc officielle | 17/07/2026 | — | « Wait for URL scanning », « Do not rewrite URLs » | 36 | retenir (faits) |
| D3 | Microsoft Learn — Prompt injection protection (Defender) | doc officielle | 10/09/2026 | — | texte caché = signal d'évasion combiné | 30 | retenir (nuance le guide délivrabilité) |
| D4 | Proofpoint (Essentials, datasheet PDF, BMCC CUNY) | docs | — | — | `urldefense.com`, sandbox prédictif + au clic | 22 | documenter (portail Essentials = page de login, PDF illisible) |
| D5 | Mimecast (page produit ; support Zendesk 403) | doc | — | — | réécriture + scan au clic ; `protect-xx.mimecast.com`, `url.xx.y.mimecastprotect.com` | 22 | documenter |
| D6 | Barracuda Link Protection | doc officielle | — | — | `linkprotect.cudasvc.com/url?a=…&c=…`, liens sans expiration | 24 | documenter |
| D7 | Cisco Secure Email (URL filtering / defense) | doc officielle | — | — | réputation Talos, réécriture vers Security Proxy au clic | 22 | documenter |
| D8 | SendGrid — non-human clicks | doc ESP | — | — | même IP sur beaucoup de clics, rafale par destinataire, « pas de filtrage côté SendGrid » | 30 | retenir partiellement |
| D9 | HubSpot — bot filtering | doc ESP | — | — | IP sur listes + rapidité ; métriques plus basses assumées | 26 | retenir (transparence) |
| D10 | Salesforce Account Engagement — Metrics Guard | doc ESP | — | — | page officielle non chargée ; sources secondaires : « surges » | 18 | documenter |
| D11 | Mailgun — Open/Click bot detection | doc ESP | — | — | `client-info.bot` = apple / gmail / generic | 26 | documenter |
| D12 | Adobe Marketo — Filtering email bot activity | doc ESP | 13/05/2026 | — | liste IAB + **proximité 0-3 s** ; le lien caché de 2022 n'est plus documenté | 33 | retenir partiellement |
| D13 | RFC 8058 | norme | 2017 | — | GET ≠ désinscription ; POST `List-Unsubscribe=One-Click` ; pas de redirection | 45 | **retenir** |
| D14 | Gmail 81126 / 14229414 / 14668346 | docs officielles | 2026 | — | spam < 0,1 % / 0,3 % ; **« Don't use HTML and CSS to hide content »** ; Postmaster | 42 | **retenir** |
| D15 | Yahoo Sender best practices / FAQ | docs officielles | — | — | plaintes < 0,3 % ; désinscription sous 2 jours ; CFL | 34 | retenir |
| D16 | Microsoft SNDS / JMRP | doc officielle | — | — | réputation IP, retours de plaintes Outlook.com | 26 | retenir (dashboard) |
| D17 | CNIL — FAQ recommandation pixels (14/04/2026) | doc officielle | 2026 | — | liens traçants : art. 82, consentement sauf strict nécessaire ; sécurité « centrée utilisateur » seulement | 40 | **retenir** |
| D18 | CNIL — mesure d'audience exemptée | doc officielle | 04/07/2025 | — | 13 mois traceurs, 25 mois données, pas de recoupement | 32 | retenir (durées) |
| X1 | **Nos données Mass Email (cas BNP, lecture seule)** | observation | 26/09/2026 | — | voir fiche X1 | 44 | **retenir** (jeu de test) |

---

## Fiches détaillées

### 1. Microsoft Customer Insights — Journeys, « Exclude bot interactions »

```text
Nom de la source : Exclude bot interactions for reliable analytics
URL : https://github.com/MicrosoftDocs/customer-insights/blob/main/ci-docs/journeys/bot-protection.md
Type : documentation (dépôt de docs officiel)
Auteur / organisation : Microsoft (Joni-M / udag)
Licence : CC-BY-4.0 (dépôt)
Date du dernier commit ou de la dernière activité : 02/09/2026 (« Remove outdated notes #2945 »), ms.date 09/02/2026
Étoiles / forks / activité : 21 ★ / 77 forks, commits hebdomadaires
Langage / stack : Markdown
Objectif réel du projet : documenter la protection anti-bot de Dynamics 365 Customer Insights - Journeys
Cas d'usage compatible avec notre besoin : partiel

Fichiers lus :
- ci-docs/journeys/bot-protection.md (intégral, via raw) ; historique des 3 derniers commits

Règles ou mécanismes détectés :
- « Any time a link is selected, it goes through an intermediate page. Customer Insights - Journeys runs checks on the intermediate page to determine if the click was made by a bot or a human. »
- signaux : non publiés ; seuil : non publié ; décision : clic exclu des analytics
- « Bot protection doesn't apply to email opens » ; « It doesn't impact any historical data »

Données collectées : non documentées (page intermédiaire → probablement JS/headers)
Faux positifs possibles : non documentés ; les déclencheurs « email clicked » des parcours peuvent changer
Faux négatifs possibles : scanners qui exécutent la page intermédiaire (non discuté)
Dépendances externes : plateforme Dynamics
Qualité technique : sans objet (doc) ; pas de seuils → non vérifiable
Éléments à reprendre : le principe « tout lien passe par une page first-party où se fait la qualification » ; exclure les bots aussi des déclencheurs (chez nous : notification rappel, export client)
Éléments à adapter : notre page de rappel joue déjà ce rôle, sans JS
Éléments à ne pas reprendre : l'idée de ne pas recalculer l'historique (nous gardons le brut et recalculons)
Niveau de confiance : moyen
Justification : source officielle, mais aucune règle concrète publiée.
```
Note : Pertinence 5, Fiabilité 3, Maintenabilité 4, B2B 2, FP 3, Explicabilité 2, Vie privée 3, Intégration 3, Tests 0, Valeur 5 → **30/50 — retenir partiellement**.

### 2. Mautic issue #16263 — « Bot detection misses cloud link-scanning security gateways »

```text
Nom de la source : Mautic #16263
URL : https://github.com/mautic/mautic/issues/16263
Type : issue
Auteur / organisation : utilisateur en production Mautic 7.1.1 ; commentaires redbullpeter, msoukhomlinov
Licence : dépôt Mautic GPL-3.0 (le correctif proposé serait sous GPL)
Date de la dernière activité : 15/09/2026 (ouverte, marquée « stale » puis relancée)
Étoiles / forks / activité : dépôt 10 561 ★ / 3 465 forks, très actif
Langage / stack : PHP 8 / Symfony / Doctrine
Objectif réel : proposer un 4e signal anti-scanner à Mautic
Cas d'usage compatible : oui

Fichiers lus :
- corps complet de l'issue + 4 commentaires (API GitHub)
- app/bundles/EmailBundle/Helper/BotRatioHelper.php (branche 7.x)

Règles ou mécanismes détectés :
- Constat : un envoi scanné = « ~23 link hits from 10 distinct IPs inside a ~15-second span, all from datacenter ranges, all with normal-looking browser UAs »
- Les 3 signaux historiques échouent : délai < 2 s depuis l'ENVOI (le scan a lieu à la REMISE, « tens of seconds after send ») ; listes d'IP (« rotate… goes stale fast ») ; UA (« Scanners present real browser UA strings »)
- Règle proposée : même email_id + lead_id touchés depuis ≥ burstMaxDistinctIps IP DISTINCTES en burstWindowSeconds → bot ; défaut désactivé, l'auteur tourne à 3 IP / 30 s
- Décision : bot (OU logique avec l'existant)

Données collectées : IP, date du hit, email, contact (colonnes déjà présentes)
Faux positifs possibles : humain multi-appareils (3 IP en 30 s : rare) ; NAT d'entreprise à IP tournantes
Faux négatifs possibles : les 1-2 premiers hits d'une rafale (contrôle avant insertion) ; scanners à 1-2 IP
Dépendances externes : aucune (« list-free »)
Qualité technique : proposition avec test prévu ; pas de PR fusionnée au 26/09/2026
Éléments à reprendre : le signal « nombre de réseaux distincts par destinataire dans une fenêtre courte » ; le diagnostic (délai depuis l'envoi ≠ délai depuis la remise)
Éléments à adapter : compter des /24 (IPv4) et /48 (IPv6) plutôt que des IP (une ferme de scan tourne dans un même /24) ; évaluer a posteriori (nous classons en différé, donc pas de « premiers hits » ratés)
Éléments à ne pas reprendre : la classification en temps réel avant insertion
Niveau de confiance : élevé
Justification : retour terrain chiffré, cohérent avec notre cas BNP (5 réseaux en 2 min).
```
Note : 5,4,4,5,4,5,4,5,2,5 → **43… ramené à 41/50** (pas de code fusionné) — **retenir**.

### 2b. msoukhomlinov/IntellectITBotFilterBundle (plugin Mautic lié à #16263)

```text
Nom de la source : IIT Bot Filter for Mautic
URL : https://github.com/msoukhomlinov/IntellectITBotFilterBundle
Type : repository
Auteur / organisation : msoukhomlinov / IntellectIT
Licence : GPL-3.0
Date du dernier commit : 14/09/2026
Étoiles / forks / activité : 0 ★, jeune mais documenté (README, docs/architecture.md, CHANGELOG)
Langage / stack : PHP 8, Mautic 7, MySQL 8
Objectif réel : détecter les scanners de passerelles (Safe Links, Mimecast, Proofpoint, Barracuda)
Cas d'usage compatible : oui

Fichiers lus :
- README.md (intégral : réglages, détection, honeypot, ASN, données, limites)
- Helper/VelocityBotRatioHelper.php (intégral)
- docs/architecture.md (début) ; arbre complet (Tests/*.php présents : LogicTest, RecorderTest, HoneypotInjectionTest…)

Règles ou mécanismes détectés :
- ordre : cœur Mautic (3 signaux) → rafale clics → rafale ouvertures ; premier qui matche gagne
- rafale : COUNT(DISTINCT ip) ≥ max_distinct_ips (défaut 3) depuis hit − window_seconds (défaut 30)
- preuve enregistrée : distinct_ip_count, trigger_ips (JSON), window_seconds, reason (core-3signal / burst-click / burst-open / honeypot)
- honeypot optionnel : `<a … style="display:none" aria-hidden="true">.</a>` avant </body>, endpoint 204 ; README : « The honeypot changes outgoing email content, so send a seed test and confirm deliverability before enabling it »
- enrichissement ASN (GeoLite2) **pour l'affichage uniquement** : « It has no effect on whether a hit is classified as a bot »
- commande `recount` pour recalculer a posteriori

Données collectées : IP, UA (255 o), URL, domaine du destinataire, IP déclencheuses
Faux positifs possibles (README) : « Multi-device users can be false positives »
Faux négatifs possibles (README) : « Early hits of a burst are not caught » ; « Scanners using few IPs are not caught »
Dépendances externes : MaxMind GeoLite2 (optionnel)
Qualité technique : tests unitaires, erreurs avalées sans casser le tracking, réglages versionnés dans l'intégration, journal d'audit dédié
Éléments à reprendre : table d'audit avec la PREUVE (IP déclencheuses, fenêtre) ; ASN en affichage et non en décision ; recalcul
Éléments à adapter : seuils (3 réseaux / 120 s chez nous, voir matrice)
Éléments à ne pas reprendre : le honeypot `display:none` (contenu caché, cf. Gmail D14) ; le code (GPL-3.0, PHP)
Niveau de confiance : élevé
Justification : limites documentées honnêtement, tests présents, cohérent avec #16263.
```
Note : 5,4,4,5,4,5,3,3,4,4 → **41 − 3 (jeune, 0 ★, GPL) = 38/50 — retenir partiellement**.

### 2c. Mautic `BotRatioHelper.php` (cœur, 7.x)

```text
URL : https://github.com/mautic/mautic/blob/7.x/app/bundles/EmailBundle/Helper/BotRatioHelper.php
Type : code de production — Licence GPL-3.0 — branche 7.x active
Règles : isUnderTimeThreshold (hit − date d'ENVOI < 2 s) + isIpInIgnoreList + isUserAgentInIgnoreList (Matomo DeviceDetector isBot() OU sous-chaîne) ; bot si points/3 ≥ 0,6 (2 sur 3)
Faux négatifs : tous les scanners modernes (voir #16263) ; faux positifs faibles
Éléments à reprendre : l'idée d'un vote combiné (aucun signal seul) ; Matomo DeviceDetector pour les UA explicites
Éléments à ne pas reprendre : le délai calculé depuis l'envoi et à 2 s
Niveau de confiance : élevé (sur son inefficacité, démontrée par #16263)
```
Note : 3,3,4,1,4,3,4,3,2,1 → **22/50 — documenter seulement**.

### 3. alm-000/slack-crm-automation — `email-tracking/`

```text
Nom de la source : slack-crm-automation
URL : https://github.com/alm-000/slack-crm-automation
Type : repository (« reference modules… not turnkey »)
Auteur / organisation : alm-000
Licence : MIT
Date du dernier commit : 14/06/2026
Étoiles / forks / activité : 0 ★ / 0 fork
Langage / stack : TypeScript, Deno edge functions, PostgREST
Objectif réel : modules extraits d'un CRM (Gmail push, tracking, Slack)
Cas d'usage compatible : partiel

Fichiers lus :
- README.md ; email-tracking/bot-detection.ts ; email-tracking/index.ts (intégraux) ; arbre complet (aucun test)

Règles ou mécanismes détectés :
- UA < 10 caractères ou vide → bot
- regex UA : googleimageproxy, yahoo…, /outlook/i, /microsoft office/i, barracuda, proofpoint, mimecast, fireeye, messagelab, /security/i, /scanner/i, /bot\b/i, crawler, spider, curl, wget, python, go-http, java/, /fetch/i
- « Apple MPP » : applewebkit ET < 30 s depuis l'envoi → bot
- préfixes IP par String.startsWith : "13.", "18.", "34.", "35.", "44.", "46.", "47.", "50.", "52.", "54.", "99."… (AWS « broad »), 40.92-94/107, 52.96-101, 104.47 (Microsoft), 159.135. (Barracuda), 67.231. (Proofpoint), 91.220./185.73. (Mimecast)
- < 5 s depuis l'envoi → bot ; ouverture en double même IP < 60 s → bot
- journal : is_bot + bot_reason + ms_since_send ; seuls les humains mettent à jour opened_at/clicked_at

Données collectées : IP en clair, UA, délai, lien
Faux positifs possibles : MAJEURS — /outlook/i exclut les vrais utilisateurs d'Outlook desktop (UA « Microsoft Outlook ») ; « 46. », « 50. », « 47. » couvrent des FAI grand public ; /fetch/i, /security/i trop larges ; un humain sur Safari/iOS qui clique < 30 s = bot
Faux négatifs possibles : scanners à UA Chrome banal hors des préfixes (cas BNP : 185.152.39.x, 192.227.x, 147.185.x)
Dépendances externes : aucune
Qualité technique : aucun test ; destination en base64 NON SIGNÉE (paramètre u) = redirection ouverte ; IP prise dans x-forwarded-for en premier (falsifiable)
Éléments à reprendre : le couple is_bot + bot_reason stocké à chaque événement, et « seuls les humains mettent à jour le clic du destinataire » (déjà fait chez nous)
Éléments à adapter : —
Éléments à ne pas reprendre : listes de préfixes IP, regex UA larges, seuils de délai depuis l'envoi, redirection non signée
Niveau de confiance : faible
Justification : règles non testées, dangereuses en faux positifs, contraires au § 9.6 du cahier (exclusion sur IP cloud seule).
```
Note : 4,1,2,3,0,3,2,4,0,1 → **20 → 17/50** (redirection ouverte) — **écarter**.

### 4. GoPhish issue #1607 — « RFC: Alternative tracking of clicks »

```text
URL : https://github.com/gophish/gophish/issues/1607
Type : issue (outil de simulation de phishing — objectif NON repris)
Activité : 26/09/2019 → 23/02/2025, ouverte ; dépôt : dernier push 23/09/2024
Règles ou mécanismes :
- proposition : JS sur la landing qui appelle un endpoint (preuve d'exécution JS)
- retour terrain (luminous706, 2022) : « this solution depends on the automated bot not supporting JavaScript, and most of them supports it nowadays »
- piste : ASN (AWS, Azure, Cloudflare vs FAI) pour distinguer ; marquage manuel « faux positif » dans l'interface
- Defender scanne pixels ET liens par défaut ; BingBot suit les liens (argie09, 2022)
- Team Cymru IP→ASN proposé (2025)
Faux positifs / négatifs : JS exécuté par les sandbox → faux négatifs ; JS bloqué côté humain → faux positifs
Éléments à reprendre : « JS seul ne prouve rien » ; ASN comme enrichissement ; correction manuelle tracée
Éléments à ne pas reprendre : servir un contenu différent aux IP de sécurité (évasion, hors périmètre § 4) ; pare-feu contre les scanners
Niveau de confiance : moyen
```
Note : 4,2,1,4,3,3,3,2,0,5 → **27/50 — documenter seulement**.

### 5. atc0005/safelinks

```text
URL : https://github.com/atc0005/safelinks — MIT — dernier push 17/09/2026 — 3 ★ — Go
Objectif : outils CLI/GUI pour décoder/encoder des URL Safe Links (pas de détection de bot)
Fichiers lus : README.md ; internal/safelinks/safelinks.go (constantes, ValidSafeLinkURL) ; arbre (testdata/ riche, exported_test.go)
Mécanismes : SafeLinksBaseDomain = "safelinks.protection.outlook.com" ; gabarit
  https://SUBDOMAIN.safelinks.protection.outlook.com/?url=ENCODED_URL&data=…&sdata=…&reserved=0 ;
  validité = hôte contient le domaine + paramètre url présent
Tests : oui (fixtures CRLF/LF, e-mails complets)
Utilité pour nous : FAIBLE — la requête qui arrive chez Sweego ou sur notre page de rappel porte
  NOTRE URL, pas l'URL Safe Links : la signature n'est visible que dans le HTML reçu par le
  destinataire (ou éventuellement un Referer, que Sweego ne transmet pas).
Éléments à reprendre : le motif de domaine pour un futur diagnostic « lien réécrit par la passerelle » (outil de support, pas règle de score)
Niveau de confiance : élevé (sur le format)
```
Note : 2,5,5,3,3,2,5,2,4,1 → **32 → 24/50** (hors sujet détection) — **documenter seulement**.

### 6 / 6b. polarityio/proofpoint-url-decoder → cardi/proofpoint-url-decoder

```text
6 : https://github.com/polarityio/proofpoint-url-decoder → HTTP 404 le 26/09/2026 (dépôt supprimé ou privé ; absent de la liste publique de l'organisation polarityio). Non auditable.
6b (substitut) : https://github.com/cardi/proofpoint-url-decoder — CC0 — dernier push 02/07/2024 — 20 ★ — Python
Fichiers lus : decode.py (commentaires de format v2/v3), arbre (decode_test.py, tests/urls-plain.txt)
Formats : v2 https://urldefense.proofpoint.com/v2/url?u=…&c=&d=&r=&m=&s=&e= (r = identifiant lié à l'adresse) ;
  v3 https://urldefense.com/v3/__<url>__;<base64>!!<org>!<id>$
Risque : le format est non documenté par Proofpoint (rétro-ingénierie) ; dépendre du décodage est fragile.
Utilité : diagnostic seulement (même raison que 5).
```
Note 6b : 2,3,2,3,3,2,5,3,3,1 → **27 → 22/50 — documenter seulement**.

### 7. Gist OVlasiuk — `urldec.py`

```text
URL : https://gist.github.com/OVlasiuk/7afbbe4fc75e27ed408a332a2b3f2494 — créé 11/02/2021, MAJ 13/06/2025 — « GPL v.3 », status beta
Contenu : classe URLDecoder, regex urldefense v1/v2/v3 + safelinks (…safelinks.protection.outlook.com/?url=…&data=…reserved=0), nettoyage « [EXTERNAL] »
Comparaison : même logique v3 que cardi (table A..Z,0..9,-,_ → longueurs 2..65) ; pas de tests ; regex non ancrées
Décision : documenter seulement (non maintenu, pas de détection).
```
Note : 2,2,1,3,3,2,5,3,0,1 → **22 → 19/50**.

### 8. Gist NeutralKaon — « CLI Outlook Safelinks Decoder »

```text
URL : https://gist.github.com/NeutralKaon/23dec87e8d76fb16cae530142d595890 — 23/06/2024, MAJ 09/04/2025 — GPL v3
Contenu : regex Safe Links (\w+\.safelinks\.protection\.outlook\.com) + Proofpoint v1-v3 ; aucun test ; base64 v3 décodé via b64decode après remplacement
Décision : documenter seulement.
```
Note : 2,2,1,3,3,2,5,3,0,1 → **18/50**.

### 9. Ghost issue #30388 — Mailgun `client-info.bot`

```text
URL : https://github.com/TryGhost/Ghost/issues/30388 — ouverte 31/08/2026 ; PR #30625 (09/09/2026)
Constat : Ghost ignore `client-info.bot` (apple / gmail / generic) ; Ghost désactive le suivi des clics Mailgun (o:tracking-clicks: 'no') et suit les clics lui-même → seules les ouvertures sont concernées
Décision produit : filtrer TOUT événement dont client-info.bot est renseigné ; tests unitaires ajoutés
Pertinence pour nous : le drapeau `proxy` de Sweego est l'équivalent ; il faut le traiter comme un signal fort mais pas comme la seule source (0 sur 1 712 clics Cheffer)
Éléments à reprendre : « le verdict de l'ESP est un signal, stocké et visible » ; séparer données ESP et analytics applicatif
Niveau de confiance : moyen
```
Note : 4,3,5,2,3,4,4,4,3,3 → **35 → 31/50 — retenir partiellement**.

### 10. jdavidbakr/mail-tracker #255 (+ README)

```text
URL : https://github.com/jdavidbakr/mail-tracker/issues/255 — 18/01 → 17/03/2025 ; dépôt MIT, 622 ★, push 07/09/2026
Règles : README : exemple d'écouteur ValidActionEvent qui ignore 2 UA EXACTS ('Mozilla/5.0' et un Edge/12.246 figé) ; issue : regex /bot|crawl|spider|fetch|monitor|scanner|slurp|curl|wget|headless/ + UA vide
Retour du mainteneur : « i have never had a spider/crawler bot check a link before, only ever antivirus »
Éléments à reprendre : UA vide = signal (déjà chez nous)
Éléments à ne pas reprendre : correspondances exactes d'UA figées ; /fetch/ /monitor/ trop larges
```
Note : 3,2,4,1,2,3,4,4,1,1 → **25 → 18/50 — écarter (règles), documenter**.

### 11. GitHub topic `email-analytics`

Page lue le 26/09/2026 : 20 dépôts (laravel-mail 11 ★, mail-tracker CF Workers 8 ★, CadenceRelay, sestracking, pixel-tracker-vercel…). Aucun ne contient de logique anti-scanner exploitable pour des clics B2B (pixels d'ouverture, tableaux de bord). **8/50 — écarter.**

### 12. shamanic-technologies/instantly-service issue #773 (trouvée par les recherches § 6.2)

```text
URL : https://github.com/shamanic-technologies/instantly-service/issues/773
Type : issue (post-mortem d'incident) — septembre 2026 — correctif v0.81.5 → v0.81.7
Constat : le redirecteur /c/ comptait chaque GET comme un clic ; 131 « cliqueurs » sur 337 (39 %) contre 95 sur 2 049 pour le groupe témoin ; les séquences étaient arrêtées (« stop-on-click »)
Règles implémentées :
- « Paired opt-out fetches within ±60 seconds of the click (scanners and humans rarely fetch body links seconds apart) »
- méthode HEAD ; UA non navigateur, dont Safe Links « MSIE 8.0 … Trident/4.0 », clients Go, robots d'aperçu
- « Unreduced Chrome version » : un vrai Chrome envoie Chrome/1xx.0.0.0 (UA réduit depuis Chrome 101-110) ; un scanner envoie un numéro complet (ex. 142.0.7444.175)
- vraie IP client (avant : IP du proxy Caddy)
- décision différée : fenêtre d'appariement de 60 s avant de promouvoir un clic
Recalcul : endpoint de backfill : 148 hits → 110 scanners, 38 humains ; 131 → 18 clics réels
Faux positifs : humain qui clique puis se désinscrit dans la minute (rare, et sans conséquence si la désinscription est traitée à part)
Faux négatifs : scanner qui ne suit pas le lien de désinscription ; UA Chrome réduit (notre cas BNP : Chrome/148.0.0.0 réduit → règle « Chrome non réduit » muette)
Éléments à reprendre : la PAIRE désinscription + contenu ; la décision différée ; le recalcul ; la vraie IP
Éléments à adapter : « Chrome non réduit » en signal faible (−15), jamais seul
Niveau de confiance : élevé (chiffres avant/après)
```
Note : 5,4,3,4,4,5,3,4,2,5 → **39 + 1 (backfill mesuré) = 40/50 — retenir**.

### 13. MediumMasala/click-tracker-email

```text
URL : https://github.com/MediumMasala/click-tracker-email — pas de licence (droits réservés) — push 25/06/2026 — 1 ★ — JS, Cloudflare Workers (Hono, D1, KV)
Fichiers lus : README.md, src/classify.js, src/interstitial.js, src/routes/confirm.js, src/routes/redirect.js
Mécanismes :
- UA par familles avec raison précise (whatsapp_prefetch, programmatic_curl, headless_chrome, generic_bot…), motifs ANCRÉS pour ne pas exclure les webviews in-app
- `Purpose: prefetch` / `Sec-Purpose: prefetch` → 204 (pas de 302 mis en cache)
- tout UA propre est enregistré is_bot=1 « pending_js », puis promu is_bot=0 par un beacon JS (fetch keepalive + sendBeacon) ; « Worst-case bias is under-count humans, never over-count »
- unicité par cookie first-party, sinon hash d'IP salé
Pertinence : prévisualisations de messageries (WhatsApp, Slack), pas les passerelles email
Limites : les sandbox de sécurité exécutent le JS (GoPhish #1607) ; cookie 2 ans = traceur (CNIL)
Éléments à reprendre : raisons spécifiques par motif ; motifs ancrés ; hash d'IP salé ; 204 sur prefetch
Éléments à ne pas reprendre : le code (sans licence) ; « JS = humain » comme preuve
```
Note : 3,3,3,1,4,5,3,4,1,2 → **29/50 — retenir partiellement (idées)**.

### 14. fusion-ai-uk/links-fusionagency-solutions

```text
URL : https://github.com/fusion-ai-uk/links-fusionagency-solutions — licence privée/commerciale — TypeScript (Next.js 15, Prisma) — 0 ★
Lu : README (via la page GitHub)
Mécanismes : `client_kind` dérivé de Sec-Fetch-* (navigation / image / other / none ; « none » typique des scanners), enregistré depuis septembre 2026 ; grappes 10 s (5/10/30/60) par campagne+lien : « echo » = IP différente du clic principal (signature scanner), « repeat » = même IP ; choix du clic principal : non-bot > navigation > pays dominant > le plus tardif (« scanners typically fetch first ») ; « Absence of hints is a soft signal » ; IP stockées en HMAC-SHA256
Éléments à reprendre (idées, pas le code) : journaliser Sec-Fetch-* et Accept-Language sur NOTRE page de rappel ; IP en HMAC ; « le scanner arrive en premier »
Niveau de confiance : moyen (non vérifié par le code)
```
Note : 4,3,3,3,4,4,4,2,0,3 → **30/50 — documenter seulement**.

### 15. 00destruct0/kb4-bot-click-prevention

Doc MIT, 07/02/2026, 1 commit. Contexte : simulations de phishing KnowBe4 ; méthode = relire les IP à la main (IPInfo) puis les ajouter à une liste d'exclusion. Contraire à « jamais de liste IP figée » (§ 18) et hors périmètre (simulation de phishing). **10/50 — écarter.**

---

## Documentation officielle (§ 7)

### D1. Microsoft Learn — Safe Links overview (en-us, et fr-fr identique sur le fond)

URL : https://learn.microsoft.com/en-us/defender-office-365/safe-links-about (ms.date 22/05/2026) ; https://learn.microsoft.com/fr-fr/defender-office-365/safe-links-about

Formulations exactes utiles :
- « Safe Links provides URL scanning and rewriting of inbound email messages during mail flow, and time-of-click verification of URLs »
- « Scanned URLs are rewritten or wrapped using the Microsoft standard URL prefix: `https://<DataCenterLocation>.safelinks.protection.outlook.com` »
- « **As long as Safe Links protection is turned on, URLs are scanned prior to message delivery, regardless of whether the URLs are rewritten or not.** If rewriting is enabled, links are scanned on click. If rewriting is disabled, unwrapped URLs are checked by a client-side Safe Links API call at the time of click »
- « URLs that don't have a valid reputation are detonated asynchronously in the background. »
- « Wrapping is done per message recipient »
- « Using another service to wrap links before Defender for Office 365 might prevent Safe Links from processing links » (Sweego réécrit déjà nos liens)

Réponses aux questions du § 7 : réécriture par préfixe régional ; scan AVANT remise (requêtes automatiques, cas BNP) + vérification AU CLIC (le vrai humain passe aussi par Safe Links → **on ne peut pas exclure tout ce qui traverse Safe Links**) ; détonation asynchrone = requêtes supplémentaires sans humain ; mode « Do not rewrite » : pas de domaine safelinks visible du tout. La doc ne publie ni UA ni plages d'IP de scan. **40/50 — retenir.**

### D2. Microsoft Learn — Safe Links policies configure (17/07/2026)

« Wait for URL scanning to complete before delivering the message » (recommandé : On) ; « Do not rewrite URLs, do checks via SafeLinks API only » ; « Track user clicks » (données côté client Microsoft, pas chez nous). Test officiel : `http://spamlink.contoso.com`. **36/50 — retenir.**

### D3. Microsoft Learn — Prompt injection protection in Defender for Office 365 (ms.date 02/09/2026, MAJ 10/09/2026)

- Analyse : « Hidden, invisible, or off-screen text that renders differently than the raw source. »
- Verdict : « Detections are classified under the existing **High confidence phishing** verdict »
- Nuance importante : « The protection uses multiple signals to identify messages that pose a credible threat, including sender reputation, **evasion techniques such as hidden text**, the broader message context, and the intent of the instructions. »
- Portée : exfiltration de données par URL, révélation du prompt système, découverte d'outils.

Conclusion : le texte caché est un **signal d'évasion** pesé avec d'autres (réputation d'expéditeur, instructions) ; un lien piège 1 px sans instruction n'est pas, d'après la doc, mis en quarantaine à lui seul. Notre guide délivrabilité (« Defender met en quarantaine le texte invisible ») est donc un peu plus strict que la doc, mais va dans le même sens, surtout pour un expéditeur à réputation fragile. **30/50 — retenir (nuance).**

### D4. Proofpoint

- https://help.proofpoint.com/Proofpoint_Essentials/Email_Security → page de connexion, aucun contenu public.
- https://www.proofpoint.com/sites/default/files/pfpt-us-ds-essentials-url-defense.pdf → PDF téléchargé mais non extractible ici (pas d'outil PDF sur le serveur).
- https://www.bmcc.cuny.edu/irt/security/proofpoint-target-attack-protection/ → réécriture vers « https://urldefense.com/ », analyse des liens réécrits.
- Complément (recherche) : Proofpoint TAP « predictive analysis… sandboxes suspicious URLs » AVANT le clic, et bac à sable à chaque clic ; domaines urldefense.com, urldefense.proofpoint.com, pphosted.com.

Signaux observables chez nous : requêtes pré-clic depuis l'infrastructure du fournisseur (rafale, réseaux hébergeurs). **22/50 — documenter.**

### D5. Mimecast

- https://www.mimecast.com/content/url-protection/ : « rewrites all links in inbound email and scans the destination website in real-time when clicked by the user » + analyse de domaine avant remise.
- https://mimecastsupport.zendesk.com/…/34000769379219 → **HTTP 403** (non lisible).
- Formats (sources secondaires c7solutions / support Mimecast cités par la recherche) : `protect-xx.mimecast.com/s/…` avant mars 2024, `url.xx.y.mimecastprotect.com/s/…` ensuite.
**22/50 — documenter.**

### D6. Barracuda — Link Protection (EGD)

« https://linkprotect.cudasvc.com/url?a=http://www.codestore.net&c=E,1,… » ; « real-time analysis of URLs and domains » ; « rewritten URLs do not expire and function indefinitely » ; pas de réécriture dans les messages chiffrés ni les pièces jointes. **24/50 — documenter.**

### D7. Cisco Secure Email — URL filtering / URL defense

Réputation Talos −10 à +10 ; URL « rewritten to pass through Cisco's Security Proxy for additional verification when clicked » ; suivi « web interaction tracking » (allowed / blocked / unknown). Pas de domaine publié dans les extraits lus. **22/50 — documenter.**

### D8. SendGrid — Non-Human Clicks

« Aggressive spam filters can open messages and click links in incoming mail before delivering them » ; « Same IP address reported for a high number of click events » ; « A large number of clicks/opens associated with a single recipient, in a short amount of time, or even just before a delivered response is recorded » ; « We are **not** able to filter clicks like this ». → même situation que Sweego : l'ESP fournit ip/UA/horodatage, à nous d'analyser. **30/50 — retenir partiellement.**

### D9. HubSpot — bot filtering

« identifying information (e.g. IP addresses present on referrer blocklists) and behavioral patterns (e.g. how quickly interactions are taking place) » ; exclut « security scanners, privacy filters like Apple's Mail Privacy Protection, and corporate screeners such as Mimecast » ; « Filtering bot activity will usually show lower overall performance metrics than other platforms » ; activé par défaut, désactivable. → modèle de transparence client. **26/50.**

### D10. Salesforce Account Engagement — Email Metrics Guard

Page officielle (help.salesforce.com) : chargement en échec (application JS). Sources secondaires (nebulaconsulting, salesforceben) : filtrage des « surges » de clics, 2 millions de clics de scanners écartés la première semaine, filtres IP fournis. Non vérifiable → **18/50 — documenter.**

### D11. Mailgun — Open and Click Bot Detection

`client-info.bot` : `apple`, `gmail`, `generic` (« Unknown bot (firewall, anti-virus scan, etc.) »), vide sinon. Méthode non publiée. **26/50 — documenter.**

### D12. Adobe Marketo — Filtering email bot activity (MAJ 13/05/2026)

Deux méthodes en production : liste IAB (UA/IP) et « proximity pattern » (plusieurs activités même lead + même email dans 0 s par défaut, 3 s max). Le « hidden link » annoncé en avril 2022 (forum Marketo, fil V2) **n'apparaît plus** dans la doc officielle 2026 (raison non publiée). **33/50 — retenir partiellement** (seuil de proximité très court = peu de faux positifs).

### D13. RFC 8058

« anti-spam software often fetches all resources in mail header fields automatically, without any action by the user, and there is no mechanical way for a sender to tell whether a request was made automatically » ; POST avec corps `List-Unsubscribe=One-Click` ; en-têtes couverts par DKIM (`h=`) ; « MUST NOT return an HTTPS redirect ». → exactement le bug BNP (désinscription sur GET). **45/50 — retenir.**

### D14. Gmail (81126, 14229414, 14668346)

- 81126 (Message formatting) : « **Don't use HTML and CSS to hide content in your messages. Hiding content might cause messages to be marked as spam.** » ; « Web links in the message body should be visible and easy to understand. » ; spam < 0,30 % (recommandé < 0,10 %) ; one-click unsubscribe + lien visible.
- 14229414 : « fulfill unsubscribe requests within 48 hours ».
- 14668346 : Postmaster Tools — taux de spam, tableau « Compliance status », « Delivery Errors » séparant rejets et échecs temporaires ; données à J+1.
**42/50 — retenir** (règle décisive pour le lien piège).

### D15. Yahoo Sender Hub (best practices, FAQ)

Spam < 0,3 % ; list-unsubscribe one-click ; « If the unsubscribe is not honored in 2 days, then it would not meet the requirement » ; SPF + DKIM + DMARC p=none minimum ; CFL (boucle de plaintes) une fois DKIM en place. **34/50.**

### D16. Microsoft SNDS / JMRP

SNDS : « high-level insight on how users are rating the email they receive » (réputation IP) ; JMRP : rapports de courrier marqué indésirable par les utilisateurs Outlook.com. Utile seulement avec IP dédiée (Sweego = IP partagée). **26/50.**

### D17. CNIL — FAQ recommandation pixels (recommandation publiée le 14/04/2026)

- Liens traçants : « ne sont pas directement visés par la recommandation » mais relèvent de l'art. 82 ; consentement sauf opération **strictement nécessaire** (ex. désinscription sécurisée).
- Q18 : « L'anonymisation préalable des données sur le terminal n'est pas une condition suffisante » (pour s'exempter de consentement).
- Q13 : la lutte contre la fraude en général n'exempte pas ; exemption possible quand la sécurité est « centrée sur l'utilisateur » (authentification, réinitialisation de mot de passe).
→ la qualification anti-bot se fait **côté serveur sur des données déjà reçues** (pas de nouvel accès au terminal, pas de fingerprinting) ; le suivi individuel des clics reste à couvrir par la base légale / l'information existantes. **40/50 — retenir.**

### D18. CNIL — solutions pour la mesure d'audience (04/07/2025)

Exemption si finalité limitée, statistiques anonymes, pas de recoupement ; traceurs ≤ 13 mois ; données ≤ 25 mois. → durées de référence pour nos agrégats. **32/50.**

---

### X1. Nos données Mass Email — cas BNP du 26/09/2026 (lecture seule)

```text
Source : tables mass_mailing.clicks et mass_mailing.rappels + settings.click_rules (SELECT en session READ ONLY)
Destinataire : @bnpparibas.com, campagne JAECOO palier 4

Page de rappel (horodatage SERVEUR, exact) :
- 14:42:47 → 14:42:50 (UTC) : 4 « visites » depuis 52.34.76.65 (AS16509 Amazon, US)
- 14:42:52 → 14:42:56 : 4 « visites » depuis 54.70.53.60 (AS16509 Amazon, US)
- UA : Mozilla/5.0 (Windows NT 10.0; Win64; x64) … Chrome/148.0.0.0 Safari/537.36 (UA RÉDUIT, identique à un vrai Chrome)
- envoi (submitted_at) ≈ 14:42:21 → 1re visite **~26 s après l'envoi** (scan à la remise)

Webhook Sweego (horodatage Sweego) :
- 14:52:46 → 14:52:50 : 9 URL (désinscription ×2, piège, miroir, contenu ×4, tel:+33327468236) depuis 52.34.76.65
- 14:53:24 → 14:53:26 : désinscription, désinscription, tel: depuis 172.120.11.0 (AS10557), 192.227.255.180 et 192.227.254.20 (AS36352 ColoCrossing/HostPapa)
- 14:54:02 → 14:54:10 : tel:, désinscription ×2 depuis 185.152.39.42/.28/.39 (AS203020 HostRoyale, IN)
- 14:54:25 : tel: depuis 147.185.226.13 (AS149428 Code200)
- proxy = false partout ; secondes_depuis_envoi = 625 à 724 s

Constats :
1. Les horodatages Sweego sont décalés de **+600 s exactement** par rapport à nos visites serveur (14:42:47 → 14:52:47) :
   le délai « depuis l'envoi » calculé sur Sweego est faux de 10 min → la règle delai_min_s (15 s) ne peut JAMAIS se
   déclencher ; les ÉCARTS entre clics d'un même lot restent justes (rafales valables). À confirmer sur d'autres envois.
2. 5 réseaux (/24) hébergeurs distincts, 4 pays, en 2 min pour UNE personne : signature « ferme de scan » (Mautic #16263).
3. Aucune IP Microsoft/Proofpoint : une liste d'IP de fournisseurs n'aurait rien vu.
4. UA Chrome réduit : la règle « Chrome non réduit » (instantly #773) n'aurait rien vu.
5. Le lien de désinscription est suivi dans la même seconde que les liens de contenu (paire #773).
6. Sweego réécrit aussi le lien tel: → un « clic » tel: en HTTP depuis un Windows de bureau.
7. Contrôle humain (même jour) : visite 10:56:11 puis POST « accepte » 10:56:22, IPv6 Orange (2a01:cb00::/…), Mac Chrome 152 → 1 URL, 1 réseau, POST.
```
Note : 5,5,—,5,5,5,4,5,5,5 → **44/50 — retenir** comme jeu de test de référence (fixtures).
