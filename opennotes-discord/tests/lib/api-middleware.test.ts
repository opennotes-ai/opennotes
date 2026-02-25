import { jest } from '@jest/globals';
import { loggerFactory } from '@opennotes/test-utils';

const mockLogger = loggerFactory.build();

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const mockIsRunningOnGCP = jest.fn<() => Promise<boolean>>();
const mockGetIdentityToken = jest.fn<() => Promise<string | null>>();

jest.unstable_mockModule('../../src/utils/gcp-auth.js', () => ({
  isRunningOnGCP: mockIsRunningOnGCP,
  getIdentityToken: mockGetIdentityToken,
}));

const mockCreateDiscordClaimsToken = jest.fn<() => string | null>();

jest.unstable_mockModule('../../src/utils/discord-claims.js', () => ({
  createDiscordClaimsToken: mockCreateDiscordClaimsToken,
}));

const {
  createAuthMiddleware,
  createTracingMiddleware,
  createLoggingMiddleware,
  createResponseSizeMiddleware,
  createRetryFetch,
  validateHttps,
  buildProfileHeaders,
  initGCPDetection,
  resetGCPState,
} = await import('../../src/lib/api-middleware.js');

const { ApiError } = await import('../../src/lib/errors.js');

function makeRequest(url = 'https://api.example.com/test', init?: RequestInit): Request {
  return new Request(url, init);
}

function makeResponse(status = 200, body = '{}', headers: Record<string, string> = {}): Response {
  return new Response(body, { status, headers: { 'content-type': 'application/json', ...headers } });
}

describe('createAuthMiddleware', () => {
  beforeEach(() => {
    resetGCPState();
    mockIsRunningOnGCP.mockResolvedValue(false);
    mockGetIdentityToken.mockResolvedValue(null);
  });

  it('sets X-API-Key header when apiKey is provided', async () => {
    const middleware = createAuthMiddleware({
      baseUrl: 'https://api.example.com',
      apiKey: 'test-key',
    });

    const request = makeRequest();
    const result = await middleware.onRequest!({
      request,
      schemaPath: '/test',
      params: {},
      id: '1',
      options: {} as any,
    });

    expect((result as Request).headers.get('X-API-Key')).toBe('test-key');
  });

  it('sets X-Internal-Auth header when internalServiceSecret is provided', async () => {
    const middleware = createAuthMiddleware({
      baseUrl: 'https://api.example.com',
      internalServiceSecret: 'secret-123',
    });

    const request = makeRequest();
    const result = await middleware.onRequest!({
      request,
      schemaPath: '/test',
      params: {},
      id: '1',
      options: {} as any,
    });

    expect((result as Request).headers.get('X-Internal-Auth')).toBe('secret-123');
  });

  it('sets Authorization header when running on GCP', async () => {
    mockIsRunningOnGCP.mockResolvedValue(true);
    mockGetIdentityToken.mockResolvedValue('gcp-token-xyz');

    resetGCPState();
    initGCPDetection();

    const middleware = createAuthMiddleware({
      baseUrl: 'https://api.example.com',
    });

    const request = makeRequest();
    const result = await middleware.onRequest!({
      request,
      schemaPath: '/test',
      params: {},
      id: '1',
      options: {} as any,
    });

    expect((result as Request).headers.get('Authorization')).toBe('Bearer gcp-token-xyz');
  });

  it('does not set Authorization header when not on GCP', async () => {
    mockIsRunningOnGCP.mockResolvedValue(false);
    resetGCPState();
    initGCPDetection();

    const middleware = createAuthMiddleware({
      baseUrl: 'https://api.example.com',
    });

    const request = makeRequest();
    const result = await middleware.onRequest!({
      request,
      schemaPath: '/test',
      params: {},
      id: '1',
      options: {} as any,
    });

    expect((result as Request).headers.get('Authorization')).toBeNull();
  });
});

describe('initGCPDetection idempotency', () => {
  beforeEach(() => {
    resetGCPState();
    mockIsRunningOnGCP.mockResolvedValue(true);
    mockGetIdentityToken.mockResolvedValue('gcp-token');
  });

  it('only calls isRunningOnGCP once when called multiple times', async () => {
    initGCPDetection();
    initGCPDetection();
    initGCPDetection();

    const middleware = createAuthMiddleware({ baseUrl: 'https://api.example.com' });
    await middleware.onRequest!({
      request: makeRequest(),
      schemaPath: '/test',
      params: {},
      id: '1',
      options: {} as any,
    });

    expect(mockIsRunningOnGCP).toHaveBeenCalledTimes(1);
  });

  it('does not re-detect after detection has completed', async () => {
    initGCPDetection();

    const middleware = createAuthMiddleware({ baseUrl: 'https://api.example.com' });
    await middleware.onRequest!({
      request: makeRequest(),
      schemaPath: '/test',
      params: {},
      id: '1',
      options: {} as any,
    });

    initGCPDetection();
    expect(mockIsRunningOnGCP).toHaveBeenCalledTimes(1);
  });
});

