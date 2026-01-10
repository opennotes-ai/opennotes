import { jest } from '@jest/globals';
import { loggerFactory, cacheFactory } from '../factories/index.js';

interface MockResponse {
  ok: boolean;
  status?: number;
  statusText?: string;
  json?: () => Promise<unknown>;
  text?: () => Promise<string>;
  headers?: {
    get: (name: string) => string | null;
  };
}

const createMockResponse = (overrides: Partial<MockResponse> = {}): MockResponse => ({
  ok: true,
  status: 200,
  statusText: 'OK',
  json: async () => ({}),
  text: async () => '',
  headers: {
    get: (name: string) => (name === 'content-type' ? 'application/json' : null),
  },
  ...overrides,
});

const mockFetch = jest.fn<() => Promise<MockResponse>>();
global.fetch = mockFetch as unknown as typeof fetch;

const mockLogger = loggerFactory.build();
const mockCache = cacheFactory.build();

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../../src/config.js', () => ({
  config: {
    serverUrl: 'http://localhost:8000',
    discordToken: 'test-token',
    clientId: 'test-client-id',
  },
}));

jest.unstable_mockModule('../../src/utils/gcp-auth.js', () => ({
  isRunningOnGCP: async () => false,
  getIdentityToken: async () => null,
  clearTokenCache: () => {},
}));

const { ApiClient } = await import('../../src/lib/api-client.js');

const createJSONAPIResponse = <T>(type: string, id: string, attributes: T) => ({
  jsonapi: { version: '1.1' },
  data: {
    type,
    id,
    attributes,
  },
});

const createJSONAPIListResponse = <T>(type: string, items: Array<{id: string; attributes: T}>) => ({
  jsonapi: { version: '1.1' },
  data: items.map(item => ({
    type,
    id: item.id,
    attributes: item.attributes,
  })),
});

const createCommunityServerJSONAPIResponse = (id: string, platformId: string) => createJSONAPIResponse(
  'community-servers',
  id,
  {
    platform: 'discord',
    platform_community_server_id: platformId,
    name: 'Test Guild',
    is_active: true,
  }
);

const createNoteJSONAPIResponse = (id: string, attrs: {
  author_participant_id: string;
  summary: string;
  classification?: string;
  status?: string;
  community_server_id?: string;
  created_at?: string;
  updated_at?: string | null;
  helpfulness_score?: number;
  ratings_count?: number;
  force_published?: boolean;
}) => createJSONAPIResponse(
  'notes',
  id,
  {
    author_participant_id: attrs.author_participant_id,
    summary: attrs.summary,
    classification: attrs.classification || 'NOT_MISLEADING',
    status: attrs.status || 'NEEDS_MORE_RATINGS',
    helpfulness_score: attrs.helpfulness_score ?? 0,
    ratings_count: attrs.ratings_count ?? 0,
    force_published: attrs.force_published ?? false,
    force_published_at: null,
    community_server_id: attrs.community_server_id || '550e8400-e29b-41d4-a716-446655440001',
    channel_id: null,
    content: null,
    request_id: null,
    created_at: attrs.created_at || new Date().toISOString(),
    updated_at: attrs.updated_at ?? null,
  }
);

const createRatingJSONAPIResponse = (id: string, attrs: {
  note_id: string;
  rater_participant_id: string;
  helpfulness_level: string;
  created_at?: string;
}) => createJSONAPIResponse(
  'ratings',
  id,
  {
    note_id: attrs.note_id,
    rater_participant_id: attrs.rater_participant_id,
    helpfulness_level: attrs.helpfulness_level,
    created_at: attrs.created_at || new Date().toISOString(),
    updated_at: null,
  }
);

const createRequestJSONAPIResponse = (id: string, attrs: {
  request_id: string;
  requested_by: string;
  status?: string;
}) => createJSONAPIResponse(
  'requests',
  id,
  {
    request_id: attrs.request_id,
    requested_by: attrs.requested_by,
    status: attrs.status || 'pending',
    note_id: null,
    community_server_id: null,
    requested_at: new Date().toISOString(),
    created_at: new Date().toISOString(),
    updated_at: null,
  }
);

