// Désinscription one-click (RFC 8058) et en-têtes List-Unsubscribe.
//
// Le jeton ne contient ni l'adresse ni de donnée personnelle en clair : seulement
// l'empreinte de l'adresse, le tenant et le flux, signés en HMAC. L'URL peut donc
// apparaître dans les logs, les proxys et les en-têtes sans fuite d'adresse.
import { createHmac, timingSafeEqual } from "node:crypto";
import { emailHash, type EmailRepo } from "../repo";
import type { Stream } from "../types";

interface TokenPayload {
  t: string;      // tenantId
  h: string;      // sha256 de l'adresse
  s: Stream;      // flux
  m?: string;     // id du message (statistiques)
  v: 1;
}

const b64 = (b: Buffer | string) => Buffer.from(b).toString("base64url");

function sign(body: string, secret: string) {
  return createHmac("sha256", secret).update(body).digest("base64url");
}

export function createUnsubscribeToken(input: { tenantId: string; recipient: string; stream: Stream; messageId?: string }, secret: string): string {
  const payload: TokenPayload = { t: input.tenantId, h: emailHash(input.recipient), s: input.stream, m: input.messageId, v: 1 };
  const body = b64(JSON.stringify(payload));
  return `${body}.${sign(body, secret)}`;
}

export function readUnsubscribeToken(token: string, secret: string): TokenPayload | null {
  const [body, mac] = token.split(".");
  if (!body || !mac) return null;
  const expected = Buffer.from(sign(body, secret));
  const given = Buffer.from(mac);
  if (expected.length !== given.length || !timingSafeEqual(expected, given)) return null;
  try {
    const p = JSON.parse(Buffer.from(body, "base64url").toString("utf8")) as TokenPayload;
    return p.v === 1 && p.t && p.h ? p : null;
  } catch {
    return null;
  }
}

/**
 * En-têtes à poser sur chaque email marketing. L'ESP doit les couvrir par la
 * signature DKIM (Resend et SES signent tous les en-têtes ajoutés à l'envoi).
 */
export function listUnsubscribeHeaders(input: { tenantId: string; recipient: string; stream: Stream; messageId?: string; baseUrl: string; mailto?: string }, secret: string): Record<string, string> {
  const token = createUnsubscribeToken(input, secret);
  const url = `${input.baseUrl.replace(/\/$/, "")}/api/email/unsubscribe/${token}`;
  const mailto = input.mailto ? `, <mailto:${input.mailto}?subject=unsubscribe-${token.slice(0, 24)}>` : "";
  return {
    "List-Unsubscribe": `<${url}>${mailto}`,
    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
  };
}

/** URL visible à mettre aussi dans le pied de page (exigé en plus de l'en-tête). */
export function unsubscribeLink(input: { tenantId: string; recipient: string; stream: Stream; messageId?: string; baseUrl: string }, secret: string) {
  return `${input.baseUrl.replace(/\/$/, "")}/unsubscribe/${createUnsubscribeToken(input, secret)}`;
}

/**
 * Traitement du POST one-click : pas de cookie, pas de CSRF, pas de page, pas de
 * redirection — le jeton signé est l'autorisation. Idempotent.
 * Une désinscription ne coupe que le marketing (le transactionnel reste permis).
 */
export async function handleOneClickUnsubscribe(token: string, repo: EmailRepo, secret: string): Promise<{ status: 200 | 400 }> {
  const p = readUnsubscribeToken(token, secret);
  if (!p) return { status: 400 };
  await repo.suppress({ scope: p.t, emailHash: p.h, streamScope: "marketing", reason: "UNSUBSCRIBE", detail: p.m ? `message ${p.m}` : undefined });
  return { status: 200 };
}
