import { jest } from '@jest/globals';
import type { Client } from 'discord.js';

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

const mockResolveCommunityServerId = jest.fn<() => Promise<string>>();

const mockClient = {
  channels: {
    cache: {
      get: jest.fn(),
    },
  },
} as unknown as Client;

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

jest.unstable_mockModule('../../src/lib/community-server-resolver.js', () => ({
  resolveCommunityServerId: mockResolveCommunityServerId,
}));

const mockLogger = {
  info: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
  debug: jest.fn(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const { MessageMonitorService } = await import('../../src/services/MessageMonitorService.js');

describe('MessageMonitorService - UUID Resolution', () => {
  let service: InstanceType<typeof MessageMonitorService>;
  const mockRedis = {} as any;

  const testGuildId = 'guild-123456789';
  const resolvedUuid = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';

  const testMessageContent = {
    messageId: 'msg-123',
    channelId: 'channel-456',
    guildId: testGuildId,
    authorId: 'user-789',
    content: 'Test message content about a claim',
    timestamp: Date.now(),
    channelConfig: {
      id: 'config-123',
      community_server_id: resolvedUuid,
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
    mockResolveCommunityServerId.mockResolvedValue(resolvedUuid);
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
          rrf_score_threshold: 0,
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

  describe('createNoteRequestForMatch - UUID resolution', () => {
    it('should resolve guild ID to UUID before calling requestNote', async () => {
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
            rrf_score_threshold: 0,
            total_matches: 1,
          },
        },
      };

      await (service as any).createNoteRequestForMatch(testMessageContent, similarityResponse);

      expect(mockResolveCommunityServerId).toHaveBeenCalledWith(testGuildId);
      expect(mockResolveCommunityServerId).toHaveBeenCalledTimes(1);

      expect(mockApiClient.requestNote).toHaveBeenCalledWith(
        expect.objectContaining({
          community_server_id: resolvedUuid,
          messageId: testMessageContent.messageId,
        })
      );
    });

    it('should NOT use guildId directly in requestNote', async () => {
      const similarityResponse = {
        jsonapi: { version: '1.1' },
        data: {
          type: 'similarity-search-results',
          id: 'search-124',
          attributes: {
            matches: [testSimilarityMatch],
            query_text: 'test',
            dataset_tags: ['snopes'],
            similarity_threshold: 0.7,
            rrf_score_threshold: 0,
            total_matches: 1,
          },
        },
      };

      await (service as any).createNoteRequestForMatch(testMessageContent, similarityResponse);

      expect(mockApiClient.requestNote).not.toHaveBeenCalledWith(
        expect.objectContaining({
          community_server_id: testGuildId,
        })
      );
    });

    it('should handle UUID resolution errors gracefully', async () => {
      mockResolveCommunityServerId.mockRejectedValue(new Error('Community server not found'));

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
            rrf_score_threshold: 0,
            total_matches: 1,
          },
        },
      };

      await (service as any).createNoteRequestForMatch(testMessageContent, similarityResponse);

      expect(mockResolveCommunityServerId).toHaveBeenCalledWith(testGuildId);
      expect(mockApiClient.requestNote).not.toHaveBeenCalled();
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to create note request for similarity match',
        expect.objectContaining({
          messageId: testMessageContent.messageId,
        })
      );
    });
  });

  describe('createAutoRequestForSimilarContent - UUID resolution', () => {
    it('should resolve guild ID to UUID before calling requestNote', async () => {
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

      expect(mockResolveCommunityServerId).toHaveBeenCalledWith(testGuildId);
      expect(mockResolveCommunityServerId).toHaveBeenCalledTimes(1);

      expect(mockApiClient.requestNote).toHaveBeenCalledWith(
        expect.objectContaining({
          community_server_id: resolvedUuid,
          messageId: testMessageContent.messageId,
        })
      );
    });

    it('should NOT use guildId directly in requestNote', async () => {
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

      expect(mockApiClient.requestNote).not.toHaveBeenCalledWith(
        expect.objectContaining({
          community_server_id: testGuildId,
        })
      );
    });

    it('should handle UUID resolution errors gracefully', async () => {
      mockResolveCommunityServerId.mockRejectedValue(new Error('Community server not found'));

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

      expect(mockResolveCommunityServerId).toHaveBeenCalledWith(testGuildId);
      expect(mockApiClient.requestNote).not.toHaveBeenCalled();
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to create note request for similar content',
        expect.objectContaining({
          messageId: testMessageContent.messageId,
        })
      );
    });
  });

  describe('Both code paths use the same resolution pattern', () => {
    it('should use the same resolveCommunityServerId function in both paths', async () => {
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
            rrf_score_threshold: 0,
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

      expect(mockResolveCommunityServerId).toHaveBeenCalledTimes(2);
      expect(mockResolveCommunityServerId).toHaveBeenNthCalledWith(1, testGuildId);
      expect(mockResolveCommunityServerId).toHaveBeenNthCalledWith(2, testGuildId);

      expect(mockApiClient.requestNote).toHaveBeenCalledTimes(2);
      const calls = mockApiClient.requestNote.mock.calls as unknown[][];
      const firstCall = calls[0]?.[0] as { community_server_id: string } | undefined;
      const secondCall = calls[1]?.[0] as { community_server_id: string } | undefined;

      expect(firstCall?.community_server_id).toBe(resolvedUuid);
      expect(secondCall?.community_server_id).toBe(resolvedUuid);
    });
  });
});
