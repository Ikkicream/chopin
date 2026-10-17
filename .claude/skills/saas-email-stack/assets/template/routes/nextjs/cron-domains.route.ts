// app/api/cron/email-domains/route.ts — appelé chaque minute (Vercel Cron via vercel.ts,
// ou la file de jobs du projet). Traite les domaines dont la vérification est due.
// Les appels de gestion SES sont limités à 1/s : petit lot, séquentiel.
import { emailProviders, emailRepo } from "@/lib/email/deps";
import { refreshDomain } from "@/lib/email/domains/service";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  if (req.headers.get("authorization") !== `Bearer ${process.env.CRON_SECRET}`) return new Response("unauthorized", { status: 401 });
  const due = await emailRepo.listDomainsToCheck(new Date(), 20);
  for (const d of due) {
    const ageMs = Date.now() - d.createdAt.getTime(); // 72 h max pour vérifier, puis échec
    try {
      await refreshDomain({ repo: emailRepo, providers: emailProviders }, d.id, ageMs);
    } catch (e) {
      // Erreur DNS ou API transitoire : on ne conclut rien, on réessaiera au prochain passage.
      console.error("[email] refresh", d.name, e);
    }
    await new Promise((r) => setTimeout(r, 1100));
  }
  return Response.json({ checked: due.length });
}
