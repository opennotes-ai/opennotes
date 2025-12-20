/**
 * TDD Tests for JSONAPI Note structure passthrough (task-857.01)
 *
 * These tests verify that note-related API methods pass through raw JSONAPI
 * structure instead of transforming/flattening the response.
 *
 * Expected JSONAPI structure:
 * {
 *   data: {
 *     type: 'notes',
 *     id: 'xxx',
 *     attributes: { ... }
 *   },
 *   jsonapi: { version: '1.1' }
 * }
 */
import { jest } from '@jest/globals';
import { ApiClient } from '../../src/lib/api-client.js';

interface JSONAPIResource {
  type: string;
  id: string;
  attributes: Record<string, unknown>;
}

interface JSONAPISingleResponse {
  data: JSONAPIResource;
  jsonapi: { version: string };
  links?: Record<string, string>;
}

interface JSONAPIListResponse {
  data: JSONAPIResource[];
  jsonapi: { version: string };
  meta?: { count?: number };
  links?: Record<string, string>;
}

const mockFetch = jest.fn<typeof fetch>();
global.fetch = mockFetch;

jest.mock('../../src/logger.js', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    warn: jest.fn(),
    debug: jest.fn(),
  },
}));

jest.mock('../../src/utils/gcp-auth.js', () => ({
  isRunningOnGCP: jest.fn<() => Promise<boolean>>().mockResolvedValue(false),
  getIdentityToken: jest.fn<() => Promise<string | null>>().mockResolvedValue(null),
}));

