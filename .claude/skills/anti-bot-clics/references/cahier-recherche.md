# Mission de recherche — Qualification des clics email et filtration anti-bot

> Cahier des charges fourni par Camille le 26/09/2026 (copie fidèle). C'est le prompt à donner à
> l'agent de recherche : voir `../SKILL.md` § « Lancer la recherche ».

## 1. But du document

Ce document est un **prompt/cahier des charges de recherche** destiné à un agent IA de veille, d’architecture et d’analyse de code. Sa mission est de rechercher, lire, auditer et comparer les dépôts GitHub, documentations officielles et retours d’expérience pertinents afin de recommander une solution de qualification des clics email qui équilibre :

- simplicité de mise en œuvre ;
- efficacité réelle en environnement B2B ;
- faible risque de faux positifs ;
- explicabilité des règles ;
- maintenabilité ;
- compatibilité avec des outils de sécurité email ;
- qualité des KPI remontés aux clients ;
- conformité RGPD et minimisation des données.

L’objectif n’est pas de « bloquer » tous les bots. L’objectif est de ne **pas présenter ni valoriser comme un clic humain** une requête générée par un scanner de sécurité, un préchargement, une passerelle d’entreprise, un proxy de confidentialité ou une automatisation.

La sortie attendue est une recommandation claire : une architecture cible, une stratégie de filtrage graduée, un ensemble de règles initiales, les sources à reprendre, les éléments à ne pas reprendre, et un plan de validation sur données réelles.

---

## 2. Contexte métier

Le système cible mesure uniquement les **clics issus d’emails marketing**. Il doit être adapté à la fois :

- aux boîtes grand public : Gmail, Outlook.com, Hotmail, Live, Yahoo, AOL, iCloud, Apple Mail ;
- aux boîtes B2B hébergées chez Microsoft 365, Google Workspace ou sur des domaines d’entreprise ;
- aux environnements B2B protégés par Microsoft Defender Safe Links, Proofpoint URL Defense, Mimecast URL Protect, Barracuda Link Protection, Cisco Secure Email, Zscaler, Netskope ou systèmes comparables.

Les liens d’un email peuvent être :

- réécrits avant arrivée dans la boîte ;
- vérifiés à la remise ;
- vérifiés au clic ;
- ouverts automatiquement par un scanner de sécurité ;
- appelés par un proxy ou une sandbox ;
- appelés plusieurs fois sans action humaine ;
- bloqués avant arrivée sur la landing page.

Ces événements peuvent gonfler artificiellement les KPI : taux de clic, clics uniques, clics par lien, signaux de maturité CRM, relances, scoring et facturation à la performance.

---

## 3. Question de recherche principale

> Quelle solution technique minimale mais robuste permet de distinguer, avec un niveau de confiance explicable, les clics humains plausibles des scans de sécurité et des clics automatisés dans des campagnes email B2B/B2C, sans casser les redirections ni pénaliser les vrais utilisateurs qui transitent par Safe Links, Proofpoint ou une autre gateway ?

### Sous-questions obligatoires

1. Quels repos GitHub, issues et documentations décrivent des patterns de détection de bots dans les clics email ?
2. Quelles règles sont réellement implémentées dans les projets étudiés ?
3. Quelles règles sont seulement évoquées mais non testées ou non fiables ?
4. Quelles signatures permettent d’identifier Safe Links, Proofpoint, Mimecast, Barracuda et les autres gateways ?
5. Dans quels cas une signature gateway correspond-elle aussi à un vrai clic humain ?
6. Quelles règles basées sur IP sont utiles, et lesquelles sont dangereuses à cause des proxies, NAT, VPN ou infrastructures cloud ?
7. Comment détecter une rafale de liens et différencier un scan d’une navigation humaine rapide ?
8. Une landing page intermédiaire ou une preuve de chargement navigateur apporte-t-elle un gain significatif ?
9. Quelles métriques client doivent être affichées pour rester honnête : brut, suspect, qualifié, confirmé, conversion ?
10. Quelles données techniques doivent être collectées, pseudonymisées, limitées ou supprimées au regard du RGPD ?
11. Quel est le compromis recommandé entre simplicité, efficacité, coût d’exploitation et précision ?

---

## 4. Périmètre et non-objectifs

### Dans le périmètre

