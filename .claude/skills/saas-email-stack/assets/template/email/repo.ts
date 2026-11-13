// Accès aux données de la brique email, indépendant de l'ORM.
// Le projet fournit une implémentation (voir db/prisma-repo.ts pour Prisma) ;
// les services ne connaissent que cette interface.
import { createHash } from "node:crypto";
import type { DnsMode, DnsRecord, DomainStatus, ProviderId, Stream } from "./types";

/** Normalise puis hache une adresse : on stocke et compare des empreintes, pas des adresses. */
export function emailHash(address: string): string {
  return createHash("sha256").update(address.trim().toLowerCase()).digest("hex");
}

export interface DomainRow {
  id: string;
  tenantId: string;
  name: string;
  rootDomain: string;
  stream: Stream;
  region: string;
  status: DomainStatus;
  dnsMode: DnsMode;
  hostedZoneId: string | null;
  nameServers: string[];
  delegationVerifiedAt: Date | null;
  webhookVerifiedAt: Date | null;
  unsubscribeVerifiedAt: Date | null;
  postmasterConfirmedAt: Date | null;
  senderHubConfirmedAt: Date | null;
  warmupStartedAt: Date | null;
  warmupTargetPerDay: number | null;
  warmupFirstWeekPerDay: number;
  warmupHeldWeeks: number;
  dmarcPolicyObserved: string | null;
  dmarcRuaObserved: boolean;
  createdAt: Date;
}

export interface IdentityRow {
  id: string;
  domainId: string;
  provider: ProviderId;
  providerRef: string;
  status: DomainStatus;
  region: string;
  isPrimary: boolean;
  configurationSet: string | null;
  sesTenantName: string | null;
}

export interface EmailRepo {
  // Domaines
  createDomain(input: Pick<DomainRow, "tenantId" | "name" | "rootDomain" | "stream" | "region" | "dnsMode">): Promise<DomainRow>;
  getDomainByName(name: string): Promise<DomainRow | null>;
  getDomain(id: string): Promise<DomainRow | null>;
  updateDomain(id: string, patch: Partial<DomainRow> & { lastCheckedAt?: Date; nextCheckAt?: Date }): Promise<void>;
  listDomainsToCheck(now: Date, limit: number): Promise<DomainRow[]>;

  upsertIdentity(input: Omit<IdentityRow, "id">): Promise<IdentityRow>;
  listIdentities(domainId: string): Promise<IdentityRow[]>;
  updateIdentity(id: string, patch: Partial<IdentityRow>): Promise<void>;

  replaceRecords(domainId: string, provider: ProviderId | null, records: DnsRecord[]): Promise<void>;
  listRecords(domainId: string): Promise<(DnsRecord & { observed?: string | null })[]>;

  // Envois et événements
  createMessage(input: { tenantId: string; domainId: string | null; stream: Stream; provider: ProviderId; toHash: string; subject: string; idempotencyKey?: string; campaignId?: string }): Promise<{ id: string }>;
  markMessageSent(id: string, providerMessageId: string): Promise<void>;
  markMessageStatus(id: string, status: string): Promise<void>;
  findMessageByProviderId(providerMessageId: string): Promise<{ id: string; tenantId: string; domainId: string | null } | null>;
  /** Auto-test des webhooks : a-t-on reçu un bounce et une plainte des simulateurs pour ce domaine ? */
  simulatorEventsSeen(domainId: string, recipientHashes: string[]): Promise<{ bounce: boolean; complaint: boolean }>;
  /** Insère l'événement ; renvoie false s'il existait déjà (providerEventId unique). */
  insertEvent(input: { messageId?: string; tenantId?: string; provider: ProviderId; providerEventId: string; type: string; recipientHash: string; detail?: string; occurredAt: Date }): Promise<boolean>;

  // Suppression
  isSuppressed(input: { tenantId: string; emailHash: string; stream: Stream }): Promise<{ reason: string } | null>;
  suppress(input: { scope: "global" | string; emailHash: string; streamScope: "all" | "marketing" | "transactional"; reason: "HARD_BOUNCE" | "COMPLAINT" | "UNSUBSCRIBE" | "MANUAL"; detail?: string }): Promise<void>;

  // Warm-up : incrément atomique, renvoie le total du jour APRÈS incrément
  incrementDailyCounter(domainId: string, day: string): Promise<number>;
}
