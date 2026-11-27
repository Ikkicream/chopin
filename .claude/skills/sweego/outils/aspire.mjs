// Aspire la doc Sweego (Docusaurus, rendu JS) et la reconvertit en Markdown.
// Usage : node aspire.mjs <dossier_sortie>
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const BASE = "https://learn.sweego.io";
const OUT = process.argv[2] || "out";
const pages = JSON.parse(fs.readFileSync("pages.json", "utf8"));
const rt = fs.readFileSync("rt.js", "utf8");

// runtime : deux dictionnaires id→nom et id→hash
const dicts = [...rt.matchAll(/\{((?:\d+:"[^"]+",?)+)\}/g)].map(m =>
  Object.fromEntries([...m[1].matchAll(/(\d+):"([^"]+)"/g)].map(x => [x[1], x[2]])));
const [noms, hashs] = dicts.sort((a, b) => Object.keys(a).length - Object.keys(b).length);
const nom2id = Object.fromEntries(Object.entries(noms).map(([i, n]) => [n, i]));

const FRAG = Symbol("frag");
const h = (type, props) => ({ type, props: props || {} });
const composant = (nom) => { const f = (p) => h(f, p); f.nomComposant = nom; return f; };
const placeholder = (id) => new Proxy({}, {
  get: (_, k) => (k === "__esModule" ? true : k === "default" ? composant("M" + id) : composant(String(k))),
});

function charger(code) {
  const ctx = { globalThis: {}, JSON, Object, Array, Symbol, Promise, console };
  ctx.globalThis.webpackChunksweego_openapi_docs = [];
  ctx.self = ctx.globalThis;
  vm.createContext(ctx);
  vm.runInContext(code, ctx);
  const [[, mods]] = ctx.globalThis.webpackChunksweego_openapi_docs;
  const cache = {};
  const req = (id) => {
    id = String(id);
    if (cache[id]) return cache[id].exports;
    if (id === "74848") return { jsx: h, jsxs: h, Fragment: FRAG };
    if (id === "28453") return { R: () => ({}), x: () => null };
    if (id === "96540") return { default: {}, createElement: h, Fragment: FRAG, useState: v => [v, () => {}], useEffect: () => {} };
    if (mods[id]) {
      const m = (cache[id] = { exports: {} });
      mods[id](m, m.exports, req);
      return m.exports;
    }
    return placeholder(id);
  };
  req.r = () => {};
  req.d = (ex, defs) => { for (const k in defs) Object.defineProperty(ex, k, { get: typeof defs[k] === "function" ? defs[k] : () => defs[k], enumerable: true, configurable: true }); };
  req.p = "/";
  req.n = (m) => { const g = () => (m && m.__esModule ? m.default : m); g.a = g(); return g; };
  // Les clés numériques sont triées : la page n'est pas forcément la première.
  for (const id of Object.keys(mods)) {
    if (/metadata:\(\)=>/.test(String(mods[id]))) return req(id);
  }
  throw new Error("module de page introuvable");
}

// ── Rendu Markdown ──────────────────────────────────────────────────────────
const txt = (n) => rendre(n).replace(/\n+/g, " ").trim();
function enfants(p) { return rendre(p.children); }
const estElement = (v) => v && typeof v === "object" && ("props" in v) && ("type" in v);
const contientElement = (v) => estElement(v) || (Array.isArray(v) && v.some(contientElement));
function donnees(props) {
  const d = {};
  for (const [k, v] of Object.entries(props))
    if (k !== "children" && typeof v !== "function" && !contientElement(v)) d[k] = v;
  return Object.keys(d).length ? d : null;
}
function elementsEnProps(props) {
  let s = "";
  for (const [k, v] of Object.entries(props))
    if (k !== "children" && contientElement(v)) s += rendre(v);
  return s;
}
function rendre(n) {
  if (n == null || n === false || n === true) return "";
  if (typeof n === "string" || typeof n === "number") return String(n);
  if (Array.isArray(n)) return n.map(rendre).join("");
  let { type, props } = n;
  if (typeof type === "function" && !type.nomComposant) {
    try { return rendre(type(props)); } catch (e) { return `\n[composant non rendu : ${e.message}]\n`; }
  }
  if (type === FRAG) return enfants(props);
  if (typeof type === "string") {
    const c = () => enfants(props);
    switch (type) {
      case "h1": case "h2": case "h3": case "h4": case "h5": case "h6":
        return `\n\n${"#".repeat(+type[1])} ${txt(props.children)}\n\n`;
      case "p": return `\n\n${c().trim()}\n\n`;
      case "strong": case "b": return `**${c()}**`;
      case "em": case "i": return `*${c()}*`;
      case "code": {
        const lang = (props.className || "").replace("language-", "");
        const v = c();
        return props.className || v.includes("\n") ? `\n\`\`\`${lang}\n${v.replace(/\n$/, "")}\n\`\`\`\n` : "`" + v + "`";
      }
      case "pre": return `\n${c()}\n`;
      case "a": return `[${txt(props.children)}](${props.href || ""})`;
      case "img": return `![${props.alt || ""}](${props.src || ""})`;
      case "br": return "\n";
      case "hr": return "\n\n---\n\n";
      case "li": return `\n- ${c().trim().replace(/\n/g, "\n  ")}`;
      case "ul": case "ol": return `\n${c()}\n`;
      case "blockquote": return `\n> ${c().trim().replace(/\n/g, "\n> ")}\n`;
      case "table": return `\n\n${c()}\n\n`;
      case "thead": { const r = c(); const n = (r.match(/\|/g) || []).length - 1; return r + "|" + " --- |".repeat(Math.max(n, 1)) + "\n"; }
      case "tbody": return c();
      case "tr": return "|" + c() + "\n";
      case "th": case "td": return " " + txt(props.children).replace(/\|/g, "\\|") + " |";
      case "details": return `\n${c()}\n`;
      case "summary": return `\n**${txt(props.children)}**\n`;
      default: return c();
    }
  }
  // composant inconnu : son contenu + ses données (schémas d'API, onglets…)
  const nom = type?.nomComposant || "?";
  const d = donnees(props);
  let s = "";
  if (d && "label" in d && Object.keys(d).length <= 4) s += `\n\n**[${d.label}]**\n`;
  else if (d && "type" in d && "title" in d === false && Object.keys(d).length === 1) s += `\n\n> **${String(d.type).toUpperCase()}**\n`;
  else if (d) s += `\n\n<!-- ${nom} -->\n\`\`\`json\n${JSON.stringify(d, null, 1).slice(0, 60000)}\n\`\`\`\n`;
  return s + elementsEnProps(props) + enfants(props);
}

const rapport = [];
for (const [cle, source] of pages) {
  const id = nom2id[cle];
  const url = `${BASE}/assets/js/${cle}.${hashs[id]}.js`;
  const dest = path.join(OUT, source.replace(/\.mdx?$/, ".md"));
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error("HTTP " + r.status);
    const ex = charger(await r.text());
    const meta = ex.metadata || {};
    const corps = rendre(ex.default ? ex.default({}) : null)
      .replace(/\n{3,}/g, "\n\n").trim();
    const entete = `# ${meta.title || cle}\n\nSource : ${BASE}${meta.permalink || ""}\n` +
      (meta.description ? `\n> ${meta.description}\n` : "") + "\n";
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, entete + corps + "\n");
    rapport.push({ source, ok: true, octets: corps.length, titre: meta.title });
  } catch (e) {
    rapport.push({ source, ok: false, erreur: String(e.message || e).slice(0, 200) });
  }
}
fs.writeFileSync(path.join(OUT, "_rapport.json"), JSON.stringify(rapport, null, 1));
const ko = rapport.filter(r => !r.ok);
console.log(`${rapport.length - ko.length}/${rapport.length} pages`, ko.slice(0, 10));
