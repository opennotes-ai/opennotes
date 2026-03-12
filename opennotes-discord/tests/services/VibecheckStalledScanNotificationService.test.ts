import { jest } from '@jest/globals';
import { EventType } from '../../src/types/bulk-scan.js';

const mockLogger = {
  debug: jest.fn<(...args: unknown[]) => void>(),
  info: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
};

const mockApiClient = {
  getBulkScanResults: jest.fn<(scanId: string) => Promise<any>>(),
};

const mockCacheGet = jest.fn<(key: string) => Promise<any>>();
const mockCacheSet = jest.fn<(key: string, value: unknown, ttl?: number) => Promise<boolean>>().mockResolvedValue(true);
const mockCacheDelete = jest.fn<(key: string) => Promise<boolean>>().mockResolvedValue(true);
const mockUserSend = jest.fn<(content: string) => Promise<void>>().mockResolvedValue(undefined);
const mockUsersFetch = jest.fn<(userId: string) => Promise<any>>().mockResolvedValue({
  send: mockUserSend,
});

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: {
    get: mockCacheGet,
    set: mockCacheSet,
    delete: mockCacheDelete,
  },
}));

const { VibecheckStalledScanNotificationService } = await import('../../src/services/VibecheckStalledScanNotificationService.js');

describe('VibecheckStalledScanNotificationService', () => {
  let service: InstanceType<typeof VibecheckStalledScanNotificationService>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockCacheSet.mockResolvedValue(true);
    mockCacheDelete.mockResolvedValue(true);
    mockUsersFetch.mockResolvedValue({
      send: mockUserSend,
    });
    service = new VibecheckStalledScanNotificationService({
      users: {
        fetch: mockUsersFetch,
      },
    } as any);
  });

  it('sends a completion DM for a cached stalled scan and clears the cache', async () => {
    mockCacheGet.mockResolvedValue({
      scanId: 'scan-123',
      initiatorId: 'user-123',
      guildId: 'guild-123',
      days: 7,
      source: 'slash_command',
    });
    mockApiClient.getBulkScanResults.mockResolvedValue({
      data: {
        type: 'bulk-scans',
        id: 'scan-123',
        attributes: {
          status: 'completed',
          initiated_at: new Date().toISOString(),
          messages_scanned: 80,
          messages_flagged: 2,
        },
      },
      included: [],
      jsonapi: { version: '1.1' },
    });

    await service.handleTerminalEvent({
      event_id: 'evt-1',
      event_type: EventType.BULK_SCAN_PROCESSING_FINISHED,
      version: '1.0',
      timestamp: new Date().toISOString(),
      metadata: {},
      scan_id: 'scan-123',
      community_server_id: 'community-123',
      messages_scanned: 80,
      messages_flagged: 2,
    });

    const dm = mockUserSend.mock.calls[0][0] as string;
    expect(dm).toContain('Messages scanned: 80');
    expect(dm).toContain('Flagged: 2');
    expect(dm).toContain('/vibecheck status scan_id:scan-123');
    expect(mockCacheDelete).toHaveBeenCalledWith('vibecheck:stalled:scan-123');
  });

  it('sends failure guidance for a cached failed stalled scan', async () => {
    mockCacheGet.mockResolvedValue({
      scanId: 'scan-456',
      initiatorId: 'user-123',
      guildId: 'guild-123',
      days: 14,
      source: 'prompt',
    });

    await service.handleTerminalEvent({
      event_id: 'evt-2',
      event_type: EventType.BULK_SCAN_FAILED,
      version: '1.0',
      timestamp: new Date().toISOString(),
      metadata: {},
      scan_id: 'scan-456',
      community_server_id: 'community-123',
      error_message: 'worker crashed',
    });

    const dm = mockUserSend.mock.calls[0][0] as string;
    expect(dm).toContain('scan-456');
    expect(dm).toContain('failed');
    expect(dm).toContain('/vibecheck status scan_id:scan-456');
    expect(mockCacheDelete).toHaveBeenCalledWith('vibecheck:stalled:scan-456');
  });
});
