import Redis from 'ioredis';

export interface RedisTestContext {
  available: boolean;
  reason: string;
  redis: Redis | null;
}

const context: RedisTestContext = {
  available: false,
  reason: 'Redis availability not yet checked',
  redis: null,
};

let checkPromise: Promise<void> | null = null;

export function getRedisUrl(): string {
  return (
    process.env.REDIS_URL?.replace('redis://redis:', 'redis://localhost:') ||
    'redis://localhost:6379'
  );
}

export async function ensureRedisChecked(): Promise<RedisTestContext> {
  if (!checkPromise) {
    checkPromise = (async () => {
      const redisUrl = getRedisUrl();

      const redis = new Redis(redisUrl, {
        maxRetriesPerRequest: 1,
        enableReadyCheck: true,
        lazyConnect: true,
        connectTimeout: 2000,
        retryStrategy: () => null,
      });

      try {
        await redis.connect();
        await redis.ping();
        context.available = true;
        context.reason = '';
        context.redis = redis;
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'Unknown connection error';
        context.available = false;
        context.reason = `Redis unavailable: ${message}`;
        context.redis = null;
        await redis.quit().catch(() => {});
      }
    })();
  }

  await checkPromise;
  return context;
}

export async function cleanupRedisTestConnection(): Promise<void> {
  if (context.redis && context.redis.status !== 'end') {
    await context.redis.quit().catch(() => {});
    context.redis = null;
  }
}

export function getRedisTestContext(): RedisTestContext {
  return context;
}

export function skipTest(testContext: RedisTestContext): boolean {
  if (!testContext.available) {
    console.log(`[SKIPPED] ${testContext.reason}`);
    return true;
  }
  return false;
}
