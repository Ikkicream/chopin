#!/usr/bin/env node
// Audit DNS d'un domaine d'envoi : SPF, DKIM, DMARC (avec héritage), MAIL FROM /
// Return-Path, BIMI, MTA-STS, TLS-RPT, APRF, domaine de tracking.
// Zéro dépendance. Les clés de règle (domain:dmarc:monitoring-only, …) sont
// stables : elles servent d'identifiants d'alerte dans une plateforme.
//
// Usage :
//   node dns-audit.mjs mail.client.com --provider resend
//   node dns-audit.mjs client.com --selectors google,brevo1,brevo2 --return-path bounce.client.com
//   node dns-audit.mjs mail.client.com --expect plan.json --json
import { readFileSync } from "node:fs";
import {
  makeResolver, txt, cname, mx, a, parseTags, dkimKeyInfo, dmarcLookup, spfWalk, spfAll, orgDomain,
} from "./lib/dns.mjs";
import { PROVIDERS, returnPathHost } from "./lib/providers.mjs";

const COMMON_SELECTORS = [
  "resend", "brevo1", "brevo2", "mail", "google", "selector1", "selector2", "s1", "s2", "k1", "k2", "k3",
  "default", "dkim", "smtp", "mta", "pm", "mailjet", "mte1", "scph0125", "sendgrid", "mandrill", "mxvault",
  "pdk1", "pdk2", "cf-bounce", "krs", "pic", "zoho", "protonmail", "protonmail2", "protonmail3",
];

function parseArgs(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t.startsWith("--")) {
      const k = t.slice(2);
      const next = argv[i + 1];
      if (next === undefined || next.startsWith("--")) out[k] = true;
      else { out[k] = next; i++; }
    } else out._.push(t);
  }
  return out;
}

const args = parseArgs(process.argv.slice(2));
const domain = (args._[0] ?? "").toLowerCase().replace(/\.$/, "");
if (!domain || args.help) {
  console.log(`Usage: node dns-audit.mjs <domaine-d-envoi> [options]
  --provider <${Object.keys(PROVIDERS).join("|")}>  préréglages (sélecteurs DKIM, return-path, include SPF)
  --selectors a,b,c        sélecteurs DKIM à vérifier (sinon : préréglage + liste courante)
  --return-path <host>     hôte MAIL FROM / Return-Path (ex: send.mail.client.com)
  --tracking <host>        domaine de tracking des liens (ex: click.client.com)
  --expect <plan.json>     compare au plan généré par dns-plan.mjs
  --resolver 1.1.1.1,8.8.8.8
  --fetch-mta-sts          télécharge aussi la politique MTA-STS en HTTPS
  --json                   sortie JSON (pour une API / un job)`);
  process.exit(domain ? 0 : 2);
}

const r = makeResolver(args.resolver ? String(args.resolver).split(",") : undefined);
const provider = args.provider ? PROVIDERS[args.provider] : null;
if (args.provider && !provider) {
  console.error(`Fournisseur inconnu : ${args.provider}. Connus : ${Object.keys(PROVIDERS).join(", ")}`);
  process.exit(2);
}

const findings = [];
const add = (key, severity, title, detail = "", fix = "") => findings.push({ key, severity, title, detail, fix });

