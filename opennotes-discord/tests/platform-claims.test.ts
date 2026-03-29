import { jest } from '@jest/globals';
import jwt from 'jsonwebtoken';
import { loggerFactory } from './factories/index.js';

const mockLogger = loggerFactory.build();

jest.unstable_mockModule('../src/logger.js', () => ({
  logger: mockLogger,
}));

describe('Platform Claims JWT Utility', () => {
  const TEST_JWT_SECRET = 'abcdefghij1234567890abcdefghij12';
  const TEST_USER_ID = '123456789012345678';
  const TEST_GUILD_ID = '987654321098765432';

  beforeEach(() => {
    jest.resetModules();
    jest.clearAllMocks();
  });

  describe('createPlatformClaimsToken', () => {
    it('should create valid JWT with platform claims when JWT_SECRET_KEY is configured', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createPlatformClaimsToken } = await import('../src/utils/platform-claims.js');

      const token = createPlatformClaimsToken(
        'discord',
        '*',
        TEST_USER_ID,
        TEST_GUILD_ID,
        true
      );

      expect(token).not.toBeNull();
      expect(typeof token).toBe('string');

      const decoded = jwt.decode(token!) as jwt.JwtPayload;
      expect(decoded).not.toBeNull();
      expect(decoded.platform).toBe('discord');
      expect(decoded.scope).toBe('*');
      expect(decoded.sub).toBe(TEST_USER_ID);
      expect(decoded.community_id).toBe(TEST_GUILD_ID);
      expect(decoded.can_administer_community).toBe(true);
      expect(decoded.type).toBe('platform_claims');
      expect(decoded.iat).toBeDefined();
      expect(decoded.exp).toBeDefined();
    });

    it('should create JWT that can be verified with the secret key', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createPlatformClaimsToken } = await import('../src/utils/platform-claims.js');

      const token = createPlatformClaimsToken(
        'discord',
        '*',
        TEST_USER_ID,
        TEST_GUILD_ID,
        false
      );

      expect(() => {
        jwt.verify(token!, TEST_JWT_SECRET, { algorithms: ['HS256'] });
      }).not.toThrow();

      const verified = jwt.verify(token!, TEST_JWT_SECRET, { algorithms: ['HS256'] }) as jwt.JwtPayload;
      expect(verified.sub).toBe(TEST_USER_ID);
      expect(verified.can_administer_community).toBe(false);
    });

    it('should set expiry approximately 5 minutes from creation', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createPlatformClaimsToken } = await import('../src/utils/platform-claims.js');

      const beforeCreation = Math.floor(Date.now() / 1000);
      const token = createPlatformClaimsToken(
        'discord',
        '*',
        TEST_USER_ID,
        TEST_GUILD_ID,
        true
      );
      const afterCreation = Math.floor(Date.now() / 1000);

      const decoded = jwt.decode(token!) as jwt.JwtPayload;

      const expectedExpiry = 300;
      const iat = decoded.iat!;
      const exp = decoded.exp!;

      expect(iat).toBeGreaterThanOrEqual(beforeCreation);
      expect(iat).toBeLessThanOrEqual(afterCreation);

      const expiryDiff = exp - iat;
      expect(expiryDiff).toBe(expectedExpiry);
    });

    it('should return null when JWT_SECRET_KEY is not configured', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: undefined,
        },
      }));

      const { createPlatformClaimsToken } = await import('../src/utils/platform-claims.js');

      const token = createPlatformClaimsToken(
        'discord',
        '*',
        TEST_USER_ID,
        TEST_GUILD_ID,
        true
      );

      expect(token).toBeNull();
      expect(mockLogger.warn).toHaveBeenCalledWith(
        'JWT_SECRET_KEY not configured, cannot create platform claims token'
      );
    });

    it('should return null when JWT_SECRET_KEY is empty string', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: '',
        },
      }));

      const { createPlatformClaimsToken } = await import('../src/utils/platform-claims.js');

      const token = createPlatformClaimsToken(
        'discord',
        '*',
        TEST_USER_ID,
        TEST_GUILD_ID,
        false
      );

      expect(token).toBeNull();
    });

    it('should correctly encode can_administer_community as true', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createPlatformClaimsToken } = await import('../src/utils/platform-claims.js');

      const token = createPlatformClaimsToken('discord', '*', TEST_USER_ID, TEST_GUILD_ID, true);
      const decoded = jwt.decode(token!) as jwt.JwtPayload;

      expect(decoded.can_administer_community).toBe(true);
    });

    it('should correctly encode can_administer_community as false', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createPlatformClaimsToken } = await import('../src/utils/platform-claims.js');

      const token = createPlatformClaimsToken('discord', '*', TEST_USER_ID, TEST_GUILD_ID, false);
      const decoded = jwt.decode(token!) as jwt.JwtPayload;

      expect(decoded.can_administer_community).toBe(false);
    });

    it('should handle empty community_id', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createPlatformClaimsToken } = await import('../src/utils/platform-claims.js');

      const token = createPlatformClaimsToken('discord', '*', TEST_USER_ID, '', false);

      expect(token).not.toBeNull();
      const decoded = jwt.decode(token!) as jwt.JwtPayload;
      expect(decoded.community_id).toBe('');
    });

    it('should use HS256 algorithm for signing', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createPlatformClaimsToken } = await import('../src/utils/platform-claims.js');

      const token = createPlatformClaimsToken('discord', '*', TEST_USER_ID, TEST_GUILD_ID, true);

      const header = jwt.decode(token!, { complete: true })?.header;
      expect(header?.alg).toBe('HS256');
    });

    it('should fail verification with wrong secret', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createPlatformClaimsToken } = await import('../src/utils/platform-claims.js');

      const token = createPlatformClaimsToken('discord', '*', TEST_USER_ID, TEST_GUILD_ID, true);

      expect(() => {
        jwt.verify(token!, 'wrong-secret-key-12345678901234', { algorithms: ['HS256'] });
      }).toThrow();
    });

    it('should not include old Discord-specific claim names', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createPlatformClaimsToken } = await import('../src/utils/platform-claims.js');

      const token = createPlatformClaimsToken('discord', '*', TEST_USER_ID, TEST_GUILD_ID, true);
      const decoded = jwt.decode(token!) as jwt.JwtPayload;

      expect(decoded.user_id).toBeUndefined();
      expect(decoded.guild_id).toBeUndefined();
      expect(decoded.has_manage_server).toBeUndefined();
    });
  });
});
