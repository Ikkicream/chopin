---
name: saas-email-stack
description: Ajoute la brique email complète à un projet SaaS multi-comptes (multi-tenant) — Resend pour le transactionnel, Amazon SES avec un tenant SES par client pour le marketing, domaines d'envoi des clients branchés par délégation de sous-domaine (NS vers Route 53) ou par records, webhooks bounces/plaintes signés, désinscription one-click RFC 8058, liste de suppression, garde-fous, warm-up et portes de mise en service bloquantes. Fournit un gabarit TypeScript testé (Next.js, Prisma, adaptable), la doc technique et le guide client de délégation. À utiliser dès qu'on branche ou refond l'envoi d'emails d'une plateforme, qu'on veut permettre à des clients d'envoyer depuis leur propre domaine, qu'on parle de Resend, SES, multi-tenant, plateforme marketing, routage d'emails, onboarding de domaine client ou délégation DNS — même si l'utilisateur ne dit pas « stack ».
---

# Brique email SaaS multi-tenant (Resend + SES + délégation)

Ce skill installe dans un projet existant une brique email où **chaque client de la plateforme
envoie depuis son propre domaine**, isolé des autres, avec les règles de délivrabilité appliquées
par le code et pas seulement par une checklist.

| Flux | Fournisseur | Pourquoi |
|---|---|---|
| Transactionnel (codes, factures, invitations) | **Resend** | mise en route rapide, SDK, faible volume donc faible risque |
| Marketing des clients | **Amazon SES** + 1 tenant SES par client | isolation de réputation, suppression et pause par client ; coût |
| DNS des clients | **délégation NS** du sous-domaine vers Route 53 (ou records copiés) | le client agit une fois ; la plateforme gère DKIM, MAIL FROM, DMARC, tracking et peut changer de fournisseur |

Un compte Resend partage entre tous les clients le débit (10 req/s), la liste de suppression, les
désinscriptions et des seuils de compte : un seul client à 4 % de bounces peut suspendre tout le
monde. C'est la raison du découpage — détail dans `references/architecture.md`.

Le skill compagnon **`email-domain-setup`** (audit DNS, plan DNS, `golive-check`) est utilisé pour
les vérifications ; ses scripts utiles sont copiés dans `scripts/` pour que ce skill soit autonome.

## Déroulé dans un projet

**1. Reconnaissance** (`references/integration-playbook.md` §1) : framework, ORM, modèle
d'organisation, file de jobs, Redis, envois existants, templates. Résumer en quelques lignes à
l'utilisateur avant d'écrire du code. Si plusieurs projets sont connectés, faire ce relevé pour
chacun : la brique est la même, l'adaptation change.

**2. Décisions** : proposer les valeurs par défaut du playbook §2 (régions UE `eu-west-1` Resend /
`eu-west-3` SES, `news.` marketing, `mail.` transactionnel, délégation NS). Les régions et le nom du
Return-Path Resend sont **définitifs** : les faire valider avant de créer quoi que ce soit.

**3. Copier et adapter le gabarit** `assets/template/` :

| Fichier | Rôle | Adaptation |
|---|---|---|
| `db/schema.prisma` | tables `Email*` | fusionner, relier `tenantId` au modèle d'organisation, migrer (Drizzle : traduire) |
| `email/types.ts`, `repo.ts` | contrats | aucune |
| `email/prisma-repo.ts` | accès données | réécrire avec l'ORM du projet si ce n'est pas Prisma |
| `email/providers/resend.ts`, `ses.ts` | adaptateurs | aucune |
| `email/router.ts`, `send.ts` | routage + pipeline | politique flux → fournisseur si besoin |
| `email/compliance/*` | désinscription, garde-fous, mise en service, warm-up | aucune |
| `email/events.ts`, `webhooks/*` | bounces, plaintes, auto-test, état des tenants SES | aucune |
| `email/domains/*` | onboarding, Route 53, vérifications DNS | aucune |
| `email/deps.ts` | câblage | client Prisma/Redis du projet |
| `routes/nextjs/*` | routes API et cron | déplacer selon le framework (Hono, Express, Nuxt : mêmes handlers) |
| `email/email.test.ts` | tests | adapter l'import si jest |

Dépendances : `resend`, `@aws-sdk/client-sesv2`, `@aws-sdk/client-route-53`, `svix`.
Le gabarit compile en TypeScript strict et ses tests passent avec `resend` 6.32, AWS SDK v3,
Prisma 6 et vitest 3 : si le typage casse après adaptation, c'est l'adaptation qu'il faut revoir.

**4. Configuration** (variables à déclarer dans `.env.example` et le gestionnaire de secrets) :

