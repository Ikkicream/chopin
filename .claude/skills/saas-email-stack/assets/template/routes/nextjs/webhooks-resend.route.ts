// app/api/email/webhooks/resend/route.ts
// Corps lu en TEXTE BRUT (la signature porte sur les octets exacts). 401 si non signé :
// c'est ce que vérifient golive-check.mjs et selftest.mjs.
import { emailRepo, emailWindows } from "@/lib/email/deps";
import { processDeliveryEvent } from "@/lib/email/events";
import { InvalidSignatureError, normalizeResendEvent, verifyResendWebhook } from "@/lib/email/webhooks/resend";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const raw = await req.text();
  let evt;
  try {
    evt = verifyResendWebhook(raw, req.headers);
  } catch (e) {
    if (e instanceof InvalidSignatureError) return new Response("invalid signature", { status: 401 });
    throw e;
  }
  for (const event of normalizeResendEvent(evt, req.headers.get("svix-id")!)) {
    await processDeliveryEvent(event, { repo: emailRepo, windows: emailWindows });
  }
  // 2xx rapide : Resend réessaie (5 s, 5 min, 30 min, 2 h…) puis désactive l'endpoint en cas d'échecs répétés.
  return new Response("ok");
}
