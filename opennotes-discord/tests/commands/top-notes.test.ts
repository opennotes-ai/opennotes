import { jest } from '@jest/globals';
import { MessageFlags, ChannelType, TextChannel } from 'discord.js';
import { createSuccessResult, createErrorResult, createMockTopNotesJSONAPIResponse } from '../utils/service-mocks.js';
import { ErrorCode } from '../../src/services/types.js';
import { TEST_SCORE_ABOVE_THRESHOLD } from '../test-constants.js';
import { loggerFactory, cacheFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();
const mockScoringService = {
  getNoteScore: jest.fn<(...args: any[]) => Promise<any>>(),
  getTopNotes: jest.fn<(...args: any[]) => Promise<any>>(),
  getScoringStatus: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockQueueRenderer = {
  render: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
    summaryMessage: { id: 'summary123' },
    itemMessages: new Map(),
    paginationMessage: null,
  }),
};

const mockDiscordFormatter = {
  formatTopNotes: jest.fn().mockReturnValue({ embeds: [] }),
  formatTopNotesForQueue: jest.fn().mockReturnValue({
    summary: { embed: {} },
    items: [],
  }),
  formatTopNotesForQueueV2: jest.fn().mockReturnValue({
    container: { toJSON: () => ({}) },
    components: [{}],
    flags: MessageFlags.IsComponentsV2,
    forcePublishButtonRows: [],
  }),
  formatError: jest.fn<(...args: any[]) => any>().mockReturnValue({ content: 'Error occurred' }),
};

const mockApiClient = {
  healthCheck: jest.fn<() => Promise<any>>(),
  createNote: jest.fn<(...args: any[]) => Promise<any>>(),
  getNotes: jest.fn<(...args: any[]) => Promise<any>>(),
  rateNote: jest.fn<(...args: any[]) => Promise<any>>(),
  scoreNotes: jest.fn<(...args: any[]) => Promise<any>>(),
  createNoteRequest: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockCache = cacheFactory.build();

const mockGuildConfigService = {
  get: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue('open-notes'),
  set: jest.fn<(...args: any[]) => Promise<any>>(),
  delete: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockServiceProvider = {
  getScoringService: jest.fn(() => mockScoringService),
  getStatusService: jest.fn<() => any>(),
  getWriteNoteService: jest.fn<() => any>(),
  getViewNotesService: jest.fn<() => any>(),
  getRateNoteService: jest.fn<() => any>(),
  getRequestNoteService: jest.fn<() => any>(),
  getGuildConfigService: jest.fn(() => mockGuildConfigService),
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

jest.unstable_mockModule('../../src/services/index.js', () => ({
  serviceProvider: mockServiceProvider,
}));

jest.unstable_mockModule('../../src/services/DiscordFormatter.js', () => ({
  DiscordFormatter: mockDiscordFormatter,
}));

jest.unstable_mockModule('../../src/lib/config-cache.js', () => ({
  ConfigCache: jest.fn(() => mockCache),
}));

jest.unstable_mockModule('../../src/lib/queue-renderer.js', () => ({
  QueueRenderer: mockQueueRenderer,
  QueueRendererV2: mockQueueRenderer,
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
    constructor(message: string, public endpoint?: string, public statusCode?: number, public responseBody?: any) {
      super(message);
    }
  },
}));

jest.unstable_mockModule('../../src/lib/discord-utils.js', () => ({
  suppressExpectedDiscordErrors: jest.fn(() => jest.fn()),
  extractPlatformMessageId: jest.fn((platformMessageId: string | null, _requestId: string) => platformMessageId ?? null),
  createForcePublishConfirmationButtons: jest.fn((noteId: string, shortId: string) => ({
    content: `Confirm Force Publish Note #${noteId}`,
    components: [],
  })),
  createDisabledForcePublishButtons: jest.fn(() => []),
}));

jest.unstable_mockModule('../../src/lib/bot-channel-helper.js', () => {
  return {
    getBotChannelOrRedirect: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
      shouldProceed: true,
      botChannel: { id: 'channel123', name: 'open-notes' },
    }),
    checkBotChannel: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
      isInBotChannel: true,
      botChannel: { id: 'channel123', name: 'open-notes' },
      botChannelName: 'open-notes',
    }),
    ensureBotChannel: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({ id: 'channel123', name: 'open-notes' }),
  };
});

