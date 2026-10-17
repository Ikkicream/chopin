// Webhook SES (via un topic SNS en HTTPS) → événements normalisés.
//
// Un seul topic SNS reçoit :
//   - les événements d'envoi (destination SNS des configuration sets partagés) ;
//   - les changements d'état des tenants SES (règle EventBridge `source: aws.ses`,
//     « Sending Status Disabled/Enabled » → même topic) : AWS peut mettre un client
//     en pause tout seul (politique de réputation standard/strict).
//
// Vérification de signature SNS faite ici sans dépendance : certificat téléchargé
// uniquement depuis sns.<région>.amazonaws.com, SignatureVersion 1 (SHA1) ou 2 (SHA256),
// et TopicArn comparé à celui attendu. Ne PAS activer « raw message delivery » sur
// l'abonnement : le corps brut n'est pas signé.
import { createVerify } from "node:crypto";
import type { DeliveryEvent, DeliveryEventType } from "../types";
import { InvalidSignatureError } from "./resend";

type SnsMessage = {
  Type: "Notification" | "SubscriptionConfirmation" | "UnsubscribeConfirmation";
  MessageId: string; TopicArn: string; Message: string; Timestamp: string;
  Subject?: string; Token?: string; SubscribeURL?: string;
  SignatureVersion: "1" | "2"; Signature: string; SigningCertURL: string;
};

const certCache = new Map<string, string>();

async function fetchCert(url: string): Promise<string> {
  const u = new URL(url);
  if (u.protocol !== "https:" || !/^sns\.[a-z0-9-]+\.amazonaws\.com(\.cn)?$/.test(u.hostname) || !u.pathname.endsWith(".pem")) {
    throw new InvalidSignatureError(`Certificat SNS refusé : ${url}`);
  }
  if (!certCache.has(url)) certCache.set(url, await (await fetch(url)).text());
  return certCache.get(url)!;
}

function stringToSign(m: SnsMessage): string {
  const keys = m.Type === "Notification"
    ? ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]
    : ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"];
  return keys.filter((k) => (m as Record<string, unknown>)[k] !== undefined).map((k) => `${k}\n${(m as Record<string, string>)[k]}\n`).join("");
}

export async function verifySnsMessage(rawBody: string): Promise<SnsMessage> {
  let m: SnsMessage;
  try { m = JSON.parse(rawBody); } catch { throw new InvalidSignatureError("Corps SNS illisible"); }
  if (m.TopicArn !== process.env.SES_EVENTS_TOPIC_ARN) throw new InvalidSignatureError(`Topic inattendu : ${m.TopicArn}`);
  const verifier = createVerify(m.SignatureVersion === "2" ? "RSA-SHA256" : "RSA-SHA1");
  verifier.update(stringToSign(m), "utf8");
  if (!verifier.verify(await fetchCert(m.SigningCertURL), m.Signature, "base64")) throw new InvalidSignatureError("Signature SNS invalide");
  // Rejeu : au-delà de 24 h on refuse (les nouveaux essais SNS arrivent bien avant) ; le
  // dédoublonnage sur MessageId couvre les redistributions normales.
  if (Date.now() - new Date(m.Timestamp).getTime() > 86_400_000) throw new InvalidSignatureError("Message SNS trop ancien");
  return m;
}

/** À appeler une fois après vérification : confirme l'abonnement HTTPS au topic. */
export async function confirmSubscription(m: SnsMessage) {
  if (m.Type === "SubscriptionConfirmation" && m.SubscribeURL) await fetch(m.SubscribeURL);
}

type SesEvent = {
  eventType: string;
  mail: { messageId: string; timestamp: string; destination: string[]; tags?: Record<string, string[]> };
  bounce?: { bounceType: string; bounceSubType: string; bouncedRecipients: { emailAddress: string; diagnosticCode?: string }[]; timestamp: string };
  complaint?: { complainedRecipients: { emailAddress: string }[]; complaintFeedbackType?: string; timestamp: string };
  delivery?: { recipients: string[]; timestamp: string };
  deliveryDelay?: { delayType: string; delayedRecipients: { emailAddress: string }[]; timestamp: string };
  reject?: { reason: string };
};

export type TenantStatusEvent = { kind: "tenant-status"; tenantArn: string; status: "ENABLED" | "DISABLED" | "REINSTATED"; origin?: string };

export function normalizeSesNotification(m: SnsMessage): { deliveries: DeliveryEvent[]; tenantStatus?: TenantStatusEvent } {
  const payload = JSON.parse(m.Message);

  // Changement d'état d'un tenant SES (EventBridge → SNS).
  if (payload.source === "aws.ses" && /Sending Status/i.test(payload["detail-type"] ?? "")) {
    return {
      deliveries: [],
      tenantStatus: { kind: "tenant-status", tenantArn: payload.resources?.[0], status: payload.detail?.data?.record?.status, origin: payload.detail?.data?.origin },
    };
  }

  const e: SesEvent = payload.eventType ? payload : payload.detail; // SNS direct ou EventBridge
  if (!e?.eventType) return { deliveries: [] };
  const tenantId = e.mail.tags?.tenant?.[0];
  const base = { provider: "ses" as const, providerMessageId: e.mail.messageId, tenantId };
  const mk = (type: DeliveryEventType, recipient: string, at: string, detail?: string, i = 0): DeliveryEvent =>
    ({ ...base, providerEventId: `${m.MessageId}:${i}`, type, recipient, occurredAt: new Date(at), detail });

  switch (e.eventType) {
    case "Bounce": {
      // Permanent = adresse invalide ; Transient (MailboxFull…) = réessayable ; Undetermined = prudence (soft).
      const hard = e.bounce!.bounceType === "Permanent";
      return { deliveries: e.bounce!.bouncedRecipients.map((r, i) => mk(hard ? "bounced_hard" : "bounced_soft", r.emailAddress, e.bounce!.timestamp, `${e.bounce!.bounceSubType} ${r.diagnosticCode ?? ""}`.trim(), i)) };
    }
    case "Complaint":
      return { deliveries: e.complaint!.complainedRecipients.map((r, i) => mk("complained", r.emailAddress, e.complaint!.timestamp, e.complaint!.complaintFeedbackType, i)) };
    case "Delivery":
      return { deliveries: e.delivery!.recipients.map((r, i) => mk("delivered", r, e.delivery!.timestamp, undefined, i)) };
    case "DeliveryDelay":
      return { deliveries: e.deliveryDelay!.delayedRecipients.map((r, i) => mk("delayed", r.emailAddress, e.deliveryDelay!.timestamp, e.deliveryDelay!.delayType, i)) };
    case "Reject":
    case "Rendering Failure":
      return { deliveries: e.mail.destination.map((r, i) => mk("failed", r, e.mail.timestamp, e.reject?.reason ?? e.eventType, i)) };
    case "Send":
      return { deliveries: e.mail.destination.map((r, i) => mk("sent", r, e.mail.timestamp, undefined, i)) };
    default:
      return { deliveries: [] };
  }
}
