import { jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';
import { createMockLogger, createSuccessResult, createErrorResult } from '../utils/service-mocks.js';
import { ErrorCode } from '../../src/services/types.js';
import { TEST_SCORE_ABOVE_THRESHOLD, TEST_NOTE_UUID } from '../test-constants.js';

const mockLogger = createMockLogger();
const mockScoringService = {
  getNoteScore: jest.fn<(...args: any[]) => Promise<any>>(),
  getTopNotes: jest.fn<(...args: any[]) => Promise<any>>(),
  getScoringStatus: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockDiscordFormatter = {
  formatNoteScore: jest.fn().mockReturnValue({ embeds: [] }),
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

describe('note-score command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockServiceProvider.getScoringService.mockReturnValue(mockScoringService);
    mockDiscordFormatter.formatNoteScore.mockReturnValue({ embeds: [] });
    mockDiscordFormatter.formatError.mockReturnValue({ content: 'Error occurred' });
  });

  describe('successful execution', () => {
    it('should display note score', async () => {
      mockScoringService.getNoteScore.mockResolvedValue(
        createSuccessResult({
          noteId: TEST_NOTE_UUID,
          score: TEST_SCORE_ABOVE_THRESHOLD,
          confidence: 'standard',
          tier: 4,
          totalRatings: 15,
        })
      );

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('score'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockScoringService.getNoteScore).toHaveBeenCalledWith(TEST_NOTE_UUID);
      expect(mockInteraction.editReply).toHaveBeenCalled();
      expect(mockLogger.info).toHaveBeenCalledWith(
        'Note score retrieved successfully',
        expect.objectContaining({
          note_id: TEST_NOTE_UUID,
          score: TEST_SCORE_ABOVE_THRESHOLD,
          confidence: 'standard',
        })
      );
    });
  });

  describe('error handling', () => {
    it('should handle NOT_FOUND error', async () => {
      mockScoringService.getNoteScore.mockResolvedValue(
        createErrorResult(ErrorCode.NOT_FOUND, 'Note not found')
      );

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('score'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
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
          content: expect.stringContaining('not found'),
          flags: MessageFlags.Ephemeral,
        })
      );
      expect(mockInteraction.deleteReply).toHaveBeenCalled();
    });

    it('should handle API_ERROR with default message', async () => {
      mockScoringService.getNoteScore.mockResolvedValue(
        createErrorResult(ErrorCode.API_ERROR, 'Score calculation in progress')
      );

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('score'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
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
          content: expect.stringContaining('Failed to retrieve score'),
        })
      );
    });

    it('should handle API_ERROR for service unavailable', async () => {
      mockScoringService.getNoteScore.mockResolvedValue(
        createErrorResult(ErrorCode.API_ERROR, 'Service unavailable')
      );

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('score'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
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
          content: expect.stringContaining('Failed to retrieve score'),
        })
      );
    });

    it('should handle VALIDATION_ERROR', async () => {
      mockScoringService.getNoteScore.mockResolvedValue(
        createErrorResult(ErrorCode.VALIDATION_ERROR, 'Invalid note ID format')
      );

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('score'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
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
          content: expect.stringContaining('Invalid note ID format'),
        })
      );
    });

    it('should handle unexpected errors', async () => {
      mockScoringService.getNoteScore.mockRejectedValue(new Error('Unexpected error'));

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('score'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
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
          content: expect.stringContaining('Error ID'),
          flags: MessageFlags.Ephemeral,
        })
      );
    });
  });
});
