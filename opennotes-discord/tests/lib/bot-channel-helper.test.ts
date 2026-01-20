import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import { Collection, ChannelType, MessageFlags, PermissionFlagsBits } from 'discord.js';
import {
  discordChannelFactory,
  discordGuildFactory,
  discordMemberFactory,
  discordUserFactory,
  chatInputCommandInteractionFactory,
  loggerFactory,
} from '../factories/index.js';

const mockLogger = loggerFactory.build();

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

  function createMockBotChannel(id = 'bot-channel-123', name = 'open-notes') {
    return {
      ...discordChannelFactory.build({
        id,
        name,
        type: ChannelType.GuildText,
      }),
      toString: () => `<#${id}>`,
    };
  }

  function createMockGuild(
    id = 'guild-123',
    name = 'Test Guild',
    channels: any[] = [],
    options: { fullMode?: boolean } = {}
  ) {
    const { fullMode = false } = options;

    const botMember = fullMode
      ? discordMemberFactory.build(
          {},
          {
            transient: {
              permissionOverrides: {
                [PermissionFlagsBits.ManageChannels.toString()]: true,
                [PermissionFlagsBits.ManageMessages.toString()]: true,
              },
            },
            associations: {
              user: discordUserFactory.build({
                id: 'bot-user',
                username: 'OpenNotesBot',
                bot: true,
              }),
            },
          }
        )
      : undefined;

    const guild = discordGuildFactory.build(
      { id, name },
      { transient: { botMember } }
    );
    for (const channel of channels) {
      guild.channels.cache.set(channel.id, channel);
    }
    return guild;
  }

  function createMockInteraction(
    overrides: {
      guild?: any;
      guildId?: string | null;
      channelId?: string | null;
      commandName?: string;
      isDeferred?: boolean;
      isReplied?: boolean;
    } = {}
  ): any {
    const {
      guild,
      guildId = guild?.id ?? 'guild-123',
      channelId = 'bot-channel-123',
      commandName = 'list',
      isDeferred = false,
      isReplied = false,
    } = overrides;

    const baseInteraction = chatInputCommandInteractionFactory.build(
      { commandName },
      { transient: { isDeferred, isReplied } }
    );

    return {
      ...baseInteraction,
      guild,
      guildId,
      channelId,
    };
  }

  beforeEach(() => {
    botChannelService = new BotChannelService();
    mockGuildConfigService = {
      get: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue('open-notes'),
    };
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('checkBotChannel', () => {
    it('should return isInBotChannel=true when user is in bot channel', async () => {
      const mockBotChannel = createMockBotChannel();
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [mockBotChannel]);
      const mockInteraction = createMockInteraction({ guild: mockGuild, channelId: 'bot-channel-123' });

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
      const mockBotChannel = createMockBotChannel();
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [mockBotChannel]);
      const mockInteraction = createMockInteraction({ guild: mockGuild, channelId: 'other-channel-456' });

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
      const mockGuild = createMockGuild('guild-123', 'Test Guild', []);
      const mockInteraction = createMockInteraction({ guild: mockGuild });

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
      const mockInteraction = createMockInteraction({ guild: null, guildId: null });

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
      const customChannel = createMockBotChannel('custom-channel-789', 'custom-bot-channel');
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [customChannel]);
      const mockInteraction = createMockInteraction({ guild: mockGuild, channelId: 'custom-channel-789' });

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
      const mockBotChannel = createMockBotChannel();
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [mockBotChannel]);
      const mockInteraction = createMockInteraction({ guild: mockGuild, channelId: 'bot-channel-123' });

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
      const mockBotChannel = createMockBotChannel();
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [mockBotChannel]);
      const mockInteraction = createMockInteraction({ guild: mockGuild, channelId: 'other-channel-456' });

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
      const mockBotChannel = createMockBotChannel();
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [mockBotChannel]);
      const mockInteraction = createMockInteraction({
        guild: mockGuild,
        channelId: 'other-channel-456',
        isDeferred: true,
      });

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

    it('should use editReply when interaction is already replied', async () => {
      const mockBotChannel = createMockBotChannel();
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [mockBotChannel]);
      const mockInteraction = createMockInteraction({
        guild: mockGuild,
        channelId: 'other-channel-456',
        isReplied: true,
        isDeferred: false,
      });

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

    it('should use editReply for bot channel not found when interaction is replied (full mode)', async () => {
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [], { fullMode: true });
      const mockInteraction = createMockInteraction({
        guild: mockGuild,
        isReplied: true,
        isDeferred: false,
      });

      const result = await getBotChannelOrRedirect(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(result.shouldProceed).toBe(false);
      expect(result.botChannel).toBeNull();
      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: expect.stringContaining('not found'),
      });
      expect(mockInteraction.reply).not.toHaveBeenCalled();
    });

    it('should show error when bot channel not found (full mode)', async () => {
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [], { fullMode: true });
      const mockInteraction = createMockInteraction({ guild: mockGuild });

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

    it('should allow command to proceed when bot channel not found (minimal mode)', async () => {
      const mockGuild = createMockGuild('guild-123', 'Test Guild', []);
      const mockInteraction = createMockInteraction({ guild: mockGuild });

      const result = await getBotChannelOrRedirect(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(result.shouldProceed).toBe(true);
      expect(result.botChannel).toBeNull();
      expect(mockInteraction.reply).not.toHaveBeenCalled();
    });

    it('should log when redirecting user', async () => {
      const mockBotChannel = createMockBotChannel();
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [mockBotChannel]);
      const mockInteraction = createMockInteraction({ guild: mockGuild, channelId: 'other-channel-456' });

      await getBotChannelOrRedirect(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(mockLogger.info).toHaveBeenCalledWith(
        expect.stringContaining('Redirecting'),
        expect.objectContaining({
          userId: mockInteraction.user.id,
          guildId: 'guild-123',
          botChannelId: 'bot-channel-123',
        })
      );
    });

    it('should warn when bot channel not found (full mode)', async () => {
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [], { fullMode: true });
      const mockInteraction = createMockInteraction({ guild: mockGuild });

      await getBotChannelOrRedirect(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(mockLogger.warn).toHaveBeenCalledWith(
        expect.stringContaining('not found'),
        expect.objectContaining({
          userId: mockInteraction.user.id,
          guildId: 'guild-123',
          expectedChannelName: 'open-notes',
        })
      );
    });

    it('should log debug when allowing command in minimal mode without bot channel', async () => {
      const mockGuild = createMockGuild('guild-123', 'Test Guild', []);
      const mockInteraction = createMockInteraction({ guild: mockGuild });

      await getBotChannelOrRedirect(
        mockInteraction,
        botChannelService,
        mockGuildConfigService
      );

      expect(mockLogger.debug).toHaveBeenCalledWith(
        expect.stringContaining('minimal mode'),
        expect.objectContaining({
          userId: mockInteraction.user.id,
          guildId: 'guild-123',
        })
      );
    });

    it('should log error and re-throw when reply fails', async () => {
      const mockBotChannel = createMockBotChannel();
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [mockBotChannel]);
      const mockInteraction = createMockInteraction({ guild: mockGuild, channelId: 'other-channel-456' });
      const replyError = new Error('Discord API error');
      mockInteraction.reply.mockRejectedValue(replyError);

      await expect(
        getBotChannelOrRedirect(mockInteraction, botChannelService, mockGuildConfigService)
      ).rejects.toThrow('Discord API error');

      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to reply'),
        expect.objectContaining({
          guildId: 'guild-123',
          userId: mockInteraction.user.id,
        })
      );
    });

    it('should log error and re-throw when editReply fails', async () => {
      const mockBotChannel = createMockBotChannel();
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [mockBotChannel]);
      const mockInteraction = createMockInteraction({
        guild: mockGuild,
        channelId: 'other-channel-456',
        isDeferred: true,
      });
      const editError = new Error('Interaction expired');
      mockInteraction.editReply.mockRejectedValue(editError);

      await expect(
        getBotChannelOrRedirect(mockInteraction, botChannelService, mockGuildConfigService)
      ).rejects.toThrow('Interaction expired');

      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to reply'),
        expect.objectContaining({
          guildId: 'guild-123',
          userId: mockInteraction.user.id,
        })
      );
    });

    it('should include command and channel context in error logs', async () => {
      const mockBotChannel = createMockBotChannel();
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [mockBotChannel]);
      const mockInteraction = createMockInteraction({
        guild: mockGuild,
        channelId: 'other-channel-456',
        commandName: 'test-command',
      });
      const replyError = new Error('API timeout');
      mockInteraction.reply.mockRejectedValue(replyError);

      await expect(
        getBotChannelOrRedirect(mockInteraction, botChannelService, mockGuildConfigService)
      ).rejects.toThrow('API timeout');

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to reply to interaction',
        expect.objectContaining({
          guildId: 'guild-123',
          userId: mockInteraction.user.id,
          channelId: 'other-channel-456',
          command: 'test-command',
          error: 'API timeout',
        })
      );
    });
  });

  describe('ensureBotChannel', () => {
    it('should return channel when it exists', async () => {
      const mockBotChannel = createMockBotChannel();
      const mockGuild = createMockGuild('guild-123', 'Test Guild', [mockBotChannel]);
      const mockEnsureResult = { channel: mockBotChannel, wasCreated: false };
      jest.spyOn(botChannelService, 'ensureChannelExists').mockResolvedValue(mockEnsureResult as any);

      const result = await ensureBotChannel(
        mockGuild as any,
        botChannelService,
        mockGuildConfigService
      );

      expect(result).toBe(mockBotChannel);
    });

    it('should return null when ensureChannelExists fails', async () => {
      const mockGuild = createMockGuild('guild-123', 'Test Guild', []);
      jest.spyOn(botChannelService, 'ensureChannelExists').mockRejectedValue(
        new Error('Permission denied')
      );

      const result = await ensureBotChannel(
        mockGuild as any,
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
