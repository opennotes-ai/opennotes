import { jest } from '@jest/globals';
import type { RedisCacheAdapter } from '../../src/cache/adapters/redis.js';
import {
  ensureRedisChecked,
  cleanupRedisTestConnection,
  type RedisTestContext,
} from '../utils/redis-test-helper.js';
import { loggerFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/utils/url-sanitizer.js', () => ({
  sanitizeConnectionUrl: (url: string) => url.replace(/:[^:@]+@/, ':***@'),
}));

jest.unstable_mockModule('../../src/utils/safe-json.js', () => ({
  safeJSONParse: JSON.parse,
  safeJSONStringify: JSON.stringify,
}));

const { RedisCacheAdapter: RedisCacheAdapterClass } = await import('../../src/cache/adapters/redis.js');

describe('Cache Adapter Selection', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
    jest.clearAllMocks();
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  describe('Redis-only Configuration', () => {
    it('should use Redis adapter when REDIS_URL is configured', async () => {
      process.env.REDIS_URL = 'redis://localhost:6379';

      const { cache } = await import('../../src/cache.js');

      expect(cache.constructor.name).toBe('RedisCacheAdapter');
    });

    it('should throw error when REDIS_URL is not configured', async () => {
      delete process.env.REDIS_URL;

      await expect(async () => {
        await import('../../src/cache.js');
      }).rejects.toThrow('REDIS_URL environment variable is required');
    });
  });
});

// TODO(task-832): Fix Redis connection instability in test environment
describe.skip('RedisCacheAdapter', () => {
  let testContext: RedisTestContext;
  let cache!: RedisCacheAdapter;

  beforeAll(async () => {
    testContext = await ensureRedisChecked();

    if (testContext.available) {
      cache = new RedisCacheAdapterClass({
        url: process.env.REDIS_URL || 'redis://localhost:6379',
        defaultTtl: 300,
        keyPrefix: 'test',
        maxSize: 100,
        evictionPolicy: 'lru',
      });
    }
  });

  afterAll(async () => {
    if (cache) {
      await cache.clear();
      cache.stop();
    }
    await cleanupRedisTestConnection();
  });

  describe('Connection', () => {
    it('should start and connect to Redis', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      cache.start();

      await new Promise(resolve => setTimeout(resolve, 100));

      expect(await cache.ping()).toBe(true);
    });
  });

  describe('Basic Operations', () => {
    it('should set and get a value', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await cache.set('key1', 'value1');
      const value = await cache.get<string>('key1');

      expect(value).toBe('value1');
    });

    it('should return null for non-existent keys', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const value = await cache.get<string>('nonexistent');

      expect(value).toBeNull();
    });

    it('should delete a key', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await cache.set('key1', 'value1');
      const deleted = await cache.delete('key1');
      const value = await cache.get<string>('key1');

      expect(deleted).toBe(true);
      expect(value).toBeNull();
    });

    it('should check if a key exists', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await cache.set('key1', 'value1');

      expect(await cache.exists('key1')).toBe(true);
      expect(await cache.exists('nonexistent')).toBe(false);
    });

    it('should handle TTL expiration', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await cache.set('key1', 'value1', 1);

      await new Promise(resolve => setTimeout(resolve, 1100));

      const value = await cache.get<string>('key1');
      expect(value).toBeNull();
    });
  });

  describe('Batch Operations', () => {
    it('should get multiple keys', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await cache.set('key1', 'value1');
      await cache.set('key2', 'value2');
      await cache.set('key3', 'value3');

      const values = await cache.mget(['key1', 'key2', 'key3', 'nonexistent']);

      expect(values).toEqual(['value1', 'value2', 'value3', null]);
    });

    it('should set multiple keys', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const items = new Map([
        ['key1', 'value1'],
        ['key2', 'value2'],
        ['key3', 'value3'],
      ]);

      const result = await cache.mset(items);

      expect(result).toBe(true);
      expect(await cache.get<string>('key1')).toBe('value1');
      expect(await cache.get<string>('key2')).toBe('value2');
      expect(await cache.get<string>('key3')).toBe('value3');
    });
  });

  describe('Pub/Sub', () => {
    it('should publish and receive messages', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const receivedMessages: string[] = [];
      const handler = (message: string) => {
        receivedMessages.push(message);
      };

      await cache.subscribe('test-channel', handler);

      await new Promise(resolve => setTimeout(resolve, 100));

      await cache.publish('test-channel', 'test-message');

      await new Promise(resolve => setTimeout(resolve, 100));

      expect(receivedMessages).toContain('test-message');

      await cache.unsubscribe('test-channel');
    });
  });

  describe('Metrics', () => {
    it('should track cache hits and misses', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await cache.clear();

      await cache.set('key1', 'value1');

      await cache.get('key1');
      await cache.get('key1');
      await cache.get('nonexistent');

      const metrics = cache.getMetrics();

      expect(metrics.hits).toBeGreaterThanOrEqual(2);
      expect(metrics.misses).toBeGreaterThanOrEqual(1);
    });
  });

  describe('Clear Operations', () => {
    it('should clear all keys', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      await cache.set('clear-test:1', 'value1');
      await cache.set('clear-test:2', 'value2');

      const count = await cache.clear('clear-test:*');

      expect(count).toBeGreaterThanOrEqual(2);
      expect(await cache.get('clear-test:1')).toBeNull();
      expect(await cache.get('clear-test:2')).toBeNull();
    });
  });
});

// TODO(task-832): Fix Redis connection instability in test environment
describe.skip('Cache Invalidation Across Instances', () => {
  let testContext: RedisTestContext;

  beforeAll(async () => {
    testContext = await ensureRedisChecked();
  });

  afterAll(async () => {
    await cleanupRedisTestConnection();
  });

  it('should propagate cache invalidation via pub/sub', async () => {
    if (!testContext.available) {
      console.log(`[SKIPPED] ${testContext.reason}`);
      return;
    }

    const cache1 = new RedisCacheAdapterClass({
      url: process.env.REDIS_URL || 'redis://localhost:6379',
      defaultTtl: 300,
      keyPrefix: 'invalidation-test',
    });

    const cache2 = new RedisCacheAdapterClass({
      url: process.env.REDIS_URL || 'redis://localhost:6379',
      defaultTtl: 300,
      keyPrefix: 'invalidation-test',
    });

    cache1.start();
    cache2.start();

    await new Promise(resolve => setTimeout(resolve, 100));

    let invalidationReceived = false;
    await cache2.subscribe('cache:invalidate', (message: string) => {
      if (message === 'test-key') {
        invalidationReceived = true;
      }
    });

    await new Promise(resolve => setTimeout(resolve, 100));

    await cache1.set('test-key', 'value1');
    await cache1.publish('cache:invalidate', 'test-key');

    await new Promise(resolve => setTimeout(resolve, 200));

    expect(invalidationReceived).toBe(true);

    await cache2.unsubscribe('cache:invalidate');
    await cache1.clear();
    cache1.stop();
    cache2.stop();
  });
});
