import { jest } from '@jest/globals';
import Redis from 'ioredis';
import type { MessageContent } from '../../src/services/MessageMonitorService.js';
import type { Client } from 'discord.js';
import {
  ensureRedisChecked,
  cleanupRedisTestConnection,
  type RedisTestContext,
} from '../utils/redis-test-helper.js';

const mockChannelService = {
  getChannelConfig: jest.fn<() => Promise<any>>(),
};

const mockApiClient = {
  similaritySearch: jest.fn<() => Promise<any>>(),
  requestNote: jest.fn<() => Promise<any>>(),
};

const mockClient = {} as Client;

const mockGuildOnboardingService = {
  isOnboarded: jest.fn<() => Promise<boolean>>().mockResolvedValue(true),
  getOnboardingStatus: jest.fn<() => Promise<any>>(),
  startOnboarding: jest.fn<() => Promise<any>>(),
  completeOnboarding: jest.fn<() => Promise<any>>(),
};

jest.unstable_mockModule('../../src/services/MonitoredChannelService.js', () => ({
  MonitoredChannelService: jest.fn(() => mockChannelService),
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.mock('../../src/logger.js', () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  },
}));

const { MessageMonitorService } = await import('../../src/services/MessageMonitorService.js');

describe('MessageMonitorService - Queue Integration Tests', () => {
  let testContext: RedisTestContext;
  let redis: Redis;
  let service: InstanceType<typeof MessageMonitorService>;

  beforeAll(async () => {
    testContext = await ensureRedisChecked();
  });

  afterAll(async () => {
    await cleanupRedisTestConnection();
  });

  beforeEach(async () => {
    if (!testContext.available || !testContext.redis) return;

    redis = testContext.redis;
    // Use key-based cleanup instead of flushdb() to avoid interfering with parallel tests
    const opennnotesKeys = await redis.keys('opennotes:*');
    if (opennnotesKeys.length > 0) {
      await redis.del(...opennnotesKeys);
    }
    service = new MessageMonitorService(mockClient, mockGuildOnboardingService as any, redis);
  });

  afterEach(() => {
    if (service) {
      service.shutdown();
    }
  });

  describe('Queue Size Limits', () => {
    it('should enforce max queue size', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const testMessages: MessageContent[] = Array.from({ length: 1100 }, (_, i) => ({
        messageId: `msg-${i}`,
        channelId: 'channel-123',
        guildId: 'guild-123',
        authorId: 'user-123',
        content: `Test message ${i}`,
        timestamp: Date.now(),
        channelConfig: {
          id: 'channel-123',
          community_server_id: 'guild-123',
          channel_id: 'channel-123',
          enabled: true,
          dataset_tags: ['health'],
          similarity_threshold: 0.7,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      }));

      for (const msg of testMessages) {
        await (service as any).queueMessage(msg);
      }

      const metrics = await service.getMetrics();
      expect(metrics.queueSize).toBeLessThanOrEqual(1000);
      expect(metrics.maxQueueSize).toBe(1000);
    });

    it('should track overflow count', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const testMessages: MessageContent[] = Array.from({ length: 1100 }, (_, i) => ({
        messageId: `msg-${i}`,
        channelId: 'channel-123',
        guildId: 'guild-123',
        authorId: 'user-123',
        content: `Test message ${i}`,
        timestamp: Date.now(),
        channelConfig: {
          id: 'channel-123',
          community_server_id: 'guild-123',
          channel_id: 'channel-123',
          enabled: true,
          dataset_tags: ['health'],
          similarity_threshold: 0.7,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      }));

      for (const msg of testMessages) {
        await (service as any).queueMessage(msg);
      }

      const metrics = await service.getMetrics();
      expect(metrics.overflowCount).toBe(100);
    });

    it('should drop oldest messages when queue overflows', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const firstMessage: MessageContent = {
        messageId: 'msg-first',
        channelId: 'channel-123',
        guildId: 'guild-123',
        authorId: 'user-123',
        content: 'First message',
        timestamp: Date.now(),
        channelConfig: {
          id: 'channel-123',
          community_server_id: 'guild-123',
          channel_id: 'channel-123',
          enabled: true,
          dataset_tags: ['health'],
          similarity_threshold: 0.7,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      };

      await (service as any).queueMessage(firstMessage);

      for (let i = 0; i < 1000; i++) {
        await (service as any).queueMessage({
          ...firstMessage,
          messageId: `msg-${i}`,
          content: `Message ${i}`,
        });
      }

      const nextMessage = await service.getNextMessage();
      expect(nextMessage?.messageId).not.toBe('msg-first');
    });

    it('should update metrics after processing messages', async () => {
      if (!testContext.available) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      for (let i = 0; i < 50; i++) {
        await (service as any).queueMessage({
          messageId: `msg-${i}`,
          channelId: 'channel-123',
          guildId: 'guild-123',
          authorId: 'user-123',
          content: `Message ${i}`,
          timestamp: Date.now(),
          channelConfig: {
            id: 'channel-123',
            community_server_id: 'guild-123',
            channel_id: 'channel-123',
            enabled: true,
            dataset_tags: ['health'],
            similarity_threshold: 0.7,
          },
        });
      }

      const beforeMetrics = await service.getMetrics();
      expect(beforeMetrics.queueSize).toBe(50);

      for (let i = 0; i < 25; i++) {
        await service.getNextMessage();
      }

      const afterMetrics = await service.getMetrics();
      expect(afterMetrics.queueSize).toBe(25);
      expect(afterMetrics.utilizationPercent).toBe(2.5);
    });
  });
});