// ---------------------------------------------------------------- SPF (domaine)
async function checkSpf(host, { role, expectInclude }) {
  const records = (await txt(r, host)).filter((t) => /^v=spf1(\s|$)/i.test(t.trim()));
  const prefix = role === "return-path" ? "domain:mail-from:spf-" : "domain:spf:";
  const before = findings.filter((f) => f.severity === "error").length;
  if (records.length === 0) {
    if (role === "return-path") {
      add(`${prefix}missing`, "error", `Pas de SPF sur le Return-Path ${host}`,
        "Le SPF est évalué sur le domaine d'enveloppe (MAIL FROM), pas sur le From.",
        `TXT ${host} "v=spf1 include:${expectInclude ?? "<fournisseur>"} ~all"`);
    } else {
      add(`${prefix}missing`, provider?.spfOn === "from" ? "error" : "info", `Pas de SPF sur ${host}`,
        provider?.spfOn === "from"
          ? "Ce fournisseur utilise le domaine d'envoi lui-même comme MAIL FROM."
          : "Normal si l'envoi passe par un Return-Path dédié (le SPF y est évalué). Un SPF sur le From reste utile si d'autres outils envoient avec ce domaine en enveloppe.",
        provider?.spfOn === "from" ? `TXT ${host} "v=spf1 include:${provider.spfInclude} ~all"` : "");
    }
    return;
  }
  if (records.length > 1) {
    add(`${prefix}multiple`, "error", `${records.length} enregistrements SPF sur ${host}`,
      records.join("\n"), "Fusionner en un seul TXT v=spf1 (sinon permerror → SPF échoue partout).");
  }
  const rec = records[0];
  const walk = await spfWalk(r, host);
  const all = spfAll(rec);
  if (walk.lookups > 10) {
    add(`${prefix}too-many-lookups`, "error", `SPF ${host} : ${walk.lookups} requêtes DNS (> 10)`,
      rec, "Retirer les include inutiles ou déplacer l'envoi tiers sur un sous-domaine dédié (un SPF par sous-domaine).");
  } else if (walk.lookups >= 8) {
    add(`${prefix}lookups-near-limit`, "warn", `SPF ${host} : ${walk.lookups}/10 requêtes DNS`, rec,
      "Marge faible : tout nouvel include peut casser le SPF.");
  }
  if (walk.voids > 2) add(`${prefix}void-lookups`, "error", `SPF ${host} : ${walk.voids} include vides (> 2)`, rec, "Supprimer les include qui ne publient plus de SPF.");
  for (const e of walk.errors) add(`${prefix}syntax`, "warn", `SPF ${host} : ${e}`);
  if (all === "+all" || all === "?all") {
    add(`${prefix}permissive-all`, "error", `SPF ${host} se termine par ${all}`, rec, "Utiliser ~all (ou -all une fois DMARC en place).");
  } else if (all === "none") {
    add(`${prefix}no-all`, "warn", `SPF ${host} sans mécanisme all`, rec, "Terminer par ~all.");
  }
  if (expectInclude && !walk.tree.some((n) => n.domain === expectInclude.toLowerCase())) {
    add(`${prefix}provider-include-missing`, "error", `SPF ${host} n'inclut pas ${expectInclude}`, rec,
      `Ajouter include:${expectInclude} avant le all.`);
  }
  if (findings.filter((f) => f.severity === "error").length === before) {
    add(`${prefix}ok`, "ok", `SPF ${host} valide (${walk.lookups}/10 requêtes, ${all})`, rec);
  }
}

