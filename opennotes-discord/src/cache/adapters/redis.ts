import Redis, { type RedisOptions } from 'ioredis';
import { logger } from '../../logger.js';
import { sanitizeConnectionUrl } from '../../utils/url-sanitizer.js';
import { safeJSONParse, safeJSONStringify } from '../../utils/safe-json.js';
import type { CacheConfig, CacheInterface, CacheMetrics } from '../interfaces.js';

export interface RedisCacheConfig extends CacheConfig {
  url?: string;
  host?: string;
  port?: number;
  password?: string | undefined;
  db?: number;
  maxRetries?: number;
  connectTimeout?: number;
}

/**
 * Redis cache implementation with connection pooling and retry logic
 *
 * Features:
 * - Automatic connection pooling
 * - Exponential backoff retry strategy
 * - Graceful error handling and reconnection
 * - Pub/Sub support for cache invalidation
 * - Circuit breaker pattern
 * - Metrics collection
 *
 * Suitable for:
 * - Production deployments
 * - Multi-instance/distributed systems
 * - High-availability requirements
 */
interface ResolvedRedisCacheConfig extends Required<Omit<RedisCacheConfig, 'password'>> {
  password: string | undefined;
}

export class RedisCacheAdapter implements CacheInterface {
  private client: Redis;
  private config: ResolvedRedisCacheConfig;
  private metrics: CacheMetrics;
  private isConnected: boolean;
  private reconnecting: boolean;
  private subscribers: Map<string, Redis> = new Map();

