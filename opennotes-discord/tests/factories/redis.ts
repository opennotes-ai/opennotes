import { Factory } from 'fishery';
import { jest } from '@jest/globals';
import type { Redis, RedisOptions } from 'ioredis';

/**
 * Mock Redis subscriber for pub/sub operations.
 * Created via duplicate() in the pub/sub pattern.
 */
export interface MockRedisSubscriber {
  subscribe: jest.Mock<(channel: string) => Promise<number>>;
  unsubscribe: jest.Mock<(channel: string) => Promise<number>>;
  disconnect: jest.Mock<() => void>;
  on: jest.Mock<(event: string, callback: (...args: unknown[]) => void) => MockRedisSubscriber>;
}

/**
 * Mock Redis client with commonly used methods.
 * Includes all methods observed in the codebase test files.
 */
export interface MockRedisClient {
  get: jest.Mock<(key: string) => Promise<string | null>>;
  set: jest.Mock<(key: string, value: string, ...args: unknown[]) => Promise<'OK' | null>>;
  del: jest.Mock<(...keys: string[]) => Promise<number>>;
  exists: jest.Mock<(...keys: string[]) => Promise<number>>;
  expire: jest.Mock<(key: string, seconds: number) => Promise<number>>;
  pexpire: jest.Mock<(key: string, milliseconds: number) => Promise<number>>;
  pttl: jest.Mock<(key: string) => Promise<number>>;
  ttl: jest.Mock<(key: string) => Promise<number>>;
  incr: jest.Mock<(key: string) => Promise<number>>;
  decr: jest.Mock<(key: string) => Promise<number>>;
  mget: jest.Mock<(...keys: string[]) => Promise<(string | null)[]>>;
  mset: jest.Mock<(...args: string[]) => Promise<'OK'>>;
  keys: jest.Mock<(pattern: string) => Promise<string[]>>;
  scan: jest.Mock<(cursor: string, ...args: unknown[]) => Promise<[string, string[]]>>;
  scanStream: jest.Mock<(options?: { match?: string; count?: number }) => NodeJS.ReadableStream>;
  flushall: jest.Mock<() => Promise<'OK'>>;
  flushdb: jest.Mock<() => Promise<'OK'>>;
  ping: jest.Mock<() => Promise<string>>;

  connect: jest.Mock<() => Promise<void>>;
  disconnect: jest.Mock<() => void>;
  quit: jest.Mock<() => Promise<'OK'>>;
  duplicate: jest.Mock<(options?: Partial<RedisOptions>) => MockRedisSubscriber | MockRedisClient>;

  on: jest.Mock<(event: string, callback: (...args: unknown[]) => void) => MockRedisClient>;
  removeAllListeners: jest.Mock<(event?: string) => MockRedisClient>;

  publish: jest.Mock<(channel: string, message: string) => Promise<number>>;
  subscribe: jest.Mock<(channel: string) => Promise<number>>;
  unsubscribe: jest.Mock<(channel: string) => Promise<number>>;

  multi: jest.Mock<() => MockRedisMulti>;
  pipeline: jest.Mock<() => MockRedisPipeline>;

  eval: jest.Mock<(...args: unknown[]) => Promise<unknown>>;
  evalsha: jest.Mock<(...args: unknown[]) => Promise<unknown>>;

  defineCommand: jest.Mock<(name: string, definition: { numberOfKeys?: number; lua?: string }) => void>;

  status: string;
  options: Partial<RedisOptions>;
}

/**
 * Mock Redis multi/transaction for atomic operations.
 */
export interface MockRedisMulti {
  set: jest.Mock<(...args: unknown[]) => MockRedisMulti>;
  get: jest.Mock<(key: string) => MockRedisMulti>;
  del: jest.Mock<(...keys: string[]) => MockRedisMulti>;
  incr: jest.Mock<(key: string) => MockRedisMulti>;
  exec: jest.Mock<() => Promise<[Error | null, unknown][]>>;
}

/**
 * Mock Redis pipeline for batch operations.
 */
export interface MockRedisPipeline {
  set: jest.Mock<(...args: unknown[]) => MockRedisPipeline>;
  get: jest.Mock<(key: string) => MockRedisPipeline>;
  del: jest.Mock<(...keys: string[]) => MockRedisPipeline>;
  incr: jest.Mock<(key: string) => MockRedisPipeline>;
  exec: jest.Mock<() => Promise<[Error | null, unknown][]>>;
}

export interface RedisTransientParams {
  useIoredisMock?: boolean;
  initialData?: Record<string, string>;
  isConnected?: boolean;
  status?: 'ready' | 'connecting' | 'reconnecting' | 'end' | 'close';
  subscriberFactory?: () => MockRedisSubscriber;
  eventHandlers?: Map<string, ((...args: unknown[]) => void)[]>;
}