describe('createTracingMiddleware', () => {
  it('sets X-Request-Id header with nanoid', async () => {
    const middleware = createTracingMiddleware();

    const request = makeRequest();
    const result = await middleware.onRequest!({
      request,
      schemaPath: '/test',
      params: {},
      id: '1',
      options: {} as any,
    });

    const requestId = (result as Request).headers.get('X-Request-Id');
    expect(requestId).toBeTruthy();
    expect(typeof requestId).toBe('string');
    expect(requestId!.length).toBeGreaterThan(0);
  });

  it('generates unique IDs per request', async () => {
    const middleware = createTracingMiddleware();

    const result1 = await middleware.onRequest!({
      request: makeRequest(),
      schemaPath: '/test',
      params: {},
      id: '1',
      options: {} as any,
    });

    const result2 = await middleware.onRequest!({
      request: makeRequest(),
      schemaPath: '/test',
      params: {},
      id: '2',
      options: {} as any,
    });

    expect((result1 as Request).headers.get('X-Request-Id')).not.toBe(
      (result2 as Request).headers.get('X-Request-Id')
    );
  });
});

describe('createLoggingMiddleware', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('logs request on onRequest', async () => {
    const middleware = createLoggingMiddleware();

    await middleware.onRequest!({
      request: makeRequest(),
      schemaPath: '/api/v2/notes',
      params: {},
      id: '1',
      options: {} as any,
    });

    expect(mockLogger.debug).toHaveBeenCalledWith('API request', expect.objectContaining({
      method: 'GET',
      schemaPath: '/api/v2/notes',
    }));
  });

  it('logs success on onResponse with ok status', async () => {
    const middleware = createLoggingMiddleware();

    await middleware.onResponse!({
      request: makeRequest(),
      response: makeResponse(200),
      schemaPath: '/api/v2/notes',
      params: {},
      id: '1',
      options: {} as any,
    });

    expect(mockLogger.debug).toHaveBeenCalledWith('API request successful', expect.objectContaining({
      statusCode: 200,
    }));
  });

  it('logs error on onResponse with non-ok status', async () => {
    const middleware = createLoggingMiddleware();

    await middleware.onResponse!({
      request: makeRequest(),
      response: makeResponse(500),
      schemaPath: '/api/v2/notes',
      params: {},
      id: '1',
      options: {} as any,
    });

    expect(mockLogger.error).toHaveBeenCalledWith('API request failed', expect.objectContaining({
      statusCode: 500,
    }));
  });
});

describe('createResponseSizeMiddleware', () => {
  it('throws ApiError when response exceeds max size', async () => {
    const middleware = createResponseSizeMiddleware({ maxResponseSize: 1000 });

    await expect(
      middleware.onResponse!({
        request: makeRequest(),
        response: makeResponse(200, '{}', { 'content-length': '2000' }),
        schemaPath: '/test',
        params: {},
        id: '1',
        options: {} as any,
      })
    ).rejects.toThrow('Response size 2000 bytes exceeds maximum');
  });

  it('warns when response approaching limit', async () => {
    const middleware = createResponseSizeMiddleware({ maxResponseSize: 1000 });

    await middleware.onResponse!({
      request: makeRequest(),
      response: makeResponse(200, '{}', { 'content-length': '850' }),
      schemaPath: '/test',
      params: {},
      id: '1',
      options: {} as any,
    });

    expect(mockLogger.warn).toHaveBeenCalledWith('Response size approaching limit', expect.objectContaining({
      contentLength: 850,
    }));
  });

  it('passes through when under limit', async () => {
    const middleware = createResponseSizeMiddleware({ maxResponseSize: 1000 });

    const response = makeResponse(200, '{}', { 'content-length': '500' });
    const result = await middleware.onResponse!({
      request: makeRequest(),
      response,
      schemaPath: '/test',
      params: {},
      id: '1',
      options: {} as any,
    });

    expect(result).toBe(response);
  });
});

describe('validateHttps', () => {
  it('throws for non-HTTPS in production', () => {
    expect(() => validateHttps('http://remote.example.com', 'production')).toThrow(
      'HTTPS is required for production API connections'
    );
  });

  it('allows HTTPS in production', () => {
    expect(() => validateHttps('https://api.example.com', 'production')).not.toThrow();
  });

  it('allows localhost HTTP in production', () => {
    expect(() => validateHttps('http://localhost:8000', 'production')).not.toThrow();
  });

  it('allows localhost HTTP in development', () => {
    expect(() => validateHttps('http://localhost:8000', 'development')).not.toThrow();
  });

  it('warns for non-localhost HTTP in development', () => {
    validateHttps('http://remote.example.com', 'development');
    expect(mockLogger.warn).toHaveBeenCalledWith(
      'Non-HTTPS API connection detected in development',
      expect.any(Object)
    );
  });
});

