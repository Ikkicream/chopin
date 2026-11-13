// Implémentation Prisma de EmailRepo. Modèle pour Drizzle / Supabase : mêmes requêtes.
// Les enums Prisma sont en MAJUSCULES, les types de la brique en minuscules : on convertit ici.
import { Prisma, type EmailDnsMode, type EmailStream, type PrismaClient } from "@prisma/client";
import type { DomainRow, EmailRepo, IdentityRow } from "./repo";
import type { DnsRecord, DomainStatus, ProviderId, Stream } from "./types";

const up = <T extends string>(v: string) => v.toUpperCase() as T;
const low = <T extends string>(v: string) => v.toLowerCase() as T;

type DomainModel = Prisma.EmailDomainGetPayload<object>;
type IdentityModel = Prisma.EmailIdentityGetPayload<object>;

function toDomain(d: DomainModel): DomainRow {
  return {
    ...d,
    stream: low<Stream>(d.stream),
    status: low<DomainStatus>(d.status),
    dnsMode: low<DomainRow["dnsMode"]>(d.dnsMode),
  };
}
function toIdentity(i: IdentityModel): IdentityRow {
  return { ...i, provider: low<ProviderId>(i.provider), status: low<DomainStatus>(i.status) };
}

/** Convertit les champs énumérés d'un patch partiel vers le format Prisma. */
function domainPatch(patch: Partial<DomainRow> & { lastCheckedAt?: Date; nextCheckAt?: Date }): Prisma.EmailDomainUpdateInput {
  const { id: _id, tenantId: _t, stream, status, dnsMode, ...rest } = patch;
  return {
    ...rest,
    ...(stream ? { stream: up(stream) } : {}),
    ...(status ? { status: up(status) } : {}),
    ...(dnsMode ? { dnsMode: up(dnsMode) } : {}),
  } as Prisma.EmailDomainUpdateInput;
}

export function createPrismaEmailRepo(db: PrismaClient): EmailRepo {
  return {
    async createDomain(input) {
      return toDomain(await db.emailDomain.create({
        data: { ...input, stream: up<EmailStream>(input.stream), dnsMode: up<EmailDnsMode>(input.dnsMode) },
      }));
    },
    async getDomainByName(name) {
      const d = await db.emailDomain.findUnique({ where: { name } });
      return d ? toDomain(d) : null;
    },
    async getDomain(id) {
      const d = await db.emailDomain.findUnique({ where: { id } });
      return d ? toDomain(d) : null;
    },
    async updateDomain(id, patch) {
      await db.emailDomain.update({ where: { id }, data: domainPatch(patch) });
    },
    async listDomainsToCheck(now, limit) {
      const rows = await db.emailDomain.findMany({ where: { nextCheckAt: { lte: now } }, orderBy: { nextCheckAt: "asc" }, take: limit });
      return rows.map(toDomain);
    },

    async upsertIdentity(input) {
      const data = { ...input, provider: up<"RESEND" | "SES">(input.provider), status: up<"PENDING">(input.status) };
      return toIdentity(await db.emailIdentity.upsert({
        where: { domainId_provider: { domainId: input.domainId, provider: data.provider } },
        create: data, update: data,
      }));
    },
    async listIdentities(domainId) {
      return (await db.emailIdentity.findMany({ where: { domainId } })).map(toIdentity);
    },
    async updateIdentity(id, patch) {
      const { provider, status, id: _id, ...rest } = patch;
      await db.emailIdentity.update({
        where: { id },
        data: { ...rest, ...(provider ? { provider: up<"RESEND" | "SES">(provider) } : {}), ...(status ? { status: up<"PENDING">(status) } : {}) },
      });
    },

    async replaceRecords(domainId, provider, records: (DnsRecord & { observed?: string })[]) {
      const p = provider ? up<"RESEND" | "SES">(provider) : null;
      await db.$transaction([
        db.emailDnsRecord.deleteMany({ where: { domainId, provider: p } }),
        db.emailDnsRecord.createMany({
          data: records.map((r) => ({
            domainId, provider: p, purpose: r.purpose, type: r.type, name: r.name, value: r.value,
            priority: r.priority ?? null, status: r.status ?? "pending", observed: r.observed ?? null, lastCheckedAt: new Date(),
          })),
          skipDuplicates: true,
        }),
      ]);
    },
    async listRecords(domainId) {
      const rows = await db.emailDnsRecord.findMany({ where: { domainId } });
      return rows.map((r) => ({ purpose: r.purpose as DnsRecord["purpose"], type: r.type as DnsRecord["type"], name: r.name, value: r.value, priority: r.priority ?? undefined, status: r.status as DnsRecord["status"], observed: r.observed }));
    },

    async createMessage(input) {
      return db.emailMessage.create({
        data: { ...input, stream: up(input.stream), provider: up(input.provider) },
        select: { id: true },
      });
    },
    async markMessageSent(id, providerMessageId) {
      await db.emailMessage.update({ where: { id }, data: { providerMessageId, status: "sent", sentAt: new Date() } });
    },
    async markMessageStatus(id, status) {
      await db.emailMessage.update({ where: { id }, data: { status, lastEventAt: new Date() } });
    },
    async findMessageByProviderId(providerMessageId) {
      return db.emailMessage.findUnique({ where: { providerMessageId }, select: { id: true, tenantId: true, domainId: true } });
    },
    async simulatorEventsSeen(domainId, recipientHashes) {
      const rows = await db.emailEvent.findMany({
        where: { recipientHash: { in: recipientHashes }, type: { in: ["bounced_hard", "complained"] }, message: { domainId } },
        select: { type: true },
      });
      return { bounce: rows.some((r) => r.type === "bounced_hard"), complaint: rows.some((r) => r.type === "complained") };
    },
    async insertEvent(input) {
      try {
        await db.emailEvent.create({ data: { ...input, provider: up(input.provider) } });
        return true;
      } catch (e) {
        if (e instanceof Prisma.PrismaClientKnownRequestError && e.code === "P2002") return false; // déjà reçu
        throw e;
      }
    },

    async isSuppressed({ tenantId, emailHash, stream }) {
      const row = await db.emailSuppression.findFirst({
        where: { emailHash, scope: { in: ["global", tenantId] }, streamScope: { in: ["all", stream] } },
        select: { reason: true },
      });
      return row ? { reason: row.reason } : null;
    },
    async suppress(input) {
      await db.emailSuppression.upsert({
        where: { scope_emailHash_streamScope: { scope: input.scope, emailHash: input.emailHash, streamScope: input.streamScope } },
        create: input,
        update: {},
      });
    },

    async incrementDailyCounter(domainId, day) {
      const date = new Date(`${day}T00:00:00Z`);
      const row = await db.emailDailyCounter.upsert({
        where: { domainId_day: { domainId, day: date } },
        create: { domainId, day: date, sent: 1 },
        update: { sent: { increment: 1 } },
      });
      return row.sent;
    },
  };
}