```
RESEND_API_KEY=re_…                      RESEND_WEBHOOK_SECRET=whsec_…
AWS_ACCOUNT_ID=…                         SES_DEFAULT_REGION=eu-west-3
SES_CONFIG_SET_PREFIX=platform           SES_EVENTS_TOPIC_ARN=arn:aws:sns:eu-west-3:…:platform-ses-events
ROUTE53_DELEGATION_SET_IDS=N…,N…         EMAIL_UNSUBSCRIBE_SECRET=<32+ octets aléatoires>
EMAIL_PUBLIC_BASE_URL=https://app…       EMAIL_REQUIRE_EU_REGION=true
CRON_SECRET=…                            (+ identifiants AWS par rôle IAM, pas de clés longues)
```
Installation AWS initiale (sandbox, topic SNS, configuration sets partagés, règle EventBridge, IAM) :
`references/ses.md` §1. Jeu de serveurs réutilisable Route 53 : `references/delegation.md` §2.
Ces commandes créent des ressources facturées : les montrer et laisser l'utilisateur les lancer.

**5. Brancher dans l'ordre** : webhooks et désinscription **avant** tout envoi réel ; puis onboarding
des domaines ; puis migration des appels existants vers `sendEmail()` (`integration-playbook.md` §4).

**6. Vérifier** (`integration-playbook.md` §5) :
```bash
npx tsc --noEmit && npx vitest run email
EMAIL_UNSUBSCRIBE_SECRET=… node scripts/selftest.mjs --base-url http://localhost:3000
node scripts/golive-check.mjs --domain news.client.com --provider ses --expect-region eu \
  --webhook-url https://…/api/email/webhooks/ses --unsubscribe-url https://…/api/email/unsubscribe/TEST
```

## Les six conditions avant le premier envoi marketing

Elles sont **appliquées par `send.ts`** (refus `DOMAIN_NOT_READY` tant qu'il en manque une) et
vérifiables de l'extérieur par `golive-check.mjs` :

1. domaine créé dans la **région UE** avant de poser le DNS ;
2. sous-domaine dédié (`news.`), SPF/DKIM du fournisseur vérifiés, **DMARC `p=none` + `rua` lu**, durci
   en `quarantine` après le warm-up ;
3. webhooks **bounces et plaintes** branchés et signés — validés par l'auto-test vers les simulateurs ;
4. **`List-Unsubscribe` + `List-Unsubscribe-Post`**, endpoint POST qui désinscrit sans page ni redirection ;
5. **Google Postmaster Tools et Yahoo Sender Hub** inscrits avant le premier envoi ;
6. **warm-up** : 300–500/jour la 1ʳᵉ semaine, contacts les plus engagés d'abord, doublement hebdomadaire
   si bounces < 2 % et plaintes < 0,1 %.

Détail, champs et procédure : `references/golive-ops.md`.

## Accompagner un client (délégation)

1. `POST /api/email/domains` → identités créées (région figée), zone Route 53 créée **et remplie** avant
   de donner les NS (sinon cache négatif de 15 min).
2. Remettre `assets/client-guide-delegation.md` rempli (4 NS, piège du nom saisi deux fois, pas de DS).
3. Le cron vérifie la délégation puis le fournisseur ; zone non déléguée au bout de 7 jours → supprimée.
4. Auto-test webhooks, test one-click, confirmations Postmaster / Sender Hub, démarrage du warm-up.
5. Départ d'un client : ne jamais supprimer une zone dont les NS pointent encore vers nous
   (`references/delegation.md` §6).

## Ce qu'il faut rendre

Pour chaque projet : relevé de reconnaissance, fichiers créés/modifiés, migration, variables à
renseigner, commandes d'infrastructure à lancer par l'utilisateur, résultat réel des vérifications
(typage, tests, selftest) et ce qui n'a pas pu être testé (souvent : envoi réel, AWS non configuré).

## Références

| Fichier | Quand le lire |
|---|---|
| `references/integration-playbook.md` | à chaque intégration dans un projet |
| `references/architecture.md` | justifier les choix, schéma, isolation, quotas, coûts |
| `references/resend.md` | API Resend, limites, webhooks, clés restreintes, OAuth |
| `references/ses.md` | installation AWS, tenants SES, événements, IAM |
| `references/delegation.md` | Route 53, marque blanche, vérification, DNSSEC/CAA, Entri, Domain Connect |
| `references/golive-ops.md` | six conditions, warm-up, DMARC, surveillance, incidents |
| `assets/client-guide-delegation.md` | guide à remettre au client |
| `DOC-TECHNIQUE.md` | document d'équipe complet (à copier dans `docs/` du projet) |
