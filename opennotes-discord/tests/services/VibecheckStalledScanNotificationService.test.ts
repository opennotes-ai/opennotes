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
  let stalledScanStore: Record<string, any>;

  beforeEach(() => {
    jest.clearAllMocks();
    stalledScanStore = {};
    mockCacheGet.mockImplementation(async (key: string) => stalledScanStore[key] ?? null);
    mockCacheSet.mockImplementation(async (key: string, value: unknown) => {
      stalledScanStore[key] = value;
      return true;
    });
    mockCacheDelete.mockImplementation(async (key: string) => {
      const existed = key in stalledScanStore;
      delete stalledScanStore[key];
      return existed;
    });
    mockUsersFetch.mockResolvedValue({
      send: mockUserSend,
    });
    service = new VibecheckStalledScanNotificationService({
      users: {
        fetch: mockUsersFetch,
      },
    } as any);
  });

  it('sends a completion DM for a cached stalled scan and marks it delivered', async () => {
    stalledScanStore['vibecheck:stalled:scan-123'] = {
      scanId: 'scan-123',
      initiatorId: 'user-123',
      guildId: 'guild-123',
      days: 7,
      source: 'slash_command',
    };
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
    expect(stalledScanStore['vibecheck:stalled:scan-123']).toEqual(
      expect.objectContaining({
        scanId: 'scan-123',
        notificationState: 'sent',
      })
    );
  });

  it('sends failure guidance for a cached failed stalled scan and marks it delivered', async () => {
    stalledScanStore['vibecheck:stalled:scan-456'] = {
      scanId: 'scan-456',
      initiatorId: 'user-123',
      guildId: 'guild-123',
      days: 14,
      source: 'prompt',
    };

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
    expect(stalledScanStore['vibecheck:stalled:scan-456']).toEqual(
      expect.objectContaining({
        scanId: 'scan-456',
        notificationState: 'sent',
      })
    );
  });

  it('retries the stalled-scan lookup when the terminal event wins a near-stall race', async () => {
    let lookupCount = 0;
    mockCacheGet.mockImplementation(async (key: string) => {
      lookupCount += 1;
      if (lookupCount === 1) {
        stalledScanStore[key] = {
          scanId: 'scan-race-123',
          initiatorId: 'user-123',
          guildId: 'guild-123',
          days: 7,
          source: 'slash_command',
        };
        return null;
      }

      return stalledScanStore[key] ?? null;
    });
    mockApiClient.getBulkScanResults.mockResolvedValue({
      data: {
        type: 'bulk-scans',
        id: 'scan-race-123',
        attributes: {
          status: 'completed',
          initiated_at: new Date().toISOString(),
          messages_scanned: 90,
          messages_flagged: 1,
        },
      },
      included: [],
      jsonapi: { version: '1.1' },
    });

    await service.handleTerminalEvent({
      event_id: 'evt-3',
      event_type: EventType.BULK_SCAN_PROCESSING_FINISHED,
      version: '1.0',
      timestamp: new Date().toISOString(),
      metadata: {},
      scan_id: 'scan-race-123',
      community_server_id: 'community-123',
      messages_scanned: 90,
      messages_flagged: 1,
    });

    expect(lookupCount).toBeGreaterThan(1);
    expect(mockUserSend).toHaveBeenCalledTimes(1);
  });

  it('keeps stalled scans retryable after DM delivery failures', async () => {
    stalledScanStore['vibecheck:stalled:scan-retry-123'] = {
      scanId: 'scan-retry-123',
      initiatorId: 'user-123',
      guildId: 'guild-123',
      days: 7,
      source: 'slash_command',
    };
    mockApiClient.getBulkScanResults.mockResolvedValue({
      data: {
        type: 'bulk-scans',
        id: 'scan-retry-123',
        attributes: {
          status: 'completed',
          initiated_at: new Date().toISOString(),
          messages_scanned: 120,
          messages_flagged: 3,
        },
      },
      included: [],
      jsonapi: { version: '1.1' },
    });
    mockUserSend
      .mockRejectedValueOnce(new Error('DMs disabled'))
      .mockResolvedValueOnce(undefined);

    const event = {
      event_id: 'evt-4',
      event_type: EventType.BULK_SCAN_PROCESSING_FINISHED,
      version: '1.0',
      timestamp: new Date().toISOString(),
      metadata: {},
      scan_id: 'scan-retry-123',
      community_server_id: 'community-123',
      messages_scanned: 120,
      messages_flagged: 3,
    };

    await service.handleTerminalEvent(event);
    expect(stalledScanStore['vibecheck:stalled:scan-retry-123']).toEqual(
      expect.not.objectContaining({
        notificationState: 'sent',
      })
    );

    await service.handleTerminalEvent(event);

    expect(mockUserSend).toHaveBeenCalledTimes(2);
    expect(stalledScanStore['vibecheck:stalled:scan-retry-123']).toEqual(
      expect.objectContaining({
        notificationState: 'sent',
      })
    );
  });

  it('does not send duplicate DMs after a stalled scan has already been delivered', async () => {
    stalledScanStore['vibecheck:stalled:scan-idempotent-123'] = {
      scanId: 'scan-idempotent-123',
      initiatorId: 'user-123',
      guildId: 'guild-123',
      days: 7,
      source: 'slash_command',
    };
    mockApiClient.getBulkScanResults.mockResolvedValue({
      data: {
        type: 'bulk-scans',
        id: 'scan-idempotent-123',
        attributes: {
          status: 'completed',
          initiated_at: new Date().toISOString(),
          messages_scanned: 33,
          messages_flagged: 1,
        },
      },
      included: [],
      jsonapi: { version: '1.1' },
    });

    const event = {
      event_id: 'evt-5',
      event_type: EventType.BULK_SCAN_PROCESSING_FINISHED,
      version: '1.0',
      timestamp: new Date().toISOString(),
      metadata: {},
      scan_id: 'scan-idempotent-123',
      community_server_id: 'community-123',
      messages_scanned: 33,
      messages_flagged: 1,
    };

    await service.handleTerminalEvent(event);
    await service.handleTerminalEvent(event);

    expect(mockUserSend).toHaveBeenCalledTimes(1);
  });
});
