import { jest } from '@jest/globals';
import type { Client } from 'discord.js';
import { loggerFactory } from '../factories/index.js';

const mockChannelService = {
  getChannelConfig: jest.fn<() => Promise<any>>(),
};

const mockApiClient = {
  similaritySearch: jest.fn<() => Promise<any>>(),
  requestNote: jest.fn<() => Promise<any>>(),
};

const mockClient = {} as Client;

const mockLogger = loggerFactory.build();

// Mock RedisQueue to avoid needing real Redis
class MockRedisQueue<T> {
  private items: T[] = [];
  private metrics = {
    enqueued: 0,
    dequeued: 0,
    errors: 0,
    overflows: 0,
  };
  private readonly maxSize: number;

  constructor(_redis: any, _queueName: string, options: any) {
    this.maxSize = options.maxSize ?? 10000;
  }

  async enqueue(item: T): Promise<boolean> {
    if (this.items.length >= this.maxSize) {
      this.items.pop();
      this.metrics.overflows++;
    }
    this.items.unshift(item);
    this.metrics.enqueued++;
    return true;
  }

  async dequeue(): Promise<T | null> {
    const item = this.items.pop();
    if (item) {
      this.metrics.dequeued++;
    }
    return item || null;
  }

  async dequeueBatch(batchSize: number): Promise<T[]> {
    const batch: T[] = [];
    for (let i = 0; i < batchSize && this.items.length > 0; i++) {
      const item = this.items.pop();
      if (item) {
        batch.push(item);
        this.metrics.dequeued++;
      }
    }
    return batch;
  }

  async size(): Promise<number> {
    return this.items.length;
  }

  async getMetrics() {
    return {
      enqueued: this.metrics.enqueued,
      dequeued: this.metrics.dequeued,
      errors: this.metrics.errors,
      currentSize: this.items.length,
      overflows: this.metrics.overflows,
    };
  }

  async clear(): Promise<number> {
    const size = this.items.length;
    this.items = [];
    return size;
  }

  async peek(): Promise<T | null> {
    return this.items[this.items.length - 1] || null;
  }

  getQueueKey(): string {
    return 'mock:queue';
  }
}

jest.unstable_mockModule('../../src/utils/redis-queue.js', () => ({
  RedisQueue: MockRedisQueue,
}));

