# Amazon SES v2 — mise en place pour une plateforme multi-tenant

À lire pour l'installation AWS initiale (une fois par compte et par région) et pour tout ce qui
touche aux tenants SES, aux événements, à l'IAM ou aux quotas. Faits vérifiés au 13/10/2026.

## Sommaire
1. Installation initiale (CLI)
2. Onboarding d'un client
3. Envoi
4. Événements
5. Suppression
6. Réputation et pause des tenants
7. IAM minimal
8. Pièges

---

## 1. Installation initiale (une fois par région)

Région UE par défaut : `eu-west-3` (Paris). Remplacer `ACCOUNT` et la région.

```bash
R=eu-west-3; P=platform
# 0. Sortir de la sandbox (200 emails/24 h, destinataires vérifiés seulement)
aws sesv2 put-account-details --region $R --production-access-enabled \
  --mail-type MARKETING --website-url https://plateforme.com --contact-language EN

# 1. Topic SNS unique pour tous les événements (abonnement HTTPS = route webhooks/ses)
aws sns create-topic --region $R --name $P-ses-events
aws sns subscribe --region $R --topic-arn arn:aws:sns:$R:ACCOUNT:$P-ses-events \
  --protocol https --notification-endpoint https://app.plateforme.com/api/email/webhooks/ses
#   → la route confirme l'abonnement toute seule (SubscriptionConfirmation signé).
#   → NE PAS activer RawMessageDelivery (le corps brut n'est pas signé).
aws sns set-topic-attributes --region $R --topic-arn arn:aws:sns:$R:ACCOUNT:$P-ses-events \
  --attribute-name SignatureVersion --attribute-value 2      # SHA256 plutôt que SHA1

# 2. Configuration sets PARTAGÉS par flux (10 000 max par région, non ajustable)
for S in marketing transactional; do
  aws sesv2 create-configuration-set --region $R --configuration-set-name $P-$S \
    --reputation-options '{"ReputationMetricsEnabled":true}' --sending-options '{"SendingEnabled":true}' \
    --suppression-options '{"SuppressedReasons":["BOUNCE","COMPLAINT"]}'
  aws sesv2 create-configuration-set-event-destination --region $R \
    --configuration-set-name $P-$S --event-destination-name sns \
    --event-destination '{"Enabled":true,"MatchingEventTypes":["SEND","REJECT","BOUNCE","COMPLAINT","DELIVERY","DELIVERY_DELAY","RENDERING_FAILURE","SUBSCRIPTION"],"SnsDestination":{"TopicArn":"arn:aws:sns:'$R':ACCOUNT:'$P'-ses-events"}}'
done
#   Si SES ne publie rien : autoriser ses.amazonaws.com (condition aws:SourceAccount) dans la
#   politique du topic, et vérifier la clé KMS si le topic est chiffré.

# 3. État des tenants (pause / réactivation par AWS) → même topic via EventBridge
aws events put-rule --region $R --name $P-ses-tenant-status \
  --event-pattern '{"source":["aws.ses"],"detail-type":[{"prefix":"Sending Status"}]}'
aws events put-targets --region $R --rule $P-ses-tenant-status \
  --targets "Id=sns,Arn=arn:aws:sns:$R:ACCOUNT:$P-ses-events"
#   (la politique du topic doit autoriser events.amazonaws.com à publier)

# 4. Suppression au niveau compte activée (filet de sécurité)
aws sesv2 put-account-suppression-attributes --region $R --suppressed-reasons BOUNCE COMPLAINT
```

Les tenants SES peuvent être facturés en option (0,005 $/tenant/mois + 0,005 $/1 000 emails) ou
inclus dans le plan Enterprise (1 000 tenants). Vérifier le plan du compte
(`PutAccountPricingAttributes`) avant de dimensionner.

## 2. Onboarding d'un client (fait par `providers/ses.ts`)

1. `GetTenant` / `CreateTenant` : `TenantName = t-<tenantId>` (≤ 64 caractères `[A-Za-z0-9_-]`),
   `SuppressionAttributes {SuppressionScope: TENANT, SuppressedReasons: [BOUNCE, COMPLAINT]}`.
2. `CreateTenantResourceAssociation` des deux configuration sets partagés vers le tenant.
3. `CreateEmailIdentity` : `EmailIdentity = news.client.com`, `DkimSigningAttributes.NextSigningKeyLength = RSA_2048_BIT`,
   `ConfigurationSetName` par défaut. Réponse : 3 jetons DKIM + `SigningHostedZone`.
4. `PutEmailIdentityMailFromAttributes` : `bounce.news.client.com`, `BehaviorOnMxFailure = USE_DEFAULT_VALUE`.
5. `CreateTenantResourceAssociation` de l'identité (`arn:aws:ses:<r>:<acct>:identity/<domaine>`).
6. DNS : 3 CNAME `<jeton>._domainkey` → `<jeton>.<SigningHostedZone>` ; MAIL FROM : **un seul** MX
   `10 feedback-smtp.<r>.amazonses.com` + TXT `v=spf1 include:amazonses.com ~all`.
