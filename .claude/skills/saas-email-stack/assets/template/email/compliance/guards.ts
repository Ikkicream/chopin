// Garde-fous par destinataire (repris de Lumail) : 5 envois / 10 min et 20 / 24 h
// par adresse, tous flux confondus. Le stockage est abstrait : Redis en production
// (INCR + EXPIRE), mémoire en développement.
import { emailHash } from "../repo";
import { EmailBlockedError } from "../types";

export interface WindowStore {
  /** Incrémente le compteur `key` (créé avec un TTL de `ttlSeconds`) et renvoie la nouvelle valeur. */
  incr(key: string, ttlSeconds: number): Promise<number>;
  get(key: string): Promise<number>;
}

export class MemoryWindowStore implements WindowStore {
  private m = new Map<string, { n: number; exp: number }>();
  async incr(key: string, ttl: number) {
    const now = Date.now();
    const cur = this.m.get(key);
    const next = !cur || cur.exp < now ? { n: 1, exp: now + ttl * 1000 } : { n: cur.n + 1, exp: cur.exp };
    this.m.set(key, next);
    return next.n;
  }
  async get(key: string) {
    const cur = this.m.get(key);
    return cur && cur.exp > Date.now() ? cur.n : 0;
  }
}

// Fenêtres fixes alignées (approximation des fenêtres glissantes de Lumail, suffisante en pratique).
const RULES = [
  { name: "10m", seconds: 600, max: 5 },
  { name: "24h", seconds: 86_400, max: 20 },
];

export async function checkRecipientGuards(recipient: string, store: WindowStore): Promise<void> {
  const h = emailHash(recipient);
  if ((await store.get(`email:cooldown:${h}`)) > 0) {
    throw new EmailBlockedError("RECIPIENT_COOLDOWN", "Destinataire en pause 24 h après un bounce « boîte pleine » ou « débit limité »", 86_400);
  }
  for (const rule of RULES) {
    const bucket = Math.floor(Date.now() / 1000 / rule.seconds);
    const n = await store.incr(`email:rcpt:${rule.name}:${h}:${bucket}`, rule.seconds);
    if (n > rule.max) {
      throw new EmailBlockedError("RECIPIENT_RATE_LIMITED", `Plus de ${rule.max} emails en ${rule.name} vers ce destinataire`, rule.seconds);
    }
  }
}

/** À appeler depuis le traitement des bounces « mailbox full » / « throttled ». */
export async function startRecipientCooldown(recipient: string, store: WindowStore) {
  await store.incr(`email:cooldown:${emailHash(recipient)}`, 86_400);
}
