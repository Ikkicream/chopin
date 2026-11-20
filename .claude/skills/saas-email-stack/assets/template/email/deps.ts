// Câblage des dépendances de la brique email. Seul fichier à adapter au projet
// (client Prisma/Drizzle, client Redis). Importé par les routes et les jobs.
import { PrismaClient } from "@prisma/client";
import { createPrismaEmailRepo } from "./prisma-repo";
import { MemoryWindowStore, type WindowStore } from "./compliance/guards";
import { createResendProvider } from "./providers/resend";
import { createSesProvider } from "./providers/ses";
import type { SendDeps } from "./send";

// Réutiliser le client Prisma existant du projet plutôt que d'en créer un second.
const prisma = (globalThis as { prisma?: PrismaClient }).prisma ?? new PrismaClient();

export const emailRepo = createPrismaEmailRepo(prisma);

export const emailProviders = {
  resend: createResendProvider(process.env.RESEND_API_KEY),
  ses: createSesProvider(),
};

/**
 * Compteurs des garde-fous. En production : Redis (ioredis et @upstash/redis exposent
 * tous deux incr/expire/get). La mémoire ne convient qu'en développement (une instance).
 */
type MinimalRedis = { incr(k: string): Promise<number>; expire(k: string, s: number): Promise<unknown>; get(k: string): Promise<string | number | null> };
export function redisWindowStore(redis: MinimalRedis): WindowStore {
  return {
    async incr(key, ttl) {
      const n = await redis.incr(key);
      if (n === 1) await redis.expire(key, ttl);
      return n;
    },
    async get(key) {
      return Number((await redis.get(key)) ?? 0);
    },
  };
}
export const emailWindows: WindowStore = new MemoryWindowStore(); // remplacer par redisWindowStore(redis)

export const sendDeps: SendDeps = {
  repo: emailRepo,
  providers: emailProviders,
  windows: emailWindows,
  config: {
    unsubscribeSecret: process.env.EMAIL_UNSUBSCRIBE_SECRET!,
    publicBaseUrl: process.env.EMAIL_PUBLIC_BASE_URL!,
    requireEuRegion: process.env.EMAIL_REQUIRE_EU_REGION !== "false",
  },
};
