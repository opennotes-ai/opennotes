import { jest } from '@jest/globals';
import jwt from 'jsonwebtoken';
import { loggerFactory } from './factories/index.js';

const mockLogger = loggerFactory.build();

jest.unstable_mockModule('../src/logger.js', () => ({
  logger: mockLogger,
}));

describe('Discord Claims JWT Utility', () => {
  const TEST_JWT_SECRET = 'abcdefghij1234567890abcdefghij12';
  const TEST_USER_ID = '123456789012345678';
  const TEST_GUILD_ID = '987654321098765432';

  beforeEach(() => {
    jest.resetModules();
    jest.clearAllMocks();
  });

  describe('createDiscordClaimsToken', () => {
    it('should create valid JWT with correct claims when JWT_SECRET_KEY is configured', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createDiscordClaimsToken } = await import('../src/utils/discord-claims.js');

      const token = createDiscordClaimsToken(TEST_USER_ID, TEST_GUILD_ID, true);

      expect(token).not.toBeNull();
      expect(typeof token).toBe('string');

      const decoded = jwt.decode(token!) as jwt.JwtPayload;
      expect(decoded).not.toBeNull();
      expect(decoded.sub).toBe(TEST_USER_ID);
      expect(decoded.user_id).toBe(TEST_USER_ID);
      expect(decoded.guild_id).toBe(TEST_GUILD_ID);
      expect(decoded.has_manage_server).toBe(true);
      expect(decoded.type).toBe('discord_claims');
      expect(decoded.iat).toBeDefined();
      expect(decoded.exp).toBeDefined();
    });

    it('should create JWT that can be verified with the secret key', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createDiscordClaimsToken } = await import('../src/utils/discord-claims.js');

      const token = createDiscordClaimsToken(TEST_USER_ID, TEST_GUILD_ID, false);

      expect(() => {
        jwt.verify(token!, TEST_JWT_SECRET, { algorithms: ['HS256'] });
      }).not.toThrow();

      const verified = jwt.verify(token!, TEST_JWT_SECRET, { algorithms: ['HS256'] }) as jwt.JwtPayload;
      expect(verified.sub).toBe(TEST_USER_ID);
      expect(verified.has_manage_server).toBe(false);
    });

    it('should set expiry approximately 5 minutes from creation', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createDiscordClaimsToken } = await import('../src/utils/discord-claims.js');

      const beforeCreation = Math.floor(Date.now() / 1000);
      const token = createDiscordClaimsToken(TEST_USER_ID, TEST_GUILD_ID, true);
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

      const { createDiscordClaimsToken } = await import('../src/utils/discord-claims.js');

      const token = createDiscordClaimsToken(TEST_USER_ID, TEST_GUILD_ID, true);

      expect(token).toBeNull();
      expect(mockLogger.warn).toHaveBeenCalledWith(
        'JWT_SECRET_KEY not configured, cannot create Discord claims token'
      );
    });

    it('should return null when JWT_SECRET_KEY is empty string', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: '',
        },
      }));

      const { createDiscordClaimsToken } = await import('../src/utils/discord-claims.js');

      const token = createDiscordClaimsToken(TEST_USER_ID, TEST_GUILD_ID, false);

      expect(token).toBeNull();
    });

    it('should correctly encode has_manage_server as true', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createDiscordClaimsToken } = await import('../src/utils/discord-claims.js');

      const token = createDiscordClaimsToken(TEST_USER_ID, TEST_GUILD_ID, true);
      const decoded = jwt.decode(token!) as jwt.JwtPayload;

      expect(decoded.has_manage_server).toBe(true);
    });

    it('should correctly encode has_manage_server as false', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createDiscordClaimsToken } = await import('../src/utils/discord-claims.js');

      const token = createDiscordClaimsToken(TEST_USER_ID, TEST_GUILD_ID, false);
      const decoded = jwt.decode(token!) as jwt.JwtPayload;

      expect(decoded.has_manage_server).toBe(false);
    });

    it('should handle empty guild_id', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createDiscordClaimsToken } = await import('../src/utils/discord-claims.js');

      const token = createDiscordClaimsToken(TEST_USER_ID, '', false);

      expect(token).not.toBeNull();
      const decoded = jwt.decode(token!) as jwt.JwtPayload;
      expect(decoded.guild_id).toBe('');
    });

    it('should use HS256 algorithm for signing', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createDiscordClaimsToken } = await import('../src/utils/discord-claims.js');

      const token = createDiscordClaimsToken(TEST_USER_ID, TEST_GUILD_ID, true);

      const header = jwt.decode(token!, { complete: true })?.header;
      expect(header?.alg).toBe('HS256');
    });

    it('should fail verification with wrong secret', async () => {
      jest.unstable_mockModule('../src/config.js', () => ({
        config: {
          jwtSecretKey: TEST_JWT_SECRET,
        },
      }));

      const { createDiscordClaimsToken } = await import('../src/utils/discord-claims.js');

      const token = createDiscordClaimsToken(TEST_USER_ID, TEST_GUILD_ID, true);

      expect(() => {
        jwt.verify(token!, 'wrong-secret-key-12345678901234', { algorithms: ['HS256'] });
      }).toThrow();
    });
  });
});
