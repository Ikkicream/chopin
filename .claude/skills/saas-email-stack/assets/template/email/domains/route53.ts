// Délégation de sous-domaine : une zone hébergée Route 53 par sous-domaine client
// (ex. news.client.com). Le client pose les NS une seule fois ; ensuite la plateforme
// écrit elle-même DKIM, MAIL FROM, DMARC du sous-domaine et tracking, pour Resend
// comme pour SES, et peut changer de fournisseur sans le solliciter.
//
// Avec un « reusable delegation set » (ROUTE53_DELEGATION_SET_ID), toutes les zones
// partagent les mêmes 4 serveurs de noms : instructions identiques pour tous les clients,
// et possibilité de serveurs « marque blanche » (ns1.plateforme.com…).
import {
  ChangeResourceRecordSetsCommand, CreateHostedZoneCommand, DeleteHostedZoneCommand,
  GetHostedZoneCommand, ListResourceRecordSetsCommand, Route53Client, type Change, type RRType,
} from "@aws-sdk/client-route-53";
import type { DnsRecord } from "../types";

const r53 = new Route53Client({ region: "us-east-1" }); // service global

/**
 * Un jeu de serveurs réutilisable accepte 100 zones par défaut (quota relevable) : on en
 * liste plusieurs dans ROUTE53_DELEGATION_SET_IDS et on passe au suivant quand l'un est plein.
 * ConflictingDomainExists : une zone du même nom (ou parente/enfant) utilise déjà ces serveurs,
 * typiquement une réinscription du même domaine → réutiliser la zone existante.
 */
export async function createDelegatedZone(subdomain: string, tenantId: string) {
  const sets = (process.env.ROUTE53_DELEGATION_SET_IDS ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  let lastError: unknown;
  for (const DelegationSetId of sets.length ? sets : [undefined]) {
    try {
      const res = await r53.send(new CreateHostedZoneCommand({
        Name: subdomain,
        CallerReference: `${tenantId}:${subdomain}:${Date.now()}`, // unique par appel (idempotence côté AWS)
        DelegationSetId,
        HostedZoneConfig: { Comment: `email tenant=${tenantId}`, PrivateZone: false },
      }));
      const zoneId = res.HostedZone!.Id!.replace("/hostedzone/", "");
      return { zoneId, nameServers: res.DelegationSet?.NameServers ?? [], changeId: res.ChangeInfo?.Id };
    } catch (e) {
      lastError = e;
      if ((e as Error).name !== "TooManyHostedZones" && (e as Error).name !== "DelegationSetNotAvailable") throw e;
    }
  }
  throw lastError;
}

/** Route 53 attend des TXT entre guillemets, découpés en chaînes de 255 caractères max. */
function txtValue(v: string) {
  const chunks = v.replace(/"/g, '\\"').match(/.{1,255}/g) ?? [""];
  return chunks.map((c) => `"${c}"`).join(" ");
}

/**
 * Écrit (UPSERT) les enregistrements dans la zone déléguée. Les TXT et MX partageant un
 * même nom sont regroupés en un seul jeu d'enregistrements, comme l'exige Route 53.
 */
export async function upsertRecords(zoneId: string, records: DnsRecord[], ttl = 300) {
  const groups = new Map<string, DnsRecord[]>();
  for (const r of records) {
    if (r.type === "NS") continue; // gérés par Route 53
    const key = `${r.type} ${r.name.toLowerCase()}`;
    groups.set(key, [...(groups.get(key) ?? []), r]);
  }
  const changes: Change[] = [...groups.values()].map((recs) => ({
    Action: "UPSERT",
    ResourceRecordSet: {
      Name: recs[0].name,
      Type: recs[0].type as RRType,
      TTL: ttl,
      ResourceRecords: recs.map((r) => ({
        Value: r.type === "TXT" ? txtValue(r.value) : r.type === "MX" ? `${r.priority ?? 10} ${r.value}` : r.value,
      })),
    },
  }));
  if (!changes.length) return null;
  const res = await r53.send(new ChangeResourceRecordSetsCommand({
    HostedZoneId: zoneId,
    ChangeBatch: { Comment: "email-domain-setup", Changes: changes },
  }));
  return res.ChangeInfo?.Id ?? null; // PENDING puis INSYNC (GetChange) en général sous 60 s
}

export async function listZoneRecords(zoneId: string) {
  const res = await r53.send(new ListResourceRecordSetsCommand({ HostedZoneId: zoneId }));
  return res.ResourceRecordSets ?? [];
}

/**
 * Suppression d'une zone. ATTENTION au « subdomain takeover » : si le client garde ses NS
 * vers des serveurs Route 53 alors que la zone n'existe plus, un tiers peut recréer une zone
 * du même nom sur ces serveurs. Ne supprimer qu'après que le client a retiré ses NS
 * (vérifier avec checkDelegation → found vide), et sinon conserver la zone vide.
 */
export async function deleteDelegatedZone(zoneId: string) {
  const records = (await listZoneRecords(zoneId)).filter((r) => r.Type !== "NS" && r.Type !== "SOA");
  if (records.length) {
    await r53.send(new ChangeResourceRecordSetsCommand({
      HostedZoneId: zoneId,
      ChangeBatch: { Changes: records.map((r) => ({ Action: "DELETE", ResourceRecordSet: r })) },
    }));
  }
  await r53.send(new DeleteHostedZoneCommand({ Id: zoneId }));
}

export async function getZoneNameServers(zoneId: string) {
  const res = await r53.send(new GetHostedZoneCommand({ Id: zoneId }));
  return res.DelegationSet?.NameServers ?? [];
}
