#!/usr/bin/env node
// Score de contenu 0–100 avant envoi : reproduction des 11 critères du
// « Content Deliverability Checker » de Lumail (mêmes points), plus des
// contrôles de conformité hors score (One-Click unsubscribe, clipping Gmail…).
//
// Usage :
//   node content-score.mjs email.html --subject "Votre facture de mars" --brand "Acme"
//   node content-score.mjs message.eml --brand acme.fr --json
import { readFileSync } from "node:fs";

const argv = process.argv.slice(2);
const opt = (name) => { const i = argv.indexOf(`--${name}`); return i === -1 ? undefined : argv[i + 1]; };
const flag = (name) => argv.includes(`--${name}`);
const file = argv.find((a, i) => !a.startsWith("--") && !argv[i - 1]?.startsWith("--"));
if (!file) {
  console.log("Usage: node content-score.mjs <email.html|.md|.txt|.eml> [--subject \"…\"] [--brand \"Nom ou domaine\"] [--json]");
  process.exit(2);
}

let raw = readFileSync(file, "utf8");
let headers = null;
let subject = opt("subject");

// --- .eml minimal : en-têtes + partie text/html (quoted-printable / base64)
if (/\.eml$/i.test(file)) {
  const split = raw.search(/\r?\n\r?\n/);
  const head = raw.slice(0, split).replace(/\r?\n[ \t]+/g, " ");
  headers = {};
  for (const line of head.split(/\r?\n/)) {
    const i = line.indexOf(":");
    if (i > 0) headers[line.slice(0, i).trim().toLowerCase()] = line.slice(i + 1).trim();
  }
  subject ??= headers.subject;
  const parts = raw.split(/\r?\n--[^\r\n]+/);
  const pick = (type) => parts.find((p) => new RegExp(`content-type:\\s*${type}`, "i").test(p));
  const decode = (p) => {
    if (!p) return "";
    const s = p.search(/\r?\n\r?\n/);
    const h = p.slice(0, s), body = p.slice(s).trim();
    if (/base64/i.test(h)) return Buffer.from(body.replace(/\s+/g, ""), "base64").toString("utf8");
    if (/quoted-printable/i.test(h)) {
      return Buffer.from(body.replace(/=\r?\n/g, "").replace(/=([0-9A-F]{2})/gi, (_, x) => String.fromCharCode(parseInt(x, 16))), "latin1").toString("utf8");
    }
    return body;
  };
  headers._hasText = !!pick("text/plain");
  raw = decode(pick("text/html")) || decode(pick("text/plain")) || raw.slice(split);
}

const isHtml = /<\/?[a-z][\s\S]*>/i.test(raw);
const html = isHtml ? raw : raw.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>').replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img alt="$1" src="$2">');
const text = html
  .replace(/<(script|style|head)[\s\S]*?<\/\1>/gi, " ")
  .replace(/<br\s*\/?>|<\/(p|div|tr|h\d|li)>/gi, "\n")
  .replace(/<[^>]+>/g, " ")
  .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&#39;|&apos;/g, "'").replace(/&quot;/g, '"')
  .replace(/[ \t]+/g, " ").trim();
