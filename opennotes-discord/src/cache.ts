import { RedisCacheAdapter } from './cache/adapters/redis.js';
import type { CacheInterface } from './cache/interfaces.js';
import { logger } from './logger.js';

function createCacheAdapter(): CacheInterface {
  const redisUrl = process.env.REDIS_URL;

  if (!redisUrl) {
    throw new Error('REDIS_URL environment variable is required');
  }

  logger.info('Using Redis cache adapter', {
    redisUrl: redisUrl.replace(/:[^:@]+@/, ':****@'),
  });

  return new RedisCacheAdapter({
    url: redisUrl,
    defaultTtl: 300,
    keyPrefix: 'opennotes',
    maxSize: 10000,
    evictionPolicy: 'lru',
  });
}

export const cache: CacheInterface = createCacheAdapter();
