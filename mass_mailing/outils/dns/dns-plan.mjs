#!/usr/bin/env node
// Génère le plan DNS d'un domaine d'envoi pour un fournisseur donné.
// Sans --from-api : gabarit avec <jetons> à remplacer.
// Avec --from-api : convertit la réponse brute de l'API du fournisseur
// (Resend, SES GetEmailIdentity, Brevo, Postmark, Mailgun, SendGrid, Lumail)
// en plan normalisé, prêt pour cloudflare-apply.mjs et dns-audit.mjs --expect.
//
//   node dns-plan.mjs --provider resend --domain mail.client.com --region eu-west-1 --rua dmarc@client.com
//   node dns-plan.mjs --provider ses --domain news.client.com --from-api identity.json --tracking click --format bind
import { readFileSync, writeFileSync } from "node:fs";
import { PROVIDERS, mxList } from "./lib/providers.mjs";
import { orgDomain } from "./lib/dns.mjs";

const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(`--${n}`); return i === -1 ? d : argv[i + 1]; };
const has = (n) => argv.includes(`--${n}`);

const providerId = opt("provider");
const domain = opt("domain")?.toLowerCase().replace(/\.$/, "");
const provider = PROVIDERS[providerId];
if (!provider || !domain) {
  console.log(`Usage: node dns-plan.mjs --provider <${Object.keys(PROVIDERS).join("|")}> --domain mail.client.com [options]
  --zone client.com            zone DNS (défaut : domaine organisationnel)
  --region eu-west-1           région du fournisseur (MX feedback SES/Resend)
  --return-path bounce         étiquette du sous-domaine MAIL FROM (défaut fournisseur)
  --from-api reponse.json      réponse brute de l'API du fournisseur (remplace les <jetons>)
  --rua dmarc@client.com       adresse des rapports DMARC agrégés
  --dmarc-policy none|quarantine|reject   (défaut none = phase d'observation)
  --dmarc-on root|domain       où publier DMARC (défaut root = couvre tous les sous-domaines)
  --tracking click             sous-domaine de tracking des liens (CNAME)
  --tracking-target host       cible du CNAME de tracking
  --existing-spf "v=spf1 …"    SPF déjà présent sur le From (fusion)
  --bimi https://…/logo.svg    ajoute default._bimi (+ --vmc https://…/cert.pem)
  --tls-rpt tls@client.com     ajoute _smtp._tls sur la zone
  --aprf aprf@client.com       ajoute le record APRF (draft IETF) pour les sélecteurs DKIM
  --format md|json|bind|all    (défaut md)   --out plan.json`);
  process.exit(2);
}

const zone = (opt("zone") ?? orgDomain(domain)).toLowerCase();
const region = opt("region", provider.defaultRegion);
const rpLabel = opt("return-path", provider.returnPath?.label);
const records = [];
const notes = [];
const push = (r) => records.push({ required: true, ttl: 3600, ...r });

// ------------------------------------------------------------- import API
// Les noms renvoyés par les API sont soit absolus, soit relatifs à la zone,
// soit relatifs au domaine d'envoi. On normalise en FQDN.
const rel = domain === zone ? "" : domain.slice(0, -(zone.length + 1));
function fqdn(name) {
  const n = String(name ?? "@").toLowerCase().replace(/\.$/, "");
  if (n === "@" || n === "") return domain;
  if (n === domain || n.endsWith(`.${zone}`) || n === zone) return n;
  if (rel && (n === rel || n.endsWith(`.${rel}`))) return `${n}.${zone}`;
  return `${n}.${domain}`;
}
const purposeOf = (type, name, value) => {
  const v = String(value).toLowerCase(), n = String(name).toLowerCase();
  if (n.includes("_domainkey")) return n.includes("_aprf") ? "aprf" : "dkim";
  if (n.startsWith("_dmarc")) return "dmarc";
  if (v.startsWith("v=spf1")) return "spf";
  if (type === "MX") return "mail-from";
  if (/code|verification|site-verification/.test(v) || n.includes("_amazonses")) return "verification";
  if (type === "CNAME") return n.includes("bounce") || n.includes("pm-bounces") ? "mail-from" : "tracking";
  return "other";
};