- Clics HTTP sur des URL de tracking email.
- Redirection contrôlée via un domaine de tracking first-party.
- Détection de scanners de sécurité email et bots.
- Qualification post-clic à partir d’une landing page first-party.
- Signatures URL, user-agent, IP, ASN, headers, méthode HTTP, rafales et séquences de liens.
- Reporting séparant événements bruts, suspects et qualifiés.
- Diagnostics de blocage de lien et de délivrabilité à un niveau opérationnel.

### Hors périmètre

- Création d’un outil de phishing ou de simulation d’attaque.
- Contournement de protections de messagerie.
- Évasion de Safe Links, Proofpoint, Mimecast, Barracuda ou de toute sécurité email.
- Blocage agressif d’outils de sécurité.
- Fingerprinting invasif ou collecte excessive de données de navigation.
- Promesse d’une détection à 100 % parfaite des bots.

Le projet doit être conçu pour la **qualité de la mesure**, non pour contourner les mécanismes de sécurité des destinataires.

---

## 5. Résultat cible : le compromis simplicité / efficacité

La solution recommandée devra viser le modèle suivant.

### Couche A — Indispensable et simple

- Redirecteur de tracking first-party.
- Journalisation d’un événement de clic brut.
- Token signé ou opaque, sans donnée personnelle lisible dans l’URL.
- Déduplication par campagne, destinataire pseudonymisé, lien et fenêtre temporelle.
- Règles simples : user-agent évident, méthodes HEAD/OPTIONS, rafales de liens, IP multi-destinataires, timing anormal.
- Statuts : `raw`, `security_scan`, `bot_suspected`, `unknown`, `human_likely`, `human_confirmed`.
- Reporting client fondé sur les clics qualifiés, sans cacher le volume brut en audit.

### Couche B — Forte valeur avec complexité modérée

- Détection de signatures de gateways de sécurité.
- Enrichissement ASN / type de réseau.
- Rapprochement clic → arrivée landing page → session first-party.
- Score explicable avec raisons versionnées.
- Détection de rafales par destinataire, par IP et par campagne.
- Vue d’audit permettant de comprendre l’exclusion d’un clic.

### Couche C — À ne recommander que si nécessaire

- Modèle de machine learning supervisé.
- Réputation IP externe payante.
- Fingerprint navigateur avancé.
- Heuristiques très fines par fournisseur de messagerie.
- Sandbox, rendu navigateur externe ou infrastructures de détection lourdes.

La recommandation par défaut doit privilégier **A + B**, avec une justification précise de ce qui est écarté en couche C.

---

## 6. Corpus GitHub obligatoire à auditer individuellement

L’agent doit ouvrir chaque lien, lire le README, la licence, la structure du projet, les fichiers directement liés au sujet, les issues pertinentes et l’historique récent quand il est disponible. Il ne doit pas se contenter du titre ou d’un extrait de moteur de recherche.

### 6.1 Repos et sources principaux

| Priorité | Source | URL | Objet attendu de l’analyse |
|---:|---|---|---|
| 1 | Microsoft Customer Insights documentation | https://github.com/MicrosoftDocs/customer-insights/blob/main/ci-docs/journeys/bot-protection.md | Identifier le modèle officiel de bot protection, les conditions de filtrage, le rôle d’une page intermédiaire et les limites annoncées. |
| 1 | Mautic issue #16263 | https://github.com/mautic/mautic/issues/16263 | Étudier les problèmes réels remontés concernant Safe Links, Mimecast, Proofpoint et Barracuda ; relever les propositions, limites, correctifs et retours terrain. |
| 1 | alm-000/slack-crm-automation | https://github.com/alm-000/slack-crm-automation | Auditer le handler de tracking / redirect et toutes les règles de détection de gateway, user-agent, comportement et conversion. Vérifier licence, qualité, maintenabilité, tests et date d’activité. |
| 1 | GoPhish issue #1607 | https://github.com/gophish/gophish/issues/1607 | Analyser l’idée de validation JavaScript / page intermédiaire face aux liens préchargés par les gateways. Adapter les apprentissages au marketing légitime, sans reprendre l’objectif phishing. |
| 1 | atc0005/safelinks | https://github.com/atc0005/safelinks | Identifier les formats Microsoft Safe Links, les routines de normalisation/décodage et les signaux fiables dans les URL. |
| 1 | polarityio/proofpoint-url-decoder | https://github.com/polarityio/proofpoint-url-decoder | Identifier les formats Proofpoint URL Defense/TAP, versions traitées et risques de dépendre du décodage. |
| 2 | Gist Safe Links / Proofpoint | https://gist.github.com/OVlasiuk/7afbbe4fc75e27ed408a332a2b3f2494 | Comparer regex et logique de décodage avec les repos dédiés ; signaler le caractère non maintenu éventuel. |
| 2 | Gist CLI Safe Links / Proofpoint | https://gist.github.com/NeutralKaon/23dec87e8d76fb16cae530142d595890 | Examiner formats couverts, robustesse, tests, limites et éléments récupérables. |
| 2 | Ghost issue #30388 | https://github.com/TryGhost/Ghost/issues/30388 | Étudier la séparation entre données ESP, Mailgun bot detection et analytics applicatif ; relever les décisions produit pertinentes. |
| 2 | mail-tracker issue #255 | https://github.com/jdavidbakr/mail-tracker/issues/255 | Extraire les retours historiques sur antivirus, anti-spam et faux signaux open/click. |
| 2 | GitHub topic email analytics | https://github.com/topics/email-analytics | Explorer les projets pertinents de tracking email ; sélectionner les repos réellement actifs ou techniquement utiles. |

