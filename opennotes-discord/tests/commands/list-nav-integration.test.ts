import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import { MessageFlags, ContainerBuilder } from 'discord.js';
import { loggerFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();

const cacheStore = new Map<string, unknown>();
const mockCache = {
  get: jest.fn<(key: string) => Promise<unknown>>(),
  set: jest.fn<(key: string, value: unknown, ttl?: number) => Promise<boolean>>(),
  delete: jest.fn<(key: string) => Promise<boolean>>(),
  expire: jest.fn<(key: string, ttl: number) => Promise<boolean>>(),
  clear: jest.fn<() => Promise<number>>(),
  start: jest.fn<() => void>(),
  stop: jest.fn<() => void>(),
  getMetrics: jest.fn(() => ({ size: cacheStore.size })),
};

function setupCacheImplementations() {
  mockCache.get.mockImplementation(async (key: string) => {
    return cacheStore.get(key) ?? null;
  });
  mockCache.set.mockImplementation(async (key: string, value: unknown, _ttl?: number) => {
    cacheStore.set(key, value);
    return true;
  });
  mockCache.delete.mockImplementation(async (key: string) => {
    return cacheStore.delete(key);
  });
  mockCache.expire.mockImplementation(async (key: string, _ttl: number) => {
    return cacheStore.has(key);
  });
  mockCache.clear.mockImplementation(async () => {
    const count = cacheStore.size;
    cacheStore.clear();
    return count;
  });
}

const mockApiClient = {
  listNotesWithStatus: jest.fn<(...args: any[]) => Promise<any>>(),
  getCommunityServerByPlatformId: jest.fn<(...args: any[]) => Promise<any>>(),
  rateNote: jest.fn<() => Promise<void>>(),
  forcePublishNote: jest.fn<() => Promise<any>>(),
  generateAiNote: jest.fn<() => Promise<any>>(),
  getRequest: jest.fn<() => Promise<any>>(),
};

const mockConfigCache = {
  getRatingThresholds: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockGuildConfigService = {
  get: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue('open-notes'),
  set: jest.fn<(...args: any[]) => Promise<any>>(),
  delete: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockListRequestsService = {
  execute: jest.fn<() => Promise<any>>(),
};

const mockServiceProvider = {
  getGuildConfigService: jest.fn(() => mockGuildConfigService),
  getListRequestsService: jest.fn(() => mockListRequestsService),
  getWriteNoteService: jest.fn(),
};

class MockDiscordFormatter {
  static formatListRequestsSuccessV2 = jest.fn<() => Promise<any>>();
  static formatErrorV2 = jest.fn<() => any>();
  static formatWriteNoteSuccessV2 = jest.fn<() => any>();
}

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/lib/config-cache.js', () => ({
  ConfigCache: jest.fn(() => mockConfigCache),
}));

jest.unstable_mockModule('../../src/services/index.js', () => ({
  serviceProvider: mockServiceProvider,
}));

jest.unstable_mockModule('../../src/services/DiscordFormatter.js', () => ({
  DiscordFormatter: MockDiscordFormatter,
}));

const mockGetBotChannelOrRedirect = jest.fn<(...args: any[]) => Promise<any>>();

jest.unstable_mockModule('../../src/lib/bot-channel-helper.js', () => ({
  getBotChannelOrRedirect: mockGetBotChannelOrRedirect,
}));

jest.unstable_mockModule('../../src/services/BotChannelService.js', () => ({
  BotChannelService: class MockBotChannelService {
    findChannel() {
      return { id: 'channel-456', name: 'open-notes' };
    }
    async ensureChannelExists() {
      return { channel: { id: 'channel-456', name: 'open-notes' }, wasCreated: false };
    }
  },
}));

jest.unstable_mockModule('../../src/services/PermissionModeService.js', () => ({
  PermissionModeService: class MockPermissionModeService {},
}));

const mockResolveUserProfileId = jest.fn<(...args: any[]) => Promise<string>>();

jest.unstable_mockModule('../../src/lib/user-profile-resolver.js', () => ({
  resolveUserProfileId: mockResolveUserProfileId,
  isValidUUID: jest.fn(),
  clearCache: jest.fn(),
}));

jest.unstable_mockModule('../../src/lib/errors.js', () => ({
  generateErrorId: () => 'test-error-id',
  extractErrorDetails: (error: any) => ({
    message: error?.message || 'Unknown error',
    type: error?.constructor?.name || 'Error',
    stack: error?.stack || '',
  }),
  formatErrorForUser: (errorId: string, message: string) => `${message} (Error ID: ${errorId})`,
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public endpoint?: string,
      public statusCode?: number,
      public responseBody?: any
    ) {
      super(message);
    }
  },
}));

