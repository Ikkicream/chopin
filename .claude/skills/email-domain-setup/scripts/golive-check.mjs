#!/usr/bin/env node
// Contrôle « prêt pour le premier envoi » d'un domaine d'envoi.
// Vérifie, dans l'ordre de mise en service :
//   1. région du fournisseur (déduite du MX de retour, ou de l'API Resend)
//   2. sous-domaine dédié + SPF/DKIM du fournisseur + DMARC avec rua
//   3. webhooks bounces/plaintes branchés (endpoint joignable et signature exigée)
//   4. désinscription one-click : endpoint POST qui répond 2xx sans redirection
//   5. Google Postmaster Tools + Yahoo Sender Hub (indice DNS + confirmation)
//   6. plan de warm-up défini
// Rend GO / NO-GO. N'écrit rien nulle part ; les seuls appels sortants sont
// des lectures DNS, un GET sur l'API Resend (si RESEND_API_KEY) et deux POST de
// test vers VOS endpoints (webhook non signé, désinscription avec jeton de test).
//
//   node golive-check.mjs --domain news.client.com --provider resend --expect-region eu \
//     --webhook-url https://app.client.com/api/email/webhooks/resend \
//     --unsubscribe-url https://app.client.com/api/email/unsubscribe/TEST_TOKEN \
//     --confirmed postmaster,senderhub --warmup-start 2026-10-20
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { makeResolver, txt, mx, cname, orgDomain } from "./lib/dns.mjs";
import { PROVIDERS, returnPathHost } from "./lib/providers.mjs";

const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(`--${n}`); return i === -1 ? d : argv[i + 1]; };
const domain = opt("domain")?.toLowerCase();
const providerId = opt("provider", "resend");
const provider = PROVIDERS[providerId];
if (!domain || !provider) {
  console.log("Usage: node golive-check.mjs --domain news.client.com --provider resend|ses [--expect-region eu] [--return-path send.news.client.com] [--selectors …] [--webhook-url URL] [--unsubscribe-url URL] [--confirmed postmaster,senderhub] [--warmup-start AAAA-MM-JJ] [--json]");
  process.exit(2);
}
const here = dirname(fileURLToPath(import.meta.url));
const r = makeResolver();
const items = [];
const item = (step, status, title, detail = "") => items.push({ step, status, title, detail });
const confirmed = new Set(String(opt("confirmed", "")).split(",").map((s) => s.trim()).filter(Boolean));

