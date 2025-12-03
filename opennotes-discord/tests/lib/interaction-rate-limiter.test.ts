import { jest } from '@jest/globals';
import { InteractionRateLimiter } from '../../src/lib/interaction-rate-limiter.js';

describe('InteractionRateLimiter', () => {
  let rateLimiter: InteractionRateLimiter;

  beforeEach(() => {
    rateLimiter = new InteractionRateLimiter({
      cooldownMs: 1000,
    });
  });

  afterEach(() => {
    rateLimiter.destroy();
  });

  describe('isRateLimited', () => {
    it('should return false for first interaction', () => {
      expect(rateLimiter.isRateLimited('user-123')).toBe(false);
    });

    it('should return true if interaction within cooldown period', () => {
      rateLimiter.recordInteraction('user-123');
      expect(rateLimiter.isRateLimited('user-123')).toBe(true);
    });

    it('should return false after cooldown period expires', async () => {
      rateLimiter.recordInteraction('user-123');
      expect(rateLimiter.isRateLimited('user-123')).toBe(true);

      await new Promise(resolve => setTimeout(resolve, 1100));

      expect(rateLimiter.isRateLimited('user-123')).toBe(false);
    });

    it('should track different users independently', () => {
      rateLimiter.recordInteraction('user-123');

      expect(rateLimiter.isRateLimited('user-123')).toBe(true);
      expect(rateLimiter.isRateLimited('user-456')).toBe(false);
    });
  });

  describe('checkAndRecord', () => {
    it('should return false and record interaction for first use', () => {
      const isLimited = rateLimiter.checkAndRecord('user-123');

      expect(isLimited).toBe(false);
      expect(rateLimiter.isRateLimited('user-123')).toBe(true);
    });

    it('should return true and not update timestamp if rate limited', () => {
      const firstCall = rateLimiter.checkAndRecord('user-123');
      expect(firstCall).toBe(false);

      const secondCall = rateLimiter.checkAndRecord('user-123');
      expect(secondCall).toBe(true);
    });

    it('should record new interaction after cooldown expires', async () => {
      rateLimiter.checkAndRecord('user-123');

      await new Promise(resolve => setTimeout(resolve, 1100));

      const result = rateLimiter.checkAndRecord('user-123');
      expect(result).toBe(false);
    });
  });

  describe('cleanup', () => {
    it('should remove expired entries on cleanup', async () => {
      const limiterWithCleanup = new InteractionRateLimiter({
        cooldownMs: 500,
        cleanupIntervalMs: 200,
      });

      limiterWithCleanup.recordInteraction('user-123');
      limiterWithCleanup.recordInteraction('user-456');

      await new Promise(resolve => setTimeout(resolve, 1200));

      expect(limiterWithCleanup.isRateLimited('user-123')).toBe(false);
      expect(limiterWithCleanup.isRateLimited('user-456')).toBe(false);

      limiterWithCleanup.destroy();
    });
  });

  describe('destroy', () => {
    it('should clear all timestamps', () => {
      rateLimiter.recordInteraction('user-123');
      rateLimiter.recordInteraction('user-456');

      rateLimiter.destroy();

      expect(rateLimiter.isRateLimited('user-123')).toBe(false);
      expect(rateLimiter.isRateLimited('user-456')).toBe(false);
    });

    it('should stop cleanup interval', () => {
      const limiterWithCleanup = new InteractionRateLimiter({
        cooldownMs: 1000,
        cleanupIntervalMs: 500,
      });

      limiterWithCleanup.destroy();

      expect(() => limiterWithCleanup.destroy()).not.toThrow();
    });
  });

  describe('global instances', () => {
    it('should export buttonInteractionRateLimiter with 1.5s cooldown', async () => {
      const { buttonInteractionRateLimiter } = await import('../../src/lib/interaction-rate-limiter.js');

      expect(buttonInteractionRateLimiter).toBeDefined();

      const firstCall = buttonInteractionRateLimiter.checkAndRecord('test-user');
      expect(firstCall).toBe(false);

      const secondCall = buttonInteractionRateLimiter.checkAndRecord('test-user');
      expect(secondCall).toBe(true);

      await new Promise(resolve => setTimeout(resolve, 1600));

      const thirdCall = buttonInteractionRateLimiter.checkAndRecord('test-user');
      expect(thirdCall).toBe(false);
    });

    it('should export modalSubmissionRateLimiter with 2s cooldown', async () => {
      const { modalSubmissionRateLimiter } = await import('../../src/lib/interaction-rate-limiter.js');

      expect(modalSubmissionRateLimiter).toBeDefined();

      const firstCall = modalSubmissionRateLimiter.checkAndRecord('test-user-2');
      expect(firstCall).toBe(false);

      const secondCall = modalSubmissionRateLimiter.checkAndRecord('test-user-2');
      expect(secondCall).toBe(true);

      await new Promise(resolve => setTimeout(resolve, 2100));

      const thirdCall = modalSubmissionRateLimiter.checkAndRecord('test-user-2');
      expect(thirdCall).toBe(false);
    });
  });
});
