import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import { ChannelType, Collection, ComponentType, MessageFlags, MessageType } from 'discord.js';
import {
  loggerFactory,
  discordGuildFactory,
  discordChannelFactory,
  discordMemberFactory,
} from '../factories/index.js';

const mockLogger = loggerFactory.build();

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const { BotChannelService } = await import('../../src/services/BotChannelService.js');
const { GuildOnboardingService } = await import('../../src/services/GuildOnboardingService.js');
const { buildWelcomeContainer, WELCOME_MESSAGE_REVISION } = await import('../../src/lib/welcome-content.js');

// Helper to create FetchPinnedMessagesResponse format (Discord.js v14.25+)
function createMockPinsResponse(messages: any[]) {
  return {
    hasMore: false,
    items: messages.map((msg) => ({
      message: msg,
      pinnedAt: new Date(),
      pinnedTimestamp: Date.now(),
    })),
  };
}

describe('Bot Channel Welcome Flow Integration', () => {
  let botChannelService: InstanceType<typeof BotChannelService>;
  let guildOnboardingService: InstanceType<typeof GuildOnboardingService>;
  let mockGuild: any;
  let mockChannel: any;
  let mockRole: any;
  let mockBotMember: any;
  let mockGuildConfigService: any;

  beforeEach(() => {
    botChannelService = new BotChannelService();
    guildOnboardingService = new GuildOnboardingService();

    mockRole = {
      id: 'role-123',
      name: 'OpenNotes',
    };

    mockBotMember = {
      id: 'bot-123',
      user: {
        id: 'bot-user-123',
      },
    };

    const mockBotUser = {
      id: 'bot-user-123',
      username: 'OpenNotes',
      bot: true,
    };

    mockChannel = {
      id: 'channel-123',
      name: 'open-notes',
      type: ChannelType.GuildText,
      guild: null,
      client: {
        user: mockBotUser,
      },
      send: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
      delete: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
      permissionOverwrites: {
        set: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
      },
      messages: {
        fetchPins: jest.fn<() => Promise<any>>().mockResolvedValue(createMockPinsResponse([])),
        fetch: jest.fn<() => Promise<any>>().mockResolvedValue(new Collection()),
      },
    };

    mockGuild = {
      id: 'guild-123',
      name: 'Test Guild',
      roles: {
        everyone: { id: 'everyone-role-id' },
        cache: new Collection([['role-123', mockRole]]),
      },
      channels: {
        cache: new Collection<string, any>(),
        create: jest.fn<(...args: any[]) => Promise<any>>(),
      },
      members: {
        me: mockBotMember,
      },
    };

    mockChannel.guild = mockGuild;
    mockGuild.channels.create.mockResolvedValue(mockChannel);

    mockGuildConfigService = {
      get: jest.fn<(...args: any[]) => Promise<any>>()
        .mockResolvedValueOnce('open-notes')
        .mockResolvedValueOnce('OpenNotes'),
    };
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('Guild Join Flow', () => {
    it('should create bot channel on guild join', async () => {
      const result = await botChannelService.ensureChannelExists(
        mockGuild,
        mockGuildConfigService
      );

      expect(result.wasCreated).toBe(true);
      expect(result.channel).toBe(mockChannel);
      expect(mockGuild.channels.create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'open-notes',
          type: ChannelType.GuildText,
        })
      );
    });

    it('should post welcome message after channel creation', async () => {
      const result = await botChannelService.ensureChannelExists(
        mockGuild,
        mockGuildConfigService
      );

      expect(result.wasCreated).toBe(true);

      await guildOnboardingService.postWelcomeToChannel(result.channel);

      expect(mockChannel.send).toHaveBeenCalledTimes(1);
      const sendCall = mockChannel.send.mock.calls[0][0];
      expect(sendCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
      expect(sendCall.flags & MessageFlags.Ephemeral).toBeFalsy();
    });

    it('should not create duplicate channel if one exists', async () => {
      mockGuild.channels.cache.set('channel-123', mockChannel);

      mockGuildConfigService.get.mockReset();
      mockGuildConfigService.get.mockResolvedValue('open-notes');

      const result = await botChannelService.ensureChannelExists(
        mockGuild,
        mockGuildConfigService
      );

      expect(result.wasCreated).toBe(false);
      expect(result.channel).toBe(mockChannel);
      expect(mockGuild.channels.create).not.toHaveBeenCalled();
    });

    it('should set up proper permissions on new channel', async () => {
      const result = await botChannelService.ensureChannelExists(
        mockGuild,
        mockGuildConfigService
      );

      expect(result.wasCreated).toBe(true);
      expect(mockChannel.permissionOverwrites.set).toHaveBeenCalled();
    });
  });

  describe('Bot Startup Flow', () => {
    it('should find existing channel on startup', async () => {
      mockGuild.channels.cache.set('channel-123', mockChannel);
      mockGuildConfigService.get.mockReset();
      mockGuildConfigService.get.mockResolvedValue('open-notes');

      const result = await botChannelService.ensureChannelExists(
        mockGuild,
        mockGuildConfigService
      );

      expect(result.wasCreated).toBe(false);
      expect(result.channel).toBe(mockChannel);
    });

    it('should create channel and post welcome if channel was deleted', async () => {
      mockGuildConfigService.get.mockReset();
      mockGuildConfigService.get
        .mockResolvedValueOnce('open-notes')
        .mockResolvedValueOnce('OpenNotes');

      const result = await botChannelService.ensureChannelExists(
        mockGuild,
        mockGuildConfigService
      );

      expect(result.wasCreated).toBe(true);

      await guildOnboardingService.postWelcomeToChannel(result.channel);

      expect(mockChannel.send).toHaveBeenCalledTimes(1);
    });
  });

  describe('Welcome Message Content', () => {
    it('should include all required sections in welcome message', async () => {
      const result = await botChannelService.ensureChannelExists(
        mockGuild,
        mockGuildConfigService
      );

      await guildOnboardingService.postWelcomeToChannel(result.channel);

      const sendCall = mockChannel.send.mock.calls[0][0];
      const container = sendCall.components[0];
      const allContent = JSON.stringify(container.toJSON().components);

      expect(allContent).toContain('About OpenNotes');
      expect(allContent).toContain('How It Works');
      expect(allContent).toContain('Note Submission');
      expect(allContent).toContain('Commands');
      expect(allContent).toContain('Scoring System');
      expect(allContent).toContain('Community Moderation');
    });

    it('should use same content as about-opennotes command', async () => {
      const commandContainer = buildWelcomeContainer();

      await guildOnboardingService.postWelcomeToChannel(mockChannel);

      const sendCall = mockChannel.send.mock.calls[0][0];
      const welcomeContainer = sendCall.components[0];

      const commandContent = JSON.stringify(commandContainer.toJSON().components);
      const welcomeContent = JSON.stringify(welcomeContainer.toJSON().components);

      expect(welcomeContent).toBe(commandContent);
    });
  });

  describe('Error Handling', () => {
    it('should handle channel creation failure gracefully', async () => {
      mockGuild.channels.create.mockRejectedValue(new Error('Missing permissions'));

      await expect(
        botChannelService.ensureChannelExists(mockGuild, mockGuildConfigService)
      ).rejects.toThrow('Missing permissions');

      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to create bot channel'),
        expect.any(Object)
      );
    });

    it('should handle welcome message send failure gracefully', async () => {
      mockChannel.send.mockRejectedValue(new Error('Channel not accessible'));

      await expect(
        guildOnboardingService.postWelcomeToChannel(mockChannel)
      ).resolves.not.toThrow();

      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to post welcome message'),
        expect.objectContaining({
          channelId: 'channel-123',
          error: 'Channel not accessible',
        })
      );
    });

    it('should continue with other guilds if one fails on startup', async () => {
      // Reset mock to clear beforeEach values
      mockGuildConfigService.get.mockReset();

      const failingGuild = {
        ...mockGuild,
        id: 'failing-guild',
        channels: {
          cache: new Collection<string, any>(),
          create: jest.fn<(...args: any[]) => Promise<any>>()
            .mockRejectedValue(new Error('Guild error')),
        },
      };

      // Failing guild only consumes 1 mock value (channel name) before throwing
      mockGuildConfigService.get.mockResolvedValueOnce('open-notes');

      await expect(
        botChannelService.ensureChannelExists(failingGuild, mockGuildConfigService)
      ).rejects.toThrow('Guild error');

      // Second guild needs both channel name and role name
      mockGuildConfigService.get
        .mockResolvedValueOnce('open-notes')
        .mockResolvedValueOnce('opennotes');
      const secondGuild = { ...mockGuild, id: 'second-guild' };
      secondGuild.channels = {
        cache: new Collection<string, any>(),
        create: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(mockChannel),
      };

      const result = await botChannelService.ensureChannelExists(
        secondGuild,
        mockGuildConfigService
      );

      expect(result.wasCreated).toBe(true);
    });
  });

  describe('Idempotency', () => {
    it('should be idempotent when channel exists', async () => {
      mockGuild.channels.cache.set('channel-123', mockChannel);
      mockGuildConfigService.get.mockReset();
      mockGuildConfigService.get.mockResolvedValue('open-notes');

      const result1 = await botChannelService.ensureChannelExists(
        mockGuild,
        mockGuildConfigService
      );
      const result2 = await botChannelService.ensureChannelExists(
        mockGuild,
        mockGuildConfigService
      );
      const result3 = await botChannelService.ensureChannelExists(
        mockGuild,
        mockGuildConfigService
      );

      expect(result1.wasCreated).toBe(false);
      expect(result2.wasCreated).toBe(false);
      expect(result3.wasCreated).toBe(false);
      expect(result1.channel).toBe(result2.channel);
      expect(result2.channel).toBe(result3.channel);
      expect(mockGuild.channels.create).not.toHaveBeenCalled();
    });

    it('should handle case-insensitive channel name matching', async () => {
      const upperCaseChannel = { ...mockChannel, name: 'OPEN-NOTES' };
      mockGuild.channels.cache.set('channel-123', upperCaseChannel);
      mockGuildConfigService.get.mockReset();
      mockGuildConfigService.get.mockResolvedValue('open-notes');

      const result = await botChannelService.ensureChannelExists(
        mockGuild,
        mockGuildConfigService
      );

      expect(result.wasCreated).toBe(false);
      expect(result.channel).toBe(upperCaseChannel);
    });
  });

  describe('Revision-based Idempotency', () => {
    function createMockPinnedMessage(revision: string, messageId = 'msg-123') {
      return {
        id: messageId,
        author: { id: 'bot-user-123' },
        createdTimestamp: Date.now(),
        type: 0,
        components: [
          {
            type: ComponentType.Container,
            components: [
              {
                toJSON: () => ({
                  type: ComponentType.TextDisplay,
                  content: `-# Revision ${revision}`,
                }),
              },
            ],
          },
        ],
        delete: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      };
    }

    it('should include revision string in welcome message', async () => {
      await guildOnboardingService.postWelcomeToChannel(mockChannel);

      const sendCall = mockChannel.send.mock.calls[0][0];
      const container = sendCall.components[0];
      const allContent = JSON.stringify(container.toJSON().components);

      expect(allContent).toContain('Revision');
      expect(allContent).toContain(WELCOME_MESSAGE_REVISION);
    });

    it('should skip posting if revision matches existing pinned message', async () => {
      const existingMessage = createMockPinnedMessage(WELCOME_MESSAGE_REVISION);
      mockChannel.messages.fetchPins.mockResolvedValue(createMockPinsResponse([existingMessage]));
      mockChannel.messages.fetch.mockResolvedValue(new Collection());

      await guildOnboardingService.postWelcomeToChannel(mockChannel);

      expect(mockChannel.send).not.toHaveBeenCalled();
      expect(existingMessage.delete).not.toHaveBeenCalled();
    });

    it('should replace message if revision differs', async () => {
      const existingMessage = createMockPinnedMessage('2024-01-01.1');
      mockChannel.messages.fetchPins.mockResolvedValue(createMockPinsResponse([existingMessage]));
      mockChannel.messages.fetch.mockResolvedValue(new Collection());

      const newMessage = {
        id: 'new-msg-456',
        pin: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        pinned: false,
        channel: mockChannel,
      };
      mockChannel.send.mockResolvedValue(newMessage);

      await guildOnboardingService.postWelcomeToChannel(mockChannel);

      expect(existingMessage.delete).toHaveBeenCalled();
      expect(mockChannel.send).toHaveBeenCalled();
    });

    it('should keep most recent message when multiple welcome messages exist', async () => {
      const olderMessage = createMockPinnedMessage(WELCOME_MESSAGE_REVISION, 'old-msg');
      olderMessage.createdTimestamp = Date.now() - 10000;
      const newerMessage = createMockPinnedMessage(WELCOME_MESSAGE_REVISION, 'new-msg');
      newerMessage.createdTimestamp = Date.now();

      mockChannel.messages.fetchPins.mockResolvedValue(createMockPinsResponse([olderMessage, newerMessage]));
      mockChannel.messages.fetch.mockResolvedValue(new Collection());

      await guildOnboardingService.postWelcomeToChannel(mockChannel);

      expect(olderMessage.delete).toHaveBeenCalled();
      expect(newerMessage.delete).not.toHaveBeenCalled();
      expect(mockChannel.send).not.toHaveBeenCalled();
    });

    it('should clean up pin notifications on startup', async () => {
      const pinNotification = {
        id: 'pin-notification-123',
        type: MessageType.ChannelPinnedMessage,
        delete: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      };
      const messageCollection = new Collection([['pin-notification-123', pinNotification]]);
      mockChannel.messages.fetch.mockResolvedValue(messageCollection);

      await guildOnboardingService.postWelcomeToChannel(mockChannel);

      expect(pinNotification.delete).toHaveBeenCalled();
    });
  });
});