function importApi(json) {
  const out = [];
  const add = (type, name, value, priority) => out.push({ type: String(type).toUpperCase(), name: fqdn(name), value: String(value), ...(priority != null ? { priority: Number(priority) } : {}), purpose: purposeOf(String(type).toUpperCase(), name, value), source: "api" });
  const j = json.data ?? json;
  if (Array.isArray(j.records)) {                                        // Resend
    for (const r of j.records) add(r.type, r.name, r.value, r.priority);
  } else if (j.DkimAttributes) {                                         // SES v2 GetEmailIdentity
    // La zone de signature varie selon la région/identité : ne pas coder « dkim.amazonses.com » en dur.
    const zoneDkim = j.DkimAttributes.SigningHostedZone ?? "dkim.amazonses.com";
    for (const t of j.DkimAttributes.Tokens ?? []) add("CNAME", `${t}._domainkey.${domain}`, `${t}.${zoneDkim}`);
    const mf = j.MailFromAttributes?.MailFromDomain;
    if (mf) { add("MX", mf, `feedback-smtp.${region}.amazonses.com`, 10); add("TXT", mf, "v=spf1 include:amazonses.com ~all"); }
  } else if (j.dns_records || j.dnsRecords && !Array.isArray(j.dnsRecords)) { // Brevo
    for (const r of Object.values(j.dns_records ?? j.dnsRecords)) if (r?.value) add(r.type ?? "TXT", r.host_name ?? r.hostName ?? "@", r.value);
  } else if (Array.isArray(j.dnsRecords)) {                              // Lumail / format normalisé
    for (const r of j.dnsRecords) add(r.type, r.name, r.value, r.priority);
  } else if (j.DKIMPendingHost || j.DKIMHost) {                           // Postmark
    add("TXT", j.DKIMPendingHost || j.DKIMHost, j.DKIMPendingTextValue || j.DKIMTextValue);
    if (j.ReturnPathDomain) add("CNAME", j.ReturnPathDomain, j.ReturnPathDomainCNAMEValue ?? "pm.mtasv.net");
  } else if (j.sending_dns_records) {                                    // Mailgun
    for (const r of j.sending_dns_records) add(r.record_type, r.name, r.value);
    if (has("receive")) for (const r of j.receiving_dns_records ?? []) add(r.record_type, r.name ?? domain, r.value, r.priority);
  } else if (j.dns && (j.dns.dkim1 || j.dns.mail_cname)) {               // SendGrid domain authentication
    for (const r of Object.values(j.dns)) if (r?.host) add(r.type ?? "CNAME", r.host, r.data);
  } else {
    throw new Error("Format de réponse API non reconnu : fournir un tableau records/dnsRecords.");
  }
  return out;
}

// ------------------------------------------------------------- plan
if (opt("from-api")) {
  const imported = importApi(JSON.parse(readFileSync(opt("from-api"), "utf8")));
  for (const r of imported) push(r);
  notes.push(`Enregistrements importés depuis l'API ${provider.label} (${imported.length}). Valeurs exactes : ne pas les retaper.`);
} else {
  if (provider.verification) push(provider.verification(domain));
  for (const r of provider.dkim.records(domain)) push(r);
  if (provider.returnPath && rpLabel) {
    const host = `${rpLabel}.${domain}`;
    if (provider.returnPath.type === "mx") {
      for (const mxHost of mxList(provider, region)) {
        push({ type: "MX", name: host, value: mxHost, priority: provider.returnPath.priority ?? 10, purpose: "mail-from" });
      }
      if (provider.spfInclude) push({ type: "TXT", name: host, value: `v=spf1 include:${provider.spfInclude} ~all`, purpose: "spf" });
    } else {
      push({ type: "CNAME", name: host, value: provider.returnPath.target, purpose: "mail-from" });
    }
  }
  notes.push("Les valeurs entre <chevrons> sont propres au domaine : créer d'abord le domaine chez le fournisseur, puis relancer avec --from-api.");
}

// SPF sur le From quand le fournisseur utilise le domaine d'envoi comme enveloppe.
if (provider.spfOn === "from" && !records.some((r) => r.purpose === "spf" && r.name === domain)) {
  const existing = opt("existing-spf");
  let value = `v=spf1 include:${provider.spfInclude} ~all`;
  if (existing) {
    value = existing.includes(`include:${provider.spfInclude}`) ? existing
      : existing.replace(/\s([~+\-?]?all)\b/, ` include:${provider.spfInclude} $1`);
    notes.push("SPF fusionné avec l'existant : un seul TXT v=spf1 par nom.");
  }
  push({ type: "TXT", name: domain, value, purpose: "spf" });
}

