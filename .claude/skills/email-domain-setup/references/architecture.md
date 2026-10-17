# Architecture d'un module « domaines d'envoi » multi-fournisseurs

À lire quand il faut **construire** la fonctionnalité dans une plateforme (et pas seulement
configurer un domaine). C'est la version simplifiée de ce que font Lumail, Brevo et Resend.

## Sommaire
1. Principes
2. Convention de nommage des sous-domaines
3. Modèle de données
4. Machine à états
5. Interface d'adaptateur fournisseur
6. Jobs et webhooks
7. API exposée
8. UI minimale
9. Ce qu'on ne clone pas (et pourquoi)

---

## 1. Principes

1. **Le fournisseur est la source de vérité des jetons** (DKIM, vérification). La plateforme ne
   les invente jamais : elle les récupère par API et les affiche tels quels.
2. **La plateforme lit le DNS, elle ne l'écrit pas** — sauf si le client a connecté son DNS
   (token Cloudflare, Entri, Domain Connect). Dans ce cas, écrire en `proxied: false`.
3. **Deux vérifications distinctes** : l'état chez le fournisseur (`verified`) et notre propre
   audit DNS (SPF lookups, DMARC hérité, BIMI…). Le fournisseur ne vérifie pas DMARC.
4. **Un sous-domaine par flux** isole la réputation : un incident marketing ne bloque pas les
   codes OTP.
5. **Rien ne se résout sur un échec DNS** : une alerte se ferme seulement sur un scan sain.

## 2. Convention de nommage

Pour un client `client.com` :

| Usage | Domaine du From | Return-Path / MAIL FROM | DKIM | Tracking |
|---|---|---|---|---|
| Transactionnel (OTP, factures) | `mail.client.com` | `bounce.mail.client.com` (SES) / `send.mail.client.com` (Resend) | sur `mail.client.com` | aucun ou `links.client.com` |
| Marketing / newsletter | `news.client.com` | `bounce.news.client.com` | sur `news.client.com` | `click.client.com` |
| Pages web (capture) | — | — | — | `pages.client.com` |

- DMARC : **un seul** enregistrement sur `_dmarc.client.com` couvre tous les sous-domaines
  (`sp=` gouverne). Ne créer `_dmarc.mail.client.com` que pour une politique différente.
- L'alignement DMARC relâché (par défaut) accepte `bounce.mail.client.com` et `d=mail.client.com`
  pour un From `@mail.client.com` (même domaine organisationnel).
- Le From sur la racine (`hello@client.com`) reste possible : DKIM `d=client.com`, Return-Path
  `bounce.client.com`. Moins d'isolation, meilleure reconnaissance de marque.
- Le domaine de tracking **ne doit pas** être le From (Lumail) ; un sous-domaine dédié évite qu'une
  mise en liste noire du domaine partagé du fournisseur emporte vos liens.

### Trois façons de brancher le DNS du client

| Mode | Ce que fait le client | Changer de fournisseur | Quand le choisir |
|---|---|---|---|
| **Records copiés** (Lumail, Resend) | 5–7 records chez son hébergeur | tout refaire | peu de clients, clients techniques |
| **Écriture par API** (Brevo « automatique », token Cloudflare, Entri, Domain Connect) | connecte son DNS une fois | automatique | clients non techniques sur un hébergeur supporté |
| **Délégation NS** (Brevo « managed », lemlist via Scaleway) | 2 NS `mail.client.com` → zone de la plateforme | transparent | plateforme multi-fournisseurs : recommandé |

Délégation NS, en pratique :
```
; chez le client (zone client.com)
mail   IN NS  ns-123.awsdns-45.com.
mail   IN NS  ns-678.awsdns-90.net.
; dans la zone mail.client.com hébergée par la plateforme (Route 53 / Cloudflare)
<token>._domainkey   CNAME  <token>.dkim.eu-west-3.amazonses.com.   ; ou resend._domainkey TXT …
bounce               MX 10  feedback-smtp.eu-west-3.amazonses.com.
bounce               TXT    "v=spf1 include:amazonses.com ~all"
_dmarc               TXT    "v=DMARC1; p=quarantine; rua=mailto:dmarc@plateforme.com"
```
- La plateforme peut publier un `_dmarc.mail.client.com` propre (il prime sur celui de la racine).
- Le DMARC de la racine reste au client ; la délégation ne touche pas à ses MX ni à son SPF racine.
- Le tracking reste sur un nom séparé (`click.client.com`) ou passe aussi sous la délégation
  (`click.mail.client.com`).
