// Orchestration de l'onboarding d'un domaine client, de la création à la mise en service.
//
//   createSendingDomain()  → région figée, identités chez le(s) fournisseur(s), zone déléguée
//                            ou liste de records à copier, DMARC du sous-domaine si délégué
//   refreshDomain()        → job périodique : délégation, statut fournisseur, DNS observé, DMARC
//   confirmGoLiveStep()    → confirmations manuelles (Postmaster Tools, Sender Hub) et warm-up
//
// Les appels de gestion SES sont limités à 1/s : appeler createSendingDomain depuis une file.
import type { EmailRepo } from "../repo";
import { sendEmail, type SendDeps } from "../send";
import type { DnsMode, DnsRecord, DomainStatus, EmailProvider, ProviderId, Stream } from "../types";
import { checkDelegation, checkRecords, readDmarc } from "./dns-check";
import { createDelegatedZone, deleteDelegatedZone, upsertRecords } from "./route53";
import { configSetFor, sesTenantName } from "../providers/ses";

const DOMAIN_RE = /^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$/;

export interface CreateDomainInput {
  tenantId: string;
  name: string;               // news.client.com
  rootDomain: string;         // client.com (saisi ou déduit)
  stream: Stream;
  dnsMode: DnsMode;
  providers: ProviderId[];    // ex. ["ses"] pour le marketing, ["resend"] pour le transactionnel, ou les deux
  regions: Partial<Record<ProviderId, string>>; // ex. { resend: "eu-west-1", ses: "eu-west-3" }
  dmarcRua?: string;          // boîte RÉELLEMENT lue (ou parseur DMARC)
}

export async function createSendingDomain(deps: { repo: EmailRepo; providers: Partial<Record<ProviderId, EmailProvider>> }, input: CreateDomainInput) {
  const name = input.name.trim().toLowerCase().replace(/\.$/, "");
  if (!DOMAIN_RE.test(name) || /^(www|http)/.test(name)) throw new Error("Nom de domaine invalide (pas de http://, pas de www)");
  if (name === input.rootDomain) throw new Error("Utiliser un sous-domaine dédié (news. pour le marketing, mail. pour le transactionnel)");
  if (!name.endsWith(`.${input.rootDomain}`)) throw new Error("Le sous-domaine doit appartenir au domaine racine indiqué");
  if (await deps.repo.getDomainByName(name)) throw new Error("Ce domaine est déjà enregistré sur la plateforme");
  for (const p of input.providers) if (!input.regions[p]) throw new Error(`Région manquante pour ${p} : elle est définitive, la choisir maintenant`);

  const domain = await deps.repo.createDomain({
    tenantId: input.tenantId, name, rootDomain: input.rootDomain, stream: input.stream,
    region: input.regions[input.providers[0]]!, dnsMode: input.dnsMode,
  });

  // 1. Identités chez les fournisseurs (la région est fixée ICI, avant tout DNS).
  const all: DnsRecord[] = [];
  for (const p of input.providers) {
    const provider = deps.providers[p];
    if (!provider) throw new Error(`Fournisseur ${p} non configuré`);
    const created = await provider.createDomain({ name, region: input.regions[p]!, tenantId: input.tenantId, returnPathLabel: p === "resend" ? "send" : "bounce" });
    await deps.repo.upsertIdentity({
      domainId: domain.id, provider: p, providerRef: created.ref, status: created.status, region: created.region,
      isPrimary: p === input.providers[0],
      configurationSet: p === "ses" ? configSetFor(input.stream) : null,
      sesTenantName: p === "ses" ? sesTenantName(input.tenantId) : null,
    });
    await deps.repo.replaceRecords(domain.id, p, created.records);
    all.push(...created.records);
  }

  // 2. DMARC propre au sous-domaine (seulement si on contrôle sa zone) : p=none + rua pendant le
  //    warm-up, durci ensuite. Mais on n'AFFAIBLIT jamais une politique existante : si la racine
  //    impose déjà quarantine/reject aux sous-domaines (sp= ou p=), on la reprend en ajoutant rua.
  const inherited = await readDmarc(name); // avant délégation : renvoie la politique héritée de la racine
  const policy = inherited.policy && inherited.policy !== "none" ? inherited.policy : "none";
  const dmarc: DnsRecord = { purpose: "dmarc", type: "TXT", name: `_dmarc.${name}`, value: `v=DMARC1; p=${policy}${input.dmarcRua ? `; rua=mailto:${input.dmarcRua}` : ""}` };

  // 3. Branchement DNS.
  if (input.dnsMode === "delegated") {
    const zone = await createDelegatedZone(name, input.tenantId);
    await upsertRecords(zone.zoneId, [...all, ...(input.dmarcRua ? [dmarc] : [])]);
    await deps.repo.updateDomain(domain.id, { hostedZoneId: zone.zoneId, nameServers: zone.nameServers, status: "pending", nextCheckAt: new Date(Date.now() + 60_000) });
    // Ce que le client doit poser chez lui : uniquement les NS.
    const ns: DnsRecord[] = zone.nameServers.map((v) => ({ purpose: "other", type: "NS", name, value: v }));
    await deps.repo.replaceRecords(domain.id, null, ns);
    return { domainId: domain.id, clientRecords: ns };
  }
  await deps.repo.updateDomain(domain.id, { status: "pending", nextCheckAt: new Date(Date.now() + 60_000) });
  return { domainId: domain.id, clientRecords: all };
}

