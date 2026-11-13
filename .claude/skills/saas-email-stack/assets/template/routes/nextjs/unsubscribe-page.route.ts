// app/unsubscribe/[token]/route.ts — page visible du lien de pied de page.
// GET n'a AUCUN effet (les scanners de liens et antivirus ouvrent les URL) : la désinscription
// se fait au clic sur le bouton, qui envoie le même POST que le one-click RFC 8058.
import { readUnsubscribeToken } from "@/lib/email/compliance/unsubscribe";

export const dynamic = "force-dynamic";

export async function GET(_req: Request, ctx: { params: Promise<{ token: string }> }) {
  const { token } = await ctx.params;
  const valid = readUnsubscribeToken(token, process.env.EMAIL_UNSUBSCRIBE_SECRET!) !== null;
  const html = `<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Désinscription</title>
<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem;line-height:1.5">
${valid ? `<h1>Se désinscrire</h1>
<p>Vous ne recevrez plus nos emails marketing. Les emails liés à votre compte (factures, sécurité) continueront.</p>
<form method="post" action="/api/email/unsubscribe/${encodeURIComponent(token)}">
<input type="hidden" name="List-Unsubscribe" value="One-Click"><button type="submit" style="padding:.6rem 1.2rem">Confirmer la désinscription</button></form>`
  : `<h1>Lien invalide</h1><p>Ce lien de désinscription n'est pas valide. Répondez à l'email pour être retiré de la liste.</p>`}
</body></html>`;
  return new Response(html, { status: valid ? 200 : 400, headers: { "content-type": "text/html; charset=utf-8" } });
}
