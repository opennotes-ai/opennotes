import type { Redis } from 'ioredis';
import { RedisRateLimitService } from './RedisRateLimitService.js';
import { RateLimitResult, ServiceError } from './types.js';
import { logger } from '../logger.js';

export interface RateLimiterInterface {
  check(userId: string): Promise<RateLimitResult>;
  reset(userId: string): Promise<void>;
  createError(resetAt: number): ServiceError;
  cleanup?(): Promise<void>;
}

export interface RateLimitFactoryConfig {
  useRedis: boolean;
  maxRequests: number;
  windowSeconds: number;
  keyPrefix?: string;
}

export class RateLimitFactory {
  static create(
    config: RateLimitFactoryConfig,
    redis: Redis
  ): RateLimiterInterface {
    if (!config.useRedis) {
      throw new Error('In-memory rate limiting is no longer supported. Set useRedis: true');
    }

    logger.info('Using Redis-backed rate limiter', {
      maxRequests: config.maxRequests,
      windowSeconds: config.windowSeconds,
      keyPrefix: config.keyPrefix,
    });

    return new RedisRateLimiterAdapter(
      new RedisRateLimitService(redis, {
        maxRequests: config.maxRequests,
        windowSeconds: config.windowSeconds,
        keyPrefix: config.keyPrefix,
      })
    );
  }
}

class RedisRateLimiterAdapter implements RateLimiterInterface {
  constructor(private limiter: RedisRateLimitService) {}

  async check(userId: string): Promise<RateLimitResult> {
    return this.limiter.check(userId);
  }

  async reset(userId: string): Promise<void> {
    return this.limiter.reset(userId);
  }

  createError(resetAt: number): ServiceError {
    return this.limiter.createError(resetAt);
  }

  async cleanup(): Promise<void> {
    return this.limiter.cleanup();
  }
}
