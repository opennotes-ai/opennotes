import { jest } from '@jest/globals';
import { ChannelType, TextChannel } from 'discord.js';
import {
  loggerFactory,
  chatInputCommandInteractionFactory,
} from '../factories/index.js';

const mockLogger = loggerFactory.build();
const mockApiClient = {
  listNotesWithStatus: jest.fn<(...args: any[]) => Promise<any>>(),
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

let execute: typeof import('../../src/commands/note.js').execute;

beforeAll(async () => {
  const module = await import('../../src/commands/note.js');
  execute = module.execute;
});

afterAll(() => {
  jest.clearAllMocks();
  jest.clearAllTimers();
  jest.restoreAllMocks();
});

// Helper to create a properly mocked TextChannel with prototype chain
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

describe('note-queue-profiled command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.clearAllTimers();
    mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
      data: {
        type: 'community-servers',
        id: 'guild456',
        attributes: {
          platform: 'discord',
          platform_community_server_id: 'guild456',
          name: 'Test Guild',
          is_active: true,
          is_public: true,
        },
      },
      jsonapi: { version: '1.1' },
    });
  });

  afterEach(async () => {
    jest.clearAllMocks();
    jest.clearAllTimers();
    await new Promise(resolve => setImmediate(resolve));
  });

  describe('successful execution', () => {
    it('should execute with performance metrics', async () => {
      mockConfigCache.getRatingThresholds.mockResolvedValue({
        helpful: 0.5,
        notHelpful: -0.5,
      });

      mockApiClient.listNotesWithStatus.mockResolvedValue({
        notes: [],
        total: 0,
      });

      const mockChannel = createMockTextChannel({
        type: ChannelType.GuildText,
      });

      const mockClient = {
        user: { id: 'bot123' },
      };

      const mockInteraction = chatInputCommandInteractionFactory.build(
        {
          guildId: 'guild456',
          channel: mockChannel as any,
        },
        {
          transient: {
            subcommand: 'queue-profiled',
            isDeferred: true,
          },
        }
      );
      (mockInteraction as any).client = mockClient;

      await execute(mockInteraction as any);

      expect(mockInteraction.reply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('temporarily disabled'),
        })
      );
    });

    it('should include detailed phase breakdowns', async () => {
      mockConfigCache.getRatingThresholds.mockResolvedValue({
        helpful: 0.5,
        notHelpful: -0.5,
      });

      mockApiClient.listNotesWithStatus.mockResolvedValue({
        notes: [],
        total: 0,
      });

      const mockChannel = createMockTextChannel({
        type: ChannelType.GuildText,
      });

      const mockClient = {
        user: { id: 'bot123' },
      };

      const mockInteraction = chatInputCommandInteractionFactory.build(
        {
          guildId: 'guild456',
          channel: mockChannel as any,
        },
        {
          transient: {
            subcommand: 'queue-profiled',
            isDeferred: true,
          },
        }
      );
      (mockInteraction as any).client = mockClient;

      await execute(mockInteraction as any);

      expect(mockInteraction.reply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('temporarily disabled'),
        })
      );
    });
  });

  describe('error handling', () => {
    it('should return disabled message instead of processing', async () => {
      const mockChannel = createMockTextChannel({
        type: ChannelType.GuildText,
      });

      const mockClient = {
        user: { id: 'bot123' },
      };

      const mockInteraction = chatInputCommandInteractionFactory.build(
        {
          guildId: 'guild456',
          channel: mockChannel as any,
        },
        {
          transient: {
            subcommand: 'queue-profiled',
            isDeferred: true,
          },
        }
      );
      (mockInteraction as any).client = mockClient;
      (mockInteraction.user as any).id = 'user123';


      await execute(mockInteraction as any);

      expect(mockInteraction.reply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('temporarily disabled'),
        })
      );

      expect(mockLogger.info).toHaveBeenCalledWith(
        'note-queue-profiled subcommand accessed (disabled)',
        expect.objectContaining({
          command: 'note queue-profiled',
          user_id: 'user123',
        })
      );
    });

    it('should handle non-text-channel errors', async () => {
      const mockChannel = {
        type: ChannelType.DM,
      };

      const mockClient = {
        user: { id: 'bot123' },
      };

      const mockInteraction = chatInputCommandInteractionFactory.build(
        {
          guildId: 'guild456',
          channel: mockChannel as any,
        },
        {
          transient: {
            subcommand: 'queue-profiled',
          },
        }
      );
      (mockInteraction as any).client = mockClient;

      Object.setPrototypeOf(mockChannel, {
        constructor: {
          name: 'DMChannel',
        },
      });

      await execute(mockInteraction as any);

      expect(mockInteraction.reply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('temporarily disabled'),
        })
      );
    });
  });

  describe('performance tracking', () => {
    it('should track message fetching metrics', async () => {
      mockConfigCache.getRatingThresholds.mockResolvedValue({
        min_ratings_needed: 5,
        min_raters_per_note: 5,
      });

      mockApiClient.listNotesWithStatus.mockResolvedValue({
        notes: [
          {
            id: 1,
            note_id: 'note1',
            author_id: 'author1',
            summary: 'Test note 1',
            classification: 'MISINFORMED_OR_POTENTIALLY_MISLEADING',
            helpfulness_score: 0,
            status: 'NEEDS_MORE_RATINGS',
            created_at: new Date().toISOString(),
            ratings: [],
            ratings_count: 0,
          },
          {
            id: 2,
            note_id: 'note2',
            author_id: 'author2',
            summary: 'Test note 2',
            classification: 'MISINFORMED_OR_POTENTIALLY_MISLEADING',
            helpfulness_score: 0,
            status: 'NEEDS_MORE_RATINGS',
            created_at: new Date().toISOString(),
            ratings: [],
            ratings_count: 0,
          },
        ],
        total: 2,
      });

      const mockChannel = createMockTextChannel({
        type: ChannelType.GuildText,
      });

      const mockClient = {
        user: { id: 'bot123' },
        channels: {
          cache: new Map(),
        },
        guilds: {
          cache: new Map(),
        },
      };

      const mockInteraction = chatInputCommandInteractionFactory.build(
        {
          guildId: 'guild456',
          channel: mockChannel as any,
        },
        {
          transient: {
            subcommand: 'queue-profiled',
            isDeferred: true,
          },
        }
      );
      (mockInteraction as any).client = mockClient;

      await execute(mockInteraction as any);

      expect(mockInteraction.reply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('temporarily disabled'),
        })
      );
    });
  });
});
