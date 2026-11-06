# Fournisseurs d'envoi : enregistrements DNS et API (octobre 2026)

À lire à l'étape 4 du flux A (créer l'identité chez le fournisseur) et pour écrire un adaptateur.
`D` = domaine enregistré chez le fournisseur (ex. `mail.client.com`). Tous les noms sont sous `D`.
**Copier les valeurs renvoyées par l'API** : les exemples ci-dessous montrent la forme, pas les jetons.

## Sommaire
1. Tableau de synthèse
2. Resend
3. Amazon SES v2
4. Brevo
5. Postmark
6. Mailgun
7. SendGrid
8. Scaleway, Mailjet, Cloudflare Email Service
9. Google Workspace, Microsoft 365 et lemlist
10. Pièges communs à tous les hébergeurs DNS

---

## 1. Synthèse

| Fournisseur | DKIM | Return-Path (aligne SPF) | SPF à publier | Tracking | Statut de domaine |
|---|---|---|---|---|---|
| Resend | TXT `resend._domainkey` (1024 bits seulement) | `send.D` MX `feedback-smtp.<region>.amazonses.com` | TXT sur `send.D` | `links.D` → `links1.resend-dns.com` | webhook `domain.updated` |
| SES | 3 CNAME `<token>._domainkey` → `<token>.<SigningHostedZone>` (2048 bits) | sous-domaine libre, MX `feedback-smtp.<region>.amazonses.com` | TXT sur le MAIL FROM | — | polling `GetEmailIdentity` |
| Brevo | 2 CNAME `brevo1/2._domainkey` (ou ancien TXT `mail._domainkey`) | `brevosend.com` sauf sous-domaine brandé | seulement avec IP dédiée | sous le sous-domaine brandé (`r.`, `img.`) | bouton / `PUT …/authenticate` |
| Postmark | TXT `<horodatage>pm._domainkey` (1024 bits) | `pm-bounces.D` CNAME `pm.mtasv.net` | **aucun** (porté par le CNAME) | — | `PUT /domains/{id}/verifyDkim` |
| Mailgun | TXT `<sélecteur>._domainkey` ou 2 CNAME `pdk1/pdk2` (2048, rotation 120 j) | le domaine lui-même | TXT `include:mailgun.org` sur `D` | `email.D` → `mailgun.org` | `PUT /v4/domains/{name}/verify` |
| SendGrid | 2 CNAME `s1/s2._domainkey` → `…sendgrid.net` | `em1234.D` CNAME `u…wl….sendgrid.net` | porté par le CNAME | `url1234.D` + `1234.D` → `sendgrid.net` | `POST …/validate` |
| Scaleway TEM | TXT `<project_id>._domainkey` | — | `include:_spf.tem.scaleway.com` sur `D` | — | `POST …/domains/{id}/check` |
| Mailjet | TXT `mailjet._domainkey` | `bnc3.D` CNAME `bnc3.mailjet.com` (sur ticket, payant) | `include:spf.mailjet.com` | — | `POST /v3/REST/dns/{id}/check` |
| Cloudflare Email | TXT `cf-bounce._domainkey` | `cf-bounce.D` MX `route1/2/3.mx.cloudflare.net` | TXT sur `cf-bounce.D` | — | auto (DNS Cloudflare obligatoire) |

Seul Resend notifie un changement de statut de domaine par webhook : partout ailleurs, prévoir un
polling avec backoff.

## 2. Resend

```bash
curl -X POST https://api.resend.com/domains \
  -H "Authorization: Bearer $RESEND_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"mail.client.com","region":"eu-west-1","custom_return_path":"send",
       "click_tracking":true,"tracking_subdomain":"links","tls":"opportunistic"}'
# → { id, status, records: [{record, name, type, value, ttl, status, priority}] }
curl -X POST https://api.resend.com/domains/$ID/verify -H "Authorization: Bearer $RESEND_API_KEY"   # asynchrone
curl https://api.resend.com/domains/$ID -H "Authorization: Bearer $RESEND_API_KEY" > resend.json
node scripts/dns-plan.mjs --provider resend --domain mail.client.com --from-api resend.json --out plan.json
```
- Régions : `us-east-1`, `eu-west-1`, `sa-east-1`, `ap-northeast-1` (figée).
- Depuis août 2026, le Return-Path peut être publié en **2 CNAME** (`send`, `rsend`) au lieu de MX + TXT :
  toujours afficher le tableau `records` renvoyé par l'API (la région ne se lit alors plus dans le DNS).
