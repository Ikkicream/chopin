// app/api/email/unsubscribe/[token]/route.ts — désinscription one-click (RFC 8058).
//
// Les messageries (Gmail, Yahoo, Apple Mail) font un POST serveur à serveur avec le
// corps « List-Unsubscribe=One-Click » : pas de cookie, pas de session, pas de CSRF.
// On répond 200 sans redirection ni page. Le jeton signé est la seule autorisation.
// Le lien visible du pied de page pointe vers une page (/unsubscribe/[token]) dont le
// bouton envoie ce même POST.
import { handleOneClickUnsubscribe } from "@/lib/email/compliance/unsubscribe";
import { emailRepo } from "@/lib/email/deps";

export const dynamic = "force-dynamic";

export async function POST(_req: Request, ctx: { params: Promise<{ token: string }> }) {
  const { token } = await ctx.params;
  const { status } = await handleOneClickUnsubscribe(token, emailRepo, process.env.EMAIL_UNSUBSCRIBE_SECRET!);
  return new Response(status === 200 ? "Unsubscribed" : "Invalid token", { status });
}
