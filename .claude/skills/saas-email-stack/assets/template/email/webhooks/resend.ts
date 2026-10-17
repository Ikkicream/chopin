// Webhook Resend → événements normalisés.
// Un seul endpoint pour toute la plateforme (Resend en limite le nombre par plan) :
// le tenant est retrouvé grâce au tag `tenant` posé à l'envoi (data.tags est un objet).
// Signature Svix vérifiée sur le CORPS BRUT ; dédoublonnage sur l'en-tête svix-id.
// On vérifie avec `svix` directement : pas besoin de clé d'API Resend pour valider une signature
// (instancier le client Resend sans clé lève une exception au chargement du module).
import { Webhook } from "svix";
import type { DeliveryEvent, DeliveryEventType } from "../types";

export class InvalidSignatureError extends Error {}

type ResendEvent = {
  type: string;
  created_at: string;
  data: { email_id?: string; to?: string[]; tags?: Record<string, string>; bounce?: { type: string; subType: string; message: string }; failed?: { reason: string } };
};

export function verifyResendWebhook(rawBody: string, headers: Headers): ResendEvent {
  const id = headers.get("svix-id"), timestamp = headers.get("svix-timestamp"), signature = headers.get("svix-signature");
  if (!id || !timestamp || !signature) throw new InvalidSignatureError("En-têtes Svix manquants");
  try {
    // Contrôle aussi la fraîcheur de l'horodatage (protection contre le rejeu). Selon la version
    // de svix, verify() ne renvoie rien : on parse le corps nous-mêmes, APRÈS vérification.
    new Webhook(process.env.RESEND_WEBHOOK_SECRET!).verify(rawBody, {
      "svix-id": id, "svix-timestamp": timestamp, "svix-signature": signature,
    });
  } catch {
    throw new InvalidSignatureError("Signature Resend invalide");
  }
  return JSON.parse(rawBody) as ResendEvent;
}

export function normalizeResendEvent(evt: ResendEvent, svixId: string): DeliveryEvent[] {
  const d = evt.data;
  if (!d?.email_id) return []; // domain.*, contact.*… : traités ailleurs si besoin
  let type: DeliveryEventType | null = null;
  let detail: string | undefined;
  switch (evt.type) {
    case "email.sent": type = "sent"; break;
    case "email.delivered": type = "delivered"; break;
    case "email.delivery_delayed": type = "delayed"; break;
    case "email.bounced":
      type = d.bounce?.type === "Permanent" ? "bounced_hard" : "bounced_soft";
      detail = [d.bounce?.subType, d.bounce?.message].filter(Boolean).join(" — ");
      break;
    case "email.complained": type = "complained"; break;
    case "email.opened": type = "opened"; break;
    case "email.clicked": type = "clicked"; break;
    case "email.failed": type = "failed"; detail = d.failed?.reason; break;
    // Déjà sur la liste de suppression du compte Resend : on aligne notre propre liste.
    case "email.suppressed": type = "bounced_hard"; detail = "OnAccountSuppressionList"; break;
  }
  if (!type) return [];
  return (d.to ?? []).map((recipient, i) => ({
    provider: "resend" as const,
    providerMessageId: d.email_id!,
    providerEventId: (d.to?.length ?? 0) > 1 ? `${svixId}:${i}` : svixId,
    type: type!,
    recipient,
    occurredAt: new Date(evt.created_at),
    tenantId: d.tags?.tenant,
    detail,
  }));
}
