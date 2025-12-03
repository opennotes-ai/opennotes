import { jest } from '@jest/globals';

// Mock fetch with proper Response objects
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

const { apiClient, ApiClient } = await import('../src/api-client.js');

describe('ApiClient Wrapper', () => {
  describe('Sensitive Data Sanitization', () => {
    it('should sanitize password fields in logs', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      const errorBody = {
        password: 'secret123',
        username: 'testuser',
        data: {
          api_key: 'sk-12345',
          value: 'safe',
        },
      };

      mockFetch.mockImplementationOnce(async () =>
        new Response(JSON.stringify(errorBody), {
          status: 400,
          statusText: 'Bad Request',
          headers: { 'Content-Type': 'application/json' }
        })
      );

      mockLogger.error.mockClear();

      await expect(client.healthCheck()).rejects.toThrow();

      expect(mockLogger.error).toHaveBeenCalledWith(
        'API request failed',
        expect.objectContaining({
          responseBody: {
            password: '[REDACTED]',
            username: 'testuser',
            data: {
              api_key: '[REDACTED]',
              value: 'safe',
            },
          },
        })
      );
    });

    it('should sanitize authorization headers in logs', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      const errorBody = {
        error: 'Unauthorized',
        headers: {
          authorization: 'Bearer sk-12345',
          'content-type': 'application/json',
        },
      };

      mockFetch.mockImplementationOnce(async () =>
        new Response(JSON.stringify(errorBody), {
          status: 401,
          statusText: 'Unauthorized',
          headers: { 'Content-Type': 'application/json' }
        })
      );

      mockLogger.error.mockClear();

      await expect(client.healthCheck()).rejects.toThrow();

      expect(mockLogger.error).toHaveBeenCalledWith(
        'API request failed',
        expect.objectContaining({
          responseBody: {
            error: 'Unauthorized',
            headers: {
              authorization: '[REDACTED]',
              'content-type': 'application/json',
            },
          },
        })
      );
    });

    it('should sanitize arrays of objects', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      const errorBody = {
        users: [
          { username: 'user1', password: 'pass1' },
          { username: 'user2', token: 'token123' },
        ],
      };

      mockFetch.mockImplementationOnce(async () =>
        new Response(JSON.stringify(errorBody), {
          status: 500,
          statusText: 'Internal Server Error',
          headers: { 'Content-Type': 'application/json' }
        })
      );

      mockLogger.error.mockClear();

      await expect(client.healthCheck()).rejects.toThrow();

      expect(mockLogger.error).toHaveBeenCalledWith(
        'API request failed',
        expect.objectContaining({
          responseBody: {
            users: [
              { username: 'user1', password: '[REDACTED]' },
              { username: 'user2', token: '[REDACTED]' },
            ],
          },
        })
      );
    });

    it('should preserve non-sensitive data', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      const errorBody = {
        error: 'Not found',
        details: {
          id: 123,
          name: 'test',
          nested: {
            value: 'safe',
          },
        },
      };

      mockFetch.mockImplementationOnce(async () =>
        new Response(JSON.stringify(errorBody), {
          status: 404,
          statusText: 'Not Found',
          headers: { 'Content-Type': 'application/json' }
        })
      );

      mockLogger.error.mockClear();

      await expect(client.healthCheck()).rejects.toThrow();

      expect(mockLogger.error).toHaveBeenCalledWith(
        'API request failed',
        expect.objectContaining({
          responseBody: errorBody,
        })
      );
    });
  });

  describe('Response Size Limits', () => {
    it('should reject responses exceeding size limit', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
        maxResponseSize: 1000,
      });

      mockFetch.mockResolvedValueOnce(
        new Response('Large response', {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': '2000',
          },
        })
      );

      mockLogger.error.mockClear();

      await expect(client.healthCheck()).rejects.toThrow('Response size 2000 bytes exceeds maximum allowed size of 1000 bytes');

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Response size exceeds limit',
        expect.objectContaining({
          contentLength: 2000,
          maxResponseSize: 1000,
        })
      );
    });

    it('should accept responses within size limit', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
        maxResponseSize: 10000,
      });

      const mockResponse = {
        status: 'healthy',
        version: '1.0.0',
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': '50',
          },
        })
      );

      const result = await client.healthCheck();

      expect(result).toEqual(mockResponse);
    });

    it('should warn when response size approaches limit', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
        maxResponseSize: 1000,
      });

      const mockResponse = {
        status: 'healthy',
        version: '1.0.0',
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': '850',
          },
        })
      );

      mockLogger.warn.mockClear();

      const result = await client.healthCheck();

      expect(result).toEqual(mockResponse);
      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Response size approaching limit',
        expect.objectContaining({
          contentLength: 850,
          maxResponseSize: 1000,
        })
      );
    });

    it('should use default size limit of 10MB', () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      expect((client as any).maxResponseSize).toBe(10 * 1024 * 1024);
    });

    it('should respect custom size limit', () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
        maxResponseSize: 5000000,
      });

      expect((client as any).maxResponseSize).toBe(5000000);
    });

    it('should handle responses without Content-Length header', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
        maxResponseSize: 1000,
      });

      const mockResponse = {
        status: 'healthy',
        version: '1.0.0',
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
          },
        })
      );

      const result = await client.healthCheck();

      expect(result).toEqual(mockResponse);
    });
  });

  describe('Retry-After Header Support', () => {
    it('should respect Retry-After header with seconds', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
        retryAttempts: 2,
      });

      let attemptCount = 0;
      mockFetch.mockImplementation(async () => {
        attemptCount++;
        if (attemptCount === 1) {
          return new Response('Too Many Requests', {
            status: 429,
            statusText: 'Too Many Requests',
            headers: {
              'Retry-After': '2',
            },
          });
        }
        return new Response(JSON.stringify({ status: 'healthy', version: '1.0.0' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      });

      mockLogger.info.mockClear();

      const result = await client.healthCheck();

      expect(result).toEqual({ status: 'healthy', version: '1.0.0' });
      expect(attemptCount).toBe(2);
      expect(mockLogger.info).toHaveBeenCalledWith(
        'Retrying API request',
        expect.objectContaining({
          delayMs: 2000,
        })
      );
    });

    it('should respect Retry-After header with HTTP date', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
        retryAttempts: 2,
      });

      const futureDate = new Date(Date.now() + 3000);

      let attemptCount = 0;
      mockFetch.mockImplementation(async () => {
        attemptCount++;
        if (attemptCount === 1) {
          return new Response('Too Many Requests', {
            status: 429,
            statusText: 'Too Many Requests',
            headers: {
              'Retry-After': futureDate.toUTCString(),
            },
          });
        }
        return new Response(JSON.stringify({ status: 'healthy', version: '1.0.0' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      });

      mockLogger.info.mockClear();

      const result = await client.healthCheck();

      expect(result).toEqual({ status: 'healthy', version: '1.0.0' });
      expect(attemptCount).toBe(2);
      expect(mockLogger.info).toHaveBeenCalledWith(
        'Retrying API request',
        expect.objectContaining({
          delayMs: expect.any(Number),
        })
      );

      const retryCalls = mockLogger.info.mock.calls.filter(
        call => call[0] === 'Retrying API request'
      );
      const loggedDelay = (retryCalls[0][1] as any).delayMs;
      expect(loggedDelay).toBeGreaterThan(2000);
      expect(loggedDelay).toBeLessThan(4000);
    });

    it('should cap Retry-After delay at 60 seconds', () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      const mockResponse = new Response('', {
        status: 429,
        headers: { 'Retry-After': '120' },
      });

      const delay = (client as any).getRetryDelay(mockResponse, 1);

      expect(delay).toBe(60000);
    });

    it('should use exponential backoff when Retry-After is not present', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
        retryAttempts: 3,
        retryDelayMs: 1000,
      });

      let attemptCount = 0;
      mockFetch.mockImplementation(async () => {
        attemptCount++;
        if (attemptCount < 3) {
          return new Response('Internal Server Error', {
            status: 500,
            statusText: 'Internal Server Error',
          });
        }
        return new Response(JSON.stringify({ status: 'healthy', version: '1.0.0' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      });

      mockLogger.info.mockClear();

      const result = await client.healthCheck();

      expect(result).toEqual({ status: 'healthy', version: '1.0.0' });
      expect(attemptCount).toBe(3);

      const retryCalls = mockLogger.info.mock.calls.filter(
        call => call[0] === 'Retrying API request'
      );
      const firstRetryDelay = (retryCalls[0][1] as any).delayMs;
      const secondRetryDelay = (retryCalls[1][1] as any).delayMs;

      expect(firstRetryDelay).toBe(1000);
      expect(secondRetryDelay).toBe(2000);
    });
  });

  describe('Request Timeouts', () => {
    it('should timeout requests after configured duration', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
        requestTimeout: 100,
      });

      mockFetch.mockImplementationOnce((_url, options) => {
        return new Promise((resolve, reject) => {
          const signal = options?.signal as AbortSignal | undefined;
          if (signal) {
            signal.addEventListener('abort', () => {
              const error = new Error('The operation was aborted');
              error.name = 'AbortError';
              reject(error);
            });
          }

          setTimeout(() => {
            resolve(new Response(JSON.stringify({ status: 'ok' }), {
              status: 200,
              headers: { 'Content-Type': 'application/json' }
            }));
          }, 200);
        });
      });

      await expect(client.healthCheck()).rejects.toThrow('API request timeout after 100ms');
    });

    it('should not timeout if request completes in time', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
        requestTimeout: 5000,
      });

      const mockResponse = {
        status: 'healthy',
        version: '1.0.0',
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      );

      const result = await client.healthCheck();
      expect(result).toEqual(mockResponse);
    });

    it('should use default timeout of 30 seconds', () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      expect((client as any).requestTimeout).toBe(30000);
    });

    it('should respect custom timeout configuration', () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
        requestTimeout: 5000,
      });

      expect((client as any).requestTimeout).toBe(5000);
    });
  });

  describe('HTTPS Enforcement', () => {
    it('should allow HTTPS URLs in production', () => {
      expect(() => {
        new ApiClient({
          serverUrl: 'https://api.example.com',
          environment: 'production',
        });
      }).not.toThrow();
    });

    it('should throw error for HTTP URLs in production', () => {
      expect(() => {
        new ApiClient({
          serverUrl: 'http://api.example.com',
          environment: 'production',
        });
      }).toThrow('HTTPS is required for production API connections');
    });

    it('should allow HTTP localhost in production', () => {
      expect(() => {
        new ApiClient({
          serverUrl: 'http://localhost:8000',
          environment: 'production',
        });
      }).not.toThrow();

      expect(() => {
        new ApiClient({
          serverUrl: 'http://127.0.0.1:8000',
          environment: 'production',
        });
      }).not.toThrow();
    });

    it('should allow HTTP URLs in development', () => {
      expect(() => {
        new ApiClient({
          serverUrl: 'http://api.example.com',
          environment: 'development',
        });
      }).not.toThrow();
    });

    it('should warn for non-localhost HTTP in development', () => {
      mockLogger.warn.mockClear();

      new ApiClient({
        serverUrl: 'http://api.example.com',
        environment: 'development',
      });

      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Non-HTTPS API connection detected in development',
        expect.objectContaining({
          serverUrl: 'http://api.example.com',
          protocol: 'http:',
          environment: 'development',
        })
      );
    });

    it('should not warn for localhost HTTP in development', () => {
      mockLogger.warn.mockClear();

      new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      expect(mockLogger.warn).not.toHaveBeenCalled();
    });

    it('should default to production environment', () => {
      expect(() => {
        new ApiClient({
          serverUrl: 'http://api.example.com',
        });
      }).toThrow('HTTPS is required for production API connections');
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
    mockCache.get.mockReturnValue(null);
  });

  describe('healthCheck', () => {
    it('should successfully check health', async () => {
      const mockResponse = {
        status: 'healthy',
        version: '1.0.0',
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      );

      const result = await apiClient.healthCheck();

      expect(result).toEqual(mockResponse);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/health',
        expect.objectContaining({
          headers: {
            'Content-Type': 'application/json',
          },
        })
      );
    });

    it('should handle health check errors', async () => {
      mockFetch.mockImplementation(async () =>
        new Response('Internal Server Error', {
          status: 500,
          statusText: 'Internal Server Error'
        })
      );

      await expect(apiClient.healthCheck()).rejects.toThrow('API request failed: 500 Internal Server Error');
    });
  });

  describe('scoreNotes', () => {
    const mockRequest = {
      notes: [
        {
          noteId: 1,
          noteAuthorParticipantId: 'participant-1',
          createdAtMillis: Date.now(),
          tweetId: 123456,
          summary: 'Test note 1',
          classification: 'NOT_MISLEADING'
        },
        {
          noteId: 2,
          noteAuthorParticipantId: 'participant-2',
          createdAtMillis: Date.now(),
          tweetId: 123457,
          summary: 'Test note 2',
          classification: 'MISINFORMED_OR_POTENTIALLY_MISLEADING'
        },
      ],
      ratings: [],
      enrollment: [],
    };

    const mockResponse = {
      scored_notes: [],
      helpful_scores: [],
      auxiliary_info: [],
    };

    it('should successfully score notes', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      );

      const result = await apiClient.scoreNotes(mockRequest);

      expect(result).toEqual(mockResponse);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/scoring/score',
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(mockRequest),
        })
      );
    });


    it('should handle scoring errors', async () => {
      const errorMessage = 'Bad request';
      mockFetch.mockImplementation(async () =>
        new Response(errorMessage, {
          status: 400,
          statusText: 'Bad Request'
        })
      );

      await expect(apiClient.scoreNotes(mockRequest)).rejects.toThrow('API request failed: 400 Bad Request');
    });
  });

  describe('getNotes', () => {
    it('should return notes for a message', async () => {
      const mockNotes = [
        { id: 'note-1', content: 'Test note 1', messageId: '123456789012345678' },
        { id: 'note-2', content: 'Test note 2', messageId: '123456789012345678' },
      ];

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockNotes), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      );

      const result = await apiClient.getNotes('123456789012345678');

      expect(result).toEqual(mockNotes);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/notes/123456789012345678',
        expect.objectContaining({
          headers: {
            'Content-Type': 'application/json',
          },
        })
      );
    });

    it('should handle empty notes', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      );

      const result = await apiClient.getNotes('123456789012345678');

      expect(result).toEqual([]);
    });
  });

  describe('createNote', () => {
    it('should successfully create a note', async () => {
      const request = {
        messageId: '123456789012345678',
        content: 'Test note content',
        authorId: 'user-456',
        authorName: 'testuser',
        communityServerId: 'guild-123',
      };

      const mockCommunityServerResponse = {
        data: {
          type: 'community-servers',
          id: '123e4567-e89b-12d3-a456-426614174000',
          attributes: {
            platform: 'discord',
            platform_id: 'guild-123',
            name: 'Test Guild',
            is_active: true,
          },
        },
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockCommunityServerResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const mockNoteResponse = {
        data: {
          type: 'notes',
          id: '789',
          attributes: {
            author_participant_id: 'user-456',
            community_server_id: '123e4567-e89b-12d3-a456-426614174000',
            summary: 'Test note content',
            classification: 'NOT_MISLEADING',
            status: 'NEEDS_MORE_RATINGS',
            helpfulness_score: 0,
            created_at: '2025-10-31T16:00:00Z',
            updated_at: '2025-10-31T16:00:00Z',
            ratings_count: 0,
            force_published: false,
          },
        },
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockNoteResponse), {
          status: 201,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const result = await apiClient.createNote(request, {
        userId: 'user-123',
        guildId: 'guild-123',
      });

      expect(result).toEqual({
        id: '789',
        messageId: '123456789012345678',
        authorId: 'user-456',
        content: 'Test note content',
        createdAt: new Date('2025-10-31T16:00:00Z').getTime(),
        helpfulCount: 0,
        notHelpfulCount: 0,
      });

      expect(mockFetch).toHaveBeenNthCalledWith(
        2,
        'http://localhost:8000/api/v2/notes',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );

      const fetchCall = mockFetch.mock.calls[1];
      const fetchInit = fetchCall?.[1] as RequestInit | undefined;
      expect(fetchInit).toBeDefined();
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);
      expect(sentBody.data.type).toBe('notes');
      expect(sentBody.data.attributes.author_participant_id).toBe(request.authorId);
      expect(sentBody.data.attributes.summary).toBe(request.content);
      expect(sentBody.data.attributes.classification).toBe('NOT_MISLEADING');
    });
  });

  describe('rateNote', () => {
    it('should successfully rate a note as helpful', async () => {
      const request = {
        noteId: '550e8400-e29b-41d4-a716-446655440000',
        userId: 'user-456',
        helpful: true,
      };

      const mockJsonApiResponse = {
        data: {
          type: 'ratings',
          id: '1',
          attributes: {
            note_id: '550e8400-e29b-41d4-a716-446655440000',
            rater_participant_id: 'user-456',
            helpfulness_level: 'HELPFUL',
            created_at: '2025-10-23T12:00:00Z',
            updated_at: '2025-10-23T12:00:00Z',
          },
        },
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 201,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const result = await apiClient.rateNote(request);

      expect(result).toEqual({
        noteId: '550e8400-e29b-41d4-a716-446655440000',
        userId: 'user-456',
        helpful: true,
        createdAt: new Date('2025-10-23T12:00:00Z').getTime(),
      });

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/ratings',
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
        })
      );

      const fetchCall = mockFetch.mock.calls[0];
      const fetchInit = fetchCall?.[1] as RequestInit | undefined;
      expect(fetchInit).toBeDefined();
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);
      expect(sentBody).toEqual({
        data: {
          type: 'ratings',
          attributes: {
            note_id: '550e8400-e29b-41d4-a716-446655440000',
            rater_participant_id: 'user-456',
            helpfulness_level: 'HELPFUL',
          },
        },
      });
    });

    it('should successfully rate a note as not helpful', async () => {
      const request = {
        noteId: '660e8400-e29b-41d4-a716-446655440001',
        userId: 'user-789',
        helpful: false,
      };

      const mockJsonApiResponse = {
        data: {
          type: 'ratings',
          id: '2',
          attributes: {
            note_id: '660e8400-e29b-41d4-a716-446655440001',
            rater_participant_id: 'user-789',
            helpfulness_level: 'NOT_HELPFUL',
            created_at: '2025-10-23T13:00:00Z',
            updated_at: '2025-10-23T13:00:00Z',
          },
        },
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 201,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const result = await apiClient.rateNote(request);

      expect(result).toEqual({
        noteId: '660e8400-e29b-41d4-a716-446655440001',
        userId: 'user-789',
        helpful: false,
        createdAt: new Date('2025-10-23T13:00:00Z').getTime(),
      });

      const fetchCall = mockFetch.mock.calls[0];
      const fetchInit = fetchCall?.[1] as RequestInit | undefined;
      expect(fetchInit).toBeDefined();
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);
      expect(sentBody).toEqual({
        data: {
          type: 'ratings',
          attributes: {
            note_id: '660e8400-e29b-41d4-a716-446655440001',
            rater_participant_id: 'user-789',
            helpfulness_level: 'NOT_HELPFUL',
          },
        },
      });
    });
  });

  describe('updateRating', () => {
    it('should successfully update a rating to helpful', async () => {
      const ratingId = '1';
      const helpful = true;

      const mockJsonApiResponse = {
        data: {
          type: 'ratings',
          id: '1',
          attributes: {
            note_id: '123',
            rater_participant_id: 'user-456',
            helpfulness_level: 'HELPFUL',
            created_at: '2025-10-23T12:00:00Z',
            updated_at: '2025-10-24T12:00:00Z',
          },
        },
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const result = await apiClient.updateRating(ratingId, helpful);

      expect(result).toEqual({
        noteId: '123',
        userId: 'user-456',
        helpful: true,
        createdAt: new Date('2025-10-23T12:00:00Z').getTime(),
      });

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/ratings/1',
        expect.objectContaining({
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
        })
      );

      const fetchCall = mockFetch.mock.calls[0];
      const fetchInit = fetchCall?.[1] as RequestInit | undefined;
      expect(fetchInit).toBeDefined();
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);
      expect(sentBody).toEqual({
        data: {
          type: 'ratings',
          id: '1',
          attributes: {
            helpfulness_level: 'HELPFUL',
          },
        },
      });
    });

    it('should successfully update a rating to not helpful', async () => {
      const ratingId = '2';
      const helpful = false;

      const mockJsonApiResponse = {
        data: {
          type: 'ratings',
          id: '2',
          attributes: {
            note_id: '456',
            rater_participant_id: 'user-789',
            helpfulness_level: 'NOT_HELPFUL',
            created_at: '2025-10-23T13:00:00Z',
            updated_at: '2025-10-24T13:00:00Z',
          },
        },
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const result = await apiClient.updateRating(ratingId, helpful);

      expect(result).toEqual({
        noteId: '456',
        userId: 'user-789',
        helpful: false,
        createdAt: new Date('2025-10-23T13:00:00Z').getTime(),
      });
    });
  });

  describe('getRatingsForNote', () => {
    it('should successfully get ratings for a note', async () => {
      const noteId = '123';

      const mockJsonApiResponse = {
        data: [
          {
            type: 'ratings',
            id: '1',
            attributes: {
              note_id: '123',
              rater_participant_id: 'user-456',
              helpfulness_level: 'HELPFUL',
              created_at: '2025-10-23T12:00:00Z',
              updated_at: '2025-10-23T12:00:00Z',
            },
          },
          {
            type: 'ratings',
            id: '2',
            attributes: {
              note_id: '123',
              rater_participant_id: 'user-789',
              helpfulness_level: 'NOT_HELPFUL',
              created_at: '2025-10-23T13:00:00Z',
              updated_at: '2025-10-23T13:00:00Z',
            },
          },
        ],
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const result = await apiClient.getRatingsForNote(noteId);

      expect(result).toEqual([
        {
          id: '1',
          note_id: '123',
          rater_participant_id: 'user-456',
          helpfulness_level: 'HELPFUL',
          created_at: '2025-10-23T12:00:00Z',
          updated_at: '2025-10-23T12:00:00Z',
        },
        {
          id: '2',
          note_id: '123',
          rater_participant_id: 'user-789',
          helpfulness_level: 'NOT_HELPFUL',
          created_at: '2025-10-23T13:00:00Z',
          updated_at: '2025-10-23T13:00:00Z',
        },
      ]);

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/notes/123/ratings',
        expect.objectContaining({
          headers: {
            'Content-Type': 'application/json',
          },
        })
      );
    });

    it('should return empty array when note has no ratings', async () => {
      const noteId = '456';

      const mockJsonApiResponse = {
        data: [],
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const result = await apiClient.getRatingsForNote(noteId);

      expect(result).toEqual([]);
    });
  });

  describe('requestNote', () => {
    it('should successfully request a note', async () => {
      const request = {
        messageId: '123456789012345678',
        userId: 'user-456',
        community_server_id: 'guild-123',
        reason: 'Need clarification',
      };

      const mockJsonApiResponse = {
        data: {
          type: 'requests',
          id: 'req-1',
          attributes: {
            request_id: 'discord-123456789012345678-1234567890',
            requested_by: 'user-456',
            status: 'PENDING',
          },
        },
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 201,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const result = await apiClient.requestNote(request);

      expect(result).toBeUndefined();
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/requests',
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
        })
      );

      const fetchCall = mockFetch.mock.calls[0];
      const fetchInit = fetchCall?.[1] as RequestInit | undefined;
      expect(fetchInit).toBeDefined();
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);

      expect(sentBody.data.type).toBe('requests');
      expect(sentBody.data.attributes.request_id).toMatch(/^discord-123456789012345678-\d+$/);
      expect(sentBody.data.attributes.platform_message_id).toBe('123456789012345678');
      expect(sentBody.data.attributes.requested_by).toBe('user-456');
    });

    it('should request a note without a reason', async () => {
      const request = {
        messageId: '123456789012345678',
        userId: 'user-456',
        community_server_id: 'guild-123',
      };

      const mockJsonApiResponse = {
        data: {
          type: 'requests',
          id: 'req-1',
          attributes: {
            request_id: 'discord-123456789012345678-1234567890',
            requested_by: 'user-456',
            status: 'PENDING',
          },
        },
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 201,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const result = await apiClient.requestNote(request);
      expect(result).toBeUndefined();
    });
  });

  describe('Security Headers', () => {
    const TEST_INTERNAL_SECRET = 'internal-service-secret-1234567890';
    const TEST_USER_ID = '123456789012345678';
    const TEST_GUILD_ID = '987654321098765432';

    describe('X-Internal-Auth Header', () => {
      it('should send X-Internal-Auth header when internalServiceSecret is configured', async () => {
        const client = new ApiClient({
          serverUrl: 'http://localhost:8000',
          environment: 'development',
          internalServiceSecret: TEST_INTERNAL_SECRET,
        });

        const mockResponse = { status: 'healthy', version: '1.0.0' };
        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(mockResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
          })
        );

        await client.healthCheck();

        expect(mockFetch).toHaveBeenCalledWith(
          'http://localhost:8000/health',
          expect.objectContaining({
            headers: expect.objectContaining({
              'X-Internal-Auth': TEST_INTERNAL_SECRET,
            }),
          })
        );
      });

      it('should NOT send X-Internal-Auth header when internalServiceSecret is not configured', async () => {
        const client = new ApiClient({
          serverUrl: 'http://localhost:8000',
          environment: 'development',
        });

        const mockResponse = { status: 'healthy', version: '1.0.0' };
        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(mockResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
          })
        );

        await client.healthCheck();

        const fetchCall = mockFetch.mock.calls[0];
        const fetchInit = fetchCall?.[1] as RequestInit | undefined;
        const headers = fetchInit?.headers as Record<string, string> | undefined;

        expect(headers?.['X-Internal-Auth']).toBeUndefined();
      });
    });

    describe('X-Discord-Claims JWT Header', () => {
      it('should NOT send X-Discord-Claims header when no user context is provided', async () => {
        const client = new ApiClient({
          serverUrl: 'http://localhost:8000',
          environment: 'development',
        });

        const mockResponse = { status: 'healthy', version: '1.0.0' };
        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(mockResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
          })
        );

        await client.healthCheck();

        const fetchCall = mockFetch.mock.calls[0];
        const fetchInit = fetchCall?.[1] as RequestInit | undefined;
        const headers = fetchInit?.headers as Record<string, string> | undefined;

        expect(headers?.['X-Discord-Claims']).toBeUndefined();
      });

      it('should NOT send X-Discord-Claims header when createDiscordClaimsToken returns null (JWT secret not configured)', async () => {
        const client = new ApiClient({
          serverUrl: 'http://localhost:8000',
          environment: 'development',
        });

        const mockJsonApiResponse = {
          data: [],
          jsonapi: { version: '1.1' },
          meta: { count: 0 },
        };
        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(mockJsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' }
          })
        );

        const userContext = {
          userId: TEST_USER_ID,
          guildId: TEST_GUILD_ID,
          hasManageServer: true,
        };

        await client.listRequests({}, userContext);

        const fetchCall = mockFetch.mock.calls[0];
        const fetchInit = fetchCall?.[1] as RequestInit | undefined;
        const headers = fetchInit?.headers as Record<string, string> | undefined;

        expect(headers?.['X-Discord-Claims']).toBeUndefined();
      });

      it('should send profile headers when user context is provided', async () => {
        const client = new ApiClient({
          serverUrl: 'http://localhost:8000',
          environment: 'development',
        });

        const mockJsonApiResponse = {
          data: [],
          jsonapi: { version: '1.1' },
          meta: { count: 0 },
        };
        mockFetch.mockResolvedValueOnce(
          new Response(JSON.stringify(mockJsonApiResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/vnd.api+json' }
          })
        );

        const userContext = {
          userId: TEST_USER_ID,
          username: 'testuser',
          displayName: 'Test User',
          guildId: TEST_GUILD_ID,
          hasManageServer: true,
        };

        await client.listRequests({}, userContext);

        const fetchCall = mockFetch.mock.calls[0];
        const fetchInit = fetchCall?.[1] as RequestInit | undefined;
        const headers = fetchInit?.headers as Record<string, string> | undefined;

        expect(headers?.['X-Discord-User-Id']).toBe(TEST_USER_ID);
        expect(headers?.['X-Discord-Username']).toBe('testuser');
        expect(headers?.['X-Discord-Display-Name']).toBe('Test User');
        expect(headers?.['X-Guild-Id']).toBe(TEST_GUILD_ID);
        expect(headers?.['X-Discord-Has-Manage-Server']).toBe('true');
      });
    });
  });
});
