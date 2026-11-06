#!/usr/bin/env node
// Auto-test des endpoints email d'une plateforme (local ou déployée) :
//   - les webhooks Resend et SES refusent un appel NON signé (400/401/403) ;
//   - l'endpoint one-click refuse un jeton invalide (400) et accepte un jeton
//     signé avec EMAIL_UNSUBSCRIBE_SECRET (200, sans redirection).
// N'utilise que vos propres URLs ; aucun email n'est envoyé.
//
//   EMAIL_UNSUBSCRIBE_SECRET=… node selftest.mjs --base-url http://localhost:3000
import { createHash, createHmac } from "node:crypto";

const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(`--${n}`); return i === -1 ? d : argv[i + 1]; };
const base = (opt("base-url") ?? "").replace(/\/$/, "");
if (!base) {
  console.log("Usage: EMAIL_UNSUBSCRIBE_SECRET=… node selftest.mjs --base-url https://app.plateforme.com [--resend-path /api/email/webhooks/resend] [--ses-path /api/email/webhooks/ses] [--unsub-path /api/email/unsubscribe]");
  process.exit(2);
}
const paths = {
  resend: opt("resend-path", "/api/email/webhooks/resend"),
  ses: opt("ses-path", "/api/email/webhooks/ses"),
  unsub: opt("unsub-path", "/api/email/unsubscribe"),
};
const results = [];
const check = (name, ok, detail) => results.push({ name, ok, detail });

async function post(url, body, headers) {
  try {
    const res = await fetch(url, { method: "POST", headers, body, redirect: "manual", signal: AbortSignal.timeout(8000) });
    return res.status;
  } catch (e) {
    return `ERR ${e.cause?.code ?? e.message}`;
  }
}

// Webhooks : un appel non signé doit être refusé.
for (const [name, path, body, headers] of [
  ["Webhook Resend", paths.resend, JSON.stringify({ type: "email.bounced", data: { email_id: "selftest" } }), { "content-type": "application/json" }],
  ["Webhook SES (SNS)", paths.ses, JSON.stringify({ Type: "Notification", Message: "{}", Signature: "invalid", SigningCertURL: "https://evil.example/cert.pem" }), { "content-type": "text/plain; charset=UTF-8", "x-amz-sns-message-type": "Notification" }],
]) {
  const s = await post(base + path, body, headers);
  check(`${name} refuse un appel non signé`, [400, 401, 403].includes(s), `HTTP ${s}`);
}

// One-click : jeton invalide → 400 ; jeton valide → 200 sans redirection.
const form = { "content-type": "application/x-www-form-urlencoded" };
const bad = await post(`${base}${paths.unsub}/invalid.token`, "List-Unsubscribe=One-Click", form);
check("One-click refuse un jeton invalide", bad === 400, `HTTP ${bad}`);

const secret = process.env.EMAIL_UNSUBSCRIBE_SECRET;
if (secret) {
  const payload = { t: "selftest-tenant", h: createHash("sha256").update("selftest@example.invalid").digest("hex"), s: "marketing", v: 1 };
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const token = `${body}.${createHmac("sha256", secret).update(body).digest("base64url")}`;
  const good = await post(`${base}${paths.unsub}/${token}`, "List-Unsubscribe=One-Click", form);
  check("One-click accepte un jeton signé (200, sans redirection)", good === 200, `HTTP ${good}`);
} else {
  check("One-click avec jeton signé", false, "EMAIL_UNSUBSCRIBE_SECRET non défini : test sauté");
}

for (const r of results) console.log(`${r.ok ? "✓" : "✗"} ${r.name}  (${r.detail})`);
const failed = results.filter((r) => !r.ok).length;
console.log(failed ? `\n${failed} échec(s).` : "\nEndpoints conformes.");
process.exit(failed ? 1 : 0);