jest.unstable_mockModule('../../src/lib/error-handler.js', () => ({
  classifyApiError: () => 'API_ERROR',
  getQueueErrorMessage: () => 'An error occurred while processing your request.',
}));

jest.unstable_mockModule('../../src/lib/validation.js', () => ({
  parseCustomId: (customId: string, expectedParts: number) => {
    const parts = customId.split(':');
    if (parts.length !== expectedParts) {
      return { success: false, error: 'Invalid parts count' };
    }
    return { success: true, parts };
  },
  generateShortId: () => 'test1234',
}));

jest.unstable_mockModule('../../src/lib/constants.js', () => ({
  LIST_COMMAND_LIMITS: {
    NOTES_PER_PAGE: 4,
    REQUESTS_PER_PAGE: 5,
    STATE_CACHE_TTL_SECONDS: 300,
    RATE_LIMIT_MS: 0,
  },
}));

jest.unstable_mockModule('../../src/lib/permissions.js', () => ({
  hasManageGuildPermission: jest.fn(() => false),
}));

jest.unstable_mockModule('../../src/lib/discord-utils.js', () => ({
  suppressExpectedDiscordErrors: jest.fn(() => () => {}),
  extractPlatformMessageId: jest.fn(() => null),
}));

const {
  execute,
  handlePaginationButton,
  handleRequestQueuePageButton,
} = await import('../../src/commands/list.js');

function getNavCustomIds(components: any[]): string[] {
  if (!components || !Array.isArray(components)) return [];
  const ids: string[] = [];
  for (const component of components) {
    const json = typeof component?.toJSON === 'function' ? component.toJSON() : component;
    if (!json) continue;

    if (json.type === 1) {
      for (const btn of json.components || []) {
        if (btn.custom_id?.startsWith('nav:')) ids.push(btn.custom_id);
      }
    }

    if (json.type === 17 && json.components) {
      for (const child of json.components) {
        if (child.type === 1) {
          for (const btn of child.components || []) {
            if (btn.custom_id?.startsWith('nav:')) ids.push(btn.custom_id);
          }
        }
      }
    }
  }
  return ids;
}

function createMockInteraction(subcommand: string, userId: string = 'user-nav-test'): any {
  return {
    user: { id: userId, username: 'testuser', displayName: 'Test User', avatarURL: () => null },
    guildId: 'guild-456',
    channelId: 'channel-456',
    guild: {
      members: {
        cache: new Map(),
      },
    },
    options: {
      getSubcommand: jest.fn<() => string>().mockReturnValue(subcommand),
      getString: jest.fn<() => string | null>().mockReturnValue(null),
      getBoolean: jest.fn<() => boolean | null>().mockReturnValue(null),
      getInteger: jest.fn<() => number | null>().mockReturnValue(null),
    },
    deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
    editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
    reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
    deferred: true,
  };
}

function createMockButtonInteraction(customId: string, overrides: Record<string, any> = {}): any {
  const interaction: any = {
    customId,
    user: { id: 'user-nav-btn', username: 'testuser', displayName: 'Test User', avatarURL: () => null },
    guildId: 'guild-456',
    channelId: 'channel-456',
    guild: {
      members: {
        cache: new Map(),
      },
    },
    reply: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    deferReply: jest.fn<() => Promise<any>>(),
    editReply: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    update: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    deferUpdate: jest.fn<() => Promise<any>>(),
    followUp: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    deferred: false,
    replied: false,
    message: {
      id: 'msg-123',
      components: [],
      flags: { bitfield: 0 },
    },
    ...overrides,
  };
  interaction.deferReply.mockImplementation(async () => { interaction.deferred = true; });
  interaction.deferUpdate.mockImplementation(async () => { interaction.deferred = true; });
  return interaction;
}

function setupDefaultMocks() {
  mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
    data: {
      type: 'community-servers',
      id: 'community-uuid-123',
      attributes: {
        platform: 'discord',
        platform_community_server_id: 'guild-456',
        name: 'Test Guild',
        is_active: true,
        is_public: true,
      },
    },
    jsonapi: { version: '1.1' },
  });

  mockConfigCache.getRatingThresholds.mockResolvedValue({
    min_ratings_needed: 5,
    min_raters_per_note: 5,
  });

  mockServiceProvider.getGuildConfigService.mockReturnValue(mockGuildConfigService);
  mockServiceProvider.getListRequestsService.mockReturnValue(mockListRequestsService);

  mockGetBotChannelOrRedirect.mockResolvedValue({
    shouldProceed: true,
    botChannel: { id: 'channel-456', name: 'open-notes' },
  });

  mockResolveUserProfileId.mockImplementation(
    async (discordId: string) => `profile-uuid-${discordId}`
  );
}