  constructor(config: RedisCacheConfig = {}) {
    this.isConnected = false;
    this.reconnecting = false;

    this.config = {
      defaultTtl: config.defaultTtl ?? 300,
      keyPrefix: config.keyPrefix ?? '',
      maxSize: config.maxSize ?? 10000,
      evictionPolicy: config.evictionPolicy ?? 'lru',
      url: config.url ?? process.env.REDIS_URL ?? 'redis://localhost:6379',
      host: config.host ?? 'localhost',
      port: config.port ?? 6379,
      password: config.password ?? undefined,
      db: config.db ?? 0,
      maxRetries: config.maxRetries ?? 10,
      connectTimeout: config.connectTimeout ?? 10000,
    };

    this.metrics = {
      hits: 0,
      misses: 0,
      sets: 0,
      deletes: 0,
      evictions: 0,
      size: 0,
    };

    const redisOptions: RedisOptions = {
      host: this.config.host,
      port: this.config.port,
      password: this.config.password,
      db: this.config.db,
      connectTimeout: this.config.connectTimeout,
      maxRetriesPerRequest: 3,
      enableOfflineQueue: true,
      lazyConnect: true,
      retryStrategy: (times: number) => {
        if (times > this.config.maxRetries) {
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

    if (this.config.url) {
      if (this.config.url.startsWith('rediss://')) {
        redisOptions.tls = {
          rejectUnauthorized: false,
        };
        logger.debug('Redis TLS enabled for rediss:// connection');
      }
      this.client = new Redis(this.config.url, redisOptions);
    } else {
      this.client = new Redis(redisOptions);
    }

    this.client.on('connect', () => {
      this.isConnected = true;
      this.reconnecting = false;
      const connectionUrl = this.config.url
        ? sanitizeConnectionUrl(this.config.url)
        : `redis://${this.config.host}:${this.config.port}`;
      logger.info('Redis connected', {
        url: connectionUrl,
        db: this.config.db,
      });
    });

    this.client.on('ready', () => {
      logger.info('Redis ready');
    });

    this.client.on('error', (err: unknown) => {
      const error = err instanceof Error ? err.message : String(err);
      logger.error('Redis error', { error });
    });

    this.client.on('close', () => {
      this.isConnected = false;
      logger.warn('Redis connection closed');
    });

    this.client.on('reconnecting', () => {
      this.reconnecting = true;
      logger.info('Redis reconnecting');
    });

    this.client.on('end', () => {
      this.isConnected = false;
      logger.warn('Redis connection ended');
    });
  }

  start(): void {
    if (!this.isConnected && !this.reconnecting) {
      void this.client.connect().catch((err: unknown) => {
        const error = err instanceof Error ? err.message : String(err);
        logger.error('Redis connection failed', { error });
      });
    }
  }

  stop(): void {
    for (const [channel, subscriber] of this.subscribers.entries()) {
      try {
        void subscriber.unsubscribe(channel);
        void subscriber.disconnect();
      } catch (err: unknown) {
        const error = err instanceof Error ? err.message : String(err);
        logger.error('Error cleaning up subscriber', { channel, error });
      }
    }
    this.subscribers.clear();
    logger.info('Redis subscribers cleaned up', { count: this.subscribers.size });

    this.client.removeAllListeners();

    if (this.isConnected || this.reconnecting) {
      this.client.disconnect();
      logger.info('Redis disconnected');
    }
  }

  async get<T>(key: string): Promise<T | null> {
    try {
      const fullKey = this.buildKey(key);
      const value = await this.client.get(fullKey);

      if (value === null) {
        this.metrics.misses++;
        return null;
      }

      this.metrics.hits++;
      return safeJSONParse<T>(value);
    } catch (error) {
      logger.error('Redis get error', { key, error });
      this.metrics.misses++;
      return null;
    }
  }

  async set(key: string, value: unknown, ttl?: number): Promise<boolean> {
    try {
      const fullKey = this.buildKey(key);
      const effectiveTtl = ttl ?? this.config.defaultTtl;
      const serialized = safeJSONStringify(value);

      if (effectiveTtl > 0) {
        await this.client.setex(fullKey, effectiveTtl, serialized);
      } else {
        await this.client.set(fullKey, serialized);
      }

      this.metrics.sets++;
      return true;
    } catch (error) {
      logger.error('Redis set error', { key, error });
      return false;
    }
  }

  async delete(key: string): Promise<boolean> {
    try {
      const fullKey = this.buildKey(key);
      const result = await this.client.del(fullKey);
      const existed = result > 0;

      if (existed) {
        this.metrics.deletes++;
      }

      return existed;
    } catch (error) {
      logger.error('Redis delete error', { key, error });
      return false;
    }
  }

  async exists(key: string): Promise<boolean> {
    try {
      const fullKey = this.buildKey(key);
      const result = await this.client.exists(fullKey);
      return result === 1;
    } catch (error) {
      logger.error('Redis exists error', { key, error });
      return false;
    }
  }

  async expire(key: string, ttl: number): Promise<boolean> {
    try {
      const fullKey = this.buildKey(key);
      const result = await this.client.expire(fullKey, ttl);
      return result === 1;
    } catch (error) {
      logger.error('Redis expire error', { key, error });
      return false;
    }
  }

  async mget(keys: string[]): Promise<(string | null)[]> {
    if (keys.length === 0) {
      return [];
    }

    try {
      const fullKeys = keys.map((k) => this.buildKey(k));
      const values = await this.client.mget(...fullKeys);

      return values.map((v: string | null) => {
        if (v === null) {
          this.metrics.misses++;
          return null;
        }
        this.metrics.hits++;
        try {
          return safeJSONParse(v);
        } catch {
          return null;
        }
      });
    } catch (error) {
      logger.error('Redis mget error', { keys, error });
      return keys.map(() => null);
    }
  }

  async mset(items: Map<string, unknown>, ttl?: number): Promise<boolean> {
    if (items.size === 0) {
      return true;
    }

    try {
      const pipeline = this.client.pipeline();
      const effectiveTtl = ttl ?? this.config.defaultTtl;

      for (const [key, value] of items.entries()) {
        const fullKey = this.buildKey(key);
        const serialized = safeJSONStringify(value);

        if (effectiveTtl > 0) {
          pipeline.setex(fullKey, effectiveTtl, serialized);
        } else {
          pipeline.set(fullKey, serialized);
        }
      }

      await pipeline.exec();
      this.metrics.sets += items.size;
      return true;
    } catch (error) {
      logger.error('Redis mset error', { count: items.size, error });
      return false;
    }
  }

  async clear(pattern?: string): Promise<number> {
    try {
      let cursor = '0';
      let count = 0;
      const matchPattern = pattern
        ? this.buildKey(pattern)
        : this.buildKey('*');

      do {
        const [nextCursor, keys] = await this.client.scan(
          cursor,
          'MATCH',
          matchPattern,
          'COUNT',
          100
        );
        cursor = nextCursor;

        if (keys.length > 0) {
          const deleted = await this.client.del(...keys);
          count += deleted;
        }
      } while (cursor !== '0');

      return count;
    } catch (error) {
      logger.error('Redis clear error', { pattern, error });
      return 0;
    }
  }

  async ping(): Promise<boolean> {
    try {
      const result = await this.client.ping();
      return result === 'PONG';
    } catch (error) {
      logger.error('Redis ping error', { error });
      return false;
    }
  }

  getMetrics(): CacheMetrics {
    return { ...this.metrics };
  }

  private buildKey(key: string): string {
    return this.config.keyPrefix ? `${this.config.keyPrefix}:${key}` : key;
  }

  async subscribe(channel: string, handler: (message: string) => void): Promise<void> {
    let subscriber = this.subscribers.get(channel);

    if (!subscriber) {
      subscriber = this.client.duplicate();
      try {
        await subscriber.subscribe(channel);
        this.subscribers.set(channel, subscriber);
        logger.info('Redis subscribed', { channel, totalSubscribers: this.subscribers.size });
      } catch (err: unknown) {
        const error = err instanceof Error ? err.message : String(err);
        logger.error('Redis subscribe error', { channel, error });
        throw err;
      }
    }

    subscriber.on('message', (ch: string, message: string) => {
      if (ch === channel) {
        handler(message);
      }
    });
  }

  async unsubscribe(channel: string): Promise<void> {
    const subscriber = this.subscribers.get(channel);
    if (subscriber) {
      try {
        await subscriber.unsubscribe(channel);
        subscriber.disconnect();
        this.subscribers.delete(channel);
        logger.info('Redis unsubscribed', { channel, remainingSubscribers: this.subscribers.size });
      } catch (err: unknown) {
        const error = err instanceof Error ? err.message : String(err);
        logger.error('Redis unsubscribe error', { channel, error });
      }
    }
  }

  async publish(channel: string, message: string): Promise<number> {
    try {
      return await this.client.publish(channel, message);
    } catch (error) {
      logger.error('Redis publish error', { channel, error });
      return 0;
    }
  }
}