### 6.2 Recherches GitHub à effectuer

L’agent doit exécuter au minimum les recherches suivantes, lire les résultats les plus pertinents et sélectionner les dépôts dont le code apporte des règles réutilisables :

```text
"Safe Links" "bot detection"
Proofpoint "bot click" tracking
"email security scanner" click filtering
"email click redirect" bot detection
"link scanner" email analytics
"email tracking" "Proofpoint"
"email tracking" "Mimecast"
"email tracking" "Barracuda"
"click bot detection" email
"security scanner" "click tracking"
Mailgun "click bot" detection
SendGrid "non-human clicks"
HubSpot "bot filtering" email
Mautic SafeLinks Proofpoint
```

L’agent doit distinguer :

- dépôts actifs / inactifs ;
- code de production / snippet expérimental ;
- projet de marketing légitime / outil de sécurité / outil de phishing ;
- documentation officielle / opinion communautaire ;
- règles testées / règles hypothétiques.

---

## 7. Documentation officielle obligatoire à auditer

Les sources officielles sont prioritaires sur les blogs et snippets. L’agent doit lire les pages et relever les formulations exactes utiles.

### Microsoft Defender Safe Links

- https://learn.microsoft.com/en-us/defender-office-365/safe-links-about
- https://learn.microsoft.com/en-us/defender-office-365/safe-links-policies-configure
- https://learn.microsoft.com/fr-fr/defender-office-365/safe-links-about

Questions à traiter :

- Comment Safe Links réécrit-il les URL ?
- Quels sont les domaines/patterns identifiables ?
- Que signifie la protection au moment du clic ?
- Quels événements peuvent être causés par une analyse plutôt que par un humain ?
- Pourquoi faut-il éviter d’exclure automatiquement tous les clics traversant Safe Links ?

### Proofpoint

- https://help.proofpoint.com/Proofpoint_Essentials/Email_Security
- https://www.proofpoint.com/sites/default/files/pfpt-us-ds-essentials-url-defense.pdf
- https://www.bmcc.cuny.edu/irt/security/proofpoint-target-attack-protection/

Questions à traiter :

- Quels domaines et formats de réécriture sont observables ?
- Quelle différence entre vérification à la remise et au clic ?
- Quels signaux peuvent indiquer une analyse automatique ?

### Mimecast, Barracuda et Cisco

- https://www.mimecast.com/content/url-protection/
- https://mimecastsupport.zendesk.com/hc/en-us/articles/34000769379219-Targeted-Threat-Protection-URL-Protect-Embedded-Links
- https://documentation.campus.barracuda.com/wiki/spaces/EGD/pages/2850935
- https://docs.ces.cisco.com/docs/url-filtering
- https://docs.ces.cisco.com/docs/url-defense

Questions à traiter :

- Quelles protections réécrivent les URL ?
- Lesquelles analysent au clic ?
- Quelles sont les signatures de domaine ou de comportement identifiables de manière légitime ?
- Quelles différences observables dans les logs HTTP ?

### ESP et plateformes marketing

- https://support.sendgrid.com/hc/en-us/articles/4416801410459-Spam-Filters-Non-Human-Clicks-and-Open-Engagement-Recorded
- https://knowledge.hubspot.com/marketing-email/understand-bot-filtering-in-marketing-email-analytics
- https://help.salesforce.com/s/articleView?id=mktg.pardot_email_metrics_guard.htm
- https://github.com/MicrosoftDocs/customer-insights/blob/main/ci-docs/journeys/bot-protection.md

Questions à traiter :

