// Tests unitaires de la brique (vitest ; adapter `import` pour jest si besoin).
// Ils couvrent les règles qui protègent la réputation : on ne les casse pas par accident.
import { describe, expect, it } from "vitest";
import { evaluateGoLive, shouldHoldWarmup, warmupDailyCap, warmupOpenSegments } from "./compliance/golive";
import { checkRecipientGuards, MemoryWindowStore } from "./compliance/guards";
import { createUnsubscribeToken, listUnsubscribeHeaders, readUnsubscribeToken } from "./compliance/unsubscribe";
import type { DomainRow, IdentityRow } from "./repo";

const SECRET = "test-secret";
const day = 86_400_000;

function domain(over: Partial<DomainRow> = {}): DomainRow {
  return {
    id: "d1", tenantId: "t1", name: "news.client.com", rootDomain: "client.com", stream: "marketing", region: "eu-west-3",
    status: "verified", dnsMode: "delegated", hostedZoneId: "Z1", nameServers: [], delegationVerifiedAt: new Date(),
    webhookVerifiedAt: new Date(), unsubscribeVerifiedAt: new Date(), postmasterConfirmedAt: new Date(), senderHubConfirmedAt: new Date(),
    warmupStartedAt: new Date(), warmupTargetPerDay: 40_000, warmupFirstWeekPerDay: 400, warmupHeldWeeks: 0,
    dmarcPolicyObserved: "none", dmarcRuaObserved: true, createdAt: new Date(), ...over,
  };
}
const ses: IdentityRow = { id: "i1", domainId: "d1", provider: "ses", providerRef: "news.client.com", status: "verified", region: "eu-west-3", isPrimary: true, configurationSet: "t1-marketing", sesTenantName: "t1" };

describe("désinscription one-click", () => {
  it("le jeton est signé et ne contient pas l'adresse", () => {
    const token = createUnsubscribeToken({ tenantId: "t1", recipient: "Jean@Example.com", stream: "marketing" }, SECRET);
    expect(token).not.toContain("example");
    expect(readUnsubscribeToken(token, SECRET)?.t).toBe("t1");
    expect(readUnsubscribeToken(token, "autre-secret")).toBeNull();
    expect(readUnsubscribeToken(token.slice(0, -2) + "xx", SECRET)).toBeNull();
  });
  it("pose List-Unsubscribe (https) et List-Unsubscribe-Post", () => {
    const h = listUnsubscribeHeaders({ tenantId: "t1", recipient: "a@b.co", stream: "marketing", baseUrl: "https://app.p.com/" }, SECRET);
    expect(h["List-Unsubscribe"]).toMatch(/^<https:\/\/app\.p\.com\/api\/email\/unsubscribe\/[^>]+>$/);
    expect(h["List-Unsubscribe-Post"]).toBe("List-Unsubscribe=One-Click");
  });
});

describe("mise en service", () => {
  it("marketing : les six conditions sont exigées", () => {
    expect(evaluateGoLive(domain(), [ses], "marketing", { requireEu: true }).ready).toBe(true);
    for (const missing of ["webhookVerifiedAt", "unsubscribeVerifiedAt", "postmasterConfirmedAt", "senderHubConfirmedAt", "warmupStartedAt"] as const) {
      expect(evaluateGoLive(domain({ [missing]: null }), [ses], "marketing").ready, missing).toBe(false);
    }
    expect(evaluateGoLive(domain({ dmarcRuaObserved: false }), [ses], "marketing").ready).toBe(false);
    expect(evaluateGoLive(domain({ name: "client.com" }), [ses], "marketing").ready).toBe(false);
  });
  it("région hors UE refusée quand l'UE est exigée", () => {
    expect(evaluateGoLive(domain(), [{ ...ses, region: "us-east-1" }], "marketing", { requireEu: true }).ready).toBe(false);
  });
  it("transactionnel : ni warm-up ni désinscription exigés", () => {
    expect(evaluateGoLive(domain({ warmupStartedAt: null, unsubscribeVerifiedAt: null }), [ses], "transactional").ready).toBe(true);
  });
});

describe("warm-up", () => {
  const now = new Date("2026-11-01T12:00:00Z");
  it("400/jour la 1ʳᵉ semaine puis doublement hebdomadaire", () => {
    const start = (weeksAgo: number) => new Date(now.getTime() - weeksAgo * 7 * day - 3600_000);
    expect(warmupDailyCap(domain({ warmupStartedAt: start(0) }), now)).toBe(400);
    expect(warmupDailyCap(domain({ warmupStartedAt: start(1) }), now)).toBe(800);
    expect(warmupDailyCap(domain({ warmupStartedAt: start(3) }), now)).toBe(3200);
    expect(warmupDailyCap(domain({ warmupStartedAt: start(12) }), now)).toBeNull(); // cible atteinte
  });
  it("une semaine retenue garde le palier", () => {
    const d = domain({ warmupStartedAt: new Date(now.getTime() - 2 * 7 * day - 3600_000), warmupHeldWeeks: 1 });
    expect(warmupDailyCap(d, now)).toBe(800);
  });
  it("ouvre les segments les plus engagés d'abord", () => {
    expect(warmupOpenSegments(domain({ warmupStartedAt: now }), now)).toEqual(["engaged_30d"]);
  });
  it("retient le palier si bounces ≥ 2 % ou plaintes ≥ 0,1 %, pas sous 200 envois", () => {
    expect(shouldHoldWarmup({ sent: 1000, delivered: 980, hardBounces: 25, complaints: 0 })).toBe(true);
    expect(shouldHoldWarmup({ sent: 1000, delivered: 990, hardBounces: 5, complaints: 1 })).toBe(true);
    expect(shouldHoldWarmup({ sent: 1000, delivered: 990, hardBounces: 5, complaints: 0 })).toBe(false);
    expect(shouldHoldWarmup({ sent: 100, delivered: 50, hardBounces: 50, complaints: 5 })).toBe(false);
  });
});

describe("garde-fous destinataire", () => {
  it("bloque le 6ᵉ envoi en 10 minutes", async () => {
    const store = new MemoryWindowStore();
    for (let i = 0; i < 5; i++) await checkRecipientGuards("x@y.co", store);
    await expect(checkRecipientGuards("x@y.co", store)).rejects.toMatchObject({ code: "RECIPIENT_RATE_LIMITED" });
  });
});

describe("webhook Resend", () => {
  it("vérifie la signature Svix et normalise un hard bounce avec le tenant", async () => {
    const { Webhook } = await import("svix");
    const { verifyResendWebhook, normalizeResendEvent } = await import("./webhooks/resend");
    const secret = "whsec_" + Buffer.from("k".repeat(32)).toString("base64");
    process.env.RESEND_WEBHOOK_SECRET = secret;
    const body = JSON.stringify({ type: "email.bounced", created_at: "2026-10-13T10:00:00Z", data: { email_id: "em_1", to: ["x@y.co"], tags: { tenant: "t1" }, bounce: { type: "Permanent", subType: "General", message: "550 no such user" } } });
    const ts = new Date();
    const sig = new Webhook(secret).sign("msg_1", ts, body);
    const headers = new Headers({ "svix-id": "msg_1", "svix-timestamp": String(Math.floor(ts.getTime() / 1000)), "svix-signature": sig });
    const [evt] = normalizeResendEvent(verifyResendWebhook(body, headers), "msg_1");
    expect(evt).toMatchObject({ type: "bounced_hard", tenantId: "t1", recipient: "x@y.co", providerEventId: "msg_1" });
    expect(() => verifyResendWebhook(body.replace("Permanent", "Temporary"), headers)).toThrow();
  });
});
