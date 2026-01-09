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

describe('MessageMonitorService - Platform ID Handling', () => {
  let service: InstanceType<typeof MessageMonitorService>;
  const mockRedis = {} as any;

  const testGuildId = 'guild-123456789';

  const testMessageContent = {
    messageId: 'msg-123',
    channelId: 'channel-456',
    guildId: testGuildId,
    authorId: 'user-789',
    content: 'Test message content about a claim',
    timestamp: Date.now(),
    channelConfig: {
      id: 'config-123',
      community_server_id: 'some-uuid',
      channel_id: 'channel-456',
      enabled: true,
      dataset_tags: ['snopes'],
      similarity_threshold: 0.7,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  };

  const testSimilarityMatch = {
    id: 'match-1',
    dataset_name: 'snopes',
    dataset_tags: ['snopes'],
    title: 'Test Claim',
    content: 'This is a test claim content',
    summary: 'Test summary',
    rating: 'FALSE',
    source_url: 'https://example.com/claim',
    similarity_score: 0.85,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockApiClient.requestNote.mockResolvedValue(undefined);
    mockApiClient.similaritySearch.mockResolvedValue({
      jsonapi: { version: '1.1' },
      data: {
        type: 'similarity-search-results',
        id: 'search-default',
        attributes: {
          matches: [],
          query_text: '',
          dataset_tags: [],
          similarity_threshold: 0.7,
          score_threshold: 0,
          total_matches: 0,
        },
      },
    });
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

  describe('createNoteRequestForMatch - Platform ID handling', () => {
    it('should pass platform ID (guild ID) directly to requestNote', async () => {
      const similarityResponse = {
        jsonapi: { version: '1.1' },
        data: {
          type: 'similarity-search-results',
          id: 'search-123',
          attributes: {
            matches: [testSimilarityMatch],
            query_text: 'test',
            dataset_tags: ['snopes'],
            similarity_threshold: 0.7,
            score_threshold: 0,
            total_matches: 1,
          },
        },
      };

      await (service as any).createNoteRequestForMatch(testMessageContent, similarityResponse);

      expect(mockApiClient.requestNote).toHaveBeenCalledWith(
        expect.objectContaining({
          community_server_id: testGuildId,
          messageId: testMessageContent.messageId,
        })
      );
    });

    it('should handle API errors gracefully', async () => {
      mockApiClient.requestNote.mockRejectedValue(new Error('API error'));

      const similarityResponse = {
        jsonapi: { version: '1.1' },
        data: {
          type: 'similarity-search-results',
          id: 'search-125',
          attributes: {
            matches: [testSimilarityMatch],
            query_text: 'test',
            dataset_tags: ['snopes'],
            similarity_threshold: 0.7,
            score_threshold: 0,
            total_matches: 1,
          },
        },
      };

      await (service as any).createNoteRequestForMatch(testMessageContent, similarityResponse);

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to create note request for similarity match',
        expect.objectContaining({
          messageId: testMessageContent.messageId,
        })
      );
    });
  });

  describe('createAutoRequestForSimilarContent - Platform ID handling', () => {
    it('should pass platform ID (guild ID) directly to requestNote', async () => {
      const previouslySeenResult = {
        data: {
          type: 'previously-seen-check-results',
          id: 'check-123',
          attributes: {
            should_auto_publish: false,
            should_auto_request: true,
            autopublish_threshold: 0.9,
            autorequest_threshold: 0.75,
            matches: [
              {
                id: 'prev-1',
                community_server_id: 'some-uuid',
                original_message_id: 'orig-msg-1',
                published_note_id: 'note-1',
                created_at: new Date().toISOString(),
                similarity_score: 0.8,
              },
            ],
            top_match: {
              id: 'prev-1',
              community_server_id: 'some-uuid',
              original_message_id: 'orig-msg-1',
              published_note_id: 'note-1',
              created_at: new Date().toISOString(),
              similarity_score: 0.8,
            },
          },
        },
        jsonapi: { version: '1.1' },
      };

      await (service as any).createAutoRequestForSimilarContent(testMessageContent, previouslySeenResult);

      expect(mockApiClient.requestNote).toHaveBeenCalledWith(
        expect.objectContaining({
          community_server_id: testGuildId,
          messageId: testMessageContent.messageId,
        })
      );
    });

    it('should handle API errors gracefully', async () => {
      mockApiClient.requestNote.mockRejectedValue(new Error('API error'));

      const previouslySeenResult = {
        data: {
          type: 'previously-seen-check-results',
          id: 'check-123',
          attributes: {
            should_auto_publish: false,
            should_auto_request: true,
            autopublish_threshold: 0.9,
            autorequest_threshold: 0.75,
            matches: [
              {
                id: 'prev-1',
                community_server_id: 'some-uuid',
                original_message_id: 'orig-msg-1',
                published_note_id: 'note-1',
                created_at: new Date().toISOString(),
                similarity_score: 0.8,
              },
            ],
            top_match: {
              id: 'prev-1',
              community_server_id: 'some-uuid',
              original_message_id: 'orig-msg-1',
              published_note_id: 'note-1',
              created_at: new Date().toISOString(),
              similarity_score: 0.8,
            },
          },
        },
        jsonapi: { version: '1.1' },
      };

      await (service as any).createAutoRequestForSimilarContent(testMessageContent, previouslySeenResult);

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to create note request for similar content',
        expect.objectContaining({
          messageId: testMessageContent.messageId,
        })
      );
    });
  });

  describe('Both code paths use consistent platform ID handling', () => {
    it('should use platform ID directly in both paths', async () => {
      const similarityResponse = {
        jsonapi: { version: '1.1' },
        data: {
          type: 'similarity-search-results',
          id: 'search-126',
          attributes: {
            matches: [testSimilarityMatch],
            query_text: 'test',
            dataset_tags: ['snopes'],
            similarity_threshold: 0.7,
            score_threshold: 0,
            total_matches: 1,
          },
        },
      };

      const previouslySeenResult = {
        data: {
          type: 'previously-seen-check-results',
          id: 'check-123',
          attributes: {
            should_auto_publish: false,
            should_auto_request: true,
            autopublish_threshold: 0.9,
            autorequest_threshold: 0.75,
            matches: [
              {
                id: 'prev-1',
                community_server_id: 'some-uuid',
                original_message_id: 'orig-msg-1',
                published_note_id: 'note-1',
                created_at: new Date().toISOString(),
                similarity_score: 0.8,
              },
            ],
            top_match: {
              id: 'prev-1',
              community_server_id: 'some-uuid',
              original_message_id: 'orig-msg-1',
              published_note_id: 'note-1',
              created_at: new Date().toISOString(),
              similarity_score: 0.8,
            },
          },
        },
        jsonapi: { version: '1.1' },
      };

      await (service as any).createNoteRequestForMatch(testMessageContent, similarityResponse);
      await (service as any).createAutoRequestForSimilarContent(testMessageContent, previouslySeenResult);

      expect(mockApiClient.requestNote).toHaveBeenCalledTimes(2);
      const calls = mockApiClient.requestNote.mock.calls as unknown[][];
      const firstCall = calls[0]?.[0] as { community_server_id: string } | undefined;
      const secondCall = calls[1]?.[0] as { community_server_id: string } | undefined;

      expect(firstCall?.community_server_id).toBe(testGuildId);
      expect(secondCall?.community_server_id).toBe(testGuildId);
    });
  });
});
