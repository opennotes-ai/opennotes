import { jest } from '@jest/globals';

const mockWriteNoteService = {
  execute: jest.fn<() => Promise<any>>(),
};

const mockGuildConfigService = {
  get: jest.fn<() => Promise<boolean>>().mockResolvedValue(false),
};

const mockServiceProvider = {
  getWriteNoteService: jest.fn(() => mockWriteNoteService),
  getViewNotesService: jest.fn<() => any>(),
  getRateNoteService: jest.fn<() => any>(),
  getRequestNoteService: jest.fn<() => any>(),
  getStatusService: jest.fn<() => any>(),
  getGuildConfigService: jest.fn(() => mockGuildConfigService),
};

class MockDiscordFormatter {
  static formatWriteNoteSuccess = jest.fn();
  static formatError = jest.fn<(...args: any[]) => any>();
}

const mockDiscordFormatter = MockDiscordFormatter;

const mockLogger = {
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  info: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
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

jest.unstable_mockModule('../../src/services/index.js', () => ({
  serviceProvider: mockServiceProvider,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../../src/services/DiscordFormatter.js', () => ({
  DiscordFormatter: mockDiscordFormatter,
}));

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
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

jest.unstable_mockModule('../../src/lib/interaction-rate-limiter.js', () => ({
  modalSubmissionRateLimiter: {
    checkAndRecord: jest.fn(() => false), // Not rate limited
  },
}));

const { execute, handleModalSubmit } =
  await import('../../src/commands/note.js');

describe('note-write command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockServiceProvider.getWriteNoteService.mockReturnValue(mockWriteNoteService);
    mockServiceProvider.getGuildConfigService.mockReturnValue(mockGuildConfigService);
    // Set default return value for formatError
    mockDiscordFormatter.formatError.mockReturnValue({
      content: 'An error occurred',
    });
  });

  describe('execute', () => {
    it('should show modal', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('write'),
          getString: jest.fn<() => string>().mockReturnValue('12345678901234567'),
        },
        showModal: jest.fn(),
        reply: jest.fn<(opts: any) => Promise<any>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.showModal).toHaveBeenCalled();
      expect(mockInteraction.reply).not.toHaveBeenCalled();
    });

    it('should use correct message ID from options', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('write'),
          getString: jest.fn<() => string>().mockReturnValue('12345678901234789'),
        },
        showModal: jest.fn((modal: { data: { custom_id: string } }) => {
          expect(modal.data.custom_id).toBe('note-write:12345678901234789');
        }),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.options.getString).toHaveBeenCalledWith(
        'message-id',
        true,
      );
    });
  });

  describe('handleModalSubmit', () => {
    it('should create note successfully', async () => {
      const mockNote = {
        id: '123',
        messageId: '12345678901234567',
        authorId: 'user789',
        content: 'Test note content',
        createdAt: Date.now(),
        helpfulCount: 0,
        notHelpfulCount: 0,
      };

      mockWriteNoteService.execute.mockResolvedValue({
        success: true,
        data: mockNote,
      });

      mockDiscordFormatter.formatWriteNoteSuccess.mockReturnValue({
        embeds: [
          {
            data: {
              title: 'Community Note Created',
            },
          },
        ],
      });

      const mockInteraction = {
        customId: 'note-write:12345678901234567',
        user: {
          id: 'user789',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: null,
        fields: {
          getTextInputValue: jest.fn<() => string>().mockReturnValue('Test note content'),
        },
        deferReply: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<() => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<() => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      };

      await handleModalSubmit(mockInteraction as any);

      expect(mockInteraction.deferReply).toHaveBeenCalledWith({});
      expect(mockWriteNoteService.execute).toHaveBeenCalledWith({
        messageId: '12345678901234567',
        authorId: 'user789',
        content: 'Test note content',
        channelId: undefined,
        guildId: undefined,
        username: 'testuser',
        displayName: 'Test User',
        avatarUrl: 'https://example.com/avatar.png',
      });
      expect(mockDiscordFormatter.formatWriteNoteSuccess).toHaveBeenCalledWith(
        mockNote,
        '12345678901234567',
        undefined,
        undefined
      );
      expect(mockInteraction.editReply).toHaveBeenCalled();
    });

    it('should handle creation errors gracefully', async () => {
      mockWriteNoteService.execute.mockResolvedValue({
        success: false,
        error: {
          code: 'RATE_LIMIT_EXCEEDED',
          message: 'Rate limit exceeded',
        },
      });

      // Override the default formatError mock for this test
      mockDiscordFormatter.formatError.mockReturnValue({
        content: 'Failed to create note. Please try again later.',
      });

      const mockInteraction = {
        customId: 'note-write:msg456',
        user: {
          id: 'user789',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: null,
        fields: {
          getTextInputValue: jest.fn<() => string>().mockReturnValue('Test note content'),
        },
        deferReply: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<() => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<() => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      };

      await handleModalSubmit(mockInteraction as any);

      // Debug: check if service was called
      expect(mockWriteNoteService.execute).toHaveBeenCalled();
      expect(mockDiscordFormatter.formatError).toHaveBeenCalled();
      expect(mockInteraction.followUp).toHaveBeenCalledWith(
        expect.objectContaining({
          content: 'Failed to create note. Please try again later.',
          flags: 64, // MessageFlags.Ephemeral
        }),
      );
      expect(mockInteraction.deleteReply).toHaveBeenCalled();
    });
  });
});
