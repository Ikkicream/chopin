# Brancher la brique email dans un projet existant

À suivre chaque fois que la stack est ajoutée à un nouveau projet. L'objectif est d'adapter le
gabarit (`assets/template/`) aux conventions du projet, pas l'inverse : on garde son ORM, sa
file de jobs, son système d'organisations et son style de code.

## Sommaire
1. Reconnaissance du projet
2. Décisions à prendre (et valeurs par défaut)
3. Ordre d'implémentation
4. Migration des envois existants
5. Vérification avant de rendre la main

---

## 1. Reconnaissance (lire avant d'écrire une ligne)

| Question | Où regarder | Impact |
|---|---|---|
| Framework et runtime | `package.json`, `next.config.*`, `nuxt.config.*`, `src/server`, `vercel.ts` | emplacement des routes (`app/api/...` pour Next.js App Router, `server/api` Nuxt, routeur Hono/Express) |
| ORM / base | `prisma/schema.prisma`, `drizzle.config.*`, `supabase/` | traduction de `db/schema.prisma` et implémentation de `EmailRepo` |
| Modèle multi-tenant | modèles `Organization`, `Workspace`, `Team`, `Account` | ce que `tenantId` référence ; contrôle d'accès des routes domaines |
| File de jobs | BullMQ, Inngest, Trigger.dev, QStash, Vercel Queues, cron | envoi des campagnes, polling des domaines, job de santé hebdo |
| Redis | `REDIS_URL`, `@upstash/redis`, `ioredis` | `WindowStore` des garde-fous (sinon : table SQL ou mémoire en dev) |
| Envois existants | `grep -r "resend\|nodemailer\|@aws-sdk/client-ses\|sendgrid\|postmark"` | appels à remplacer par `sendEmail()` |
| Templates | `emails/`, `react-email`, MJML, handlebars | le rendu reste celui du projet ; la brique ne reçoit que `html`/`text` |
| Secrets | `.env.example`, `vercel env`, Doppler, SST | où déclarer les variables ci-dessous |

Rapporter ce relevé à l'utilisateur en 5–10 lignes avant d'implémenter.

## 2. Décisions (proposer ces valeurs par défaut)

| Décision | Défaut | Alternative |
|---|---|---|
| Flux → fournisseur | transactionnel → Resend, marketing → SES | tout Resend (petit volume), tout SES (coût) |
| Région | UE : Resend `eu-west-1`, SES `eu-west-3` (Paris) ou `eu-central-1` | — (figée à la création) |
| Sous-domaines clients | `news.<client>` marketing, `mail.<client>` transactionnel | un seul sous-domaine si un seul flux |
| Branchement DNS | délégation NS vers Route 53 (zone hébergée par sous-domaine) | records copiés ; écriture via token Cloudflare |
| Domaine de la plateforme | `mail.<plateforme>` sur Resend pour les emails système | — |
| Suivi ouvertures/clics | désactivé sur le transactionnel, activé sur le marketing avec domaine de tracking client | — |

## 3. Ordre d'implémentation

1. **Variables d'environnement** (voir `SKILL.md` §Configuration) et `.env.example`.
2. **Schéma** : traduire `db/schema.prisma` (préfixe `Email*`, relation `tenantId` → modèle d'org), migration.
3. **`EmailRepo`** : implémentation avec l'ORM du projet (`db/prisma-repo.ts` comme modèle).
4. **Adaptateurs** `providers/resend.ts` et `providers/ses.ts` (dépendances : `resend`, `@aws-sdk/client-sesv2`, `@aws-sdk/client-route-53`, `svix`).
5. **Pipeline** `send.ts` + `compliance/*` + `router.ts` (copie quasi telle quelle).
6. **Routes webhooks** (Resend signé Svix, SES via SNS signé) → `events.ts`. À brancher **avant** tout envoi réel.
7. **Routes désinscription** : `POST /api/email/unsubscribe/[token]` (one-click, 200 sans redirection) et page `GET /unsubscribe/[token]` pour le lien visible.
8. **Onboarding domaine** : routes `POST /api/email/domains`, `GET /api/email/domains/[id]`, `POST /api/email/domains/[id]/verify`, actions de mise en service (confirmations Postmaster / Sender Hub, démarrage du warm-up).
9. **Jobs** : polling des domaines (backoff 1 min → 1 h, 72 h max), santé hebdomadaire (retenue du warm-up), audit DNS quotidien.
10. **UI** : tableau des records (copier, statut attendu/trouvé), instructions de délégation, checklist de mise en service.

## 4. Migration des envois existants

- Remplacer chaque appel direct (`resend.emails.send`, `transporter.sendMail`, `SendEmailCommand`)
  par `sendEmail(deps, { tenantId, stream, from, to, subject, html, text })`.
- Les emails système de la plateforme (invitations, reset) utilisent le tenant « plateforme » et le
  domaine `mail.<plateforme>` : même pipeline, même suppression.
- Un destinataire par appel : les envois groupés passent par la file (un job par destinataire ou
  `emails.batch` Resend par lots de 100 sans pièces jointes).
- Conserver les templates du projet ; ajouter dans le pied de page marketing la phrase « vous
  recevez cet email car… », l'adresse postale et le lien `unsubscribeLink()`.

## 5. Vérification avant de rendre la main

```bash
npx tsc --noEmit                                  # typage
npm test -- email                                 # tests unitaires fournis (jetons, portes, warm-up)
node scripts/selftest.mjs --base-url http://localhost:3000   # webhook non signé refusé, one-click 200
```
Puis, sur un domaine de test réel :
1. créer le domaine (région UE) → records ou délégation → `verify` ;
2. envoyer vers `bounced@resend.dev` / `complained@resend.dev` (ou les simulateurs SES) et constater
   la suppression + `webhookVerifiedAt` ;
3. `node ../email-domain-setup/scripts/golive-check.mjs …` → **GO** attendu.

Rendre compte : fichiers créés/modifiés, migration, variables à renseigner, ce qui a été testé
réellement et ce qui ne l'a pas été.
