import { jest } from '@jest/globals';

const mockCacheGet = jest.fn<(key: string) => Promise<any>>();
const mockCacheSet = jest.fn<(key: string, value: unknown, ttl?: number) => Promise<boolean>>().mockResolvedValue(true);

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: {
    get: mockCacheGet,
    set: mockCacheSet,
    delete: jest.fn<(key: string) => Promise<boolean>>().mockResolvedValue(true),
  },
}));

const {
  createStallWarningController,
} = await import('../../src/lib/vibecheck-stall-warning.js');
const {
  recordStalledScan,
} = await import('../../src/lib/vibecheck-stalled-scan.js');

describe('createStallWarningController', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const cacheStore = new Map<string, unknown>();
    mockCacheGet.mockImplementation(async (key: string) => cacheStore.get(key) ?? null);
    mockCacheSet.mockImplementation(async (key: string, value: unknown) => {
      cacheStore.set(key, value);
      return true;
    });
  });

  it('keeps suppressing updates after stalled metadata is recorded even if later warning work fails', async () => {
    const controller = createStallWarningController(async (scanId) => {
      await recordStalledScan({
        scanId,
        initiatorId: 'user-123',
        guildId: 'guild-123',
        days: 7,
        source: 'slash_command',
      });
      throw new Error('failed to edit interaction');
    });

    await expect(controller.onStallWarning('scan-warning-123')).rejects.toThrow(
      'failed to edit interaction'
    );

    await expect(controller.shouldSuppressUpdates()).resolves.toBe(true);
  });
});
