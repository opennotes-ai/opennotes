import { jest } from '@jest/globals';
import jwtLib from 'jsonwebtoken';
import { loggerFactory, cacheFactory } from '@opennotes/test-utils';

const TEST_JWT_SECRET = 'jwt-secret-key-1234567890abcdef';
const TEST_USER_ID = '123456789012345678';
const TEST_GUILD_ID = '987654321098765432';

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
    jwtSecretKey: TEST_JWT_SECRET,
  },
}));

function createTestToken(userId: string, guildId: string, hasManageServer: boolean): string {
  const now = Math.floor(Date.now() / 1000);
  return jwtLib.sign(
    {
      sub: userId,
      user_id: userId,
      guild_id: guildId,
      has_manage_server: hasManageServer,
      iat: now,
      exp: now + 300,
      type: 'discord_claims',
    },
    TEST_JWT_SECRET,
    { algorithm: 'HS256' }
  );
}

jest.unstable_mockModule('../src/utils/discord-claims.js', () => ({
  createDiscordClaimsToken: (userId: string, guildId: string, hasManageServer: boolean) => {
    return createTestToken(userId, guildId, hasManageServer);
  },
}));

jest.unstable_mockModule('../src/utils/gcp-auth.js', () => ({
  getIdentityToken: jest.fn<() => Promise<string | null>>().mockResolvedValue(null),
  isRunningOnGCP: jest.fn<() => Promise<boolean>>().mockResolvedValue(false),
}));

const { ApiClient } = await import('../src/lib/api-client.js');

describe('ApiClient X-Discord-Claims JWT Header', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCache.get.mockResolvedValue(null);
  });

  it('should send X-Discord-Claims JWT header when user context is provided and JWT secret is configured', async () => {
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

    expect(headers?.['X-Discord-Claims']).toBeDefined();

    const claimsToken = headers?.['X-Discord-Claims'];
    const decoded = jwtLib.decode(claimsToken!) as jwtLib.JwtPayload;

    expect(decoded).not.toBeNull();
    expect(decoded.sub).toBe(TEST_USER_ID);
    expect(decoded.user_id).toBe(TEST_USER_ID);
    expect(decoded.guild_id).toBe(TEST_GUILD_ID);
    expect(decoded.has_manage_server).toBe(true);
    expect(decoded.type).toBe('discord_claims');
  });

  it('should include correct claims matching user context in X-Discord-Claims JWT', async () => {
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
      userId: 'user-abc-123',
      guildId: 'guild-xyz-456',
      hasManageServer: false,
      username: 'testuser',
      displayName: 'Test User',
    };

    await client.listRequests({}, userContext);

    const fetchCall = mockFetch.mock.calls[0];
    const fetchInit = fetchCall?.[1] as RequestInit | undefined;
    const headers = fetchInit?.headers as Record<string, string> | undefined;

    const claimsToken = headers?.['X-Discord-Claims'];
    expect(claimsToken).toBeDefined();

    const decoded = jwtLib.decode(claimsToken!) as jwtLib.JwtPayload;

    expect(decoded.sub).toBe('user-abc-123');
    expect(decoded.user_id).toBe('user-abc-123');
    expect(decoded.guild_id).toBe('guild-xyz-456');
    expect(decoded.has_manage_server).toBe(false);
    expect(decoded.type).toBe('discord_claims');
    expect(decoded.iat).toBeDefined();
    expect(decoded.exp).toBeDefined();

    const expiryDiff = decoded.exp! - decoded.iat!;
    expect(expiryDiff).toBe(300);
  });

  it('should send profile headers alongside X-Discord-Claims', async () => {
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
    expect(headers?.['X-Discord-Claims']).toBeDefined();
  });

  it('should create JWT that can be verified with the secret key', async () => {
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
    const claimsToken = headers?.['X-Discord-Claims'];

    expect(claimsToken).toBeDefined();

    expect(() => {
      jwtLib.verify(claimsToken!, TEST_JWT_SECRET, { algorithms: ['HS256'] });
    }).not.toThrow();

    const verified = jwtLib.verify(claimsToken!, TEST_JWT_SECRET, { algorithms: ['HS256'] }) as jwtLib.JwtPayload;
    expect(verified.sub).toBe(TEST_USER_ID);
    expect(verified.user_id).toBe(TEST_USER_ID);
    expect(verified.guild_id).toBe(TEST_GUILD_ID);
    expect(verified.has_manage_server).toBe(true);
  });

  it('should use HS256 algorithm for signing', async () => {
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
      hasManageServer: false,
    };

    await client.listRequests({}, userContext);

    const fetchCall = mockFetch.mock.calls[0];
    const fetchInit = fetchCall?.[1] as RequestInit | undefined;
    const headers = fetchInit?.headers as Record<string, string> | undefined;
    const claimsToken = headers?.['X-Discord-Claims'];

    const header = jwtLib.decode(claimsToken!, { complete: true })?.header;
    expect(header?.alg).toBe('HS256');
  });
});
