import { jest } from '@jest/globals';

const mockFetch = jest.fn<typeof fetch>();
global.fetch = mockFetch;

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
    environment: 'development',
  },
}));

jest.unstable_mockModule('../src/utils/gcp-auth.js', () => ({
  getIdentityToken: jest.fn<() => Promise<string | null>>().mockResolvedValue(null),
  isRunningOnGCP: jest.fn<() => Promise<boolean>>().mockResolvedValue(false),
}));

const { ApiClient } = await import('../src/lib/api-client.js');

describe('JSON:API Response Parsing', () => {
  let client: InstanceType<typeof ApiClient>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockCache.get.mockReturnValue(null);
    client = new ApiClient({
      serverUrl: 'http://localhost:8000',
      environment: 'development',
    });
  });

  describe('Single Resource Responses', () => {
    describe('Notes', () => {
      it('extracts data from single note response', async () => {
        const jsonApiResponse = {
          data: {
            type: 'notes',
            id: '550e8400-e29b-41d4-a716-446655440000',
            attributes: {
              summary: 'This is a test note summary',
              classification: 'NOT_MISLEADING',
              status: 'NEEDS_MORE_RATINGS',
              helpfulness_score: 0.75,
              author_participant_id: 'participant-123',
              community_server_id: 'server-456',
              channel_id: 'channel-789',
              content: 'Original content here',
              request_id: 'req-001',
              ratings_count: 5,
              force_published: false,
              force_published_at: null,
              ai_generated: true,
              ai_provider: 'openai',
              created_at: '2025-01-15T10:30:00Z',
              updated_at: '2025-01-15T11:00:00Z',
            },
          },
          jsonapi: { version: '1.1' },
          links: {
            self: '/api/v2/notes/550e8400-e29b-41d4-a716-446655440000',
          },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getNote('550e8400-e29b-41d4-a716-446655440000');

        expect(result.data.id).toBe('550e8400-e29b-41d4-a716-446655440000');
        expect(result.data.attributes.summary).toBe('This is a test note summary');
        expect(result.data.attributes.classification).toBe('NOT_MISLEADING');
        expect(result.data.attributes.status).toBe('NEEDS_MORE_RATINGS');
        expect(result.data.attributes.helpfulness_score).toBe(0.75);
        expect(result.data.attributes.author_participant_id).toBe('participant-123');
        expect(result.data.attributes.community_server_id).toBe('server-456');
        expect(result.data.attributes.channel_id).toBe('channel-789');
        expect(result.data.attributes.request_id).toBe('req-001');
        expect(result.data.attributes.ratings_count).toBe(5);
        expect(result.data.attributes.force_published).toBe(false);
        expect(result.data.attributes.created_at).toBe('2025-01-15T10:30:00Z');
        expect(result.data.attributes.updated_at).toBe('2025-01-15T11:00:00Z');
      });

      it('handles note with null optional fields', async () => {
        const jsonApiResponse = {
          data: {
            type: 'notes',
            id: 'note-minimal',
            attributes: {
              summary: 'Minimal note',
              classification: 'NOT_MISLEADING',
              status: 'NEEDS_MORE_RATINGS',
              helpfulness_score: 0,
              author_participant_id: 'author-1',
              community_server_id: 'server-1',
              channel_id: null,
              content: null,
              request_id: null,
              ratings_count: 0,
              force_published: false,
              force_published_at: null,
              ai_generated: false,
              ai_provider: null,
              created_at: '2025-01-15T10:00:00Z',
              updated_at: null,
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getNote('note-minimal');

        expect(result.data.id).toBe('note-minimal');
        expect(result.data.attributes.channel_id).toBeNull();
        expect(result.data.attributes.request_id).toBeNull();
        expect(result.data.attributes.updated_at).toBeNull();
      });
    });

    describe('Ratings', () => {
      it('extracts data from single rating response', async () => {
        const noteId = '550e8400-e29b-41d4-a716-446655440000';
        const jsonApiResponse = {
          data: {
            type: 'ratings',
            id: 'rating-uuid-123',
            attributes: {
              note_id: noteId,
              rater_participant_id: 'user-789',
              helpfulness_level: 'HELPFUL',
              created_at: '2025-01-15T12:00:00Z',
              updated_at: '2025-01-15T12:30:00Z',
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 201,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.rateNote({
          noteId,
          userId: 'user-789',
          helpful: true,
        });

        expect(result.noteId).toBe(noteId);
        expect(result.userId).toBe('user-789');
        expect(result.helpful).toBe(true);
        expect(result.createdAt).toBe(new Date('2025-01-15T12:00:00Z').getTime());
      });

      it('handles rating without created_at (uses current time)', async () => {
        const noteId = '660e8400-e29b-41d4-a716-446655440001';
        const jsonApiResponse = {
          data: {
            type: 'ratings',
            id: 'rating-no-date',
            attributes: {
              note_id: noteId,
              rater_participant_id: 'user-1',
              helpfulness_level: 'NOT_HELPFUL',
              created_at: null,
              updated_at: null,
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 201,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const before = Date.now();
        const result = await client.rateNote({
          noteId,
          userId: 'user-1',
          helpful: false,
        });
        const after = Date.now();

        expect(result.data.attributes.helpfulness_level).toBe('NOT_HELPFUL');
        const createdAtMillis = new Date(result.data.attributes.created_at).getTime();
        expect(createdAtMillis).toBeGreaterThanOrEqual(before);
        expect(createdAtMillis).toBeLessThanOrEqual(after);
      });
    });

    describe('Requests', () => {
      it('extracts data from single request response', async () => {
        const jsonApiResponse = {
          data: {
            type: 'requests',
            id: 'request-uuid-123',
            attributes: {
              request_id: 'discord-123-456',
              requested_by: 'user-abc',
              status: 'PENDING',
              note_id: null,
              community_server_id: 'server-xyz',
              requested_at: '2025-01-15T09:00:00Z',
              created_at: '2025-01-15T09:00:00Z',
              updated_at: '2025-01-15T09:05:00Z',
              platform_message_id: 'discord-msg-789',
              content: 'Please add a note',
              metadata: { source: 'discord' },
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getRequest('discord-123-456');

        expect(result.id).toBe('request-uuid-123');
        expect(result.request_id).toBe('discord-123-456');
        expect(result.requested_by).toBe('user-abc');
        expect(result.status).toBe('PENDING');
        expect(result.note_id).toBeUndefined();
        expect(result.community_server_id).toBe('server-xyz');
        expect(result.platform_message_id).toBe('discord-msg-789');
        expect(result.metadata).toEqual({ source: 'discord' });
      });

      it('handles request with associated note_id', async () => {
        const jsonApiResponse = {
          data: {
            type: 'requests',
            id: 'request-with-note',
            attributes: {
              request_id: 'discord-fulfilled',
              requested_by: 'user-def',
              status: 'FULFILLED',
              note_id: 'associated-note-id',
              community_server_id: 'server-123',
              requested_at: '2025-01-14T08:00:00Z',
              created_at: '2025-01-14T08:00:00Z',
              updated_at: '2025-01-15T10:00:00Z',
              platform_message_id: null,
              content: null,
              metadata: null,
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getRequest('discord-fulfilled');

        expect(result.status).toBe('FULFILLED');
        expect(result.note_id).toBe('associated-note-id');
        expect(result.platform_message_id).toBeUndefined();
        expect(result.metadata).toBeUndefined();
      });
    });

    describe('Note Scores', () => {
      it('extracts data from single note score response', async () => {
        const jsonApiResponse = {
          data: {
            type: 'note-scores',
            id: 'note-score-123',
            attributes: {
              score: 0.85,
              confidence: 'standard',
              algorithm: 'bayesian-v2',
              rating_count: 25,
              tier: 3,
              tier_name: 'established',
              calculated_at: '2025-01-15T14:00:00Z',
              content: 'The original claim',
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getNoteScore('note-score-123');

        expect(result.note_id).toBe('note-score-123');
        expect(result.score).toBe(0.85);
        expect(result.confidence).toBe('standard');
        expect(result.algorithm).toBe('bayesian-v2');
        expect(result.rating_count).toBe(25);
        expect(result.tier).toBe(3);
        expect(result.tier_name).toBe('established');
        expect(result.calculated_at).toBe('2025-01-15T14:00:00Z');
      });

      it('handles note score with null optional fields', async () => {
        const jsonApiResponse = {
          data: {
            type: 'note-scores',
            id: 'new-note',
            attributes: {
              score: 0.5,
              confidence: 'no_data',
              algorithm: 'simple-v1',
              rating_count: 1,
              tier: 1,
              tier_name: 'new',
              calculated_at: null,
              content: null,
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getNoteScore('new-note');

        expect(result.calculated_at).toBeUndefined();
      });
    });

    describe('Community Servers', () => {
      it('extracts data from community server lookup response', async () => {
        const jsonApiResponse = {
          data: {
            type: 'community-servers',
            id: 'cs-uuid-123',
            attributes: {
              platform: 'discord',
              platform_id: 'guild-123456789',
              name: 'Test Community',
              description: 'A test community server',
              is_active: true,
              is_public: false,
              created_at: '2025-01-01T00:00:00Z',
              updated_at: '2025-01-15T00:00:00Z',
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getCommunityServerByPlatformId('guild-123456789');

        expect(result.id).toBe('cs-uuid-123');
        expect(result.platform).toBe('discord');
        expect(result.platform_id).toBe('guild-123456789');
        expect(result.name).toBe('Test Community');
        expect(result.is_active).toBe(true);
      });
    });
  });

  describe('Collection Responses', () => {
    describe('Notes List', () => {
      it('extracts items from notes data array', async () => {
        const jsonApiResponse = {
          data: [
            {
              type: 'notes',
              id: 'note-1',
              attributes: {
                summary: 'First note',
                classification: 'NOT_MISLEADING',
                status: 'NEEDS_MORE_RATINGS',
                helpfulness_score: 0.6,
                author_participant_id: 'author-1',
                community_server_id: 'server-1',
                channel_id: null,
                content: null,
                request_id: null,
                ratings_count: 3,
                force_published: false,
                force_published_at: null,
                created_at: '2025-01-15T10:00:00Z',
                updated_at: null,
              },
            },
            {
              type: 'notes',
              id: 'note-2',
              attributes: {
                summary: 'Second note',
                classification: 'MISINFORMED_OR_POTENTIALLY_MISLEADING',
                status: 'CURRENTLY_RATED_HELPFUL',
                helpfulness_score: 0.9,
                author_participant_id: 'author-2',
                community_server_id: 'server-1',
                channel_id: 'channel-1',
                content: 'Some content',
                request_id: 'req-1',
                ratings_count: 10,
                force_published: true,
                force_published_at: '2025-01-15T11:00:00Z',
                created_at: '2025-01-14T09:00:00Z',
                updated_at: '2025-01-15T11:00:00Z',
              },
            },
          ],
          jsonapi: { version: '1.1' },
          links: {
            self: '/api/v2/notes?page[number]=1&page[size]=20',
            first: '/api/v2/notes?page[number]=1&page[size]=20',
            last: '/api/v2/notes?page[number]=3&page[size]=20',
            next: '/api/v2/notes?page[number]=2&page[size]=20',
          },
          meta: {
            count: 45,
          },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.listNotesWithStatus('NEEDS_MORE_RATINGS', 1, 20, 'server-1');

        expect(result.data).toHaveLength(2);
        expect(result.total).toBe(45);
        expect(result.page).toBe(1);
        expect(result.size).toBe(20);

        expect(result.data[0]!.id).toBe('note-1');
        expect(result.data[0]!.attributes.summary).toBe('First note');
        expect(result.data[1]!.id).toBe('note-2');
        expect(result.data[1]!.attributes.summary).toBe('Second note');
        expect(result.data[1]!.attributes.force_published).toBe(true);
      });

      it('handles pagination meta correctly', async () => {
        const jsonApiResponse = {
          data: [],
          jsonapi: { version: '1.1' },
          meta: {
            count: 0,
          },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.listNotesWithStatus('NEEDS_MORE_RATINGS', 5, 10);

        expect(result.data).toHaveLength(0);
        expect(result.total).toBe(0);
        expect(result.page).toBe(5);
        expect(result.size).toBe(10);
      });
    });

    describe('Notes Rated By User', () => {
      it('calls v2 API with JSON:API filter parameters', async () => {
        const jsonApiResponse = {
          data: [
            {
              type: 'notes',
              id: 'note-rated-1',
              attributes: {
                summary: 'A rated note',
                classification: 'NOT_MISLEADING',
                status: 'NEEDS_MORE_RATINGS',
                helpfulness_score: 0.7,
                author_participant_id: 'author-1',
                community_server_id: 'server-456',
                channel_id: 'channel-1',
                content: null,
                request_id: null,
                ratings_count: 3,
                force_published: false,
                force_published_at: null,
                created_at: '2025-01-15T10:00:00Z',
                updated_at: null,
              },
            },
          ],
          jsonapi: { version: '1.1' },
          meta: {
            count: 15,
          },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.listNotesRatedByUser(
          'rater-participant-123',
          2,
          10,
          'server-456',
          'NEEDS_MORE_RATINGS'
        );

        expect(mockFetch).toHaveBeenCalledTimes(1);
        const fetchUrl = mockFetch.mock.calls[0]![0] as string;

        expect(fetchUrl).toContain('/api/v2/notes');
        expect(fetchUrl).toContain('filter%5Brated_by_participant_id%5D=rater-participant-123');
        expect(fetchUrl).toContain('page%5Bnumber%5D=2');
        expect(fetchUrl).toContain('page%5Bsize%5D=10');
        expect(fetchUrl).toContain('filter%5Bcommunity_server_id%5D=server-456');
        expect(fetchUrl).toContain('filter%5Bstatus%5D=NEEDS_MORE_RATINGS');

        expect(result.notes).toHaveLength(1);
        expect(result.notes[0]!.id).toBe('note-rated-1');
        expect(result.notes[0]!.summary).toBe('A rated note');
        expect(result.total).toBe(15);
        expect(result.page).toBe(2);
        expect(result.size).toBe(10);
      });

      it('calls v2 API without status filter when not provided', async () => {
        const jsonApiResponse = {
          data: [],
          jsonapi: { version: '1.1' },
          meta: { count: 0 },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        await client.listNotesRatedByUser(
          'rater-123',
          1,
          20,
          'server-789'
        );

        expect(mockFetch).toHaveBeenCalledTimes(1);
        const fetchUrl = mockFetch.mock.calls[0]![0] as string;

        expect(fetchUrl).toContain('/api/v2/notes');
        expect(fetchUrl).toContain('filter%5Brated_by_participant_id%5D=rater-123');
        expect(fetchUrl).toContain('filter%5Bcommunity_server_id%5D=server-789');
        expect(fetchUrl).not.toContain('filter%5Bstatus%5D');
      });

      it('transforms JSON:API response to NoteListResponse format', async () => {
        const jsonApiResponse = {
          data: [
            {
              type: 'notes',
              id: 'note-1',
              attributes: {
                summary: 'First note',
                classification: 'NOT_MISLEADING',
                status: 'CURRENTLY_RATED_HELPFUL',
                helpfulness_score: 0.9,
                author_participant_id: 'author-1',
                community_server_id: 'server-1',
                channel_id: 'ch-1',
                content: null,
                request_id: 'req-1',
                ratings_count: 10,
                force_published: true,
                force_published_at: '2025-01-15T12:00:00Z',
                created_at: '2025-01-14T10:00:00Z',
                updated_at: '2025-01-15T10:00:00Z',
              },
            },
            {
              type: 'notes',
              id: 'note-2',
              attributes: {
                summary: 'Second note',
                classification: 'MISINFORMED_OR_POTENTIALLY_MISLEADING',
                status: 'NEEDS_MORE_RATINGS',
                helpfulness_score: 0.5,
                author_participant_id: 'author-2',
                community_server_id: 'server-1',
                channel_id: null,
                content: null,
                request_id: null,
                ratings_count: 2,
                force_published: false,
                force_published_at: null,
                created_at: '2025-01-13T08:00:00Z',
                updated_at: null,
              },
            },
          ],
          jsonapi: { version: '1.1' },
          links: {
            self: '/api/v2/notes?page[number]=1&page[size]=20',
          },
          meta: {
            count: 50,
          },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.listNotesRatedByUser(
          'rater-abc',
          1,
          20,
          'server-1'
        );

        expect(result.notes).toHaveLength(2);
        expect(result.total).toBe(50);
        expect(result.page).toBe(1);
        expect(result.size).toBe(20);

        expect(result.notes[0]!.id).toBe('note-1');
        expect(result.notes[0]!.summary).toBe('First note');
        expect(result.notes[0]!.classification).toBe('NOT_MISLEADING');
        expect(result.notes[0]!.status).toBe('CURRENTLY_RATED_HELPFUL');
        expect(result.notes[0]!.force_published).toBe(true);
        expect(result.notes[0]!.request_id).toBe('req-1');

        expect(result.notes[1]!.id).toBe('note-2');
        expect(result.notes[1]!.channel_id).toBeNull();
        expect(result.notes[1]!.request_id).toBeNull();
        expect(result.notes[1]!.force_published).toBe(false);
      });
    });

    describe('Ratings List', () => {
      it('extracts items from ratings data array', async () => {
        const jsonApiResponse = {
          data: [
            {
              type: 'ratings',
              id: 'rating-1',
              attributes: {
                note_id: 'note-123',
                rater_participant_id: 'user-a',
                helpfulness_level: 'HELPFUL',
                created_at: '2025-01-15T10:00:00Z',
                updated_at: '2025-01-15T10:00:00Z',
              },
            },
            {
              type: 'ratings',
              id: 'rating-2',
              attributes: {
                note_id: 'note-123',
                rater_participant_id: 'user-b',
                helpfulness_level: 'NOT_HELPFUL',
                created_at: '2025-01-15T11:00:00Z',
                updated_at: '2025-01-15T11:00:00Z',
              },
            },
            {
              type: 'ratings',
              id: 'rating-3',
              attributes: {
                note_id: 'note-123',
                rater_participant_id: 'user-c',
                helpfulness_level: 'HELPFUL',
                created_at: '2025-01-15T12:00:00Z',
                updated_at: null,
              },
            },
          ],
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getRatingsForNote('note-123');

        expect(result.data).toHaveLength(3);
        expect(result.data[0]!.id).toBe('rating-1');
        expect(result.data[0]!.attributes.helpfulness_level).toBe('HELPFUL');
        expect(result.data[1]!.id).toBe('rating-2');
        expect(result.data[1]!.attributes.helpfulness_level).toBe('NOT_HELPFUL');
        expect(result.data[2]!.id).toBe('rating-3');
      });
    });

    describe('Requests List', () => {
      it('extracts items from requests data array with pagination', async () => {
        const jsonApiResponse = {
          data: [
            {
              type: 'requests',
              id: 'req-uuid-1',
              attributes: {
                request_id: 'discord-req-1',
                requested_by: 'user-1',
                status: 'PENDING',
                note_id: null,
                community_server_id: 'server-1',
                requested_at: '2025-01-15T09:00:00Z',
                created_at: '2025-01-15T09:00:00Z',
                updated_at: null,
                platform_message_id: 'msg-1',
                content: 'Request 1',
                metadata: null,
              },
            },
            {
              type: 'requests',
              id: 'req-uuid-2',
              attributes: {
                request_id: 'discord-req-2',
                requested_by: 'user-2',
                status: 'FULFILLED',
                note_id: 'note-fulfilled',
                community_server_id: 'server-1',
                requested_at: '2025-01-14T08:00:00Z',
                created_at: '2025-01-14T08:00:00Z',
                updated_at: '2025-01-15T10:00:00Z',
                platform_message_id: 'msg-2',
                content: 'Request 2',
                metadata: { priority: 'high' },
              },
            },
          ],
          jsonapi: { version: '1.1' },
          links: {
            self: '/api/v2/requests?page[number]=1&page[size]=20',
          },
          meta: {
            count: 50,
          },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.listRequests({ page: 1, size: 20 });

        expect(result.requests).toHaveLength(2);
        expect(result.total).toBe(50);
        expect(result.page).toBe(1);
        expect(result.size).toBe(20);

        expect(result.requests[0]!.id).toBe('req-uuid-1');
        expect(result.requests[0]!.status).toBe('PENDING');
        expect(result.requests[1]!.status).toBe('FULFILLED');
        expect(result.requests[1]!.note_id).toBe('note-fulfilled');
        expect(result.requests[1]!.metadata).toEqual({ priority: 'high' });
      });
    });

    describe('Top Notes', () => {
      it('extracts items from top notes response with meta', async () => {
        const jsonApiResponse = {
          data: [
            {
              type: 'note-scores',
              id: 'top-note-1',
              attributes: {
                score: 0.95,
                confidence: 'standard',
                algorithm: 'bayesian-v2',
                rating_count: 100,
                tier: 4,
                tier_name: 'veteran',
                calculated_at: '2025-01-15T14:00:00Z',
                content: 'Claim 1',
              },
            },
            {
              type: 'note-scores',
              id: 'top-note-2',
              attributes: {
                score: 0.92,
                confidence: 'standard',
                algorithm: 'bayesian-v2',
                rating_count: 80,
                tier: 3,
                tier_name: 'established',
                calculated_at: '2025-01-15T13:00:00Z',
                content: 'Claim 2',
              },
            },
          ],
          jsonapi: { version: '1.1' },
          meta: {
            total_count: 150,
            current_tier: 3,
            filters_applied: {
              min_confidence: 'standard',
            },
          },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getTopNotes(10, 'standard');

        expect(result.notes).toHaveLength(2);
        expect(result.total_count).toBe(150);
        expect(result.current_tier).toBe(3);
        expect(result.filters_applied).toEqual({ min_confidence: 'standard' });

        expect(result.notes[0]!.note_id).toBe('top-note-1');
        expect(result.notes[0]!.score).toBe(0.95);
        expect(result.notes[1]!.note_id).toBe('top-note-2');
      });
    });

    describe('Batch Note Scores', () => {
      it('extracts scores from batch response', async () => {
        const jsonApiResponse = {
          data: [
            {
              type: 'note-scores',
              id: 'batch-note-1',
              attributes: {
                score: 0.8,
                confidence: 'provisional',
                algorithm: 'bayesian-v2',
                rating_count: 15,
                tier: 2,
                tier_name: 'growing',
                calculated_at: '2025-01-15T12:00:00Z',
                content: null,
              },
            },
            {
              type: 'note-scores',
              id: 'batch-note-2',
              attributes: {
                score: 0.65,
                confidence: 'no_data',
                algorithm: 'simple-v1',
                rating_count: 3,
                tier: 1,
                tier_name: 'new',
                calculated_at: '2025-01-15T11:00:00Z',
                content: null,
              },
            },
          ],
          jsonapi: { version: '1.1' },
          meta: {
            total_requested: 3,
            total_found: 2,
            not_found: ['missing-note'],
          },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getBatchNoteScores(['batch-note-1', 'batch-note-2', 'missing-note']);

        expect(Object.keys(result.scores)).toHaveLength(2);
        expect(result.total_requested).toBe(3);
        expect(result.total_found).toBe(2);
        expect(result.not_found).toEqual(['missing-note']);

        expect(result.scores['batch-note-1']!.score).toBe(0.8);
        expect(result.scores['batch-note-2']!.score).toBe(0.65);
      });
    });
  });

  describe('JSON:API Structure Handling', () => {
    describe('data.id Field', () => {
      it('correctly extracts resource ID from data.id', async () => {
        const jsonApiResponse = {
          data: {
            type: 'notes',
            id: 'uuid-format-550e8400-e29b-41d4-a716-446655440000',
            attributes: {
              summary: 'Test',
              classification: 'NOT_MISLEADING',
              status: 'NEEDS_MORE_RATINGS',
              helpfulness_score: 0,
              author_participant_id: 'author',
              community_server_id: 'server',
              channel_id: null,
              content: null,
              request_id: null,
              ratings_count: 0,
              force_published: false,
              force_published_at: null,
              created_at: '2025-01-15T00:00:00Z',
              updated_at: null,
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getNote('uuid-format-550e8400-e29b-41d4-a716-446655440000');

        expect(result.data.id).toBe('uuid-format-550e8400-e29b-41d4-a716-446655440000');
      });
    });

    describe('jsonapi.version Field', () => {
      it('accepts responses with jsonapi version 1.1', async () => {
        const jsonApiResponse = {
          data: [],
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getRatingsForNote('any-note');

        expect(result).toEqual([]);
      });

      it('accepts responses with jsonapi version 1.0', async () => {
        const jsonApiResponse = {
          data: [],
          jsonapi: { version: '1.0' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getRatingsForNote('any-note');

        expect(result).toEqual([]);
      });
    });

    describe('Links Section', () => {
      it('processes response even when links section is present', async () => {
        const jsonApiResponse = {
          data: {
            type: 'notes',
            id: 'note-with-links',
            attributes: {
              summary: 'Note with links',
              classification: 'NOT_MISLEADING',
              status: 'NEEDS_MORE_RATINGS',
              helpfulness_score: 0,
              author_participant_id: 'author',
              community_server_id: 'server',
              channel_id: null,
              content: null,
              request_id: null,
              ratings_count: 0,
              force_published: false,
              force_published_at: null,
              created_at: '2025-01-15T00:00:00Z',
              updated_at: null,
            },
          },
          jsonapi: { version: '1.1' },
          links: {
            self: '/api/v2/notes/note-with-links',
            related: {
              href: '/api/v2/notes/note-with-links/ratings',
              meta: {
                count: 5,
              },
            },
          },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getNote('note-with-links');

        expect(result.data.id).toBe('note-with-links');
        expect(result.data.attributes.summary).toBe('Note with links');
      });

      it('handles pagination links in list responses', async () => {
        const jsonApiResponse = {
          data: [],
          jsonapi: { version: '1.1' },
          links: {
            self: '/api/v2/notes?page[number]=2&page[size]=10',
            first: '/api/v2/notes?page[number]=1&page[size]=10',
            prev: '/api/v2/notes?page[number]=1&page[size]=10',
            next: '/api/v2/notes?page[number]=3&page[size]=10',
            last: '/api/v2/notes?page[number]=5&page[size]=10',
          },
          meta: {
            count: 50,
          },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.listNotesWithStatus('NEEDS_MORE_RATINGS', 2, 10);

        expect(result.total).toBe(50);
        expect(result.page).toBe(2);
        expect(result.size).toBe(10);
      });
    });

    describe('Meta Section', () => {
      it('extracts count from meta.count', async () => {
        const jsonApiResponse = {
          data: [
            {
              type: 'requests',
              id: 'req-1',
              attributes: {
                request_id: 'r1',
                requested_by: 'user',
                status: 'PENDING',
                note_id: null,
                community_server_id: 'server',
                requested_at: '2025-01-15T00:00:00Z',
                created_at: '2025-01-15T00:00:00Z',
                updated_at: null,
                platform_message_id: null,
                content: null,
                metadata: null,
              },
            },
          ],
          jsonapi: { version: '1.1' },
          meta: {
            count: 1000,
          },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.listRequests({ page: 1, size: 1 });

        expect(result.total).toBe(1000);
        expect(result.requests).toHaveLength(1);
      });

      it('falls back to data length when meta.count is missing', async () => {
        const jsonApiResponse = {
          data: [
            {
              type: 'ratings',
              id: 'r1',
              attributes: {
                note_id: 'n1',
                rater_participant_id: 'u1',
                helpfulness_level: 'HELPFUL',
                created_at: '2025-01-15T00:00:00Z',
                updated_at: null,
              },
            },
            {
              type: 'ratings',
              id: 'r2',
              attributes: {
                note_id: 'n1',
                rater_participant_id: 'u2',
                helpfulness_level: 'NOT_HELPFUL',
                created_at: '2025-01-15T00:00:00Z',
                updated_at: null,
              },
            },
          ],
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getRatingsForNote('n1');

        expect(result).toHaveLength(2);
      });
    });
  });

  describe('Error Responses', () => {
    describe('JSON:API Error Format', () => {
      it('handles JSON:API errors array format', async () => {
        const errorResponse = {
          errors: [
            {
              status: '404',
              code: 'NOT_FOUND',
              title: 'Resource not found',
              detail: 'Note with ID not-exist does not exist',
              source: {
                pointer: '/data/id',
              },
            },
          ],
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(errorResponse), {
            status: 404,
            statusText: 'Not Found',
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        await expect(client.getNote('not-exist')).rejects.toThrow('API request failed: 404 Not Found');
      });

      it('handles multiple errors in errors array', async () => {
        const errorResponse = {
          errors: [
            {
              status: '400',
              code: 'VALIDATION_ERROR',
              title: 'Invalid field',
              detail: 'summary is required',
              source: { pointer: '/data/attributes/summary' },
            },
            {
              status: '400',
              code: 'VALIDATION_ERROR',
              title: 'Invalid field',
              detail: 'classification must be valid',
              source: { pointer: '/data/attributes/classification' },
            },
          ],
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(errorResponse), {
            status: 400,
            statusText: 'Bad Request',
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        await expect(client.getNote('bad-note-id')).rejects.toThrow(
          'API request failed: 400 Bad Request'
        );
      });

      it('handles 422 Unprocessable Entity with JSON:API errors', async () => {
        const errorResponse = {
          errors: [
            {
              status: '422',
              code: 'UNPROCESSABLE_ENTITY',
              title: 'Validation failed',
              detail: 'Invalid entity',
            },
          ],
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(errorResponse), {
            status: 422,
            statusText: 'Unprocessable Entity',
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        await expect(client.getNote('unprocessable-id')).rejects.toThrow(
          'API request failed: 422 Unprocessable Entity'
        );
      });

      it('handles 409 Conflict error', async () => {
        const errorResponse = {
          errors: [
            {
              status: '409',
              code: 'CONFLICT',
              title: 'Resource conflict',
              detail: 'Note already exists for this request',
            },
          ],
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(errorResponse), {
            status: 409,
            statusText: 'Conflict',
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        await expect(client.getNote('conflict-note-id')).rejects.toThrow(
          'API request failed: 409 Conflict'
        );
      });

      it('handles 500 Internal Server Error', async () => {
        const errorResponse = {
          errors: [
            {
              status: '500',
              code: 'INTERNAL_ERROR',
              title: 'Internal server error',
              detail: 'An unexpected error occurred',
            },
          ],
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockImplementation(async () =>
          new Response(JSON.stringify(errorResponse), {
            status: 500,
            statusText: 'Internal Server Error',
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        await expect(client.getNote('test')).rejects.toThrow(
          'API request failed: 500 Internal Server Error'
        );
      });
    });

    describe('Non-JSON:API Error Responses', () => {
      it('handles plain text error responses', async () => {
        mockFetch.mockImplementation(async () =>
          new Response('Internal Server Error', {
            status: 500,
            statusText: 'Internal Server Error',
            headers: { 'Content-Type': 'text/plain' },
          })
        );

        await expect(client.healthCheck()).rejects.toThrow(
          'API request failed: 500 Internal Server Error'
        );
      });

      it('handles HTML error responses (e.g., from proxy)', async () => {
        mockFetch.mockImplementation(async () =>
          new Response('<html><body>Bad Gateway</body></html>', {
            status: 502,
            statusText: 'Bad Gateway',
            headers: { 'Content-Type': 'text/html' },
          })
        );

        await expect(client.healthCheck()).rejects.toThrow(
          'API request failed: 502 Bad Gateway'
        );
      });
    });
  });

  describe('Edge Cases', () => {
    describe('Empty Arrays', () => {
      it('handles empty notes list', async () => {
        const jsonApiResponse = {
          data: [],
          jsonapi: { version: '1.1' },
          meta: { count: 0 },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.listNotesWithStatus('NEEDS_MORE_RATINGS');

        expect(result.data).toEqual([]);
        expect(result.total).toBe(0);
      });

      it('handles empty ratings list', async () => {
        const jsonApiResponse = {
          data: [],
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getRatingsForNote('note-no-ratings');

        expect(result).toEqual([]);
      });

      it('handles empty requests list', async () => {
        const jsonApiResponse = {
          data: [],
          jsonapi: { version: '1.1' },
          meta: { count: 0 },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.listRequests({ status: 'PENDING' });

        expect(result.requests).toEqual([]);
        expect(result.total).toBe(0);
      });
    });

    describe('Null Values', () => {
      it('handles null channel_id correctly', async () => {
        const jsonApiResponse = {
          data: {
            type: 'notes',
            id: 'note-null-channel',
            attributes: {
              summary: 'Test',
              classification: 'NOT_MISLEADING',
              status: 'NEEDS_MORE_RATINGS',
              helpfulness_score: 0,
              author_participant_id: 'author',
              community_server_id: 'server',
              channel_id: null,
              content: null,
              request_id: null,
              ratings_count: 0,
              force_published: false,
              force_published_at: null,
              created_at: '2025-01-15T00:00:00Z',
              updated_at: null,
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getNote('note-null-channel');

        expect(result.data.attributes.channel_id).toBeNull();
      });

      it('handles null metadata in requests', async () => {
        const jsonApiResponse = {
          data: {
            type: 'requests',
            id: 'req-null-meta',
            attributes: {
              request_id: 'discord-null',
              requested_by: 'user',
              status: 'PENDING',
              note_id: null,
              community_server_id: 'server',
              requested_at: '2025-01-15T00:00:00Z',
              created_at: '2025-01-15T00:00:00Z',
              updated_at: null,
              platform_message_id: null,
              content: null,
              metadata: null,
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getRequest('discord-null');

        expect(result.metadata).toBeUndefined();
        expect(result.platform_message_id).toBeUndefined();
      });

      it('handles null updated_at timestamps', async () => {
        const noteId = '770e8400-e29b-41d4-a716-446655440002';
        const jsonApiResponse = {
          data: {
            type: 'ratings',
            id: 'rating-no-update',
            attributes: {
              note_id: noteId,
              rater_participant_id: 'user-1',
              helpfulness_level: 'HELPFUL',
              created_at: '2025-01-15T00:00:00Z',
              updated_at: null,
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 201,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.rateNote({
          noteId,
          userId: 'user-1',
          helpful: true,
        });

        expect(result.noteId).toBe(noteId);
        expect(result.helpful).toBe(true);
      });
    });

    describe('Missing Optional Fields', () => {
      it('handles response without links section', async () => {
        const jsonApiResponse = {
          data: [],
          jsonapi: { version: '1.1' },
          meta: { count: 0 },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.listNotesWithStatus('NEEDS_MORE_RATINGS');

        expect(result).toBeDefined();
        expect(result.data).toEqual([]);
      });

      it('handles response without meta section for list', async () => {
        const jsonApiResponse = {
          data: [
            {
              type: 'ratings',
              id: 'r1',
              attributes: {
                note_id: 'n1',
                rater_participant_id: 'u1',
                helpfulness_level: 'HELPFUL',
                created_at: '2025-01-15T00:00:00Z',
                updated_at: null,
              },
            },
          ],
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getRatingsForNote('n1');

        expect(result).toHaveLength(1);
      });

      it('handles score response without calculated_at', async () => {
        const jsonApiResponse = {
          data: {
            type: 'note-scores',
            id: 'uncalculated-note',
            attributes: {
              score: 0.5,
              confidence: 'LOW',
              algorithm: 'default',
              rating_count: 0,
              tier: 1,
              tier_name: 'new',
              calculated_at: null,
              content: null,
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getNoteScore('uncalculated-note');

        expect(result.calculated_at).toBeUndefined();
      });
    });

    describe('Special Characters and Unicode', () => {
      it('handles note summary with special characters', async () => {
        const jsonApiResponse = {
          data: {
            type: 'notes',
            id: 'note-special',
            attributes: {
              summary: 'Note with special chars: <script>alert("xss")</script> & "quotes" \'apostrophe\'',
              classification: 'NOT_MISLEADING',
              status: 'NEEDS_MORE_RATINGS',
              helpfulness_score: 0,
              author_participant_id: 'author',
              community_server_id: 'server',
              channel_id: null,
              content: null,
              request_id: null,
              ratings_count: 0,
              force_published: false,
              force_published_at: null,
              created_at: '2025-01-15T00:00:00Z',
              updated_at: null,
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getNote('note-special');

        expect(result.data.attributes.summary).toBe(
          'Note with special chars: <script>alert("xss")</script> & "quotes" \'apostrophe\''
        );
      });

      it('handles note with unicode characters', async () => {
        const jsonApiResponse = {
          data: {
            type: 'notes',
            id: 'note-unicode',
            attributes: {
              summary: 'Unicode test: Japanese test Emoji test',
              classification: 'NOT_MISLEADING',
              status: 'NEEDS_MORE_RATINGS',
              helpfulness_score: 0,
              author_participant_id: 'author',
              community_server_id: 'server',
              channel_id: null,
              content: null,
              request_id: null,
              ratings_count: 0,
              force_published: false,
              force_published_at: null,
              created_at: '2025-01-15T00:00:00Z',
              updated_at: null,
            },
          },
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getNote('note-unicode');

        expect(result.data.attributes.summary).toBe('Unicode test: Japanese test Emoji test');
      });
    });

    describe('Content-Type Header Variations', () => {
      it('handles application/vnd.api+json content type', async () => {
        const jsonApiResponse = {
          data: [],
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getRatingsForNote('any');

        expect(result).toEqual([]);
      });

      it('handles application/json content type', async () => {
        const jsonApiResponse = {
          data: [],
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        );

        const result = await client.getRatingsForNote('any');

        expect(result).toEqual([]);
      });

      it('handles content type with charset', async () => {
        const jsonApiResponse = {
          data: [],
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json; charset=utf-8' },
          })
        );

        const result = await client.getRatingsForNote('any');

        expect(result).toEqual([]);
      });
    });

    describe('Large Collections', () => {
      it('handles list with many items', async () => {
        const ratings = Array.from({ length: 100 }, (_, i) => ({
          type: 'ratings',
          id: `rating-${i}`,
          attributes: {
            note_id: 'note-large',
            rater_participant_id: `user-${i}`,
            helpfulness_level: i % 2 === 0 ? 'HELPFUL' : 'NOT_HELPFUL',
            created_at: '2025-01-15T00:00:00Z',
            updated_at: null,
          },
        }));

        const jsonApiResponse = {
          data: ratings,
          jsonapi: { version: '1.1' },
        };

        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(jsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' },
          })
        );

        const result = await client.getRatingsForNote('note-large');

        expect(result).toHaveLength(100);
        expect(result[0]!.id).toBe('rating-0');
        expect(result[99]!.id).toBe('rating-99');
      });
    });
  });
});
