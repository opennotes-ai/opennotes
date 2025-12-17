import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import RedisMock from 'ioredis-mock';
import type { Redis } from 'ioredis';
import { RedisRateLimitService } from '../../src/services/RedisRateLimitService.js';
import { ErrorCode } from '../../src/services/types.js';

describe('RedisRateLimitService', () => {
  let redis: Redis;
  let rateLimiter: RedisRateLimitService;

  beforeEach(() => {
    redis = new RedisMock() as Redis;
    rateLimiter = new RedisRateLimitService(redis, {
      maxRequests: 3,
      windowSeconds: 1,
      keyPrefix: 'test:ratelimit',
    });
  });

  afterEach(async () => {
    await redis.flushall();
    redis.disconnect();
  });

  describe('check', () => {
    it('should allow requests within limit', async () => {
      const userId = 'user123';

      const result1 = await rateLimiter.check(userId);
      expect(result1.allowed).toBe(true);
      expect(result1.remaining).toBe(2);

      const result2 = await rateLimiter.check(userId);
      expect(result2.allowed).toBe(true);
      expect(result2.remaining).toBe(1);

      const result3 = await rateLimiter.check(userId);
      expect(result3.allowed).toBe(true);
      expect(result3.remaining).toBe(0);
    });

    it('should reject requests over limit', async () => {
      const userId = 'user123';

      await rateLimiter.check(userId);
      await rateLimiter.check(userId);
      await rateLimiter.check(userId);

      const result = await rateLimiter.check(userId);
      expect(result.allowed).toBe(false);
      expect(result.remaining).toBe(0);
    });

    it('should set TTL on first request', async () => {
      const userId = 'user123';

      await rateLimiter.check(userId);

      const ttl = await redis.pttl('test:ratelimit:user123');
      expect(ttl).toBeGreaterThan(0);
      expect(ttl).toBeLessThanOrEqual(1000);
    });

    it('should reset after window expires', async () => {
      const userId = 'user123';

      await rateLimiter.check(userId);
      await rateLimiter.check(userId);
      await rateLimiter.check(userId);

      const rejected = await rateLimiter.check(userId);
      expect(rejected.allowed).toBe(false);

      await redis.del('test:ratelimit:user123');

      const afterExpiry = await rateLimiter.check(userId);
      expect(afterExpiry.allowed).toBe(true);
      expect(afterExpiry.remaining).toBe(2);
    });

    it('should handle different users independently', async () => {
      const user1 = 'user1';
      const user2 = 'user2';

      await rateLimiter.check(user1);
      await rateLimiter.check(user1);
      await rateLimiter.check(user1);

      const user1Result = await rateLimiter.check(user1);
      expect(user1Result.allowed).toBe(false);

      const user2Result = await rateLimiter.check(user2);
      expect(user2Result.allowed).toBe(true);
      expect(user2Result.remaining).toBe(2);
    });

    it('should include resetAt timestamp', async () => {
      const userId = 'user123';
      const before = Date.now();

      const result = await rateLimiter.check(userId);

      expect(result.resetAt).toBeGreaterThan(before);
      expect(result.resetAt).toBeLessThanOrEqual(before + 1100);
    });

    it('should handle Redis errors gracefully', async () => {
      const brokenRedis = new RedisMock() as Redis;
      await brokenRedis.disconnect();

      const brokenLimiter = new RedisRateLimitService(brokenRedis, {
        maxRequests: 3,
        windowSeconds: 1,
      });

      const result = await brokenLimiter.check('user123');

      expect(result.allowed).toBe(true);
      expect(result.remaining).toBe(2);
    });
  });

  describe('reset', () => {
    it('should reset user rate limit', async () => {
      const userId = 'user123';

      await rateLimiter.check(userId);
      await rateLimiter.check(userId);
      await rateLimiter.check(userId);

      let result = await rateLimiter.check(userId);
      expect(result.allowed).toBe(false);

      await rateLimiter.reset(userId);

      result = await rateLimiter.check(userId);
      expect(result.allowed).toBe(true);
      expect(result.remaining).toBe(2);
    });

    it('should handle reset for non-existent user', async () => {
      await expect(rateLimiter.reset('nonexistent')).resolves.not.toThrow();
    });
  });

  describe('createError', () => {
    it('should create rate limit error with correct format', () => {
      const resetAt = Date.now() + 60000;
      const error = rateLimiter.createError(resetAt);

      expect(error.code).toBe(ErrorCode.RATE_LIMIT_EXCEEDED);
      expect(error.message).toContain('Rate limit exceeded');
      expect(error.details).toEqual({ resetAt });
    });
  });

  describe('getMetrics', () => {
    it('should return metrics', async () => {
      await rateLimiter.check('user1');
      await rateLimiter.check('user2');
      await rateLimiter.check('user3');

      const metrics = await rateLimiter.getMetrics();

      expect(metrics.keysCount).toBe(3);
      expect(metrics.memoryUsage).toBeDefined();
    });

    it('should return zero count when no keys exist', async () => {
      const metrics = await rateLimiter.getMetrics();

      expect(metrics.keysCount).toBe(0);
    });

    it('should use scanStream instead of keys for non-blocking iteration', async () => {
      const scanStreamSpy = jest.spyOn(redis, 'scanStream');
      const keysSpy = jest.spyOn(redis, 'keys');

      await rateLimiter.check('user1');
      await rateLimiter.check('user2');

      await rateLimiter.getMetrics();

      expect(scanStreamSpy).toHaveBeenCalledWith({
        match: 'test:ratelimit:*',
        count: 100,
      });
      expect(keysSpy).not.toHaveBeenCalled();

      scanStreamSpy.mockRestore();
      keysSpy.mockRestore();
    });
  });

  describe('cleanup', () => {
    it('should not throw on cleanup', async () => {
      await expect(rateLimiter.cleanup()).resolves.not.toThrow();
    });
  });

  describe('Distributed Rate Limiting', () => {
    it('should share rate limits across multiple instances', async () => {
      const limiter1 = new RedisRateLimitService(redis, {
        maxRequests: 3,
        windowSeconds: 1,
        keyPrefix: 'shared',
      });

      const limiter2 = new RedisRateLimitService(redis, {
        maxRequests: 3,
        windowSeconds: 1,
        keyPrefix: 'shared',
      });

      await limiter1.check('user123');
      await limiter1.check('user123');

      const result = await limiter2.check('user123');
      expect(result.allowed).toBe(true);
      expect(result.remaining).toBe(0);

      const rejected = await limiter2.check('user123');
      expect(rejected.allowed).toBe(false);
    });

    it('should maintain isolation with different key prefixes', async () => {
      const limiter1 = new RedisRateLimitService(redis, {
        maxRequests: 3,
        windowSeconds: 1,
        keyPrefix: 'app1',
      });

      const limiter2 = new RedisRateLimitService(redis, {
        maxRequests: 3,
        windowSeconds: 1,
        keyPrefix: 'app2',
      });

      await limiter1.check('user123');
      await limiter1.check('user123');
      await limiter1.check('user123');

      const result = await limiter2.check('user123');
      expect(result.allowed).toBe(true);
      expect(result.remaining).toBe(2);
    });
  });
});