- `custom_return_path` : défaut `send`, ≤ 63 caractères, commence par une lettre, **non modifiable**
  (supprimer et recréer le domaine).
- Statuts domaine et records : `not_started`, `pending`, `verified`, `partially_verified`,
  `partially_failed`, `failed` (records absents après 72 h), `temporary_failure` (re-vérifié 72 h).
- Webhooks : `email.bounced`, `email.complained`, `email.failed`, `email.suppressed`,
  `email.delivery_delayed`, `domain.created|updated|deleted`, `suppression.added|removed`.
- One-click : à ajouter soi-même dans `headers` sur `/emails` (`List-Unsubscribe` +
  `List-Unsubscribe-Post`) ; Broadcasts : `{{{RESEND_UNSUBSCRIBE_URL}}}`.
- Réception (inbound) : MX fourni par le dashboard, de préférence sur un sous-domaine dédié.
- DKIM limité à 1024 bits (accepté par Gmail, en dessous des 2048 recommandés) — d'où l'avertissement
  `domain:dkim:weak` de l'audit, sans action possible côté client.

## 3. Amazon SES v2

```bash
aws sesv2 create-email-identity --region eu-west-3 --email-identity news.client.com \
  --dkim-signing-attributes NextSigningKeyLength=RSA_2048_BIT \
  --configuration-set-name marketing
aws sesv2 put-email-identity-mail-from-attributes --region eu-west-3 \
  --email-identity news.client.com --mail-from-domain bounce.news.client.com \
  --behavior-on-mx-failure USE_DEFAULT_VALUE
aws sesv2 get-email-identity --region eu-west-3 --email-identity news.client.com > identity.json
node scripts/dns-plan.mjs --provider ses --domain news.client.com --region eu-west-3 --from-api identity.json --out plan.json
```
- **Easy DKIM** : 3 CNAME `<token>._domainkey.D` → `<token>.<DkimAttributes.SigningHostedZone>` ;
  la zone varie selon région et identité (ex. `dkim.us-west-2.amazonses.com`) : ne pas coder
  `dkim.amazonses.com` en dur. Rotation automatique ; longueur modifiable une fois par 24 h.
- **BYODKIM** : sélecteur et clé privée fournis (`DomainSigningSelector`, `DomainSigningPrivateKey`)
  → TXT `<sélecteur>._domainkey.D = p=…`. Utile pour garder un sélecteur stable entre fournisseurs.
- **MAIL FROM** : sous-domaine du domaine vérifié, jamais utilisé comme From ni pour recevoir ;
  **un seul MX** `10 feedback-smtp.<region>.amazonses.com` + TXT `v=spf1 include:amazonses.com ~all`.
  `BehaviorOnMxFailure=USE_DEFAULT_VALUE` repasse sur `amazonses.com` (SPF non aligné) en cas
  d'échec ; `REJECT_MESSAGE` refuse l'envoi.
- **Statuts** (`VerificationStatus`, `DkimAttributes.Status`) : `PENDING`, `SUCCESS`, `FAILED`,
  `TEMPORARY_FAILURE`, `NOT_STARTED` ; `MailFromDomainStatus` : `PENDING`, `SUCCESS`,
  `TEMPORARY_FAILURE`, `FAILED` (fenêtre 72 h). Pas d'appel « verify » : SES interroge le DNS.
  Pas de webhook d'identité → polling de `GetEmailIdentity`.
- **Événements** : configuration set + destination (`SNS`, `EventBridge`, Firehose, CloudWatch)
  avec `BOUNCE`, `COMPLAINT`, `DELIVERY`, `DELIVERY_DELAY`, `REJECT`, `RENDERING_FAILURE`,
  `OPEN`, `CLICK`, `SUBSCRIPTION`.
- **Liste de suppression** : niveau compte (`PutAccountSuppressionAttributes BOUNCE COMPLAINT`)
  ou par configuration set ; seuls les hard bounces y entrent ; Gmail n'envoie pas de plaintes à SES.
- **Sandbox** par région : destinataires vérifiés, 200 messages/24 h, 1/s ; sortie via
  `put-account-details --production-access-enabled --mail-type MARKETING|TRANSACTIONAL`.
- **One-click natif** : `ListManagementOptions {ContactListName, TopicName}` → SES ajoute les deux
  en-têtes (un seul destinataire, Easy DKIM requis) ; placeholder `{{amazonSESUnsubscribeUrl}}`.
- DMARC : `aspf=s` casse l'alignement SPF via MAIL FROM ; garder l'alignement relâché.

## 4. Brevo

