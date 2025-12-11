import { jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';
import { ConfigKey } from '../../src/lib/config-schema.js';
import {
  createMockLogger,
  createSuccessResult,
  createErrorResult,
  createMockRateNoteService,
} from '../utils/service-mocks.js';
import { ErrorCode } from '../../src/services/types.js';
import { TEST_NOTE_UUID } from '../test-constants.js';

const mockLogger = createMockLogger();
const mockRateNoteService = createMockRateNoteService();
const mockGuildConfigService = {
  get: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(false),
};

const mockDiscordFormatter = {
  formatRateNoteSuccessV2: jest.fn().mockReturnValue({ embeds: [] }),
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
  getRateNoteService: jest.fn(() => mockRateNoteService),
  getGuildConfigService: jest.fn(() => mockGuildConfigService),
  getStatusService: jest.fn<() => any>(),
  getWriteNoteService: jest.fn<() => any>(),
  getViewNotesService: jest.fn<() => any>(),
  getRequestNoteService: jest.fn<() => any>(),
  getScoringService: jest.fn<() => any>(),
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

describe('note-rate command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Re-set mock implementations after clearAllMocks()
    mockServiceProvider.getRateNoteService.mockReturnValue(mockRateNoteService);
    mockServiceProvider.getGuildConfigService.mockReturnValue(mockGuildConfigService);
    mockGuildConfigService.get.mockResolvedValue(false);
    mockDiscordFormatter.formatRateNoteSuccessV2.mockReturnValue({ embeds: [] });
    mockDiscordFormatter.formatErrorV2.mockReturnValue({ content: 'Error occurred' });
  });

  describe('successful rating', () => {
    it('should rate note as helpful', async () => {
      mockRateNoteService.execute.mockResolvedValue(
        createSuccessResult({
          rating: {
            noteId: TEST_NOTE_UUID,
            userId: 'user456',
            helpful: true,
            createdAt: Date.now(),
          },
        })
      );

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: 'guild789',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('rate'),
          getString: jest.fn((name: string) => {
            if (name === 'note-id') return TEST_NOTE_UUID;
            return null;
          }),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(true),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockRateNoteService.execute).toHaveBeenCalledWith({
        noteId: TEST_NOTE_UUID,
        userId: 'user456',
        helpful: true,
        username: 'testuser',
        displayName: 'Test User',
        avatarUrl: 'https://example.com/avatar.png',
        guildId: 'guild789',
      });
      expect(mockInteraction.editReply).toHaveBeenCalled();
    });

    it('should rate note as not helpful', async () => {
      mockRateNoteService.execute.mockResolvedValue(
        createSuccessResult({
          rating: {
            noteId: TEST_NOTE_UUID,
            userId: 'user456',
            helpful: false,
            createdAt: Date.now(),
          },
        })
      );

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: 'guild789',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('rate'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(false),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockRateNoteService.execute).toHaveBeenCalledWith({
        noteId: TEST_NOTE_UUID,
        userId: 'user456',
        helpful: false,
        username: 'testuser',
        displayName: 'Test User',
        avatarUrl: 'https://example.com/avatar.png',
        guildId: 'guild789',
      });
      expect(mockInteraction.editReply).toHaveBeenCalled();
    });
  });

  describe('ephemeral configuration', () => {
    it('should respect ephemeral config when true', async () => {
      mockGuildConfigService.get.mockResolvedValue(true);
      mockRateNoteService.execute.mockResolvedValue(
        createSuccessResult({
          rating: {
            noteId: TEST_NOTE_UUID,
            userId: 'user456',
            helpful: true,
            createdAt: Date.now(),
          },
        })
      );

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: 'guild789',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('rate'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(true),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockGuildConfigService.get).toHaveBeenCalledWith('guild789', ConfigKey.RATE_NOTE_EPHEMERAL);
      expect(mockInteraction.deferReply).toHaveBeenCalledWith({ flags: MessageFlags.Ephemeral });
      expect(mockInteraction.editReply).toHaveBeenCalled();
    });

    it('should respect ephemeral config when false', async () => {
      mockGuildConfigService.get.mockResolvedValue(false);
      mockRateNoteService.execute.mockResolvedValue(
        createSuccessResult({
          rating: {
            noteId: TEST_NOTE_UUID,
            userId: 'user456',
            helpful: true,
            createdAt: Date.now(),
          },
        })
      );

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: 'guild789',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('rate'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(true),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.deferReply).toHaveBeenCalledWith({});
    });

    it('should work without guildId', async () => {
      mockRateNoteService.execute.mockResolvedValue(
        createSuccessResult({
          rating: {
            noteId: TEST_NOTE_UUID,
            userId: 'user456',
            helpful: true,
            createdAt: Date.now(),
          },
        })
      );

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: null,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('rate'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(true),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockGuildConfigService.get).not.toHaveBeenCalled();
      expect(mockInteraction.deferReply).toHaveBeenCalledWith({});
    });
  });

  describe('error handling', () => {
    it('should handle service errors with ephemeral response', async () => {
      mockGuildConfigService.get.mockResolvedValue(true);
      mockRateNoteService.execute.mockResolvedValue(
        createErrorResult(ErrorCode.API_ERROR, 'Failed to rate note')
      );

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: 'guild789',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('rate'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(true),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.any(String),
        })
      );
    });

    it('should handle service errors with non-ephemeral response', async () => {
      mockGuildConfigService.get.mockResolvedValue(false);
      mockRateNoteService.execute.mockResolvedValue(
        createErrorResult(ErrorCode.API_ERROR, 'Failed to rate note')
      );

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: 'guild789',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('rate'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(true),
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
      mockRateNoteService.execute.mockRejectedValue(new Error('Unexpected error'));

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: 'guild789',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('rate'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(true),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockRejectedValue(new Error('Edit failed')),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalled();
    });

    it('should handle config fetch errors gracefully', async () => {
      mockGuildConfigService.get.mockRejectedValue(new Error('Config error'));
      mockRateNoteService.execute.mockRejectedValue(new Error('Rate error'));

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: 'guild789',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('rate'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(true),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.warn).toHaveBeenCalledWith(
        expect.stringContaining('Failed to fetch ephemeral config'),
        expect.any(Object)
      );
    });
  });

  describe('logging', () => {
    it('should log command execution', async () => {
      mockRateNoteService.execute.mockResolvedValue(
        createSuccessResult({
          rating: {
            noteId: TEST_NOTE_UUID,
            userId: 'user456',
            helpful: true,
            createdAt: Date.now(),
          },
        })
      );

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: 'guild789',
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('rate'),
          getString: jest.fn<() => string>().mockReturnValue(TEST_NOTE_UUID),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(true),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Executing rate-note command',
        expect.objectContaining({
          command: 'note rate',
          user_id: 'user456',
          community_server_id: 'guild789',
          note_id: TEST_NOTE_UUID,
          helpful: true,
        })
      );

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Rate-note completed successfully',
        expect.any(Object)
      );
    });
  });
});
