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
  checkClaimRelevance: jest.fn<() => Promise<any>>(),
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

describe('MessageMonitorService - Claim Relevance Check', () => {
  let service: InstanceType<typeof MessageMonitorService>;
  const mockRedis = {} as any;

  const testGuildId = 'guild-123456789';

  const testMessageContent = {
    messageId: 'msg-123',
    channelId: 'channel-456',
    guildId: testGuildId,
    authorId: '00000000-0000-0001-aaaa-000000000789',
    content: 'Test message content about a claim that vaccines cause autism',
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
              title: 'Vaccines and Autism Claim',
              content: 'This claim about vaccines causing autism has been debunked',
              summary: 'Vaccines do not cause autism',
              rating: 'FALSE',
              source_url: 'https://snopes.com/vaccines-autism',
              similarity_score: score,
              cosine_similarity: score,
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

  function makePreviouslySeenResponse() {
    return {
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
    };
  }

  beforeEach(() => {
    jest.clearAllMocks();
    mockApiClient.requestNote.mockResolvedValue(undefined);
    mockApiClient.checkPreviouslySeen.mockResolvedValue(makePreviouslySeenResponse());
    mockApiClient.checkClaimRelevance.mockResolvedValue({
      outcome: 'relevant',
      reasoning: 'The message makes a factual claim that matches the fact-check',
      shouldFlag: true,
    });
    service = new MessageMonitorService(mockClient, mockRedis);
  });

  afterEach(() => {
    service.shutdown();
  });

  describe('relevance check integration in processMessage', () => {
    it('should call checkClaimRelevance when a similarity match is above threshold', async () => {
      mockApiClient.similaritySearch.mockResolvedValue(makeSimilarityResponse(0.85));

      await (service as any).processMessage(testMessageContent);

      expect(mockApiClient.checkClaimRelevance).toHaveBeenCalledWith({
        originalMessage: testMessageContent.content,
        matchedContent: 'This claim about vaccines causing autism has been debunked',
        matchedSource: 'https://snopes.com/vaccines-autism',
        similarityScore: 0.85,
      });
    });

    it('should use dataset_name as matchedSource when source_url is missing', async () => {
      const response = makeSimilarityResponse(0.85);
      response.data.attributes.matches[0].source_url = null as any;
      mockApiClient.similaritySearch.mockResolvedValue(response);

      await (service as any).processMessage(testMessageContent);

      expect(mockApiClient.checkClaimRelevance).toHaveBeenCalledWith(
        expect.objectContaining({
          matchedSource: 'snopes',
        })
      );
    });

    it('should create note request when relevance check says shouldFlag=true', async () => {
      mockApiClient.similaritySearch.mockResolvedValue(makeSimilarityResponse(0.85));
      mockApiClient.checkClaimRelevance.mockResolvedValue({
        outcome: 'relevant',
        reasoning: 'The message is making a factual claim',
        shouldFlag: true,
      });

      await (service as any).processMessage(testMessageContent);

      expect(mockApiClient.requestNote).toHaveBeenCalledTimes(1);
    });

    it('should NOT create note request when relevance check says shouldFlag=false', async () => {
      mockApiClient.similaritySearch.mockResolvedValue(makeSimilarityResponse(0.85));
      mockApiClient.checkClaimRelevance.mockResolvedValue({
        outcome: 'not_relevant',
        reasoning: 'The message is discussing the topic but not making a claim',
        shouldFlag: false,
      });

      await (service as any).processMessage(testMessageContent);

      expect(mockApiClient.requestNote).not.toHaveBeenCalled();
      expect(mockLogger.info).toHaveBeenCalledWith(
        'Claim relevance check determined match is not relevant, skipping note request',
        expect.objectContaining({
          messageId: testMessageContent.messageId,
          outcome: 'not_relevant',
          reasoning: 'The message is discussing the topic but not making a claim',
        })
      );
    });

    it('should still create note request when relevance check fails (returns null) - fail-open', async () => {
      mockApiClient.similaritySearch.mockResolvedValue(makeSimilarityResponse(0.85));
      mockApiClient.checkClaimRelevance.mockResolvedValue(null);

      await (service as any).processMessage(testMessageContent);

      expect(mockApiClient.requestNote).toHaveBeenCalledTimes(1);
      expect(mockLogger.info).toHaveBeenCalledWith(
        'Claim relevance check failed, proceeding with note request (fail-open)',
        expect.objectContaining({
          messageId: testMessageContent.messageId,
        })
      );
    });

    it('should NOT call checkClaimRelevance when similarity score is below threshold', async () => {
      mockApiClient.similaritySearch.mockResolvedValue(makeSimilarityResponse(0.55));

      await (service as any).processMessage(testMessageContent);

      expect(mockApiClient.checkClaimRelevance).not.toHaveBeenCalled();
      expect(mockApiClient.requestNote).not.toHaveBeenCalled();
    });

    it('should NOT call checkClaimRelevance when no matches exist', async () => {
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

      expect(mockApiClient.checkClaimRelevance).not.toHaveBeenCalled();
      expect(mockApiClient.requestNote).not.toHaveBeenCalled();
    });

    it('should handle indeterminate outcome with shouldFlag=true as normal flagging', async () => {
      mockApiClient.similaritySearch.mockResolvedValue(makeSimilarityResponse(0.75));
      mockApiClient.checkClaimRelevance.mockResolvedValue({
        outcome: 'indeterminate',
        reasoning: 'Cannot determine with confidence',
        shouldFlag: true,
      });

      await (service as any).processMessage(testMessageContent);

      expect(mockApiClient.requestNote).toHaveBeenCalledTimes(1);
    });

    it('should handle content_filtered outcome with shouldFlag=false', async () => {
      mockApiClient.similaritySearch.mockResolvedValue(makeSimilarityResponse(0.75));
      mockApiClient.checkClaimRelevance.mockResolvedValue({
        outcome: 'content_filtered',
        reasoning: 'Content was filtered by safety system',
        shouldFlag: false,
      });

      await (service as any).processMessage(testMessageContent);

      expect(mockApiClient.requestNote).not.toHaveBeenCalled();
    });
  });
});
