---
name: email-domain-setup
description: Configure et audite un domaine ou sous-domaine d'envoi d'emails pour n'importe quel fournisseur (Resend, Amazon SES, Brevo, Postmark, Mailgun, SendGrid, Scaleway, Mailjet, Cloudflare Email, Google Workspace, Microsoft 365) — SPF, DKIM, DMARC, MAIL FROM / Return-Path, domaine de tracking, BIMI, MTA-STS, TLS-RPT, APRF, one-click unsubscribe (RFC 8058) et exigences Gmail/Yahoo/Microsoft. Génère le plan DNS exact, l'applique sur Cloudflare, vérifie la propagation, explique chaque alerte et score le contenu avant envoi. Sert aussi à concevoir un module « domaines d'envoi » multi-fournisseurs façon Lumail/Brevo dans un SaaS. À utiliser dès qu'il est question de configurer un domaine pour envoyer des emails, d'emails qui arrivent en spam, de DNS email, de vérification de domaine chez un ESP, de DMARC p=none/quarantine/reject, de bounces ou plaintes, de délivrabilité, ou de router des emails transactionnels/marketing d'une plateforme — même si l'utilisateur ne cite ni SPF ni DKIM.
---

# Configuration de domaines d'envoi (SPF · DKIM · DMARC · et au-delà)

Ce skill reproduit, en plus simple, ce que font Lumail, Brevo et Resend quand un client
connecte son domaine : **créer l'identité chez le fournisseur → publier les bons enregistrements
→ vérifier → surveiller → expliquer chaque alerte**. Il couvre aussi la conception de cette
fonctionnalité dans une plateforme.

Les scripts sont en Node ≥ 18, **sans dépendance** : `node scripts/<script>.mjs --help`.

## Trois idées à garder en tête

Elles expliquent 90 % des erreurs de configuration :

1. **SPF est évalué sur le domaine d'enveloppe (MAIL FROM / Return-Path), pas sur le From.**
   C'est pour ça que Resend demande `send.<domaine>`, SES un MAIL FROM personnalisé et Lumail
   `ses.<domaine>` : ce sous-domaine porte le MX de retour des bounces et le SPF. Un SPF sur le
   From ne sert que si ce domaine est aussi l'enveloppe (Brevo sans sous-domaine brandé,
   Google Workspace, Mailgun).
2. **DMARC passe si SPF *ou* DKIM passe et est aligné** avec le domaine du From (alignement
   relâché = même domaine organisationnel). DKIM aligné suffit ; c'est le chemin le plus robuste.
3. **Un sous-domaine par flux** (`mail.` transactionnel, `news.` marketing) isole la réputation.
   Un seul DMARC sur la racine les couvre tous via `sp=`.

## Choisir le bon flux de travail

| La demande | Flux |
|---|---|
| « Configure mon domaine / sous-domaine pour Resend, SES, Brevo… » | **A. Configurer** |
| « Mes emails vont en spam », « DMARC échoue », une alerte d'ESP | **B. Diagnostiquer** |
| « Je veux la même chose que Lumail dans mon SaaS » | **C. Construire** → `references/architecture.md` |
| « Vérifie cet email / ce template avant envoi » | **D. Contenu** |

---

## A. Configurer un domaine d'envoi

**1. Recueillir le contexte** (déduire de la conversation ou du code avant de demander) :
domaine racine, usage (transactionnel / marketing / cold), fournisseur et région, hébergeur
DNS, et **qui envoie déjà avec ce domaine** (Google Workspace, Microsoft 365, CRM, helpdesk).
Ce dernier point conditionne le SPF et le futur passage de DMARC à `reject`.

**2. Photographier l'existant** avant toute modification :
```bash
node scripts/dns-audit.mjs client.com                 # racine : SPF, DMARC, MX existants
node scripts/dns-audit.mjs mail.client.com --provider resend
```
Ne jamais écraser un SPF ou un DMARC existant : il ne doit y en avoir qu'**un** par nom.

**3. Choisir les noms** (convention par défaut, à adapter) :

| Rôle | Nom | Exemple |
|---|---|---|
| From transactionnel | `mail.<racine>` | `notifications@mail.client.com` |
| From marketing | `news.<racine>` | `hello@news.client.com` |
| Return-Path | préfixe du fournisseur sous le From | `send.mail.client.com` (Resend), `bounce.news.client.com` (SES) |
| Tracking des liens | `click.<racine>` | CNAME, jamais le domaine du From |
| DMARC | `_dmarc.<racine>` | un seul, hérité par les sous-domaines |

Reply-To vers une vraie boîte si le sous-domaine d'envoi n'a pas de MX.

