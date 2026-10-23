// app/api/email/domains/route.ts           POST  : créer un domaine d'envoi pour le tenant courant
// app/api/email/domains/[id]/route.ts      GET   : domaine + records (attendu / trouvé) + portes de mise en service
// app/api/email/domains/[id]/verify        POST  : revérifier maintenant
// app/api/email/domains/[id]/golive        POST  : confirmer Postmaster / Sender Hub / démarrer le warm-up
// app/api/email/domains/[id]/selftest      POST  : auto-test des webhooks (simulateurs)
//
// Gabarit regroupé : chaque fonction va dans son propre fichier route.ts, exportée en POST ou GET.
// `getTenantId` vient de l'authentification du projet (organisation / workspace courant).
// Le contrôle d'accès est le point clé : un tenant ne voit et ne modifie que SES domaines.
import { evaluateGoLive } from "@/lib/email/compliance/golive";
import { emailProviders, emailRepo, sendDeps } from "@/lib/email/deps";
import { confirmGoLiveStep, createSendingDomain, refreshDomain, runWebhookSelfTest } from "@/lib/email/domains/service";
import { getTenantId } from "@/lib/auth"; // à adapter

export async function POST(req: Request) {
  const tenantId = await getTenantId(req);
  const body = await req.json();
  const marketing = body.stream === "marketing";
  // Politique par défaut : marketing → SES (isolé par tenant SES), transactionnel → Resend. Région UE.
  const result = await createSendingDomain({ repo: emailRepo, providers: emailProviders }, {
    tenantId,
    name: body.name,
    rootDomain: body.rootDomain,
    stream: marketing ? "marketing" : "transactional",
    dnsMode: body.dnsMode ?? "delegated",
    providers: body.providers ?? (marketing ? ["ses"] : ["resend"]),
    regions: { resend: "eu-west-1", ses: process.env.SES_DEFAULT_REGION ?? "eu-west-3" },
    dmarcRua: body.dmarcRua,
  });
  return Response.json(result, { status: 201 });
}

export async function GET(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const tenantId = await getTenantId(req);
  const { id } = await ctx.params;
  const domain = await emailRepo.getDomain(id);
  if (!domain || domain.tenantId !== tenantId) return new Response("not found", { status: 404 });
  const identities = await emailRepo.listIdentities(id);
  return Response.json({
    domain,
    identities,
    records: await emailRepo.listRecords(id),
    golive: evaluateGoLive(domain, identities, domain.stream, { requireEu: true }),
  });
}

export async function verify(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const tenantId = await getTenantId(req);
  const { id } = await ctx.params;
  const domain = await emailRepo.getDomain(id);
  if (!domain || domain.tenantId !== tenantId) return new Response("not found", { status: 404 });
  await refreshDomain({ repo: emailRepo, providers: emailProviders }, id, 0);
  return Response.json(await emailRepo.getDomain(id));
}

export async function golive(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const tenantId = await getTenantId(req);
  const { id } = await ctx.params;
  const domain = await emailRepo.getDomain(id);
  if (!domain || domain.tenantId !== tenantId) return new Response("not found", { status: 404 });
  const { step, targetPerDay } = await req.json();
  await confirmGoLiveStep(emailRepo, id, step, { targetPerDay });
  return Response.json(await emailRepo.getDomain(id));
}

// app/api/email/domains/[id]/selftest/route.ts → export POST
export async function selftest(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const tenantId = await getTenantId(req);
  const { id } = await ctx.params;
  const domain = await emailRepo.getDomain(id);
  if (!domain || domain.tenantId !== tenantId) return new Response("not found", { status: 404 });
  await runWebhookSelfTest(sendDeps, id);
  return Response.json({ started: true }, { status: 202 }); // webhookVerifiedAt se remplit à réception des 2 événements
}