jest.unstable_mockModule('../../src/services/BotChannelService.js', () => ({
  BotChannelService: class MockBotChannelService {
    findChannel() {
      return { id: 'channel123', name: 'open-notes' };
    }
    async ensureChannelExists() {
      return { channel: { id: 'channel123', name: 'open-notes' }, wasCreated: false };
    }
  },
}));

const { execute } = await import('../../src/commands/list.js');

function createMockTextChannel() {
  const mock = {
    id: 'channel123',
    type: ChannelType.GuildText,
    guild: {
      id: 'guild456',
      members: {
        fetchMe: (jest.fn() as any).mockResolvedValue({
          permissions: {
            has: jest.fn().mockReturnValue(true),
          },
        }),
      },
    },
    permissionsFor: jest.fn().mockReturnValue({
      has: jest.fn().mockReturnValue(true),
    }),
    threads: {
      create: (jest.fn() as any).mockResolvedValue({
        id: 'thread123',
        name: 'test-thread',
        send: (jest.fn() as any).mockResolvedValue({}),
      }),
    },
  };

  Object.setPrototypeOf(mock, TextChannel.prototype);

  return mock as any;
}

let mockBotChannelHelper: any;

describe('top-notes command', () => {
  beforeEach(async () => {
    jest.clearAllMocks();
    mockServiceProvider.getScoringService.mockReturnValue(mockScoringService);
    mockDiscordFormatter.formatTopNotes.mockReturnValue({ embeds: [] });
    mockDiscordFormatter.formatTopNotesForQueue.mockReturnValue({
      summary: { embed: {} },
      items: [],
    });
    mockDiscordFormatter.formatTopNotesForQueueV2.mockReturnValue({
      container: { toJSON: () => ({}) },
      components: [{}],
      flags: MessageFlags.IsComponentsV2,
      forcePublishButtonRows: [],
    });
    mockDiscordFormatter.formatError.mockReturnValue({ content: 'Error occurred' });
    mockQueueRenderer.render.mockResolvedValue({
      summaryMessage: { id: 'summary123' },
      itemMessages: new Map(),
      paginationMessage: null,
    });

    mockBotChannelHelper = await import('../../src/lib/bot-channel-helper.js');
    (mockBotChannelHelper.getBotChannelOrRedirect as any).mockResolvedValue({
      shouldProceed: true,
      botChannel: { id: 'channel123', name: 'open-notes' },
    });
    (mockBotChannelHelper.checkBotChannel as any).mockResolvedValue({
      isInBotChannel: true,
      botChannel: { id: 'channel123', name: 'open-notes' },
      botChannelName: 'open-notes',
    });
    (mockBotChannelHelper.ensureBotChannel as any).mockResolvedValue({ id: 'channel123', name: 'open-notes' });
  });

  describe('successful execution', () => {
    it('should display top notes with default limit as ephemeral message', async () => {
      const mockTopNotesResponse = createMockTopNotesJSONAPIResponse({
        notes: [
          { noteId: 'note1', score: 0.95, confidence: 'standard', tier: 5, ratingCount: 10 },
          { noteId: 'note2', score: TEST_SCORE_ABOVE_THRESHOLD, confidence: 'standard', tier: 4, ratingCount: 8 },
        ],
        totalCount: 2,
      });

      mockScoringService.getTopNotes.mockResolvedValue(
        createSuccessResult(mockTopNotesResponse)
      );

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
        guild: {
          id: 'guild456',
          members: {
            cache: {
              get: jest.fn().mockReturnValue(null),
            },
          },
        },
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('top-notes'),
          getInteger: jest.fn((name: string) => {
            if (name === 'limit') return null;
            if (name === 'tier') return null;
            return null;
          }),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.deferReply).toHaveBeenCalledWith({ flags: MessageFlags.Ephemeral });
      expect(mockScoringService.getTopNotes).toHaveBeenCalledWith({
        limit: 10,
        minConfidence: undefined,
        tier: undefined,
      });
      expect(mockDiscordFormatter.formatTopNotesForQueueV2).toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        components: expect.any(Array),
        flags: MessageFlags.IsComponentsV2,
      });
    });

    it('should respect custom limit parameter', async () => {
      const mockEmptyResponse = createMockTopNotesJSONAPIResponse({
        notes: [],
        totalCount: 0,
      });

      mockScoringService.getTopNotes.mockResolvedValue(
        createSuccessResult(mockEmptyResponse)
      );

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
        guild: {
          id: 'guild456',
          members: {
            cache: {
              get: jest.fn().mockReturnValue(null),
            },
          },
        },
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('top-notes'),
          getInteger: jest.fn((name: string) => {
            if (name === 'limit') return 25;
            if (name === 'tier') return null;
            return null;
          }),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockScoringService.getTopNotes).toHaveBeenCalledWith({
        limit: 25,
        minConfidence: undefined,
        tier: undefined,
      });
    });

    it('should filter by confidence level', async () => {
      const mockResponse = createMockTopNotesJSONAPIResponse({
        notes: [{ noteId: 'note1', score: 0.95, confidence: 'standard', tier: 5, ratingCount: 10 }],
        totalCount: 1,
      });

      mockScoringService.getTopNotes.mockResolvedValue(
        createSuccessResult(mockResponse)
      );

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
        guild: {
          id: 'guild456',
          members: {
            cache: {
              get: jest.fn().mockReturnValue(null),
            },
          },
        },
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('top-notes'),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
          getString: jest.fn<() => string>().mockReturnValue('standard'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockScoringService.getTopNotes).toHaveBeenCalledWith({
        limit: 10,
        minConfidence: 'standard',
        tier: undefined,
      });
    });

    it('should filter by tier', async () => {
      const mockResponse = createMockTopNotesJSONAPIResponse({
        notes: [{ noteId: 'note1', score: 0.95, confidence: 'standard', tier: 5, ratingCount: 10 }],
        totalCount: 1,
      });

      mockScoringService.getTopNotes.mockResolvedValue(
        createSuccessResult(mockResponse)
      );

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
        guild: {
          id: 'guild456',
          members: {
            cache: {
              get: jest.fn().mockReturnValue(null),
            },
          },
        },
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('top-notes'),
          getInteger: jest.fn((name: string) => {
            if (name === 'tier') return 5;
            return null;
          }),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockScoringService.getTopNotes).toHaveBeenCalledWith({
        limit: 10,
        minConfidence: undefined,
        tier: 5,
      });
    });

    it('should handle empty results', async () => {
      const mockEmptyResponse = createMockTopNotesJSONAPIResponse({
        notes: [],
        totalCount: 0,
      });

      mockScoringService.getTopNotes.mockResolvedValue(
        createSuccessResult(mockEmptyResponse)
      );

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
        guild: {
          id: 'guild456',
          members: {
            cache: {
              get: jest.fn().mockReturnValue(null),
            },
          },
        },
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('top-notes'),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: 'No notes found matching the specified criteria.',
      });
    });

    it('should redirect to bot channel when not in bot channel', async () => {
      const botChannelHelper = await import('../../src/lib/bot-channel-helper.js');
      (botChannelHelper.getBotChannelOrRedirect as any).mockResolvedValueOnce({
        shouldProceed: false,
        botChannel: { id: 'bot-channel-123', name: 'open-notes' },
      });

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('top-notes'),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockScoringService.getTopNotes).not.toHaveBeenCalled();
    });
  });

  describe('error handling', () => {
    it('should handle SERVICE_UNAVAILABLE error', async () => {
      mockScoringService.getTopNotes.mockResolvedValue(
        createErrorResult(ErrorCode.API_ERROR, 'Service unavailable')
      );

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('top-notes'),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Failed to retrieve top notes'),
        })
      );
    });

    it('should handle generic errors', async () => {
      mockScoringService.getTopNotes.mockResolvedValue(
        createErrorResult(ErrorCode.UNKNOWN_ERROR, 'Unknown error')
      );

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('top-notes'),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Failed to retrieve top notes'),
        })
      );
    });

    it('should handle unexpected errors', async () => {
      mockScoringService.getTopNotes.mockRejectedValue(new Error('Unexpected error'));

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('top-notes'),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Error ID'),
        })
      );
    });
  });

  describe('logging', () => {
    it('should log successful execution', async () => {
      const mockResponse = createMockTopNotesJSONAPIResponse({
        notes: [{ noteId: 'note1', score: 0.95, confidence: 'standard', tier: 5, ratingCount: 10 }],
        totalCount: 10,
      });

      mockScoringService.getTopNotes.mockResolvedValue(
        createSuccessResult(mockResponse)
      );

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
        guild: {
          id: 'guild456',
          members: {
            cache: {
              get: jest.fn().mockReturnValue(null),
            },
          },
        },
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('top-notes'),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Top notes rendered as ephemeral message',
        expect.objectContaining({
          note_count: 1,
          total_count: 10,
        })
      );
    });
  });
});