**4. Créer l'identité chez le fournisseur, en choisissant la région d'abord.** La région
(Resend `eu-west-1`, SES `eu-west-3`/`eu-central-1`…) est **figée à la création** et fixe la
valeur du MX de retour : la choisir avant de poser le moindre enregistrement, sinon il faut
supprimer le domaine, le recréer et refaire tout le DNS. Pour une clientèle européenne : région UE.
La création renvoie les jetons réels (clé DKIM, tokens SES, code Brevo) — commandes par
fournisseur dans `references/providers.md`. **Ne jamais inventer un jeton** : le plan affiche
`<…>` tant qu'on n'a pas la réponse API.

**5. Générer le plan DNS** :
```bash
node scripts/dns-plan.mjs --provider ses --domain news.client.com --region eu-west-3 \
  --from-api identity.json --rua dmarc@client.com --tracking click --format all --out plan.json
```
Formats : `md` (tableau à copier), `bind` (zone), `json` (pour les étapes 6–7). Le `rua` doit
pointer vers une boîte **réellement lue** (ou un parseur DMARC) : ce sont ces rapports qui
autoriseront le passage à `quarantine`.

**6. Publier les enregistrements.** Si le DNS est chez Cloudflare et qu'un token est disponible :
```bash
CF_API_TOKEN=… node scripts/cloudflare-apply.mjs plan.json           # simulation
CF_API_TOKEN=… node scripts/cloudflare-apply.mjs plan.json --apply   # écriture
```
Le script fusionne le SPF, conserve un DMARC existant, refuse les conflits et force
`proxied: false`. Écrire dans le DNS d'un client est une action externe : montrer la simulation
et obtenir un accord explicite avant `--apply`. Sinon, remettre le tableau Markdown en précisant
le piège de chaque hébergeur (nom relatif vs absolu, nuage gris Cloudflare, TXT > 255 caractères
découpé en chaînes).