jest.unstable_mockModule('../../src/services/MonitoredChannelService.js', () => ({
  MonitoredChannelService: jest.fn(() => mockChannelService),
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const { MessageMonitorService } = await import('../../src/services/MessageMonitorService.js');

describe('MessageMonitorService - Metrics Unit Tests', () => {
  let service: InstanceType<typeof MessageMonitorService>;
  const mockRedis = {} as any;

  beforeEach(() => {
    mockChannelService.getChannelConfig.mockReset();
    mockLogger.info.mockReset();
    mockLogger.warn.mockReset();
    mockLogger.error.mockReset();
    mockLogger.debug.mockReset();
    service = new MessageMonitorService(mockClient, mockRedis);
  });

  afterEach(() => {
    service.shutdown();
  });

  describe('Queue Metrics', () => {
    it('should return accurate metrics', async () => {
      for (let i = 0; i < 100; i++) {
        await (service as any).queueMessage({
          messageId: `msg-${i}`,
          channelId: 'channel-123',
          guildId: 'guild-123',
          authorId: '00000000-0000-0001-aaaa-123',
          content: `Message ${i}`,
          timestamp: Date.now(),
          channelConfig: {
            type: 'monitored-channels',
            id: 'channel-123',
            attributes: {
              community_server_id: 'guild-123',
              channel_id: 'channel-123',
              enabled: true,
              dataset_tags: ['health'],
              similarity_threshold: 0.7,
            },
          },
        });
      }

      const metrics = await service.getMetrics();
      expect(metrics.queueSize).toBe(100);
      expect(metrics.maxQueueSize).toBe(1000);
      expect(metrics.utilizationPercent).toBe(10);
      expect(metrics.overflowCount).toBe(0);
    });

    it('should calculate utilization percentage correctly', async () => {
      for (let i = 0; i < 500; i++) {
        await (service as any).queueMessage({
          messageId: `msg-${i}`,
          channelId: 'channel-123',
          guildId: 'guild-123',
          authorId: '00000000-0000-0001-aaaa-123',
          content: `Message ${i}`,
          timestamp: Date.now(),
          channelConfig: {
            type: 'monitored-channels',
            id: 'channel-123',
            attributes: {
              community_server_id: 'guild-123',
              channel_id: 'channel-123',
              enabled: true,
              dataset_tags: ['health'],
              similarity_threshold: 0.7,
            },
          },
        });
      }

      const metrics = await service.getMetrics();
      expect(metrics.utilizationPercent).toBe(50);
    });
  });

  describe('getQueueSize', () => {
    it('should return current queue size', async () => {
      const size1 = await service.getQueueSize();
      expect(size1).toBe(0);

      for (let i = 0; i < 10; i++) {
        await (service as any).queueMessage({
          messageId: `msg-${i}`,
          channelId: 'channel-123',
          guildId: 'guild-123',
          authorId: '00000000-0000-0001-aaaa-123',
          content: `Message ${i}`,
          timestamp: Date.now(),
          channelConfig: {
            type: 'monitored-channels',
            id: 'channel-123',
            attributes: {
              community_server_id: 'guild-123',
              channel_id: 'channel-123',
              enabled: true,
              dataset_tags: ['health'],
              similarity_threshold: 0.7,
            },
          },
        });
      }

      const size2 = await service.getQueueSize();
      expect(size2).toBe(10);
    });
  });

  describe('shutdown', () => {
    it('should report metrics on shutdown', async () => {
      for (let i = 0; i < 100; i++) {
        await (service as any).queueMessage({
          messageId: `msg-${i}`,
          channelId: 'channel-123',
          guildId: 'guild-123',
          authorId: '00000000-0000-0001-aaaa-123',
          content: `Message ${i}`,
          timestamp: Date.now(),
          channelConfig: {
            type: 'monitored-channels',
            id: 'channel-123',
            attributes: {
              community_server_id: 'guild-123',
              channel_id: 'channel-123',
              enabled: true,
              dataset_tags: ['health'],
              similarity_threshold: 0.7,
            },
          },
        });
      }

      const metrics = await service.getMetrics();
      expect(metrics.queueSize).toBe(100);

      service.shutdown();
    });
  });

  describe('queueMessage error handling', () => {
    it('should log errors when queueMessage fails during handleMessage', async () => {
      const mockMessage = {
        id: 'msg-123',
        channelId: 'channel-123',
        guildId: 'guild-123',
        author: {
          id: 'user-123',
          bot: false,
        },
        system: false,
        webhookId: null,
        content: 'Test message content',
        createdTimestamp: Date.now(),
        embeds: [],
      };

      (service as any).monitoredChannelService = {
        getChannelConfig: jest.fn<() => Promise<any>>().mockResolvedValue({
          type: 'monitored-channels',
          id: 'channel-123',
          attributes: {
            community_server_id: 'guild-123',
            channel_id: 'channel-123',
            enabled: true,
            dataset_tags: ['health'],
            similarity_threshold: 0.7,
          },
        }),
      };

      const redisError = new Error('Redis connection failed');
      const originalQueueMessage = (service as any).queueMessage.bind(service);
      (service as any).queueMessage = jest.fn<() => Promise<void>>().mockRejectedValue(redisError);

      await service.handleMessage(mockMessage as any);

      await new Promise(resolve => setTimeout(resolve, 50));

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to queue message',
        expect.objectContaining({
          messageId: 'msg-123',
          error: 'Redis connection failed',
        })
      );

      (service as any).queueMessage = originalQueueMessage;
    });
  });
});
