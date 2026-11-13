// app/api/email/webhooks/ses/route.ts — abonnement HTTPS au topic SNS des événements SES.
import { emailRepo, emailWindows } from "@/lib/email/deps";
import { processDeliveryEvent } from "@/lib/email/events";
import { InvalidSignatureError } from "@/lib/email/webhooks/resend";
import { confirmSubscription, normalizeSesNotification, verifySnsMessage } from "@/lib/email/webhooks/ses-sns";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const raw = await req.text(); // SNS envoie du JSON en text/plain
  let msg;
  try {
    msg = await verifySnsMessage(raw);
  } catch (e) {
    if (e instanceof InvalidSignatureError) return new Response("invalid signature", { status: 401 });
    throw e;
  }
  if (msg.Type === "SubscriptionConfirmation") {
    await confirmSubscription(msg);
    return new Response("subscribed");
  }
  if (msg.Type !== "Notification") return new Response("ignored");

  const { deliveries, tenantStatus } = normalizeSesNotification(msg);
  for (const event of deliveries) await processDeliveryEvent(event, { repo: emailRepo, windows: emailWindows });
  if (tenantStatus?.status === "DISABLED") {
    // AWS a mis le tenant en pause (réputation) : bloquer ses envois et prévenir l'équipe / le client.
    // À brancher : notification interne + bandeau dans l'app du client.
    console.warn("[email] tenant SES en pause", tenantStatus);
  }
  return new Response("ok");
}