Variante à proposer quand la plateforme gère beaucoup de clients ou veut pouvoir changer de
fournisseur : **déléguer le sous-domaine d'envoi** (`news.client.com`) à une zone de la plateforme
avec quelques enregistrements NS. Le client agit une seule fois ; DKIM, MAIL FROM, tracking et
passage de Resend à SES se font ensuite côté plateforme (c'est le « Brevo-managed setup »).
Détails : `references/architecture.md` §2.

**7. Vérifier** — propagation de quelques minutes à 48 h :
```bash
node scripts/dns-audit.mjs news.client.com --provider ses --selectors tok1,tok2,tok3 \
  --return-path bounce.news.client.com --expect plan.json
```
puis déclencher la vérification chez le fournisseur (`verify`), puis un email réel vers une boîte
Gmail (« Afficher l'original » : SPF, DKIM et DMARC doivent être `PASS`).

**8. Mise en service : six conditions avant le premier envoi réel.** L'ordre compte — chaque point
rattrapé après coup coûte de la réputation ou des données perdues :

| # | Condition | Pourquoi avant le 1ᵉʳ envoi |
|---|---|---|
| 1 | Domaine créé dans la **bonne région** (UE) avant le DNS | non modifiable ensuite |
| 2 | Sous-domaine dédié (`news.` marketing, `mail.` transactionnel), SPF/DKIM du fournisseur, DMARC `p=none` + `rua` lu | sans `rua`, aucune preuve pour durcir plus tard |
| 3 | Webhooks **bounces et plaintes** branchés et signés (Resend `email.bounced`, `email.complained` ; SES `Bounce`, `Complaint`) | un bounce ou une plainte non traité → renvoi à l'adresse → réputation brûlée dès la 1ʳᵉ campagne |
| 4 | `List-Unsubscribe` + `List-Unsubscribe-Post: List-Unsubscribe=One-Click` sur le marketing, endpoint **POST** qui désinscrit sans page, sans cookie, sans redirection | exigé par Gmail/Yahoo/Microsoft ; un désabonnement difficile devient un clic « spam » |
| 5 | **Google Postmaster Tools** (domaine organisationnel) et **Yahoo Sender Hub** (boucle de plaintes par domaine DKIM `d=`) inscrits | les données ne remontent qu'à partir de l'inscription : pas d'historique rétroactif |
| 6 | **Warm-up** : 300–500/jour la 1ʳᵉ semaine, contacts les plus engagés d'abord, puis doublement hebdomadaire si bounces < 2 % et plaintes < 0,1 % | un domaine neuf n'a aucune réputation ; un pic de volume = filtrage |

```bash
node scripts/warmup-plan.mjs --target 40000 --start 2026-10-20          # paliers + segments
node scripts/golive-check.mjs --domain news.client.com --provider resend --expect-region eu \
  --webhook-url https://app.client.com/api/email/webhooks/resend \
  --unsubscribe-url https://app.client.com/api/email/unsubscribe/TEST_TOKEN \
  --confirmed postmaster,senderhub --warmup-start 2026-10-20            # GO / NO-GO
```
`golive-check.mjs` déduit la région du MX de retour (et de l'API Resend si `RESEND_API_KEY`
est défini), relance l'audit DNS, envoie un POST **non signé** au webhook (il doit être refusé)
et un POST one-click à l'URL de désinscription de test (il doit répondre 2xx sans redirection).
Les inscriptions Postmaster / Sender Hub ne se vérifient pas par DNS : les confirmer avec l'utilisateur.

Après le warm-up, si les rapports `rua` sont propres : DMARC `p=quarantine` (éventuellement
`t=y` une semaine), puis `p=reject` quand tous les expéditeurs légitimes sont alignés
(`references/standards.md` §4). Microsoft SNDS seulement en cas d'IP dédiée.

## B. Diagnostiquer

1. `node scripts/dns-audit.mjs <domaine> --provider <p> --json` : chaque constat a une clé stable
   (`domain:dmarc:monitoring-only`, `domain:mail-from:mx-missing`…).
2. Chercher la clé dans `references/alerts-catalog.md` pour la cause et la correction ; les alertes
   de métriques (bounces > 2 %, plaintes > 0,1 %, retards > 10 %) y sont aussi, avec leurs seuils.
3. Si le DNS est sain mais que les emails vont en spam, le problème est rarement DNS : regarder
   taux de plainte, qualité de liste, contenu (flux D), réputation (Postmaster Tools), et les
   exigences de `references/standards.md` (one-click unsubscribe, PTR, TLS).
4. Ne pas conclure sur une erreur DNS transitoire (`dns:transient`) : relancer.

Pièges les plus fréquents, dans l'ordre : deux SPF sur le même nom ; plus de 10 lookups SPF ;
DMARC modifié sur le sous-domaine alors que la politique vient de la racine (ou `sp=none`) ;
CNAME DKIM proxifié par Cloudflare ; MAIL FROM sans MX ; DKIM collé en TXT au lieu de CNAME.

## C. Construire la fonctionnalité dans une plateforme

Lire `references/architecture.md` (modèle de données, machine à états, interface d'adaptateur
fournisseur, jobs, API, UI) et `references/alerts-catalog.md` (règles d'alerte à implémenter).
Les scripts de ce skill sont réutilisables tels quels côté serveur : `dns-audit.mjs --json`
pour le job de re-scan, `dns-plan.mjs` pour normaliser les réponses API des fournisseurs,
`content-score.mjs --json` pour le score de contenu dans l'éditeur.

## D. Vérifier un email avant envoi

```bash
node scripts/content-score.mjs campagne.html --subject "…" --brand "Acme"
node scripts/content-score.mjs message.eml --brand acme.fr     # vérifie aussi les en-têtes
```
Onze critères notés sur 100 (désinscription 25, adresse 10, raison de l'envoi 10, objet 10,
ratio image/texte 10, mots spam 10, liens 5, raccourcisseurs 5, majuscules 5, longueur 5,
marque 5), plus des contrôles hors score : `List-Unsubscribe` + `List-Unsubscribe-Post:
List-Unsubscribe=One-Click` (RFC 8058), HTML > 102 Ko tronqué par Gmail, scripts/formulaires.

## Format de réponse

Pour une configuration, rendre dans cet ordre :
1. Le schéma retenu (From, Return-Path, DKIM, DMARC, tracking) en une ligne chacun.
2. Le tableau des enregistrements (sortie `dns-plan.mjs`), noms relatifs à la zone.
3. Ce qui a été vérifié et ce qui reste en attente (sortie `dns-audit.mjs`).
4. Le verdict de mise en service (`golive-check.mjs`) et les prochaines étapes datées (paliers de warm-up, passage DMARC).

## Références

| Fichier | Quand le lire |
|---|---|
| `references/providers.md` | Créer le domaine chez Resend, SES, Brevo, Postmark, Mailgun, SendGrid ; formats exacts et API |
| `references/standards.md` | Règles Gmail/Yahoo/Microsoft, DMARCbis, BIMI, MTA-STS, TLS-RPT, APRF, limites SPF |
| `references/alerts-catalog.md` | Signification et correction d'une alerte ; seuils de santé d'envoi |
| `references/architecture.md` | Concevoir le module domaines dans un SaaS |
