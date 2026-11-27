// Pipeline d'envoi unique pour tous les flux et tous les fournisseurs.
// Ordre volontaire : les contrôles les moins coûteux et les plus définitifs d'abord.
//
//   1. route (domaine possédé par le tenant, identité vérifiée)
//   2. portes de mise en service (marketing : les six conditions)
//   3. liste de suppression (globale + tenant)
//   4. garde-fous par destinataire (5/10 min, 20/24 h)
//   5. plafond de warm-up du domaine (marketing)
//   6. journal du message (idempotence)
//   7. en-têtes : List-Unsubscribe one-click (marketing), tags de corrélation
//   8. envoi, avec bascule sur l'autre fournisseur si l'identité est en cause
import { evaluateGoLive, warmupDailyCap } from "./compliance/golive";
import { checkRecipientGuards, type WindowStore } from "./compliance/guards";
import { listUnsubscribeHeaders } from "./compliance/unsubscribe";
import { emailHash, type EmailRepo } from "./repo";
import { isIdentityFailure, resolveRoute, type RoutingPolicy } from "./router";
import { EmailBlockedError, type EmailProvider, type OutboundEmail, type ProviderId } from "./types";

/** Adresses de test des fournisseurs : autorisées avant la mise en service (auto-test des webhooks). */
export const SIMULATOR_RECIPIENTS = new Set([
  "delivered@resend.dev", "bounced@resend.dev", "complained@resend.dev",
  "success@simulator.amazonses.com", "bounce@simulator.amazonses.com", "complaint@simulator.amazonses.com",
  "ooto@simulator.amazonses.com", "suppressionlist@simulator.amazonses.com",
]);

export interface SendDeps {
  repo: EmailRepo;
  providers: Partial<Record<ProviderId, EmailProvider>>;
  windows: WindowStore;
  config: {
    unsubscribeSecret: string;
    publicBaseUrl: string;      // https://app.plateforme.com — sert l'endpoint one-click
    requireEuRegion?: boolean;
    policy?: RoutingPolicy;
  };
}

export async function sendEmail(deps: SendDeps, email: OutboundEmail) {
  const { repo, config } = deps;
  const isSimulator = SIMULATOR_RECIPIENTS.has(email.to.toLowerCase());

  // 1. Route
  const route = await resolveRoute(repo, { tenantId: email.tenantId, stream: email.stream, fromEmail: email.from.email }, config.policy);

  // 2. Mise en service
  if (!isSimulator) {
    const gate = evaluateGoLive(route.domain, route.identities, email.stream, { requireEu: config.requireEuRegion });
    if (!gate.ready) {
      const missing = gate.items.filter((i) => !i.ok).map((i) => `${i.key}: ${i.message}`).join(" · ");
      throw new EmailBlockedError("DOMAIN_NOT_READY", `Mise en service incomplète pour ${route.domain.name} — ${missing}`);
    }
  }

  // 3. Suppression
  const h = emailHash(email.to);
  const suppressed = await repo.isSuppressed({ tenantId: email.tenantId, emailHash: h, stream: email.stream });
  if (suppressed) throw new EmailBlockedError("RECIPIENT_SUPPRESSED", `Destinataire supprimé (${suppressed.reason})`);

  // 4. Garde-fous destinataire
  if (!isSimulator) await checkRecipientGuards(email.to, deps.windows);

  // 5. Warm-up
  if (email.stream === "marketing" && !isSimulator) {
    const cap = warmupDailyCap(route.domain);
    if (cap !== null) {
      const today = new Date().toISOString().slice(0, 10);
      const n = await repo.incrementDailyCounter(route.domain.id, today);
      if (n > cap) {
        const midnight = new Date(`${today}T00:00:00Z`).getTime() + 86_400_000;
        throw new EmailBlockedError("WARMUP_CAP_REACHED", `Plafond de warm-up atteint (${cap}/jour) pour ${route.domain.name}`, Math.ceil((midnight - Date.now()) / 1000));
      }
    }
  }

  // 6. Journal
  const message = await repo.createMessage({
    tenantId: email.tenantId, domainId: route.domain.id, stream: email.stream, provider: route.primary.provider,
    toHash: h, subject: email.subject, idempotencyKey: email.idempotencyKey,
  });

  // 7. En-têtes et tags
  const headers: Record<string, string> = { ...(email.headers ?? {}) };
  if (email.stream === "marketing") {
    Object.assign(headers, listUnsubscribeHeaders({
      tenantId: email.tenantId, recipient: email.to, stream: email.stream, messageId: message.id, baseUrl: config.publicBaseUrl,
    }, config.unsubscribeSecret));
  }
  const tags = { ...(email.tags ?? {}), tenant: email.tenantId, message: message.id, stream: email.stream };
  const outbound: OutboundEmail = { ...email, headers, tags, idempotencyKey: email.idempotencyKey ?? message.id };

  // 8. Envoi + bascule
  let lastError: unknown = new EmailBlockedError("NO_PROVIDER", "Aucun fournisseur configuré pour ce domaine");
  for (const identity of [route.primary, ...route.fallbacks]) {
    const provider = deps.providers[identity.provider];
    if (!provider) continue;
    try {
      const res = await provider.send(outbound, { region: identity.region, configurationSet: identity.configurationSet ?? undefined, sesTenant: identity.sesTenantName ?? undefined });
      await repo.markMessageSent(message.id, res.providerMessageId);
      return { messageId: message.id, ...res };
    } catch (err) {
      lastError = err;
      // Seul un échec d'identité justifie de tenter le fournisseur suivant (même From,
      // autre DKIM / Return-Path). Contenu invalide, quota ou débit : on remonte l'erreur.
      if (!isIdentityFailure(err)) break;
    }
  }
  await repo.markMessageStatus(message.id, "failed");
  throw lastError;
}