```bash
curl -X POST https://api.brevo.com/v3/senders/domains -H "api-key: $BREVO_API_KEY" \
  -H "Content-Type: application/json" -d '{"name":"news.client.com"}'
# → { id, domain_name, domain_provider, message, dns_records: { brevo_code, dkim_record, dmarc_record } }
#   chaque record : { type, value, host_name, status }
curl https://api.brevo.com/v3/senders/domains/news.client.com -H "api-key: $BREVO_API_KEY" > brevo.json
curl -X PUT https://api.brevo.com/v3/senders/domains/news.client.com/authenticate -H "api-key: $BREVO_API_KEY"
```
- Records : `brevo-code:<hash>` (TXT `@`), DKIM 2 CNAME `brevo1._domainkey` / `brevo2._domainkey`
  → `b1|b2.<valeur>.dkim.brevo.com` (2048 bits, rotation par Brevo ; l'API ne documente encore
  qu'un `dkim_record`), ancien DKIM TXT `mail._domainkey` (1024 bits) à garder jusqu'à
  authentification des CNAME, DMARC proposé `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com`.
- **Sous-domaine brandé** (`send.`, `mail.`, `em.`) : Return-Path, tracking (`r.`) et images (`img.`)
  sous le domaine client → SPF aligné. Sinon Return-Path `brevosend.com` et DMARC par DKIM seul.
- **Délégation** possible : 2 NS pour le sous-domaine brandé (« Brevo-managed setup »).
- Pièges hébergeurs listés par Brevo : nom à saisir avec ou sans domaine, point final, domaine
  doublé (`…client.com.client.com`), CNAME flattening Cloudflare à désactiver, TXT > 255 caractères.
- Erreurs API : 400 « DNS records not properly configured », « DMARC policy requires domain
  authentication », « Domain already exists in your account » ; 404 domaine inexistant.

## 5. Postmark

```bash
curl -X POST https://api.postmarkapp.com/domains -H "X-Postmark-Account-Token: $PM_ACCOUNT_TOKEN" \
  -H "Content-Type: application/json" -d '{"Name":"mail.client.com","ReturnPathDomain":"pm-bounces.mail.client.com"}'
curl -X PUT https://api.postmarkapp.com/domains/$ID/verifyDkim -H "X-Postmark-Account-Token: $PM_ACCOUNT_TOKEN"
curl -X PUT https://api.postmarkapp.com/domains/$ID/verifyReturnPath -H "X-Postmark-Account-Token: $PM_ACCOUNT_TOKEN"
curl -X POST https://api.postmarkapp.com/domains/$ID/rotatedkim -H "X-Postmark-Account-Token: $PM_ACCOUNT_TOKEN"
```
- Champs : `DKIMHost`/`DKIMTextValue`, `DKIMPendingHost`/`DKIMPendingTextValue` (rotation en cours),
  `DKIMRevokedHost`, `SafeToRemoveRevokedKeyFromDNS`, `ReturnPathDomain`, `ReturnPathDomainVerified`,
  `ReturnPathDomainCNAMEValue`.
- **Aucun SPF à ajouter** : le CNAME `pm-bounces` → `pm.mtasv.net` porte le SPF ; ajouter
  `include:spf.mtasv.net` sur la racine ne sert à rien.
- Rotation DKIM conseillée au moins chaque trimestre. Les streams « broadcast » ajoutent le
  one-click automatiquement.

## 6. Mailgun

```bash
curl -s --user "api:$MAILGUN_API_KEY" https://api.eu.mailgun.net/v4/domains \
  -F name=mg.client.com -F use_automatic_sender_security=true -F dkim_key_size=2048 -F web_prefix=email
# → sending_dns_records[], receiving_dns_records[] (chacun avec "valid")
curl -s --user "api:$MAILGUN_API_KEY" -X PUT https://api.eu.mailgun.net/v4/domains/mg.client.com/verify
```
- SPF `v=spf1 include:mailgun.org ~all` **sur le domaine lui-même** (c'est aussi l'enveloppe).
- DKIM : TXT `<dkim_selector>._domainkey.D`, ou avec Automatic Sender Security 2 CNAME
  `pdk1/pdk2._domainkey.D` → `pdk1/pdk2._domainkey.<id>.dkim1.mailgun.com` (rotation 120 j).
- Tracking `email.D` → `mailgun.org` (EU : `eu.mailgun.org`) ; MX de réception `mxa/mxb.mailgun.org`
  (EU : `mxa/mxb.eu.mailgun.org`) seulement pour recevoir.
- Événements : `delivered`, `failed` (permanent), `temporary_fail`, `complained`, `unsubscribed`,
  `opened`, `clicked`.

## 7. SendGrid

```bash
curl -X POST https://api.sendgrid.com/v3/whitelabel/domains -H "Authorization: Bearer $SENDGRID_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"domain":"client.com","subdomain":"em","automatic_security":true,"custom_dkim_selector":"cl1"}'
# → dns.{mail_cname, dkim1, dkim2} avec host, data, valid
curl -X POST https://api.sendgrid.com/v3/whitelabel/domains/$ID/validate -H "Authorization: Bearer $SENDGRID_API_KEY"
```
- Automated security : `em1234.D` CNAME `u123.wl456.sendgrid.net`, `s1/s2._domainkey.D` CNAME
  `s1/s2.domainkey.u123.wl456.sendgrid.net`. Link branding : `url1234.D` et `1234.D` → `sendgrid.net`.
- Base EU : `api.eu.sendgrid.com`. Les sous-domaines n'héritent pas de l'authentification.

## 8. Scaleway, Mailjet, Cloudflare Email Service

- **Scaleway TEM** (`fr-par`, données en France) : SPF `v=spf1 include:_spf.tem.scaleway.com -all`,
  DKIM TXT `<project_id>._domainkey` (lire `dkim_config`), MX `blackhole.tem.scaleway.com` seulement si
  aucun MX, DMARC exigé pour la vérification. API `POST …/regions/fr-par/domains`, `…/{id}/check`.
  Auto-configuration si le DNS est chez Scaleway. Pas de one-click natif documenté.
- **Mailjet** : TXT de propriété (`OwnerShipTokenRecordName` / `OwnerShipToken`), SPF
  `include:spf.mailjet.com`, DKIM `mailjet._domainkey` ; Return-Path `bnc3.D` → `bnc3.mailjet.com`
  sur ticket (plans payants). API `GET /v3/REST/dns/{id}`, `POST /v3/REST/dns/{id}/check`.
- **Cloudflare Email Service** (bêta, Workers payant, DNS Cloudflare obligatoire, records ajoutés
  automatiquement) : MX `cf-bounce.D` → `route1/2/3.mx.cloudflare.net`, SPF
  `include:_spf.mx.cloudflare.net` sur `cf-bounce.D`, DKIM `cf-bounce._domainkey.D`, DMARC `p=none`.
  Pas d'API de domaine ni de webhook de bounce à ce jour.

## 9. Google Workspace, Microsoft 365 et lemlist

- **Google Workspace** : SPF `include:_spf.google.com` sur la racine, DKIM TXT `google._domainkey`
  généré dans la console Admin (2048 bits).
- **Microsoft 365** : SPF `include:spf.protection.outlook.com`, DKIM 2 CNAME `selector1/selector2._domainkey`
  vers les cibles affichées dans Defender.
- **lemlist** n'envoie pas lui-même : il utilise ces boîtes. Ne pas l'ajouter au SPF. Domaine de
  tracking obligatoire si le suivi est actif : CNAME (`trail`, `route`…) → `custom.lemlist.com`,
  TXT de vérification, CAA `letsencrypt.org` si la zone restreint les autorités, DNS only.
  lemlist recommande DMARC `p=quarantine` minimum pour le cold email.

## 10. Pièges communs aux hébergeurs DNS

| Piège | Symptôme | Correction |
|---|---|---|
| Cloudflare proxy (nuage orange) sur un CNAME DKIM ou tracking | DKIM introuvable, erreur 526 | DNS only (nuage gris), désactiver le CNAME flattening sur ces noms |
| Nom saisi en absolu chez un hébergeur qui ajoute la zone | `resend._domainkey.mail.client.com.client.com` | saisir le nom relatif (`resend._domainkey.mail`) ou terminer par un point |
| TXT > 255 caractères (clé 2048 bits) | clé tronquée, DKIM `fail` | découper en plusieurs chaînes entre guillemets (Route 53, BIND) |
| Deux SPF au même nom | `permerror` sur tout le domaine | fusionner en un seul TXT |
| CNAME sur un nom qui a déjà d'autres records | refus de l'hébergeur | changer de sous-domaine (le CNAME ne cohabite avec rien) |
| MX ajouté sur le Return-Path SES en plus de celui de SES | MAIL FROM en échec | un seul MX sur ce nom |
| Ancien DKIM supprimé trop tôt pendant une rotation | échecs DKIM pendant quelques heures | garder l'ancien sélecteur jusqu'à vérification du nouveau |
