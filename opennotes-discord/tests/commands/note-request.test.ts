import { jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';
import { ConfigKey } from '../../src/lib/config-schema.js';
import {
  createSuccessResult,
  createErrorResult,
} from '../utils/service-mocks.js';
import {
  loggerFactory,
  chatInputCommandInteractionFactory,
} from '../factories/index.js';
import { ErrorCode } from '../../src/services/types.js';

const mockLogger = loggerFactory.build();
const mockRequestNoteService = {
  execute: jest.fn<(...args: any[]) => Promise<any>>(),
};
const mockGuildConfigService = {
  get: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(false),
};

const mockDiscordFormatter = {
  formatRequestNoteSuccessV2: jest.fn().mockReturnValue({ embeds: [] }),
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
  getRequestNoteService: jest.fn(() => mockRequestNoteService),
  getGuildConfigService: jest.fn(() => mockGuildConfigService),
  getStatusService: jest.fn<() => any>(),
  getWriteNoteService: jest.fn<() => any>(),
  getViewNotesService: jest.fn<() => any>(),
  getRateNoteService: jest.fn<() => any>(),
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

describe('note-request command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockServiceProvider.getRequestNoteService.mockReturnValue(mockRequestNoteService);
    mockServiceProvider.getGuildConfigService.mockReturnValue(mockGuildConfigService);
    mockGuildConfigService.get.mockResolvedValue(false);
    mockDiscordFormatter.formatRequestNoteSuccessV2.mockReturnValue({ embeds: [] });
    mockDiscordFormatter.formatErrorV2.mockReturnValue({ content: 'Error occurred' });
  });

  describe('successful execution', () => {
    it('should create note request without reason', async () => {
      mockRequestNoteService.execute.mockResolvedValue(
        createSuccessResult({ requestId: 'req123' })
      );

      const mockChannel = {
        messages: {
          fetch: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
            content: 'Original message content',
          }),
        },
        isTextBased: () => true,
      };

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: 'guild789',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('request'),
          getString: jest.fn((name: string) => {
            if (name === 'message-id') return '12345678901234567';
            if (name === 'reason') return null;
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockRequestNoteService.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          messageId: '12345678901234567',
          userId: 'user456',
          reason: undefined,
          username: 'testuser',
          displayName: 'Test User',
          avatarUrl: 'https://example.com/avatar.png',
        })
      );
      expect(mockInteraction.editReply).toHaveBeenCalled();
    });

    it('should create note request with reason', async () => {
      mockRequestNoteService.execute.mockResolvedValue(
        createSuccessResult({ requestId: 'req123' })
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
        channel: null,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('request'),
          getString: jest.fn((name: string) => {
            if (name === 'message-id') return '12345678901234567';
            if (name === 'reason') return 'This needs context';
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockRequestNoteService.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          messageId: '12345678901234567',
          userId: 'user456',
          reason: 'This needs context',
          username: 'testuser',
          displayName: 'Test User',
          avatarUrl: 'https://example.com/avatar.png',
        })
      );
    });
  });

  describe('ephemeral configuration', () => {
    it('should respect ephemeral config when true', async () => {
      mockGuildConfigService.get.mockResolvedValue(true);
      mockRequestNoteService.execute.mockResolvedValue(
        createSuccessResult({ requestId: 'req123' })
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
        channel: null,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('request'),
          getString: jest.fn((name: string) => {
            if (name === 'message-id') return '12345678901234567';
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockGuildConfigService.get).toHaveBeenCalledWith('guild789', ConfigKey.REQUEST_NOTE_EPHEMERAL);
      expect(mockInteraction.deferReply).toHaveBeenCalledWith({ flags: MessageFlags.Ephemeral });
    });

    it('should work without guildId', async () => {
      mockRequestNoteService.execute.mockResolvedValue(
        createSuccessResult({ requestId: 'req123' })
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
        channel: null,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('request'),
          getString: jest.fn((name: string) => {
            if (name === 'message-id') return '12345678901234567';
            return null;
          }),
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
      mockRequestNoteService.execute.mockResolvedValue(
        createErrorResult(ErrorCode.API_ERROR, 'Failed to create request')
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
        channel: null,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('request'),
          getString: jest.fn((name: string) => {
            if (name === 'message-id') return '12345678901234567';
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalled();
    });

    it('should handle service errors with non-ephemeral response', async () => {
      mockGuildConfigService.get.mockResolvedValue(false);
      mockRequestNoteService.execute.mockResolvedValue(
        createErrorResult(ErrorCode.API_ERROR, 'Failed to create request')
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
        channel: null,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('request'),
          getString: jest.fn((name: string) => {
            if (name === 'message-id') return '12345678901234567';
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      // Note: The implementation does NOT add ephemeral flags for non-ephemeral error responses
      // in the request subcommand (unlike rate subcommand)
      expect(mockInteraction.followUp).toHaveBeenCalled();
      expect(mockInteraction.deleteReply).toHaveBeenCalled();
    });

    it('should handle unexpected errors', async () => {
      mockRequestNoteService.execute.mockRejectedValue(new Error('Unexpected error'));

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: 'guild789',
        channel: null,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('request'),
          getString: jest.fn((name: string) => {
            if (name === 'message-id') return '12345678901234567';
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}).mockRejectedValue(new Error('Edit failed')),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('message content fetching', () => {
    it('should fetch message content when available', async () => {
      mockRequestNoteService.execute.mockResolvedValue(
        createSuccessResult({ requestId: 'req123' })
      );

      const mockChannel = {
        messages: {
          fetch: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
            content: 'Original message',
          }),
        },
        isTextBased: () => true,
      };

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: 'guild789',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('request'),
          getString: jest.fn((name: string) => {
            if (name === 'message-id') return '12345678901234567';
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockChannel.messages.fetch).toHaveBeenCalledWith('12345678901234567');
      expect(mockRequestNoteService.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          originalMessageContent: 'Original message',
          username: 'testuser',
          displayName: 'Test User',
          avatarUrl: 'https://example.com/avatar.png',
        })
      );
    });

    it('should handle message fetch errors gracefully', async () => {
      mockRequestNoteService.execute.mockResolvedValue(
        createSuccessResult({ requestId: 'req123' })
      );

      const mockChannel = {
        messages: {
          fetch: jest.fn<(...args: any[]) => Promise<any>>().mockRejectedValue(new Error('Message not found')),
        },
        isTextBased: () => true,
      };

      const mockInteraction = {
        user: {
          id: 'user456',
          username: 'testuser',
          displayName: 'Test User',
          globalName: 'Test User',
          displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
        },
        guildId: 'guild789',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('request'),
          getString: jest.fn((name: string) => {
            if (name === 'message-id') return '12345678901234567';
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.warn).toHaveBeenCalledWith(
        expect.stringContaining('Failed to fetch original message'),
        expect.any(Object)
      );
      expect(mockRequestNoteService.execute).toHaveBeenCalled();
    });
  });
});
