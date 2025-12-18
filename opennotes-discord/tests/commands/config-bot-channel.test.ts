import { jest } from '@jest/globals';
import { ChannelType, Collection, MessageFlags } from 'discord.js';
import { ConfigKey } from '../../src/lib/config-schema.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
};

const mockGuildConfigService = {
  getAll: jest.fn<(guildId: string) => Promise<Record<string, any>>>(),
  get: jest.fn<(guildId: string, key: string) => Promise<any>>(),
  set: jest.fn<(guildId: string, key: string, value: any, updatedBy: string) => Promise<void>>(),
  reset: jest.fn<(guildId: string, key?: string, updatedBy?: string) => Promise<void>>(),
};

const mockMigrateChannelResult = {
  newChannel: {
    id: 'new-channel-123',
    name: 'new-bot-channel',
    toString: () => '<#new-channel-123>',
  },
  oldChannelDeleted: true,
};

const mockBotChannelService = {
  migrateChannel: jest.fn<(...args: any[]) => Promise<any>>(),
  findChannel: jest.fn<(...args: any[]) => any>(),
  createChannel: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockGuildOnboardingService = {
  postWelcomeToChannel: jest.fn<(...args: any[]) => Promise<void>>(),
};

const mockApiClient = {
  healthCheck: jest.fn<() => Promise<any>>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/services/GuildConfigService.js', () => ({
  GuildConfigService: jest.fn(() => mockGuildConfigService),
}));

jest.unstable_mockModule('../../src/services/BotChannelService.js', () => ({
  BotChannelService: jest.fn(() => mockBotChannelService),
}));

jest.unstable_mockModule('../../src/services/GuildOnboardingService.js', () => ({
  GuildOnboardingService: jest.fn(() => mockGuildOnboardingService),
}));

jest.unstable_mockModule('../../src/lib/validation.js', () => ({
  parseCustomId: (customId: string, expectedParts: number, delimiter: string = ':') => {
    if (!customId || customId.trim().length === 0) {
      return { success: false, error: 'CustomId cannot be empty' };
    }
    const parts = customId.split(delimiter);
    if (parts.length < expectedParts) {
      return { success: false, error: `CustomId must have at least ${expectedParts} parts` };
    }
    return { success: true, parts };
  },
  validateMessageId: (messageId: string) => ({ valid: true }),
}));

jest.unstable_mockModule('../../src/lib/interaction-rate-limiter.js', () => ({
  buttonInteractionRateLimiter: {
    checkAndRecord: jest.fn(() => false),
  },
}));

const { execute } = await import('../../src/commands/config.js');

describe('config bot-channel migration (AC7)', () => {
  let operationOrder: string[];

  beforeEach(() => {
    jest.clearAllMocks();
    operationOrder = [];

    mockGuildConfigService.get.mockResolvedValue('old-bot-channel');
    mockBotChannelService.migrateChannel.mockImplementation(async () => {
      operationOrder.push('migrateChannel');
      return mockMigrateChannelResult;
    });
    mockGuildConfigService.set.mockImplementation(async () => {
      operationOrder.push('configService.set');
    });
    mockGuildOnboardingService.postWelcomeToChannel.mockImplementation(async () => {
      operationOrder.push('postWelcomeToChannel');
    });
  });

  describe('atomicity of operations', () => {
    it('should post welcome message BEFORE updating config for proper atomicity', async () => {
      const mockGuild = {
        id: 'guild-123',
        name: 'Test Guild',
        channels: {
          cache: new Collection(),
        },
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild-123',
        guild: mockGuild,
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string) => string | null>((name: string) => {
            if (name === 'key') return ConfigKey.BOT_CHANNEL_NAME;
            if (name === 'value') return 'new-bot-channel';
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockBotChannelService.migrateChannel).toHaveBeenCalled();
      expect(mockGuildOnboardingService.postWelcomeToChannel).toHaveBeenCalled();
      expect(mockGuildConfigService.set).toHaveBeenCalled();

      expect(operationOrder).toEqual([
        'migrateChannel',
        'postWelcomeToChannel',
        'configService.set',
      ]);
    });

    it('should NOT update config if welcome message fails', async () => {
      mockGuildOnboardingService.postWelcomeToChannel.mockImplementation(async () => {
        operationOrder.push('postWelcomeToChannel');
        throw new Error('Failed to post welcome message');
      });

      const mockGuild = {
        id: 'guild-123',
        name: 'Test Guild',
        channels: {
          cache: new Collection(),
        },
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild-123',
        guild: mockGuild,
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string) => string | null>((name: string) => {
            if (name === 'key') return ConfigKey.BOT_CHANNEL_NAME;
            if (name === 'value') return 'new-bot-channel';
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockBotChannelService.migrateChannel).toHaveBeenCalled();
      expect(mockGuildOnboardingService.postWelcomeToChannel).toHaveBeenCalled();
      expect(mockGuildConfigService.set).not.toHaveBeenCalled();

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Failed to migrate bot channel'),
        })
      );
    });

    it('should report error when welcome message fails', async () => {
      mockGuildOnboardingService.postWelcomeToChannel.mockRejectedValue(
        new Error('Discord API error: Cannot send message')
      );

      const mockGuild = {
        id: 'guild-123',
        name: 'Test Guild',
        channels: {
          cache: new Collection(),
        },
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild-123',
        guild: mockGuild,
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string) => string | null>((name: string) => {
            if (name === 'key') return ConfigKey.BOT_CHANNEL_NAME;
            if (name === 'value') return 'new-bot-channel';
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to migrate bot channel'),
        expect.any(Object)
      );
    });
  });
});