// ---------------------------------------------------------------- 1. Région
const rpHost = opt("return-path") ?? returnPathHost(provider, domain);
let region = null;
if (rpHost && !rpHost.includes("<")) {
  const mxs = await mx(r, rpHost);
  region = mxs.map((m) => m.exchange.match(/feedback-smtp\.([a-z0-9-]+)\.amazonses\.com/)?.[1]).find(Boolean) ?? null;
}
if (providerId === "resend" && process.env.RESEND_API_KEY) {
  try {
    const res = await fetch("https://api.resend.com/domains", { headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}` } });
    const list = (await res.json()).data ?? [];
    const d = list.find((x) => x.name === domain);
    if (d) { region = d.region ?? region; item(1, d.status === "verified" ? "ok" : "fail", `Resend : domaine ${d.status}`, `id ${d.id}`); }
    else item(1, "fail", `Resend : ${domain} absent du compte`, "Créer le domaine (POST /domains) en choisissant la région AVANT de poser les DNS.");
  } catch (e) { item(1, "warn", "API Resend injoignable", e.message); }
}
const wanted = opt("expect-region");
if (!region && rpHost && !rpHost.includes("<") && (await cname(r, rpHost))) {
  // Resend (depuis août 2026) peut publier le Return-Path en CNAME : la région n'apparaît plus dans le DNS.
  item(1, "fail", "Région non lisible dans le DNS (Return-Path en CNAME)", "Définir RESEND_API_KEY pour la lire via l'API, ou vérifier la région dans le tableau de bord.");
} else if (!region) item(1, "fail", "Région indéterminée", `Pas de MX feedback-smtp.<région>.amazonses.com sur ${rpHost ?? "le Return-Path"}.`);
else if (wanted && !region.startsWith(wanted)) item(1, "fail", `Région ${region} ≠ ${wanted} attendue`, "Non modifiable : supprimer le domaine et le recréer dans la bonne région, puis refaire les DNS.");
else item(1, "ok", `Région ${region}${wanted ? " (conforme)" : ""}`);

// ---------------------------------------------------------------- 2. DNS
const auditArgs = [join(here, "dns-audit.mjs"), domain, "--provider", providerId, "--json"];
if (opt("selectors")) auditArgs.push("--selectors", opt("selectors"));
if (opt("return-path")) auditArgs.push("--return-path", opt("return-path"));
let audit;
try { audit = JSON.parse(execFileSync(process.execPath, auditArgs, { encoding: "utf8" })); }
catch (e) { audit = JSON.parse(e.stdout); }
const keys = new Set(audit.findings.map((f) => f.key));
const errors = audit.findings.filter((f) => f.severity === "error");
if (domain === orgDomain(domain)) item(2, "warn", "Envoi depuis la racine", "Préférer un sous-domaine dédié (news. pour le marketing) pour isoler la réputation.");
else item(2, "ok", `Sous-domaine dédié : ${domain}`);
if (errors.length) item(2, "fail", `${errors.length} erreur(s) DNS`, errors.map((f) => `${f.title} ‹${f.key}›`).join("\n"));
else item(2, "ok", "SPF (Return-Path) et DKIM du fournisseur en place");
const dmarc = audit.findings.find((f) => f.key.startsWith("domain:dmarc:") && /v=DMARC1/i.test(f.detail ?? ""));
if (keys.has("domain:dmarc:missing")) item(2, "fail", "DMARC absent", "Publier v=DMARC1; p=none; rua=mailto:<boîte réellement lue> sur la racine.");
else if (keys.has("domain:dmarc:no-rua")) item(2, "fail", "DMARC sans rua", "Ajouter rua=mailto:<boîte lue ou parseur DMARC> : sans rapports, impossible de durcir en quarantine après le warm-up.");
else item(2, "ok", "DMARC avec rua", dmarc?.detail ?? "");

// ---------------------------------------------------------------- 3. Webhooks
const hook = opt("webhook-url");
if (!hook) item(3, "fail", "Webhooks bounces/plaintes non vérifiés", "Passer --webhook-url : email.bounced et email.complained (Resend) ou Bounce/Complaint (SES) doivent être branchés AVANT le premier envoi.");
else {
  try {
    const res = await fetch(hook, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ type: "email.bounced", data: { email_id: "golive-check" } }), redirect: "manual", signal: AbortSignal.timeout(8000) });
    if ([400, 401, 403].includes(res.status)) item(3, "ok", `Webhook joignable et refuse un appel non signé (HTTP ${res.status})`);
    else if (res.ok) item(3, "fail", `Webhook accepte un appel NON signé (HTTP ${res.status})`, "Vérifier la signature (Svix pour Resend, SNS pour SES) avant de traiter l'événement.");
    else item(3, "fail", `Webhook HTTP ${res.status}`, "Route absente ou en erreur.");
  } catch (e) { item(3, "fail", "Webhook injoignable", e.message); }
  if (providerId === "resend" && process.env.RESEND_API_KEY) {
    try {
      const res = await fetch("https://api.resend.com/webhooks", { headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}` } });
      if (res.ok) {
        const list = (await res.json()).data ?? [];
        const w = list.find((x) => x.endpoint === hook);
        const ev = new Set(w?.events ?? []);
        if (!w) item(3, "fail", "Aucun webhook Resend vers cette URL");
        else if (!ev.has("email.bounced") || !ev.has("email.complained")) item(3, "fail", "Webhook Resend sans email.bounced / email.complained", [...ev].join(", "));
        else item(3, "ok", "Webhook Resend abonné à email.bounced et email.complained");
      }
    } catch { /* API webhooks indisponible : le test HTTP ci-dessus suffit */ }
  }
}

