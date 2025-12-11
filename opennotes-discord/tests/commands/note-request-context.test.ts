import { jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';
import { ConfigKey } from '../../src/lib/config-schema.js';
import { createMockLogger } from '../utils/service-mocks.js';

const mockLogger = createMockLogger();
const mockGuildConfigService = {
  get: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(false),
};

const mockCreateNoteRequest = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
  success: true,
  response: { content: 'Request created' },
});

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
  getGuildConfigService: jest.fn(() => mockGuildConfigService),
  getRequestNoteService: jest.fn<() => any>(),
  getStatusService: jest.fn<() => any>(),
  getWriteNoteService: jest.fn<() => any>(),
  getViewNotesService: jest.fn<() => any>(),
  getRateNoteService: jest.fn<() => any>(),
  getScoringService: jest.fn<() => any>(),
};

jest.unstable_mockModule('../../src/logger', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/cache', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../../src/services/index', () => ({
  serviceProvider: mockServiceProvider,
}));

jest.unstable_mockModule('../../src/commands/note', () => ({
  createNoteRequest: mockCreateNoteRequest,
}));

jest.unstable_mockModule('../../src/lib/errors', () => ({
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

const { execute } = await import('../../src/commands/note-request-context');

describe('note-request-context command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockServiceProvider.getGuildConfigService.mockReturnValue(mockGuildConfigService);
    mockGuildConfigService.get.mockResolvedValue(false);
    mockCreateNoteRequest.mockResolvedValue({
      success: true,
      response: { content: 'Request created' },
    });
  });

  describe('successful execution', () => {
    it('should create note request from context menu', async () => {
      const mockTargetMessage = {
        id: 'msg123',
        content: 'Original message',
        embeds: [],
        attachments: new Map(),
      };

      const mockInteraction = {
        user: { id: 'user456' },
        guildId: 'guild789',
        targetMessage: mockTargetMessage,
        channel: null,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockCreateNoteRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          messageId: 'msg123',
          message: mockTargetMessage,
          userId: 'user456',
          reason: undefined,
        })
      );
      expect(mockInteraction.editReply).toHaveBeenCalledWith({ content: 'Request created' });
    });

    it('should respect ephemeral config', async () => {
      mockGuildConfigService.get.mockResolvedValue(true);

      const mockTargetMessage = {
        id: 'msg123',
        content: 'Original message',
        embeds: [],
        attachments: new Map(),
      };

      const mockInteraction = {
        user: { id: 'user456' },
        guildId: 'guild789',
        targetMessage: mockTargetMessage,
        channel: null,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockGuildConfigService.get).toHaveBeenCalledWith('guild789', ConfigKey.REQUEST_NOTE_EPHEMERAL);
      const deferReplyCall = mockInteraction.deferReply.mock.calls[0][0];
      expect(deferReplyCall?.flags & MessageFlags.IsComponentsV2).toBeTruthy();
      expect(deferReplyCall?.flags & MessageFlags.Ephemeral).toBeTruthy();
    });
  });

  describe('error handling', () => {
    it('should handle errors from createNoteRequest', async () => {
      mockCreateNoteRequest.mockResolvedValue({
        success: false,
        response: { content: 'Error creating request' },
      });

      const mockTargetMessage = {
        id: 'msg123',
        content: 'Original message',
        embeds: [],
        attachments: new Map(),
      };

      const mockInteraction = {
        user: { id: 'user456' },
        guildId: 'guild789',
        targetMessage: mockTargetMessage,
        channel: null,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      // Note: The implementation does NOT add ephemeral flags for non-ephemeral error responses
      // when ephemeral config is false (the default)
      expect(mockInteraction.followUp).toHaveBeenCalledWith(
        expect.objectContaining({
          content: 'Error creating request',
        })
      );
      expect(mockInteraction.deleteReply).toHaveBeenCalled();
    });

    it('should handle unexpected errors', async () => {
      mockCreateNoteRequest.mockRejectedValue(new Error('Unexpected error'));

      const mockTargetMessage = {
        id: 'msg123',
        content: 'Original message',
        embeds: [],
        attachments: new Map(),
      };

      const mockInteraction = {
        user: { id: 'user456' },
        guildId: 'guild789',
        targetMessage: mockTargetMessage,
        channel: null,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}).mockRejectedValue(new Error('Edit failed')),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('logging', () => {
    it('should log message metadata', async () => {
      const mockTargetMessage = {
        id: 'msg123',
        content: 'Original message',
        embeds: [{ type: 'rich' }],
        attachments: new Map([['att1', {}]]),
      };

      const mockInteraction = {
        user: { id: 'user456' },
        guildId: 'guild789',
        targetMessage: mockTargetMessage,
        channel: null,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Executing request-note-context command',
        expect.objectContaining({
          has_content: true,
          has_embeds: true,
          has_attachments: true,
        })
      );
    });
  });
});