function createMockScanStream(data: Record<string, string>): NodeJS.ReadableStream {
  const keys = Object.keys(data);
  let emitted = false;

  const stream = {
    on: jest.fn((event: string, callback: (data?: unknown) => void) => {
      if (event === 'data' && !emitted) {
        emitted = true;
        setTimeout(() => callback(keys), 0);
      }
      if (event === 'end') {
        setTimeout(() => callback(), 10);
      }
      return stream;
    }),
    once: jest.fn((_event: string, _callback: () => void) => stream),
    pipe: jest.fn(() => stream),
    destroy: jest.fn(),
  };

  return stream as unknown as NodeJS.ReadableStream;
}

function createDefaultMulti(): MockRedisMulti {
  const multi: MockRedisMulti = {
    set: jest.fn<(...args: unknown[]) => MockRedisMulti>().mockReturnThis(),
    get: jest.fn<(key: string) => MockRedisMulti>().mockReturnThis(),
    del: jest.fn<(...keys: string[]) => MockRedisMulti>().mockReturnThis(),
    incr: jest.fn<(key: string) => MockRedisMulti>().mockReturnThis(),
    exec: jest.fn<() => Promise<[Error | null, unknown][]>>().mockResolvedValue([]),
  };

  multi.set.mockImplementation(() => multi);
  multi.get.mockImplementation(() => multi);
  multi.del.mockImplementation(() => multi);
  multi.incr.mockImplementation(() => multi);

  return multi;
}

function createDefaultPipeline(): MockRedisPipeline {
  const pipeline: MockRedisPipeline = {
    set: jest.fn<(...args: unknown[]) => MockRedisPipeline>().mockReturnThis(),
    get: jest.fn<(key: string) => MockRedisPipeline>().mockReturnThis(),
    del: jest.fn<(...keys: string[]) => MockRedisPipeline>().mockReturnThis(),
    incr: jest.fn<(key: string) => MockRedisPipeline>().mockReturnThis(),
    exec: jest.fn<() => Promise<[Error | null, unknown][]>>().mockResolvedValue([]),
  };

  pipeline.set.mockImplementation(() => pipeline);
  pipeline.get.mockImplementation(() => pipeline);
  pipeline.del.mockImplementation(() => pipeline);
  pipeline.incr.mockImplementation(() => pipeline);

  return pipeline;
}

/**
 * Creates a mock Redis subscriber for pub/sub operations.
 */
export function createMockSubscriber(): MockRedisSubscriber {
  const eventHandlers = new Map<string, ((...args: unknown[]) => void)[]>();

  const subscriber: MockRedisSubscriber = {
    subscribe: jest.fn<(channel: string) => Promise<number>>().mockResolvedValue(1),
    unsubscribe: jest.fn<(channel: string) => Promise<number>>().mockResolvedValue(1),
    disconnect: jest.fn<() => void>(),
    on: jest.fn<(event: string, callback: (...args: unknown[]) => void) => MockRedisSubscriber>(
      (event: string, callback: (...args: unknown[]) => void) => {
        const handlers = eventHandlers.get(event) ?? [];
        handlers.push(callback);
        eventHandlers.set(event, handlers);
        return subscriber;
      }
    ),
  };

  return subscriber;
}

/**
 * Simulates receiving a message on a subscriber.
 * Call this to trigger message handlers registered via subscriber.on('message', handler).
 */
export function simulateMessage(
  subscriber: MockRedisSubscriber,
  channel: string,
  message: string
): void {
  const onCalls = subscriber.on.mock.calls;
  const messageHandlers = onCalls.filter((call) => call[0] === 'message');

  for (const [, handler] of messageHandlers) {
    (handler as (channel: string, message: string) => void)(channel, message);
  }
}