- Quels types de bot events sont explicitement reconnus ?
- Les plateformes filtrent-elles IP, user-agent, timing, lien, comportement ou une combinaison ?
- Comment les métriques changent-elles une fois la protection activée ?
- Quelle transparence proposent-elles aux utilisateurs ?

### Délivrabilité / placement spam

- https://support.google.com/mail/answer/81126
- https://support.google.com/mail/answer/14229414
- https://support.google.com/mail/answer/14668346
- https://senders.yahooinc.com/best-practices/
- https://senders.yahooinc.com/faqs/
- https://substrate.office.com/ip-domain-management-snds/Postmaster/Services

Questions à traiter :

- Quelles données permettent de distinguer rejet SMTP, différé, spam placement et faible engagement ?
- Quels tableaux de bord permettent d’observer réputation et plaintes ?
- Quelles alertes doivent apparaître dans un dashboard de délivrabilité ?

### Désinscription et sécurité des liens

- https://www.rfc-editor.org/rfc/rfc8058.html

Questions à traiter :

- Pourquoi un GET sur un lien de désinscription ne doit pas déclencher une désinscription irréversible ?
- Comment gérer `List-Unsubscribe` et `List-Unsubscribe-Post` sans créer de désinscriptions accidentelles par scanner ?

### CNIL / RGPD

- https://www.cnil.fr/fr/faq-recommandation-pixels-courriers-electroniques
- https://www.cnil.fr/fr/cookies-solutions-pour-les-outils-de-mesure-daudience
- https://www.cnil.fr/fr/cookies-et-autres-traceurs/regles/cookies/FAQ

Questions à traiter :

- Dans quelles conditions un clic email est-il rattachable à une personne ?
- Quelles données sont strictement nécessaires à la lutte contre les bots et à la mesure de performance ?
- Quelles données doivent être pseudonymisées, chiffrées ou supprimées rapidement ?
- Quels éléments inscrire dans le registre de traitement et la politique de confidentialité ?

---

## 8. Méthode d’audit de chaque dépôt GitHub

Pour **chaque** dépôt, issue ou gist, l’agent doit produire une fiche au format ci-dessous. Il est interdit de conclure à partir du README uniquement lorsqu’un code source est disponible.

### Fiche standard

```text
Nom de la source :
URL :
Type : repository / issue / gist / documentation
Auteur / organisation :
Licence :
Date du dernier commit ou de la dernière activité :
Étoiles / forks / activité :
Langage / stack :
Objectif réel du projet :
Cas d’usage compatible avec notre besoin : oui / partiel / non

Fichiers lus :
- [liste précise des chemins et liens]

Règles ou mécanismes détectés :
- [règle]
- [signal analysé]
- [seuil]
- [décision produite]

Données collectées :
- IP ? user-agent ? headers ? cookies ? JS ? timings ?

Faux positifs possibles :
- [cas]

Faux négatifs possibles :
- [cas]

Dépendances externes :
- API IP reputation / ASN / cloud / navigateur / base tierce

Qualité technique :
- tests présents ?
- observabilité ?
- erreurs gérées ?
- configuration versionnée ?
- sécurité des tokens ?

Éléments à reprendre :
- [liste]

Éléments à adapter :
- [liste]

Éléments à ne pas reprendre :
- [liste]

Niveau de confiance : faible / moyen / élevé
Justification :
```

### Grille d’évaluation chiffrée

Attribuer une note de 0 à 5 sur chaque critère :

| Critère | Ce qui est attendu |
|---|---|
| Pertinence | Répond directement au filtrage de clics email bots |
| Fiabilité | Règles documentées, comportement vérifiable, peu d’hypothèses fragiles |
| Maintenabilité | Code lisible, actif, config séparée, versionné |
| Couverture B2B | Prend en compte Safe Links / Proofpoint / Mimecast / Barracuda ou patterns comparables |
| Gestion des faux positifs | Ne bloque pas aveuglément les vrais clics humains |
| Explicabilité | Raisons et règles compréhensibles pour support/client |
| Respect vie privée | Minimisation, absence de fingerprinting excessif, gestion IP raisonnable |
| Facilité d’intégration | Peut être repris sans dépendance lourde |
| Tests | Tests unitaires, scénarios reproductibles, fixtures |
| Valeur pratique | Apporte une règle, un mécanisme ou une décision réellement actionnable |

Calculer :

```text
Score global / 50
Décision : retenir / retenir partiellement / documenter seulement / écarter
```

---

## 9. Règles techniques à rechercher, comparer et évaluer