describe('list command - Navigation button integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    cacheStore.clear();
    setupCacheImplementations();
    setupDefaultMocks();
  });

  describe('list notes subcommand', () => {
    it('should include nav buttons with Menu, List Requests, and Write Note in response', async () => {
      mockApiClient.listNotesWithStatus.mockResolvedValue({
        data: [
          {
            id: 'note-1',
            type: 'notes',
            attributes: {
              summary: 'Test note summary',
              ratings_count: 0,
            },
          },
        ],
        total: 1,
      });

      const interaction = createMockInteraction('notes', 'user-notes-1');
      await execute(interaction as any);

      expect(interaction.editReply).toHaveBeenCalled();
      const editReplyArg = interaction.editReply.mock.calls[0][0];
      const navIds = getNavCustomIds(editReplyArg.components);
      expect(navIds).toContain('nav:menu');
      expect(navIds).toContain('nav:list:requests');
      expect(navIds).toContain('nav:note:write');
    }, 10000);

    it('should include nav buttons even when notes queue is empty', async () => {
      mockApiClient.listNotesWithStatus.mockResolvedValue({
        data: [],
        total: 0,
      });

      const interaction = createMockInteraction('notes', 'user-notes-2');
      await execute(interaction as any);

      expect(interaction.editReply).toHaveBeenCalled();
      const editReplyArg = interaction.editReply.mock.calls[0][0];
      const navIds = getNavCustomIds(editReplyArg.components);
      expect(navIds).toContain('nav:menu');
    }, 10000);
  });

  describe('list requests subcommand', () => {
    it('should pass navContext to formatter for contextual nav', async () => {
      const requestsContainer = new ContainerBuilder();
      MockDiscordFormatter.formatListRequestsSuccessV2.mockResolvedValue({
        container: requestsContainer,
        components: [requestsContainer.toJSON()],
        flags: MessageFlags.IsComponentsV2,
        actionRows: [],
      });

      mockListRequestsService.execute.mockResolvedValue({
        success: true,
        data: {
          requests: [{ id: 'req-1', status: 'PENDING' }],
          total: 1,
          page: 1,
          size: 5,
        },
      });

      const interaction = createMockInteraction('requests', 'user-req-1');
      await execute(interaction as any);

      expect(MockDiscordFormatter.formatListRequestsSuccessV2).toHaveBeenCalledWith(
        expect.anything(),
        expect.anything(),
        'list:requests'
      );
    }, 10000);
  });

  describe('handlePaginationButton', () => {
    it('should include nav buttons in paginated notes response', async () => {
      const queueState = {
        userId: 'user-nav-btn',
        profileUuid: 'profile-uuid-user-nav-btn',
        guildId: 'guild-456',
        communityServerUuid: 'community-uuid-123',
        currentPage: 1,
        thresholds: { min_ratings_needed: 5, min_raters_per_note: 5 },
        isAdmin: false,
      };
      cacheStore.set('queue_state:state123', queueState);

      mockApiClient.listNotesWithStatus
        .mockResolvedValueOnce({ data: [], total: 8 })
        .mockResolvedValueOnce({
          data: [
            {
              id: 'note-2',
              type: 'notes',
              attributes: { summary: 'Page 2 note', ratings_count: 1 },
            },
          ],
          total: 8,
        });

      const interaction = createMockButtonInteraction('queue:next:state123');
      await handlePaginationButton(interaction as any);

      expect(interaction.update).toHaveBeenCalled();
      const updateArg = interaction.update.mock.calls[0][0];
      const navIds = getNavCustomIds(updateArg.components);
      expect(navIds).toContain('nav:menu');
    }, 10000);
  });

  describe('handleRequestQueuePageButton', () => {
    it('should pass navContext to formatter for paginated requests', async () => {
      const filterState = {
        status: 'PENDING',
        myRequestsOnly: false,
        communityServerId: 'community-uuid',
      };
      cacheStore.set('pagination:state123', filterState);

      const requestsContainer = new ContainerBuilder();
      MockDiscordFormatter.formatListRequestsSuccessV2.mockResolvedValue({
        container: requestsContainer,
        components: [requestsContainer.toJSON()],
        flags: MessageFlags.IsComponentsV2,
        actionRows: [],
      });

      mockListRequestsService.execute.mockResolvedValue({
        success: true,
        data: {
          requests: [{ id: 'req-2', status: 'PENDING' }],
          total: 10,
          page: 2,
          size: 5,
        },
      });

      const interaction = createMockButtonInteraction('request_queue_page:2:state123');
      await handleRequestQueuePageButton(interaction as any);

      expect(MockDiscordFormatter.formatListRequestsSuccessV2).toHaveBeenCalledWith(
        expect.anything(),
        expect.anything(),
        'list:requests'
      );
    }, 10000);
  });
});
