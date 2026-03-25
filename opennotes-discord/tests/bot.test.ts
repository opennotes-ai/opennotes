import { jest } from '@jest/globals';
import { Client } from 'discord.js';
import { loggerFactory, cacheFactory } from './factories/index.js';

const mockLogger = loggerFactory.build();
const mockCache = cacheFactory.build();

const mockCloseRedisClient = jest.fn<() => void>();
const mockGetRedisClient = jest.fn(() => null);
const mockConnectNats = jest.fn<() => Promise<void>>().mockResolvedValue(undefined);
const mockSubscribeToScoreUpdates = jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined);
const mockSubscribeToProgressUpdates = jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined);
const mockSubscribeToBulkScanTerminalUpdates = jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined);
const mockHandleScoreUpdate = jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined);
const mockHandleProgressEvent = jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined);
const mockHandleTerminalEvent = jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined);

const mockApiClient = {
  getCommunityServerByPlatformId: jest.fn<(...args: any[]) => Promise<any>>(),
  updateCommunityServerName: jest.fn<(...args: any[]) => Promise<any>>(),
  listMonitoredChannels: jest.fn<(...args: any[]) => Promise<any>>(),
  updateMonitoredChannel: jest.fn<(...args: any[]) => Promise<any>>(),
  healthCheck: jest.fn<() => Promise<any>>(),
};

jest.unstable_mockModule('../src/redis-client.js', () => ({
  getRedisClient: mockGetRedisClient,
  closeRedisClient: mockCloseRedisClient,
}));

jest.unstable_mockModule('../src/services/index.js', () => ({
  serviceProvider: {
    getRateLimitService: jest.fn(),
    getWriteNoteService: jest.fn(),
    getViewNotesService: jest.fn(),
    getRateNoteService: jest.fn(),
    getRequestNoteService: jest.fn(),
    getListRequestsService: jest.fn(),
    getStatusService: jest.fn(),
  },
}));

jest.unstable_mockModule('../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../src/events/NatsSubscriber.js', () => ({
  NatsSubscriber: class {
    connect = mockConnectNats;
    subscribeToScoreUpdates = mockSubscribeToScoreUpdates;
    subscribeToProgressUpdates = mockSubscribeToProgressUpdates;
    subscribeToBulkScanTerminalUpdates = mockSubscribeToBulkScanTerminalUpdates;
    close = jest.fn<() => Promise<void>>().mockResolvedValue(undefined);
    isConnected = jest.fn<() => boolean>().mockReturnValue(true);
  },
}));

jest.unstable_mockModule('../src/services/NotePublisherService.js', () => ({
  NotePublisherService: class {
    handleScoreUpdate = mockHandleScoreUpdate;
  },
}));

jest.unstable_mockModule('../src/services/VibecheckProgressService.js', () => ({
  VibecheckProgressService: class {
    handleProgressEvent = mockHandleProgressEvent;
  },
}));

jest.unstable_mockModule('../src/services/VibecheckStalledScanNotificationService.js', () => ({
  VibecheckStalledScanNotificationService: class {
    handleTerminalEvent = mockHandleTerminalEvent;
  },
}));

jest.unstable_mockModule('../src/config.js', () => ({
  config: {
    serverUrl: 'http://localhost:8000',
    discordToken: 'test-token',
    clientId: 'test-client-id',
    instanceId: 'test-instance',
    healthCheck: {
      enabled: false,
      port: 3100,
    },
  },
}));

