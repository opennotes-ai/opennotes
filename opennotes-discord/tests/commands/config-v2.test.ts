import { jest } from '@jest/globals';
import { MessageFlags, ComponentType } from 'discord.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
};

const mockApiClient = {
  addCommunityAdmin: jest.fn<(communityServerId: string, userDiscordId: string, profileData?: any) => Promise<any>>(),
  removeCommunityAdmin: jest.fn<(communityServerId: string, userDiscordId: string) => Promise<any>>(),
  listCommunityAdmins: jest.fn<(communityServerId: string) => Promise<any[]>>(),
  createLLMConfig: jest.fn<(...args: any[]) => Promise<any>>(),
  getMonitoredChannel: jest.fn<(...args: any[]) => Promise<any>>(),
  updateMonitoredChannel: jest.fn<(...args: any[]) => Promise<any>>(),
  createMonitoredChannel: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockGuildConfigService = {
  getAll: jest.fn<(guildId: string) => Promise<Record<string, any>>>(),
  get: jest.fn<(guildId: string, key: string) => Promise<any>>(),
  set: jest.fn<(guildId: string, key: string, value: any, updatedBy: string) => Promise<void>>(),
  reset: jest.fn<(guildId: string, key?: string, updatedBy?: string) => Promise<void>>(),
};

const mockGuildSetupService = {
  autoRegisterChannels: jest.fn<(...args: any[]) => Promise<void>>(),
};

const mockNotePublisherConfigService = {
  setConfig: jest.fn<(...args: any[]) => Promise<void>>(),
  setThreshold: jest.fn<(...args: any[]) => Promise<void>>(),
  enableChannel: jest.fn<(...args: any[]) => Promise<void>>(),
  disableChannel: jest.fn<(...args: any[]) => Promise<void>>(),
  getConfig: jest.fn<(...args: any[]) => Promise<any>>(),
  getDefaultThreshold: jest.fn(() => 0.7),
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

jest.unstable_mockModule('../../src/services/GuildSetupService.js', () => {
  class MockGuildSetupService {
    autoRegisterChannels = mockGuildSetupService.autoRegisterChannels;
  }
  return { GuildSetupService: MockGuildSetupService };
});

jest.unstable_mockModule('../../src/services/NotePublisherConfigService.js', () => {
  class MockNotePublisherConfigService {
    setConfig = mockNotePublisherConfigService.setConfig;
    setThreshold = mockNotePublisherConfigService.setThreshold;
    enableChannel = mockNotePublisherConfigService.enableChannel;
    disableChannel = mockNotePublisherConfigService.disableChannel;
    getConfig = mockNotePublisherConfigService.getConfig;
    getDefaultThreshold = mockNotePublisherConfigService.getDefaultThreshold;
  }
  return { NotePublisherConfigService: MockNotePublisherConfigService };
});

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
const { ConfigKey, CONFIG_SCHEMA } = await import('../../src/lib/config-schema.js');

describe('config command v2 components migration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('AC #1: Admin list uses ContainerBuilder + TextDisplayBuilder', () => {
    it('should use v2 container structure for admin list', async () => {
      const mockAdmins = [
        {
          profile_id: 'profile-1',
          display_name: 'Admin One',
          avatar_url: null,
          discord_id: 'user111',
          admin_sources: ['opennotes_platform', 'community_role'],
          is_opennotes_admin: true,
          community_role: 'admin',
        },
        {
          profile_id: 'profile-2',
          display_name: 'Admin Two',
          avatar_url: null,
          discord_id: 'user222',
          admin_sources: ['discord_manage_server'],
          is_opennotes_admin: false,
          community_role: 'member',
        },
      ];

      mockApiClient.listCommunityAdmins.mockResolvedValue(mockAdmins);

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('list'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];

      expect(editReplyCall.components).toBeDefined();
      expect(editReplyCall.components.length).toBeGreaterThan(0);
      const containerJson = editReplyCall.components[0];
      expect(containerJson.type).toBe(17);

      expect(editReplyCall.embeds).toBeUndefined();
    });

    it('should include accent color in admin list container', async () => {
      const mockAdmins = [
        {
          profile_id: 'profile-1',
          display_name: 'Admin One',
          avatar_url: null,
          discord_id: 'user111',
          admin_sources: ['community_role'],
          is_opennotes_admin: false,
          community_role: 'admin',
        },
      ];

      mockApiClient.listCommunityAdmins.mockResolvedValue(mockAdmins);

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('list'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      const containerJson = editReplyCall.components[0];

      expect(containerJson.accent_color).toBeDefined();
      expect(typeof containerJson.accent_color).toBe('number');
    });

    it('should use TextDisplayBuilder for admin entries', async () => {
      const mockAdmins = [
        {
          profile_id: 'profile-1',
          display_name: 'Test Admin',
          avatar_url: null,
          discord_id: 'user111',
          admin_sources: ['community_role'],
          is_opennotes_admin: false,
          community_role: 'admin',
        },
      ];

      mockApiClient.listCommunityAdmins.mockResolvedValue(mockAdmins);

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('list'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      const containerJson = editReplyCall.components[0];

      const textDisplays = containerJson.components.filter((c: any) => c.type === 10);
      expect(textDisplays.length).toBeGreaterThan(0);

      const adminText = textDisplays.find((t: any) => t.content?.includes('Test Admin'));
      expect(adminText).toBeDefined();
    });
  });

  describe('AC #2: Config view uses SectionBuilder with button accessories', () => {
    it('should use v2 container for config view', async () => {
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
        on: jest.fn<(event: string, handler: any) => any>().mockReturnThis(),
      };

      const mockMessage = {
        createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
      };

      let capturedReplyData: any = null;
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
          getString: jest.fn<(name: string) => string | null>(),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockImplementation((data) => {
          capturedReplyData = data;
          return Promise.resolve(mockMessage);
        }),
      };

      await execute(mockInteraction as any);

      expect(capturedReplyData).not.toBeNull();
      expect(capturedReplyData.components).toBeDefined();
      const containerJson = capturedReplyData.components[0];
      expect(containerJson.type).toBe(17);
    });

    it('should use SectionBuilder for toggle settings with inline button accessories', async () => {
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
        on: jest.fn<(event: string, handler: any) => any>().mockReturnThis(),
      };

      const mockMessage = {
        createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
      };

      let capturedReplyData: any = null;
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
          getString: jest.fn<(name: string) => string | null>(),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockImplementation((data) => {
          capturedReplyData = data;
          return Promise.resolve(mockMessage);
        }),
      };

      await execute(mockInteraction as any);

      expect(capturedReplyData).not.toBeNull();
      const containerJson = capturedReplyData.components[0];

      const sections = containerJson.components.filter((c: any) => c.type === 9);
      expect(sections.length).toBeGreaterThan(0);

      const sectionsWithButtonAccessory = sections.filter((s: any) => s.accessory?.type === 2);
      expect(sectionsWithButtonAccessory.length).toBeGreaterThan(0);
    });
  });

  describe('AC #3: SeparatorBuilder between config categories', () => {
    it('should include separators between config categories', async () => {
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
        on: jest.fn<(event: string, handler: any) => any>().mockReturnThis(),
      };

      const mockMessage = {
        createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
      };

      let capturedReplyData: any = null;
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
          getString: jest.fn<(name: string) => string | null>(),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockImplementation((data) => {
          capturedReplyData = data;
          return Promise.resolve(mockMessage);
        }),
      };

      await execute(mockInteraction as any);

      expect(capturedReplyData).not.toBeNull();
      const containerJson = capturedReplyData.components[0];

      const separators = containerJson.components.filter((c: any) => c.type === 14);
      // Page 0 has 3 separators: header, between visibility/features, and final
      expect(separators.length).toBeGreaterThanOrEqual(3);
    });
  });

  describe('AC #4: Confirmation dialogs use v2 container format', () => {
    it('should use v2 container for reset confirmation dialog', async () => {
      mockGuildConfigService.getAll.mockResolvedValue({});

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
        followUp: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
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
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue(mockMessage),
      };

      await execute(mockInteraction as any);

      expect(collectHandler).not.toBeNull();

      await collectHandler(mockButtonInteraction);

      await new Promise(resolve => setImmediate(resolve));

      expect(mockButtonInteraction.editReply).toHaveBeenCalled();
      const confirmDialogCall = mockButtonInteraction.editReply.mock.calls[0][0];

      expect(confirmDialogCall.components).toBeDefined();
      const containerJson = confirmDialogCall.components[0];
      expect(containerJson.type).toBe(17);
    });
  });

  describe('AC #5: MessageComponentCollector setup for v2 components', () => {
    it('should setup collector that works with v2 container components', async () => {
      mockGuildConfigService.getAll.mockResolvedValue({});

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
          getString: jest.fn<(name: string) => string | null>(),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue(mockMessage),
      };

      await execute(mockInteraction as any);

      expect(mockMessage.createMessageComponentCollector).toHaveBeenCalledWith(
        expect.objectContaining({
          componentType: ComponentType.Button,
        })
      );
    });
  });

  describe('AC #6: Custom ID patterns preserved', () => {
    it('should preserve config:toggle:* pattern', async () => {
      mockGuildConfigService.getAll.mockResolvedValue({});

      const mockCollector = {
        on: jest.fn<(event: string, handler: any) => any>().mockReturnThis(),
      };

      const mockMessage = {
        createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
      };

      let capturedReplyData: any = null;
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
          getString: jest.fn<(name: string) => string | null>(),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockImplementation((data) => {
          capturedReplyData = data;
          return Promise.resolve(mockMessage);
        }),
      };

      await execute(mockInteraction as any);

      expect(capturedReplyData).not.toBeNull();

      const allCustomIds = extractAllCustomIds(capturedReplyData.components);

      const togglePatterns = allCustomIds.filter((id: string) => id.startsWith('config:toggle:'));
      expect(togglePatterns.length).toBeGreaterThan(0);
    });

    it('should preserve config:reset:* pattern', async () => {
      mockGuildConfigService.getAll.mockResolvedValue({});

      const mockCollector = {
        on: jest.fn<(event: string, handler: any) => any>().mockReturnThis(),
      };

      const mockMessage = {
        createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
      };

      let capturedReplyData: any = null;
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
          getString: jest.fn<(name: string) => string | null>(),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockImplementation((data) => {
          capturedReplyData = data;
          return Promise.resolve(mockMessage);
        }),
      };

      await execute(mockInteraction as any);

      expect(capturedReplyData).not.toBeNull();

      const allCustomIds = extractAllCustomIds(capturedReplyData.components);

      const resetPatterns = allCustomIds.filter((id: string) => id.startsWith('config:reset:'));
      expect(resetPatterns.length).toBeGreaterThan(0);
    });

    it('should preserve config:refresh pattern', async () => {
      mockGuildConfigService.getAll.mockResolvedValue({});

      const mockCollector = {
        on: jest.fn<(event: string, handler: any) => any>().mockReturnThis(),
      };

      const mockMessage = {
        createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
      };

      let capturedReplyData: any = null;
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('opennotes'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
          getString: jest.fn<(name: string) => string | null>(),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockImplementation((data) => {
          capturedReplyData = data;
          return Promise.resolve(mockMessage);
        }),
      };

      await execute(mockInteraction as any);

      expect(capturedReplyData).not.toBeNull();

      const allCustomIds = extractAllCustomIds(capturedReplyData.components);

      expect(allCustomIds).toContain('config:refresh');
    });
  });

  describe('AC #7: Button interaction flow with v2 components', () => {
    it('should handle toggle button clicks and update v2 container', async () => {
      const initialConfig = {
        [ConfigKey.REQUEST_NOTE_EPHEMERAL]: true,
      };

      const updatedConfig = {
        [ConfigKey.REQUEST_NOTE_EPHEMERAL]: false,
      };

      mockGuildConfigService.getAll.mockResolvedValueOnce(initialConfig).mockResolvedValue(updatedConfig);
      mockGuildConfigService.get.mockResolvedValue(true);
      mockGuildConfigService.set.mockResolvedValue(undefined);

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
        customId: 'config:toggle:request_note_ephemeral',
        deferUpdate: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        followUp: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
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
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue(mockMessage),
      };

      await execute(mockInteraction as any);

      expect(collectHandler).not.toBeNull();
      await collectHandler(mockButtonInteraction);

      await new Promise(resolve => setImmediate(resolve));

      expect(mockGuildConfigService.set).toHaveBeenCalled();
      expect(mockButtonInteraction.editReply).toHaveBeenCalled();

      const updatedReply = mockButtonInteraction.editReply.mock.calls[0][0];
      expect(updatedReply.components).toBeDefined();
      expect(updatedReply.components[0].type).toBe(17);
    });

    it('should handle refresh button and update v2 container', async () => {
      const config = {};

      mockGuildConfigService.getAll.mockResolvedValue(config);

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
        customId: 'config:refresh',
        deferUpdate: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        followUp: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
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
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue(mockMessage),
      };

      await execute(mockInteraction as any);

      expect(collectHandler).not.toBeNull();
      await collectHandler(mockButtonInteraction);

      await new Promise(resolve => setImmediate(resolve));

      expect(mockButtonInteraction.editReply).toHaveBeenCalled();
      const refreshedReply = mockButtonInteraction.editReply.mock.calls[0][0];
      expect(refreshedReply.components).toBeDefined();
      expect(refreshedReply.components[0].type).toBe(17);
    });
  });

  describe('AC #8: MessageFlags.IsComponentsV2 applied to all replies', () => {
    it('should include IsComponentsV2 flag in deferReply for admin list', async () => {
      mockApiClient.listCommunityAdmins.mockResolvedValue([]);

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('list'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      const deferReplyCall = mockInteraction.deferReply.mock.calls[0][0];
      expect(deferReplyCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
      expect(deferReplyCall.flags & MessageFlags.Ephemeral).toBeTruthy();
    });

    it('should include IsComponentsV2 flag in deferReply for config view', async () => {
      mockGuildConfigService.getAll.mockResolvedValue({});

      const mockCollector = {
        on: jest.fn<(event: string, handler: any) => void>(),
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
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue(mockMessage),
      };

      await execute(mockInteraction as any);

      const deferReplyCall = mockInteraction.deferReply.mock.calls[0][0];
      expect(deferReplyCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should include IsComponentsV2 flag in editReply with container', async () => {
      mockApiClient.listCommunityAdmins.mockResolvedValue([
        {
          profile_id: 'profile-1',
          display_name: 'Admin',
          avatar_url: null,
          discord_id: 'user111',
          admin_sources: ['community_role'],
          is_opennotes_admin: false,
          community_role: 'admin',
        },
      ]);

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('list'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      expect(editReplyCall.flags).toBeDefined();
      expect(editReplyCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should include IsComponentsV2 flag in admin set success response', async () => {
      const mockUser = {
        id: 'user123',
        tag: 'TestUser#1234',
        username: 'TestUser',
        displayName: 'Test User Display',
        displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
      };

      const mockAdminResponse = {
        profile_id: 'profile-uuid-123',
        display_name: 'TestUser',
        avatar_url: null,
        discord_id: 'user123',
        admin_sources: ['community_role'],
        is_opennotes_admin: false,
        community_role: 'admin',
      };

      mockApiClient.addCommunityAdmin.mockResolvedValue(mockAdminResponse);

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getUser: jest.fn<(name: string, required: boolean) => any>().mockReturnValue(mockUser),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      expect(editReplyCall.flags).toBeDefined();
      expect(editReplyCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should include IsComponentsV2 flag in content-monitor enable-all response', async () => {
      mockGuildSetupService.autoRegisterChannels.mockResolvedValue(undefined);

      const mockGuild = {
        id: 'guild789',
        name: 'Test Guild',
      };

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        guild: mockGuild,
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('content-monitor'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable-all'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      const deferReplyCall = mockInteraction.deferReply.mock.calls[0][0];
      expect(deferReplyCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      expect(editReplyCall.flags).toBeDefined();
      expect(editReplyCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });
  });
});

function extractAllCustomIds(components: any[]): string[] {
  const customIds: string[] = [];

  function traverse(component: any): void {
    if (!component) return;

    if (component.custom_id) {
      customIds.push(component.custom_id);
    }

    if (component.accessory?.custom_id) {
      customIds.push(component.accessory.custom_id);
    }

    if (Array.isArray(component.components)) {
      for (const child of component.components) {
        traverse(child);
      }
    }
  }

  for (const component of components) {
    traverse(component);
  }

  return customIds;
}