- Le changement de fournisseur devient une opération interne : créer l'identité chez le nouveau,
  écrire ses records dans la zone déléguée, vérifier, basculer l'adaptateur, retirer les anciens records.

## 3. Modèle de données (Prisma-like)

```prisma
model MailDomain {
  id            String   @id            // dom_…
  orgId         String
  domain        String                  // mail.client.com
  rootDomain    String                  // client.com (domaine organisationnel)
  purpose       Purpose                 // TRANSACTIONAL | MARKETING
  provider      Provider                // RESEND | SES | BREVO | POSTMARK | MAILGUN | SENDGRID
  providerRef   String?                 // id du domaine/identité chez le fournisseur
  region        String?                 // immuable après création (Lumail, Resend)
  status        DomainStatus            // NOT_STARTED | PENDING | VERIFIED | FAILED | TEMPORARY_FAILURE
  fallbackPriority Int?                 // 1..3, null = pas de repli
  lastCheckedAt DateTime?
  records       DnsRecord[]
  findings      Recommendation[]
  senders       EmailSender[]
  @@unique([orgId, domain])
}

model DnsRecord {
  id        String @id
  domainId  String
  purpose   RecordPurpose  // VERIFICATION | SPF | DKIM | MAIL_FROM_MX | MAIL_FROM_SPF | DMARC | TRACKING | BIMI | APRF
  type      String         // TXT | CNAME | MX
  name      String         // FQDN
  value     String
  priority  Int?
  ttl       Int?
  required  Boolean        // DMARC/BIMI/APRF = false côté fournisseur, mais suivis par l'audit
  status    RecordStatus   // PENDING | VERIFIED | FAILED | NOT_FOUND
  observed  String?        // ce que le DNS renvoie réellement (pour l'UI « attendu / trouvé »)
}

model Recommendation {
  id        String @id
  orgId     String
  domainId  String?
  ruleKey   String         // domain:dmarc:monitoring-only …
  severity  Severity       // INFO | WARNING | ERROR
  status    String         // OPEN | RESOLVED
  evidence  Json
  openedAt  DateTime
  resolvedAt DateTime?
  notifiedAt DateTime?
  @@unique([orgId, domainId, ruleKey])
}

model EmailSender { id String @id; domainId String; localPart String; displayName String; replyTo String? }
```

## 4. Machine à états

```
NOT_STARTED ──create()──▶ PENDING ──provider verified──▶ VERIFIED
                             │  ▲                           │
                     timeout │  │ records fixed             │ record removed / provider failure
                       72 h  ▼  │                           ▼
                           FAILED ◀──────────────────── TEMPORARY_FAILURE
```

- `PENDING` : records créés chez le fournisseur, DNS pas encore propagé. Poll avec backoff
  (1 min, 5 min, 15 min, 1 h…) pendant 72 h.
- `VERIFIED` : déverrouille l'envoi pour les senders de ce domaine (Lumail : déverrouille aussi le compte).
- `TEMPORARY_FAILURE` (Resend) : un record a disparu après vérification → alerte, re-check, l'envoi peut
  continuer un temps ; après 72 h → `FAILED`.
- Région : figée à la création (changer de région = recréer le domaine).

## 5. Interface d'adaptateur fournisseur

```ts
interface SendingProvider {
  id: "resend" | "ses" | "brevo" | "postmark" | "mailgun" | "sendgrid";
  createDomain(input: { domain: string; region?: string; returnPathLabel?: string }): Promise<ProviderDomain>;
  getDomain(ref: string): Promise<ProviderDomain>;          // records + statuts par record
  verifyDomain(ref: string): Promise<ProviderDomain>;       // déclenche un re-check côté fournisseur
  deleteDomain(ref: string): Promise<void>;
  send(msg: OutboundMessage): Promise<{ messageId: string }>;
  parseWebhook(req: Request): Promise<DeliveryEvent[]>;     // delivered | bounced | complained | delayed | opened | clicked
}

type ProviderDomain = {
  ref: string;
  status: "not_started" | "pending" | "verified" | "failed" | "temporary_failure";
  records: { purpose: string; type: "TXT" | "CNAME" | "MX"; name: string; value: string; priority?: number; status: string }[];
};
```

