import { jest } from '@jest/globals';
import { MessageFlags, ChannelType, TextChannel } from 'discord.js';
import { createMockLogger, createSuccessResult, createErrorResult } from '../utils/service-mocks.js';
import { ErrorCode } from '../../src/services/types.js';
import { TEST_SCORE_ABOVE_THRESHOLD } from '../test-constants.js';

const mockLogger = createMockLogger();
const mockScoringService = {
  getNoteScore: jest.fn<(...args: any[]) => Promise<any>>(),
  getTopNotes: jest.fn<(...args: any[]) => Promise<any>>(),
  getScoringStatus: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockThread = {
  id: 'thread123',
  name: 'Test Thread',
  toString: () => '<#thread123>',
  send: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({ id: 'msg123' }),
};

const mockQueueManager = {
  getOrCreateOpenNotesThread: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(mockThread),
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

const mockCache = {
  get: jest.fn<(key: string) => unknown>(),
  set: jest.fn<(key: string, value: unknown, ttl?: number) => void>(),
  delete: jest.fn<(key: string) => void>(),
  start: jest.fn<() => void>(),
  stop: jest.fn<() => void>(),
  getMetrics: jest.fn(() => ({ size: 0 })),
};

const mockServiceProvider = {
  getScoringService: jest.fn(() => mockScoringService),
  getStatusService: jest.fn<() => any>(),
  getWriteNoteService: jest.fn<() => any>(),
  getViewNotesService: jest.fn<() => any>(),
  getRateNoteService: jest.fn<() => any>(),
  getRequestNoteService: jest.fn<() => any>(),
  getGuildConfigService: jest.fn<(...args: any[]) => any>(),
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

jest.unstable_mockModule('../../src/private-thread.js', () => ({
  getPrivateThreadManager: () => mockQueueManager,
  configCache: mockCache,
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
  extractPlatformMessageId: jest.fn((platformMessageId: string | null | undefined, _requestId: string) => platformMessageId ?? null),
  createForcePublishConfirmationButtons: jest.fn((noteId: string, shortId: string) => ({
    content: `Confirm Force Publish Note #${noteId}`,
    components: [],
  })),
  createDisabledForcePublishButtons: jest.fn(() => []),
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
      create: (jest.fn() as any).mockResolvedValue(mockThread),
    },
  };

  // Make instanceof TextChannel work
  Object.setPrototypeOf(mock, TextChannel.prototype);

  return mock as any;
}

describe('top-notes command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockServiceProvider.getScoringService.mockReturnValue(mockScoringService);
    mockDiscordFormatter.formatTopNotes.mockReturnValue({ embeds: [] });
    mockDiscordFormatter.formatTopNotesForQueue.mockReturnValue({
      summary: { embed: {} },
      items: [],
    });
    mockDiscordFormatter.formatError.mockReturnValue({ content: 'Error occurred' });
    mockQueueManager.getOrCreateOpenNotesThread.mockResolvedValue(mockThread);
    mockQueueRenderer.render.mockResolvedValue({
      summaryMessage: { id: 'summary123' },
      itemMessages: new Map(),
      paginationMessage: null,
    });
  });

  describe('successful execution', () => {
    it('should display top notes with default limit in a thread', async () => {
      mockScoringService.getTopNotes.mockResolvedValue(
        createSuccessResult({
          notes: [
            { note_id: 'note1', score: 0.95, confidence: 'standard', tier: 5, rating_count: 10, algorithm: 'matrix_factorization' },
            { note_id: 'note2', score: TEST_SCORE_ABOVE_THRESHOLD, confidence: 'standard', tier: 4, rating_count: 8, algorithm: 'matrix_factorization' },
          ],
          total_count: 2,
        })
      );

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
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
      expect(mockQueueManager.getOrCreateOpenNotesThread).toHaveBeenCalled();
      expect(mockDiscordFormatter.formatTopNotesForQueue).toHaveBeenCalled();
      expect(mockQueueRenderer.render).toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: expect.stringContaining('Top notes posted to'),
      });
    });

    it('should respect custom limit parameter', async () => {
      mockScoringService.getTopNotes.mockResolvedValue(
        createSuccessResult({
          notes: [],
          total_count: 0,
        })
      );

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
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
      mockScoringService.getTopNotes.mockResolvedValue(
        createSuccessResult({
          notes: [{ note_id: 'note1', score: 0.95, confidence: 'standard', tier: 5, rating_count: 10, algorithm: 'matrix_factorization' }],
          total_count: 1,
        })
      );

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
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
      mockScoringService.getTopNotes.mockResolvedValue(
        createSuccessResult({
          notes: [{ note_id: 'note1', score: 0.95, confidence: 'standard', tier: 5, rating_count: 10, algorithm: 'matrix_factorization' }],
          total_count: 1,
        })
      );

      const mockChannel = createMockTextChannel();
      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
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
      mockScoringService.getTopNotes.mockResolvedValue(
        createSuccessResult({
          notes: [],
          total_count: 0,
        })
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

      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: 'No notes found matching the specified criteria.',
      });
    });

    it('should reject non-text channels', async () => {
      const mockNonTextChannel = {
        id: 'channel123',
        type: ChannelType.GuildVoice,
      };

      const mockInteraction = {
        user: { id: 'user123', username: 'testuser' },
        guildId: 'guild456',
        channel: mockNonTextChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('top-notes'),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: 'This command can only be used in text channels or threads.',
      });
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
      mockScoringService.getTopNotes.mockResolvedValue(
        createSuccessResult({
          notes: [{ note_id: 'note1', score: 0.95, confidence: 'standard', tier: 5, rating_count: 10, algorithm: 'matrix_factorization' }],
          total_count: 10,
        })
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

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Top notes retrieved successfully',
        expect.objectContaining({
          note_count: 1,
          total_count: 10,
        })
      );
    });
  });
});
