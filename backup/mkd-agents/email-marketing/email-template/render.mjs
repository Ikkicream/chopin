/**
 * render.mjs — compile Newsletter.tsx → HTML string
 * Usage: node render.mjs > output.html
 * Requires: npm install first
 */

import { render } from "@react-email/render";
import { createElement } from "react";
import { readFileSync, writeFileSync } from "fs";
import { createRequire } from "module";
import { fileURLToPath } from "url";
import path from "path";

// Dynamic import with tsx support via ts-node or direct import
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Load the compiled version if available, otherwise error
async function main() {
  let NewsletterModule;
  try {
    // Try importing directly (requires tsx or ts-node in path)
    NewsletterModule = await import("./emails/Newsletter.tsx");
  } catch {
    console.error("Cannot import Newsletter.tsx directly. Run: npx tsx render.mjs");
    process.exit(1);
  }

  const Newsletter = NewsletterModule.default || NewsletterModule.Newsletter;

  const html = await render(
    createElement(Newsletter, {
      date: new Date().toLocaleDateString("fr-FR", {
        year: "numeric",
        month: "long",
        day: "numeric",
      }),
    })
  );

  const outPath = path.join(__dirname, "newsletter.html");
  writeFileSync(outPath, html, "utf-8");
  console.log(`HTML written to ${outPath} (${html.length} bytes)`);
  process.stdout.write(html);
}

main().catch(console.error);