// DMARC : un seul enregistrement, de préférence sur la zone (hérité par les sous-domaines via sp=).
if (!records.some((r) => r.purpose === "dmarc")) {
  const where = opt("dmarc-on", "root") === "domain" ? domain : zone;
  const policy = opt("dmarc-policy", "none");
  const rua = [opt("rua"), provider.dmarcRua && has("provider-rua") ? provider.dmarcRua : null].filter(Boolean).map((m) => `mailto:${m}`).join(",");
  const value = `v=DMARC1; p=${policy}${where === zone && domain !== zone ? `; sp=${policy}` : ""}${rua ? `; rua=${rua}` : ""}`;
  push({ type: "TXT", name: `_dmarc.${where}`, value, purpose: "dmarc", required: false });
  notes.push(`DMARC sur _dmarc.${where} : ne l'ajouter que s'il n'existe pas déjà (un seul DMARC par nom). Démarrer en p=none avec rua, puis quarantine (éventuellement avec t=y, qui remplace pct depuis RFC 9989), puis reject après 2 à 4 semaines de rapports propres.`);
}
if (opt("rua") && orgDomain(opt("rua").split("@")[1] ?? zone) !== zone) {
  const dest = opt("rua").split("@")[1];
  notes.push(`rua externe (${dest}) : ${dest} doit publier TXT ${zone}._report._dmarc.${dest} = "v=DMARC1".`);
}

// Tracking des liens
if (opt("tracking")) {
  const host = opt("tracking").includes(".") ? opt("tracking") : `${opt("tracking")}.${zone}`;
  const target = opt("tracking-target") ?? (provider.tracking ? (region === "eu" && provider.tracking.targetEu) || provider.tracking.target : "<cible fournie par la plateforme de tracking>");
  push({ type: "CNAME", name: host, value: target, purpose: "tracking", required: false });
  notes.push("Tracking : CNAME en DNS only (nuage gris) ; le certificat HTTPS est émis par le fournisseur/Cloudflare for SaaS une fois le CNAME visible.");
}

// Extras optionnels
if (opt("bimi")) {
  push({ type: "TXT", name: `default._bimi.${domain}`, value: `v=BIMI1; l=${opt("bimi")}${opt("vmc") ? `; a=${opt("vmc")}` : ";"}`, purpose: "bimi", required: false });
  notes.push("BIMI ignoré tant que DMARC n'est pas en quarantine/reject (pct=100). Gmail/Apple exigent un VMC ou CMC (a=).");
}
if (opt("tls-rpt")) push({ type: "TXT", name: `_smtp._tls.${zone}`, value: `v=TLSRPTv1; rua=mailto:${opt("tls-rpt")}`, purpose: "tls-rpt", required: false });
if (opt("aprf")) {
  push({ type: "TXT", name: `*._aprf._domainkey.${domain}`, value: `v=APRFv1; rua=mailto:${opt("aprf")}`, purpose: "aprf", required: false });
  notes.push("APRF = draft IETF (draft-ietf-mailmaint-aprf, adopté en oct. 2026) : seul Comcast envoie des rapports (bêta). Sans risque à publier ; si le rua est hors du domaine DKIM, la destination doit publier <selecteur>.<domaine DKIM>._aprf.<domaine destination>.");
}

const plan = { domain, zone, provider: providerId, region: provider.regions ? region : null, generatedAt: new Date().toISOString(), records, notes };

// ------------------------------------------------------------- sorties
const relName = (n) => (n === zone ? "@" : n.endsWith(`.${zone}`) ? n.slice(0, -(zone.length + 1)) : `${n}.`);
const md = () => [
  `### Plan DNS — ${domain} via ${provider.label}${plan.region ? ` (${plan.region})` : ""}`,
  "",
  "| Type | Nom (relatif à la zone " + zone + ") | Valeur | Prio | Rôle | Requis |",
  "|---|---|---|---|---|---|",
  ...records.map((r) => `| ${r.type} | \`${relName(r.name)}\` | \`${r.value}\` | ${r.priority ?? ""} | ${r.purpose} | ${r.required ? "oui" : "recommandé"} |`),
  "",
  ...notes.map((n) => `- ${n}`),
].join("\n");
const bind = () => [`; ${domain} via ${provider.label} — à coller dans la zone ${zone}`, ...records.map((r) => {
  const v = r.type === "TXT" ? `"${r.value}"` : r.type === "MX" ? `${r.priority ?? 10} ${r.value}.` : `${r.value}.`;
  return `${relName(r.name).padEnd(38)} ${String(r.ttl).padEnd(5)} IN ${r.type.padEnd(5)} ${v}`;
})].join("\n");

const format = opt("format", "md");
if (opt("out")) writeFileSync(opt("out"), JSON.stringify(plan, null, 2));
if (format === "json") console.log(JSON.stringify(plan, null, 2));
else if (format === "bind") console.log(bind());
else if (format === "all") console.log(`${md()}\n\n\`\`\`zone\n${bind()}\n\`\`\``);
else console.log(md());
