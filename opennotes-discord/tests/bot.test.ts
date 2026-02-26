import { jest } from '@jest/globals';
import { Client } from 'discord.js';
import { loggerFactory, cacheFactory } from './factories/index.js';

const mockLogger = loggerFactory.build();
const mockCache = cacheFactory.build();

const mockCloseRedisClient = jest.fn<() => void>();
const mockGetRedisClient = jest.fn(() => null);

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

jest.unstable_mockModule('../src/config.js', () => ({
  config: {
    serverUrl: 'http://localhost:8000',
    discordToken: 'test-token',
    clientId: 'test-client-id',
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
        expect.objectContaining({ count: 8 })
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