L’agent ne doit pas présumer que ces règles sont toutes bonnes. Il doit dire, pour chacune, si elle est :

- fiable seule ;
- utile seulement combinée à d’autres signaux ;
- faible ou dangereuse ;
- à exclure.

### 9.1 Signature de sécurité / URL réécrite

Signaux possibles :

```text
*.safelinks.protection.outlook.com
urldefense.com
*.urldefense.com
*.proofpoint.com
linkprotect.cudasvc.com
Mimecast URL Protect et domaines observés dans les tests
Cisco URL Defense / proxy observés dans les tests
```

Question critique : une signature gateway peut-elle correspondre à un vrai clic humain ?

Réponse à attendre : oui. La signature gateway doit généralement réduire la confiance ou déclencher une observation renforcée ; elle ne doit pas suffire à exclure définitivement un clic si une vraie session utilisateur suit.

### 9.2 Méthode HTTP

À évaluer :

```text
GET
HEAD
OPTIONS
TRACE
POST
```

Hypothèse : `HEAD`, `OPTIONS` et `TRACE` sont des signaux forts de contrôle automatique sur un lien de clic email. `GET` reste ambigu et peut être bot ou humain.

### 9.3 User-agent et headers

Identifier les signatures explicites :

```text
curl
wget
python-requests
Go-http-client
Java
okhttp
axios
headless
Playwright
Puppeteer
```

Mais analyser aussi :

- user-agent absent ou incohérent ;
- incohérence entre user-agent et headers `Accept`, `Accept-Language`, `Sec-CH-UA`, `Sec-Fetch-*` ;
- navigateur prétendu moderne sans cookies ni chargement de ressources ;
- user-agent identique sur beaucoup de destinataires et de liens.

L’agent doit signaler que l’user-agent est falsifiable et ne suffit pas seul.

### 9.4 Timing entre livraison et clic

Évaluer différents seuils :

```text
moins de 2 secondes
moins de 10 secondes
moins de 30 secondes
moins de 2 minutes
```

L’agent doit recommander une pondération, pas une exclusion automatique, car un destinataire peut réellement cliquer très vite.

### 9.5 Rafales de liens

Évaluer notamment :

```text
3 liens distincts en moins de 3 secondes
4 liens distincts en moins de 5 secondes
5 liens distincts en moins de 10 secondes
Tous les liens demandés dans un délai court
Ordre identique de liens sur plusieurs destinataires
```

L’agent doit proposer des seuils initiaux justifiés et un moyen de les calibrer sur les données réelles.

### 9.6 Comportement IP / réseau

Évaluer :

- même IP sur un grand nombre de destinataires ;
- même IP sur beaucoup de liens ;
- ASN cloud ou datacenter ;
- ASN d’entreprise ;
- proxy, VPN, TOR ;
- IP Microsoft, Google, Proofpoint ou autre fournisseur de sécurité.

Règle obligatoire : **ne jamais exclure un clic uniquement parce que son IP vient d’un cloud, d’un proxy, d’un VPN ou d’un ASN connu.** Ces éléments doivent servir à enrichir un score.

### 9.7 Validation post-redirection

Comparer :

- simple redirect 302 ;
- landing page intermédiaire ;
- événement JS `page_loaded` ;
- session first-party ;
- chargement de ressources ;
- page visible après délai minimal ;
- navigation vers une seconde page ;
- interaction utilisateur ;
- soumission de formulaire ;
- conversion server-side.

L’agent doit évaluer :

- valeur anti-bot réelle ;
- impact UX ;
- impact performance ;
- compatibilité avec scanners qui exécutent JavaScript ;
- risques RGPD ;
- valeur comme preuve de visite réelle.

### 9.8 Honeypots

Le projet peut examiner les honeypots, mais doit conclure avec prudence :

- ne jamais les utiliser comme preuve unique ;
- ne jamais les rendre susceptibles de pénaliser un utilisateur réel ;
- ne jamais dégrader l’accessibilité ;
- ne jamais déclencher une action utilisateur ou commerciale.

---

## 10. Règles initiales à tester dans le prototype

Ces règles sont des hypothèses initiales. L’agent doit les confirmer, ajuster ou rejeter avec références et arguments.

