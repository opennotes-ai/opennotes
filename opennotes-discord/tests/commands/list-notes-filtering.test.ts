import { jest } from '@jest/globals';
import { ChannelType, TextChannel } from 'discord.js';
import { createMockLogger } from '../utils/service-mocks.js';

const mockLogger = createMockLogger();

const mockApiClient = {
  listNotesWithStatus: jest.fn<(...args: any[]) => Promise<any>>(),
  listNotesRatedByUser: jest.fn<(...args: any[]) => Promise<any>>(),
  getCommunityServerByPlatformId: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockCache = {
  get: jest.fn<(key: string) => unknown>(),
  set: jest.fn<(key: string, value: unknown, ttl?: number) => void>(),
  delete: jest.fn<(key: string) => void>(),
  start: jest.fn<() => void>(),
  stop: jest.fn<() => void>(),
  getMetrics: jest.fn(() => ({ size: 0 })),
};

const mockConfigCache = {
  getRatingThresholds: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockQueueRenderer = {
  render: jest.fn<(...args: any[]) => Promise<any>>(),
  update: jest.fn<(...args: any[]) => Promise<any>>(),
  getAllMessages: jest.fn<(...args: any[]) => any[]>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../../src/lib/config-cache.js', () => ({
  ConfigCache: jest.fn(() => mockConfigCache),
}));

jest.unstable_mockModule('../../src/lib/queue-renderer.js', () => ({
  QueueRenderer: mockQueueRenderer,
  QueueRendererV2: {
    ...mockQueueRenderer,
    buildContainers: jest.fn<(...args: any[]) => any[]>().mockReturnValue([{ toJSON: () => ({}) }]),
  },
}));

const mockGuildConfigService = {
  get: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue('open-notes'),
  set: jest.fn<(...args: any[]) => Promise<any>>(),
  delete: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockServiceProvider = {
  getGuildConfigService: jest.fn(() => mockGuildConfigService),
};

jest.unstable_mockModule('../../src/services/index.js', () => ({
  serviceProvider: mockServiceProvider,
}));

jest.unstable_mockModule('../../src/lib/bot-channel-helper.js', () => ({
  getBotChannelOrRedirect: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
    shouldProceed: true,
    botChannel: { id: 'channel-456', name: 'open-notes' },
  }),
  checkBotChannel: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
    isInBotChannel: true,
    botChannel: { id: 'channel-456', name: 'open-notes' },
    botChannelName: 'open-notes',
  }),
  ensureBotChannel: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({ id: 'channel-456', name: 'open-notes' }),
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

let execute: typeof import('../../src/commands/list.js').execute;

beforeAll(async () => {
  const module = await import('../../src/commands/list.js');
  execute = module.execute;
});

afterAll(() => {
  jest.useRealTimers();
});

function createMockTextChannel(overrides?: any): any {
  const channelType = overrides?.type || ChannelType.GuildText;

  const mockChannel = Object.create(TextChannel.prototype, {
    type: { value: channelType, configurable: true, writable: true },
    id: { value: 'channel-456', configurable: true, writable: true },
    guild: { value: { id: 'guild-789' }, configurable: true, writable: true },
    name: { value: 'test-channel', configurable: true, writable: true },
    send: { value: jest.fn<() => Promise<any>>().mockResolvedValue({}), configurable: true, writable: true },
    threads: { value: { create: jest.fn() }, configurable: true, writable: true },
    permissionsFor: { value: jest.fn().mockReturnValue({ has: jest.fn().mockReturnValue(true) }), configurable: true, writable: true },
  });

  if (overrides) {
    Object.keys(overrides).forEach(key => {
      if (key !== 'type') {
        Object.defineProperty(mockChannel, key, {
          value: overrides[key],
          writable: true,
          configurable: true,
        });
      }
    });
  }

  return mockChannel;
}

