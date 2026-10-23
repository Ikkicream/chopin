// Adaptateur Resend (SDK `resend` ≥ 6). Usage recommandé : flux TRANSACTIONNEL.
//
// Pourquoi pas le marketing multi-tenant sur Resend : un compte (« team ») partage
// entre tous les clients la limite de 10 req/s, la liste de suppression, les contacts
// et désinscriptions, et des seuils de compte (bounces < 4 %, spam < 0,08 %) dont le
// dépassement par UN client peut suspendre l'envoi de TOUS. Et les données du compte
// sont stockées aux États-Unis quelle que soit la région d'envoi.
import { Resend } from "resend";
import type { DnsRecord, DomainStatus, EmailProvider, OutboundEmail, ProviderDomain } from "../types";

const RESEND_REGIONS = ["us-east-1", "eu-west-1", "sa-east-1", "ap-northeast-1"] as const;
type ResendRegion = (typeof RESEND_REGIONS)[number];

/** Les tags Resend n'acceptent que [A-Za-z0-9_-], 256 caractères max. */
const tagSafe = (v: string) => v.replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 256);

function mapStatus(s: string): DomainStatus {
  if (s === "verified") return "verified";
  if (s === "failed" || s === "partially_failed") return "failed";
  if (s === "temporary_failure") return "temporary_failure";
  if (s === "not_started") return "not_started";
  return "pending"; // pending, partially_verified
}

/**
 * Resend renvoie des noms relatifs (à la zone ou au domaine selon les cas) :
 * on reconstruit le FQDN. Les records peuvent être TXT+MX ou, depuis août 2026,
 * deux CNAME (`send`, `rsend`) : on affiche toujours ce que l'API renvoie.
 */
function toFqdn(name: string, domain: string): string {
  const n = name.toLowerCase().replace(/\.$/, "");
  if (n === "@" || n === "" || n === domain) return domain;
  if (n.endsWith(`.${domain}`)) return n;
  const labels = domain.split(".");
  // nom relatif à la zone : se termine par le(s) label(s) propres au sous-domaine (ex. "send.news")
  for (let i = 1; i < labels.length - 1; i++) {
    const rel = labels.slice(0, i).join(".");
    if (n === rel || n.endsWith(`.${rel}`)) return `${n}.${labels.slice(i).join(".")}`;
  }
  return `${n}.${domain}`;
}

type ResendRecord = { record: string; name: string; type: string; value: string; priority?: number; status: string };

function mapRecords(domain: string, records: ResendRecord[]): DnsRecord[] {
  return records
    .filter((r) => r.type !== "CAA" || r.value) // CAA de tracking : conservé s'il est fourni
    .map((r) => ({
      purpose: r.record === "DKIM" ? "dkim" : r.record === "SPF" ? (r.type === "TXT" ? "spf" : "mail-from") : r.record === "Tracking" || r.record === "TrackingCAA" ? "tracking" : "other",
      type: r.type as DnsRecord["type"],
      name: toFqdn(r.name, domain),
      value: r.value,
      priority: r.priority,
      status: r.status === "verified" ? "verified" : r.status === "failed" ? "failed" : "pending",
    }));
}

export function createResendProvider(apiKey = process.env.RESEND_API_KEY): EmailProvider {
  // Client créé au premier usage : un projet sans Resend (SES seul) ne plante pas au démarrage.
  let client: Resend | null = null;
  const resendClient = () => {
    if (!apiKey) throw new Error("RESEND_API_KEY manquante");
    return (client ??= new Resend(apiKey));
  };

  async function getDomain(ref: string): Promise<ProviderDomain> {
    const { data, error } = await resendClient().domains.get(ref);
    if (error || !data) throw new Error(`Resend domains.get : ${error?.message}`);
    return { provider: "resend", ref: data.id, name: data.name, region: data.region, status: mapStatus(data.status), records: mapRecords(data.name, data.records as ResendRecord[]) };
  }

  return {
    id: "resend",

    async createDomain({ name, region, returnPathLabel }) {
      if (!RESEND_REGIONS.includes(region as ResendRegion)) throw new Error(`Région Resend invalide : ${region} (UE = eu-west-1)`);
      // Région et custom return path sont DÉFINITIFS : on les fixe ici, avant tout DNS.
      const { data, error } = await resendClient().domains.create({
        name,
        region: region as ResendRegion,
        customReturnPath: returnPathLabel ?? "send",
        tls: "opportunistic",
        openTracking: false,   // le transactionnel n'a pas besoin du pixel (et Apple MPP le fausse)
        clickTracking: false,
      });
      if (error || !data) throw new Error(`Resend domains.create : ${error?.message}`);
      return { provider: "resend", ref: data.id, name: data.name, region: data.region, status: mapStatus(data.status), records: mapRecords(data.name, data.records as ResendRecord[]) };
    },

    getDomain,

    async verifyDomain(ref) {
      // Asynchrone : Resend repasse le domaine en « pending » et notifie domain.updated.
      const { error } = await resendClient().domains.verify(ref);
      if (error) throw new Error(`Resend domains.verify : ${error.message}`);
      return getDomain(ref);
    },

    async deleteDomain(ref) {
      const { error } = await resendClient().domains.remove(ref);
      if (error) throw new Error(`Resend domains.remove : ${error.message}`);
    },

    async send(email: OutboundEmail) {
      const from = email.from.name ? `${email.from.name.replace(/["<>]/g, "")} <${email.from.email}>` : email.from.email;
      const { data, error } = await resendClient().emails.send(
        {
          from,
          to: email.to,
          replyTo: email.replyTo,
          subject: email.subject,
          html: email.html,
          text: email.text,
          headers: email.headers,
          tags: Object.entries(email.tags ?? {}).map(([name, value]) => ({ name: tagSafe(name), value: tagSafe(value) })),
        },
        { idempotencyKey: email.idempotencyKey }, // 24 h côté Resend
      );
      if (error || !data) {
        const err = new Error(`Resend ${error?.name} : ${error?.message}`);
        err.name = error?.name ?? "resend_error"; // rate_limit_exceeded, validation_error, daily_quota_exceeded…
        throw err;
      }
      return { provider: "resend", providerMessageId: data.id };
    },
  };
}

/**
 * Clé d'API limitée à un domaine (permission sending_access) : à remettre à un
 * client qui envoie depuis SON code, pour qu'une fuite n'expose que son domaine.
 */
export async function createDomainScopedKey(domainId: string, label: string, apiKey = process.env.RESEND_API_KEY!) {
  const resend = new Resend(apiKey);
  const { data, error } = await resend.apiKeys.create({ name: label.slice(0, 50), permission: "sending_access", domain_id: domainId });
  if (error || !data) throw new Error(`Resend apiKeys.create : ${error?.message}`);
  return data; // { id, token } — le token n'est affiché qu'une fois : le chiffrer avant stockage
}
