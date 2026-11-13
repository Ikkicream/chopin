// Routage : quel fournisseur, quelle identité, pour (tenant, flux, domaine du From).
//
// Politique par défaut : transactionnel → Resend, marketing → SES. Un même domaine
// peut être vérifié chez les deux (enregistrements DKIM et Return-Path distincts :
// `resend._domainkey` + `send.` d'un côté, tokens SES + `bounce.` de l'autre),
// ce qui donne une bascule immédiate sans changer l'adresse d'expédition.
import type { DomainRow, EmailRepo, IdentityRow } from "./repo";
import { EmailBlockedError, type ProviderId, type Stream } from "./types";

export type RoutingPolicy = Record<Stream, ProviderId[]>; // ordre de préférence

export const DEFAULT_POLICY: RoutingPolicy = {
  transactional: ["resend", "ses"],
  marketing: ["ses", "resend"],
};

export interface Route {
  domain: DomainRow;
  identities: IdentityRow[];   // toutes, pour les portes de mise en service
  primary: IdentityRow;
  fallbacks: IdentityRow[];    // même domaine, autre fournisseur, déjà vérifié
}

export async function resolveRoute(repo: EmailRepo, input: { tenantId: string; stream: Stream; fromEmail: string }, policy: RoutingPolicy = DEFAULT_POLICY): Promise<Route> {
  const domainName = input.fromEmail.split("@")[1]?.toLowerCase();
  if (!domainName) throw new EmailBlockedError("INVALID_FROM", "Adresse d'expédition invalide");

  const domain = await repo.getDomainByName(domainName);
  // Un tenant ne peut envoyer que depuis un domaine qui lui appartient.
  if (!domain || domain.tenantId !== input.tenantId) {
    throw new EmailBlockedError("FROM_DOMAIN_NOT_OWNED", `Le domaine ${domainName} n'est pas enregistré pour ce compte`);
  }
  const identities = await repo.listIdentities(domain.id);
  const verified = identities.filter((i) => i.status === "verified");
  if (!verified.length) throw new EmailBlockedError("DOMAIN_NOT_VERIFIED", `${domainName} n'est vérifié chez aucun fournisseur`);

  const order = policy[input.stream];
  const ranked = [...verified].sort((a, b) => {
    const ra = order.indexOf(a.provider), rb = order.indexOf(b.provider);
    return (ra === -1 ? 99 : ra) - (rb === -1 ? 99 : rb) || Number(b.isPrimary) - Number(a.isPrimary);
  });
  return { domain, identities, primary: ranked[0], fallbacks: ranked.slice(1) };
}

/** Erreurs fournisseur qui justifient une bascule (problème d'identité, pas de contenu ni de quota). */
export function isIdentityFailure(err: unknown): boolean {
  const msg = String((err as { name?: string; message?: string })?.name ?? "") + " " + String((err as Error)?.message ?? "");
  return /MailFromDomainNotVerified|not verified|identity|domain is not verified|validation_error.*domain|AccountSendingPaused|SendingPaused/i.test(msg);
}