function setupDefaultMocks(communityUuid: string = 'community-uuid-123'): void {
  mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
    data: {
      type: 'community-servers',
      id: communityUuid,
      attributes: {
        platform: 'discord',
        platform_id: 'guild-456',
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

  mockApiClient.listNotesWithStatus.mockResolvedValue({
    notes: [],
    total: 0,
  });

  mockApiClient.listNotesRatedByUser.mockResolvedValue({
    notes: [],
    total: 0,
  });

  mockQueueRenderer.render.mockResolvedValue({
    summaryMessage: { id: 'summary-msg-1' },
    itemMessages: [],
    paginationMessage: null,
  });
  mockQueueRenderer.getAllMessages.mockReturnValue([{
    createMessageComponentCollector: jest.fn().mockReturnValue({
      on: jest.fn(),
    }),
  }]);
}

function createMockInteraction(userId: string = 'user-123', guildId: string = 'guild-456'): any {
  const mockChannel = createMockTextChannel({
    type: ChannelType.GuildText,
  });

  return {
    user: { id: userId },
    guildId: guildId,
    channel: mockChannel,
    guild: {
      members: {
        cache: new Map(),
      },
    },
    options: {
      getSubcommand: jest.fn<() => string>().mockReturnValue('notes'),
    },
    deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
    editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
    reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
    deferred: true,
  };
}

let mockBotChannelHelper: any;
let mockQueueRendererModule: any;

describe('list notes filtering', () => {
  beforeEach(async () => {
    jest.clearAllMocks();

    mockBotChannelHelper = await import('../../src/lib/bot-channel-helper.js');
    (mockBotChannelHelper.getBotChannelOrRedirect as any).mockResolvedValue({
      shouldProceed: true,
      botChannel: { id: 'channel-456', name: 'open-notes' },
    });
    (mockBotChannelHelper.checkBotChannel as any).mockResolvedValue({
      isInBotChannel: true,
      botChannel: { id: 'channel-456', name: 'open-notes' },
      botChannelName: 'open-notes',
    });
    (mockBotChannelHelper.ensureBotChannel as any).mockResolvedValue({ id: 'channel-456', name: 'open-notes' });

    mockQueueRendererModule = await import('../../src/lib/queue-renderer.js');
    (mockQueueRendererModule.QueueRendererV2.buildContainers as any).mockReturnValue([{ toJSON: () => ({}) }]);
  });

  describe('Notes queue API call', () => {
    it('should call listNotesWithStatus with NEEDS_MORE_RATINGS filter excluding user rated notes', async () => {
      setupDefaultMocks();
      const mockInteraction = createMockInteraction('user-123', 'guild-456');

      await execute(mockInteraction as any);

      expect(mockApiClient.listNotesWithStatus).toHaveBeenCalledTimes(1);
      expect(mockApiClient.listNotesWithStatus).toHaveBeenCalledWith(
        'NEEDS_MORE_RATINGS',
        1,
        4,
        'community-uuid-123',
        'user-123'
      );

      const calls = mockApiClient.listNotesWithStatus.mock.calls;
      const [status, page, size, communityServerId, excludeRatedByUserId] = calls[0];

      expect(status).toBe('NEEDS_MORE_RATINGS');
      expect(page).toBe(1);
      expect(size).toBe(4);
      expect(communityServerId).toBe('community-uuid-123');
      expect(excludeRatedByUserId).toBe('user-123');
    }, 10000);

    it('should still call listNotesWithStatus when community server UUID is unavailable', async () => {
      mockApiClient.getCommunityServerByPlatformId.mockRejectedValue(
        new Error('Community server not found')
      );
      mockConfigCache.getRatingThresholds.mockResolvedValue({
        min_ratings_needed: 5,
        min_raters_per_note: 5,
      });
      mockApiClient.listNotesWithStatus.mockResolvedValue({
        notes: [],
        total: 0,
      });
      mockQueueRenderer.render.mockResolvedValue({
        summaryMessage: { id: 'summary-msg-1' },
        itemMessages: [],
        paginationMessage: null,
      });
      mockQueueRenderer.getAllMessages.mockReturnValue([{
        createMessageComponentCollector: jest.fn().mockReturnValue({
          on: jest.fn(),
        }),
      }]);

      const mockInteraction = createMockInteraction('user-456', 'guild-456');

      await execute(mockInteraction as any);

      expect(mockApiClient.listNotesWithStatus).toHaveBeenCalledWith(
        'NEEDS_MORE_RATINGS',
        1,
        4,
        undefined,
        'user-456'
      );
    }, 10000);
  });
});