Correspondances utiles :
- **SES v2** : `CreateEmailIdentity` (Easy DKIM, `DkimSigningAttributes.NextSigningKeyLength=RSA_2048_BIT`),
  `PutEmailIdentityMailFromAttributes` (`BehaviorOnMxFailure=USE_DEFAULT_VALUE`),
  `GetEmailIdentity` → `DkimAttributes.Tokens/Status`, `MailFromAttributes.MailFromDomainStatus`,
  `VerifiedForSendingStatus`. Feedback via configuration set → SNS/EventBridge.
- **Resend** : `POST /domains` → `records[]` ; `POST /domains/{id}/verify` ; `GET /domains/{id}`.
- **Brevo** : `POST /senders/domains`, `GET /senders/domains/{domain}`, `PUT /senders/domains/{domain}/authenticate`.
- Le module `scripts/lib/providers.mjs` contient les gabarits par fournisseur ; `dns-plan.mjs --from-api`
  convertit la réponse API brute en plan normalisé.

## 6. Jobs et webhooks

| Job | Fréquence | Rôle |
|---|---|---|
| `domain.poll` | backoff tant que PENDING | `getDomain` + audit DNS → met à jour `DnsRecord.status/observed` |
| `domain.rescan` | quotidien par domaine VERIFIED | audit complet (`dns-audit --json`) → ouvre/ferme les `Recommendation` |
| `health.window` | horaire | agrège sent/delivered/bounce/complaint/delay par fenêtre → alertes §3 du catalogue |
| `webhook.ingest` | temps réel | événements fournisseur → suppression list (hard bounce, plainte), métriques |

Règles d'ouverture/fermeture : voir `references/alerts-catalog.md` §1.

## 7. API exposée (calquée sur Lumail v2)

```
POST   /api/v2/domains                 { domain, region?, provider?, purpose? } → { id, status, dnsRecords[] }
GET    /api/v2/domains                 → liste
GET    /api/v2/domains/:idOrHost       → objet domaine + dnsRecords[] (type, name, value, priority, ttl, purpose, status)
POST   /api/v2/domains/:idOrHost/verify → { status, isVerified, dkimStatus, mailFromStatus, dnsRecords[] }
GET    /api/v2/deliverability/health?sinceDays=30
POST   /api/v2/senders                 { domainId, localPart, displayName, replyTo? }
```
Erreurs : 400 `validation_error` (déjà enregistré, réclamé ailleurs, limite du plan, région
indisponible), 401, 403 permission `domains`, 404.

Un domaine « réclamé ailleurs » : refuser qu'une 2ᵉ organisation enregistre un domaine déjà vérifié
par une autre, sauf preuve de propriété (TXT de vérification propre à l'organisation).

## 8. UI minimale

1. Formulaire : domaine racine + usage → la plateforme propose `mail.` / `news.` et la région.
2. Tableau des records : type · nom (copiable) · valeur (copiable) · statut ● attendu/trouvé.
3. Bouton « Vérifier maintenant » + vérification automatique en arrière-plan.
4. Option « Configurer automatiquement » si le DNS est chez Cloudflare (token API) — `scripts/cloudflare-apply.mjs`.
5. Bandeau d'alertes avec lien vers le guide de chaque `ruleKey`.
6. Avertissement Cloudflare : records en **DNS only** (nuage gris), un CNAME proxifié échoue.

## 9. Ce qu'on ne clone pas

- **Le moteur d'envoi** (MTA, IP, warmup) : on le loue à SES/Resend/etc. Lumail lui-même est une
  surcouche SES (régions eu-central-1, ap-southeast-2, us-west-1) + Cloudflare for SaaS pour les
  domaines web/tracking + Redis pour les garde-fous + QStash/Hatchet pour les files.
- **Le score de confiance exact** (non publié) : reproduire l'esprit (30 jours, bounces, plaintes,
  engagement) suffit.
- **Les inbox placement tests / seed lists** : services tiers (GlockApps, Mailgun Optimize…).