| ID | Règle | Signal | Effet initial |
|---|---|---|---:|
| R01 | UA automatisé explicite | `curl`, `wget`, `python-requests`, etc. | −80 |
| R02 | Méthode non-navigation | `HEAD`, `OPTIONS`, `TRACE` | −50 |
| R03 | Signature de gateway | Safe Links, Proofpoint, Mimecast, Barracuda, Cisco | −20 à −30 |
| R04 | Clic quasi immédiat | moins de 10 s après livraison | −15 |
| R05 | Rafale de 3 liens | 3 liens distincts en moins de 3 s | −25 |
| R06 | Rafale de 4 liens | 4 liens distincts en moins de 5 s | −40 |
| R07 | Rafale de 5 liens | 5 liens distincts en moins de 10 s | −60 |
| R08 | Tous liens testés | presque tous les liens de l’email dans une même fenêtre | −40 |
| R09 | IP multi-destinataires | même IP sur 20 destinataires en moins de 10 min | −50 |
| R10 | Réseau datacenter/proxy | ASN cloud, proxy ou VPN | −10 |
| R11 | Pas de landing observée | aucun événement post-click sous 10 min | −25 |
| R12 | Session first-party | arrivée landing confirmée | +20 |
| R13 | Page active | session > 10 s ou visibilité page | +15 |
| R14 | Navigation réelle | deuxième page ou action interne | +15 à +20 |
| R15 | Formulaire valide | validation serveur | +35 |
| R16 | Conversion métier | rendez-vous, achat, DOI, lead validé | +60 |

Classification de départ à tester :

```text
score <= -60          security_scan
score -59 à -25       bot_suspected
score -24 à +14       unknown
score +15 à +39       human_likely
score >= +40          human_confirmed
```

Règle métier essentielle :

```text
Un clic passant par Safe Links ou Proofpoint ne doit pas être exclu définitivement
s’il est suivi d’une session first-party et d’un comportement cohérent.
```

---

## 11. Architecture fonctionnelle à comparer

L’agent doit comparer au moins ces trois architectures et recommander une seule architecture cible.

### Option 1 — Filtre à l’ESP uniquement

```text
ESP → événement click webhook → règles a posteriori → reporting
```

À évaluer : simplicité élevée, mais contrôle limité selon l’ESP et données HTTP souvent insuffisantes.

### Option 2 — Redirecteur first-party + règles serveur

```text
Email → clk.domaine.fr/c/token → log brut + score initial → 302 → landing
```

À évaluer : bon compromis de contrôle, simplicité raisonnable et excellente auditabilité.

### Option 3 — Redirecteur + landing validation + score enrichi

```text
Email → redirecteur → log brut → 302 → landing first-party
      → session → événements post-clic → score final → reporting
```

À évaluer : meilleure qualité KPI, plus de travail mais probablement architecture recommandée.

### Recommandation attendue

La recommandation doit préciser :

- l’option retenue ;
- les briques minimales du MVP ;
- les briques différées ;
- les raisons techniques et business ;
- les risques résiduels ;
- les critères de succès.

---

## 12. Modèle de KPI et règles de restitution client

Le projet doit recommander des définitions explicites, stables et non trompeuses.

| KPI | Définition proposée | Visible client | Usage |
|---|---|---|---|
| Clic brut | Toute requête reçue sur un lien de tracking | Audit seulement ou optionnel | Diagnostic technique |
| Clic unique brut | Au moins une requête par destinataire/lien/campagne | Optionnel | Contrôle volume |
| Scan sécurité | Clic associé à règles de scanner à confiance élevée | Oui, agrégé | Transparence |
| Clic suspect | Clic automatisé probable ou insuffisamment confirmé | Oui, agrégé | Audit qualité |
| Clic qualifié | Clic non exclu, score suffisant | Oui | KPI marketing de référence |
| Visite confirmée | Clic associé à une session first-party réelle | Oui | KPI de qualité |
| Conversion validée | Événement métier validé serveur | Oui | KPI business / performance |
| Blocage avant site | Tentative observée mais landing non atteinte / erreur connue | Oui, agrégé | Diagnostic domaine / sécurité |

Le rapport client ne doit pas promettre « 100 % humain ». Il doit expliquer que la qualification repose sur des signaux techniques et comportementaux, et que les clics de sécurité identifiés sont exclus des métriques qualifiées.

---

## 13. Délivrabilité et blocage : cadre d’analyse

L’agent doit distinguer les statuts suivants :