7. Pas d'appel « verify » : SES interroge le DNS jusqu'à 72 h → `GetEmailIdentity` en polling
   (`VerifiedForSendingStatus`, `DkimAttributes.Status`, `MailFromAttributes.MailFromDomainStatus`).

Toutes ces opérations relèvent de l'API de gestion **limitée à 1 requête/s** : les passer par une file.

## 3. Envoi

`SendEmail` avec `FromEmailAddress` (nom affiché encodé RFC 2047 si non ASCII), `Destination.ToAddresses`
(un destinataire), `Content.Simple {Subject, Body.Html/Text, Headers[]}` (15 en-têtes max, valeur ≤ 995
caractères), `EmailTags` (`[A-Za-z0-9_-]`, 256 caractères), `ConfigurationSetName`, **`TenantName`**.
L'envoi n'est accepté que si l'identité, le configuration set (et le template éventuel) sont associés
au tenant. Taille max 40 Mo, 50 destinataires/message.

Erreurs à traiter : `TooManyRequestsException` / `ThrottlingException` (débit ou quota journalier,
réessayer avec backoff), `SendingPausedException`, `AccountSuspendedException`,
`MailFromDomainNotVerifiedException` (→ bascule), `MessageRejected`.

One-click natif possible via `ListManagementOptions` (listes de contacts SES), mais la brique pose
ses propres en-têtes `List-Unsubscribe` pour rester identique sur Resend et SES.

## 4. Événements

Charge utile SNS (`Message` JSON) : `eventType` (`Send`, `Delivery`, `Bounce`, `Complaint`,
`DeliveryDelay`, `Reject`, `Rendering Failure`, `Subscription`, `Open`, `Click`), `mail.messageId`,
`mail.tags` (nos tags : `tenant`, `message`, `stream`), `bounce.bounceType`
(`Permanent` | `Transient` | `Undetermined`), `bounce.bounceSubType` (dont `OnTenantSuppressionList`,
`MailboxFull`), `complaint.complaintFeedbackType`. SES n'ajoute `ses:tenant-name` qu'aux bounces et
plaintes : d'où notre propre tag `tenant`.

## 5. Suppression

Ordre de priorité : configuration set → tenant → compte. Avec `SuppressionScope: TENANT`, la liste du
compte est ignorée pour ce tenant. `PutSuppressedDestination` / `ListSuppressedDestinations` acceptent
un `TenantName`. Supprimer un tenant supprime sa liste. Les envois supprimés comptent dans le quota.
La brique tient en plus sa propre liste (globale pour les hard bounces) : elle bloque **avant** l'appel.

## 6. Réputation et pause des tenants

- Politiques gérées : `standard` (défaut, pause sur constat grave), `strict` (pause sur tout constat),
  `none` (constate sans pauser). ARN : `arn:aws:ses:<r>:aws:reputation-policy/standard` (les suffixes
  `strict` / `none` suivent le même schéma — à vérifier dans la console).
- Constats : taux de bounce, plaintes, retours tiers, listes noires, sur 24 h à 7 jours glissants.
- Pause → événement EventBridge « Sending Status Disabled » → route webhook → bloquer le client dans
  l'app, l'avertir, investiguer (`ListRecommendations` filtré sur l'ARN du tenant).
- Réactivation : `UpdateReputationEntityCustomerManagedStatus` → état « REINSTATED » (période de grâce).
- Métriques CloudWatch par tenant (dimensions `TenantId`, `TenantName`), vue VDM par tenant.

## 7. IAM minimal

Rôle applicatif (envoi) :
```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["ses:SendEmail"],
      "Resource": ["arn:aws:ses:eu-west-3:ACCOUNT:identity/*", "arn:aws:ses:eu-west-3:ACCOUNT:configuration-set/platform-*"] }
  ]
}
```
Rôle d'administration (onboarding, séparé) : `ses:CreateEmailIdentity`, `ses:GetEmailIdentity`,
`ses:PutEmailIdentityMailFromAttributes`, `ses:CreateTenant`, `ses:GetTenant`,
`ses:CreateTenantResourceAssociation`, `ses:DeleteTenantResourceAssociation`,
`ses:DeleteEmailIdentity`, `route53:CreateHostedZone`, `route53:ChangeResourceRecordSets`,
`route53:ListResourceRecordSets`, `route53:GetHostedZone`, `route53:DeleteHostedZone`.
Refuser `ses:DeleteTenant` hors procédure. Clés de condition utiles : `ses:TenantName`,
`ses:FromAddress`. Préférer des rôles (identifiants temporaires) aux clés longues ; les identifiants
SMTP, eux, ne peuvent pas être temporaires.

## 8. Pièges

- Coder `dkim.amazonses.com` en dur : la cible dépend de `SigningHostedZone`.
- Deux MX sur le MAIL FROM, ou MAIL FROM réutilisé comme From : échec de vérification.
- Oublier d'associer le configuration set au tenant : envoi refusé.
- Supprimer une identité encore associée à un tenant : refusé, retirer l'association d'abord.
- Les tenants ne répartissent pas le quota du compte : un client peut consommer tout le débit.
- Multi-région (Global endpoints) : identités, configuration sets et tenants à recréer dans la 2ᵉ région.