// ---------------------------------------------------------------- 4. Désinscription one-click
const unsub = opt("unsubscribe-url");
if (!unsub) item(4, "fail", "Endpoint de désinscription non vérifié", "Passer --unsubscribe-url avec un jeton de TEST : il doit accepter POST « List-Unsubscribe=One-Click ».");
else if (!unsub.startsWith("https://")) item(4, "fail", "URL de désinscription non HTTPS", "RFC 8058 exige HTTPS.");
else {
  try {
    const res = await fetch(unsub, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: "List-Unsubscribe=One-Click", redirect: "manual", signal: AbortSignal.timeout(8000) });
    if (res.status >= 200 && res.status < 300) item(4, "ok", `POST one-click accepté (HTTP ${res.status})`);
    else if (res.status >= 300 && res.status < 400) item(4, "fail", `Redirection (HTTP ${res.status})`, "Le POST doit désinscrire directement, sans page ni redirection.");
    else item(4, "fail", `HTTP ${res.status} sur le POST one-click`, "Accepter un POST sans cookie ni CSRF : le jeton signé dans l'URL suffit.");
  } catch (e) { item(4, "fail", "Endpoint de désinscription injoignable", e.message); }
}

// ---------------------------------------------------------------- 5. Postmaster / Sender Hub
const org = orgDomain(domain);
const gsv = [...await txt(r, org), ...await txt(r, domain)].some((t) => t.startsWith("google-site-verification="));
if (confirmed.has("postmaster")) item(5, "ok", "Google Postmaster Tools : inscrit (confirmé)");
else item(5, "fail", "Google Postmaster Tools non confirmé", `${gsv ? "Un TXT google-site-verification existe" : "Aucun TXT google-site-verification"} sur ${org}. Ajouter ${org} dans Postmaster Tools AVANT le premier envoi, puis relancer avec --confirmed postmaster.`);
if (confirmed.has("senderhub")) item(5, "ok", "Yahoo Sender Hub : inscrit (confirmé)");
else item(5, "fail", "Yahoo Sender Hub non confirmé", `Inscrire le domaine DKIM (d=${domain}) à la boucle de plaintes (CFL) AVANT le premier envoi, puis --confirmed senderhub.`);

// ---------------------------------------------------------------- 6. Warm-up
const ws = opt("warmup-start");
if (!ws) item(6, "fail", "Pas de plan de warm-up", "node warmup-plan.mjs --target <volume/jour> --start <date> ; appliquer le plafond journalier par domaine dans la plateforme.");
else {
  const week = Math.max(1, Math.floor((Date.now() - new Date(ws).getTime()) / (7 * 86400000)) + 1);
  const cap = Date.now() < new Date(ws).getTime() ? 400 : Math.min(400 * 2 ** (week - 1), Number(opt("target", Infinity)));
  item(6, "ok", `Warm-up démarré le ${ws}`, `Semaine ${week} : plafond ≈ ${cap.toLocaleString("fr-FR")}/jour, segments les plus engagés d'abord.`);
}

// ---------------------------------------------------------------- Verdict
const blocking = items.filter((i) => i.status === "fail");
const verdict = blocking.length ? "NO-GO" : "GO";
if (argv.includes("--json")) {
  console.log(JSON.stringify({ domain, provider: providerId, region, verdict, items }, null, 2));
} else {
  const icon = { ok: "✓", warn: "!", fail: "✗" };
  const titles = ["", "Région", "DNS : sous-domaine, SPF/DKIM, DMARC + rua", "Webhooks bounces / plaintes", "Désinscription one-click (RFC 8058)", "Postmaster Tools / Sender Hub", "Warm-up"];
  console.log(`\nMise en service — ${domain} (${provider.label}) : ${verdict}\n`);
  for (let s = 1; s <= 6; s++) {
    console.log(`${s}. ${titles[s]}`);
    for (const i of items.filter((x) => x.step === s)) {
      console.log(`   [${icon[i.status]}] ${i.title}`);
      if (i.detail && i.status !== "ok") console.log(`       ${i.detail.split("\n").join("\n       ")}`);
      else if (i.detail && s === 6) console.log(`       ${i.detail}`);
    }
  }
  console.log(blocking.length ? `\n${blocking.length} point(s) bloquant(s) avant le premier envoi.\n` : "\nPrêt pour le premier envoi (au plafond de warm-up).\n");
}
process.exit(blocking.length ? 1 : 0);