| Situation | Preuve attendue | Interprétation |
|---|---|---|
| Rejet SMTP | Code 5xx / DSN / webhook ESP | Email non remis |
| Différé / soft bounce | Code 4xx ou nouvelles tentatives | Livraison retardée ou temporairement refusée |
| Livré | Acceptation SMTP / webhook ESP | Ne prouve pas inbox ni lecture |
| Probable spam placement | Accepté mais seed/test inbox spam, réputation/complaint dégradée | Inbox placement défavorable |
| Clic scanner | Event URL sans session réelle ou rafale | Analyse sécurité, pas engagement |
| Lien bloqué au clic | Gateway / navigateur affiche blocage, pas de landing | Problème URL, réputation, contenu ou politique entreprise |
| Visite humaine | Landing + session + comportement | Engagement plausible |

### Données à recommander pour le dashboard de délivrabilité

```text
date
campaign_id
sending_domain
tracking_domain
recipient_domain
mailbox_provider
ip_pool
sent
accepted_smtp
hard_bounce
soft_bounce
deferred
complaints
unsubscribes
raw_clicks
security_scans
suspected_bots
qualified_clicks
confirmed_visits
validated_conversions
spf_pass
dkim_pass
dmarc_pass
smtp_code_family
```

### Alertes à recommander

- Hausse de soft bounces/différés : throttling, réputation ou volume.
- Hausse de hard bounces : qualité de liste/adresses.
- Hausse de plaintes : ciblage, consentement, fréquence ou contenu.
- Clics bruts B2B élevés avec visites nulles : scanners.
- Baisse concentrée sur un domaine corporate : gateway ou politique interne.
- Différence anormale entre clics bruts et clics qualifiés : intensité de scanning.
- Taux de plaintes Gmail/Yahoo préoccupant : risque de spam placement.

---

## 14. RGPD, sécurité et minimisation

L’agent doit proposer une politique de données proportionnée.

### Principes obligatoires

- Ne jamais placer email, téléphone, nom, prénom ou identifiant client lisible dans une URL.
- Préférer un token opaque ou signé avec références pseudonymes.
- Séparer les données d’identité des logs techniques de clic.
- Chiffrer l’IP si elle doit être conservée en clair pour une période très limitée.
- Conserver un hash/prefix hash lorsque cela suffit pour les analyses de rafales.
- Limiter l’accès aux logs bruts.
- Versionner règles, score, motifs d’exclusion et décisions manuelles.
- Définir une durée de conservation courte pour les logs détaillés et une durée distincte pour les agrégats.
- Documenter finalités : mesure de performance, prévention de fraude/bots, sécurité, qualité du reporting.
- Éviter le fingerprinting intrusif lorsqu’une session first-party et des signaux simples suffisent.

### Questions à résoudre

1. Quelle conservation recommander pour l’IP brute, hash IP, user-agent brut, headers normalisés, session et agrégats ?
2. Quelles données sont nécessaires au support client et lesquelles peuvent être supprimées ?
3. Quel niveau de détail doit être visible au client ?
4. Comment tracer une correction manuelle sans réidentifier inutilement une personne ?

---

## 15. Jeu de tests obligatoire

L’agent doit concevoir un protocole de test, sans tenter de contourner une protection.

### Scénarios email

| Scénario | Résultat attendu |
|---|---|
| Utilisateur Gmail réel clique un CTA | Clic qualifié ou confirmé après landing |
| Utilisateur Outlook/M365 réel clique via Safe Links puis navigue | Ne pas exclure ; classer humain si session confirmée |
| Scanner Safe Links demande plusieurs liens immédiatement | `security_scan` |
| Scanner Proofpoint demande tous les liens | `security_scan` |
| User-agent curl sur redirecteur | `security_scan` |
| HEAD sur redirecteur | `security_scan` ou `bot_suspected` |
| IP datacenter avec session réelle et formulaire | Ne pas bloquer ; humain possible |
| Même IP corporate pour plusieurs salariés mais navigation réelle | Ne pas classer scanner uniquement sur IP |
| Clic très rapide d’un humain sur un mail attendu | Rester au moins `unknown` jusqu’à confirmation, pas exclusion définitive |
| Scanner qui exécute JavaScript | Détecter la limite du signal JS ; exiger combinaison de signaux |
| Lien de désinscription scanné en GET | Pas de désinscription automatique |
| Désinscription RFC 8058 via POST | Désinscription effective et journalisée |

### Seed inboxes recommandées

- Gmail personnel.
- Outlook.com/Hotmail.
- Yahoo/AOL si disponible.
- iCloud/Apple Mail si disponible.
- Microsoft 365 professionnel avec Safe Links si possible.
- Domaine B2B protégé par Proofpoint, Mimecast, Barracuda ou Cisco si accès légal et autorisé.

Le projet doit expliciter la différence entre tests reproductibles, tests disponibles et tests nécessitant un environnement client.

