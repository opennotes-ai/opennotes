import { jest } from '@jest/globals';

describe('Config', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  describe('API Key Validation', () => {
    it('should accept valid API key', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = 'valid-api-key-1234567890';
      process.env.NODE_ENV = 'development';

      const { config } = await import('../src/config.js');

      expect(config.apiKey).toBe('valid-api-key-1234567890');
    });

    it('should throw error for API key in production when missing', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.NODE_ENV = 'production';
      delete process.env.OPENNOTES_API_KEY;

      await expect(async () => {
        await import('../src/config.js');
      }).rejects.toThrow('OPENNOTES_API_KEY is required in production');
    });

    it('should reject placeholder API keys', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = 'your_api_key_here';
      process.env.NODE_ENV = 'development';

      await expect(async () => {
        await import('../src/config.js');
      }).rejects.toThrow('Invalid API key: appears to be a placeholder value');
    });

    it('should reject short API keys', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = 'short';
      process.env.NODE_ENV = 'development';

      await expect(async () => {
        await import('../src/config.js');
      }).rejects.toThrow('Invalid API key: too short');
    });

    it('should trim whitespace from API key', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = '  valid-api-key-1234567890  ';
      process.env.NODE_ENV = 'development';

      const { config } = await import('../src/config.js');

      expect(config.apiKey).toBe('valid-api-key-1234567890');
    });

    it('should allow missing API key in development with warning', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.NODE_ENV = 'development';
      delete process.env.OPENNOTES_API_KEY;

      const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

      const { config } = await import('../src/config.js');

      expect(config.apiKey).toBeUndefined();
      expect(warnSpy).toHaveBeenCalledWith(
        'Warning: OPENNOTES_API_KEY is not set. API requests may fail.'
      );

      warnSpy.mockRestore();
    });

    it('should reject exact "changeme" placeholder', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = 'changeme';
      process.env.NODE_ENV = 'development';

      await expect(async () => {
        await import('../src/config.js');
      }).rejects.toThrow('Invalid API key: appears to be a placeholder value');
    });

    it('should accept API keys containing "test" (not exact match)', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = 'test-api-key-12345';
      process.env.NODE_ENV = 'development';

      const { config } = await import('../src/config.js');

      expect(config.apiKey).toBe('test-api-key-12345');
    });

    it('should reject exact "test_key" placeholder', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = 'test_key';
      process.env.NODE_ENV = 'development';

      await expect(async () => {
        await import('../src/config.js');
      }).rejects.toThrow('Invalid API key: appears to be a placeholder value');
    });
  });

  describe('Security Secret Validation', () => {
    const VALID_API_KEY = 'validapikey12345';
    const VALID_SECRET = 'abcdefghij1234567890abcdefghij12';
    const SHORT_SECRET = 'shortsecret12345678901';

    it('should accept valid INTERNAL_SERVICE_SECRET (32+ chars)', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = VALID_API_KEY;
      process.env.INTERNAL_SERVICE_SECRET = VALID_SECRET;
      process.env.NODE_ENV = 'development';

      const { config } = await import('../src/config.js');

      expect(config.internalServiceSecret).toBe(VALID_SECRET);
    });

    it('should accept valid JWT_SECRET_KEY (32+ chars)', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = VALID_API_KEY;
      process.env.JWT_SECRET_KEY = VALID_SECRET;
      process.env.NODE_ENV = 'development';

      const { config } = await import('../src/config.js');

      expect(config.jwtSecretKey).toBe(VALID_SECRET);
    });

    it('should throw error for INTERNAL_SERVICE_SECRET in production when missing', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = VALID_API_KEY;
      process.env.JWT_SECRET_KEY = VALID_SECRET;
      process.env.NODE_ENV = 'production';
      delete process.env.INTERNAL_SERVICE_SECRET;

      await expect(async () => {
        await import('../src/config.js');
      }).rejects.toThrow('INTERNAL_SERVICE_SECRET is required in production');
    });

    it('should throw error for JWT_SECRET_KEY in production when missing', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = VALID_API_KEY;
      process.env.INTERNAL_SERVICE_SECRET = VALID_SECRET;
      process.env.NODE_ENV = 'production';
      delete process.env.JWT_SECRET_KEY;

      await expect(async () => {
        await import('../src/config.js');
      }).rejects.toThrow('JWT_SECRET_KEY is required in production');
    });

    it('should allow missing INTERNAL_SERVICE_SECRET in development with warning', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.NODE_ENV = 'development';
      delete process.env.OPENNOTES_API_KEY;
      delete process.env.INTERNAL_SERVICE_SECRET;

      const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

      const { config } = await import('../src/config.js');

      expect(config.internalServiceSecret).toBeUndefined();
      expect(warnSpy).toHaveBeenCalledWith(
        'Warning: INTERNAL_SERVICE_SECRET is not set. Security headers will not be sent.'
      );

      warnSpy.mockRestore();
    });

    it('should allow missing JWT_SECRET_KEY in development with warning', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.NODE_ENV = 'development';
      delete process.env.OPENNOTES_API_KEY;
      delete process.env.JWT_SECRET_KEY;

      const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

      const { config } = await import('../src/config.js');

      expect(config.jwtSecretKey).toBeUndefined();
      expect(warnSpy).toHaveBeenCalledWith(
        'Warning: JWT_SECRET_KEY is not set. Security headers will not be sent.'
      );

      warnSpy.mockRestore();
    });

    it('should reject exact "your_secret_here" placeholder', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = VALID_API_KEY;
      process.env.INTERNAL_SERVICE_SECRET = 'your_secret_here';
      process.env.NODE_ENV = 'development';

      await expect(async () => {
        await import('../src/config.js');
      }).rejects.toThrow('Invalid INTERNAL_SERVICE_SECRET: appears to be a placeholder value');
    });

    it('should reject exact "changeme" placeholder', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = VALID_API_KEY;
      process.env.INTERNAL_SERVICE_SECRET = 'changeme';
      process.env.NODE_ENV = 'development';

      await expect(async () => {
        await import('../src/config.js');
      }).rejects.toThrow('Invalid INTERNAL_SERVICE_SECRET: appears to be a placeholder value');
    });

    it('should accept secrets containing "example" (not exact match)', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = VALID_API_KEY;
      process.env.INTERNAL_SERVICE_SECRET = 'example-secret-value-1234567890';
      process.env.NODE_ENV = 'development';

      const { config } = await import('../src/config.js');

      expect(config.internalServiceSecret).toBe('example-secret-value-1234567890');
    });

    it('should accept secrets containing "test" (not exact match)', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = VALID_API_KEY;
      process.env.INTERNAL_SERVICE_SECRET = 'test-secret-value-123456789012';
      process.env.NODE_ENV = 'development';

      const { config } = await import('../src/config.js');

      expect(config.internalServiceSecret).toBe('test-secret-value-123456789012');
    });

    it('should reject exact "placeholder" secret', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = VALID_API_KEY;
      process.env.INTERNAL_SERVICE_SECRET = 'placeholder';
      process.env.NODE_ENV = 'development';

      await expect(async () => {
        await import('../src/config.js');
      }).rejects.toThrow('Invalid INTERNAL_SERVICE_SECRET: appears to be a placeholder value');
    });

    it('should throw error for short secret in production', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = VALID_API_KEY;
      process.env.INTERNAL_SERVICE_SECRET = SHORT_SECRET;
      process.env.JWT_SECRET_KEY = VALID_SECRET;
      process.env.NODE_ENV = 'production';

      await expect(async () => {
        await import('../src/config.js');
      }).rejects.toThrow('Invalid INTERNAL_SERVICE_SECRET: too short (minimum 32 characters in production)');
    });

    it('should warn for short secret in development but accept it', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = VALID_API_KEY;
      process.env.INTERNAL_SERVICE_SECRET = SHORT_SECRET;
      process.env.NODE_ENV = 'development';

      const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

      const { config } = await import('../src/config.js');

      expect(config.internalServiceSecret).toBe(SHORT_SECRET);
      expect(warnSpy).toHaveBeenCalledWith(
        'Warning: INTERNAL_SERVICE_SECRET is shorter than 32 characters. This is not recommended.'
      );

      warnSpy.mockRestore();
    });

    it('should trim whitespace from security secrets', async () => {
      process.env.DISCORD_TOKEN = 'test-token';
      process.env.DISCORD_CLIENT_ID = 'test-client-id';
      process.env.OPENNOTES_API_KEY = VALID_API_KEY;
      process.env.INTERNAL_SERVICE_SECRET = `  ${VALID_SECRET}  `;
      process.env.NODE_ENV = 'development';

      const { config } = await import('../src/config.js');

      expect(config.internalServiceSecret).toBe(VALID_SECRET);
    });
  });
});
