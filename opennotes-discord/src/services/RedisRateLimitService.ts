import type { Redis } from 'ioredis';
import { RateLimitResult, ServiceError, ErrorCode } from './types.js';
import { logger } from '../logger.js';

export interface RedisRateLimitConfig {
  maxRequests: number;
  windowSeconds: number;
  keyPrefix?: string;
}

export class RedisRateLimitService {
  private config: RedisRateLimitConfig;
  private windowMs: number;
  private keyPrefix: string;

  constructor(
    private redis: Redis,
    config: RedisRateLimitConfig = { maxRequests: 5, windowSeconds: 60 }
  ) {
    this.config = config;
    this.windowMs = config.windowSeconds * 1000;
    this.keyPrefix = config.keyPrefix ?? 'ratelimit';
  }

  async check(userId: string): Promise<RateLimitResult> {
    const key = this.buildKey(userId);
    const now = Date.now();

    try {
      const count = await this.redis.incr(key);

      if (count === 1) {
        await this.redis.pexpire(key, this.windowMs);
      }

      const ttl = await this.redis.pttl(key);
      const resetAt = ttl > 0 ? now + ttl : now + this.windowMs;

      if (count > this.config.maxRequests) {
        logger.warn('Rate limit exceeded (Redis)', {
          userId,
          count,
          maxRequests: this.config.maxRequests,
          resetAt,
        });

        return {
          allowed: false,
          remaining: 0,
          resetAt,
        };
      }

      return {
        allowed: true,
        remaining: this.config.maxRequests - count,
        resetAt,
      };
    } catch (error) {
      logger.error('Redis rate limit check failed, allowing request', {
        userId,
        error: error instanceof Error ? error.message : String(error),
      });

      return {
        allowed: true,
        remaining: this.config.maxRequests - 1,
        resetAt: now + this.windowMs,
      };
    }
  }

  async reset(userId: string): Promise<void> {
    const key = this.buildKey(userId);
    try {
      await this.redis.del(key);
      logger.debug('Rate limit reset (Redis)', { userId });
    } catch (error) {
      logger.error('Failed to reset rate limit (Redis)', {
        userId,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  createError(resetAt: number): ServiceError {
    return {
      code: ErrorCode.RATE_LIMIT_EXCEEDED,
      message: `Rate limit exceeded. Try again later.`,
      details: { resetAt },
    };
  }

  async getMetrics(): Promise<{
    keysCount: number;
    memoryUsage: string;
  }> {
    try {
      const pattern = `${this.keyPrefix}:*`;
      let keysCount = 0;
      const stream = this.redis.scanStream({ match: pattern, count: 100 });
      for await (const batch of stream) {
        keysCount += (batch as string[]).length;
      }

      const info = await this.redis.info('memory');
      const memoryMatch = info.match(/used_memory_human:(.+)/);
      const memoryUsage = memoryMatch ? memoryMatch[1].trim() : 'unknown';

      return {
        keysCount,
        memoryUsage,
      };
    } catch (error) {
      logger.error('Failed to get Redis rate limit metrics', {
        error: error instanceof Error ? error.message : String(error),
      });

      return {
        keysCount: 0,
        memoryUsage: 'unknown',
      };
    }
  }

  private buildKey(userId: string): string {
    return `${this.keyPrefix}:${userId}`;
  }

  // eslint-disable-next-line @typescript-eslint/require-await
  async cleanup(): Promise<void> {
    logger.debug('Redis rate limiter cleanup not needed (TTL handles expiration)');
  }
}
