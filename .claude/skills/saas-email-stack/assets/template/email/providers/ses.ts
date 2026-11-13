// Référence d'identité : « <région>/<domaine> » (ex. eu-west-3/news.client.com).
// Adaptateur Amazon SES v2 (@aws-sdk/client-sesv2). Usage recommandé : flux MARKETING
// des clients, avec isolation par « SES Tenant » (un tenant SES par client).
//
// Choix d'architecture imposés par les quotas SES :
//  - configuration sets : 10 000 par région, NON ajustable → on les PARTAGE par flux
//    (`<prefix>-marketing`, `<prefix>-transactional`) et on isole par tenant SES ;
//  - un tenant SES n'envoie que si l'identité ET le configuration set lui sont associés ;
//  - API de gestion limitée à 1 requête/s → provisionner via une file, jamais en rafale ;
//  - les tenants ne partagent pas le quota d'envoi du compte : plafonner nous-mêmes par tenant.
import {
  CreateEmailIdentityCommand, CreateTenantCommand, CreateTenantResourceAssociationCommand,
  DeleteEmailIdentityCommand, GetEmailIdentityCommand, GetTenantCommand,
  PutEmailIdentityMailFromAttributesCommand, SendEmailCommand, SESv2Client,
} from "@aws-sdk/client-sesv2";
import type { DnsRecord, DomainStatus, EmailProvider, OutboundEmail, ProviderDomain } from "../types";

const clients = new Map<string, SESv2Client>();
const ses = (region: string) => {
  if (!clients.has(region)) clients.set(region, new SESv2Client({ region }));
  return clients.get(region)!;
};

const ACCOUNT = () => process.env.AWS_ACCOUNT_ID!;
const PREFIX = () => process.env.SES_CONFIG_SET_PREFIX ?? "platform";
export const configSetFor = (stream: "marketing" | "transactional") => `${PREFIX()}-${stream}`;
/** Nom de tenant SES : 64 caractères max, [A-Za-z0-9_-]. */
export const sesTenantName = (tenantId: string) => `t-${tenantId}`.replace(/[^A-Za-z0-9_-]/g, "-").slice(0, 64);

const tagSafe = (v: string) => v.replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 256);