describe('ApiClient Note Methods - JSONAPI Passthrough', () => {
  let apiClient: ApiClient;

  const mockJSONAPINote = {
    data: {
      type: 'notes',
      id: 'note-uuid-123',
      attributes: {
        summary: 'This is a test note summary',
        classification: 'NOT_MISLEADING',
        status: 'NEEDS_MORE_RATINGS',
        helpfulness_score: 0.5,
        author_participant_id: 'user-123',
        community_server_id: 'community-uuid-456',
        channel_id: 'channel-789',
        request_id: 'request-abc',
        ratings_count: 3,
        force_published: false,
        force_published_at: null,
        ai_generated: false,
        ai_provider: null,
        created_at: '2024-01-15T10:00:00Z',
        updated_at: '2024-01-15T12:00:00Z',
      },
    },
    jsonapi: { version: '1.1' },
    links: { self: '/api/v2/notes/note-uuid-123' },
  };

  const mockJSONAPINoteList = {
    data: [
      {
        type: 'notes',
        id: 'note-uuid-1',
        attributes: {
          summary: 'First note',
          classification: 'NOT_MISLEADING',
          status: 'NEEDS_MORE_RATINGS',
          helpfulness_score: 0.6,
          author_participant_id: 'user-1',
          community_server_id: 'community-uuid-456',
          channel_id: null,
          request_id: null,
          ratings_count: 5,
          force_published: false,
          force_published_at: null,
          created_at: '2024-01-15T10:00:00Z',
          updated_at: null,
        },
      },
      {
        type: 'notes',
        id: 'note-uuid-2',
        attributes: {
          summary: 'Second note',
          classification: 'MISINFORMED_OR_POTENTIALLY_MISLEADING',
          status: 'CURRENTLY_RATED_HELPFUL',
          helpfulness_score: 0.8,
          author_participant_id: 'user-2',
          community_server_id: 'community-uuid-456',
          channel_id: 'channel-abc',
          request_id: 'request-xyz',
          ratings_count: 10,
          force_published: true,
          force_published_at: '2024-01-15T11:00:00Z',
          created_at: '2024-01-14T08:00:00Z',
          updated_at: '2024-01-15T11:00:00Z',
        },
      },
    ],
    jsonapi: { version: '1.1' },
    meta: { count: 2 },
    links: {
      self: '/api/v2/notes?page[number]=1&page[size]=20',
      first: '/api/v2/notes?page[number]=1&page[size]=20',
    },
  };

  beforeEach(() => {
    jest.clearAllMocks();
    apiClient = new ApiClient({
      serverUrl: 'http://localhost:8000',
      apiKey: 'test-api-key',
      environment: 'development',
    });
  });

  describe('getNote - should return raw JSONAPI structure', () => {
    it('should return JSONAPI response with data.type, data.id, data.attributes', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/vnd.api+json' }),
        json: async () => mockJSONAPINote,
      } as Response);

      const result = await apiClient.getNote('note-uuid-123') as unknown as JSONAPISingleResponse;

      expect(result).toHaveProperty('data');
      expect(result).toHaveProperty('jsonapi');
      expect(result.data).toHaveProperty('type', 'notes');
      expect(result.data).toHaveProperty('id', 'note-uuid-123');
      expect(result.data).toHaveProperty('attributes');
      expect(result.data.attributes).toHaveProperty('summary', 'This is a test note summary');
      expect(result.data.attributes).toHaveProperty('classification', 'NOT_MISLEADING');
      expect(result.data.attributes).toHaveProperty('status', 'NEEDS_MORE_RATINGS');
    });

    it('should NOT flatten the response into a custom NoteResponse type', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/vnd.api+json' }),
        json: async () => mockJSONAPINote,
      } as Response);

      const result = await apiClient.getNote('note-uuid-123');

      expect(result).not.toHaveProperty('id', 'note-uuid-123');
      expect(result).not.toHaveProperty('summary');
      expect(result).not.toHaveProperty('classification');
      expect(result).not.toHaveProperty('ratings');
      expect(result).not.toHaveProperty('request');
    });
  });

  describe('createNote - should return raw JSONAPI structure', () => {
    it('should return JSONAPI response with data.type, data.id, data.attributes', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/vnd.api+json' }),
          json: async () => ({
            data: {
              type: 'community-servers',
              id: '550e8400-e29b-41d4-a716-446655440001',
              attributes: {
                platform: 'discord',
                platform_id: 'guild-123',
                name: 'Test Server',
                is_active: true,
              },
            },
            jsonapi: { version: '1.1' },
          }),
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          status: 201,
          headers: new Headers({ 'content-type': 'application/vnd.api+json' }),
          json: async () => mockJSONAPINote,
        } as Response);

      const result = await apiClient.createNote(
        {
          messageId: 'msg-123',
          authorId: 'user-123',
          content: 'This is a test note summary',
          channelId: 'channel-789',
          requestId: 'request-abc',
        },
        { userId: 'user-123', guildId: 'guild-123' }
      ) as unknown as JSONAPISingleResponse;

      expect(result).toHaveProperty('data');
      expect(result).toHaveProperty('jsonapi');
      expect(result.data).toHaveProperty('type', 'notes');
      expect(result.data).toHaveProperty('id', 'note-uuid-123');
      expect(result.data).toHaveProperty('attributes');
      expect(result.data.attributes).toHaveProperty('summary', 'This is a test note summary');
    });

    it('should NOT flatten the response into a custom Note type', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/vnd.api+json' }),
          json: async () => ({
            data: {
              type: 'community-servers',
              id: '550e8400-e29b-41d4-a716-446655440001',
              attributes: {
                platform: 'discord',
                platform_id: 'guild-123',
                name: 'Test Server',
                is_active: true,
              },
            },
            jsonapi: { version: '1.1' },
          }),
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          status: 201,
          headers: new Headers({ 'content-type': 'application/vnd.api+json' }),
          json: async () => mockJSONAPINote,
        } as Response);

      const result = await apiClient.createNote(
        {
          messageId: 'msg-123',
          authorId: 'user-123',
          content: 'This is a test note summary',
        },
        { userId: 'user-123', guildId: 'guild-123' }
      );

      expect(result).not.toHaveProperty('messageId');
      expect(result).not.toHaveProperty('authorId');
      expect(result).not.toHaveProperty('content');
      expect(result).not.toHaveProperty('helpfulCount');
      expect(result).not.toHaveProperty('notHelpfulCount');
    });
  });

  describe('forcePublishNote - should return raw JSONAPI structure', () => {
    it('should return JSONAPI response with data.type, data.id, data.attributes', async () => {
      const forcePublishedNote = {
        ...mockJSONAPINote,
        data: {
          ...mockJSONAPINote.data,
          attributes: {
            ...mockJSONAPINote.data.attributes,
            status: 'CURRENTLY_RATED_HELPFUL',
            force_published: true,
            force_published_at: '2024-01-15T14:00:00Z',
          },
        },
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/vnd.api+json' }),
        json: async () => forcePublishedNote,
      } as Response);

      const result = await apiClient.forcePublishNote('note-uuid-123') as unknown as JSONAPISingleResponse;

      expect(result).toHaveProperty('data');
      expect(result).toHaveProperty('jsonapi');
      expect(result.data).toHaveProperty('type', 'notes');
      expect(result.data).toHaveProperty('id', 'note-uuid-123');
      expect(result.data.attributes).toHaveProperty('force_published', true);
      expect(result.data.attributes).toHaveProperty('force_published_at', '2024-01-15T14:00:00Z');
    });

    it('should NOT flatten the response into a custom NoteResponse type', async () => {
      const forcePublishedNote = {
        ...mockJSONAPINote,
        data: {
          ...mockJSONAPINote.data,
          attributes: {
            ...mockJSONAPINote.data.attributes,
            force_published: true,
          },
        },
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/vnd.api+json' }),
        json: async () => forcePublishedNote,
      } as Response);

      const result = await apiClient.forcePublishNote('note-uuid-123');

      expect(result).not.toHaveProperty('id', 'note-uuid-123');
      expect(result).not.toHaveProperty('summary');
      expect(result).not.toHaveProperty('ratings');
      expect(result).not.toHaveProperty('request');
    });
  });

  describe('listNotesWithStatus - should return raw JSONAPI structure', () => {
    it('should return JSONAPI list response with data array of resources', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/vnd.api+json' }),
        json: async () => mockJSONAPINoteList,
      } as Response);

      const result = await apiClient.listNotesWithStatus('NEEDS_MORE_RATINGS') as unknown as JSONAPIListResponse;

      expect(result).toHaveProperty('data');
      expect(result).toHaveProperty('jsonapi');
      expect(result).toHaveProperty('meta');
      expect(Array.isArray(result.data)).toBe(true);
      expect(result.data.length).toBe(2);

      expect(result.data[0]).toHaveProperty('type', 'notes');
      expect(result.data[0]).toHaveProperty('id', 'note-uuid-1');
      expect(result.data[0]).toHaveProperty('attributes');
      expect(result.data[0].attributes).toHaveProperty('summary', 'First note');

      expect(result.data[1]).toHaveProperty('type', 'notes');
      expect(result.data[1]).toHaveProperty('id', 'note-uuid-2');
      expect(result.data[1].attributes).toHaveProperty('summary', 'Second note');
    });

    it('should NOT transform into NoteListResponse with flattened notes array', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/vnd.api+json' }),
        json: async () => mockJSONAPINoteList,
      } as Response);

      const result = await apiClient.listNotesWithStatus('NEEDS_MORE_RATINGS');

      expect(result).not.toHaveProperty('notes');
      expect(result).not.toHaveProperty('total');
      expect(result).not.toHaveProperty('page');
      expect(result).not.toHaveProperty('size');
    });
  });

  describe('getNotes (by messageId) - should return raw JSONAPI structure', () => {
    it('should return JSONAPI list response with data array', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/vnd.api+json' }),
        json: async () => mockJSONAPINoteList,
      } as Response);

      const result = await apiClient.getNotes('message-123') as unknown as JSONAPIListResponse;

      expect(result).toHaveProperty('data');
      expect(result).toHaveProperty('jsonapi');
      expect(Array.isArray(result.data)).toBe(true);

      if (result.data.length > 0) {
        expect(result.data[0]).toHaveProperty('type', 'notes');
        expect(result.data[0]).toHaveProperty('id');
        expect(result.data[0]).toHaveProperty('attributes');
      }
    });

    it('should NOT flatten into array of Note objects', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/vnd.api+json' }),
        json: async () => mockJSONAPINoteList,
      } as Response);

      const result = await apiClient.getNotes('message-123');

      if (Array.isArray(result) && result.length > 0) {
        expect(result[0]).not.toHaveProperty('messageId');
        expect(result[0]).not.toHaveProperty('authorId');
        expect(result[0]).not.toHaveProperty('content');
        expect(result[0]).not.toHaveProperty('helpfulCount');
      }
    });
  });
});