jest.unstable_mockModule('../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

const { Bot } = await import('../src/bot.js');

describe('Bot', () => {
  let bot: any;

  beforeEach(() => {
    jest.clearAllMocks();
    bot = new Bot();
  });

  afterEach(async () => {
    if (bot && bot.isRunning()) {
      await bot.stop();
    }
  });

  describe('constructor', () => {
    it('should create a bot instance', () => {
      expect(bot).toBeDefined();
      expect(bot.isRunning()).toBe(false);
    });

    it('should load commands', () => {
      const client = bot.getClient();
      expect(client).toBeInstanceOf(Client);
    });
  });

  describe('command loading', () => {
    it('should have loaded all commands', () => {
      expect(mockLogger.info).toHaveBeenCalledWith(
        'Commands loaded',
        expect.objectContaining({ count: 9 })
      );
    });

    it('should load note command', () => {
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Loaded command',
        expect.objectContaining({ name: 'note' })
      );
    });

    it('should load config command', () => {
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Loaded command',
        expect.objectContaining({ name: 'config' })
      );
    });

    it('should load list command', () => {
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Loaded command',
        expect.objectContaining({ name: 'list' })
      );
    });

    it('should load status-bot command', () => {
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Loaded command',
        expect.objectContaining({ name: 'status-bot' })
      );
    });
  });

  describe('getClient', () => {
    it('should return the Discord client', () => {
      const client = bot.getClient();
      expect(client).toBeInstanceOf(Client);
    });
  });

  describe('isRunning', () => {
    it('should return false when bot is not started', () => {
      expect(bot.isRunning()).toBe(false);
    });
  });

  describe('stop', () => {
    it('should stop the bot gracefully', async () => {
      await bot.stop();

      expect(mockLogger.info).toHaveBeenCalledWith('Stopping bot');
      expect(mockCache.stop).toHaveBeenCalled();
      expect(bot.isRunning()).toBe(false);
    });

    it('should close Redis client during shutdown', async () => {
      await bot.stop();

      expect(mockCloseRedisClient).toHaveBeenCalled();
      expect(mockLogger.info).toHaveBeenCalledWith('Redis client closed');
    });
  });

  describe('initializeNotePublisher', () => {
    it('registers stalled scan notification handling during note publisher init', async () => {
      await (bot as any).initializeNotePublisher();

      expect(mockSubscribeToBulkScanTerminalUpdates).toHaveBeenCalledWith(expect.any(Function));
      expect((bot as any).getTerminalSubscriptionHealth()).toEqual({
        status: 'ready',
      });
    });

    it('degrades stalled scan notification startup when terminal subscription fails', async () => {
      (bot as any).isReady = true;
      mockSubscribeToBulkScanTerminalUpdates.mockRejectedValueOnce(
        new Error('terminal consumer unavailable')
      );

      await expect((bot as any).initializeNotePublisher()).resolves.toBeUndefined();

      expect(mockConnectNats).toHaveBeenCalledTimes(1);
      expect(mockSubscribeToScoreUpdates).toHaveBeenCalledWith(expect.any(Function));
      expect(mockSubscribeToProgressUpdates).toHaveBeenCalledWith(expect.any(Function));
      expect(mockSubscribeToBulkScanTerminalUpdates).toHaveBeenCalledWith(expect.any(Function));
      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Vibecheck stalled scan notification service degraded - terminal event subscription unavailable',
        expect.objectContaining({
          error: 'terminal consumer unavailable',
        })
      );
      expect((bot as any).getHealthStatus()).toBe('degraded');
      expect((bot as any).getReadinessState()).toEqual({
        ready: false,
        reason: 'bulk_scan_terminal_subscriptions_degraded',
        terminalSubscriptions: {
          status: 'degraded',
          error: 'terminal consumer unavailable',
        },
      });
    });

    it('reports terminal subscription readiness through distributed health checks', async () => {
      (bot as any).isReady = true;

      await (bot as any).initializeNotePublisher();

      await expect((bot as any).buildDistributedHealthSnapshot()).resolves.toEqual({
        allHealthy: true,
        checks: expect.objectContaining({
          instance: 'test-instance',
          bulk_scan_terminal_subscriptions: 'ready',
          nats: 'connected',
          redis: 'not_configured',
          distributed_lock: 'redis_unavailable',
        }),
      });
    });

    it('marks distributed health degraded when terminal subscriptions are unavailable', async () => {
      (bot as any).isReady = true;
      mockSubscribeToBulkScanTerminalUpdates.mockRejectedValueOnce(
        new Error('terminal consumer unavailable')
      );

      await (bot as any).initializeNotePublisher();

      await expect((bot as any).buildDistributedHealthSnapshot()).resolves.toEqual({
        allHealthy: false,
        checks: expect.objectContaining({
          instance: 'test-instance',
          bulk_scan_terminal_subscriptions: 'degraded',
          bulk_scan_terminal_subscription_error: 'terminal consumer unavailable',
          nats: 'connected',
          redis: 'not_configured',
          distributed_lock: 'redis_unavailable',
        }),
      });
    });
  });

  describe('syncCommunityNames', () => {
    const GUILD_SNOWFLAKE = '123456789012345678';
    const COMMUNITY_SERVER_UUID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';
    const CHANNEL_ID = '987654321098765432';

    beforeEach(() => {
      mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
        data: {
          type: 'community-servers',
          id: COMMUNITY_SERVER_UUID,
          attributes: {
            platform: 'discord',
            platform_community_server_id: GUILD_SNOWFLAKE,
            name: 'Test Guild',
            is_active: true,
            is_public: true,
            flashpoint_detection_enabled: false,
          },
        },
        jsonapi: { version: '1.1' },
      });
      mockApiClient.updateCommunityServerName.mockResolvedValue(undefined);
    });

    afterEach(() => {
      const client = bot.getClient();
      client.guilds.cache.clear();
    });

    it('should pass guild snowflake to listMonitoredChannels', async () => {
      const client = bot.getClient();
      client.guilds.cache.set(GUILD_SNOWFLAKE, {
        id: GUILD_SNOWFLAKE,
        name: 'Test Guild',
        memberCount: 50,
      } as any);

      mockApiClient.listMonitoredChannels.mockResolvedValue({
        data: [],
        jsonapi: { version: '1.1' },
      });

      await (bot as any).syncCommunityNames();

      expect(mockApiClient.listMonitoredChannels).toHaveBeenCalledWith(
        GUILD_SNOWFLAKE,
        false
      );
      expect(mockApiClient.listMonitoredChannels).not.toHaveBeenCalledWith(
        COMMUNITY_SERVER_UUID,
        expect.anything()
      );
    });

    it('should pass guild snowflake to updateMonitoredChannel', async () => {
      const client = bot.getClient();
      client.guilds.cache.set(GUILD_SNOWFLAKE, {
        id: GUILD_SNOWFLAKE,
        name: 'Test Guild',
        memberCount: 50,
      } as any);

      mockApiClient.listMonitoredChannels.mockResolvedValue({
        data: [
          {
            type: 'monitored-channels',
            id: 'mc-uuid-1',
            attributes: {
              community_server_id: COMMUNITY_SERVER_UUID,
              channel_id: CHANNEL_ID,
              name: 'old-channel-name',
              enabled: true,
              similarity_threshold: 0.8,
              dataset_tags: [],
            },
          },
        ],
        jsonapi: { version: '1.1' },
      });

      jest.spyOn(client.channels, 'fetch').mockResolvedValue({
        id: CHANNEL_ID,
        name: 'new-channel-name',
      } as any);

      mockApiClient.updateMonitoredChannel.mockResolvedValue(null);

      await (bot as any).syncCommunityNames();

      expect(mockApiClient.updateMonitoredChannel).toHaveBeenCalledWith(
        CHANNEL_ID,
        { name: 'new-channel-name' },
        undefined,
        GUILD_SNOWFLAKE
      );
      expect(mockApiClient.updateMonitoredChannel).not.toHaveBeenCalledWith(
        expect.anything(),
        expect.anything(),
        expect.anything(),
        COMMUNITY_SERVER_UUID
      );
    });
  });
});