describe('createRetryFetch', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    jest.clearAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('returns response on success', async () => {
    const mockFetch = jest.fn<typeof globalThis.fetch>().mockResolvedValue(makeResponse(200, '{"ok":true}'));
    globalThis.fetch = mockFetch;

    const retryFetch = createRetryFetch({
      retryAttempts: 3,
      retryDelayMs: 10,
      requestTimeout: 5000,
    });

    const response = await retryFetch(makeRequest());
    expect(response.status).toBe(200);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('retries on 5xx errors', async () => {
    const mockFetch = jest.fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(makeResponse(502))
      .mockResolvedValueOnce(makeResponse(200, '{"ok":true}'));
    globalThis.fetch = mockFetch;

    const retryFetch = createRetryFetch({
      retryAttempts: 3,
      retryDelayMs: 10,
      requestTimeout: 5000,
    });

    const response = await retryFetch(makeRequest());
    expect(response.status).toBe(200);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('retries on 429 with Retry-After', async () => {
    const rateLimitResponse = makeResponse(429, '{}', { 'retry-after': '1' });
    const mockFetch = jest.fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(rateLimitResponse)
      .mockResolvedValueOnce(makeResponse(200));
    globalThis.fetch = mockFetch;

    const retryFetch = createRetryFetch({
      retryAttempts: 3,
      retryDelayMs: 10,
      requestTimeout: 5000,
    });

    const response = await retryFetch(makeRequest());
    expect(response.status).toBe(200);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('retries on 408 request timeout', async () => {
    const mockFetch = jest.fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(makeResponse(408))
      .mockResolvedValueOnce(makeResponse(200));
    globalThis.fetch = mockFetch;

    const retryFetch = createRetryFetch({
      retryAttempts: 3,
      retryDelayMs: 10,
      requestTimeout: 5000,
    });

    const response = await retryFetch(makeRequest());
    expect(response.status).toBe(200);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('does not retry on 4xx errors (except 408/429)', async () => {
    const mockFetch = jest.fn<typeof globalThis.fetch>()
      .mockResolvedValue(makeResponse(404));
    globalThis.fetch = mockFetch;

    const retryFetch = createRetryFetch({
      retryAttempts: 3,
      retryDelayMs: 10,
      requestTimeout: 5000,
    });

    const response = await retryFetch(makeRequest());
    expect(response.status).toBe(404);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('throws ApiError after all retries exhausted', async () => {
    const mockFetch = jest.fn<typeof globalThis.fetch>()
      .mockResolvedValue(makeResponse(503));
    globalThis.fetch = mockFetch;

    const retryFetch = createRetryFetch({
      retryAttempts: 2,
      retryDelayMs: 10,
      requestTimeout: 5000,
    });

    const response = await retryFetch(makeRequest());
    expect(response.status).toBe(503);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('throws ApiError on network error after retries', async () => {
    const mockFetch = jest.fn<typeof globalThis.fetch>()
      .mockRejectedValue(new Error('ECONNREFUSED'));
    globalThis.fetch = mockFetch;

    const retryFetch = createRetryFetch({
      retryAttempts: 2,
      retryDelayMs: 10,
      requestTimeout: 5000,
    });

    await expect(retryFetch(makeRequest())).rejects.toThrow('API request failed: ECONNREFUSED');
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});

describe('buildProfileHeaders', () => {
  beforeEach(() => {
    mockCreateDiscordClaimsToken.mockReturnValue(null);
  });

  it('returns empty object when no context', () => {
    expect(buildProfileHeaders()).toEqual({});
  });

  it('sets all profile headers from context', () => {
    mockCreateDiscordClaimsToken.mockReturnValue('jwt-token-123');

    const headers = buildProfileHeaders({
      userId: 'user-1',
      username: 'testuser',
      displayName: 'Test User',
      avatarUrl: 'https://cdn.example.com/avatar.png',
      guildId: 'guild-1',
      channelId: 'channel-1',
      hasManageServer: true,
    });

    expect(headers['X-Discord-User-Id']).toBe('user-1');
    expect(headers['X-Discord-Username']).toBe('testuser');
    expect(headers['X-Discord-Display-Name']).toBe('Test User');
    expect(headers['X-Discord-Avatar-Url']).toBe('https://cdn.example.com/avatar.png');
    expect(headers['X-Guild-Id']).toBe('guild-1');
    expect(headers['X-Channel-Id']).toBe('channel-1');
    expect(headers['X-Discord-Has-Manage-Server']).toBe('true');
    expect(headers['X-Discord-Claims']).toBe('jwt-token-123');
  });

  it('only sets provided fields', () => {
    const headers = buildProfileHeaders({ userId: 'user-1' });

    expect(headers['X-Discord-User-Id']).toBe('user-1');
    expect(headers['X-Discord-Username']).toBeUndefined();
    expect(headers['X-Guild-Id']).toBeUndefined();
  });
});
