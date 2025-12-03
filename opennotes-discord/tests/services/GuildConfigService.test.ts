import { jest } from '@jest/globals';

// Mock ApiClient
const mockApiClient = {
  getGuildConfig: jest.fn<(guildId: string) => Promise<Record<string, any>>>(),
  setGuildConfig: jest.fn<(guildId: string, key: string, value: any, updatedBy: string) => Promise<void>>(),
  resetGuildConfig: jest.fn<(guildId: string) => Promise<void>>(),
};

const mockLogger = {
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  info: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const { GuildConfigService } = await import('../../src/services/GuildConfigService.js');
const { ConfigKey } = await import('../../src/lib/config-schema.js');

describe('GuildConfigService', () => {
  let service: InstanceType<typeof GuildConfigService>;
  const testGuildId = 'test-guild-123';
  const testUserId = 'user-456';

  beforeEach(() => {
    jest.clearAllMocks();
    service = new GuildConfigService(mockApiClient as any);
  });

  describe('get', () => {
    it('should fetch config from API and return value', async () => {
      const mockConfig = {
        request_note_ephemeral: true,
        note_rate_limit: 10,
      };

      mockApiClient.getGuildConfig.mockResolvedValueOnce(mockConfig);

      const result = await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL);

      expect(result).toBe(true);
      expect(mockApiClient.getGuildConfig).toHaveBeenCalledWith(testGuildId);
    });

    it('should return default value when key not in config', async () => {
      mockApiClient.getGuildConfig.mockResolvedValueOnce({});

      const result = await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL);

      expect(result).toBe(true); // default value
    });

    it('should use cached config within TTL', async () => {
      const mockConfig = { request_note_ephemeral: true };
      mockApiClient.getGuildConfig.mockResolvedValueOnce(mockConfig);

      // First call - should hit API
      await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL);
      expect(mockApiClient.getGuildConfig).toHaveBeenCalledTimes(1);

      // Second call - should use cache
      await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL);
      expect(mockApiClient.getGuildConfig).toHaveBeenCalledTimes(1); // Still 1
    });

    it('should return defaults on API error', async () => {
      mockApiClient.getGuildConfig.mockRejectedValueOnce(new Error('API Error'));

      const result = await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL);

      expect(result).toBe(true); // default value
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('getAll', () => {
    it('should return all config merged with defaults', async () => {
      const mockConfig = {
        request_note_ephemeral: true,
      };

      mockApiClient.getGuildConfig.mockResolvedValueOnce(mockConfig);

      const result = await service.getAll(testGuildId);

      expect(result.request_note_ephemeral).toBe(true);
      expect(result.note_rate_limit).toBe(5); // default value
    });
  });

  describe('set', () => {
    it('should validate and set config value', async () => {
      mockApiClient.setGuildConfig.mockResolvedValueOnce();
      mockApiClient.getGuildConfig.mockResolvedValueOnce({}); // For cache

      await service.set(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL, true, testUserId);

      expect(mockApiClient.setGuildConfig).toHaveBeenCalledWith(
        testGuildId,
        ConfigKey.REQUEST_NOTE_EPHEMERAL,
        true,
        testUserId
      );
      expect(mockLogger.info).toHaveBeenCalled();
    });

    it('should reject invalid values', async () => {
      await expect(
        service.set(testGuildId, ConfigKey.NOTE_RATE_LIMIT, 999, testUserId)
      ).rejects.toThrow();

      expect(mockApiClient.setGuildConfig).not.toHaveBeenCalled();
    });

    it('should invalidate cache after setting', async () => {
      const initialConfig = { request_note_ephemeral: false };
      const updatedConfig = { request_note_ephemeral: true };

      mockApiClient.getGuildConfig
        .mockResolvedValueOnce(initialConfig)
        .mockResolvedValueOnce(updatedConfig);

      mockApiClient.setGuildConfig.mockResolvedValueOnce();

      // Prime cache
      await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL);
      expect(mockApiClient.getGuildConfig).toHaveBeenCalledTimes(1);

      // Set new value (should invalidate cache)
      await service.set(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL, true, testUserId);

      // Get again (should fetch fresh data)
      await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL);
      expect(mockApiClient.getGuildConfig).toHaveBeenCalledTimes(2);
    });
  });

  describe('reset', () => {
    it('should reset single key to default', async () => {
      mockApiClient.setGuildConfig.mockResolvedValueOnce();

      await service.reset(testGuildId, ConfigKey.NOTE_RATE_LIMIT, testUserId);

      expect(mockApiClient.setGuildConfig).toHaveBeenCalledWith(
        testGuildId,
        ConfigKey.NOTE_RATE_LIMIT,
        5, // default value
        testUserId
      );
    });

    it('should reset all keys when no key specified', async () => {
      mockApiClient.resetGuildConfig.mockResolvedValueOnce();

      await service.reset(testGuildId, undefined, testUserId);

      expect(mockApiClient.resetGuildConfig).toHaveBeenCalledWith(testGuildId);
      expect(mockLogger.info).toHaveBeenCalled();
    });

    it('should invalidate cache after reset', async () => {
      mockApiClient.resetGuildConfig.mockResolvedValueOnce();
      mockApiClient.getGuildConfig.mockResolvedValueOnce({});

      // Prime cache
      await service.getAll(testGuildId);
      const callCount = mockApiClient.getGuildConfig.mock.calls.length;

      // Reset (should invalidate)
      await service.reset(testGuildId);

      // Get again (should fetch fresh)
      await service.getAll(testGuildId);
      expect(mockApiClient.getGuildConfig.mock.calls.length).toBe(callCount + 1);
    });
  });

  describe('cache management', () => {
    it('should expose cache size', () => {
      expect(service.getCacheSize()).toBe(0);
    });

    it('should clear all cache', async () => {
      mockApiClient.getGuildConfig.mockResolvedValueOnce({});

      await service.getAll(testGuildId);
      expect(service.getCacheSize()).toBeGreaterThan(0);

      service.clearAllCache();
      expect(service.getCacheSize()).toBe(0);
    });

    it('should track cache hits and misses', async () => {
      mockApiClient.getGuildConfig.mockResolvedValueOnce({});

      // First call - cache miss
      await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL);
      let metrics = service.getCacheMetrics();
      expect(metrics.misses).toBe(1);
      expect(metrics.hits).toBe(0);

      // Second call - cache hit
      await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL);
      metrics = service.getCacheMetrics();
      expect(metrics.hits).toBe(1);
      expect(metrics.misses).toBe(1);
      expect(metrics.totalRequests).toBe(2);
    });

    it('should calculate cache hit rate correctly', async () => {
      mockApiClient.getGuildConfig.mockResolvedValue({});

      // 1 miss, 3 hits = 75% hit rate
      await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL); // miss
      await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL); // hit
      await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL); // hit
      await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL); // hit

      const metrics = service.getCacheMetrics();
      expect(metrics.hitRate).toBe(75);
      expect(metrics.totalRequests).toBe(4);
    });

    it('should reset metrics when clearing cache', async () => {
      mockApiClient.getGuildConfig.mockResolvedValueOnce({});

      await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL);
      await service.get(testGuildId, ConfigKey.REQUEST_NOTE_EPHEMERAL);

      let metrics = service.getCacheMetrics();
      expect(metrics.totalRequests).toBeGreaterThan(0);

      service.clearAllCache();
      metrics = service.getCacheMetrics();
      expect(metrics.hits).toBe(0);
      expect(metrics.misses).toBe(0);
      expect(metrics.totalRequests).toBe(0);
    });
  });
});