export const redisClientFactory = Factory.define<MockRedisClient, RedisTransientParams>(
  ({ transientParams }) => {
    const {
      initialData = {},
      isConnected = true,
      status = 'ready',
      subscriberFactory = createMockSubscriber,
      eventHandlers = new Map(),
    } = transientParams;

    const data = new Map<string, string>(Object.entries(initialData));

    const mockClient: MockRedisClient = {
      get: jest.fn<(key: string) => Promise<string | null>>(async (key: string) => {
        return data.get(key) ?? null;
      }),
      set: jest
        .fn<(key: string, value: string, ...args: unknown[]) => Promise<'OK' | null>>(
          async (key: string, value: string) => {
            data.set(key, value);
            return 'OK';
          }
        ),
      del: jest.fn<(...keys: string[]) => Promise<number>>(async (...keys: string[]) => {
        let count = 0;
        for (const key of keys) {
          if (data.delete(key)) {
            count++;
          }
        }
        return count;
      }),
      exists: jest.fn<(...keys: string[]) => Promise<number>>(async (...keys: string[]) => {
        return keys.filter((k) => data.has(k)).length;
      }),
      expire: jest.fn<(key: string, seconds: number) => Promise<number>>().mockResolvedValue(1),
      pexpire: jest
        .fn<(key: string, milliseconds: number) => Promise<number>>()
        .mockResolvedValue(1),
      pttl: jest.fn<(key: string) => Promise<number>>().mockResolvedValue(-1),
      ttl: jest.fn<(key: string) => Promise<number>>().mockResolvedValue(-1),
      incr: jest.fn<(key: string) => Promise<number>>(async (key: string) => {
        const current = parseInt(data.get(key) ?? '0', 10);
        const next = current + 1;
        data.set(key, String(next));
        return next;
      }),
      decr: jest.fn<(key: string) => Promise<number>>(async (key: string) => {
        const current = parseInt(data.get(key) ?? '0', 10);
        const next = current - 1;
        data.set(key, String(next));
        return next;
      }),
      mget: jest.fn<(...keys: string[]) => Promise<(string | null)[]>>(
        async (...keys: string[]) => {
          return keys.map((k) => data.get(k) ?? null);
        }
      ),
      mset: jest.fn<(...args: string[]) => Promise<'OK'>>(async (...args: string[]) => {
        for (let i = 0; i < args.length; i += 2) {
          data.set(args[i], args[i + 1]);
        }
        return 'OK';
      }),
      keys: jest.fn<(pattern: string) => Promise<string[]>>(async (pattern: string) => {
        const regex = new RegExp(
          '^' + pattern.replace(/\*/g, '.*').replace(/\?/g, '.') + '$'
        );
        return [...data.keys()].filter((k) => regex.test(k));
      }),
      scan: jest
        .fn<(cursor: string, ...args: unknown[]) => Promise<[string, string[]]>>()
        .mockResolvedValue(['0', [...data.keys()]]),
      scanStream: jest.fn<(options?: { match?: string; count?: number }) => NodeJS.ReadableStream>(
        () => createMockScanStream(Object.fromEntries(data))
      ),
      flushall: jest.fn<() => Promise<'OK'>>(async () => {
        data.clear();
        return 'OK';
      }),
      flushdb: jest.fn<() => Promise<'OK'>>(async () => {
        data.clear();
        return 'OK';
      }),
      ping: jest.fn<() => Promise<string>>().mockResolvedValue('PONG'),

      connect: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      disconnect: jest.fn<() => void>(),
      quit: jest.fn<() => Promise<'OK'>>().mockResolvedValue('OK'),
      duplicate: jest.fn<() => MockRedisSubscriber | MockRedisClient>(() => subscriberFactory()),

      on: jest.fn() as MockRedisClient['on'],
      removeAllListeners: jest.fn() as MockRedisClient['removeAllListeners'],

      publish: jest.fn<(channel: string, message: string) => Promise<number>>().mockResolvedValue(1),
      subscribe: jest.fn<(channel: string) => Promise<number>>().mockResolvedValue(1),
      unsubscribe: jest.fn<(channel: string) => Promise<number>>().mockResolvedValue(1),

      multi: jest.fn<() => MockRedisMulti>(() => createDefaultMulti()),
      pipeline: jest.fn<() => MockRedisPipeline>(() => createDefaultPipeline()),

      eval: jest.fn<(...args: unknown[]) => Promise<unknown>>().mockResolvedValue(null),
      evalsha: jest.fn<(...args: unknown[]) => Promise<unknown>>().mockResolvedValue(null),

      defineCommand: jest.fn<
        (name: string, definition: { numberOfKeys?: number; lua?: string }) => void
      >(),

      status: status,
      options: {},
    };

    mockClient.on.mockImplementation(
      (event: string, callback: (...args: unknown[]) => void) => {
        const handlers = eventHandlers.get(event) ?? [];
        handlers.push(callback);
        eventHandlers.set(event, handlers);
        return mockClient;
      }
    );

    mockClient.removeAllListeners.mockImplementation(() => {
      eventHandlers.clear();
      return mockClient;
    });

    if (isConnected) {
      const connectHandlers = eventHandlers.get('connect') ?? [];
      setTimeout(() => {
        for (const handler of connectHandlers) {
          handler();
        }
      }, 0);
    }

    return mockClient;
  }
);

/**
 * Pre-configured factory for a disconnected Redis client.
 */
export const disconnectedRedisFactory = redisClientFactory.transient({
  isConnected: false,
  status: 'end',
});

/**
 * Pre-configured factory for a Redis client with pub/sub subscriber support.
 */
export const pubSubRedisFactory = redisClientFactory.transient({
  isConnected: true,
  status: 'ready',
});

/**
 * Creates a mock Redis class constructor for use with jest.unstable_mockModule.
 * This is useful when mocking the ioredis module entirely.
 */
export function createMockRedisClass(
  transientParams?: RedisTransientParams
): jest.Mock<() => MockRedisClient> {
  return jest.fn<() => MockRedisClient>(() =>
    redisClientFactory.build({}, { transient: transientParams })
  );
}

/**
 * Helper to cast the factory-built mock to the Redis type for use with
 * code that expects a real Redis instance.
 */
export function asRedis(mock: MockRedisClient): Redis {
  return mock as unknown as Redis;
}
