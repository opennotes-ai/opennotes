import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import RedisMock from 'ioredis-mock';
import type { Redis } from 'ioredis';
import { RateLimitFactory } from '../../src/services/RateLimitFactory.js';

describe('RateLimitFactory', () => {
  let redis: Redis;

  beforeEach(() => {
    redis = new RedisMock() as Redis;
  });

  afterEach(async () => {
    await redis.flushall();
    redis.disconnect();
  });

  describe('create', () => {
    it('should create Redis-backed limiter when useRedis is true', async () => {
      const limiter = RateLimitFactory.create(
        {
          useRedis: true,
          maxRequests: 5,
          windowSeconds: 60,
          keyPrefix: 'test',
        },
        redis
      );

      const result = await limiter.check('user123');

      expect(result.allowed).toBe(true);
      expect(result.remaining).toBe(4);
    });

    it('should throw error when useRedis is false (in-memory no longer supported)', () => {
      expect(() =>
        RateLimitFactory.create(
          {
            useRedis: false,
            maxRequests: 5,
            windowSeconds: 60,
          },
          redis
        )
      ).toThrow('In-memory rate limiting is no longer supported');
    });

    it('should pass configuration to underlying limiter', async () => {
      const limiter = RateLimitFactory.create(
        {
          useRedis: true,
          maxRequests: 2,
          windowSeconds: 1,
        },
        redis
      );

      await limiter.check('user123');
      await limiter.check('user123');

      const result = await limiter.check('user123');
      expect(result.allowed).toBe(false);
    });
  });

  describe('Adapter Interface', () => {
    it('should provide consistent interface for Redis limiter', async () => {
      const limiter = RateLimitFactory.create(
        {
          useRedis: true,
          maxRequests: 5,
          windowSeconds: 60,
        },
        redis
      );

      expect(typeof limiter.check).toBe('function');
      expect(typeof limiter.reset).toBe('function');
      expect(typeof limiter.createError).toBe('function');
      expect(typeof limiter.cleanup).toBe('function');
    });

    it('should handle async check for Redis limiter', async () => {
      const limiter = RateLimitFactory.create(
        {
          useRedis: true,
          maxRequests: 5,
          windowSeconds: 60,
        },
        redis
      );

      const result = limiter.check('user123');
      expect(result).toBeInstanceOf(Promise);

      const resolved = await result;
      expect(resolved.allowed).toBe(true);
    });

  });
});
