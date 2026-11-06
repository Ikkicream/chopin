// Vérifications DNS faites par la plateforme elle-même (le fournisseur ne vérifie
// ni DMARC, ni la délégation NS). Résolveurs publics pour éviter les caches locaux.
import { Resolver } from "node:dns/promises";
import type { DnsRecord } from "../types";

const resolver = new Resolver({ timeout: 4000, tries: 2 });
resolver.setServers(["1.1.1.1", "8.8.8.8"]);

const MISSING = new Set(["ENODATA", "ENOTFOUND", "NXDOMAIN", "ESERVFAIL"]);
async function q<T>(fn: () => Promise<T>, empty: T): Promise<T> {
  try { return await fn(); } catch (e) {
    if (MISSING.has((e as NodeJS.ErrnoException).code ?? "")) return empty;
    throw e; // timeout : ne pas conclure « absent » (une alerte ne se ferme jamais sur un échec DNS)
  }
}
const norm = (v: string) => v.toLowerCase().replace(/^"|"$/g, "").replace(/\.$/, "").replace(/\s+/g, " ").trim();

/** Compare chaque enregistrement attendu à ce que le DNS public renvoie. */
export async function checkRecords(records: DnsRecord[]): Promise<(DnsRecord & { observed: string })[]> {
  return Promise.all(records.map(async (rec) => {
    let observed = "", ok = false;
    if (rec.type === "CNAME") {
      observed = (await q(() => resolver.resolveCname(rec.name), []))[0] ?? "";
      ok = norm(observed) === norm(rec.value);
    } else if (rec.type === "MX") {
      const list = await q(() => resolver.resolveMx(rec.name), []);
      observed = list.map((m) => `${m.priority} ${m.exchange}`).join(", ");
      ok = list.some((m) => norm(m.exchange) === norm(rec.value));
    } else if (rec.type === "TXT") {
      const list = (await q(() => resolver.resolveTxt(rec.name), [])).map((c) => c.join(""));
      observed = list.join(" | ");
      ok = rec.purpose === "dmarc" ? list.some((t) => /^v=DMARC1/i.test(t))
        : rec.purpose === "spf" ? list.some((t) => /^v=spf1/i.test(t) && (rec.value.match(/include:\S+/g) ?? []).every((i) => t.includes(i)))
        : list.some((t) => norm(t) === norm(rec.value));
    } else if (rec.type === "NS") {
      const list = await q(() => resolver.resolveNs(rec.name), []);
      observed = list.join(", ");
      ok = list.some((n) => norm(n) === norm(rec.value));
    }
    return { ...rec, observed, status: ok ? "verified" as const : "pending" as const };
  }));
}

/**
 * Délégation NS : le sous-domaine doit répondre avec NOS serveurs de noms.
 * resolveNs interroge le résolveur récursif, qui suit la délégation posée par le client.
 */
export async function checkDelegation(subdomain: string, expectedNs: string[]) {
  const found = (await q(() => resolver.resolveNs(subdomain), [])).map(norm);
  const expected = expectedNs.map(norm);
  const matching = expected.filter((n) => found.includes(n));
  return {
    delegated: matching.length === expected.length && found.length === expected.length,
    partial: matching.length > 0 && matching.length < expected.length,
    found,
    expected,
  };
}

/** DMARC effectif (tree walk simplifié : le sous-domaine puis ses parents). */
export async function readDmarc(domain: string) {
  const labels = domain.toLowerCase().split(".");
  for (let i = 0; i < labels.length - 1; i++) {
    const host = labels.slice(i).join(".");
    const rec = (await q(() => resolver.resolveTxt(`_dmarc.${host}`), [])).map((c) => c.join("")).find((t) => /^v=DMARC1/i.test(t));
    if (rec) {
      const tags = Object.fromEntries(rec.split(";").map((p) => p.trim().split("=")).filter((kv) => kv.length === 2).map(([k, v]) => [k.toLowerCase(), v]));
      const policy = (host !== domain && tags.sp ? tags.sp : tags.p) ?? null;
      return { host, inherited: host !== domain, record: rec, policy, hasRua: /rua=mailto:/i.test(rec) };
    }
  }
  return { host: null, inherited: false, record: null, policy: null, hasRua: false };
}
