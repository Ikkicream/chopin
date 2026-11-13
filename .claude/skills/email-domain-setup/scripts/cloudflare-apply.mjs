#!/usr/bin/env node
// Applique un plan DNS (sortie JSON de dns-plan.mjs) sur une zone Cloudflare.
// Par défaut : simulation (aucune écriture). --apply pour écrire.
// Idempotent : ne recrée pas ce qui existe, fusionne le SPF, ne touche jamais
// à un DMARC existant, refuse les conflits CNAME/MX sans --replace.
//
//   CF_API_TOKEN=… node cloudflare-apply.mjs plan.json            # simulation
//   CF_API_TOKEN=… node cloudflare-apply.mjs plan.json --apply    # écriture
//
// Token : permission « Zone → DNS → Edit » limitée à la zone concernée.
import { readFileSync } from "node:fs";
import { orgDomain } from "./lib/dns.mjs";

const argv = process.argv.slice(2);
const planPath = argv.find((a) => !a.startsWith("--"));
const APPLY = argv.includes("--apply");
const REPLACE = argv.includes("--replace");
const token = process.env.CF_API_TOKEN;
if (!planPath || !token) {
  console.error("Usage: CF_API_TOKEN=… node cloudflare-apply.mjs <plan.json> [--apply] [--replace] [--zone client.com]");
  process.exit(2);
}
const plan = JSON.parse(readFileSync(planPath, "utf8"));
const zoneName = argv.includes("--zone") ? argv[argv.indexOf("--zone") + 1] : plan.zone ?? orgDomain(plan.domain);

const API = "https://api.cloudflare.com/client/v4";
async function cf(method, path, body) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json();
  if (!json.success) throw new Error(`${method} ${path} → ${JSON.stringify(json.errors)}`);
  return json.result;
}

const unquote = (s) => String(s ?? "").replace(/^"|"$/g, "").replace(/"\s*"/g, "");
const same = (a, b) => unquote(a).toLowerCase().replace(/\.$/, "").trim() === unquote(b).toLowerCase().replace(/\.$/, "").trim();

function mergeSpf(existing, wanted) {
  const incs = wanted.match(/include:\S+/g) ?? [];
  let out = unquote(existing);
  for (const inc of incs) {
    if (out.toLowerCase().includes(inc.toLowerCase())) continue;
    out = /\s[~+\-?]?all\b/.test(out) ? out.replace(/\s([~+\-?]?all)\b/, ` ${inc} $1`) : `${out} ${inc} ~all`;
  }
  return out;
}

const zones = await cf("GET", `/zones?name=${encodeURIComponent(zoneName)}`);
if (!zones.length) {
  console.error(`Zone ${zoneName} introuvable pour ce token (DNS ailleurs que chez Cloudflare ?).`);
  process.exit(1);
}
const zoneId = zones[0].id;
console.log(`Zone ${zoneName} (${zoneId}) — ${APPLY ? "ÉCRITURE" : "simulation"}\n`);

let problems = 0;
for (const rec of plan.records) {
  const label = `${rec.type.padEnd(5)} ${rec.name}`;
  if (/[<>]/.test(rec.value) || /[<>]/.test(rec.name)) {
    console.log(`✗ ${label}  jeton non résolu (${rec.value}) — récupérer la valeur via l'API du fournisseur`);
    problems++;
    continue;
  }
  const atName = await cf("GET", `/zones/${zoneId}/dns_records?name=${encodeURIComponent(rec.name)}&per_page=100`);
  const sameType = atName.filter((r) => r.type === rec.type);
  const payload = {
    type: rec.type, name: rec.name, content: rec.value, ttl: 1, proxied: false,
    ...(rec.type === "MX" ? { priority: rec.priority ?? 10 } : {}),
    comment: `email-domain-setup ${plan.provider ?? ""} ${rec.purpose ?? ""}`.trim(),
  };
  let action = "create", target = null, note = "";

  if (rec.type === "CNAME" && atName.some((r) => r.type !== "CNAME")) {
    action = "conflict"; note = `d'autres records existent sur ce nom (${atName.map((r) => r.type).join(", ")}) : un CNAME ne peut pas cohabiter`;
  } else if (rec.type !== "CNAME" && atName.some((r) => r.type === "CNAME")) {
    action = "conflict"; note = "un CNAME occupe déjà ce nom";
  } else if (rec.purpose === "spf") {
    const cur = sameType.find((r) => /^"?v=spf1/i.test(r.content));
    if (cur) {
      const merged = mergeSpf(cur.content, rec.value);
      if (same(merged, cur.content)) action = "unchanged";
      else { action = "update"; target = cur; payload.content = merged; note = `SPF fusionné : ${merged}`; }
    }
  } else if (rec.purpose === "dmarc") {
    const cur = sameType.find((r) => /^"?v=DMARC1/i.test(r.content));
    if (cur) { action = "keep"; note = `DMARC existant conservé : ${unquote(cur.content)}`; }
  } else if (sameType.some((r) => same(r.content, rec.value) && (rec.type !== "MX" || r.priority === (rec.priority ?? 10)))) {
    action = "unchanged";
  } else if (rec.type === "CNAME" || rec.type === "MX" || (rec.type === "TXT" && rec.purpose === "dkim")) {
    const cur = sameType[0];
    if (cur) {
      if (REPLACE) { action = "update"; target = cur; note = `remplace ${unquote(cur.content)}`; }
      else { action = "conflict"; note = `existant différent : ${unquote(cur.content)} (relancer avec --replace)`; }
    }
  }
  if (rec.type === "CNAME" && atName.some((r) => r.type === "CNAME" && r.proxied)) note += " ⚠ CNAME proxifié existant : doit être DNS only";

  const icon = { create: "+", update: "~", unchanged: "=", keep: "=", conflict: "✗" }[action];
  console.log(`${icon} ${label}  ${action}${note ? ` — ${note}` : ""}`);
  if (action === "conflict") { problems++; continue; }
  if (!APPLY || action === "unchanged" || action === "keep") continue;
  if (action === "create") await cf("POST", `/zones/${zoneId}/dns_records`, payload);
  if (action === "update") await cf("PATCH", `/zones/${zoneId}/dns_records/${target.id}`, payload);
}

console.log(`\n${problems ? `${problems} point(s) à régler à la main.` : "Plan cohérent."}${APPLY ? "" : " Rien n'a été écrit (ajouter --apply)."}`);
process.exit(problems ? 1 : 0);
