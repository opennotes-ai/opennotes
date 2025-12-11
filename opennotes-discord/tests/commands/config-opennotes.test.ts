import { jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';
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

const mockApiClient = {
  healthCheck: jest.fn<() => Promise<any>>(),
  createNote: jest.fn<(...args: any[]) => Promise<any>>(),
  getNotes: jest.fn<(...args: any[]) => Promise<any>>(),
  rateNote: jest.fn<(...args: any[]) => Promise<any>>(),
  scoreNotes: jest.fn<(...args: any[]) => Promise<any>>(),
  createNoteRequest: jest.fn<(...args: any[]) => Promise<any>>(),
  getGuildConfig: jest.fn<(guildId: string) => Promise<any>>(),
  updateGuildConfig: jest.fn<(...args: any[]) => Promise<void>>(),
  resetGuildConfig: jest.fn<(guildId: string) => Promise<void>>(),
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

describe('config-opennotes command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('view subcommand', () => {
    it('should display current configuration', async () => {
      const mockConfig = {
        [ConfigKey.REQUEST_NOTE_EPHEMERAL]: true,
        [ConfigKey.WRITE_NOTE_EPHEMERAL]: false,
        [ConfigKey.RATE_NOTE_EPHEMERAL]: true,
        [ConfigKey.LIST_REQUESTS_EPHEMERAL]: false,
        [ConfigKey.STATUS_EPHEMERAL]: true,
        [ConfigKey.NOTES_ENABLED]: true,
        [ConfigKey.RATINGS_ENABLED]: true,
        [ConfigKey.REQUESTS_ENABLED]: true,
        [ConfigKey.NOTE_RATE_LIMIT]: 10,
        [ConfigKey.RATING_RATE_LIMIT]: 20,
        [ConfigKey.REQUEST_RATE_LIMIT]: 5,
        [ConfigKey.NOTIFY_NOTE_HELPFUL]: true,
        [ConfigKey.NOTIFY_REQUEST_FULFILLED]: false,
      };

      mockGuildConfigService.getAll.mockResolvedValue(mockConfig);

      const mockCollector = {
        on: jest.fn<(event: string, handler: any) => any>(),
      };

      const mockMessage = {
        createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
          getString: jest.fn<(name: string) => string | null>(),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}).mockResolvedValue(mockMessage),
      };

      await execute(mockInteraction as any);

      expect(mockGuildConfigService.getAll).toHaveBeenCalledWith('guild456');
      expect(mockInteraction.deferReply).toHaveBeenCalledWith({
        flags: expect.any(Number),
      });
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          components: expect.arrayContaining([
            expect.objectContaining({
              type: 17,
              components: expect.any(Array),
            }),
          ]),
        })
      );
    });

    it('should handle missing guildId', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: null,
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: 'This command can only be used in a server.',
      });
    });
  });

  describe('set subcommand', () => {
    it('should update configuration value', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string) => string | null>((name: string) => {
            if (name === 'key') return ConfigKey.REQUEST_NOTE_EPHEMERAL;
            if (name === 'value') return 'true';
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      mockGuildConfigService.set.mockResolvedValue(undefined);

      await execute(mockInteraction as any);

      expect(mockGuildConfigService.set).toHaveBeenCalledWith(
        'guild456',
        ConfigKey.REQUEST_NOTE_EPHEMERAL,
        true,
        'user123'
      );
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Updated'),
        })
      );
    });

    it('should reject invalid configuration value', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string) => string | null>((name: string) => {
            if (name === 'key') return ConfigKey.REQUEST_NOTE_EPHEMERAL;
            if (name === 'value') return 'invalid-boolean';
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockGuildConfigService.set).not.toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Invalid value'),
        })
      );
    });
  });

  describe('reset subcommand', () => {
    it('should reset specific configuration key', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('reset'),
          getString: jest.fn<(name: string) => string>().mockReturnValue(ConfigKey.REQUEST_NOTE_EPHEMERAL),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      mockGuildConfigService.reset.mockResolvedValue(undefined);

      await execute(mockInteraction as any);

      expect(mockGuildConfigService.reset).toHaveBeenCalledWith(
        'guild456',
        ConfigKey.REQUEST_NOTE_EPHEMERAL,
        'user123'
      );
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Reset'),
        })
      );
    });

    it('should reset all configuration when no key provided', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('reset'),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      mockGuildConfigService.reset.mockResolvedValue(undefined);

      await execute(mockInteraction as any);

      expect(mockGuildConfigService.reset).toHaveBeenCalledWith(
        'guild456',
        undefined,
        'user123'
      );
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('All configuration settings have been reset'),
        })
      );
    });
  });

  describe('error handling', () => {
    it('should handle API errors gracefully', async () => {
      mockGuildConfigService.getAll.mockRejectedValue(new Error('API error'));

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Failed to process configuration command'),
        })
      );
    });
  });

  describe('ephemeral response', () => {
    it('should use v2 ephemeral flags for all responses', async () => {
      const mockCollector = {
        on: jest.fn<(event: string, handler: any) => any>().mockReturnThis(),
      };

      const mockMessage = {
        createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue(mockMessage),
      };

      mockGuildConfigService.getAll.mockResolvedValue({});

      await execute(mockInteraction as any);

      const deferReplyCall = mockInteraction.deferReply.mock.calls[0][0];
      expect(deferReplyCall.flags).toBeDefined();
      expect(deferReplyCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
      expect(deferReplyCall.flags & MessageFlags.Ephemeral).toBeTruthy();
    });
  });

  describe('reset confirmation flow', () => {
    it('should show confirmation dialog when reset all is clicked', async () => {
      let collectHandler: any = null;
      const mockCollector = {
        on: jest.fn<(event: string, handler: any) => any>().mockImplementation((event, handler) => {
          if (event === 'collect') {
            collectHandler = handler;
          }
          return mockCollector;
        }),
      };

      const mockMessage = {
        createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
      };

      const mockButtonInteraction = {
        user: { id: 'user123' },
        customId: 'config:reset:all',
        deferUpdate: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue(mockMessage),
      };

      mockGuildConfigService.getAll.mockResolvedValue({});

      await execute(mockInteraction as any);

      expect(collectHandler).not.toBeNull();

      await collectHandler(mockButtonInteraction);
      await new Promise(resolve => setImmediate(resolve));

      expect(mockButtonInteraction.editReply).toHaveBeenCalled();
      const editReplyCall = mockButtonInteraction.editReply.mock.calls[0][0];
      expect(editReplyCall.components).toBeDefined();
      expect(editReplyCall.components[0].type).toBe(17);
    });

    it('should execute reset when confirm button is clicked', async () => {
      let collectHandler: any = null;
      const mockCollector = {
        on: jest.fn<(event: string, handler: any) => any>().mockImplementation((event, handler) => {
          if (event === 'collect') {
            collectHandler = handler;
          }
          return mockCollector;
        }),
      };

      const mockMessage = {
        createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
      };

      const mockButtonInteraction = {
        user: { id: 'user123' },
        customId: 'config:reset:confirm',
        reply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        deferUpdate: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue(mockMessage),
      };

      mockGuildConfigService.getAll.mockResolvedValue({});
      mockGuildConfigService.reset.mockResolvedValue(undefined);

      await execute(mockInteraction as any);

      expect(collectHandler).not.toBeNull();
      await collectHandler(mockButtonInteraction);

      await new Promise(resolve => setImmediate(resolve));

      expect(mockGuildConfigService.reset).toHaveBeenCalledWith('guild456', undefined, 'user123');
      expect(mockButtonInteraction.editReply).toHaveBeenCalled();
      const editReplyCall = mockButtonInteraction.editReply.mock.calls[0][0];
      expect(editReplyCall.components).toBeDefined();
      expect(editReplyCall.components[0].type).toBe(17);
    });

    it('should cancel reset when cancel button is clicked', async () => {
      let collectHandler: any = null;
      const mockCollector = {
        on: jest.fn<(event: string, handler: any) => any>().mockImplementation((event, handler) => {
          if (event === 'collect') {
            collectHandler = handler;
          }
          return mockCollector;
        }),
      };

      const mockMessage = {
        createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
      };

      const mockButtonInteraction = {
        user: { id: 'user123' },
        customId: 'config:reset:cancel',
        reply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        deferUpdate: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue(mockMessage),
      };

      mockGuildConfigService.getAll.mockResolvedValue({});

      await execute(mockInteraction as any);

      expect(collectHandler).not.toBeNull();
      await collectHandler(mockButtonInteraction);

      await new Promise(resolve => setImmediate(resolve));

      expect(mockGuildConfigService.reset).not.toHaveBeenCalled();
      expect(mockButtonInteraction.editReply).toHaveBeenCalled();
      const editReplyCall = mockButtonInteraction.editReply.mock.calls[0][0];
      expect(editReplyCall.components).toBeDefined();
      expect(editReplyCall.components[0].type).toBe(17);
    });
  });
});