// ---------------------------------------------------------------- DMARC
async function checkDmarc() {
  const d = await dmarcLookup(r, domain);
  if (!d.host) {
    add("domain:dmarc:missing", "error", `Aucun DMARC pour ${domain} (ni sur ${orgDomain(domain)})`,
      "Gmail/Yahoo/Microsoft exigent DMARC (p=none minimum) pour l'envoi en volume.",
      `TXT _dmarc.${orgDomain(domain)} "v=DMARC1; p=none; rua=mailto:dmarc@${orgDomain(domain)}"`);
    return null;
  }
  if (d.records.length > 1) {
    add("domain:dmarc:multiple", "error", `${d.records.length} DMARC sur _dmarc.${d.host}`, d.records.join("\n"),
      "Il doit y avoir un seul TXT DMARC à ce nom.");
  }
  if (d.records.length === 0) {
    add("domain:dmarc:malformed", "error", `_dmarc.${d.host} ne commence pas par v=DMARC1`, d.all.join("\n"),
      "Corriger la syntaxe : v=DMARC1; p=none|quarantine|reject");
    return null;
  }
  const rec = d.records[0];
  const tags = parseTags(rec);
  const via = d.inherited ? ` (hérité de ${d.host})` : "";
  if (!["none", "quarantine", "reject"].includes((tags.p ?? "").toLowerCase())) {
    add("domain:dmarc:malformed", "error", `DMARC${via} : p= absent ou invalide`, rec, "p=none, quarantine ou reject.");
    return tags;
  }
  // Politique effective : sp= s'applique aux sous-domaines quand l'enregistrement est hérité.
  const effective = (d.inherited && tags.sp ? tags.sp : tags.p).toLowerCase();
  const which = d.inherited && tags.sp ? "sp" : "p";
  if (effective === "none") {
    add("domain:dmarc:monitoring-only", "warn", `DMARC${via} en surveillance seule (${which}=none)`, rec,
      `Passer ${which}=quarantine puis reject sur _dmarc.${d.host} une fois les rapports propres.`);
  } else {
    add("domain:dmarc:enforced", "ok", `DMARC${via} appliqué (${which}=${effective})`, rec);
  }
  // RFC 9989 (DMARCbis, mai 2026) supprime pct, rf et ri, et ajoute t= (test), np= et psd=.
  if (tags.pct && tags.pct !== "100") {
    add("domain:dmarc:legacy-pct", "warn", `DMARC pct=${tags.pct} (tag supprimé par RFC 9989)`, rec,
      "Les récepteurs DMARCbis ignorent pct : la politique s'applique à 100 %. Pour un déploiement progressif, utiliser t=y.");
  }
  if ((tags.t ?? "").toLowerCase() === "y") {
    add("domain:dmarc:testing", "warn", "DMARC t=y : mode test (politique appliquée un cran en dessous)", rec,
      "reject agit comme quarantine, quarantine comme none. Retirer t=y une fois les rapports propres (BIMI exige une politique pleinement appliquée).");
  }
  if (!d.inherited && domain === orgDomain(domain) && !tags.np && (tags.sp ?? tags.p) !== "reject") {
    add("domain:dmarc:no-np", "info", "Pas de np= (sous-domaines inexistants)", rec,
      "np=reject bloque l'usurpation via des sous-domaines qui n'existent pas (RFC 9989).");
  }
  for (const legacy of ["rf", "ri"]) {
    if (tags[legacy]) add("domain:dmarc:legacy-tag", "info", `Tag ${legacy}= obsolète (RFC 9989)`, rec, "Sans effet : peut être retiré.");
  }
  if (!tags.rua) add("domain:dmarc:no-rua", "info", "DMARC sans rua= (pas de rapports agrégés)", rec, "Ajouter rua=mailto:… pour piloter le passage à reject.");
  if (tags.rua) {
    for (const uri of tags.rua.split(",")) {
      const dest = uri.trim().replace(/^mailto:/i, "").split("!")[0].split("@")[1]?.toLowerCase();
      if (dest && orgDomain(dest) !== orgDomain(d.host)) {
        // Rapport externe : le destinataire doit autoriser via <domaine>._report._dmarc.<dest>
        const auth = (await txt(r, `${d.host}._report._dmarc.${dest}`)).some((t) => /^v=DMARC1/i.test(t));
        const wildcard = (await txt(r, `*._report._dmarc.${dest}`)).some((t) => /^v=DMARC1/i.test(t));
        if (!auth && !wildcard) {
          add("domain:dmarc:external-rua-unauthorized", "warn", `rua vers ${dest} sans autorisation externe`,
            `${d.host}._report._dmarc.${dest} absent`, `Le destinataire ${dest} doit publier TXT "${d.host}._report._dmarc.${dest}" = "v=DMARC1"`);
        }
      }
    }
  }
  if (tags.adkim === "s" || tags.aspf === "s") {
    add("domain:dmarc:strict-alignment", "info", "Alignement strict (adkim/aspf=s)", rec,
      "Avec un sous-domaine d'envoi, l'alignement strict casse si DKIM d= ou le Return-Path diffère exactement du From.");
  }
  return tags;
}