describe('API Persistence Integration Tests', () => {
  let client1: InstanceType<typeof ApiClient>;
  let client2: InstanceType<typeof ApiClient>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockCache.get.mockResolvedValue(null);

    client1 = new ApiClient({ serverUrl: 'http://localhost:8000' });
    client2 = new ApiClient({ serverUrl: 'http://localhost:8000' });
  });

  describe('Note Persistence', () => {
    it('should persist note via HTTP POST and retrieve via HTTP GET', async () => {
      const createRequest = {
        messageId: '123456789012345001',
        authorId: 'user-456',
        content: 'This note should persist to the database',
      };

      const now = new Date().toISOString();

      mockFetch.mockResolvedValueOnce(
        createMockResponse({
          ok: true,
          json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440001', 'guild-123'),
        })
      );

      mockFetch.mockResolvedValueOnce(
        createMockResponse({
          json: async () => createNoteJSONAPIResponse('note-789', {
            author_participant_id: createRequest.authorId,
            summary: createRequest.content,
            created_at: now,
          }),
        })
      );

      const result = await client1.createNote(createRequest, { userId: 'user-456', guildId: 'guild-123' });

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/notes',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );

      const fetchCalls = mockFetch.mock.calls as unknown as [string, RequestInit][];
      expect(fetchCalls[1]).toBeDefined();
      const [_, fetchInit] = fetchCalls[1];
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);
      expect(sentBody.data.attributes).toHaveProperty('author_participant_id', createRequest.authorId);
      expect(sentBody.data.attributes).toHaveProperty('summary', createRequest.content);
      expect(sentBody.data.attributes).toHaveProperty('classification', 'NOT_MISLEADING');

      expect(result.data.id).toBe('note-789');
      expect(result.data.type).toBe('notes');
      expect(result.data.attributes.author_participant_id).toBe(createRequest.authorId);
      expect(result.data.attributes.summary).toBe(createRequest.content);
      expect(new Date(result.data.attributes.created_at).getTime()).toBeGreaterThan(0);

      mockFetch.mockClear();

      mockFetch.mockResolvedValueOnce(
        createMockResponse({
          json: async () => createJSONAPIListResponse('notes', [{
            id: 'note-789',
            attributes: {
              author_participant_id: createRequest.authorId,
              summary: createRequest.content,
              classification: 'NOT_MISLEADING',
              status: 'NEEDS_MORE_RATINGS',
              helpfulness_score: 0,
              ratings_count: 0,
              created_at: new Date().toISOString(),
              community_server_id: '550e8400-e29b-41d4-a716-446655440001',
            },
          }]),
        })
      );

      const retrievedNotes = await client2.getNotes(createRequest.messageId);

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v2/notes'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );

      expect(retrievedNotes.data).toHaveLength(1);
      expect(retrievedNotes.data[0].id).toBe('note-789');
      expect(retrievedNotes.data[0].attributes.author_participant_id).toBe(createRequest.authorId);
      expect(retrievedNotes.data[0].attributes.summary).toBe(createRequest.content);
    });

    it('should persist note and retrieve it across different client instances', async () => {
      const createRequest = {
        messageId: '123456789012345002',
        authorId: 'author-001',
        content: 'Cross-client persistence test',
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440002', 'guild-123'),
      }));

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createNoteJSONAPIResponse('note-cross-client-001', {
          author_participant_id: createRequest.authorId,
          summary: createRequest.content,
        }),
      }));

      const created = await client1.createNote(createRequest, { userId: 'author-001', guildId: 'guild-123' });
      expect(created.data.id).toBe('note-cross-client-001');
      expect(created.data.attributes.author_participant_id).toBe(createRequest.authorId);
      expect(created.data.attributes.summary).toBe(createRequest.content);

      mockFetch.mockClear();

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createJSONAPIListResponse('notes', [{
          id: 'note-cross-client-001',
          attributes: {
            author_participant_id: createRequest.authorId,
            summary: createRequest.content,
            classification: 'NOT_MISLEADING',
            status: 'NEEDS_MORE_RATINGS',
            helpfulness_score: 0,
            ratings_count: 0,
            created_at: new Date().toISOString(),
            community_server_id: '550e8400-e29b-41d4-a716-446655440002',
          },
        }]),
      }));

      const retrieved = await client2.getNotes(createRequest.messageId);

      expect(retrieved.data).toHaveLength(1);
      expect(retrieved.data[0].id).toBe('note-cross-client-001');
      expect(retrieved.data[0].attributes.author_participant_id).toBe(createRequest.authorId);
      expect(retrieved.data[0].attributes.summary).toBe(createRequest.content);
    });

    it('should verify HTTP call structure for note creation', async () => {
      const request = {
        messageId: '123456789012345003',
        authorId: 'user-structure',
        content: 'Verify HTTP structure',
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440003', 'guild-123'),
      }));

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createNoteJSONAPIResponse('note-999', {
          author_participant_id: request.authorId,
          summary: request.content,
        }),
      }));

      await client1.createNote(request, { userId: 'user-structure', guildId: 'guild-123' });

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/notes',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );

      const fetchCalls = mockFetch.mock.calls as unknown as [string, RequestInit][];
      expect(fetchCalls[1]).toBeDefined();
      const [_, fetchInit] = fetchCalls[1];
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);
      expect(sentBody.data.attributes).toHaveProperty('author_participant_id', request.authorId);
      expect(sentBody.data.attributes).toHaveProperty('summary', request.content);
      expect(sentBody.data.attributes).toHaveProperty('classification', 'NOT_MISLEADING');
    });
  });

  describe('Rating Persistence', () => {
    it('should persist rating via HTTP POST', async () => {
      const ratingRequest = {
        noteId: '550e8400-e29b-41d4-a716-446655440021',
        userId: 'rater-456',
        helpful: true,
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createRatingJSONAPIResponse('rating-001', {
          note_id: ratingRequest.noteId,
          rater_participant_id: ratingRequest.userId,
          helpfulness_level: 'HELPFUL',
        }),
      }));

      const result = await client1.rateNote(ratingRequest);

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/ratings',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          body: expect.stringContaining('note_id'),
        })
      );

      expect(result.data.attributes.note_id).toBe(ratingRequest.noteId);
      expect(result.data.attributes.rater_participant_id).toBe(ratingRequest.userId);
      expect(result.data.attributes.helpfulness_level).toBe('HELPFUL');
      expect(result.data.attributes.created_at).toBeDefined();
    });

    it('should persist negative ratings correctly', async () => {
      const ratingRequest = {
        noteId: '550e8400-e29b-41d4-a716-446655440022',
        userId: 'rater-789',
        helpful: false,
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createRatingJSONAPIResponse('rating-002', {
          note_id: ratingRequest.noteId,
          rater_participant_id: ratingRequest.userId,
          helpfulness_level: 'NOT_HELPFUL',
        }),
      }));

      const result = await client1.rateNote(ratingRequest);

      expect(result.data.attributes.helpfulness_level).toBe('NOT_HELPFUL');
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/ratings',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('helpfulness_level'),
        })
      );
    });

    it('should verify rating data is sent with correct structure', async () => {
      const request = {
        noteId: '550e8400-e29b-41d4-a716-446655440023',
        userId: 'user-structure-789',
        helpful: true,
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createRatingJSONAPIResponse('rating-003', {
          note_id: request.noteId,
          rater_participant_id: request.userId,
          helpfulness_level: 'HELPFUL',
        }),
      }));

      await client1.rateNote(request);

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/ratings',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('note_id'),
        })
      );

      const fetchCalls = mockFetch.mock.calls as unknown as [string, RequestInit][];
      expect(fetchCalls[0]).toBeDefined();
      const [_, fetchInit] = fetchCalls[0];
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);
      expect(sentBody.data.attributes).toHaveProperty('note_id');
      expect(sentBody.data.attributes).toHaveProperty('rater_participant_id', request.userId);
      expect(sentBody.data.attributes).toHaveProperty('helpfulness_level', 'HELPFUL');
    });
  });

  describe('Note Request Persistence', () => {
    it('should persist note request via HTTP POST', async () => {
      const noteRequest = {
        messageId: '100000000000',
        userId: 'requester-456',
        community_server_id: 'guild-123',
        reason: 'This message needs context',
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createRequestJSONAPIResponse('request-001', {
          request_id: `discord-${noteRequest.messageId}-12345`,
          requested_by: noteRequest.userId,
        }),
      }));

      await client1.requestNote(noteRequest);

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/requests',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          body: expect.stringContaining('request_id'),
        })
      );

      const fetchCalls = mockFetch.mock.calls as unknown as [string, RequestInit][];
      expect(fetchCalls[0]).toBeDefined();
      const [_, fetchInit] = fetchCalls[0];
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);
      expect(sentBody.data.attributes).toHaveProperty('request_id');
      expect(sentBody.data.attributes.request_id).toContain(`discord-${noteRequest.messageId}`);
      expect(sentBody.data.attributes).toHaveProperty('platform_message_id', noteRequest.messageId);
      expect(sentBody.data.attributes).toHaveProperty('requested_by', noteRequest.userId);
    });

    it('should persist note request without optional reason', async () => {
      const noteRequest = {
        messageId: '200000000000',
        userId: 'requester-789',
        community_server_id: 'guild-123',
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createRequestJSONAPIResponse('request-002', {
          request_id: `discord-${noteRequest.messageId}-12345`,
          requested_by: noteRequest.userId,
        }),
      }));

      await client1.requestNote(noteRequest);

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/requests',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('request_id'),
        })
      );

      const fetchCalls = mockFetch.mock.calls as unknown as [string, RequestInit][];
      expect(fetchCalls[0]).toBeDefined();
      const [_, fetchInit] = fetchCalls[0];
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);
      expect(sentBody.data.attributes).toHaveProperty('request_id');
      expect(sentBody.data.attributes.request_id).toContain(`discord-${noteRequest.messageId}`);
      expect(sentBody.data.attributes).toHaveProperty('platform_message_id', noteRequest.messageId);
      expect(sentBody.data.attributes).toHaveProperty('requested_by', noteRequest.userId);
    });

    it('should verify request is recorded in backend', async () => {
      const request = {
        messageId: '123456789012345006',
        userId: 'user-verify-456',
        community_server_id: 'guild-123',
        reason: 'Verification test',
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createRequestJSONAPIResponse('request-003', {
          request_id: `discord-${request.messageId}-12345`,
          requested_by: request.userId,
        }),
      }));

      await expect(client1.requestNote(request)).resolves.not.toThrow();

      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/requests',
        expect.any(Object)
      );
    });

    it('should include platform_message_id and platform metadata in request', async () => {
      const noteRequest = {
        messageId: '987654321098765432',
        userId: 'system-factcheck',
        community_server_id: 'guild-123',
        originalMessageContent: 'Fact-check context',
        discord_channel_id: 'channel-123',
        discord_author_id: 'author-456',
        discord_timestamp: new Date('2024-01-15T10:30:00Z'),
        fact_check_metadata: {
          dataset_item_id: 'fc-item-789',
          similarity_score: 0.92,
          dataset_name: 'snopes',
          rating: 'FALSE',
        },
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createRequestJSONAPIResponse('request-004', {
          request_id: `discord-${noteRequest.messageId}-12345`,
          requested_by: noteRequest.userId,
        }),
      }));

      await client1.requestNote(noteRequest);

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/requests',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          body: expect.stringContaining('platform_message_id'),
        })
      );

      const fetchCalls = mockFetch.mock.calls as unknown as [string, RequestInit][];
      expect(fetchCalls[0]).toBeDefined();
      const [_, fetchInit] = fetchCalls[0];
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);

      expect(sentBody.data.attributes).toHaveProperty('platform_message_id', noteRequest.messageId);
      expect(sentBody.data.attributes).toHaveProperty('platform_channel_id', noteRequest.discord_channel_id);
      expect(sentBody.data.attributes).toHaveProperty('platform_author_id', noteRequest.discord_author_id);
      expect(sentBody.data.attributes).toHaveProperty('platform_timestamp', '2024-01-15T10:30:00.000Z');
      expect(sentBody.data.attributes).toHaveProperty('requested_by', noteRequest.userId);
      expect(sentBody.data.attributes).toHaveProperty('original_message_content', noteRequest.originalMessageContent);
    });

    it('should handle optional platform metadata fields being null', async () => {
      const noteRequest = {
        messageId: '111222333444555666',
        userId: 'user-optional-test',
        community_server_id: 'guild-456',
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createRequestJSONAPIResponse('request-005', {
          request_id: `discord-${noteRequest.messageId}-12345`,
          requested_by: noteRequest.userId,
        }),
      }));

      await client1.requestNote(noteRequest);

      const fetchCalls = mockFetch.mock.calls as unknown as [string, RequestInit][];
      expect(fetchCalls[0]).toBeDefined();
      const [_, fetchInit] = fetchCalls[0];
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);

      expect(sentBody.data.attributes).toHaveProperty('platform_message_id', noteRequest.messageId);
      expect(sentBody.data.attributes).toHaveProperty('platform_channel_id', null);
      expect(sentBody.data.attributes).toHaveProperty('platform_author_id', null);
      expect(sentBody.data.attributes).toHaveProperty('platform_timestamp', null);
    });
  });

  describe('Error Scenarios', () => {
    it('should handle server down scenario for note creation', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        retryAttempts: 1,
        retryDelayMs: 10,
      });

      const request = {
        messageId: '123456789012345007',
        authorId: 'user-error-001',
        content: 'This will fail',
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440007', 'guild-123'),
      }));

      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      await expect(client.createNote(request, { userId: 'user-error-001', guildId: 'guild-123' })).rejects.toThrow(
        'Network error'
      );

      expect(mockFetch).toHaveBeenCalled();
    });

    it('should handle 500 Internal Server Error', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        retryAttempts: 1,
        retryDelayMs: 10,
      });

      const request = {
        messageId: '123456789012345008',
        authorId: 'user-500',
        content: 'Server error test',
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440008', 'guild-123'),
      }));

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        text: async () => 'Internal Server Error',
      }));

      await expect(client.createNote(request, { userId: 'user-500', guildId: 'guild-123' })).rejects.toThrow(
        'API request failed: 500 Internal Server Error'
      );
    });

    it('should handle 400 Bad Request for invalid data', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        retryAttempts: 1,
        retryDelayMs: 10,
      });

      const request = {
        messageId: '',
        authorId: 'user-400',
        content: 'Invalid request',
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440009', 'guild-123'),
      }));

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        text: async () => 'Bad Request: messageId is required',
      }));

      await expect(client.createNote(request, { userId: 'user-400', guildId: 'guild-123' })).rejects.toThrow(
        'API request failed: 400 Bad Request'
      );
    });

    it('should handle 404 Not Found for getNotes', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        retryAttempts: 1,
        retryDelayMs: 10,
      });

      mockFetch.mockResolvedValue(createMockResponse({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        text: async () => 'Not Found',
      }));

      await expect(client.getNotes('non-existent-msg')).rejects.toThrow(
        'API request failed: 404 Not Found'
      );
    });

    it('should retry on transient failures', async () => {
      const request = {
        messageId: '123456789012345009',
        authorId: 'user-retry',
        content: 'Retry test',
      };

      mockFetch
        .mockResolvedValueOnce(createMockResponse({
          ok: true,
          json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440010', 'guild-123'),
        }))
        .mockRejectedValueOnce(new Error('Temporary network error'))
        .mockResolvedValueOnce(
          createMockResponse({
            json: async () => createNoteJSONAPIResponse('note-retry-success', {
              author_participant_id: request.authorId,
              summary: request.content,
            }),
          })
        );

      const result = await client1.createNote(request, { userId: 'user-retry', guildId: 'guild-123' });

      expect(result.data.id).toBe('note-retry-success');
      expect(result.data.type).toBe('notes');
      expect(result.data.attributes.author_participant_id).toBe(request.authorId);
      expect(result.data.attributes.summary).toBe(request.content);
      expect(new Date(result.data.attributes.created_at).getTime()).toBeGreaterThan(0);
      expect(mockFetch).toHaveBeenCalledTimes(3);
    });

    it('should fail after max retries exceeded', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        retryAttempts: 2,
        retryDelayMs: 10,
      });

      const request = {
        messageId: '123456789012345010',
        authorId: 'user-max-retry',
        content: 'Max retry test',
      };

      mockFetch
        .mockResolvedValueOnce(createMockResponse({
          ok: true,
          json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440011', 'guild-123'),
        }))
        .mockRejectedValueOnce(new Error('Error 1'))
        .mockRejectedValueOnce(new Error('Error 2'))
        .mockRejectedValueOnce(new Error('Error 3'));

      await expect(client.createNote(request, { userId: 'user-max-retry', guildId: 'guild-123' })).rejects.toThrow();

      expect(mockFetch).toHaveBeenCalledTimes(3);
    });

    it('should handle malformed JSON response', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        retryAttempts: 1,
        retryDelayMs: 10,
      });

      const request = {
        messageId: '123456789012345011',
        authorId: 'user-malformed',
        content: 'Malformed test',
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440012', 'guild-123'),
      }));

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => {
          throw new Error('Invalid JSON');
        },
      }));

      await expect(client.createNote(request, { userId: 'user-malformed', guildId: 'guild-123' })).rejects.toThrow(
        'Invalid JSON'
      );
    });

    it('should handle timeout errors', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        retryAttempts: 1,
        retryDelayMs: 10,
      });

      const request = {
        messageId: '123456789012345012',
        authorId: 'user-timeout',
        content: 'Timeout test',
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440013', 'guild-123'),
      }));

      mockFetch.mockImplementation(
        () =>
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Request timeout')), 50)
          )
      );

      await expect(client.createNote(request, { userId: 'user-timeout', guildId: 'guild-123' })).rejects.toThrow(
        'Request timeout'
      );
    });
  });

  describe('Cross-Client Data Consistency', () => {
    it('should maintain data consistency across multiple clients', async () => {
      const noteRequest = {
        messageId: '123456789012345013',
        authorId: 'author-consistency',
        content: 'Consistency test note',
      };

      const persistedNote = {
        id: 'note-consistency-001',
        ...noteRequest,
        createdAt: 1234567890,
        helpfulCount: 0,
        notHelpfulCount: 0,
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440014', 'guild-123'),
      }));

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createNoteJSONAPIResponse('note-consistency-001', {
          author_participant_id: noteRequest.authorId,
          summary: noteRequest.content,
        }),
      }));

      await client1.createNote(noteRequest, { userId: 'author-consistency', guildId: 'guild-123' });

      mockFetch.mockClear();
      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createJSONAPIListResponse('notes', [{
          id: 'note-consistency-001',
          attributes: {
            author_participant_id: noteRequest.authorId,
            summary: noteRequest.content,
            classification: 'NOT_MISLEADING',
            status: 'NEEDS_MORE_RATINGS',
            helpfulness_score: 0,
            ratings_count: 0,
            created_at: new Date().toISOString(),
            community_server_id: '550e8400-e29b-41d4-a716-446655440014',
          },
        }]),
      }));

      const notesFromClient2 = await client2.getNotes(noteRequest.messageId);

      expect(notesFromClient2.data).toHaveLength(1);
      expect(notesFromClient2.data[0].id).toBe('note-consistency-001');
      expect(notesFromClient2.data[0].attributes.author_participant_id).toBe(noteRequest.authorId);
      expect(notesFromClient2.data[0].attributes.summary).toBe(noteRequest.content);

      mockFetch.mockClear();
      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createJSONAPIListResponse('notes', [{
          id: 'note-consistency-001',
          attributes: {
            author_participant_id: noteRequest.authorId,
            summary: noteRequest.content,
            classification: 'NOT_MISLEADING',
            status: 'NEEDS_MORE_RATINGS',
            helpfulness_score: 0,
            ratings_count: 0,
            created_at: new Date().toISOString(),
            community_server_id: '550e8400-e29b-41d4-a716-446655440014',
          },
        }]),
      }));

      const notesFromClient1Again = await client1.getNotes(
        noteRequest.messageId
      );

      expect(notesFromClient1Again.data[0].id).toBe(notesFromClient2.data[0].id);
      expect(notesFromClient1Again.data[0].attributes.author_participant_id).toBe(notesFromClient2.data[0].attributes.author_participant_id);
      expect(notesFromClient1Again.data[0].attributes.summary).toBe(notesFromClient2.data[0].attributes.summary);
    });

    it('should handle concurrent note creations from different clients', async () => {
      const note1Request = {
        messageId: '123456789012345014',
        authorId: 'author-1',
        content: 'First note',
      };

      const note2Request = {
        messageId: '123456789012345014',
        authorId: 'author-2',
        content: 'Second note',
      };

      mockFetch
        .mockResolvedValueOnce(createMockResponse({
          ok: true,
          json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440015', 'guild-123'),
        }))
        .mockResolvedValueOnce(
          createMockResponse({
            json: async () => createNoteJSONAPIResponse('note-concurrent-001', {
              author_participant_id: note1Request.authorId,
              summary: note1Request.content,
            }),
          })
        )
        .mockResolvedValueOnce(createMockResponse({
          ok: true,
          json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440015', 'guild-123'),
        }))
        .mockResolvedValueOnce(
          createMockResponse({
            json: async () => createNoteJSONAPIResponse('note-concurrent-002', {
              author_participant_id: note2Request.authorId,
              summary: note2Request.content,
            }),
          })
        );

      const result1 = await client1.createNote(note1Request, { userId: 'author-1', guildId: 'guild-123' });
      const result2 = await client2.createNote(note2Request, { userId: 'author-2', guildId: 'guild-123' });

      expect(result1.data.id).toBe('note-concurrent-001');
      expect(result2.data.id).toBe('note-concurrent-002');
      expect(mockFetch).toHaveBeenCalledTimes(4);
    });

    it('should verify notes created by one client are retrievable by another', async () => {
      const notes = [
        {
          messageId: '123456789012345015',
          authorId: 'author-1',
          content: 'First note',
        },
        {
          messageId: '123456789012345015',
          authorId: 'author-2',
          content: 'Second note',
        },
        {
          messageId: '123456789012345015',
          authorId: 'author-3',
          content: 'Third note',
        },
      ];

      const communityServerUUIDs = [
        '550e8400-e29b-41d4-a716-446655440017',
        '550e8400-e29b-41d4-a716-446655440018',
        '550e8400-e29b-41d4-a716-446655440019'
      ];

      for (let i = 0; i < notes.length; i++) {
        mockFetch.mockResolvedValueOnce(createMockResponse({
          ok: true,
          json: async () => createCommunityServerJSONAPIResponse(communityServerUUIDs[i], 'guild-123'),
        }));
        mockFetch.mockResolvedValueOnce(createMockResponse({
          ok: true,
          json: async () => createNoteJSONAPIResponse(`note-multi-${i}`, {
            author_participant_id: notes[i].authorId,
            summary: notes[i].content,
          }),
        }));
      }

      for (const note of notes) {
        await client1.createNote(note, { userId: note.authorId, guildId: 'guild-123' });
      }

      mockFetch.mockClear();

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createJSONAPIListResponse('notes', notes.map((note, i) => ({
          id: `note-multi-${i}`,
          attributes: {
            author_participant_id: note.authorId,
            summary: note.content,
            classification: 'NOT_MISLEADING',
            status: 'NEEDS_MORE_RATINGS',
            helpfulness_score: 0,
            ratings_count: 0,
            created_at: new Date().toISOString(),
            community_server_id: communityServerUUIDs[i],
          },
        }))),
      }));

      const retrievedNotes = await client2.getNotes('msg-multi-note-001');

      expect(retrievedNotes.data).toHaveLength(3);
      retrievedNotes.data.forEach((note: { id: string; attributes: { author_participant_id: string; summary: string; created_at: string } }, i: number) => {
        expect(note.id).toBe(`note-multi-${i}`);
        expect(note.attributes.author_participant_id).toBe(notes[i].authorId);
        expect(note.attributes.summary).toBe(notes[i].content);
        expect(new Date(note.attributes.created_at).getTime()).toBeGreaterThan(0);
      });
    });
  });

  describe('Data Validation', () => {
    it('should verify created note data matches request data', async () => {
      const request = {
        messageId: 'validation-001',
        authorId: 'author-validation',
        content: 'Validate this content persists correctly',
      };


      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440020', 'guild-123'),
      }));

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createNoteJSONAPIResponse('note-validation-001', {
          author_participant_id: request.authorId,
          summary: request.content,
        }),
      }));

      const result = await client1.createNote(request, { userId: 'author-validation', guildId: 'guild-123' });

      expect(result.data.attributes.author_participant_id).toBe(request.authorId);
      expect(result.data.attributes.summary).toBe(request.content);
      expect(result.data.id).toBeTruthy();
      expect(new Date(result.data.attributes.created_at).getTime()).toBeGreaterThan(0);
    });

    it('should verify rating data integrity', async () => {
      const request = {
        noteId: '550e8400-e29b-41d4-a716-446655440024',
        userId: 'user-rating-validation',
        helpful: true,
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createRatingJSONAPIResponse('rating-validation-001', {
          note_id: request.noteId,
          rater_participant_id: request.userId,
          helpfulness_level: 'HELPFUL',
        }),
      }));

      const result = await client1.rateNote(request);

      expect(result.data.attributes.note_id).toBe(request.noteId);
      expect(result.data.attributes.rater_participant_id).toBe(request.userId);
      expect(result.data.attributes.helpfulness_level).toBe('HELPFUL');
      expect(result.data.attributes.created_at).toBeDefined();
    });

    it('should ensure request data is not corrupted during transmission', async () => {
      const request = {
        messageId: 'special-chars-™-©-®',
        authorId: 'user-emoji-test',
        content: 'Content with special chars: hello world',
      };

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createCommunityServerJSONAPIResponse('550e8400-e29b-41d4-a716-446655440021', 'guild-123'),
      }));

      mockFetch.mockResolvedValueOnce(createMockResponse({
        ok: true,
        json: async () => createNoteJSONAPIResponse('note-special-chars', {
          author_participant_id: request.authorId,
          summary: request.content,
        }),
      }));

      await client1.createNote(request, { userId: 'user-emoji-test', guildId: 'guild-123' });

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/notes',
        expect.objectContaining({
          method: 'POST',
        })
      );

      const fetchCalls = mockFetch.mock.calls as unknown as [string, RequestInit][];
      expect(fetchCalls[1]).toBeDefined();
      const [_, fetchInit] = fetchCalls[1];
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);
      expect(sentBody.data.attributes).toHaveProperty('author_participant_id', request.authorId);
      expect(sentBody.data.attributes).toHaveProperty('summary', request.content);
      expect(sentBody.data.attributes).toHaveProperty('classification', 'NOT_MISLEADING');
    });
  });
});
