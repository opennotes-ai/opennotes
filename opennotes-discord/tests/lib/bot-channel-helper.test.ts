import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import { ChannelType, Collection, MessageFlags } from 'discord.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const { checkBotChannel, getBotChannelOrRedirect, ensureBotChannel } = await import(
  '../../src/lib/bot-channel-helper.js'
);
const { BotChannelService } = await import('../../src/services/BotChannelService.js');

describe('bot-channel-helper', () => {
  let botChannelService: InstanceType<typeof BotChannelService>;
  let mockGuildConfigService: any;
  let mockInteraction: any;
  let mockGuild: any;
  let mockBotChannel: any;

  beforeEach(() => {
    botChannelService = new BotChannelService();

    mockBotChannel = {
      id: 'bot-channel-123',
      name: 'open-notes',
      type: ChannelType.GuildText,
      toString: () => '<#bot-channel-123>',
    };

    mockGuild = {
      id: 'guild-123',
      name: 'Test Guild',
      channels: {
        cache: new Collection([['bot-channel-123', mockBotChannel]]),
        create: jest.fn<(...args: any[]) => Promise<any>>(),
      },
      roles: {
        everyone: { id: 'everyone-role-id' },
        cache: new Collection(),
      },
      members: {
        me: { id: 'bot-123' },
      },
    };

    mockGuildConfigService = {
      get: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue('open-notes'),
    };

    mockInteraction = {
      guild: mockGuild,
      guildId: 'guild-123',
      channelId: 'bot-channel-123',
      user: { id: 'user-123' },
      commandName: 'list',
      deferred: false,
      reply: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
      editReply: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
    };
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('checkBotChannel', () => {
    it('should return isInBotChannel=true when user is in bot channel', async () => {
      const result = await checkBotChannel(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(result.isInBotChannel).toBe(true);
      expect(result.botChannel).toBe(mockBotChannel);
      expect(result.botChannelName).toBe('open-notes');
    });

    it('should return isInBotChannel=false when user is in different channel', async () => {
      mockInteraction.channelId = 'other-channel-456';

      const result = await checkBotChannel(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(result.isInBotChannel).toBe(false);
      expect(result.botChannel).toBe(mockBotChannel);
      expect(result.botChannelName).toBe('open-notes');
    });

    it('should return botChannel=null when bot channel does not exist', async () => {
      mockGuild.channels.cache = new Collection();

      const result = await checkBotChannel(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(result.isInBotChannel).toBe(false);
      expect(result.botChannel).toBeNull();
      expect(result.botChannelName).toBe('open-notes');
    });

    it('should return defaults when guild is null', async () => {
      mockInteraction.guild = null;

      const result = await checkBotChannel(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(result.isInBotChannel).toBe(false);
      expect(result.botChannel).toBeNull();
      expect(result.botChannelName).toBe('open-notes');
    });

    it('should use custom channel name from config', async () => {
      mockGuildConfigService.get.mockResolvedValue('custom-bot-channel');

      const customChannel = {
        id: 'custom-channel-789',
        name: 'custom-bot-channel',
        type: ChannelType.GuildText,
      };
      mockGuild.channels.cache = new Collection([['custom-channel-789', customChannel]]);
      mockInteraction.channelId = 'custom-channel-789';

      const result = await checkBotChannel(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(result.isInBotChannel).toBe(true);
      expect(result.botChannel).toBe(customChannel);
      expect(result.botChannelName).toBe('custom-bot-channel');
    });
  });

  describe('getBotChannelOrRedirect', () => {
    it('should return shouldProceed=true when in bot channel', async () => {
      const result = await getBotChannelOrRedirect(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(result.shouldProceed).toBe(true);
      expect(result.botChannel).toBe(mockBotChannel);
      expect(mockInteraction.reply).not.toHaveBeenCalled();
    });

    it('should redirect user when not in bot channel', async () => {
      mockInteraction.channelId = 'other-channel-456';

      const result = await getBotChannelOrRedirect(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(result.shouldProceed).toBe(false);
      expect(result.botChannel).toBe(mockBotChannel);
      expect(mockInteraction.reply).toHaveBeenCalledWith({
        content: expect.stringContaining('<#bot-channel-123>'),
        flags: MessageFlags.Ephemeral,
      });
    });

    it('should use editReply when interaction is deferred', async () => {
      mockInteraction.channelId = 'other-channel-456';
      mockInteraction.deferred = true;

      const result = await getBotChannelOrRedirect(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(result.shouldProceed).toBe(false);
      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: expect.stringContaining('<#bot-channel-123>'),
      });
      expect(mockInteraction.reply).not.toHaveBeenCalled();
    });

    it('should show error when bot channel not found', async () => {
      mockGuild.channels.cache = new Collection();

      const result = await getBotChannelOrRedirect(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(result.shouldProceed).toBe(false);
      expect(result.botChannel).toBeNull();
      expect(mockInteraction.reply).toHaveBeenCalledWith({
        content: expect.stringContaining('not found'),
        flags: MessageFlags.Ephemeral,
      });
    });

    it('should log when redirecting user', async () => {
      mockInteraction.channelId = 'other-channel-456';

      await getBotChannelOrRedirect(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(mockLogger.info).toHaveBeenCalledWith(
        expect.stringContaining('Redirecting'),
        expect.objectContaining({
          userId: 'user-123',
          guildId: 'guild-123',
          botChannelId: 'bot-channel-123',
        })
      );
    });

    it('should warn when bot channel not found', async () => {
      mockGuild.channels.cache = new Collection();

      await getBotChannelOrRedirect(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(mockLogger.warn).toHaveBeenCalledWith(
        expect.stringContaining('not found'),
        expect.objectContaining({
          userId: 'user-123',
          guildId: 'guild-123',
          expectedChannelName: 'open-notes',
        })
      );
    });
  });

  describe('ensureBotChannel', () => {
    it('should return channel when it exists', async () => {
      const mockEnsureResult = { channel: mockBotChannel, wasCreated: false };
      jest.spyOn(botChannelService, 'ensureChannelExists').mockResolvedValue(mockEnsureResult);

      const result = await ensureBotChannel(
        mockGuild,
        botChannelService,
        mockGuildConfigService
      );

      expect(result).toBe(mockBotChannel);
    });

    it('should return null when ensureChannelExists fails', async () => {
      jest.spyOn(botChannelService, 'ensureChannelExists').mockRejectedValue(
        new Error('Permission denied')
      );

      const result = await ensureBotChannel(
        mockGuild,
        botChannelService,
        mockGuildConfigService
      );

      expect(result).toBeNull();
      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to ensure bot channel'),
        expect.objectContaining({
          guildId: 'guild-123',
        })
      );
    });
  });
});
