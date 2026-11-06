// Portes de mise en service et plafond de warm-up, appliquées AU MOMENT DE L'ENVOI.
// Une règle qui ne vit que dans une checklist finit par être sautée : ici, un
// envoi marketing est refusé tant que les six conditions ne sont pas réunies.
import type { DomainRow, IdentityRow } from "../repo";
import type { Stream } from "../types";

export const EU_REGIONS = ["eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-north-1", "eu-south-1"];

export interface GateItem {
  key: "region" | "dns" | "webhooks" | "unsubscribe" | "postmaster" | "warmup";
  ok: boolean;
  message: string;
}

/**
 * Les six conditions avant le premier envoi :
 * 1 région choisie à la création · 2 sous-domaine + SPF/DKIM + DMARC avec rua ·
 * 3 webhooks bounces/plaintes · 4 désinscription one-click · 5 Postmaster + Sender Hub ·
 * 6 warm-up démarré. Le transactionnel n'exige que 1, 2, 3 (pas de désinscription,
 * volume organique) ; le marketing exige les six.
 */
export function evaluateGoLive(domain: DomainRow, identities: IdentityRow[], stream: Stream, opts: { requireEu?: boolean } = {}): { ready: boolean; items: GateItem[] } {
  const verified = identities.filter((i) => i.status === "verified");
  const items: GateItem[] = [
    {
      key: "region",
      ok: verified.length > 0 && (!opts.requireEu || verified.every((i) => EU_REGIONS.includes(i.region))),
      message: verified.length ? `région ${verified.map((i) => `${i.provider}:${i.region}`).join(", ")}` : "aucune identité vérifiée chez un fournisseur",
    },
    {
      key: "dns",
      ok: domain.name !== domain.rootDomain && domain.status === "verified" && domain.dmarcPolicyObserved !== null && domain.dmarcRuaObserved,
      message: domain.name === domain.rootDomain ? "envoi depuis la racine : utiliser un sous-domaine dédié"
        : !domain.dmarcPolicyObserved ? "DMARC absent" : !domain.dmarcRuaObserved ? "DMARC sans rua" : "SPF/DKIM vérifiés, DMARC avec rua",
    },
    { key: "webhooks", ok: !!domain.webhookVerifiedAt, message: domain.webhookVerifiedAt ? "bounces/plaintes reçus et signés" : "webhooks bounces/plaintes non vérifiés" },
  ];
  if (stream === "marketing") {
    items.push(
      { key: "unsubscribe", ok: !!domain.unsubscribeVerifiedAt, message: domain.unsubscribeVerifiedAt ? "one-click RFC 8058 testé" : "endpoint one-click non testé" },
      { key: "postmaster", ok: !!domain.postmasterConfirmedAt && !!domain.senderHubConfirmedAt, message: `Postmaster ${domain.postmasterConfirmedAt ? "✓" : "✗"} · Sender Hub ${domain.senderHubConfirmedAt ? "✓" : "✗"}` },
      { key: "warmup", ok: !!domain.warmupStartedAt, message: domain.warmupStartedAt ? `warm-up depuis le ${domain.warmupStartedAt.toISOString().slice(0, 10)}` : "warm-up non démarré" },
    );
  }
  return { ready: items.every((i) => i.ok), items };
}

/**
 * Plafond journalier du domaine pendant le warm-up : 300–500/jour la 1ʳᵉ semaine,
 * doublé chaque semaine, moins les semaines « retenues » par le job de santé
 * (bounces ≥ 2 % ou plaintes ≥ 0,1 % sur la semaine écoulée). null = plus de plafond.
 */
export function warmupDailyCap(domain: DomainRow, now = new Date()): number | null {
  if (!domain.warmupStartedAt) return 0;
  const elapsedWeeks = Math.floor((now.getTime() - domain.warmupStartedAt.getTime()) / (7 * 86_400_000));
  const week = Math.max(0, elapsedWeeks - domain.warmupHeldWeeks);
  const first = Math.min(500, Math.max(300, domain.warmupFirstWeekPerDay));
  const cap = first * 2 ** week;
  if (domain.warmupTargetPerDay && cap >= domain.warmupTargetPerDay) return null;
  return cap;
}

/** Segments ouverts pendant le warm-up : les plus engagés d'abord. */
export const WARMUP_SEGMENTS = ["engaged_30d", "engaged_90d", "new_confirmed", "engaged_180d", "rest"] as const;
export function warmupOpenSegments(domain: DomainRow, now = new Date()) {
  if (warmupDailyCap(domain, now) === null) return [...WARMUP_SEGMENTS];
  const week = Math.max(0, Math.floor((now.getTime() - (domain.warmupStartedAt?.getTime() ?? now.getTime())) / (7 * 86_400_000)) - domain.warmupHeldWeeks);
  return WARMUP_SEGMENTS.slice(0, Math.min(WARMUP_SEGMENTS.length, week + 1));
}

/** Décision hebdomadaire du job de santé : retenir le palier si la semaine a été mauvaise. */
export function shouldHoldWarmup(week: { sent: number; delivered: number; hardBounces: number; complaints: number }) {
  if (week.sent < 200) return false; // échantillon insuffisant : on ne conclut pas
  return week.hardBounces / week.sent >= 0.02 || (week.delivered > 0 && week.complaints / week.delivered >= 0.001);
}
