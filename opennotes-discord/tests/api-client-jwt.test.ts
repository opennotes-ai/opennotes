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

function createTestToken(
  platform: string,
  scope: string,
  userId: string,
  communityId: string,
  canAdministerCommunity: boolean
): string {
  const now = Math.floor(Date.now() / 1000);
  return jwtLib.sign(
    {
      platform,
      scope,
      sub: userId,
      community_id: communityId,
      can_administer_community: canAdministerCommunity,
      iat: now,
      exp: now + 300,
      type: 'platform_claims',
    },
    TEST_JWT_SECRET,
    { algorithm: 'HS256' }
  );
}

jest.unstable_mockModule('../src/utils/platform-claims.js', () => ({
  createPlatformClaimsToken: (
    platform: string,
    scope: string,
    userId: string,
    communityId: string,
    canAdministerCommunity: boolean
  ) => {
    return createTestToken(platform, scope, userId, communityId, canAdministerCommunity);
  },
}));

jest.unstable_mockModule('../src/utils/gcp-auth.js', () => ({
  getIdentityToken: jest.fn<() => Promise<string | null>>().mockResolvedValue(null),
  isRunningOnGCP: jest.fn<() => Promise<boolean>>().mockResolvedValue(false),
}));

const { ApiClient } = await import('../src/lib/api-client.js');

function getRequestHeaders(call: unknown[]): Record<string, string> {
  const request = call[0] as Request;
  const headers: Record<string, string> = {};
  request.headers.forEach((value, key) => { headers[key] = value; });
  return headers;
}

describe('ApiClient X-Platform-Claims JWT Header', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCache.get.mockResolvedValue(null);
  });

  it('should send X-Platform-Claims JWT header when user context is provided and JWT secret is configured', async () => {
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
        headers: { 'Content-Type': 'application/json' }
      })
    );

    const userContext = {
      userId: TEST_USER_ID,
      guildId: TEST_GUILD_ID,
      hasManageServer: true,
    };

    await client.listRequests({}, userContext);

    const headers = getRequestHeaders(mockFetch.mock.calls[0]);

    expect(headers['x-platform-claims']).toBeDefined();
    expect(headers['x-platform-type']).toBe('discord');

    const claimsToken = headers['x-platform-claims'];
    const decoded = jwtLib.decode(claimsToken!) as jwtLib.JwtPayload;

    expect(decoded).not.toBeNull();
    expect(decoded.platform).toBe('discord');
    expect(decoded.scope).toBe('*');
    expect(decoded.sub).toBe(TEST_USER_ID);
    expect(decoded.community_id).toBe(TEST_GUILD_ID);
    expect(decoded.can_administer_community).toBe(true);
    expect(decoded.type).toBe('platform_claims');
  });

  it('should include correct claims matching user context in X-Platform-Claims JWT', async () => {
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
        headers: { 'Content-Type': 'application/json' }
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

    const headers = getRequestHeaders(mockFetch.mock.calls[0]);

    const claimsToken = headers['x-platform-claims'];
    expect(claimsToken).toBeDefined();

    const decoded = jwtLib.decode(claimsToken!) as jwtLib.JwtPayload;

    expect(decoded.platform).toBe('discord');
    expect(decoded.scope).toBe('*');
    expect(decoded.sub).toBe('user-abc-123');
    expect(decoded.community_id).toBe('guild-xyz-456');
    expect(decoded.can_administer_community).toBe(false);
    expect(decoded.type).toBe('platform_claims');
    expect(decoded.iat).toBeDefined();
    expect(decoded.exp).toBeDefined();

    const expiryDiff = decoded.exp! - decoded.iat!;
    expect(expiryDiff).toBe(300);
  });

  it('should send X-Platform-Type header alongside X-Platform-Claims', async () => {
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
        headers: { 'Content-Type': 'application/json' }
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

    const headers = getRequestHeaders(mockFetch.mock.calls[0]);

    expect(headers['x-platform-type']).toBe('discord');
    expect(headers['x-platform-claims']).toBeDefined();
    expect(headers['x-discord-user-id']).toBeUndefined();
    expect(headers['x-discord-username']).toBeUndefined();
    expect(headers['x-discord-display-name']).toBeUndefined();
    expect(headers['x-guild-id']).toBeUndefined();
    expect(headers['x-discord-has-manage-server']).toBeUndefined();
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
        headers: { 'Content-Type': 'application/json' }
      })
    );

    const userContext = {
      userId: TEST_USER_ID,
      guildId: TEST_GUILD_ID,
      hasManageServer: true,
    };

    await client.listRequests({}, userContext);

    const headers = getRequestHeaders(mockFetch.mock.calls[0]);
    const claimsToken = headers['x-platform-claims'];

    expect(claimsToken).toBeDefined();

    expect(() => {
      jwtLib.verify(claimsToken!, TEST_JWT_SECRET, { algorithms: ['HS256'] });
    }).not.toThrow();

    const verified = jwtLib.verify(claimsToken!, TEST_JWT_SECRET, { algorithms: ['HS256'] }) as jwtLib.JwtPayload;
    expect(verified.sub).toBe(TEST_USER_ID);
    expect(verified.community_id).toBe(TEST_GUILD_ID);
    expect(verified.can_administer_community).toBe(true);
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
        headers: { 'Content-Type': 'application/json' }
      })
    );

    const userContext = {
      userId: TEST_USER_ID,
      guildId: TEST_GUILD_ID,
      hasManageServer: false,
    };

    await client.listRequests({}, userContext);

    const headers = getRequestHeaders(mockFetch.mock.calls[0]);
    const claimsToken = headers['x-platform-claims'];

    const header = jwtLib.decode(claimsToken!, { complete: true })?.header;
    expect(header?.alg).toBe('HS256');
  });
});
