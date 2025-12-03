import Redis, { type RedisOptions } from 'ioredis';
import { logger } from './logger.js';
import { sanitizeConnectionUrl } from './utils/url-sanitizer.js';

let redisClient: Redis | null = null;

export function getRedisClient(): Redis | null {
  const redisUrl = process.env.REDIS_URL;
  const nodeEnv = process.env.NODE_ENV || 'development';

  if (!redisUrl) {
    if (nodeEnv === 'production') {
      logger.warn('REDIS_URL not configured in production environment');
    }
    return null;
  }

  if (redisClient) {
    return redisClient;
  }

  const redisOptions: RedisOptions = {
    connectTimeout: 10000,
    maxRetriesPerRequest: 3,
    enableOfflineQueue: true,
    lazyConnect: false,
    retryStrategy: (times: number) => {
      if (times > 10) {
        logger.error('Redis max retries exceeded', { times });
        return null;
      }
      const delay = Math.min(times * 50, 2000);
      logger.debug('Redis retry', { times, delay });
      return delay;
    },
    reconnectOnError: (err: Error) => {
      const targetErrors = ['READONLY', 'ECONNREFUSED', 'ETIMEDOUT'];
      if (targetErrors.some((target) => err.message.includes(target))) {
        logger.warn('Redis reconnecting on error', { error: err.message });
        return 2;
      }
      return false;
    },
  };

  if (redisUrl.startsWith('rediss://')) {
    // For GCP Memorystore with SERVER_AUTHENTICATION:
    // - Server presents a Google-signed certificate
    // - Client should skip verification (traffic is VPC-internal)
    // - Need both rejectUnauthorized and checkServerIdentity for ioredis
    redisOptions.tls = {
      rejectUnauthorized: false,
      // Return undefined to skip hostname verification
      checkServerIdentity: () => undefined,
    };
    logger.debug('Redis TLS enabled for rediss:// connection with certificate verification disabled');
  }

  redisClient = new Redis(redisUrl, redisOptions);

  redisClient.on('connect', () => {
    logger.info('Redis client connected', {
      url: sanitizeConnectionUrl(redisUrl),
      isTLS: redisUrl.startsWith('rediss://'),
    });
  });

  redisClient.on('ready', () => {
    logger.info('Redis client ready and operational');
  });

  redisClient.on('error', (err: unknown) => {
    const error = err instanceof Error ? err.message : String(err);
    logger.error('Redis client error', {
      error,
      url: sanitizeConnectionUrl(redisUrl),
      isTLS: redisUrl.startsWith('rediss://'),
    });
  });

  redisClient.on('close', () => {
    logger.warn('Redis client connection closed', {
      url: sanitizeConnectionUrl(redisUrl),
    });
  });

  redisClient.on('reconnecting', () => {
    logger.info('Redis client reconnecting', {
      url: sanitizeConnectionUrl(redisUrl),
    });
  });

  redisClient.on('end', () => {
    logger.warn('Redis client connection ended', {
      url: sanitizeConnectionUrl(redisUrl),
    });
  });

  return redisClient;
}

export function closeRedisClient(): void {
  if (redisClient) {
    redisClient.removeAllListeners();
    redisClient.disconnect();
    redisClient = null;
    logger.info('Redis client disconnected');
  }
}