---

## 16. Livrables attendus de l’agent de recherche

### Livrable A — Inventaire source par source

Un tableau complet de tous les repos, issues, gists et docs consultés avec :

- URL ;
- date/activité ;
- licence si code ;
- règles trouvées ;
- éléments utiles ;
- limites ;
- décision : retenir / adapter / écarter.

### Livrable B — Matrice de règles

Une matrice de toutes les règles observées :

| Règle | Sources qui l’utilisent | Signal | Faux positifs | Faux négatifs | Coût | Décision |
|---|---|---|---|---|---|---|

### Livrable C — Comparatif d’architectures

Comparer les trois options décrites dans ce document : ESP seul, redirecteur, redirecteur + validation landing.

### Livrable D — Recommandation finale MVP

La recommandation doit contenir :

1. Architecture recommandée.
2. Règles à déployer dès V1.
3. Seuils initiaux.
4. Signaux à stocker.
5. Événements à exposer dans le reporting.
6. Ce qui doit être volontairement différé.
7. Risques résiduels.
8. Plan de calibration sur 30/60/90 jours.
9. Plan de test seed inboxes.
10. Politique RGPD de minimisation des logs.

### Livrable E — Décision build vs buy

Comparer :

- développement interne du redirecteur et scoring ;
- fonctionnalités anti-bot d’un ESP ;
- combinaison ESP + outil interne de reporting ;
- dépendance à une API de réputation IP.

La conclusion doit privilégier le meilleur rapport entre : contrôle, coût, qualité des KPI, indépendance et conformité.

---

## 17. Format obligatoire de la recommandation finale

La réponse finale de l’agent doit commencer exactement par :

```text
RECOMMANDATION : [une phrase claire]
```

Puis contenir ces sections :

1. **Synthèse exécutive** — maximum 15 lignes.
2. **Sources examinées** — tableau avec décision par source.
3. **Ce qui fonctionne réellement** — règles confirmées et leurs limites.
4. **Ce qui ne doit pas être utilisé seul** — IP cloud, timing isolé, signature gateway isolée, UA isolé, JS isolé.
5. **Architecture MVP recommandée** — flux logique sans code.
6. **Règles V1 proposées** — score, seuils, classification.
7. **KPI à remonter au client** — définitions et libellés recommandés.
8. **Délivrabilité / blocage** — ce qui est mesurable, ce qui ne l’est pas.
9. **RGPD et gouvernance** — minimisation, conservation, accès, transparence.
10. **Plan de validation 30/60/90 jours** — tests, calibration, revue des faux positifs.
11. **Risques résiduels** — ce que le système ne peut pas prouver.

Chaque affirmation technique importante doit être associée à une URL source. Les sources officielles doivent primer sur les blogs. Les dépôts doivent être cités avec leurs fichiers ou issues précis lorsque possible.

---

## 18. Critères de décision finale

La solution recommandée sera acceptée si elle respecte toutes les conditions suivantes :

- Elle ne compte pas automatiquement une requête de redirecteur comme un clic humain.
- Elle ne bloque pas de manière aveugle les vrais clics via Safe Links ou Proofpoint.
- Elle maintient le log brut pour audit et recalcul futur.
- Elle permet un score explicable avec motifs de classification.
- Elle sépare clic brut, scan, clic qualifié, visite confirmée et conversion validée.
- Elle fonctionne sans dépendre d’une liste IP figée.
- Elle réduit les faux clics B2B avec un niveau de complexité raisonnable.
- Elle permet de diagnostiquer les différences entre scan, blocage de lien, bounce, spam placement et absence d’engagement.
- Elle respecte la minimisation, la pseudonymisation et une conservation maîtrisée.
- Elle produit un reporting client honnête, stable et commercialement défendable.

---

## 19. Conclusion attendue par défaut

Sauf découverte de preuves contraires dans l’analyse, la solution la plus susceptible d’offrir le meilleur compromis est :

```text
Un redirecteur de tracking first-party
+ journalisation brute et pseudonymisée
+ règles explicables de signature / méthode / rafale / IP / timing
+ enrichissement réseau limité
+ redirection 302 vers une landing page first-party
+ confirmation par session et comportement post-clic
+ score versionné et révisable
+ reporting séparant brut, suspect, qualifié et confirmé.
```

Cette approche ne promet pas une vérité absolue sur chaque clic. Elle transforme cependant le clic brut — facilement pollué par les scans de sécurité — en métriques graduées, auditées et plus fiables pour les clients.
