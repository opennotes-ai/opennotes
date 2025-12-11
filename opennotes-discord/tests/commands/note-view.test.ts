import { jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';
import {
  createMockLogger,
  createMockViewNotesService,
  createSuccessResult,
  createErrorResult,
} from '../utils/service-mocks.js';
import { ErrorCode } from '../../src/services/types.js';
import { TEST_SCORE_ABOVE_THRESHOLD } from '../test-constants.js';

const mockLogger = createMockLogger();
const mockViewNotesService = createMockViewNotesService();
const mockScoringService = {
  getNoteScore: jest.fn<(...args: any[]) => Promise<any>>(),
  getBatchNoteScores: jest.fn<(...args: any[]) => Promise<any>>(),
  getTopNotes: jest.fn<(...args: any[]) => Promise<any>>(),
  getScoringStatus: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockDiscordFormatter = {
  formatViewNotesSuccessV2: jest.fn().mockReturnValue({ embeds: [] }),
  formatErrorV2: jest.fn<(...args: any[]) => any>().mockReturnValue({ content: 'Error occurred' }),
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
  getViewNotesService: jest.fn(() => mockViewNotesService),
  getScoringService: jest.fn(() => mockScoringService),
  getStatusService: jest.fn<() => any>(),
  getWriteNoteService: jest.fn<() => any>(),
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

const { execute } = await import('../../src/commands/note.js');

describe('note-view command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockServiceProvider.getViewNotesService.mockReturnValue(mockViewNotesService);
    mockServiceProvider.getScoringService.mockReturnValue(mockScoringService);
    mockDiscordFormatter.formatViewNotesSuccessV2.mockReturnValue({ embeds: [] });
    mockDiscordFormatter.formatErrorV2.mockReturnValue({ content: 'Error occurred' });
  });

  describe('successful execution', () => {
    it('should display notes for a message', async () => {
      const mockNotes = [
        {
          id: '1',
          messageId: '12345678901234567',
          authorId: 'author1',
          content: 'This is a community note',
          createdAt: Date.now(),
          helpfulCount: 5,
          notHelpfulCount: 1,
        },
        {
          id: '2',
          messageId: '12345678901234567',
          authorId: 'author2',
          content: 'Another community note',
          createdAt: Date.now(),
          helpfulCount: 3,
          notHelpfulCount: 0,
        },
      ];

      mockViewNotesService.execute.mockResolvedValue(
        createSuccessResult({ notes: mockNotes })
      );

      mockScoringService.getBatchNoteScores.mockResolvedValue(
        createSuccessResult({
          scores: {
            '1': { score: TEST_SCORE_ABOVE_THRESHOLD, confidence: 'standard', tier: 4 },
            '2': { score: 0.72, confidence: 'standard', tier: 3 },
          },
        })
      );

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
          getString: jest.fn<() => string>().mockReturnValue('12345678901234567'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockViewNotesService.execute).toHaveBeenCalledWith(
        { messageId: '12345678901234567' },
        'user123'
      );
      expect(mockScoringService.getBatchNoteScores).toHaveBeenCalledWith(['1', '2']);
      expect(mockInteraction.editReply).toHaveBeenCalled();
    });

    it('should handle empty notes list', async () => {
      mockViewNotesService.execute.mockResolvedValue(
        createSuccessResult({ notes: [] })
      );

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
          getString: jest.fn<() => string>().mockReturnValue('12345678901234567'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: 'No community notes found for this message.',
      });
    });
  });

  describe('error handling', () => {
    it('should handle service errors', async () => {
      mockViewNotesService.execute.mockResolvedValue(
        createErrorResult(ErrorCode.API_ERROR, 'Failed to fetch notes')
      );

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
          getString: jest.fn<() => string>().mockReturnValue('12345678901234567'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.followUp).toHaveBeenCalledWith(
        expect.objectContaining({
          flags: MessageFlags.Ephemeral,
        })
      );
      expect(mockInteraction.deleteReply).toHaveBeenCalled();
    });

    it('should handle unexpected errors', async () => {
      mockViewNotesService.execute.mockRejectedValue(new Error('Unexpected error'));

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
          getString: jest.fn<() => string>().mockReturnValue('12345678901234567'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalled();
      expect(mockInteraction.followUp).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Failed to retrieve notes'),
          flags: MessageFlags.Ephemeral,
        })
      );
    });
  });

  describe('logging', () => {
    it('should log command execution', async () => {
      mockViewNotesService.execute.mockResolvedValue(
        createSuccessResult({ notes: [] })
      );

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('view'),
          getString: jest.fn<() => string>().mockReturnValue('12345678901234567'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Executing view-notes command',
        expect.objectContaining({
          command: 'note view',
          user_id: 'user123',
          message_id: '12345678901234567',
        })
      );
    });
  });
});
