// Traitement des événements normalisés (Resend ou SES) : journal, suppression,
// cooldown destinataire, et validation des webhooks pour la mise en service.
//
// Les webhooks sont livrés « au moins une fois » et dans le désordre : tout ici
// est idempotent (providerEventId unique) et ne dépend pas de l'ordre d'arrivée.
import { startRecipientCooldown, type WindowStore } from "./compliance/guards";
import { emailHash, type EmailRepo } from "./repo";
import { SIMULATOR_RECIPIENTS } from "./send";
import type { DeliveryEvent } from "./types";

const COOLDOWN_DETAIL = /mailbox ?full|MailboxFull|quota|throttl|rate ?limit|too many/i;

export async function processDeliveryEvent(event: DeliveryEvent, deps: { repo: EmailRepo; windows: WindowStore }) {
  const { repo } = deps;
  const message = await repo.findMessageByProviderId(event.providerMessageId);
  const tenantId = event.tenantId ?? message?.tenantId;
  const recipientHash = emailHash(event.recipient);

  const isNew = await repo.insertEvent({
    messageId: message?.id, tenantId, provider: event.provider, providerEventId: event.providerEventId,
    type: event.type, recipientHash, detail: event.detail, occurredAt: event.occurredAt,
  });
  if (!isNew) return { duplicate: true };

  switch (event.type) {
    case "bounced_hard":
      // Adresse inexistante : invalide pour TOUS les tenants de la plateforme.
      if (!SIMULATOR_RECIPIENTS.has(event.recipient.toLowerCase())) {
        await repo.suppress({ scope: "global", emailHash: recipientHash, streamScope: "all", reason: "HARD_BOUNCE", detail: event.detail });
      }
      if (message) await repo.markMessageStatus(message.id, "bounced");
      break;
    case "bounced_soft":
      if (event.detail && COOLDOWN_DETAIL.test(event.detail)) await startRecipientCooldown(event.recipient, deps.windows);
      break;
    case "complained":
      // Plainte : on n'écrit plus jamais à cette personne pour CE tenant, quel que soit le flux.
      if (tenantId && !SIMULATOR_RECIPIENTS.has(event.recipient.toLowerCase())) {
        await repo.suppress({ scope: tenantId, emailHash: recipientHash, streamScope: "all", reason: "COMPLAINT", detail: event.detail });
      }
      if (message) await repo.markMessageStatus(message.id, "complained");
      break;
    case "unsubscribed":
      if (tenantId) await repo.suppress({ scope: tenantId, emailHash: recipientHash, streamScope: "marketing", reason: "UNSUBSCRIBE" });
      break;
    case "delivered":
      if (message) await repo.markMessageStatus(message.id, "delivered");
      break;
    case "failed":
      if (message) await repo.markMessageStatus(message.id, "failed");
      break;
  }

  // Auto-test : un bounce ET une plainte signés reçus des simulateurs → webhooks validés.
  if (message?.domainId && SIMULATOR_RECIPIENTS.has(event.recipient.toLowerCase()) && (event.type === "bounced_hard" || event.type === "complained")) {
    const seen = await repo.simulatorEventsSeen(message.domainId, [...SIMULATOR_RECIPIENTS].map(emailHash));
    if (seen.bounce && seen.complaint) await repo.updateDomain(message.domainId, { webhookVerifiedAt: new Date() });
  }
  return { duplicate: false };
}