// ---------------------------------------------------------------- DKIM
async function checkDkim() {
  let selectors = args.selectors ? String(args.selectors).split(",").map((s) => s.trim()).filter(Boolean) : [];
  const explicit = selectors.length > 0 || (provider?.dkim.selectors?.length ?? 0) > 0;
  if (!selectors.length && provider) selectors = [...(provider.dkim.selectors ?? [])];
  if (!selectors.length) selectors = COMMON_SELECTORS;
  let found = 0;
  for (const sel of selectors) {
    const host = `${sel}._domainkey.${domain}`;
    const target = await cname(r, host);
    const records = (await txt(r, host)).filter((t) => /(^|;)\s*(v=DKIM1|p=|k=)/i.test(t));
    if (!records.length) {
      if (explicit) {
        add("domain:dkim:missing", "error", `DKIM absent : ${host}`,
          target ? `CNAME → ${target} mais la cible ne renvoie pas de clé` : "Ni CNAME ni TXT.",
          "Copier exactement l'enregistrement fourni par l'ESP (ne pas inventer les tokens, pas de proxy Cloudflare).");
      }
      continue;
    }
    found++;
    const info = dkimKeyInfo(parseTags(records[0]));
    const how = target ? `CNAME → ${target}` : "TXT";
    if (info.revoked) add("domain:dkim:revoked", "warn", `DKIM ${sel} révoqué (p= vide)`, host);
    else if (info.type === "rsa" && info.bits < 1024) add("domain:dkim:weak", "error", `DKIM ${sel} : RSA ${info.bits} bits`, `${host} (${how})`, "Régénérer en 2048 bits.");
    else if (info.type === "rsa" && info.bits < 2048) add("domain:dkim:weak", "warn", `DKIM ${sel} : RSA ${info.bits} bits`, `${host} (${how})`, "2048 bits recommandé (M3AAWG).");
    else add("domain:dkim:ok", "ok", `DKIM ${sel} : ${info.type.toUpperCase()} ${info.bits} bits (${how})`, host);
  }
  if (!found && !explicit) {
    const sesWithoutTokens = provider?.dkim.kind === "ses-easy";
    add("domain:dkim:missing", sesWithoutTokens ? "warn" : "error", `Aucun DKIM trouvé parmi ${selectors.length} sélecteurs courants`,
      "Le sélecteur réel est visible dans l'en-tête DKIM-Signature (s=) d'un email reçu.", "Relancer avec --selectors <s>.");
  }
  if (provider?.dkim.kind === "ses-easy" && !args.selectors) {
    add("domain:dkim:tokens-needed", "info", "SES Easy DKIM : 3 tokens propres au domaine",
      "Passer --selectors tok1,tok2,tok3 (GetEmailIdentity → DkimAttributes.Tokens).");
  }
}

// ---------------------------------------------------------------- MAIL FROM / Return-Path
async function checkReturnPath() {
  const host = args["return-path"] ? String(args["return-path"]).toLowerCase() : provider ? returnPathHost(provider, domain) : null;
  if (!host) return;
  if (host.includes("<")) {
    add("domain:mail-from:host-needed", "info", `Return-Path ${provider.label} : nom propre au compte`, "", "Passer --return-path <hôte> (copié depuis le fournisseur).");
    return;
  }
  const p = provider?.returnPath;
  if (p?.type === "cname") {
    const target = await cname(r, host);
    if (!target) add("domain:mail-from:cname-missing", "error", `Return-Path ${host} : CNAME absent`, "", `CNAME ${host} → ${p.target}`);
    else if (p.target && !p.target.includes("<") && target.toLowerCase() !== p.target.toLowerCase()) {
      add("domain:mail-from:cname-mismatch", "error", `Return-Path ${host} → ${target}`, `attendu ${p.target}`);
    } else add("domain:mail-from:ok", "ok", `Return-Path ${host} → ${target}`);
    return;
  }
  const mxs = await mx(r, host);
  if (!mxs.length) {
    add("domain:mail-from:mx-missing", "error", `MAIL FROM ${host} : pas de MX`,
      "Sans MX, les bounces ne reviennent pas et le fournisseur repasse sur son propre domaine (SPF non aligné).",
      `MX ${host} 10 ${p?.mx ? [p.mx("<region>")].flat().join(" / ") : "<serveur feedback du fournisseur>"}`);
  } else {
    add("domain:mail-from:mx-ok", "ok", `MAIL FROM ${host} : MX ${mxs.map((m) => `${m.priority} ${m.exchange}`).join(", ")}`);
  }
  await checkSpf(host, { role: "return-path", expectInclude: provider?.spfInclude });
}

