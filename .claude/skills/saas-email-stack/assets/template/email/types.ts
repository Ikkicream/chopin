// Types partagés de la brique email multi-tenant.
// Aucun import de fournisseur ici : tout le reste du code dépend de ces types,
// et seuls les adaptateurs (providers/*) connaissent Resend ou SES.

export type ProviderId = "resend" | "ses";
export type Stream = "transactional" | "marketing";

/** Mode de branchement du DNS du client. */
export type DnsMode =
  | "records"     // le client copie les records chez son hébergeur
  | "delegated"   // le client a délégué le sous-domaine (NS) à notre zone Route 53
  | "api";        // on écrit chez son hébergeur via son token (Cloudflare…)

export type DomainStatus = "not_started" | "pending" | "verified" | "temporary_failure" | "failed";

export interface DnsRecord {
  purpose: "dkim" | "spf" | "mail-from" | "dmarc" | "tracking" | "verification" | "aprf" | "other";
  type: "TXT" | "CNAME" | "MX" | "NS";
  name: string;          // FQDN, sans point final
  value: string;
  priority?: number;
  status?: "pending" | "verified" | "failed";
}

/** Vue normalisée d'un domaine chez un fournisseur. */
export interface ProviderDomain {
  provider: ProviderId;
  ref: string;           // id Resend, ou nom de l'identité SES
  name: string;
  region: string;
  status: DomainStatus;
  records: DnsRecord[];
}

export interface OutboundEmail {
  tenantId: string;
  stream: Stream;
  from: { email: string; name?: string };
  to: string;            // un destinataire par message : indispensable pour le one-click et le suivi
  replyTo?: string;
  subject: string;
  html: string;
  text?: string;
  headers?: Record<string, string>;
  tags?: Record<string, string>;   // tenant, campagne, template… (renvoyés dans les événements)
  idempotencyKey?: string;
}

export interface SendResult {
  provider: ProviderId;
  providerMessageId: string;
}

/** Événement de délivrabilité normalisé, quel que soit le fournisseur. */
export type DeliveryEventType =
  | "sent" | "delivered" | "delayed" | "bounced_hard" | "bounced_soft"
  | "complained" | "opened" | "clicked" | "failed" | "unsubscribed";

export interface DeliveryEvent {
  provider: ProviderId;
  providerMessageId: string;
  providerEventId: string;   // pour dédupliquer (webhooks livrés au moins une fois)
  type: DeliveryEventType;
  recipient: string;
  occurredAt: Date;
  tenantId?: string;         // lu dans les tags du message
  detail?: string;           // sous-type de bounce, type de plainte…
}

export interface EmailProvider {
  id: ProviderId;
  createDomain(input: { name: string; region: string; returnPathLabel?: string; tenantId: string }): Promise<ProviderDomain>;
  getDomain(ref: string): Promise<ProviderDomain>;
  verifyDomain(ref: string): Promise<ProviderDomain>;
  deleteDomain(ref: string): Promise<void>;
  send(email: OutboundEmail, ctx: { region?: string; configurationSet?: string; sesTenant?: string }): Promise<SendResult>;
}

export class EmailBlockedError extends Error {
  constructor(public code: string, message: string, public retryAfterSeconds?: number) {
    super(message);
  }
}
