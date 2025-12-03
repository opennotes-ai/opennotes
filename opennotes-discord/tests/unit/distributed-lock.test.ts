import { jest } from '@jest/globals';
import Redis from 'ioredis';
import { DistributedLock } from '../../src/utils/distributed-lock.js';
import {
  ensureRedisChecked,
  cleanupRedisTestConnection,
  type RedisTestContext,
} from '../utils/redis-test-helper.js';

jest.mock('../../src/logger.js', () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  },
}));

describe('DistributedLock', () => {
  let testContext: RedisTestContext;
  let redis: Redis;
  let lock: DistributedLock;

  beforeAll(async () => {
    testContext = await ensureRedisChecked();
  });

  afterAll(async () => {
    await cleanupRedisTestConnection();
  });

  beforeEach(async () => {
    if (!testContext.available || !testContext.redis) return;

    redis = testContext.redis;
    await redis.flushdb();
    lock = new DistributedLock(redis);
  });

  describe('Lock Acquisition', () => {
    it('should successfully acquire a lock', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const acquired = await lock.acquire('test-lock');

      expect(acquired).toBe(true);
    });

    it('should fail to acquire a lock that is already held', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await lock.acquire('test-lock');

      const lock2 = new DistributedLock(redis);
      const acquired = await lock2.acquire('test-lock', {
        ttlMs: 5000,
        maxRetries: 2,
        retryDelayMs: 50,
      });

      expect(acquired).toBe(false);
    });

    it('should acquire a lock after it expires', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await lock.acquire('test-lock', { ttlMs: 100 });

      await new Promise(resolve => setTimeout(resolve, 150));

      const lock2 = new DistributedLock(redis);
      const acquired = await lock2.acquire('test-lock');

      expect(acquired).toBe(true);
    });

    it('should retry acquiring a lock until successful', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const lock1 = new DistributedLock(redis);
      const lock2 = new DistributedLock(redis);

      await lock1.acquire('test-lock', { ttlMs: 200 });

      setTimeout(async () => {
        await lock1.release('test-lock');
      }, 100);

      const acquired = await lock2.acquire('test-lock', {
        ttlMs: 5000,
        maxRetries: 10,
        retryDelayMs: 50,
      });

      expect(acquired).toBe(true);
    });
  });

  describe('Lock Release', () => {
    it('should successfully release a lock', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await lock.acquire('test-lock');
      const released = await lock.release('test-lock');

      expect(released).toBe(true);
    });

    it('should fail to release a lock not held by this instance', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const lock1 = new DistributedLock(redis);
      const lock2 = new DistributedLock(redis);

      await lock1.acquire('test-lock');

      const released = await lock2.release('test-lock');

      expect(released).toBe(false);
    });

    it('should return false when releasing a lock that does not exist', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const released = await lock.release('nonexistent-lock');

      expect(released).toBe(false);
    });

    it('should allow re-acquiring a lock after release', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await lock.acquire('test-lock');
      await lock.release('test-lock');

      const lock2 = new DistributedLock(redis);
      const acquired = await lock2.acquire('test-lock');

      expect(acquired).toBe(true);
    });
  });

  describe('Lock Extension', () => {
    it('should successfully extend a lock TTL', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await lock.acquire('test-lock', { ttlMs: 1000 });

      const extended = await lock.extend('test-lock', 5000);

      expect(extended).toBe(true);

      const ttl = await redis.pttl('lock:test-lock');
      expect(ttl).toBeGreaterThan(4000);
      expect(ttl).toBeLessThanOrEqual(5000);
    });

    it('should fail to extend a lock not held by this instance', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const lock1 = new DistributedLock(redis);
      const lock2 = new DistributedLock(redis);

      await lock1.acquire('test-lock');

      const extended = await lock2.extend('test-lock', 5000);

      expect(extended).toBe(false);
    });

    it('should fail to extend a lock that has expired', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await lock.acquire('test-lock', { ttlMs: 100 });

      await new Promise(resolve => setTimeout(resolve, 150));

      const extended = await lock.extend('test-lock', 5000);

      expect(extended).toBe(false);
    });
  });

  describe('withLock Helper', () => {
    it('should execute function with lock protection', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      let executed = false;

      const result = await lock.withLock('test-lock', async () => {
        executed = true;
        return 'success';
      });

      expect(executed).toBe(true);
      expect(result).toBe('success');
    });

    it('should release lock after function execution', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await lock.withLock('test-lock', async () => {
        return 'success';
      });

      const lock2 = new DistributedLock(redis);
      const acquired = await lock2.acquire('test-lock');

      expect(acquired).toBe(true);
    });

    it('should release lock even if function throws error', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await expect(
        lock.withLock('test-lock', async () => {
          throw new Error('Test error');
        })
      ).rejects.toThrow('Test error');

      const lock2 = new DistributedLock(redis);
      const acquired = await lock2.acquire('test-lock');

      expect(acquired).toBe(true);
    });

    it('should return null if lock acquisition fails', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const lock1 = new DistributedLock(redis);
      const lock2 = new DistributedLock(redis);

      await lock1.acquire('test-lock', { ttlMs: 5000 });

      const result = await lock2.withLock(
        'test-lock',
        async () => {
          return 'success';
        },
        {
          ttlMs: 5000,
          maxRetries: 2,
          retryDelayMs: 50,
        }
      );

      expect(result).toBeNull();
    });
  });

  describe('Multi-Instance Coordination', () => {
    it('should prevent duplicate processing across multiple instances', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const lock1 = new DistributedLock(redis);
      const lock2 = new DistributedLock(redis);
      const lock3 = new DistributedLock(redis);

      let processCount = 0;
      const processTask = async (lockInstance: DistributedLock) => {
        const acquired = await lockInstance.acquire('task:123', {
          ttlMs: 100,
          maxRetries: 0,
        });

        if (acquired) {
          processCount++;
          await new Promise(resolve => setTimeout(resolve, 50));
          await lockInstance.release('task:123');
        }
      };

      await Promise.all([
        processTask(lock1),
        processTask(lock2),
        processTask(lock3),
      ]);

      expect(processCount).toBe(1);
    });

    it('should distribute work across instances when locks are released', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const lock1 = new DistributedLock(redis);
      const lock2 = new DistributedLock(redis);
      const lock3 = new DistributedLock(redis);

      const processedBy: number[] = [];

      const processTask = async (lockInstance: DistributedLock, instanceId: number) => {
        const acquired = await lockInstance.acquire('task:456', {
          ttlMs: 100,
          maxRetries: 20,
          retryDelayMs: 10,
        });

        if (acquired) {
          processedBy.push(instanceId);
          await new Promise(resolve => setTimeout(resolve, 20));
          await lockInstance.release('task:456');
        }
      };

      await processTask(lock1, 1);
      await processTask(lock2, 2);
      await processTask(lock3, 3);

      expect(processedBy).toHaveLength(3);
      expect(processedBy).toEqual([1, 2, 3]);
    });
  });

  describe('Lock Value Security', () => {
    it('should generate cryptographically secure lock values with 32 hex characters', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await lock.acquire('test-lock');

      const lockValue = await redis.get('lock:test-lock');
      expect(lockValue).not.toBeNull();

      const parts = lockValue!.split('-');
      expect(parts.length).toBe(3);

      const randomPart = parts[2];
      expect(randomPart).toMatch(/^[a-f0-9]{32}$/);
    });

    it('should generate unique lock values on each acquisition', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const lockValues = new Set<string>();

      for (let i = 0; i < 10; i++) {
        await lock.acquire(`test-lock-${i}`);
        const lockValue = await redis.get(`lock:test-lock-${i}`);
        lockValues.add(lockValue!);
      }

      expect(lockValues.size).toBe(10);
    });
  });

  describe('Metrics', () => {
    it('should track lock acquisitions', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await lock.acquire('lock1');
      await lock.acquire('lock2');
      await lock.acquire('lock3');

      const metrics = lock.getMetrics();

      expect(metrics.acquisitions).toBe(3);
    });

    it('should track lock releases', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await lock.acquire('lock1');
      await lock.release('lock1');

      await lock.acquire('lock2');
      await lock.release('lock2');

      const metrics = lock.getMetrics();

      expect(metrics.releases).toBe(2);
    });

    it('should track lock timeouts', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const lock1 = new DistributedLock(redis);
      const lock2 = new DistributedLock(redis);

      await lock1.acquire('test-lock', { ttlMs: 5000 });

      await lock2.acquire('test-lock', {
        ttlMs: 5000,
        maxRetries: 2,
        retryDelayMs: 10,
      });

      const metrics = lock2.getMetrics();

      expect(metrics.timeouts).toBeGreaterThanOrEqual(1);
    });

    it('should track lock contentions', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const lock1 = new DistributedLock(redis);
      const lock2 = new DistributedLock(redis);

      await lock1.acquire('test-lock', { ttlMs: 5000 });

      await lock2.acquire('test-lock', {
        ttlMs: 5000,
        maxRetries: 3,
        retryDelayMs: 10,
      });

      const metrics = lock2.getMetrics();

      expect(metrics.contentions).toBeGreaterThanOrEqual(3);
    });

    it('should calculate average acquisition time', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await lock.acquire('lock1');
      await lock.acquire('lock2');
      await lock.acquire('lock3');

      const metrics = lock.getMetrics();

      expect(metrics.averageAcquisitionTimeMs).toBeGreaterThanOrEqual(0);
    });

    it('should calculate average hold time', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await lock.acquire('lock1');
      await new Promise(resolve => setTimeout(resolve, 50));
      await lock.release('lock1');

      const metrics = lock.getMetrics();

      expect(metrics.averageHoldTimeMs).toBeGreaterThan(40);
    });
  });
});
