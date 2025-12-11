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
  response: {
    components: [{ type: 17 }],
    flags: MessageFlags.IsComponentsV2,
  },
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

describe('note-request-context v2 components', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockServiceProvider.getGuildConfigService.mockReturnValue(mockGuildConfigService);
    mockGuildConfigService.get.mockResolvedValue(false);
    mockCreateNoteRequest.mockResolvedValue({
      success: true,
      response: {
        components: [{ type: 17 }],
        flags: MessageFlags.IsComponentsV2,
      },
    });
  });

  describe('AC #1: Update interaction reply to use IsComponentsV2 flag', () => {
    it('should include IsComponentsV2 flag in deferReply when not ephemeral', async () => {
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

      expect(mockInteraction.deferReply).toHaveBeenCalled();
      const deferReplyCall = mockInteraction.deferReply.mock.calls[0][0];
      expect(deferReplyCall?.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should include IsComponentsV2 flag in deferReply when ephemeral', async () => {
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
      expect(mockInteraction.deferReply).toHaveBeenCalled();
      const deferReplyCall = mockInteraction.deferReply.mock.calls[0][0];
      expect(deferReplyCall?.flags & MessageFlags.IsComponentsV2).toBeTruthy();
      expect(deferReplyCall?.flags & MessageFlags.Ephemeral).toBeTruthy();
    });
  });

  describe('AC #2: Ensure v2 components work correctly with context menu interactions', () => {
    it('should pass v2 response to editReply on success', async () => {
      const v2Response = {
        components: [{ type: 17 }],
        flags: MessageFlags.IsComponentsV2,
      };
      mockCreateNoteRequest.mockResolvedValue({
        success: true,
        response: v2Response,
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

      expect(mockInteraction.editReply).toHaveBeenCalledWith(v2Response);
    });

    it('should correctly extract message data from context menu target', async () => {
      const mockTargetMessage = {
        id: 'msg123',
        content: 'Original message with context',
        embeds: [{ type: 'rich', image: { url: 'https://example.com/image.png' } }],
        attachments: new Map([['att1', { url: 'https://example.com/file.pdf' }]]),
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
          community_server_id: 'guild789',
        })
      );
    });
  });

  describe('AC #3: Test ephemeral v2 component display', () => {
    it('should combine IsComponentsV2 and Ephemeral flags when ephemeral config is true', async () => {
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

      const deferReplyCall = mockInteraction.deferReply.mock.calls[0][0];
      const expectedFlags = MessageFlags.IsComponentsV2 | MessageFlags.Ephemeral;
      expect(deferReplyCall?.flags).toBe(expectedFlags);
    });

    it('should handle ephemeral error responses with v2 components', async () => {
      mockGuildConfigService.get.mockResolvedValue(true);
      mockCreateNoteRequest.mockResolvedValue({
        success: false,
        response: {
          components: [{ type: 17 }],
          flags: MessageFlags.IsComponentsV2 | MessageFlags.Ephemeral,
        },
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

      expect(mockInteraction.editReply).toHaveBeenCalled();
    });
  });

  describe('AC #4: Verify attachment/image handling with v2', () => {
    it('should handle messages with image attachments', async () => {
      const mockAttachment = {
        url: 'https://cdn.discordapp.com/attachments/123/456/image.png',
        contentType: 'image/png',
        width: 800,
        height: 600,
        size: 12345,
        name: 'image.png',
      };

      const mockTargetMessage = {
        id: 'msg123',
        content: 'Check this image',
        embeds: [],
        attachments: new Map([['att1', mockAttachment]]),
      };

      (mockTargetMessage.attachments as any).first = () => mockAttachment;

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
          message: expect.objectContaining({
            attachments: expect.anything(),
          }),
        })
      );
    });

    it('should handle messages with embedded images', async () => {
      const mockEmbed = {
        type: 'rich',
        image: { url: 'https://example.com/embedded-image.png' },
      };

      const mockTargetMessage = {
        id: 'msg123',
        content: 'Check this embedded content',
        embeds: [mockEmbed],
        attachments: new Map(),
      };

      (mockTargetMessage.attachments as any).first = () => undefined;

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
          message: expect.objectContaining({
            embeds: expect.arrayContaining([
              expect.objectContaining({
                image: { url: 'https://example.com/embedded-image.png' },
              }),
            ]),
          }),
        })
      );
    });
  });

  describe('error handling with v2 components', () => {
    it('should handle non-ephemeral error response with followUp and deleteReply', async () => {
      mockGuildConfigService.get.mockResolvedValue(false);
      mockCreateNoteRequest.mockResolvedValue({
        success: false,
        response: {
          components: [{ type: 17 }],
          flags: MessageFlags.IsComponentsV2,
        },
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

      expect(mockInteraction.followUp).toHaveBeenCalled();
      expect(mockInteraction.deleteReply).toHaveBeenCalled();
    });

    it('should handle missing guild ID with plain text error', async () => {
      const mockTargetMessage = {
        id: 'msg123',
        content: 'Original message',
        embeds: [],
        attachments: new Map(),
      };

      const mockInteraction = {
        user: { id: 'user456' },
        guildId: null,
        targetMessage: mockTargetMessage,
        channel: null,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
        deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('This command can only be used in a server'),
        })
      );
    });
  });
});
