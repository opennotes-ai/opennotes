import { jest } from '@jest/globals';
import type { RedisCacheAdapter } from '../../../src/cache/adapters/redis.js';

process.env.DISCORD_TOKEN = 'test-token';
process.env.CLIENT_ID = 'test-client-id';
process.env.SERVER_URL = 'http://localhost:3000';
process.env.API_KEY = 'test-api-key';

const mockRedisClass = jest.fn();

jest.unstable_mockModule('ioredis', () => ({
  __esModule: true,
  default: mockRedisClass,
}));

jest.unstable_mockModule('../../../src/logger.js', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    warn: jest.fn(),
    debug: jest.fn(),
  },
}));

jest.unstable_mockModule('../../../src/utils/url-sanitizer.js', () => ({
  sanitizeConnectionUrl: (url: string) => url.replace(/:[^:@]+@/, ':***@'),
}));

jest.unstable_mockModule('../../../src/utils/safe-json.js', () => ({
  safeJSONParse: JSON.parse,
  safeJSONStringify: JSON.stringify,
}));

const { RedisCacheAdapter: RedisCacheAdapterClass } = await import('../../../src/cache/adapters/redis.js');

describe('RedisCacheAdapter - Memory Leak Prevention', () => {
  let adapter!: RedisCacheAdapter;
  let mockRedisClient: any;

  beforeEach(() => {
    mockRedisClient = {
      connect: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      disconnect: jest.fn(),
      on: jest.fn(),
      removeAllListeners: jest.fn(),
      duplicate: jest.fn(),
    };

    mockRedisClass.mockImplementation(() => mockRedisClient);

    adapter = new RedisCacheAdapterClass({
      host: 'localhost',
      port: 6379,
    });
  });

  afterEach(() => {
    if (adapter) {
      adapter.stop();
    }
    jest.clearAllMocks();
  });

  describe('event listener registration', () => {
    it('should register event listeners on construction', () => {
      expect(mockRedisClient.on).toHaveBeenCalledWith('connect', expect.any(Function));
      expect(mockRedisClient.on).toHaveBeenCalledWith('ready', expect.any(Function));
      expect(mockRedisClient.on).toHaveBeenCalledWith('error', expect.any(Function));
      expect(mockRedisClient.on).toHaveBeenCalledWith('close', expect.any(Function));
      expect(mockRedisClient.on).toHaveBeenCalledWith('reconnecting', expect.any(Function));
      expect(mockRedisClient.on).toHaveBeenCalledWith('end', expect.any(Function));
    });
  });

  describe('stop method', () => {
    it('should remove all event listeners', () => {
      adapter.stop();
      expect(mockRedisClient.removeAllListeners).toHaveBeenCalledTimes(1);
    });

    it('should disconnect the client', () => {
      // Access private field for testing
      (adapter as any).isConnected = true;
      adapter.stop();
      expect(mockRedisClient.disconnect).toHaveBeenCalledTimes(1);
    });

    it('should clean up subscribers before disconnecting', () => {
      const mockSubscriber = {
        unsubscribe: jest.fn(),
        disconnect: jest.fn(),
      };

      (adapter as any).subscribers.set('test-channel', mockSubscriber);

      adapter.stop();

      expect(mockSubscriber.unsubscribe).toHaveBeenCalledWith('test-channel');
      expect(mockSubscriber.disconnect).toHaveBeenCalled();
      expect((adapter as any).subscribers.size).toBe(0);
    });

    it('should remove listeners before disconnecting to prevent leaks', () => {
      (adapter as any).isConnected = true;

      const callOrder: string[] = [];
      mockRedisClient.removeAllListeners.mockImplementation(() => {
        callOrder.push('removeAllListeners');
        return mockRedisClient;
      });
      mockRedisClient.disconnect.mockImplementation(() => {
        callOrder.push('disconnect');
      });

      adapter.stop();

      expect(callOrder).toEqual(['removeAllListeners', 'disconnect']);
    });
  });

  describe('memory leak prevention', () => {
    it('should not accumulate listeners when adapter is restarted', () => {
      adapter.stop();

      const adapter2 = new RedisCacheAdapterClass({
        host: 'localhost',
        port: 6379,
      });

      expect(mockRedisClient.on).toHaveBeenCalledTimes(12);

      adapter2.stop();
      expect(mockRedisClient.removeAllListeners).toHaveBeenCalledTimes(2);
    });

    it('should handle stop being called multiple times', () => {
      (adapter as any).isConnected = true;

      adapter.stop();
      adapter.stop();

      expect(mockRedisClient.removeAllListeners).toHaveBeenCalledTimes(2);
      expect(mockRedisClient.disconnect).toHaveBeenCalledTimes(2);
    });

    it('should clean up all subscribers on stop', () => {
      const mockSubscriber1 = {
        unsubscribe: jest.fn(),
        disconnect: jest.fn(),
      };

      const mockSubscriber2 = {
        unsubscribe: jest.fn(),
        disconnect: jest.fn(),
      };

      (adapter as any).subscribers.set('channel-1', mockSubscriber1);
      (adapter as any).subscribers.set('channel-2', mockSubscriber2);

      expect((adapter as any).subscribers.size).toBe(2);

      adapter.stop();

      expect((adapter as any).subscribers.size).toBe(0);
      expect(mockSubscriber1.unsubscribe).toHaveBeenCalled();
      expect(mockSubscriber2.unsubscribe).toHaveBeenCalled();
    });
  });

  describe('subscriber error handling', () => {
    it('should handle errors when cleaning up subscribers', () => {
      const mockSubscriber = {
        unsubscribe: jest.fn().mockImplementation(() => {
          throw new Error('Unsubscribe failed');
        }),
        disconnect: jest.fn(),
      };

      (adapter as any).subscribers.set('test-channel', mockSubscriber);

      expect(() => adapter.stop()).not.toThrow();
      expect((adapter as any).subscribers.size).toBe(0);
    });

    it('should continue cleanup even if one subscriber fails', () => {
      const failingSubscriber = {
        unsubscribe: jest.fn().mockImplementation(() => {
          throw new Error('Failed');
        }),
        disconnect: jest.fn(),
      };

      const workingSubscriber = {
        unsubscribe: jest.fn(),
        disconnect: jest.fn(),
      };

      (adapter as any).subscribers.set('failing-channel', failingSubscriber);
      (adapter as any).subscribers.set('working-channel', workingSubscriber);

      adapter.stop();

      expect(workingSubscriber.unsubscribe).toHaveBeenCalled();
      expect(workingSubscriber.disconnect).toHaveBeenCalled();
      expect((adapter as any).subscribers.size).toBe(0);
    });
  });
});
