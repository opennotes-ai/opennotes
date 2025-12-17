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

const { BotChannelService } = await import('../../src/services/BotChannelService.js');
const { GuildOnboardingService } = await import('../../src/services/GuildOnboardingService.js');
const { buildWelcomeContainer } = await import('../../src/lib/welcome-content.js');

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

    mockChannel = {
      id: 'channel-123',
      name: 'open-notes',
      type: ChannelType.GuildText,
      guild: null,
      send: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
      delete: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
      permissionOverwrites: {
        set: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
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
      const failingGuild = {
        ...mockGuild,
        id: 'failing-guild',
        channels: {
          cache: new Collection<string, any>(),
          create: jest.fn<(...args: any[]) => Promise<any>>()
            .mockRejectedValue(new Error('Guild error')),
        },
      };

      mockGuildConfigService.get
        .mockResolvedValueOnce('open-notes')
        .mockResolvedValueOnce('OpenNotes');

      await expect(
        botChannelService.ensureChannelExists(failingGuild, mockGuildConfigService)
      ).rejects.toThrow('Guild error');

      mockGuildConfigService.get
        .mockResolvedValueOnce('open-notes')
        .mockResolvedValueOnce('OpenNotes');
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
});
