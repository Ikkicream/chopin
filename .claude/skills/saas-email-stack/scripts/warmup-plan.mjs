#!/usr/bin/env node
// Plan de montée en charge (warm-up) d'un domaine ou sous-domaine d'envoi neuf.
// Règle : 300–500 emails/jour la première semaine, contacts les plus engagés
// d'abord, puis doublement chaque semaine jusqu'au volume cible. Le plafond
// journalier produit ici est celui que la plateforme doit appliquer par domaine.
//
//   node warmup-plan.mjs --target 40000 --start 2026-10-20
//   node warmup-plan.mjs --target 40000 --first 300 --json
const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(`--${n}`); return i === -1 ? d : argv[i + 1]; };

const target = Number(opt("target", 0));
const first = Math.min(500, Math.max(300, Number(opt("first", 400))));
const start = new Date(opt("start", new Date().toISOString().slice(0, 10)));
if (!target) {
  console.log("Usage: node warmup-plan.mjs --target <emails/jour visés> [--first 300..500] [--start AAAA-MM-JJ] [--json]");
  process.exit(2);
}

// Ordre d'ouverture des segments : on n'élargit l'audience que quand le volume l'exige.
const SEGMENTS = [
  { key: "engaged_30d", label: "ont ouvert ou cliqué ces 30 derniers jours" },
  { key: "engaged_90d", label: "ont ouvert ou cliqué ces 90 derniers jours" },
  { key: "new_confirmed", label: "inscrits récents confirmés (double opt-in)" },
  { key: "engaged_180d", label: "engagés ces 180 derniers jours" },
  { key: "rest", label: "reste de la liste active (jamais les adresses inactives > 12 mois)" },
];

const weeks = [];
let cap = first;
for (let w = 0; ; w++) {
  const capped = Math.min(cap, target);
  const from = new Date(start.getTime() + w * 7 * 86400000);
  const to = new Date(from.getTime() + 6 * 86400000);
  weeks.push({
    week: w + 1,
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
    dailyCap: capped,
    segments: SEGMENTS.slice(0, Math.min(SEGMENTS.length, w + 1)).map((s) => s.key),
  });
  if (capped >= target || w > 30) break;
  cap *= 2;
}

// Conditions pour passer à la semaine suivante (sinon on reste au palier).
const gates = {
  maxBounceRate: 0.02,     // bounces permanents / envoyés
  maxComplaintRate: 0.001, // plaintes / délivrés (Gmail exige < 0,3 %, viser < 0,1 %)
  minSample: 200,          // en dessous, on ne conclut pas
};

if (argv.includes("--json")) {
  console.log(JSON.stringify({ target, start: start.toISOString().slice(0, 10), weeks, segments: SEGMENTS, gates }, null, 2));
} else {
  console.log(`\nWarm-up → ${target.toLocaleString("fr-FR")} emails/jour (${weeks.length} semaines)\n`);
  console.log("Sem.  Du          Au          Plafond/jour  Segments ouverts");
  for (const w of weeks) {
    console.log(`${String(w.week).padEnd(5)} ${w.from}  ${w.to}  ${String(w.dailyCap.toLocaleString("fr-FR")).padStart(12)}  ${w.segments.join(", ")}`);
  }
  console.log("\nSegments, dans l'ordre d'ouverture :");
  SEGMENTS.forEach((s, i) => console.log(`  ${i + 1}. ${s.key} — ${s.label}`));
  console.log(`\nPasser au palier suivant seulement si, sur la semaine écoulée (≥ ${gates.minSample} envois) :`);
  console.log(`  bounces permanents < ${gates.maxBounceRate * 100} %, plaintes < ${gates.maxComplaintRate * 100} %, pas de retards massifs (4.7.x).`);
  console.log("Sinon : rester au même palier une semaine de plus et nettoyer la liste.");
  console.log("DMARC : passer de p=none à p=quarantine à la fin du warm-up si les rapports rua sont propres.\n");
}
