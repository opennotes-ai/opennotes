import { jest } from '@jest/globals';
import { DiscordAPIError, RESTJSONErrorCodes } from 'discord.js';
import { EventType } from '../../src/types/bulk-scan.js';

const STALLED_SCAN_RETENTION_SECONDS = 7 * 24 * 60 * 60;

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
    expect(mockCacheSet).toHaveBeenLastCalledWith(
      'vibecheck:stalled:scan-123',
      expect.objectContaining({
        scanId: 'scan-123',
        notificationState: 'sent',
      }),
      STALLED_SCAN_RETENTION_SECONDS
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
    expect(mockCacheSet).toHaveBeenLastCalledWith(
      'vibecheck:stalled:scan-456',
      expect.objectContaining({
        scanId: 'scan-456',
        notificationState: 'sent',
      }),
      STALLED_SCAN_RETENTION_SECONDS
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

  it('waits long enough for stalled-scan metadata that becomes visible after the initial retry window', async () => {
    let lookupCount = 0;
    mockCacheGet.mockImplementation(async (key: string) => {
      lookupCount += 1;
      if (lookupCount < 8) {
        return null;
      }

      stalledScanStore[key] = {
        scanId: 'scan-slow-visibility-123',
        initiatorId: 'user-123',
        guildId: 'guild-123',
        days: 7,
        source: 'slash_command',
      };
      return stalledScanStore[key];
    });
    mockApiClient.getBulkScanResults.mockResolvedValue({
      data: {
        type: 'bulk-scans',
        id: 'scan-slow-visibility-123',
        attributes: {
          status: 'completed',
          initiated_at: new Date().toISOString(),
          messages_scanned: 64,
          messages_flagged: 2,
        },
      },
      included: [],
      jsonapi: { version: '1.1' },
    });

    await service.handleTerminalEvent({
      event_id: 'evt-slow-visibility',
      event_type: EventType.BULK_SCAN_PROCESSING_FINISHED,
      version: '1.0',
      timestamp: new Date().toISOString(),
      metadata: {},
      scan_id: 'scan-slow-visibility-123',
      community_server_id: 'community-123',
      messages_scanned: 64,
      messages_flagged: 2,
    });

    expect(lookupCount).toBeGreaterThanOrEqual(8);
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

    await expect(service.handleTerminalEvent(event)).rejects.toThrow('DMs disabled');
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

  it('rethrows transient DM delivery failures so terminal events can be retried', async () => {
    stalledScanStore['vibecheck:stalled:scan-transient-123'] = {
      scanId: 'scan-transient-123',
      initiatorId: 'user-123',
      guildId: 'guild-123',
      days: 7,
      source: 'slash_command',
    };
    mockApiClient.getBulkScanResults.mockResolvedValue({
      data: {
        type: 'bulk-scans',
        id: 'scan-transient-123',
        attributes: {
          status: 'completed',
          initiated_at: new Date().toISOString(),
          messages_scanned: 55,
          messages_flagged: 4,
        },
      },
      included: [],
      jsonapi: { version: '1.1' },
    });
    mockUserSend.mockRejectedValueOnce(new Error('network timeout'));

    await expect(service.handleTerminalEvent({
      event_id: 'evt-transient',
      event_type: EventType.BULK_SCAN_PROCESSING_FINISHED,
      version: '1.0',
      timestamp: new Date().toISOString(),
      metadata: {},
      scan_id: 'scan-transient-123',
      community_server_id: 'community-123',
      messages_scanned: 55,
      messages_flagged: 4,
    })).rejects.toThrow('network timeout');

    expect(stalledScanStore['vibecheck:stalled:scan-transient-123']).toEqual(
      expect.not.objectContaining({
        notificationState: 'sent',
      })
    );
  });

  it('swallows permanent DM-closed failures and only logs them', async () => {
    stalledScanStore['vibecheck:stalled:scan-closed-123'] = {
      scanId: 'scan-closed-123',
      initiatorId: 'user-123',
      guildId: 'guild-123',
      days: 7,
      source: 'slash_command',
    };
    mockApiClient.getBulkScanResults.mockResolvedValue({
      data: {
        type: 'bulk-scans',
        id: 'scan-closed-123',
        attributes: {
          status: 'completed',
          initiated_at: new Date().toISOString(),
          messages_scanned: 12,
          messages_flagged: 0,
        },
      },
      included: [],
      jsonapi: { version: '1.1' },
    });
    mockUserSend.mockRejectedValueOnce(
      new DiscordAPIError(
        {
          code: RESTJSONErrorCodes.CannotSendMessagesToThisUser,
          message: 'Cannot send messages to this user',
        },
        RESTJSONErrorCodes.CannotSendMessagesToThisUser,
        403,
        'POST',
        'https://discord.com/api/v10/users/@me/channels',
        {}
      )
    );

    await expect(service.handleTerminalEvent({
      event_id: 'evt-closed',
      event_type: EventType.BULK_SCAN_PROCESSING_FINISHED,
      version: '1.0',
      timestamp: new Date().toISOString(),
      metadata: {},
      scan_id: 'scan-closed-123',
      community_server_id: 'community-123',
      messages_scanned: 12,
      messages_flagged: 0,
    })).resolves.toBeUndefined();

    expect(mockLogger.warn).toHaveBeenCalledWith(
      'Skipping stalled scan DM after permanent Discord failure',
      expect.objectContaining({
        scanId: 'scan-closed-123',
        initiatorId: 'user-123',
        error: expect.stringContaining('Cannot send messages to this user'),
      })
    );
    expect(stalledScanStore['vibecheck:stalled:scan-closed-123']).toEqual(
      expect.objectContaining({
        notificationState: 'failed_permanent',
      })
    );

    await expect(service.handleTerminalEvent({
      event_id: 'evt-closed-retry',
      event_type: EventType.BULK_SCAN_PROCESSING_FINISHED,
      version: '1.0',
      timestamp: new Date().toISOString(),
      metadata: {},
      scan_id: 'scan-closed-123',
      community_server_id: 'community-123',
      messages_scanned: 12,
      messages_flagged: 0,
    })).resolves.toBeUndefined();

    expect(mockUserSend).toHaveBeenCalledTimes(1);
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

  it('ignores replayed terminal events after delivery is already marked sent', async () => {
    stalledScanStore['vibecheck:stalled:scan-replayed-123'] = {
      scanId: 'scan-replayed-123',
      initiatorId: 'user-123',
      guildId: 'guild-123',
      days: 7,
      source: 'slash_command',
      notificationState: 'sent',
      notifiedAt: new Date().toISOString(),
    };

    await service.handleTerminalEvent({
      event_id: 'evt-replayed',
      event_type: EventType.BULK_SCAN_PROCESSING_FINISHED,
      version: '1.0',
      timestamp: new Date().toISOString(),
      metadata: {},
      scan_id: 'scan-replayed-123',
      community_server_id: 'community-123',
      messages_scanned: 33,
      messages_flagged: 1,
    });

    expect(mockUserSend).not.toHaveBeenCalled();
    expect(mockApiClient.getBulkScanResults).not.toHaveBeenCalled();
    expect(stalledScanStore['vibecheck:stalled:scan-replayed-123']).toEqual(
      expect.objectContaining({
        notificationState: 'sent',
      })
    );
  });

  it('reclaims an expired sending lease after a restart and delivers the replayed terminal event', async () => {
    const restartedService = new VibecheckStalledScanNotificationService({
      users: {
        fetch: mockUsersFetch,
      },
    } as any);

    stalledScanStore['vibecheck:stalled:scan-restart-123'] = {
      scanId: 'scan-restart-123',
      initiatorId: 'user-123',
      guildId: 'guild-123',
      days: 7,
      source: 'slash_command',
      notificationState: 'sending',
      deliveryClaimedAt: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    };
    mockApiClient.getBulkScanResults.mockResolvedValue({
      data: {
        type: 'bulk-scans',
        id: 'scan-restart-123',
        attributes: {
          status: 'completed',
          initiated_at: new Date().toISOString(),
          messages_scanned: 73,
          messages_flagged: 2,
        },
      },
      included: [],
      jsonapi: { version: '1.1' },
    });

    await restartedService.handleTerminalEvent({
      event_id: 'evt-restart-replay',
      event_type: EventType.BULK_SCAN_PROCESSING_FINISHED,
      version: '1.0',
      timestamp: new Date().toISOString(),
      metadata: {},
      scan_id: 'scan-restart-123',
      community_server_id: 'community-123',
      messages_scanned: 73,
      messages_flagged: 2,
    });

    expect(mockUserSend).toHaveBeenCalledTimes(1);
    expect(stalledScanStore['vibecheck:stalled:scan-restart-123']).toEqual(
      expect.objectContaining({
        notificationState: 'sent',
      })
    );
  });

  it('does not send duplicate DMs when a second worker reacquires delivery mid-send', async () => {
    const mockDistributedLock = {
      acquire: jest.fn<(...args: unknown[]) => Promise<boolean>>().mockResolvedValue(true),
      release: jest.fn<(...args: unknown[]) => Promise<boolean>>().mockResolvedValue(true),
      extend: jest.fn<(...args: unknown[]) => Promise<boolean>>().mockResolvedValue(true),
    };
    service = new VibecheckStalledScanNotificationService(
      {
        users: {
          fetch: mockUsersFetch,
        },
      } as any,
      mockDistributedLock as any
    );
    stalledScanStore['vibecheck:stalled:scan-lock-race-123'] = {
      scanId: 'scan-lock-race-123',
      initiatorId: 'user-123',
      guildId: 'guild-123',
      days: 7,
      source: 'slash_command',
    };
    mockApiClient.getBulkScanResults.mockResolvedValue({
      data: {
        type: 'bulk-scans',
        id: 'scan-lock-race-123',
        attributes: {
          status: 'completed',
          initiated_at: new Date().toISOString(),
          messages_scanned: 21,
          messages_flagged: 1,
        },
      },
      included: [],
      jsonapi: { version: '1.1' },
    });

    let releaseFirstSend!: () => void;
    mockUserSend.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          releaseFirstSend = resolve;
        })
    );

    const event = {
      event_id: 'evt-lock-race',
      event_type: EventType.BULK_SCAN_PROCESSING_FINISHED,
      version: '1.0',
      timestamp: new Date().toISOString(),
      metadata: {},
      scan_id: 'scan-lock-race-123',
      community_server_id: 'community-123',
      messages_scanned: 21,
      messages_flagged: 1,
    };

    const firstDelivery = service.handleTerminalEvent(event);
    while (!releaseFirstSend) {
      await Promise.resolve();
    }
    await service.handleTerminalEvent({
      ...event,
      event_id: 'evt-lock-race-retry',
    });
    releaseFirstSend();
    await firstDelivery;

    expect(mockUserSend).toHaveBeenCalledTimes(1);
  });
});