/** Prochaine vérification : 1 min, 5 min, 15 min, 1 h… jusqu'à 72 h, puis échec. */
function nextCheck(createdAgeMs: number) {
  const steps = [60_000, 300_000, 900_000, 3_600_000];
  const i = Math.min(steps.length - 1, Math.floor(createdAgeMs / 3_600_000));
  return new Date(Date.now() + steps[i]);
}

export async function refreshDomain(deps: { repo: EmailRepo; providers: Partial<Record<ProviderId, EmailProvider>> }, domainId: string, ageMs: number) {
  const { repo } = deps;
  const domain = await repo.getDomain(domainId);
  if (!domain) return;

  // Délégation NS (le fournisseur ne peut rien vérifier tant qu'elle n'est pas en place).
  if (domain.dnsMode === "delegated" && !domain.delegationVerifiedAt) {
    const d = await checkDelegation(domain.name, domain.nameServers);
    if (d.delegated) await repo.updateDomain(domain.id, { delegationVerifiedAt: new Date() });
    // Zone jamais déléguée après 7 jours : on la libère pour qu'un tenant ne puisse pas
    // « réserver » le sous-domaine d'une marque qui ne lui appartient pas. Sans risque de
    // reprise (subdomain takeover) puisqu'aucun NS ne pointe vers elle.
    else if (d.found.length === 0 && ageMs > 7 * 86_400_000) {
      if (domain.hostedZoneId) await deleteDelegatedZone(domain.hostedZoneId);
      await repo.updateDomain(domain.id, { status: "failed", hostedZoneId: null, nextCheckAt: undefined });
      return;
    }
  }

  // Statut chez chaque fournisseur + DNS observé.
  let best: DomainStatus = "pending";
  for (const identity of await repo.listIdentities(domain.id)) {
    const provider = deps.providers[identity.provider];
    if (!provider) continue;
    const pd = identity.provider === "resend" && identity.status !== "verified" ? await provider.verifyDomain(identity.providerRef) : await provider.getDomain(identity.providerRef);
    await repo.updateIdentity(identity.id, { status: pd.status });
    await repo.replaceRecords(domain.id, identity.provider, await checkRecords(pd.records));
    if (pd.status === "verified") best = "verified";
  }

  const dmarc = await readDmarc(domain.name);
  const timedOut = best !== "verified" && ageMs > 72 * 3_600_000;
  await repo.updateDomain(domain.id, {
    status: timedOut ? "failed" : best,
    dmarcPolicyObserved: dmarc.policy,
    dmarcRuaObserved: dmarc.hasRua,
    lastCheckedAt: new Date(),
    nextCheckAt: best === "verified" ? new Date(Date.now() + 86_400_000) : timedOut ? undefined : nextCheck(ageMs),
  });
}

/** Confirmations de mise en service qui ne se vérifient pas automatiquement. */
export async function confirmGoLiveStep(repo: EmailRepo, domainId: string, step: "postmaster" | "senderhub" | "unsubscribe" | "warmup", opts: { targetPerDay?: number; firstWeekPerDay?: number } = {}) {
  const now = new Date();
  if (step === "postmaster") return repo.updateDomain(domainId, { postmasterConfirmedAt: now });
  if (step === "senderhub") return repo.updateDomain(domainId, { senderHubConfirmedAt: now });
  if (step === "unsubscribe") return repo.updateDomain(domainId, { unsubscribeVerifiedAt: now });
  return repo.updateDomain(domainId, {
    warmupStartedAt: now, warmupTargetPerDay: opts.targetPerDay ?? null,
    warmupFirstWeekPerDay: Math.min(500, Math.max(300, opts.firstWeekPerDay ?? 400)),
  });
}


/**
 * Auto-test des webhooks (condition n°3) : deux envois vers les simulateurs du fournisseur
 * principal. Quand le bounce ET la plainte reviennent signés, events.ts renseigne
 * webhookVerifiedAt. Les simulateurs contournent les portes de mise en service.
 */
export async function runWebhookSelfTest(deps: SendDeps, domainId: string, fromLocalPart = "selftest") {
  const domain = await deps.repo.getDomain(domainId);
  if (!domain) throw new Error("Domaine introuvable");
  const primary = (await deps.repo.listIdentities(domainId)).find((i) => i.isPrimary && i.status === "verified");
  if (!primary) throw new Error("Aucune identité vérifiée : vérifier le domaine d'abord");
  const targets = primary.provider === "resend"
    ? ["bounced@resend.dev", "complained@resend.dev"]
    : ["bounce@simulator.amazonses.com", "complaint@simulator.amazonses.com"];
  for (const to of targets) {
    await sendEmail(deps, {
      tenantId: domain.tenantId, stream: domain.stream, to,
      from: { email: `${fromLocalPart}@${domain.name}`, name: "Auto-test" },
      subject: "Auto-test des webhooks", html: "<p>Auto-test des webhooks de délivrabilité.</p>", text: "Auto-test des webhooks.",
      tags: { selftest: "webhooks" },
    });
  }
}