const words = text.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w));
const links = [...html.matchAll(/<a\b[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi)].map((m) => ({ href: m[1], label: m[2].replace(/<[^>]+>/g, "").trim() }));
const images = [...html.matchAll(/<img\b[^>]*>/gi)].map((m) => ({ tag: m[0], alt: m[0].match(/alt=["']([^"']*)["']/i)?.[1] ?? null, src: m[0].match(/src=["']([^"']*)["']/i)?.[1] ?? "" }));

// ------------------------------------------------------------------ règles
const UNSUB_VAR = /\{\{\s*(unsubscribe(_?url|_?link)?|unsubscribeUrl)\s*\}\}|\*\|UNSUB\|\*|%unsubscribe(_url)?%|\[unsubscribe\]|\{\{\s*mirror\s*\}\}|\$unsubscribe|\{%\s*unsubscribe/i;
const UNSUB_WORD = /unsubscribe|d[ée]sinscri|d[ée]sabonn|se retirer de la liste|darse de baja|cancelar suscripci|disiscriv|annulla iscrizione|abmelden|abbestellen|cancelar inscri/i;
const isUnsubLink = (l) => UNSUB_VAR.test(l.href) || UNSUB_WORD.test(l.href) || UNSUB_WORD.test(l.label);

const ADDRESS = [
  /\{\{\s*(org-adresse|org_address|address|company_address)\s*\}\}|@org-adresse/i,
  /\b\d{1,5}\s+[\p{L}0-9.' -]{2,40}\b(st|street|ave|avenue|rd|road|blvd|boulevard|lane|ln|drive|dr|way|suite)\b[^\n]{0,60}\b[A-Z]{2}\s*\d{5}(-\d{4})?/iu,
  /\b\d{1,4}\s*(bis|ter)?,?\s*(rue|avenue|av\.|boulevard|bd|place|pl\.|chemin|all[ée]e|impasse|quai|route|cours|square|passage)\s[^\n]{2,60}?\b\d{5}\b\s*[\p{L}-]+/iu,
  /\b(calle|via|viale|piazza|stra(ss|ß)e|rua|avenida)\s[^\n]{2,50}\d{4,5}/iu,
  /\b(P\.?\s?O\.?\s?Box|Bo[iî]te Postale|\bBP\s?\d+|\bCS\s?\d{4,5})\b/i,
];

const REASON = [
  /you('| a)re receiving this (e-?mail|message|newsletter)/i, /you (received|get|are getting) this (e-?mail|message) because/i,
  /you (signed up|subscribed|registered|opted in|created an account)/i, /because you (signed up|subscribed|registered|requested|purchased|bought)/i,
  /(tu re[çc]ois|vous recevez|vous avez re[çc]u|tu as re[çc]u) (ce|cet|cette) (mail|e-?mail|courriel|message|newsletter)/i,
  /(car|parce que) (tu t'es|vous vous [êe]tes|tu es|vous [êe]tes) (inscrit|abonn)/i, /vous [êe]tes inscrit|tu es inscrit|suite à votre (inscription|commande|demande)/i,
  /(est[áa]s recibiendo|recibes|has recibido) este (correo|e-?mail|mensaje)/i, /porque te (has suscrito|registraste|suscribiste)/i,
  /(ricevi|stai ricevendo|hai ricevuto) questa (e-?mail|mail|newsletter)/i, /perch[ée] ti sei (iscritt|registrat)/i,
  /Sie erhalten diese (E-?Mail|Nachricht)/i, /weil Sie sich .* (angemeldet|registriert)/i,
  /(voc[êe] est[áa] recebendo|recebeu) (este|esse) (e-?mail|mensagem)/i,
];

const SPAM_WORDS = [
  // EN
  "act now", "limited time", "expires today", "urgent", "don't delete", "do it today", "while supplies last", "last chance", "once in a lifetime",
  "free money", "earn cash", "earn money", "double your money", "get rich", "make money", "cash bonus", "extra income", "risk-free", "risk free", "100% free",
  "no credit check", "lowest price", "best price", "cheap", "guaranteed", "money back", "no catch", "no strings attached", "investment opportunity",
  "click here", "click below", "verify your account", "confirm your identity", "update your account", "account suspended", "password expired", "unusual activity",
  "congratulations", "you're a winner", "you are a winner", "you have been selected", "you've been selected", "claim your prize", "winner", "prize", "jackpot", "lottery",
  "weight loss", "lose weight", "no prescription", "miracle cure", "viagra", "cialis", "pharmacy", "diet pills", "anti-aging",
  "this is not spam", "not spam", "dear friend", "100% satisfied", "no obligation", "order now", "buy now", "apply now", "call now", "special promotion",
  "bitcoin", "crypto giveaway", "wire transfer", "nigerian", "inheritance", "beneficiary",
  // FR
  "agissez maintenant", "offre limitée", "dernière chance", "expire aujourd'hui", "urgent", "ne supprimez pas", "temps limité",
  "argent facile", "gagnez de l'argent", "gagner de l'argent", "devenez riche", "doublez votre argent", "revenu supplémentaire", "sans risque", "100% gratuit", "gratuit",
  "satisfait ou remboursé", "meilleur prix", "prix le plus bas", "sans engagement", "garanti", "aucun frais", "crédit sans justificatif",
  "cliquez ici", "vérifiez votre compte", "confirmez votre identité", "mettez à jour votre compte", "compte suspendu", "activité inhabituelle",
  "félicitations", "vous avez gagné", "vous êtes le gagnant", "vous avez été sélectionné", "réclamez votre prix", "gagnant", "loterie",
  "perte de poids", "perdre du poids", "sans ordonnance", "remède miracle", "cure miracle", "ceci n'est pas un spam", "achetez maintenant", "commandez maintenant",
  // ES
  "actúe ahora", "tiempo limitado", "última oportunidad", "dinero fácil", "gane dinero", "hazte rico", "sin riesgo", "100% gratis", "haga clic aquí", "haz clic aquí",
  "verifique su cuenta", "felicidades", "usted ha ganado", "has ganado", "ha sido seleccionado", "pérdida de peso", "sin receta", "cura milagrosa", "compre ahora",
  // IT
  "agisci ora", "tempo limitato", "ultima occasione", "soldi facili", "guadagna soldi", "diventa ricco", "senza rischi", "100% gratis", "clicca qui",
  "verifica il tuo account", "congratulazioni", "hai vinto", "sei stato selezionato", "perdita di peso", "senza ricetta", "cura miracolosa", "compra ora",
];

const SHORTENERS = /\b(bit\.ly|tinyurl\.com|t\.co|goo\.gl|ow\.ly|is\.gd|buff\.ly|adf\.ly|tiny\.cc|cutt\.ly|rb\.gy|shorturl\.at|rebrand\.ly|bl\.ink|t\.ly|s\.id|v\.gd|qr\.co|lnkd\.in|short\.io)\//i;
const CAPS_OK = new Set(["API", "URL", "HTML", "CEO", "ROI", "AWS", "LLC", "INC", "USA", "FAQ", "SaaS", "HTTP", "HTTPS", "SMTP", "DKIM", "SPF", "DMARC", "RGPD", "GDPR", "TVA", "SIRET", "SIREN", "PDF", "NASA", "UNESCO", "CNIL", "IBAN", "SEPA", "EUR", "USD", "B2B", "B2C", "CRM", "SEO", "JSON", "HTML5", "IOS", "MCP"]);

const brand = (opt("brand") ?? "").trim();
const checks = [];
const check = (id, label, max, score, reason, fix = "") => checks.push({ id, label, max, score: Math.max(0, Math.min(max, score)), reason, fix });

// 1. Lien de désinscription — 25
const unsub = links.some(isUnsubLink) || UNSUB_VAR.test(html);
check("unsubscribe", "Lien de désinscription", 25, unsub ? 25 : 0, unsub ? "présent" : "aucun lien de désinscription",
  "Ajouter un lien visible dans le pied de page ({{unsubscribeUrl}}), en plus des en-têtes List-Unsubscribe.");

// 2. Adresse postale — 10
const addr = ADDRESS.some((re) => re.test(text) || re.test(html));
check("physical_address", "Adresse postale", 10, addr ? 10 : 0, addr ? "adresse détectée" : "aucune adresse postale", "Ajouter l'adresse de l'expéditeur dans le pied de page (CAN-SPAM, LCEN).");

// 3. Raison de l'envoi — 10
const textNoDefault = text.replace(/don'?t want to receive these emails\??/gi, "");
const reason = REASON.some((re) => re.test(textNoDefault));
check("reason_for_sending", "Raison de l'envoi", 10, reason ? 10 : 0, reason ? "phrase « pourquoi vous recevez cet email » trouvée" : "pas de phrase expliquant pourquoi le destinataire reçoit l'email",
  "Ex. « Vous recevez cet email car vous vous êtes inscrit sur acme.fr ». La ligne de désinscription par défaut ne compte pas.");

// 4. Longueur de l'objet — 10
const sl = (subject ?? "").trim().length;
check("subject_length", "Longueur de l'objet", 10, sl === 0 ? 0 : sl >= 20 && sl <= 70 ? 10 : 5,
  subject === undefined ? "objet non fourni (--subject)" : `${sl} caractères`, "Viser 20–70 caractères, l'essentiel dans les 30 premiers.");

// 5. Ratio image / texte — 10 (règle : ~1 image pour 200 mots, alt obligatoire)
const imgCount = images.filter((i) => !/width=["']?1["']?|height=["']?1["']?/i.test(i.tag)).length;
const missingAlt = images.filter((i) => i.alt === null || i.alt === "").length;
let imgScore = 10;
if (imgCount > 0) {
  // 1 image autorisée par tranche de 200 mots (un logo seul passe toujours si le texte est réel).
  const allowed = Math.max(1, Math.ceil(words.length / 200));
  imgScore = words.length < 20 ? 0 : imgCount <= allowed ? 10 : imgCount <= allowed * 2 ? 6 : 2;
  imgScore -= Math.min(3, missingAlt);
}
check("image_ratio", "Ratio image/texte", 10, imgScore, `${imgCount} image(s), ${words.length} mots, ${missingAlt} sans alt`, "≈ 1 image pour 200 mots, texte alternatif sur chaque image, jamais un email 100 % image.");

// 6. Mots déclencheurs — 10 (−3 par occurrence)
const hay = `${subject ?? ""}\n${text}`.toLowerCase();
const hits = [...new Set(SPAM_WORDS)].filter((w) => new RegExp(`(^|[^\\p{L}])${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}($|[^\\p{L}])`, "iu").test(hay));
check("spam_words", "Mots déclencheurs de spam", 10, 10 - 3 * hits.length, hits.length ? `trouvés : ${hits.join(", ")}` : "aucun", "Reformuler sans urgence artificielle ni promesse financière.");

// 7. Nombre de liens — 5
const realLinks = links.filter((l) => /^https?:/i.test(l.href) && !isUnsubLink(l));
check("link_count", "Nombre de liens", 5, realLinks.length <= 5 ? 5 : 2, `${realLinks.length} lien(s)`, "1 à 3 appels à l'action suffisent.");

// 8. Raccourcisseurs — 5
const short = links.filter((l) => SHORTENERS.test(l.href));
check("no_shorteners", "Pas d'URL raccourcie", 5, short.length ? 0 : 5, short.length ? short.map((l) => l.href).join(", ") : "aucune", "Utiliser des liens sur votre propre domaine (le tracking s'en charge).");

// 9. MAJUSCULES — 5 (max 2 mots de 4+ majuscules hors acronymes connus)
const capsWords = `${subject ?? ""} ${text}`.split(/[^\p{L}\p{N}]+/u).filter((w) => (w.match(/\p{Lu}/gu) ?? []).length >= 4 && w === w.toUpperCase() && !CAPS_OK.has(w) && !(brand && w.toLowerCase() === brand.toLowerCase()));
check("all_caps", "Pas d'abus de MAJUSCULES", 5, capsWords.length <= 2 ? 5 : 0, capsWords.length ? capsWords.slice(0, 10).join(", ") : "ok", "Éviter FREE, URGENT, PROMO… en capitales.");

// 10. Longueur du texte — 5
check("text_length", "Longueur du texte", 5, words.length >= 50 ? 5 : words.length >= 20 ? 2 : 0, `${words.length} mots`, "50 mots minimum : un email presque vide ressemble à du spam.");

// 11. Marque visible — 5 (nom, domaine seul ou logo dans le premier bloc)
const firstBlock = text.slice(0, 300).toLowerCase();
const brandTokens = brand ? [brand.toLowerCase(), brand.toLowerCase().replace(/\.[a-z]{2,}$/, "")] : [];
const logo = images.slice(0, 2).some((i) => /logo/i.test(i.src) || /logo/i.test(i.alt ?? "") || (brand && (i.alt ?? "").toLowerCase().includes(brandTokens[1])));
const branded = logo || (brandTokens.length && brandTokens.some((b) => b && firstBlock.includes(b))) || /\{\{\s*org-name\s*\}\}|@org-name/i.test(html.slice(0, 2000));
check("branding", "Marque identifiable", 5, branded ? 5 : 0, branded ? "marque visible en haut de l'email" : brand ? `« ${brand} » absent du début de l'email` : "aucun logo détecté (passer --brand)", "Logo avec alt ou nom de la marque dans le premier écran.");

// ------------------------------------------------------------------ hors score
const flags = [];
const size = Buffer.byteLength(html, "utf8");
if (size > 102 * 1024) flags.push({ severity: "warn", message: `HTML de ${(size / 1024).toFixed(0)} Ko : Gmail tronque au-delà de 102 Ko (lien de désinscription caché).` });
if (/<script|javascript:|<form|<iframe|<embed|<object/i.test(html)) flags.push({ severity: "error", message: "Script, formulaire ou iframe : bloqués par les webmails et signal de phishing." });
if (headers) {
  const lu = headers["list-unsubscribe"], lup = headers["list-unsubscribe-post"];
  if (!lu) flags.push({ severity: "error", message: "En-tête List-Unsubscribe absent (exigé Gmail/Yahoo/Microsoft pour le marketing)." });
  else if (!/<https:\/\//i.test(lu)) flags.push({ severity: "error", message: "List-Unsubscribe sans URI https : le one-click RFC 8058 exige une URL HTTPS." });
  if (lu && !/List-Unsubscribe=One-Click/i.test(lup ?? "")) flags.push({ severity: "error", message: "List-Unsubscribe-Post: List-Unsubscribe=One-Click absent (RFC 8058)." });
  if (lu && !headers["dkim-signature"]) flags.push({ severity: "info", message: "Pas de DKIM-Signature dans ce .eml (normal pour un brouillon ; l'ESP signe à l'envoi et doit couvrir les deux en-têtes List-Unsubscribe)." });
  if (!headers._hasText) flags.push({ severity: "info", message: "Pas de partie text/plain : recommandé (multipart/alternative)." });
  if (/no-?reply@/i.test(headers.from ?? "")) flags.push({ severity: "warn", message: "Expéditeur noreply@ : empêche les réponses, signal d'engagement négatif." });
  if (!headers["message-id"]) flags.push({ severity: "warn", message: "Message-ID absent (RFC 5322) — l'ESP l'ajoute normalement." });
}

const total = checks.reduce((s, c) => s + c.score, 0);
const band = total >= 90 ? "Excellent" : total >= 75 ? "Bon" : total >= 50 ? "À améliorer" : "Risqué";

if (flag("json")) {
  console.log(JSON.stringify({ file, subject: subject ?? null, score: total, band, checks, flags }, null, 2));
} else {
  console.log(`\nScore de contenu : ${total}/100 — ${band}${subject ? `\nObjet : « ${subject} »` : ""}\n`);
  for (const c of checks) {
    const ok = c.score === c.max;
    console.log(`${ok ? "✓" : c.score === 0 ? "✗" : "~"} ${c.label.padEnd(28)} ${String(c.score).padStart(2)}/${c.max}  ${c.reason}`);
    if (!ok && c.fix) console.log(`  → ${c.fix}`);
  }
  if (flags.length) {
    console.log("\nConformité (hors score) :");
    for (const f of flags) console.log(`  [${f.severity}] ${f.message}`);
  }
  console.log("\nRappel : un bon score de contenu ne garantit pas la boîte de réception — DNS, réputation et qualité de liste comptent davantage.\n");
}
