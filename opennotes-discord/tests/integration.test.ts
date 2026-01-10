import { jest } from '@jest/globals';

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

const mockLogger = {
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  info: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

const mockCache = {
  get: jest.fn<(key: string) => unknown>(),
  set: jest.fn<(key: string, value: unknown, ttl?: number) => void>(),
  delete: jest.fn<(key: string) => void>(),
  start: jest.fn<() => void>(),
  stop: jest.fn<() => void>(),
};

jest.unstable_mockModule('../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../src/config.js', () => ({
  config: {
    serverUrl: 'http://localhost:8000',
    discordToken: 'test-token',
    clientId: 'test-client-id',
  },
}));

const { apiClient } = await import('../src/api-client.js');

const createJSONAPIResponse = <T>(type: string, id: string, attributes: T) => ({
  jsonapi: { version: '1.1' },
  data: {
    type,
    id,
    attributes,
  },
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
}) => createJSONAPIResponse(
  'notes',
  id,
  {
    author_participant_id: attrs.author_participant_id,
    summary: attrs.summary,
    classification: attrs.classification || 'NOT_MISLEADING',
    status: attrs.status || 'NEEDS_MORE_RATINGS',
    helpfulness_score: 0,
    ratings_count: 0,
    force_published: false,
    force_published_at: null,
    community_server_id: attrs.community_server_id || '550e8400-e29b-41d4-a716-446655440000',
    channel_id: null,
    original_message_content: null,
    request_id: null,
    created_at: attrs.created_at || new Date().toISOString(),
    updated_at: null,
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

describe('End-to-End Integration Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCache.get.mockReturnValue(null);
  });

  describe('Complete workflow', () => {
    it('should complete full note creation and rating workflow', async () => {
      const messageId = '234567890123';
      const communityServerId = '550e8400-e29b-41d4-a716-446655440000';

      mockFetch
        .mockResolvedValueOnce(
          createMockResponse({
            json: async () => ({ status: 'healthy', version: '1.0.0' }),
          })
        )
        .mockResolvedValueOnce(
          createMockResponse({
            status: 200,
            json: async () => createCommunityServerJSONAPIResponse(communityServerId, '550e8400e29b41d4a716446655440000'),
          })
        )
        .mockResolvedValueOnce(
          createMockResponse({
            status: 201,
            json: async () => createNoteJSONAPIResponse('550e8400-e29b-41d4-a716-446655440001', {
              author_participant_id: 'user456',
              summary: 'This is a test community note',
              community_server_id: communityServerId,
            }),
          })
        )
        .mockResolvedValueOnce(
          createMockResponse({
            status: 201,
            json: async () => createRatingJSONAPIResponse('550e8400-e29b-41d4-a716-446655440002', {
              note_id: '550e8400-e29b-41d4-a716-446655440001',
              rater_participant_id: 'rater789',
              helpfulness_level: 'HELPFUL',
            }),
          })
        );

      const healthResult = await apiClient.healthCheck();
      expect(healthResult.status).toBe('healthy');

      const note = await apiClient.createNote({
        messageId,
        authorId: 'user456',
        content: 'This is a test community note',
      }, {
        guildId: '550e8400e29b41d4a716446655440000',
        userId: 'user456',
        channelId: 'channel123',
      });

      expect(note.data.id).toBe('550e8400-e29b-41d4-a716-446655440001');
      expect(note.data.type).toBe('notes');
      expect(note.data.attributes.summary).toBe('This is a test community note');
      expect(note.data.attributes.author_participant_id).toBe('user456');
      expect(note.data.attributes.created_at).toBeDefined();

      const rating = await apiClient.rateNote({
        noteId: note.data.id,
        userId: 'rater789',
        helpful: true,
      });

      // Rating now returns JSONAPI format
      expect(rating).toHaveProperty('data');
      expect(rating).toHaveProperty('jsonapi');
      expect(rating.data.type).toBe('ratings');
      expect(rating.data.id).toBeDefined();
      expect(rating.data.attributes.note_id).toBe('550e8400-e29b-41d4-a716-446655440001');
      expect(rating.data.attributes.rater_participant_id).toBe('rater789');
      expect(rating.data.attributes.helpfulness_level).toBe('HELPFUL');
      expect(rating.data.attributes.created_at).toBeDefined();

      mockFetch.mockClear();
      const jsonApiNotesResponse = {
        data: [
          {
            type: 'notes',
            id: 'note-123',
            attributes: {
              summary: 'This is a test community note',
              classification: 'NOT_MISLEADING',
              status: 'published',
              helpfulness_score: 0.5,
              author_participant_id: 'user456',
              community_server_id: 'community-uuid',
              channel_id: null,
              request_id: 'request-1',
              ratings_count: 0,
              force_published: false,
              force_published_at: null,
              created_at: new Date().toISOString(),
              updated_at: null,
            },
          },
        ],
        jsonapi: { version: '1.1' },
        links: {},
        meta: { count: 1 },
      };

      mockFetch.mockResolvedValueOnce(
        createMockResponse({
          json: async () => jsonApiNotesResponse,
        })
      );

      const notes = await apiClient.getNotes(messageId);
      expect(notes.data).toContainEqual(expect.objectContaining({
        type: 'notes',
        attributes: expect.objectContaining({
          author_participant_id: 'user456',
          summary: 'This is a test community note',
        }),
      }));
    });

    it('should handle scoring workflow with real data structure', async () => {
      const communityServerId = '550e8400-e29b-41d4-a716-446655440000';

      const mockScoringResponse = {
        data: {
          type: 'scoring-results',
          id: 'result-1',
          attributes: {
            scored_notes: [],
            helpful_scores: [],
            auxiliary_info: [],
          }
        }
      };

      mockFetch
        .mockResolvedValueOnce(
          createMockResponse({
            status: 200,
            json: async () => createCommunityServerJSONAPIResponse(communityServerId, 'guild123'),
          })
        )
        .mockResolvedValueOnce(
          createMockResponse({
            status: 201,
            json: async () => createNoteJSONAPIResponse('550e8400-e29b-41d4-a716-446655440003', {
              author_participant_id: 'author-001',
              summary: 'Test note for scoring',
              community_server_id: communityServerId,
            }),
          })
        )
        .mockResolvedValueOnce(
          createMockResponse({
            status: 201,
            json: async () => createRatingJSONAPIResponse('550e8400-e29b-41d4-a716-446655440004', {
              note_id: '550e8400-e29b-41d4-a716-446655440003',
              rater_participant_id: 'rater-001',
              helpfulness_level: 'HELPFUL',
            }),
          })
        )
        .mockResolvedValueOnce(
          createMockResponse({
            json: async () => mockScoringResponse,
          })
        );

      const note = await apiClient.createNote({
        messageId: '234567890123456790',
        authorId: 'author-001',
        content: 'Test note for scoring',
      }, {
        guildId: 'guild123',
        userId: 'author-001',
        channelId: 'channel456',
      });

      const rating = await apiClient.rateNote({
        noteId: note.data.id,
        userId: 'rater-001',
        helpful: true,
      });

      const noteCreatedAtMillis = new Date(note.data.attributes.created_at!).getTime();
      const ratingCreatedAtMillis = new Date(rating.data.attributes.created_at!).getTime();
      const scoringRequest = {
        notes: [
          {
            noteId: parseInt(note.data.id.split('-')[1]) || 456,
            noteAuthorParticipantId: note.data.attributes.author_participant_id,
            createdAtMillis: noteCreatedAtMillis,
            tweetId: 234567890123456790,
            summary: note.data.attributes.summary,
            classification: 'NOT_MISLEADING',
          },
        ],
        ratings: [
          {
            raterParticipantId: rating.data.attributes.rater_participant_id,
            noteId: parseInt(note.data.id.split('-')[1]) || 456,
            createdAtMillis: ratingCreatedAtMillis,
            helpfulnessLevel: rating.data.attributes.helpfulness_level,
          },
        ],
        enrollment: [
          {
            participantId: note.data.attributes.author_participant_id,
            enrollmentState: 'EARNED_IN',
            successfulRatingNeededToEarnIn: 0,
            timestampOfLastStateChange: noteCreatedAtMillis,
          },
          {
            participantId: rating.data.attributes.rater_participant_id,
            enrollmentState: 'EARNED_IN',
            successfulRatingNeededToEarnIn: 0,
            timestampOfLastStateChange: ratingCreatedAtMillis,
          },
        ],
      };

      const scoringResult = await apiClient.scoreNotes(scoringRequest);

      expect(scoringResult.data.attributes).toHaveProperty('scored_notes');
      expect(scoringResult.data.attributes).toHaveProperty('helpful_scores');
      expect(scoringResult.data.attributes).toHaveProperty('auxiliary_info');
    });
  });

  describe('Error recovery', () => {
    it('should handle API failures gracefully', async () => {
      mockFetch.mockImplementation(async () =>
        createMockResponse({
          ok: false,
          status: 500,
          statusText: 'Internal Server Error',
          text: async () => 'Internal Server Error',
        })
      );

      await expect(apiClient.healthCheck()).rejects.toThrow();

      mockFetch.mockClear();
      mockFetch.mockResolvedValueOnce(
        createMockResponse({
          json: async () => ({ status: 'healthy', version: '1.0.0' }),
        })
      );

      const result = await apiClient.healthCheck();
      expect(result.status).toBe('healthy');
    });

    it('should handle network timeouts', async () => {
      mockFetch.mockImplementation(
        () =>
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Timeout')), 100)
          )
      );

      await expect(apiClient.healthCheck()).rejects.toThrow('Timeout');
    });
  });


  describe('Concurrent operations', () => {
    it('should handle multiple simultaneous note creations', async () => {
      const communityServerId = '550e8400-e29b-41d4-a716-446655440000';
      let noteIndex = 0;

      (mockFetch as jest.Mock).mockImplementation(async (url: unknown) => {
        const urlStr = String(url);
        if (urlStr.includes('/api/v2/community-servers')) {
          return createMockResponse({
            status: 200,
            json: async () => createCommunityServerJSONAPIResponse(communityServerId, 'guild-concurrent'),
          });
        }

        if (urlStr.includes('/api/v2/notes')) {
          const i = noteIndex++;
          const noteId = `550e8400-e29b-41d4-a716-446655440${String(i).padStart(3, '0')}`;
          const response = createNoteJSONAPIResponse(noteId, {
            author_participant_id: `user${i}`,
            summary: `Note ${i}`,
            community_server_id: communityServerId,
          });

          return createMockResponse({
            status: 201,
            json: async () => response,
          });
        }

        return createMockResponse({
          status: 404,
          ok: false,
          text: async () => 'Not Found',
        });
      });

      const promises = Array.from({ length: 5 }, (_, i) =>
        apiClient.createNote({
          messageId: `${345678901234567890 + i}`,
          authorId: `user${i}`,
          content: `Note ${i}`,
        }, {
          guildId: 'guild-concurrent',
          userId: `user${i}`,
          channelId: 'channel-concurrent',
        })
      );

      const notes = await Promise.all(promises);

      expect(notes).toHaveLength(5);
      notes.forEach((note) => {
        expect(note).toBeDefined();
        expect(note.data).toBeDefined();
        expect(note.data.id).toBeDefined();
        expect(typeof note.data.id).toBe('string');
      });
    });

    it('should handle concurrent health checks', async () => {
      mockFetch.mockImplementation(async () =>
        createMockResponse({
          json: async () => ({ status: 'healthy', version: '1.0.0' }),
        })
      );

      const promises = Array.from({ length: 10 }, () =>
        apiClient.healthCheck()
      );

      const results = await Promise.all(promises);

      expect(results).toHaveLength(10);
      results.forEach((result) => {
        expect(result.status).toBe('healthy');
      });
    });
  });
});
