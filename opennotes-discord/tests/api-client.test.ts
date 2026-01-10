import { jest } from '@jest/globals';
import { loggerFactory, cacheFactory } from '@opennotes/test-utils';

const mockFetch = jest.fn<typeof fetch>();
global.fetch = mockFetch;

const mockLogger = loggerFactory.build();

const mockCache = cacheFactory.build();

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
    mockCache.get.mockResolvedValue(null);
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
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
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

    const mockJsonApiResponse = {
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

    it('should successfully score notes', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      );

      const result = await apiClient.scoreNotes(mockRequest);

      expect(result).toEqual(mockJsonApiResponse);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/scoring/score',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
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
    it('should return raw JSONAPI response for notes using v2 endpoint with platform_message_id filter', async () => {
      const mockJsonApiResponse = {
        data: [
          {
            type: 'notes',
            id: 'note-uuid-1',
            attributes: {
              summary: 'Test note 1',
              classification: 'NOT_MISLEADING',
              status: 'published',
              helpfulness_score: 0.8,
              author_participant_id: 'participant-1',
              community_server_id: 'community-uuid',
              channel_id: null,
              request_id: 'request-1',
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
              summary: 'Test note 2',
              classification: 'MISINFORMED_OR_POTENTIALLY_MISLEADING',
              status: 'published',
              helpfulness_score: 0.6,
              author_participant_id: 'participant-2',
              community_server_id: 'community-uuid',
              channel_id: 'channel-1',
              request_id: 'request-2',
              ratings_count: 3,
              force_published: false,
              force_published_at: null,
              created_at: '2024-01-15T11:00:00Z',
              updated_at: '2024-01-15T12:00:00Z',
            },
          },
        ],
        jsonapi: { version: '1.1' },
        links: {},
        meta: { count: 2 },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const result = await apiClient.getNotes('123456789012345678');

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/notes?filter%5Bplatform_message_id%5D=123456789012345678',
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );

      expect(result.jsonapi.version).toBe('1.1');
      expect(result.meta?.count).toBe(2);
      expect(result.data).toHaveLength(2);
      expect(result.data[0].type).toBe('notes');
      expect(result.data[0].id).toBe('note-uuid-1');
      expect(result.data[0].attributes.summary).toBe('Test note 1');
      expect(result.data[0].attributes.classification).toBe('NOT_MISLEADING');
      expect(result.data[0].attributes.author_participant_id).toBe('participant-1');
      expect(result.data[0].attributes.ratings_count).toBe(5);
      expect(result.data[1].type).toBe('notes');
      expect(result.data[1].id).toBe('note-uuid-2');
      expect(result.data[1].attributes.summary).toBe('Test note 2');
      expect(result.data[1].attributes.classification).toBe('MISINFORMED_OR_POTENTIALLY_MISLEADING');
      expect(result.data[1].attributes.author_participant_id).toBe('participant-2');
      expect(result.data[1].attributes.ratings_count).toBe(3);
    });

    it('should return empty data array in JSONAPI response when no notes exist', async () => {
      const mockEmptyResponse = {
        data: [],
        jsonapi: { version: '1.1' },
        links: {},
        meta: { count: 0 },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockEmptyResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const result = await apiClient.getNotes('123456789012345678');

      expect(result.data).toEqual([]);
      expect(result.jsonapi.version).toBe('1.1');
      expect(result.meta?.count).toBe(0);
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
            platform_community_server_id: 'guild-123',
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

      expect(result.data.id).toBe('1');
      expect(result.data.type).toBe('ratings');
      expect(result.data.attributes.note_id).toBe('550e8400-e29b-41d4-a716-446655440000');
      expect(result.data.attributes.rater_participant_id).toBe('user-456');
      expect(result.data.attributes.helpfulness_level).toBe('HELPFUL');

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/ratings',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
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

      expect(result.data.id).toBe('2');
      expect(result.data.type).toBe('ratings');
      expect(result.data.attributes.note_id).toBe('660e8400-e29b-41d4-a716-446655440001');
      expect(result.data.attributes.rater_participant_id).toBe('user-789');
      expect(result.data.attributes.helpfulness_level).toBe('NOT_HELPFUL');

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

      expect(result.data.id).toBe('1');
      expect(result.data.type).toBe('ratings');
      expect(result.data.attributes.note_id).toBe('123');
      expect(result.data.attributes.rater_participant_id).toBe('user-456');
      expect(result.data.attributes.helpfulness_level).toBe('HELPFUL');

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/ratings/1',
        expect.objectContaining({
          method: 'PUT',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
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

      expect(result.data.id).toBe('2');
      expect(result.data.type).toBe('ratings');
      expect(result.data.attributes.note_id).toBe('456');
      expect(result.data.attributes.rater_participant_id).toBe('user-789');
      expect(result.data.attributes.helpfulness_level).toBe('NOT_HELPFUL');
    });
  });

  describe('generateAiNote', () => {
    it('should return raw JSONAPI response for AI-generated note', async () => {
      const requestId = 'discord-123456789-1234567890';

      const mockJsonApiResponse = {
        data: {
          type: 'notes',
          id: 'note-uuid-1',
          attributes: {
            summary: 'AI-generated summary',
            classification: 'NOT_MISLEADING',
            status: 'draft',
            helpfulness_score: 0,
            author_participant_id: 'ai-participant',
            community_server_id: 'community-uuid',
            channel_id: null,
            request_id: requestId,
            ratings_count: 0,
            force_published: false,
            force_published_at: null,
            created_at: '2024-01-15T10:00:00Z',
            updated_at: null,
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

      const result = await apiClient.generateAiNote(requestId);

      expect(mockFetch).toHaveBeenCalledWith(
        `http://localhost:8000/api/v2/requests/${encodeURIComponent(requestId)}/ai-notes`,
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );

      expect(result.jsonapi.version).toBe('1.1');
      expect(result.data.type).toBe('notes');
      expect(result.data.id).toBe('note-uuid-1');
      expect(result.data.attributes.summary).toBe('AI-generated summary');
      expect(result.data.attributes.classification).toBe('NOT_MISLEADING');
      expect(result.data.attributes.request_id).toBe(requestId);
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

      expect(result.data).toHaveLength(2);
      expect(result.data[0].id).toBe('1');
      expect(result.data[0].type).toBe('ratings');
      expect(result.data[0].attributes.note_id).toBe('123');
      expect(result.data[0].attributes.rater_participant_id).toBe('user-456');
      expect(result.data[0].attributes.helpfulness_level).toBe('HELPFUL');
      expect(result.data[1].id).toBe('2');
      expect(result.data[1].attributes.helpfulness_level).toBe('NOT_HELPFUL');

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/notes/123/ratings',
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
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

      expect(result.data).toEqual([]);
    });
  });

  describe('listNotesRatedByUser', () => {
    it('should return raw JSONAPI response with pagination for notes rated by user', async () => {
      const mockJsonApiResponse = {
        data: [
          {
            type: 'notes',
            id: 'note-uuid-1',
            attributes: {
              summary: 'First rated note',
              classification: 'NOT_MISLEADING',
              status: 'published',
              helpfulness_score: 0.8,
              author_participant_id: 'author-1',
              community_server_id: 'community-uuid',
              channel_id: null,
              request_id: 'request-1',
              ratings_count: 10,
              force_published: false,
              force_published_at: null,
              created_at: '2024-01-15T10:00:00Z',
              updated_at: null,
            },
          },
        ],
        jsonapi: { version: '1.1' },
        meta: { count: 1 },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const result = await apiClient.listNotesRatedByUser(
        'rater-participant-1',
        1,
        20,
        'community-uuid'
      );

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v2/notes?'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );

      const url = mockFetch.mock.calls[0][0] as string;
      expect(url).toContain('filter%5Brated_by_participant_id%5D=rater-participant-1');
      expect(url).toContain('filter%5Bcommunity_server_id%5D=community-uuid');
      expect(url).toContain('page%5Bnumber%5D=1');
      expect(url).toContain('page%5Bsize%5D=20');

      expect(result.jsonapi.version).toBe('1.1');
      expect(result.data).toHaveLength(1);
      expect(result.data[0].type).toBe('notes');
      expect(result.data[0].id).toBe('note-uuid-1');
      expect(result.data[0].attributes.summary).toBe('First rated note');
      expect(result.total).toBe(1);
      expect(result.page).toBe(1);
      expect(result.size).toBe(20);
    });

    it('should return empty data array with pagination when no notes rated', async () => {
      const mockEmptyResponse = {
        data: [],
        jsonapi: { version: '1.1' },
        meta: { count: 0 },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockEmptyResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' }
        })
      );

      const result = await apiClient.listNotesRatedByUser(
        'rater-participant-1',
        1,
        20,
        'community-uuid'
      );

      expect(result.data).toEqual([]);
      expect(result.total).toBe(0);
      expect(result.page).toBe(1);
      expect(result.size).toBe(20);
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
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
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

  describe('checkPreviouslySeen', () => {
    it('should return raw JSONAPI response structure', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      const mockJsonApiResponse = {
        data: {
          type: 'previously-seen-check-results',
          id: 'check-123',
          attributes: {
            should_auto_publish: true,
            should_auto_request: false,
            autopublish_threshold: 0.9,
            autorequest_threshold: 0.75,
            matches: [
              {
                id: 'match-1',
                community_server_id: 'community-uuid-1',
                original_message_id: 'msg-123',
                published_note_id: 'note-456',
                embedding_provider: 'openai',
                embedding_model: 'text-embedding-3-small',
                extra_metadata: { key: 'value' },
                created_at: '2024-01-15T10:00:00Z',
                similarity_score: 0.95,
              },
            ],
            top_match: {
              id: 'match-1',
              community_server_id: 'community-uuid-1',
              original_message_id: 'msg-123',
              published_note_id: 'note-456',
              embedding_provider: 'openai',
              embedding_model: 'text-embedding-3-small',
              extra_metadata: { key: 'value' },
              created_at: '2024-01-15T10:00:00Z',
              similarity_score: 0.95,
            },
          },
        },
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' },
        })
      );

      const result = await client.checkPreviouslySeen('test message', 'guild-123', 'channel-456');

      expect(result.data.type).toBe('previously-seen-check-results');
      expect(result.data.id).toBe('check-123');
      expect(result.data.attributes.should_auto_publish).toBe(true);
      expect(result.data.attributes.should_auto_request).toBe(false);
      expect(result.data.attributes.autopublish_threshold).toBe(0.9);
      expect(result.data.attributes.autorequest_threshold).toBe(0.75);
      expect(result.data.attributes.matches).toHaveLength(1);
      expect(result.data.attributes.matches[0].similarity_score).toBe(0.95);
      expect(result.data.attributes.top_match?.published_note_id).toBe('note-456');
      expect(result.jsonapi.version).toBe('1.1');
    });

    it('should send correct JSONAPI request body', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      const mockJsonApiResponse = {
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

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' },
        })
      );

      await client.checkPreviouslySeen('test message', 'guild-123', 'channel-456');

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/previously-seen-messages/check',
        expect.objectContaining({
          method: 'POST',
        })
      );

      const fetchCall = mockFetch.mock.calls[0];
      const fetchInit = fetchCall?.[1] as RequestInit | undefined;
      expect(fetchInit).toBeDefined();
      const sentBody = JSON.parse((fetchInit as RequestInit & { body: string }).body);

      expect(sentBody).toEqual({
        data: {
          type: 'previously-seen-check',
          attributes: {
            message_text: 'test message',
            guild_id: 'guild-123',
            channel_id: 'channel-456',
          },
        },
      });
    });

    it('should return empty matches when no similar messages found', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      const mockJsonApiResponse = {
        data: {
          type: 'previously-seen-check-results',
          id: 'check-456',
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

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' },
        })
      );

      const result = await client.checkPreviouslySeen('new message', 'guild-123', 'channel-456');

      expect(result.data.attributes.should_auto_publish).toBe(false);
      expect(result.data.attributes.should_auto_request).toBe(false);
      expect(result.data.attributes.matches).toEqual([]);
      expect(result.data.attributes.top_match).toBeNull();
    });
  });

  describe('getLatestScan', () => {
    const TEST_COMMUNITY_SERVER_UUID = '11111111-1111-1111-1111-111111111111';
    const TEST_SCAN_ID = '22222222-2222-2222-2222-222222222222';

    it('should fetch the latest scan for a community server', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      const mockJsonApiResponse = {
        data: {
          type: 'bulk-scans',
          id: TEST_SCAN_ID,
          attributes: {
            status: 'completed',
            initiated_at: '2024-01-15T10:00:00Z',
            completed_at: '2024-01-15T10:05:00Z',
            messages_scanned: 100,
            messages_flagged: 5,
            scan_window_days: 7,
          },
        },
        included: [
          {
            type: 'flagged-messages',
            id: 'msg-1',
            attributes: {
              channel_id: 'ch-1',
              content: 'Flagged content',
              author_id: 'author-1',
              timestamp: '2024-01-15T09:00:00Z',
              matches: [
                {
                  scan_type: 'similarity',
                  score: 0.95,
                  matched_claim: 'Test claim',
                  matched_source: 'snopes',
                },
              ],
            },
          },
        ],
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' },
        })
      );

      const result = await client.getLatestScan(TEST_COMMUNITY_SERVER_UUID);

      expect(result.data.id).toBe(TEST_SCAN_ID);
      expect(result.data.attributes.status).toBe('completed');
      expect(result.data.attributes.messages_scanned).toBe(100);
      expect(result.included).toHaveLength(1);
      expect(result.included![0].id).toBe('msg-1');
      const firstMatch = result.included![0].attributes.matches![0];
      expect(firstMatch.scan_type).toBe('similarity');
      if (firstMatch.scan_type === 'similarity') {
        expect(firstMatch.score).toBe(0.95);
      }
    });

    it('should call the correct endpoint', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      const mockJsonApiResponse = {
        data: {
          type: 'bulk-scans',
          id: TEST_SCAN_ID,
          attributes: {
            status: 'pending',
            initiated_at: '2024-01-15T10:00:00Z',
            completed_at: null,
            messages_scanned: 0,
            messages_flagged: 0,
            scan_window_days: 7,
          },
        },
        included: [],
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' },
        })
      );

      await client.getLatestScan(TEST_COMMUNITY_SERVER_UUID);

      expect(mockFetch).toHaveBeenCalledWith(
        `http://localhost:8000/api/v2/bulk-scans/communities/${TEST_COMMUNITY_SERVER_UUID}/latest`,
        expect.any(Object)
      );
    });

    it('should throw ApiError when no scans exist (404)', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
        retryAttempts: 1,
      });

      const errorResponse = {
        errors: [
          {
            status: '404',
            title: 'Not Found',
            detail: 'No scans found for this community',
          },
        ],
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(errorResponse), {
          status: 404,
          statusText: 'Not Found',
          headers: { 'Content-Type': 'application/vnd.api+json' },
        })
      );

      await expect(client.getLatestScan(TEST_COMMUNITY_SERVER_UUID)).rejects.toThrow();
    });

    it('should return pending scan without flagged messages', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      const mockJsonApiResponse = {
        data: {
          type: 'bulk-scans',
          id: TEST_SCAN_ID,
          attributes: {
            status: 'pending',
            initiated_at: '2024-01-15T10:00:00Z',
            completed_at: null,
            messages_scanned: 0,
            messages_flagged: 0,
            scan_window_days: 14,
          },
        },
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' },
        })
      );

      const result = await client.getLatestScan(TEST_COMMUNITY_SERVER_UUID);

      expect(result.data.attributes.status).toBe('pending');
      expect(result.included).toBeUndefined();
    });

    it('should return in_progress scan', async () => {
      const client = new ApiClient({
        serverUrl: 'http://localhost:8000',
        environment: 'development',
      });

      const mockJsonApiResponse = {
        data: {
          type: 'bulk-scans',
          id: TEST_SCAN_ID,
          attributes: {
            status: 'in_progress',
            initiated_at: '2024-01-15T10:00:00Z',
            completed_at: null,
            messages_scanned: 50,
            messages_flagged: 2,
            scan_window_days: 7,
          },
        },
        jsonapi: { version: '1.1' },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockJsonApiResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/vnd.api+json' },
        })
      );

      const result = await client.getLatestScan(TEST_COMMUNITY_SERVER_UUID);

      expect(result.data.attributes.status).toBe('in_progress');
      expect(result.data.attributes.messages_scanned).toBe(50);
    });
  });
});
