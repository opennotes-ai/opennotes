import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import { ChannelType, Events } from 'discord.js';

const mockLogger = {
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  info: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

const mockGuildConfigService = {
  get: jest.fn<(guildId: string, key: string) => Promise<string>>(),
  set: jest.fn<(guildId: string, key: string, value: string, updatedBy: string) => Promise<void>>(),
};

const mockCache = {
  get: jest.fn<(key: string) => unknown>(),
  set: jest.fn<(key: string, value: unknown, ttl?: number) => void>(),
  delete: jest.fn<(key: string) => void>(),
  start: jest.fn<() => void>(),
  stop: jest.fn<() => void>(),
};

const mockCloseRedisClient = jest.fn<() => void>();
const mockGetRedisClient = jest.fn(() => null);

jest.unstable_mockModule('../../src/redis-client.js', () => ({
  getRedisClient: mockGetRedisClient,
  closeRedisClient: mockCloseRedisClient,
}));

jest.unstable_mockModule('../../src/services/index.js', () => ({
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

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../../src/config.js', () => ({
  config: {
    serverUrl: 'http://localhost:8000',
    discordToken: 'test-token',
    clientId: 'test-client-id',
  },
}));

const { Bot } = await import('../../src/bot.js');

describe('Bot Channel Update Handler', () => {
  let bot: InstanceType<typeof Bot>;

  beforeEach(() => {
    jest.clearAllMocks();
    bot = new Bot();
  });

  afterEach(async () => {
    if (bot && bot.isRunning()) {
      await bot.stop();
    }
  });

  describe('onChannelUpdate', () => {
    it('should update bot channel config when bot channel is renamed', async () => {
      const guildId = '123456789';
      const oldChannelName = 'open-notes';
      const newChannelName = 'bot-channel';

      mockGuildConfigService.get.mockResolvedValue(oldChannelName);
      mockGuildConfigService.set.mockResolvedValue(undefined);

      const mockGuild = {
        id: guildId,
        name: 'Test Guild',
      };

      const oldChannel = {
        id: 'channel-123',
        name: oldChannelName,
        type: ChannelType.GuildText,
        guild: mockGuild,
        isDMBased: () => false,
      };

      const newChannel = {
        id: 'channel-123',
        name: newChannelName,
        type: ChannelType.GuildText,
        guild: mockGuild,
        isDMBased: () => false,
      };

      // Access the private method via the exposed handler
      // @ts-expect-error - accessing private method for testing
      bot.guildConfigService = mockGuildConfigService;
      // @ts-expect-error - accessing private method for testing
      await bot.onChannelUpdate(oldChannel, newChannel);

      expect(mockGuildConfigService.get).toHaveBeenCalledWith(guildId, 'bot_channel_name');
      expect(mockGuildConfigService.set).toHaveBeenCalledWith(
        guildId,
        'bot_channel_name',
        newChannelName,
        'system'
      );
      expect(mockLogger.info).toHaveBeenCalledWith(
        'Bot channel renamed - config updated',
        expect.objectContaining({
          guildId,
          oldName: oldChannelName,
          newName: newChannelName,
        })
      );
    });

    it('should not update config when non-bot channel is renamed', async () => {
      const guildId = '123456789';
      const configuredBotChannel = 'open-notes';

      mockGuildConfigService.get.mockResolvedValue(configuredBotChannel);

      const mockGuild = {
        id: guildId,
        name: 'Test Guild',
      };

      const oldChannel = {
        id: 'channel-456',
        name: 'general',
        type: ChannelType.GuildText,
        guild: mockGuild,
        isDMBased: () => false,
      };

      const newChannel = {
        id: 'channel-456',
        name: 'general-chat',
        type: ChannelType.GuildText,
        guild: mockGuild,
        isDMBased: () => false,
      };

      // @ts-expect-error - accessing private method for testing
      bot.guildConfigService = mockGuildConfigService;
      // @ts-expect-error - accessing private method for testing
      await bot.onChannelUpdate(oldChannel, newChannel);

      expect(mockGuildConfigService.get).toHaveBeenCalledWith(guildId, 'bot_channel_name');
      expect(mockGuildConfigService.set).not.toHaveBeenCalled();
    });

    it('should not process DM channels', async () => {
      const oldChannel = {
        id: 'dm-123',
        name: 'DM Channel',
        isDMBased: () => true,
      };

      const newChannel = {
        id: 'dm-123',
        name: 'DM Channel Renamed',
        isDMBased: () => true,
      };

      // @ts-expect-error - accessing private method for testing
      bot.guildConfigService = mockGuildConfigService;
      // @ts-expect-error - accessing private method for testing
      await bot.onChannelUpdate(oldChannel, newChannel);

      expect(mockGuildConfigService.get).not.toHaveBeenCalled();
      expect(mockGuildConfigService.set).not.toHaveBeenCalled();
    });

    it('should not process when channel name has not changed', async () => {
      const mockGuild = {
        id: '123456789',
        name: 'Test Guild',
      };

      const oldChannel = {
        id: 'channel-123',
        name: 'open-notes',
        type: ChannelType.GuildText,
        guild: mockGuild,
        isDMBased: () => false,
      };

      const newChannel = {
        id: 'channel-123',
        name: 'open-notes',
        type: ChannelType.GuildText,
        guild: mockGuild,
        isDMBased: () => false,
      };

      // @ts-expect-error - accessing private method for testing
      bot.guildConfigService = mockGuildConfigService;
      // @ts-expect-error - accessing private method for testing
      await bot.onChannelUpdate(oldChannel, newChannel);

      expect(mockGuildConfigService.get).not.toHaveBeenCalled();
      expect(mockGuildConfigService.set).not.toHaveBeenCalled();
    });

    it('should not process non-text channels', async () => {
      const mockGuild = {
        id: '123456789',
        name: 'Test Guild',
      };

      const oldChannel = {
        id: 'voice-123',
        name: 'Voice Channel',
        type: ChannelType.GuildVoice,
        guild: mockGuild,
        isDMBased: () => false,
      };

      const newChannel = {
        id: 'voice-123',
        name: 'Voice Channel Renamed',
        type: ChannelType.GuildVoice,
        guild: mockGuild,
        isDMBased: () => false,
      };

      // @ts-expect-error - accessing private method for testing
      bot.guildConfigService = mockGuildConfigService;
      // @ts-expect-error - accessing private method for testing
      await bot.onChannelUpdate(oldChannel, newChannel);

      expect(mockGuildConfigService.get).not.toHaveBeenCalled();
      expect(mockGuildConfigService.set).not.toHaveBeenCalled();
    });

    it('should handle guildConfigService not initialized', async () => {
      const mockGuild = {
        id: '123456789',
        name: 'Test Guild',
      };

      const oldChannel = {
        id: 'channel-123',
        name: 'open-notes',
        type: ChannelType.GuildText,
        guild: mockGuild,
        isDMBased: () => false,
      };

      const newChannel = {
        id: 'channel-123',
        name: 'bot-channel',
        type: ChannelType.GuildText,
        guild: mockGuild,
        isDMBased: () => false,
      };

      // guildConfigService is undefined by default
      // @ts-expect-error - accessing private method for testing
      await bot.onChannelUpdate(oldChannel, newChannel);

      // Should not throw and should not try to access the service
      expect(mockGuildConfigService.get).not.toHaveBeenCalled();
      expect(mockGuildConfigService.set).not.toHaveBeenCalled();
    });

    it('should handle API errors gracefully', async () => {
      const guildId = '123456789';
      const oldChannelName = 'open-notes';
      const newChannelName = 'bot-channel';

      mockGuildConfigService.get.mockResolvedValue(oldChannelName);
      mockGuildConfigService.set.mockRejectedValue(new Error('API Error'));

      const mockGuild = {
        id: guildId,
        name: 'Test Guild',
      };

      const oldChannel = {
        id: 'channel-123',
        name: oldChannelName,
        type: ChannelType.GuildText,
        guild: mockGuild,
        isDMBased: () => false,
      };

      const newChannel = {
        id: 'channel-123',
        name: newChannelName,
        type: ChannelType.GuildText,
        guild: mockGuild,
        isDMBased: () => false,
      };

      // @ts-expect-error - accessing private method for testing
      bot.guildConfigService = mockGuildConfigService;
      // @ts-expect-error - accessing private method for testing
      await bot.onChannelUpdate(oldChannel, newChannel);

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to update bot channel config after rename',
        expect.objectContaining({
          guildId,
          oldName: oldChannelName,
          newName: newChannelName,
          error: 'API Error',
        })
      );
    });

    it('should be case-insensitive when comparing channel names', async () => {
      const guildId = '123456789';
      const configuredBotChannel = 'Open-Notes';
      const oldChannelName = 'open-notes';
      const newChannelName = 'bot-channel';

      mockGuildConfigService.get.mockResolvedValue(configuredBotChannel);
      mockGuildConfigService.set.mockResolvedValue(undefined);

      const mockGuild = {
        id: guildId,
        name: 'Test Guild',
      };

      const oldChannel = {
        id: 'channel-123',
        name: oldChannelName,
        type: ChannelType.GuildText,
        guild: mockGuild,
        isDMBased: () => false,
      };

      const newChannel = {
        id: 'channel-123',
        name: newChannelName,
        type: ChannelType.GuildText,
        guild: mockGuild,
        isDMBased: () => false,
      };

      // @ts-expect-error - accessing private method for testing
      bot.guildConfigService = mockGuildConfigService;
      // @ts-expect-error - accessing private method for testing
      await bot.onChannelUpdate(oldChannel, newChannel);

      expect(mockGuildConfigService.set).toHaveBeenCalledWith(
        guildId,
        'bot_channel_name',
        newChannelName,
        'system'
      );
    });
  });
});