// ---------------------------------------------------------------- BIMI / MTA-STS / TLS-RPT / APRF / MX
async function checkExtras(dmarcTags) {
  const bimi = (await txt(r, `default._bimi.${domain}`)).filter((t) => /bimi/i.test(t));
  if (bimi.length) {
    const t = parseTags(bimi[0]);
    if (!/^BIMI1$/i.test(t.v ?? "") || (t.l && !/^https:\/\//i.test(t.l))) {
      add("domain:bimi:malformed", "warn", "BIMI mal formé", bimi[0], "v=BIMI1; l=https://…/logo.svg; a=https://…/vmc.pem (ou supprimer).");
    } else {
      const enforced = dmarcTags && ["quarantine", "reject"].includes((dmarcTags.p ?? "").toLowerCase())
        && (!dmarcTags.pct || dmarcTags.pct === "100") && (dmarcTags.t ?? "n").toLowerCase() !== "y" && (dmarcTags.sp ?? "").toLowerCase() !== "none";
      add(enforced ? "domain:bimi:ok" : "domain:bimi:needs-enforcement", enforced ? "ok" : "warn",
        enforced ? "BIMI publié" : "BIMI publié mais DMARC non appliqué (ignoré par les boîtes)", bimi[0]);
      if (!t.a) add("domain:bimi:no-certificate", "info", "BIMI sans a= (VMC/CMC)", "Gmail et Apple n'affichent le logo qu'avec un certificat VMC ou CMC.");
    }
  }

  const org = orgDomain(domain);
  const sts = (await txt(r, `_mta-sts.${org}`)).filter((t) => /^v=STSv1/i.test(t));
  const tlsrpt = (await txt(r, `_smtp._tls.${org}`)).filter((t) => /^v=TLSRPTv1/i.test(t));
  if (sts.length) {
    add("domain:mta-sts:present", "ok", `MTA-STS publié sur ${org}`, sts[0]);
    if (args["fetch-mta-sts"]) {
      try {
        const res = await fetch(`https://mta-sts.${org}/.well-known/mta-sts.txt`, { signal: AbortSignal.timeout(6000) });
        const body = await res.text();
        const mode = body.match(/mode:\s*(\w+)/)?.[1];
        add(res.ok ? "domain:mta-sts:policy-ok" : "domain:mta-sts:policy-unreachable", res.ok ? "ok" : "error",
          res.ok ? `Politique MTA-STS : mode=${mode}` : `Politique MTA-STS HTTP ${res.status}`, body.slice(0, 300));
      } catch (e) {
        add("domain:mta-sts:policy-unreachable", "error", "Politique MTA-STS injoignable", String(e.message));
      }
    }
  } else {
    add("domain:mta-sts:absent", "info", `Pas de MTA-STS sur ${org}`, "Protège la réception (inbound). Optionnel pour un sous-domaine d'envoi pur.");
  }
  if (tlsrpt.length) add("domain:tls-rpt:present", "ok", `TLS-RPT publié sur ${org}`, tlsrpt[0]);
  else add("domain:tls-rpt:absent", "info", `Pas de TLS-RPT sur ${org}`, `TXT _smtp._tls.${org} "v=TLSRPTv1; rua=mailto:tls@${org}"`);

  // APRF (draft-ietf-mailmaint-aprf) : <s>._aprf._domainkey.<d>, puis *._aprf._domainkey.<d>
  // (le wildcard répond à toute sonde), puis _aprf._domainkey.<d> sans sélecteur.
  const selectors = args.selectors ? String(args.selectors).split(",") : provider?.dkim.selectors ?? [];
  const aprfNames = [...(selectors.length ? selectors : ["x-probe"]).map((s) => `${s.trim()}._aprf._domainkey.${domain}`), `_aprf._domainkey.${domain}`];
  for (const name of aprfNames) {
    const rec = (await txt(r, name)).filter((t) => /^v=APRFv1/i.test(t));
    if (rec.length) {
      const ok = /rua=mailto:/i.test(rec[0]);
      add(ok ? "domain:aprf:present" : "domain:aprf:malformed", ok ? "ok" : "warn", ok ? `APRF publié (${name})` : "APRF sans rua=mailto: (ignoré)", rec[0]);
      break;
    }
  }

  const mxs = await mx(r, domain);
  if (mxs.length === 1 && mxs[0].exchange === "") add("domain:mx:null-mx", "info", `${domain} publie un Null MX (RFC 7505)`, "Les réponses directes au From seront rejetées : définir un Reply-To.");
  else if (!mxs.length) add("domain:mx:none", "info", `${domain} n'a pas de MX`, "Les réponses au From partiront dans le vide : utiliser Reply-To vers une boîte réelle.");
}

// ---------------------------------------------------------------- Tracking
async function checkTracking() {
  if (!args.tracking) return;
  const host = String(args.tracking).toLowerCase();
  const target = await cname(r, host);
  const ips = await a(r, host);
  if (!target && !ips.length) add("domain:tracking:missing", "error", `Domaine de tracking ${host} absent du DNS`);
  else add("domain:tracking:ok", "ok", `Tracking ${host} → ${target ?? ips.join(", ")}`);
  try {
    const res = await fetch(`https://${host}/`, { method: "HEAD", redirect: "manual", signal: AbortSignal.timeout(6000) });
    add("domain:tracking:https", "ok", `HTTPS répond sur ${host} (HTTP ${res.status})`);
  } catch (e) {
    add("domain:tracking:https-failed", "error", `HTTPS en échec sur ${host}`, String(e.cause?.code ?? e.message),
      "Certificat non émis ou CNAME proxifié : vérifier le custom hostname (Cloudflare for SaaS) ou le SSL du fournisseur.");
  }
}

// ---------------------------------------------------------------- Plan attendu
const norm = (v) => String(v ?? "").toLowerCase().replace(/^"|"$/g, "").replace(/\.$/, "").replace(/\s+/g, " ").trim();

async function checkExpected() {
  if (!args.expect) return;
  const plan = JSON.parse(readFileSync(String(args.expect), "utf8"));
  for (const rec of plan.records ?? []) {
    const name = rec.name.toLowerCase();
    const placeholder = /[<>]/.test(rec.value);
    let ok = false, got = "";
    if (rec.type === "CNAME") {
      got = (await cname(r, name)) ?? "";
      ok = placeholder ? !!got : norm(got) === norm(rec.value);
    } else if (rec.type === "MX") {
      const list = await mx(r, name);
      got = list.map((m) => `${m.priority} ${m.exchange}`).join(", ");
      ok = placeholder ? list.length > 0 : list.some((m) => norm(m.exchange) === norm(rec.value) && (rec.priority == null || m.priority === rec.priority));
    } else if (rec.type === "TXT") {
      const list = await txt(r, name);
      got = list.join(" | ");
      if (rec.purpose === "spf") {
        const inc = rec.value.match(/include:([^\s]+)/g) ?? [];
        ok = list.some((t) => /^v=spf1/i.test(t) && inc.every((i) => t.toLowerCase().includes(i.toLowerCase())));
      } else if (rec.purpose === "dmarc") {
        ok = list.some((t) => /^v=DMARC1/i.test(t));
      } else {
        ok = placeholder ? list.length > 0 : list.some((t) => norm(t) === norm(rec.value));
      }
    }
    add(`plan:${rec.purpose ?? rec.type.toLowerCase()}:${ok ? "ok" : "pending"}`, ok ? "ok" : "error",
      `${ok ? "✓" : "✗"} ${rec.type} ${name}`, ok ? "" : `attendu : ${rec.value}${rec.priority != null ? ` (prio ${rec.priority})` : ""}\ntrouvé : ${got || "rien"}`);
  }
}

// ---------------------------------------------------------------- Run
try {
  await checkSpf(domain, { role: "from", expectInclude: provider?.spfOn === "from" ? provider.spfInclude : undefined });
  const dmarcTags = await checkDmarc();
  await checkDkim();
  await checkReturnPath();
  await checkExtras(dmarcTags);
  await checkTracking();
  await checkExpected();
} catch (e) {
  add("dns:transient", "error", "Erreur DNS transitoire — ne pas conclure, relancer", e.message);
}

const rank = { error: 0, warn: 1, info: 2, ok: 3 };
findings.sort((x, y) => rank[x.severity] - rank[y.severity]);
const summary = Object.fromEntries(["error", "warn", "info", "ok"].map((s) => [s, findings.filter((f) => f.severity === s).length]));
const status = summary.error ? "FAILED" : summary.warn ? "WARNING" : "HEALTHY";

if (args.json) {
  console.log(JSON.stringify({ domain, orgDomain: orgDomain(domain), provider: args.provider ?? null, status, summary, checkedAt: new Date().toISOString(), findings }, null, 2));
} else {
  const icon = { error: "✗", warn: "!", info: "i", ok: "✓" };
  console.log(`\nAudit DNS — ${domain}${provider ? ` (${provider.label})` : ""} — ${status}`);
  console.log(`${summary.error} erreur(s), ${summary.warn} avertissement(s), ${summary.info} info, ${summary.ok} ok\n`);
  for (const f of findings) {
    console.log(`[${icon[f.severity]}] ${f.title}   ‹${f.key}›`);
    if (f.detail && f.severity !== "ok") console.log(`    ${f.detail.split("\n").join("\n    ")}`);
    if (f.fix) console.log(`    → ${f.fix}`);
  }
  console.log("");
}
process.exit(summary.error ? 1 : 0);
