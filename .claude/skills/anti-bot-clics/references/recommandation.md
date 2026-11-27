RECOMMANDATION : Garder notre architecture actuelle (webhook Sweego + page de rappel first-party à jeton signé) et remplacer le verdict « un signal = robot » par un score explicable et versionné par destinataire, fondé sur trois signaux sans liste (rafale de liens distincts, paire désinscription + contenu, diversité de réseaux en 2 min) et confirmé uniquement par une action POST sur la page de rappel ; retirer le lien piège caché des nouveaux envois.

> Recherche du 26/09/2026 (cahier `cahier-recherche.md`), fiches : `fiches-sources.md`, matrice :
> `matrice-regles.md`. Toutes les URL citées ont été ouvertes le 26/09/2026 ; le code des dépôts a été
> lu (pas seulement le README). Données Mass Email lues en session **lecture seule**.

---

## 1. Synthèse exécutive

1. Aucun éditeur (Microsoft, Proofpoint, Mimecast, Barracuda, Cisco) ne publie d'UA ni de plages d'IP de scan ; Safe Links scanne **avant la remise** et **au clic** ([MS Learn](https://learn.microsoft.com/en-us/defender-office-365/safe-links-about)) : le vrai humain passe par la même passerelle que le scanner.
2. Les scanners modernes ont un UA Chrome banal et tournent sur des IP hébergeurs variées ([Mautic #16263](https://github.com/mautic/mautic/issues/16263)) : c'est exactement le cas BNP (Chrome/148.0.0.0 réduit, 5 réseaux hébergeurs, 4 pays en 2 min).
3. Ce qui marche en production : la **rafale** (Marketo, #16263), la **diversité de réseaux par destinataire** (#16263, IntellectITBotFilterBundle), la **paire désinscription + contenu** ([instantly-service #773](https://github.com/shamanic-technologies/instantly-service/issues/773) : 131 → 18 clics réels).
4. Découverte chez nous : l'horodatage du webhook Sweego est décalé de **+600 s** par rapport à nos visites serveur ; notre règle `delai_min_s` ne peut jamais se déclencher. Les écarts *entre* clics restent justes.
5. La page de rappel est notre vraie « page intermédiaire » (modèle [Microsoft Customer Insights](https://github.com/MicrosoftDocs/customer-insights/blob/main/ci-docs/journeys/bot-protection.md)) : une **visite GET ne prouve rien** (8 visites du scanner BNP), un **POST** oui/non prouve un humain.
6. Le lien piège caché est contraire à la règle officielle Gmail « Don't use HTML and CSS to hide content » ([Gmail](https://support.google.com/mail/answer/81126)) et, rejoué sur le cas BNP, il n'apporte rien que la rafale et la paire n'apportent déjà → **à retirer**.
7. Recommandation : **option 3 allégée** (Sweego + redirecteur first-party + score), 6 statuts, KPI séparés brut / scan / suspect / qualifié / visite confirmée / conversion ; build interne (≈ 1 fichier : `jobs/clics.py`), pas d'API de réputation payante.

## 2. Sources examinées

Tableau complet et fiches § 8 : `fiches-sources.md`. Décisions principales :

| Source | Note /50 | Décision |
|---|---:|---|
| [Mautic #16263](https://github.com/mautic/mautic/issues/16263) — rafale d'IP distinctes | 41 | retenir |
| [instantly-service #773](https://github.com/shamanic-technologies/instantly-service/issues/773) — paire désinscription, HEAD, Chrome non réduit, recalcul | 40 | retenir |
| [IntellectITBotFilterBundle](https://github.com/msoukhomlinov/IntellectITBotFilterBundle) (`Helper/VelocityBotRatioHelper.php`, README « Limitations ») | 38 | retenir partiellement (règle et journal de preuve, pas le code GPL, pas le honeypot) |
| [RFC 8058](https://www.rfc-editor.org/rfc/rfc8058.html) | 45 | retenir |
| [Gmail sender guidelines](https://support.google.com/mail/answer/81126) | 42 | retenir |
| [Safe Links overview](https://learn.microsoft.com/en-us/defender-office-365/safe-links-about) / [policies](https://learn.microsoft.com/en-us/defender-office-365/safe-links-policies-configure) | 40 / 36 | retenir (faits) |
| [CNIL FAQ pixels](https://www.cnil.fr/fr/faq-recommandation-pixels-courriers-electroniques) | 40 | retenir |
| [Marketo bot filtering](https://experienceleague.adobe.com/en/docs/marketo/using/product-docs/administration/email-setup/filtering-email-bot-activity) — proximité 0-3 s | 33 | retenir partiellement |
| [Ghost #30388](https://github.com/TryGhost/Ghost/issues/30388) — verdict ESP (`client-info.bot`) | 31 | retenir partiellement |
| [MS Customer Insights bot-protection.md](https://github.com/MicrosoftDocs/customer-insights/blob/main/ci-docs/journeys/bot-protection.md) | 30 | retenir partiellement (principe) |
| [Defender prompt injection](https://learn.microsoft.com/en-us/defender-office-365/step-by-step-guides/prompt-injection-protection-defender-for-office-365) | 30 | retenir (nuance texte caché) |
| [SendGrid non-human clicks](https://support.sendgrid.com/hc/en-us/articles/4416801410459-Spam-Filters-Non-Human-Clicks-and-Open-Engagement-Recorded), [HubSpot](https://knowledge.hubspot.com/marketing-email/understand-bot-filtering-in-marketing-email-analytics) | 30 / 26 | retenir partiellement |
| [click-tracker-email](https://github.com/MediumMasala/click-tracker-email) (`src/classify.js`, `src/interstitial.js`) | 29 | idées seulement (sans licence) |
| [GoPhish #1607](https://github.com/gophish/gophish/issues/1607) | 27 | documenter (le JS ne prouve rien) |
| [atc0005/safelinks](https://github.com/atc0005/safelinks), [cardi/proofpoint-url-decoder](https://github.com/cardi/proofpoint-url-decoder), gists [OVlasiuk](https://gist.github.com/OVlasiuk/7afbbe4fc75e27ed408a332a2b3f2494) / [NeutralKaon](https://gist.github.com/NeutralKaon/23dec87e8d76fb16cae530142d595890) | 18-24 | documenter (décodage, pas de détection) |
| polarityio/proofpoint-url-decoder | — | **introuvable (404)**, remplacé par cardi |
| [alm-000/slack-crm-automation](https://github.com/alm-000/slack-crm-automation) (`email-tracking/bot-detection.ts`) | 17 | **écarter** (préfixes IP géants, /outlook/i, redirection non signée) |
| [jdavidbakr/mail-tracker #255](https://github.com/jdavidbakr/mail-tracker/issues/255), [topic email-analytics](https://github.com/topics/email-analytics), [kb4-bot-click-prevention](https://github.com/00destruct0/kb4-bot-click-prevention) | 8-18 | écarter |

## 3. Ce qui fonctionne réellement

| Règle | Preuve | Limite |
|---|---|---|
| Rafale : ≥ 3 URL distinctes en ≤ 10 s pour un destinataire | Marketo « proximity » 0-3 s ([doc](https://experienceleague.adobe.com/en/docs/marketo/using/product-docs/administration/email-setup/filtering-email-bot-activity)) ; #16263 : « ~23 link hits… inside a ~15-second span » ; BNP : 9 URL en 4 s | un humain très rapide sur 3 onglets (à 10 s) ; scanner lent |
| Diversité de réseaux : ≥ 3 préfixes /24 (v4) ou /48 (v6) pour un destinataire en ≤ 120 s | #16263 (3 IP / 30 s, « list-free ») ; IntellectIT `VelocityBotRatioHelper.php` ; BNP : 5 réseaux en 2 min | README IntellectIT : « Multi-device users can be false positives » ; « Scanners using few IPs are not caught » |
| Paire désinscription + autre lien à ± 60 s | instantly #773 : « scanners and humans rarely fetch body links seconds apart » ; BNP : désinscription dans la même seconde que les liens | scanner qui ignore le pied de page |
| UA explicite de robot (curl, python-requests, HeadlessChrome, MSIE 8.0/Trident 4.0 de Safe Links…) | Mautic (Matomo DeviceDetector), #773, click-tracker `classify.js` | rarement présent chez les passerelles modernes |
| POST sur la page first-party (formulaire) | principe page intermédiaire (MS) ; RFC 8058 (seul le POST agit) | ne concerne que les campagnes avec page de rappel active |
| Recalcul sur le brut | #773 (backfill 148 hits) ; IntellectIT `recount` ; notre `classer()` déjà idempotent | — |

## 4. Ce qui ne doit pas être utilisé seul

- **IP cloud / ASN / VPN** : les VPN et proxys web d'entreprise (Zscaler, Netskope) sont hébergés ; le cahier § 9.6 l'interdit ; IntellectIT n'utilise l'ASN que pour l'affichage. Nos IP BNP n'étaient d'ailleurs pas chez Microsoft ni Proofpoint.
- **Délai isolé** : le scan arrive à la *remise* (dizaines de secondes après l'envoi, #16263 ; BNP : 26 s) et un humain peut cliquer vite ; **et sur Sweego l'heure est décalée (+600 s observés)**.
- **Signature de passerelle isolée** : non observable chez nous (la requête porte notre URL), et le vrai humain passe aussi par Safe Links « at the time of click » ([MS](https://learn.microsoft.com/en-us/defender-office-365/safe-links-about)).
- **UA isolé** : falsifiable ; le scanner BNP envoyait un Chrome/148.0.0.0 réduit parfait. « Chrome non réduit » (#773) = indice faible.
- **JS isolé** : « most of them supports it nowadays » ([GoPhish #1607](https://github.com/gophish/gophish/issues/1607)).
- **Visite GET de la page de rappel** : 8 visites BNP = scanner.
- **Clic sans ouverture** : les ouvertures sont non fiables (images bloquées, MPP ; Microsoft n'applique même pas sa protection aux ouvertures) → règle à neutraliser.
- **Drapeau `proxy` Sweego** : boîte noire (0 sur 1 712 chez Cheffer, 0 sur 16 BNP) → signal −40, pas une vérité.

## 5. Architecture MVP recommandée (Livrable C + D.1)

Comparatif (cahier § 11) :

| Option | Pour | Contre | Chez nous |
|---|---|---|---|
| 1. ESP seul (webhook → règles) | déjà en place, zéro infra | pas de méthode HTTP, pas d'en-têtes, horodatage décalé, verdict `proxy` opaque | c'est l'état actuel pour les liens directs |
| 2. Redirecteur first-party + règles | heure exacte, méthode, en-têtes, jeton signé | un saut de plus (déjà présent) | page de rappel, désinscription GET, miroir |
| **3. Redirecteur + landing + score** | preuve de visite (POST), meilleure qualité KPI | seulement quand la page de rappel est active | **retenu, allégé** : pas de JS en V1 |

Flux cible (sans code) :

```text
Envoi Sweego (liens réécrits t.news… → notre URL signée)
  ├─ webhook email_clicked ──► webhook_events (brut, inchangé) ──► clicks (brut, inchangé)
  └─ navigateur/scanner ──► mail.cheffer.email : rappel (GET) / désinscription (GET) / miroir
                                 └─ journal first-party (heure serveur, méthode, IP, UA, [en-têtes V1.5])
                                 └─ POST oui/non (seule action) ──► conversion / visite confirmée
jobs/clics.classer(campagne) — toutes les 5 min et à chaque changement de règles :
  grappe par destinataire (± 10 min, deux sources) → règles → score + raisons + version
  → statut par événement (6 statuts) → statut par destinataire (le meilleur événement humain)
  → recipients.clicked_at (premier événement qualifié), export, parcours
```

Briques MVP : score + 6 statuts + raisons versionnées dans `clicks` ; mêmes règles sur `rappels` (visites) ; 3 nouvelles règles sans liste ; neutralisation de `delai_min_s` sur Sweego et de `sans_ouverture` ; retrait du piège à l'envoi ; KPI séparés dans `parcours.calculer` et l'export.
Briques différées : ASN (V2), JS « page visible » (V2), en-têtes Sec-Fetch (V1.5 en observation), HEAD journalisé (V1.5), ratio « tous les liens » (V2).

## 6. Règles V1 proposées (à coder dans `jobs/clics.py`)

Principe de calcul : pour chaque destinataire, on prend **tous** ses événements (clics Sweego + visites
`rappels`) ; on évalue chaque événement dans sa fenêtre ; les poids s'additionnent ; les raisons sont
stockées en clair avec la version des règles.

| # | Règle V1 | Seuil de départ | Poids | Source | Sur |
|---|---|---|---:|---|---|
| V1-1 | UA de robot explicite (liste nettoyée, motifs en mot entier) ou UA vide / < 10 car. | — | −80 / −60 | Mautic, #773, click-tracker | S + R |
| V1-2 | Rafale : URL distinctes (tous types : contenu, désinscription, miroir, tel:, piège) du même destinataire | ≥ 3 en 10 s ; **≥ 5 en 10 s** | −60 ; **−80** | Marketo, #16263, BNP | S + R (R : ≥ 3 requêtes en 10 s) |
| V1-3 | Paire désinscription + autre lien | ± 60 s | −50 | #773 | S + R |
| V1-4 | Réseaux distincts pour un destinataire (/24 IPv4, /48 IPv6) | ≥ 3 en 120 s | −60 | #16263, IntellectIT | S + R |
| V1-5 | Drapeau `proxy` Sweego | vrai | −40 | Sweego, Ghost #30388 | S |
| V1-6 | Première requête très tôt après l'envoi — **heure serveur uniquement** | < 60 s après `submitted_at` | −20 | #16263, BNP (26 s) | R seulement |
| V1-7 | Même IP sur plusieurs destinataires **de domaines différents** | ≥ 10 en 10 min | −30 | SendGrid, cahier R09 | S + R |
| V1-8 | Clic isolé cohérent (≤ 2 URL, 1 réseau, pas de V1-1 à V1-7) | — | +15 | déduit | S + R |
| V1-9 | POST sur la page de rappel (refus = visite confirmée ; oui = conversion) | jeton valide | +60 | MS, RFC 8058 | R |

Signaux conservés à poids faible (jamais seuls) : Chrome non réduit −15 ; `ips_robots` −30 ; lien piège
des **anciens** envois −60 (le hit reste un fait, mais on n'en crée plus).

Classification (cahier, inchangée) : ≤ −60 `security_scan` · −59 à −25 `bot_suspected` · −24 à +14
`unknown` · +15 à +39 `human_likely` · ≥ +40 `human_confirmed`. Compatibilité : `verdict` = `robot` si
`security_scan`/`bot_suspected`, sinon `humain` (l'`unknown` est un clic qualifié non confirmé, pas un
robot) ; `suspect` disparaît.

### Ce qu'il faut changer dans `settings.click_rules`

```json
{
  "version": "2026-09-v1",
  "seuils": {"security_scan": -60, "bot_suspected": -25, "human_likely": 15, "human_confirmed": 40},
  "ua_robot_poids": -80, "user_agent_vide_poids": -60,
  "user_agents_robots": ["curl/", "wget/", "python-requests", "python-urllib", "aiohttp", "go-http-client",
    "java/", "okhttp", "axios/", "node-fetch", "undici", "apache-httpclient", "headlesschrome", "phantomjs",
    "puppeteer", "playwright", "msie 8.0", "trident/4.0", "googleimageproxy", "yahoomailproxy",
    "bot", "crawler", "spider", "scanner", "safelinks", "mimecast", "barracuda", "proofpoint", "urldefense"],
  "ua_mot_entier": true,
  "rafale_liens": 3, "rafale_fenetre_s": 10, "rafale_poids": -60,
  "rafale_forte_liens": 5, "rafale_forte_poids": -80, "rafale_types": "tous",
  "paire_desinscription_s": 60, "paire_desinscription_poids": -50,
  "reseaux_distincts": 3, "reseaux_fenetre_s": 120, "reseaux_prefixe_v4": 24, "reseaux_prefixe_v6": 48, "reseaux_poids": -60,
  "proxy_sweego": true, "proxy_sweego_poids": -40,
  "delai_min_s": 0, "delai_rapide_s": 60, "delai_poids": -20, "delai_source": "serveur",
  "ip_multi_destinataires": 10, "ip_multi_fenetre_s": 600, "ip_multi_poids": -30,
  "chrome_non_reduit_poids": -15,
  "isole_bonus": 15, "post_rappel_bonus": 60,
  "sans_ouverture": "ignorer",
  "ips_robots": [], "ips_robots_poids": -30,
  "piege_actif": false, "piege_signal": true, "piege_fenetre_s": 120, "piege_poids": -60
}
```

Retraits de la liste actuelle : `preview`, `cisco`, `symantec`, `trendmicro`, `fortinet`, `sophos`,
`forcepoint`, `zscaler`, `appengine`, `microsoft office protection`, `phantom` (→ `phantomjs`) : sous-chaînes
larges ou noms d'éditeurs qui peuvent apparaître dans l'UA d'un **navigateur humain** derrière un proxy
d'entreprise (Zscaler, Forcepoint ajoutent parfois leur marque) ; motifs en **mot entier** pour `bot` (éviter
« Cubot », « Abbott »). `piege_actif` passe à `false` (plus d'injection) mais `piege_signal` reste vrai.
`PUT /reglages/clics` doit accepter les nouvelles clés (bornes comme aujourd'hui) et toujours reclasser.

## 7. KPI à remonter au client

| Libellé client | Définition | Visible |
|---|---|---|
| Clics bruts (audit) | toute requête reçue (Sweego + nos pages) | audit / option |
| Contrôles de sécurité détectés | destinataires dont tous les événements sont `security_scan` | oui, agrégé |
| Clics douteux | `bot_suspected` | oui, agrégé |
| **Clics qualifiés** (KPI de référence) | destinataires avec ≥ 1 événement `unknown`, `human_likely` ou `human_confirmed` sur un lien de contenu | oui |
| Visites confirmées | destinataires `human_confirmed` (POST sur la page de rappel) | oui |
| Demandes de rappel (conversion) | POST « oui » valide | oui |
| Désinscriptions | POST (RFC 8058 ou bouton), jamais un GET | oui |

Phrase obligatoire dans l'export et l'écran : « Les clics sont qualifiés à partir de signaux techniques et
de comportement ; les contrôles automatiques des messageries d'entreprise sont exclus des clics qualifiés.
Aucune méthode ne garantit 100 % de clics humains. » (modèle [HubSpot](https://knowledge.hubspot.com/marketing-email/understand-bot-filtering-in-marketing-email-analytics) : « lower overall performance metrics »). Export CSV : colonnes `statut`, `score`, `raisons`, `version_regles` ; l'IP et l'UA ne sortent **pas** vers le client (support interne seulement).

## 8. Délivrabilité / blocage

Mesurable : rejets 5xx et différés 4xx (webhook Sweego, [Postmaster Delivery Errors](https://support.google.com/mail/answer/14668346)), plaintes (Postmaster, [Yahoo CFL](https://senders.yahooinc.com/best-practices/), JMRP), désinscriptions POST, scans (rafales), visites confirmées.
Non mesurable : placement boîte de réception vs indésirables (seulement par seed inboxes), lecture réelle (ouvertures faussées), lien bloqué au clic par la passerelle (aucune requête ne nous arrive).
Alertes à ajouter au dashboard : « clics bruts B2B élevés et 0 visite confirmée » (scan) ; « écart brut/qualifié > 80 % sur un domaine » (passerelle) ; hausse des 4xx (ralentir) ; plaintes Gmail ≥ 0,10 % (alerte) / 0,30 % (crise) ([Gmail](https://support.google.com/mail/answer/81126)).
Désinscription : déployer le correctif GET = page / POST = action ([RFC 8058](https://www.rfc-editor.org/rfc/rfc8058.html) : « there is no mechanical way for a sender to tell whether a request was made automatically ») **avant tout nouvel envoi** — c'est le seul dommage réel du cas BNP.

### Décision sur le lien piège caché : **supprimer des nouveaux envois**

- Règle officielle Gmail : « Don't use HTML and CSS to hide content in your messages. Hiding content might cause messages to be marked as spam. » ([81126](https://support.google.com/mail/answer/81126)). Notre lien : `font-size:1px; color:transparent` = exactement ce cas.
- Defender : le texte caché est un **signal d'évasion** pesé avec la réputation de l'expéditeur ([doc 09/2026](https://learn.microsoft.com/en-us/defender-office-365/step-by-step-guides/prompt-injection-protection-defender-for-office-365)) ; il ne met pas en quarantaine un lien sans instruction à lui seul, mais notre réputation est fragile (domaine partagé, ~0,4 % d'ouvertures Microsoft) : on n'ajoute pas un signal négatif.
- Valeur marginale nulle sur le cas réel : rejoué sans piège, le BNP reste 100 % `security_scan` (matrice, § « Rejeu »). Marketo a annoncé un lien caché en 2022 et ne le documente plus en 2026 ; IntellectIT l'accompagne d'un avertissement délivrabilité.
- Mise en œuvre : `ajouter_piege` n'est plus appelé à l'envoi (`piege_actif: false`) ; **garder** la route `/p` (204) et la règle en lecture (`piege_signal: true`) pour les mails déjà partis ; ne jamais le remplacer par un lien visible « piège » (un humain le cliquerait).

## 9. RGPD et gouvernance

- Base : les liens traçants relèvent de l'art. 82 ; la qualification anti-bot se fait **côté serveur**, sur des données déjà reçues, sans nouvel accès au terminal ni fingerprinting ([CNIL FAQ](https://www.cnil.fr/fr/faq-recommandation-pixels-courriers-electroniques)). Pas de cookie, pas de JS en V1.
- Jetons : déjà signés (HMAC) ; le jeton de rappel contient l'**email en clair encodé base64** quand il s'agit d'un BAT (`rappel.jeton(..., email)`) → réservé aux tests ; vérifié le 26/09 : l'envoi réel (`jobs/envoi.py` l. 307) n'y met pas l'email, seul l'identifiant numérique voyage (à garder ainsi). Attention toutefois : le jeton base64 porte l'URL de destination et l'id de campagne en clair (non personnels).
- Conservation proposée : IP brute (`clicks.ip`, `rappels.ip` des visites) **30 jours**, puis remplacée par un HMAC du préfixe /24 (ou /48) — suffisant pour V1-4 et V1-7 en recalcul ; UA brut 90 jours puis famille (« Chrome 148 Windows ») ; `webhook_events.raw_payload` des clics 90 jours ; agrégats 25 mois ([CNIL mesure d'audience](https://www.cnil.fr/fr/cookies-solutions-pour-les-outils-de-mesure-daudience)) ; preuve de consentement `rappels` action `accepte` : durée affichée sur la page (3 ans), IP comprise (preuve).
- Accès : IP/UA visibles des seuls super-admins ; le client voit statuts, scores et raisons en clair, pas l'IP.
- Registre : ajouter la finalité « qualité de la mesure des clics et exclusion des contrôles automatiques », les données (IP, UA, horodatages, URL cliquée), les durées ci-dessus ; mention dans la politique de confidentialité.
- Corrections manuelles : `statut_force`, `force_par`, `force_motif`, `force_le` sur l'événement, sans ré-identifier (on corrige par identifiant d'événement).

## 10. Plan de validation 30 / 60 / 90 jours

- **J0-J30** : coder V1 en mode **double calcul** (ancien `verdict` + nouveau `statut` côte à côte, sans changer l'export) ; fixtures du cas BNP + du POST humain du 26/09 (tests unitaires de `classer`) ; mesurer le décalage Sweego (visite serveur ↔ clic webhook, même IP + même destination) sur toutes les campagnes avec page de rappel ; seed inboxes : Gmail, Outlook.com, Yahoo, iCloud, un M365 avec Safe Links si disponible (clic humain lent, clic rapide < 30 s, clic sur 3 liens en 20 s, désinscription GET puis POST).
- **J30-J60** : revue manuelle de tous les `bot_suspected` et des `unknown` B2B (faux positifs ?) ; ajuster les seuils (3 URL / 10 s, 3 réseaux / 120 s) ; basculer l'export et le parcours sur `statut` ; activer la journalisation méthode + Sec-Fetch-* + Accept-Language sur nos routes (V1.5).
- **J60-J90** : décider V2 (ASN hors ligne −10, beacon JS « page visible » +15, ratio « tous les liens ») sur la base des cas réels ; alerte dashboard « brut B2B élevé / 0 visite confirmée » ; purge RGPD automatique (30 j IP brute).
- Critères de succès : 0 scan compté comme clic qualifié sur les rafales connues ; 0 humain ayant POSTé classé robot ; écart brut/qualifié expliqué par des raisons lisibles pour 100 % des événements.

## 11. Risques résiduels

- Scanner mono-lien, mono-IP, lent (1 hit) : indiscernable d'un humain → `unknown` (compté qualifié non confirmé). C'est pourquoi le KPI « visites confirmées » existe à part.
- Humain très rapide (3 liens en < 10 s) ou multi-réseaux (Wi-Fi + 4G + VPN) : risque de `bot_suspected` ; mitigé par le POST (+60) et la revue J30.
- Liens directs (page de rappel inactive) : pas de preuve de visite possible, seulement Sweego (heure décalée, pas de méthode).
- Décalage Sweego : une seule campagne observée (+600 s constant) ; s'il varie, toute règle de délai sur Sweego reste interdite.
- Passerelle qui bloque le lien au clic : invisible chez nous (aucune requête) ; seule la baisse de visites par domaine le suggère.
- Les éditeurs changent leurs comportements sans préavis : les règles sont sans liste pour cette raison, et le brut est gardé pour recalculer.

---

## Annexe D — Réponses aux points du livrable D non couverts ci-dessus

- **Signaux à stocker** (par événement) : source (sweego / rappel / desinscription / miroir), heure (serveur si R), destinataire, URL/type de lien, IP (30 j) + préfixe haché, UA (90 j), `proxy`, [V1.5 : méthode, Sec-Fetch-Mode/Site/User/Dest, Accept-Language], score, statut, raisons, version des règles, correction manuelle.
- **Événements exposés** : voir § 7.
- **Différé** : ASN, JS, en-têtes (observation), ratio tous liens, réputation IP externe, ML, fingerprint (couche C écartée : coût, RGPD, pas de gain démontré dans les sources).

## Annexe E — Build vs buy

| Option | Contrôle | Coût | Qualité KPI | Indépendance | Conformité | Verdict |
|---|---|---|---|---|---|---|
| Interne (redirecteur + score) | total | faible (existant) | bonne, explicable | totale | maîtrisée | **retenu** |
| Anti-bot de l'ESP (Sweego `proxy`) | nul (boîte noire) | 0 | faible (0 / 1 712) | dépendant | inconnue | garder comme signal −40 |
| ESP + reporting interne | bon | faible | bonne | bonne | maîtrisée | = notre cible (c'est l'option retenue) |
| API de réputation IP payante | faible | récurrent | marginale (les IP BNP sont des hébergeurs génériques) | dépendant | transfert d'IP à un tiers (RGPD) | **écarter** |

## Ce qu'il faut coder en premier (ordre)

1. **Déployer le correctif désinscription GET = page / POST = action** (déjà prêt) — seul dommage réel.
2. `ajouter_piege` hors du chemin d'envoi (`piege_actif: false`), route `/p` conservée.
3. Dans `classer()` : rafale sur **tous** les types de liens + seuil fort 5 ; paire désinscription ; réseaux distincts /24-/48 ; neutraliser `delai_min_s` (Sweego) et `sans_ouverture` → score + statut + version (colonnes `score`, `statut`, `version_regles` ; `verdict` dérivé).
4. Même classement sur `rappels` (visites) avec l'heure serveur (+ V1-6) et le POST (+60) ; `parcours.calculer` : « visites » = visites non `security_scan`, « visites confirmées » = POST.
5. Tests : fixtures BNP (16 clics + 8 visites) et POST humain du 26/09.
