// Helpers DNS sans dépendance (Node >= 18). Toutes les fonctions renvoient
// null / [] quand le nom n'existe pas, au lieu de lever une exception :
// pour un audit, « pas d'enregistrement » est un résultat, pas une erreur.
import { Resolver } from "node:dns/promises";
import { createPublicKey } from "node:crypto";

const NOT_FOUND = new Set(["ENODATA", "ENOTFOUND", "ENOTIMP", "ESERVFAIL", "EREFUSED", "NXDOMAIN"]);

export function makeResolver(servers = ["1.1.1.1", "8.8.8.8"], timeout = 5000) {
  const r = new Resolver({ timeout, tries: 2 });
  r.setServers(servers);
  return r;
}

async function safe(fn, fallback) {
  try {
    return await fn();
  } catch (e) {
    if (NOT_FOUND.has(e.code)) return fallback;
    if (e.code === "ETIMEOUT" || e.code === "ECONNREFUSED") {
      const err = new Error(`DNS timeout/refus pour ${e.hostname ?? "?"}`);
      err.transient = true;
      throw err;
    }
    return fallback;
  }
}

/** Renvoie la liste des TXT (chaque TXT = chaînes concaténées). */
export const txt = (r, name) =>
  safe(async () => (await r.resolveTxt(name)).map((chunks) => chunks.join("")), []);

export const cname = (r, name) => safe(async () => (await r.resolveCname(name))[0] ?? null, null);

export const mx = (r, name) =>
  safe(async () => (await r.resolveMx(name)).sort((a, b) => a.priority - b.priority), []);

export const a = (r, name) => safe(() => r.resolve4(name), []);

/** true si le nom existe dans le DNS (quel que soit le type). */
export async function exists(r, name) {
  try {
    await r.resolveAny(name);
    return true;
  } catch (e) {
    if (e.code === "ENOTFOUND") return false;
    return true; // ENODATA = le nom existe mais pas ce type
  }
}

/** Parse "k=v; k2=v2" (DMARC, DKIM, BIMI, MTA-STS, TLS-RPT, APRF). */
export function parseTags(record) {
  const tags = {};
  for (const part of record.split(";")) {
    const i = part.indexOf("=");
    if (i === -1) continue;
    const k = part.slice(0, i).trim().toLowerCase();
    const v = part.slice(i + 1).trim();
    if (k) tags[k] = v;
  }
  return tags;
}

/** Taille d'une clé DKIM à partir du tag p= (base64 SPKI pour RSA, brut pour ed25519). */
export function dkimKeyInfo(tags) {
  const p = (tags.p ?? "").replace(/\s+/g, "");
  if (!p) return { revoked: true, bits: 0, type: tags.k ?? "rsa" };
  const raw = Buffer.from(p, "base64");
  if ((tags.k ?? "rsa").toLowerCase() === "ed25519") return { type: "ed25519", bits: 256, revoked: false };
  try {
    const key = createPublicKey({ key: raw, format: "der", type: "spki" });
    return { type: key.asymmetricKeyType, bits: key.asymmetricKeyDetails?.modulusLength ?? 0, revoked: false };
  } catch {
    // Certains fournisseurs publient une clé RSA PKCS#1 nue.
    try {
      const key = createPublicKey({ key: raw, format: "der", type: "pkcs1" });
      return { type: "rsa", bits: key.asymmetricKeyDetails?.modulusLength ?? 0, revoked: false };
    } catch {
      return { type: "unknown", bits: Math.round(raw.length * 8 * 0.9), revoked: false, unparsable: true };
    }
  }
}

