import { jest } from '@jest/globals';
import type { Client } from 'discord.js';
import { loggerFactory } from '../factories/index.js';

const mockChannelService = {
  getChannelConfig: jest.fn<() => Promise<any>>(),
};

const mockApiClient = {
  similaritySearch: jest.fn<() => Promise<any>>(),
  requestNote: jest.fn<() => Promise<any>>(),
  checkPreviouslySeen: jest.fn<() => Promise<any>>(),
  getNote: jest.fn<() => Promise<any>>(),
  getCommunityServerByPlatformId: jest.fn<() => Promise<any>>(),
};

const mockClient = {
  channels: {
    cache: {
      get: jest.fn(),
    },
  },
} as unknown as Client;

const mockLogger = loggerFactory.build();

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

describe('MessageMonitorService - CC Score Threshold', () => {
  let service: InstanceType<typeof MessageMonitorService>;
  const mockRedis = {} as any;

  const testGuildId = 'guild-123456789';

  const testMessageContent = {
    messageId: 'msg-123',
    channelId: 'channel-456',
    guildId: testGuildId,
    authorId: '00000000-0000-0001-aaaa-000000000789',
    content: 'Test message content about a claim',
    timestamp: Date.now(),
    channelConfig: {
      type: 'monitored-channels',
      id: 'config-123',
      attributes: {
        community_server_id: testGuildId,
        channel_id: 'channel-456',
        enabled: true,
        dataset_tags: ['snopes'],
        similarity_threshold: 0.7,
      },
    },
  };

  function makeSimilarityResponse(score: number) {
    return {
      jsonapi: { version: '1.1' },
      data: {
        type: 'similarity-search-results',
        id: 'search-123',
        attributes: {
          matches: [
            {
              id: 'match-1',
              dataset_name: 'snopes',
              dataset_tags: ['snopes'],
              title: 'Test Claim',
              content: 'This is a test claim content',
              summary: 'Test summary',
              rating: 'FALSE',
              source_url: 'https://example.com/claim',
              similarity_score: score,
            },
          ],
          query_text: 'test',
          dataset_tags: ['snopes'],
          similarity_threshold: 0.7,
          score_threshold: 0,
          total_matches: 1,
        },
      },
    };
  }

  beforeEach(() => {
    jest.clearAllMocks();
    mockApiClient.requestNote.mockResolvedValue(undefined);
    mockApiClient.checkPreviouslySeen.mockResolvedValue({
      data: {
        type: 'previously-seen-check-results',
        id: 'check-123',
        attributes: {
          should_auto_publish: false,
          should_auto_request: false,
          autopublish_threshold: 0.9,
          autorequest_threshold: 0.75,
          matches: [],
          top_match: null,
        },
      },
      jsonapi: { version: '1.1' },
    });
    service = new MessageMonitorService(mockClient, mockRedis);
  });

  afterEach(() => {
    service.shutdown();
  });

  describe('processMessage threshold filtering', () => {
    it('should skip note request creation when top score is below 0.4', async () => {
      mockApiClient.similaritySearch.mockResolvedValue(makeSimilarityResponse(0.35));

      await (service as any).processMessage(testMessageContent);

      expect(mockApiClient.requestNote).not.toHaveBeenCalled();
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Similarity match below CC score threshold, skipping note request',
        expect.objectContaining({
          messageId: testMessageContent.messageId,
          channelId: testMessageContent.channelId,
          topScore: 0.35,
          minCcScore: 0.4,
        })
      );
    });

    it('should skip note request creation when top score is 0.24', async () => {
      mockApiClient.similaritySearch.mockResolvedValue(makeSimilarityResponse(0.24));

      await (service as any).processMessage(testMessageContent);

      expect(mockApiClient.requestNote).not.toHaveBeenCalled();
    });

    it('should create note request when top score is exactly 0.4', async () => {
      mockApiClient.similaritySearch.mockResolvedValue(makeSimilarityResponse(0.4));

      await (service as any).processMessage(testMessageContent);

      expect(mockApiClient.requestNote).toHaveBeenCalledTimes(1);
    });

    it('should create note request when top score is above 0.4', async () => {
      mockApiClient.similaritySearch.mockResolvedValue(makeSimilarityResponse(0.85));

      await (service as any).processMessage(testMessageContent);

      expect(mockApiClient.requestNote).toHaveBeenCalledTimes(1);
    });

    it('should not call requestNote when no matches exist', async () => {
      mockApiClient.similaritySearch.mockResolvedValue({
        jsonapi: { version: '1.1' },
        data: {
          type: 'similarity-search-results',
          id: 'search-empty',
          attributes: {
            matches: [],
            query_text: 'test',
            dataset_tags: ['snopes'],
            similarity_threshold: 0.7,
            score_threshold: 0,
            total_matches: 0,
          },
        },
      });

      await (service as any).processMessage(testMessageContent);

      expect(mockApiClient.requestNote).not.toHaveBeenCalled();
    });
  });

  describe('createNoteRequestForMatch - fact_check_metadata fields', () => {
    it('should include fact_check_metadata in the requestNote call', async () => {
      const similarityResponse = makeSimilarityResponse(0.85);

      await (service as any).createNoteRequestForMatch(testMessageContent, similarityResponse);

      expect(mockApiClient.requestNote).toHaveBeenCalledWith(
        expect.objectContaining({
          fact_check_metadata: expect.objectContaining({
            dataset_item_id: 'match-1',
            similarity_score: 0.85,
            dataset_name: 'snopes',
            rating: 'FALSE',
          }),
        })
      );
    });
  });
});