/** Nom affiché encodé en RFC 2047 s'il contient des caractères non ASCII (exigé par SES). */
function formatFrom(email: string, name?: string) {
  if (!name) return email;
  const clean = name.replace(/["\r\n<>]/g, "");
  return /^[\x20-\x7e]*$/.test(clean) ? `"${clean}" <${email}>` : `=?UTF-8?B?${Buffer.from(clean).toString("base64")}?= <${email}>`;
}

function statusOf(id: { VerifiedForSendingStatus?: boolean; DkimAttributes?: { Status?: string }; MailFromAttributes?: { MailFromDomain?: string; MailFromDomainStatus?: string } }): DomainStatus {
  const dkim = id.DkimAttributes?.Status, mf = id.MailFromAttributes?.MailFromDomainStatus;
  if (dkim === "FAILED" || mf === "FAILED") return "failed";
  if (dkim === "TEMPORARY_FAILURE" || mf === "TEMPORARY_FAILURE") return "temporary_failure";
  // MAIL FROM non vérifié = SPF non aligné : on n'annonce « verified » qu'avec les deux.
  if (id.VerifiedForSendingStatus && dkim === "SUCCESS" && (!mf || mf === "SUCCESS")) return "verified";
  return dkim === "NOT_STARTED" ? "not_started" : "pending";
}

function recordsOf(name: string, region: string, id: { DkimAttributes?: { Tokens?: string[]; SigningHostedZone?: string; Status?: string }; MailFromAttributes?: { MailFromDomain?: string; MailFromDomainStatus?: string } }): DnsRecord[] {
  // La zone de signature varie selon la région et l'identité : ne jamais coder « dkim.amazonses.com » en dur.
  const zone = id.DkimAttributes?.SigningHostedZone ?? "dkim.amazonses.com";
  const dkimOk = id.DkimAttributes?.Status === "SUCCESS";
  const records: DnsRecord[] = (id.DkimAttributes?.Tokens ?? []).map((t) => ({
    purpose: "dkim", type: "CNAME", name: `${t}._domainkey.${name}`, value: `${t}.${zone}`, status: dkimOk ? "verified" : "pending",
  }));
  const mf = id.MailFromAttributes?.MailFromDomain;
  if (mf) {
    const ok = id.MailFromAttributes?.MailFromDomainStatus === "SUCCESS" ? "verified" : "pending";
    // Un seul MX sur le MAIL FROM, et ce sous-domaine ne sert ni de From ni à recevoir.
    records.push(
      { purpose: "mail-from", type: "MX", name: mf, value: `feedback-smtp.${region}.amazonses.com`, priority: 10, status: ok },
      { purpose: "spf", type: "TXT", name: mf, value: "v=spf1 include:amazonses.com ~all", status: ok },
    );
  }
  return records;
}

/** Crée le tenant SES du client s'il n'existe pas, avec suppression isolée au niveau tenant. */
export async function ensureSesTenant(region: string, tenantId: string) {
  const TenantName = sesTenantName(tenantId);
  try {
    const { Tenant } = await ses(region).send(new GetTenantCommand({ TenantName }));
    return Tenant!;
  } catch (e) {
    if ((e as Error).name !== "NotFoundException") throw e;
  }
  const created = await ses(region).send(new CreateTenantCommand({
    TenantName,
    Tags: [{ Key: "tenantId", Value: tenantId }],
    // Les bounces/plaintes d'un client ne bloquent pas les destinataires des autres clients.
    SuppressionAttributes: { SuppressionScope: "TENANT", SuppressedReasons: ["BOUNCE", "COMPLAINT"] },
  }));
  // Les configuration sets partagés doivent aussi être associés au tenant pour qu'il puisse envoyer.
  for (const stream of ["marketing", "transactional"] as const) {
    await ses(region).send(new CreateTenantResourceAssociationCommand({
      TenantName, ResourceArn: `arn:aws:ses:${region}:${ACCOUNT()}:configuration-set/${configSetFor(stream)}`,
    }));
  }
  return created;
}

export function createSesProvider(): EmailProvider {
  async function getDomain(ref: string, region?: string): Promise<ProviderDomain> {
    const [reg, name] = ref.includes("/") ? ref.split("/") : [region ?? process.env.SES_DEFAULT_REGION ?? "eu-west-3", ref];
    const id = await ses(reg).send(new GetEmailIdentityCommand({ EmailIdentity: name }));
    return { provider: "ses", ref: `${reg}/${name}`, name, region: reg, status: statusOf(id), records: recordsOf(name, reg, id) };
  }

  return {
    id: "ses",

    async createDomain({ name, region, returnPathLabel, tenantId }) {
      const client = ses(region);
      const tenant = await ensureSesTenant(region, tenantId);
      const created = await client.send(new CreateEmailIdentityCommand({
        EmailIdentity: name,
        DkimSigningAttributes: { NextSigningKeyLength: "RSA_2048_BIT" }, // Easy DKIM, 3 CNAME, rotation par AWS
        ConfigurationSetName: configSetFor("marketing"),
        Tags: [{ Key: "tenantId", Value: tenantId }],
      }));
      await client.send(new PutEmailIdentityMailFromAttributesCommand({
        EmailIdentity: name,
        MailFromDomain: `${returnPathLabel ?? "bounce"}.${name}`,
        // USE_DEFAULT_VALUE : si le MX disparaît, SES repasse sur amazonses.com (SPF non aligné mais
        // DKIM reste aligné → DMARC passe). REJECT_MESSAGE bloquerait l'envoi.
        BehaviorOnMxFailure: "USE_DEFAULT_VALUE",
      }));
      await client.send(new CreateTenantResourceAssociationCommand({
        TenantName: tenant.TenantName!, ResourceArn: `arn:aws:ses:${region}:${ACCOUNT()}:identity/${name}`,
      }));
      return {
        provider: "ses", ref: `${region}/${name}`, name, region,
        status: statusOf({ ...created, MailFromAttributes: { MailFromDomain: `${returnPathLabel ?? "bounce"}.${name}`, MailFromDomainStatus: "PENDING" } }),
        records: recordsOf(name, region, { ...created, MailFromAttributes: { MailFromDomain: `${returnPathLabel ?? "bounce"}.${name}` } }),
      };
    },

    getDomain: (ref) => getDomain(ref),
    // SES n'a pas d'appel « verify » : il interroge le DNS lui-même pendant 72 h. On relit l'état.
    verifyDomain: (ref) => getDomain(ref),

    async deleteDomain(ref) {
      const [region, name] = ref.split("/");
      // Retirer d'abord l'association au tenant (DeleteTenantResourceAssociation) si nécessaire.
      await ses(region).send(new DeleteEmailIdentityCommand({ EmailIdentity: name }));
    },

    async send(email: OutboundEmail, ctx) {
      const region = ctx.region ?? process.env.SES_DEFAULT_REGION ?? "eu-west-3";
      const headers = Object.entries(email.headers ?? {}).slice(0, 15).map(([Name, Value]) => ({ Name, Value })); // 15 en-têtes max
      const res = await ses(region).send(new SendEmailCommand({
        FromEmailAddress: formatFrom(email.from.email, email.from.name),
        Destination: { ToAddresses: [email.to] },
        ReplyToAddresses: email.replyTo ? [email.replyTo] : undefined,
        Content: {
          Simple: {
            Subject: { Data: email.subject, Charset: "UTF-8" },
            Body: { Html: { Data: email.html, Charset: "UTF-8" }, ...(email.text ? { Text: { Data: email.text, Charset: "UTF-8" } } : {}) },
            Headers: headers,
          },
        },
        // Notre propre tag tenant : SES n'ajoute `ses:tenant-name` qu'aux bounces et plaintes.
        EmailTags: Object.entries(email.tags ?? {}).map(([Name, Value]) => ({ Name: tagSafe(Name), Value: tagSafe(Value) })),
        ConfigurationSetName: ctx.configurationSet ?? configSetFor(email.stream),
        TenantName: ctx.sesTenant ?? sesTenantName(email.tenantId),
      }));
      return { provider: "ses", providerMessageId: res.MessageId! };
    },
  };
}
