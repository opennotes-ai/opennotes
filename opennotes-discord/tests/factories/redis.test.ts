import { describe, it, expect, beforeEach, jest } from '@jest/globals';
import {
  redisClientFactory,
  disconnectedRedisFactory,
  pubSubRedisFactory,
  createMockSubscriber,
  createMockRedisClass,
  simulateMessage,
  asRedis,
  type MockRedisClient,
  type MockRedisSubscriber,
} from './redis.js';

describe('Redis Factory', () => {
  describe('redisClientFactory', () => {
    it('should create a mock Redis client with default values', () => {
      const client = redisClientFactory.build();

      expect(client.status).toBe('ready');
      expect(client.get).toBeDefined();
      expect(client.set).toBeDefined();
      expect(client.disconnect).toBeDefined();
      expect(client.duplicate).toBeDefined();
      expect(client.on).toBeDefined();
    });

    it('should support basic get/set operations', async () => {
      const client = redisClientFactory.build();

      await client.set('key1', 'value1');
      const value = await client.get('key1');

      expect(value).toBe('value1');
    });

    it('should support initial data via transient params', async () => {
      const client = redisClientFactory.build(
        {},
        {
          transient: {
            initialData: {
              existingKey: 'existingValue',
              anotherKey: 'anotherValue',
            },
          },
        }
      );

      expect(await client.get('existingKey')).toBe('existingValue');
      expect(await client.get('anotherKey')).toBe('anotherValue');
      expect(await client.get('nonexistent')).toBeNull();
    });

    it('should support del operation', async () => {
      const client = redisClientFactory.build(
        {},
        { transient: { initialData: { key1: 'value1', key2: 'value2' } } }
      );

      const deleted = await client.del('key1');

      expect(deleted).toBe(1);
      expect(await client.get('key1')).toBeNull();
      expect(await client.get('key2')).toBe('value2');
    });

    it('should support exists operation', async () => {
      const client = redisClientFactory.build(
        {},
        { transient: { initialData: { key1: 'value1' } } }
      );

      expect(await client.exists('key1')).toBe(1);
      expect(await client.exists('nonexistent')).toBe(0);
      expect(await client.exists('key1', 'nonexistent')).toBe(1);
    });

    it('should support incr/decr operations', async () => {
      const client = redisClientFactory.build(
        {},
        { transient: { initialData: { counter: '5' } } }
      );

      expect(await client.incr('counter')).toBe(6);
      expect(await client.incr('counter')).toBe(7);
      expect(await client.decr('counter')).toBe(6);

      expect(await client.incr('newCounter')).toBe(1);
    });

    it('should support mget/mset operations', async () => {
      const client = redisClientFactory.build();

      await client.mset('key1', 'value1', 'key2', 'value2');
      const values = await client.mget('key1', 'key2', 'key3');

      expect(values).toEqual(['value1', 'value2', null]);
    });

    it('should support keys pattern matching', async () => {
      const client = redisClientFactory.build(
        {},
        {
          transient: {
            initialData: {
              'user:1': 'alice',
              'user:2': 'bob',
              'session:1': 'data',
            },
          },
        }
      );

      const userKeys = await client.keys('user:*');

      expect(userKeys).toHaveLength(2);
      expect(userKeys).toContain('user:1');
      expect(userKeys).toContain('user:2');
    });

    it('should support ping', async () => {
      const client = redisClientFactory.build();

      expect(await client.ping()).toBe('PONG');
    });

    it('should support flushall/flushdb', async () => {
      const client = redisClientFactory.build(
        {},
        { transient: { initialData: { key1: 'value1', key2: 'value2' } } }
      );

      await client.flushall();

      expect(await client.get('key1')).toBeNull();
      expect(await client.get('key2')).toBeNull();
    });

    it('should support multi/exec transactions', async () => {
      const client = redisClientFactory.build();

      const multi = client.multi();
      multi.set('key1', 'value1');
      multi.incr('counter');

      const results = await multi.exec();

      expect(results).toEqual([]);
      expect(multi.set).toHaveBeenCalled();
      expect(multi.incr).toHaveBeenCalled();
    });

    it('should support pipeline operations', async () => {
      const client = redisClientFactory.build();

      const pipeline = client.pipeline();
      pipeline.set('key1', 'value1');
      pipeline.get('key1');

      const results = await pipeline.exec();

      expect(results).toEqual([]);
      expect(pipeline.set).toHaveBeenCalled();
      expect(pipeline.get).toHaveBeenCalled();
    });

    it('should support custom status via transient params', () => {
      const client = redisClientFactory.build(
        {},
        { transient: { status: 'connecting' } }
      );

      expect(client.status).toBe('connecting');
    });
  });

  describe('disconnectedRedisFactory', () => {
    it('should create a disconnected Redis client', () => {
      const client = disconnectedRedisFactory.build();

      expect(client.status).toBe('end');
    });
  });

  describe('pubSubRedisFactory', () => {
    it('should create a Redis client configured for pub/sub', () => {
      const client = pubSubRedisFactory.build();

      expect(client.status).toBe('ready');
      expect(client.duplicate).toBeDefined();
    });
  });

  describe('duplicate() and subscribers', () => {
    let client: MockRedisClient;
    let subscriber: MockRedisSubscriber;

    beforeEach(() => {
      client = redisClientFactory.build();
      subscriber = client.duplicate() as MockRedisSubscriber;
    });

    it('should create a subscriber via duplicate()', () => {
      expect(subscriber.subscribe).toBeDefined();
      expect(subscriber.unsubscribe).toBeDefined();
      expect(subscriber.disconnect).toBeDefined();
      expect(subscriber.on).toBeDefined();
    });

    it('should support subscribing to channels', async () => {
      await subscriber.subscribe('test-channel');

      expect(subscriber.subscribe).toHaveBeenCalledWith('test-channel');
    });

    it('should support registering message handlers', () => {
      const handler = jest.fn();

      subscriber.on('message', handler);

      expect(subscriber.on).toHaveBeenCalledWith('message', handler);
    });

    it('should support unsubscribing', async () => {
      await subscriber.subscribe('test-channel');
      await subscriber.unsubscribe('test-channel');

      expect(subscriber.unsubscribe).toHaveBeenCalledWith('test-channel');
    });

    it('should support custom subscriber factory', () => {
      const customSubscriber = createMockSubscriber();
      customSubscriber.subscribe.mockResolvedValue(42);

      const clientWithCustomSub = redisClientFactory.build(
        {},
        { transient: { subscriberFactory: () => customSubscriber } }
      );

      const sub = clientWithCustomSub.duplicate() as MockRedisSubscriber;

      expect(sub).toBe(customSubscriber);
    });
  });

  describe('createMockSubscriber', () => {
    it('should create a standalone mock subscriber', () => {
      const subscriber = createMockSubscriber();

      expect(subscriber.subscribe).toBeDefined();
      expect(subscriber.unsubscribe).toBeDefined();
      expect(subscriber.disconnect).toBeDefined();
      expect(subscriber.on).toBeDefined();
    });

    it('should chain on() calls', () => {
      const subscriber = createMockSubscriber();

      const result = subscriber.on('message', jest.fn()).on('error', jest.fn());

      expect(result).toBe(subscriber);
    });
  });

  describe('simulateMessage', () => {
    it('should trigger message handlers on subscriber', () => {
      const subscriber = createMockSubscriber();
      const handler = jest.fn();

      subscriber.on('message', handler);
      simulateMessage(subscriber, 'test-channel', 'test message');

      expect(handler).toHaveBeenCalledWith('test-channel', 'test message');
    });

    it('should trigger multiple message handlers', () => {
      const subscriber = createMockSubscriber();
      const handler1 = jest.fn();
      const handler2 = jest.fn();

      subscriber.on('message', handler1);
      subscriber.on('message', handler2);
      simulateMessage(subscriber, 'channel', 'message');

      expect(handler1).toHaveBeenCalledWith('channel', 'message');
      expect(handler2).toHaveBeenCalledWith('channel', 'message');
    });

    it('should not trigger non-message handlers', () => {
      const subscriber = createMockSubscriber();
      const messageHandler = jest.fn();
      const errorHandler = jest.fn();

      subscriber.on('message', messageHandler);
      subscriber.on('error', errorHandler);
      simulateMessage(subscriber, 'channel', 'message');

      expect(messageHandler).toHaveBeenCalled();
      expect(errorHandler).not.toHaveBeenCalled();
    });
  });

  describe('createMockRedisClass', () => {
    it('should create a mock Redis constructor', () => {
      const MockRedis = createMockRedisClass();

      const client = MockRedis();

      expect(client.get).toBeDefined();
      expect(client.set).toBeDefined();
      expect(client.status).toBe('ready');
    });

    it('should accept transient params', () => {
      const MockRedis = createMockRedisClass({
        status: 'connecting',
        initialData: { key: 'value' },
      });

      const client = MockRedis();

      expect(client.status).toBe('connecting');
    });
  });

  describe('asRedis', () => {
    it('should cast MockRedisClient to Redis type', () => {
      const client = redisClientFactory.build();

      const redis = asRedis(client);

      expect(redis).toBe(client);
    });
  });

  describe('event handlers', () => {
    it('should register and track event handlers', () => {
      const client = redisClientFactory.build();
      const connectHandler = jest.fn();
      const errorHandler = jest.fn();

      client.on('connect', connectHandler);
      client.on('error', errorHandler);

      expect(client.on).toHaveBeenCalledWith('connect', connectHandler);
      expect(client.on).toHaveBeenCalledWith('error', errorHandler);
    });

    it('should chain on() calls', () => {
      const client = redisClientFactory.build();

      const result = client.on('connect', jest.fn()).on('error', jest.fn());

      expect(result).toStrictEqual(client);
    });

    it('should support removeAllListeners', () => {
      const client = redisClientFactory.build();

      client.on('connect', jest.fn());
      const result = client.removeAllListeners();

      expect(client.removeAllListeners).toHaveBeenCalled();
      expect(result).toStrictEqual(client);
    });
  });

  describe('publish operations', () => {
    it('should support publish', async () => {
      const client = redisClientFactory.build();

      const count = await client.publish('channel', 'message');

      expect(count).toBe(1);
      expect(client.publish).toHaveBeenCalledWith('channel', 'message');
    });
  });
});
