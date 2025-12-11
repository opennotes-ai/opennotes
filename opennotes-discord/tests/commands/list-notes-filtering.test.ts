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

const mockQueueManager = {
  getOrCreateOpenNotesThread: jest.fn<(...args: any[]) => Promise<any>>(),
  getNotesPerPage: jest.fn<() => number>().mockReturnValue(4),
  getCurrentPage: jest.fn<() => number>().mockReturnValue(1),
  setPage: jest.fn<(...args: any[]) => void>(),
  updateNotes: jest.fn<(...args: any[]) => void>(),
  getNotes: jest.fn<() => any[]>().mockReturnValue([]),
  closeQueue: jest.fn<(...args: any[]) => void>(),
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

jest.unstable_mockModule('../../src/private-thread.js', () => ({
  configCache: mockConfigCache,
  getPrivateThreadManager: () => mockQueueManager,
}));

jest.unstable_mockModule('../../src/lib/queue-renderer.js', () => ({
  QueueRenderer: mockQueueRenderer,
  QueueRendererV2: mockQueueRenderer,
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

function createMockThread(): any {
  return {
    id: 'thread-123',
    send: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
      createMessageComponentCollector: jest.fn<() => any>().mockReturnValue({
        on: jest.fn<(event: string, handler: any) => any>(),
      }),
    }),
    toString: () => '<#thread-123>',
  };
}

function setupDefaultMocks(communityUuid: string = 'community-uuid-123'): void {
  mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
    id: communityUuid,
    platform: 'discord',
    platform_id: 'guild-456',
    name: 'Test Guild',
    is_active: true,
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

  const mockThread = createMockThread();
  mockQueueManager.getOrCreateOpenNotesThread.mockResolvedValue(mockThread);

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

describe('list notes filtering', () => {
  describe('Section 2 - Your Rated Notes API call', () => {
    it('should call listNotesRatedByUser with correct parameters including NEEDS_MORE_RATINGS status filter', async () => {
      setupDefaultMocks();
      const mockInteraction = createMockInteraction('user-123', 'guild-456');

      await execute(mockInteraction as any);

      expect(mockApiClient.listNotesRatedByUser).toHaveBeenCalledTimes(1);
      expect(mockApiClient.listNotesRatedByUser).toHaveBeenCalledWith(
        'user-123',
        1,
        5,
        'community-uuid-123',
        'NEEDS_MORE_RATINGS'
      );

      const calls = mockApiClient.listNotesRatedByUser.mock.calls;
      const [raterParticipantId, page, size, communityServerId, statusFilter] = calls[0];

      expect(raterParticipantId).toBe('user-123');
      expect(page).toBe(1);
      expect(size).toBe(5);
      expect(communityServerId).toBe('community-uuid-123');
      expect(statusFilter).toBe('NEEDS_MORE_RATINGS');
      expect(statusFilter).not.toBe('CURRENTLY_RATED_HELPFUL');
      expect(statusFilter).not.toBe('CURRENTLY_RATED_NOT_HELPFUL');
    }, 10000);

    it('should skip rated notes section when community server UUID is unavailable', async () => {
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
      const mockThread = createMockThread();
      mockQueueManager.getOrCreateOpenNotesThread.mockResolvedValue(mockThread);
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

      const mockInteraction = createMockInteraction('user-123', 'guild-456');

      await execute(mockInteraction as any);

      expect(mockApiClient.listNotesRatedByUser).not.toHaveBeenCalled();
    }, 10000);
  });
});
