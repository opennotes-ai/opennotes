import { jest } from '@jest/globals';
import type { RedisCacheAdapter } from '../../../src/cache/adapters/redis.js';

const mockRedisClass = jest.fn();
const mockSubscriberTemplate = {
  subscribe: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
  unsubscribe: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
  disconnect: jest.fn(),
  on: jest.fn(),
};

jest.unstable_mockModule('ioredis', () => ({
  __esModule: true,
  default: mockRedisClass,
}));

const { RedisCacheAdapter: RedisCacheAdapterClass } = await import('../../../src/cache/adapters/redis.js');

describe('RedisCacheAdapter - Subscription Management', () => {
  let adapter!: RedisCacheAdapter;
  let mockRedisInstance: any;
  let mockSubscriber: any;

  beforeEach(() => {
    mockSubscriber = {
      subscribe: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      unsubscribe: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      disconnect: jest.fn(),
      on: jest.fn(),
    };

    mockRedisInstance = {
      connect: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      disconnect: jest.fn(),
      duplicate: jest.fn().mockReturnValue(mockSubscriber),
      on: jest.fn(),
      ping: jest.fn<() => Promise<string>>().mockResolvedValue('PONG'),
      removeAllListeners: jest.fn(),
    };

    mockRedisClass.mockImplementation(() => mockRedisInstance);

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

  describe('Subscribe', () => {
    it('should create new subscriber for first subscription', async () => {
      const handler = jest.fn();

      await adapter.subscribe('test-channel', handler);

      expect(mockRedisInstance.duplicate).toHaveBeenCalledTimes(1);
      expect(mockSubscriber.subscribe).toHaveBeenCalledWith('test-channel');
    });

    it('should reuse existing subscriber for same channel', async () => {
      const handler1 = jest.fn();
      const handler2 = jest.fn();

      await adapter.subscribe('test-channel', handler1);
      await adapter.subscribe('test-channel', handler2);

      expect(mockRedisInstance.duplicate).toHaveBeenCalledTimes(1);
      expect(mockSubscriber.subscribe).toHaveBeenCalledTimes(1);
    });

    it('should create separate subscribers for different channels', async () => {
      const handler1 = jest.fn();
      const handler2 = jest.fn();

      const mockSubscriber2 = {
        subscribe: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        unsubscribe: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        disconnect: jest.fn(),
        on: jest.fn(),
      };

      mockRedisInstance.duplicate
        .mockReturnValueOnce(mockSubscriber)
        .mockReturnValueOnce(mockSubscriber2);

      await adapter.subscribe('channel-1', handler1);
      await adapter.subscribe('channel-2', handler2);

      expect(mockRedisInstance.duplicate).toHaveBeenCalledTimes(2);
      expect(mockSubscriber.subscribe).toHaveBeenCalledWith('channel-1');
      expect(mockSubscriber2.subscribe).toHaveBeenCalledWith('channel-2');
    });

    it('should handle subscription errors', async () => {
      const handler = jest.fn();
      mockSubscriber.subscribe.mockRejectedValueOnce(new Error('Connection failed'));

      await expect(adapter.subscribe('test-channel', handler)).rejects.toThrow('Connection failed');
    });
  });

  describe('Unsubscribe', () => {
    it('should unsubscribe and disconnect subscriber', async () => {
      const handler = jest.fn();

      await adapter.subscribe('test-channel', handler);
      await adapter.unsubscribe('test-channel');

      expect(mockSubscriber.unsubscribe).toHaveBeenCalledWith('test-channel');
      expect(mockSubscriber.disconnect).toHaveBeenCalled();
    });

    it('should handle unsubscribe for non-existent channel', async () => {
      await expect(adapter.unsubscribe('non-existent')).resolves.not.toThrow();
    });

    it('should handle unsubscribe errors gracefully', async () => {
      const handler = jest.fn();

      await adapter.subscribe('test-channel', handler);
      mockSubscriber.unsubscribe.mockRejectedValueOnce(new Error('Unsubscribe failed'));

      await expect(adapter.unsubscribe('test-channel')).resolves.not.toThrow();
    });
  });

  describe('Stop and Cleanup', () => {
    it('should clean up all subscribers on stop', async () => {
      const handler1 = jest.fn();
      const handler2 = jest.fn();

      const mockSubscriber2 = {
        subscribe: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        unsubscribe: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        disconnect: jest.fn(),
        on: jest.fn(),
      };

      mockRedisInstance.duplicate
        .mockReturnValueOnce(mockSubscriber)
        .mockReturnValueOnce(mockSubscriber2);

      await adapter.subscribe('channel-1', handler1);
      await adapter.subscribe('channel-2', handler2);

      adapter.stop();

      expect(mockSubscriber.unsubscribe).toHaveBeenCalledWith('channel-1');
      expect(mockSubscriber.disconnect).toHaveBeenCalled();
      expect(mockSubscriber2.unsubscribe).toHaveBeenCalledWith('channel-2');
      expect(mockSubscriber2.disconnect).toHaveBeenCalled();
    });

    it('should handle cleanup errors gracefully', async () => {
      const handler = jest.fn();

      await adapter.subscribe('test-channel', handler);
      mockSubscriber.unsubscribe.mockImplementation(() => {
        throw new Error('Cleanup error');
      });

      expect(() => adapter.stop()).not.toThrow();
    });

    it('should disconnect main client after cleaning subscribers', async () => {
      const handler = jest.fn();

      await adapter.subscribe('test-channel', handler);

      // Simulate the connect event callback that was registered during adapter construction
      const connectCallbacks = mockRedisInstance.on.mock.calls
        .filter((call: any[]) => call[0] === 'connect')
        .map((call: any[]) => call[1]);

      // Manually trigger the connect callback to set isConnected = true
      connectCallbacks.forEach((callback: Function) => callback());

      adapter.stop();

      expect(mockSubscriber.disconnect).toHaveBeenCalled();
      expect(mockRedisInstance.disconnect).toHaveBeenCalled();
    });
  });

  describe('Connection Leak Prevention', () => {
    it('should not create duplicate connections for same channel', async () => {
      const handler = jest.fn();

      for (let i = 0; i < 10; i++) {
        await adapter.subscribe('test-channel', handler);
      }

      expect(mockRedisInstance.duplicate).toHaveBeenCalledTimes(1);
    });

    it('should track subscriber count correctly', async () => {
      const handler = jest.fn();

      const mockSubscriber2 = {
        subscribe: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        unsubscribe: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        disconnect: jest.fn(),
        on: jest.fn(),
      };

      const mockSubscriber3 = {
        subscribe: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        unsubscribe: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        disconnect: jest.fn(),
        on: jest.fn(),
      };

      mockRedisInstance.duplicate
        .mockReturnValueOnce(mockSubscriber)
        .mockReturnValueOnce(mockSubscriber2)
        .mockReturnValueOnce(mockSubscriber3);

      await adapter.subscribe('channel-1', handler);
      await adapter.subscribe('channel-2', handler);
      await adapter.subscribe('channel-3', handler);

      expect(mockRedisInstance.duplicate).toHaveBeenCalledTimes(3);

      await adapter.unsubscribe('channel-2');

      expect(mockSubscriber2.disconnect).toHaveBeenCalled();
    });
  });

  describe('Message Handling', () => {
    it('should register message handler for subscriber', async () => {
      const handler = jest.fn();

      await adapter.subscribe('test-channel', handler);

      expect(mockSubscriber.on).toHaveBeenCalledWith('message', expect.any(Function));
    });

    it('should call handler only for matching channel', async () => {
      const handler = jest.fn();

      await adapter.subscribe('test-channel', handler);

      const messageHandler = mockSubscriber.on.mock.calls.find(
        (call: any[]) => call[0] === 'message'
      )?.[1];

      messageHandler('test-channel', 'test message');
      expect(handler).toHaveBeenCalledWith('test message');

      handler.mockClear();

      messageHandler('other-channel', 'other message');
      expect(handler).not.toHaveBeenCalled();
    });
  });
});