// Suffixes publics multi-labels courants. Ce n'est pas la Public Suffix List
// complète : assez pour les cas FR/UK/AU/BR usuels. DMARCbis remplace de toute
// façon la PSL par un « tree walk » (voir dmarcLookup).
const MULTI_SUFFIX = new Set([
  "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au", "co.nz", "co.jp", "com.br",
  "com.mx", "com.ar", "co.za", "com.tr", "com.cn", "com.hk", "com.sg", "co.in", "co.il", "co.kr",
  "gouv.fr", "asso.fr", "nom.fr", "com.fr", "tm.fr", "presse.fr", "co.at", "or.at", "com.es", "com.pt",
  "com.pl", "com.be", "co.it", "com.co", "com.pe", "com.ve", "com.ua", "co.id", "com.my", "com.ph",
]);

export function orgDomain(domain) {
  const labels = domain.toLowerCase().replace(/\.$/, "").split(".");
  if (labels.length <= 2) return labels.join(".");
  const last2 = labels.slice(-2).join(".");
  return MULTI_SUFFIX.has(last2) ? labels.slice(-3).join(".") : last2;
}

/**
 * Découverte DMARC façon DMARCbis (tree walk) : on essaie _dmarc.<domaine>,
 * puis chaque parent jusqu'au domaine organisationnel inclus. Le premier
 * enregistrement v=DMARC1 trouvé s'applique ; s'il vient d'un parent, c'est
 * sp= (ou np= pour un sous-domaine inexistant) qui gouverne.
 */
export async function dmarcLookup(r, domain) {
  const org = orgDomain(domain);
  const labels = domain.toLowerCase().split(".");
  const orgDepth = org.split(".").length;
  for (let i = 0; labels.length - i >= orgDepth; i++) {
    const host = labels.slice(i).join(".");
    const all = await txt(r, `_dmarc.${host}`);
    const records = all.filter((t) => /^v\s*=\s*DMARC1/i.test(t.trim()));
    if (records.length || all.some((t) => /dmarc/i.test(t))) {
      return { host, inherited: host !== domain.toLowerCase(), records, all };
    }
  }
  return { host: null, inherited: false, records: [], all: [] };
}

/**
 * Évalue récursivement un SPF pour compter les requêtes DNS (limite RFC 7208 :
 * 10 mécanismes déclenchant une requête, 2 « void lookups »).
 */
export async function spfWalk(r, domain, state = { lookups: 0, voids: 0, seen: new Set(), tree: [], errors: [] }, depth = 0) {
  if (depth > 12 || state.seen.has(domain)) {
    state.errors.push(`boucle ou profondeur excessive sur ${domain}`);
    return state;
  }
  state.seen.add(domain);
  const records = (await txt(r, domain)).filter((t) => /^v=spf1(\s|$)/i.test(t.trim()));
  if (records.length === 0) {
    state.voids++;
    state.tree.push({ domain, depth, record: null });
    return state;
  }
  if (records.length > 1) state.errors.push(`plusieurs SPF sur ${domain} (permerror)`);
  const record = records[0];
  state.tree.push({ domain, depth, record });
  for (const term of record.split(/\s+/).slice(1)) {
    const t = term.replace(/^[+\-~?]/, "").toLowerCase();
    if (t.startsWith("include:")) {
      state.lookups++;
      await spfWalk(r, t.slice(8), state, depth + 1);
    } else if (t.startsWith("redirect=")) {
      state.lookups++;
      await spfWalk(r, t.slice(9), state, depth + 1);
    } else if (t === "a" || t.startsWith("a:") || t.startsWith("a/")) {
      state.lookups++;
    } else if (t === "mx" || t.startsWith("mx:") || t.startsWith("mx/")) {
      state.lookups++;
    } else if (t === "ptr" || t.startsWith("ptr:")) {
      state.lookups++;
      state.errors.push(`mécanisme ptr déconseillé (RFC 7208 §5.5) dans ${domain}`);
    } else if (t.startsWith("exists:")) {
      state.lookups++;
    }
  }
  return state;
}

export function spfAll(record) {
  const m = record.match(/(^|\s)([+\-~?]?)all(\s|$)/i);
  if (!m) return record.includes("redirect=") ? "redirect" : "none";
  return { "": "+all", "+": "+all", "-": "-all", "~": "~all", "?": "?all" }[m[2]];
}
