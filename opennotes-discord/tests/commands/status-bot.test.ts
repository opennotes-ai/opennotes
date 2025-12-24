import { jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';
import {
  createMockStatusService,
  createSuccessResult,
  createErrorResult,
} from '../utils/service-mocks.js';
import { ErrorCode } from '../../src/services/types.js';
import { loggerFactory, cacheFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();
const mockStatusService = createMockStatusService();
const mockScoringService = {
  getNoteScore: jest.fn<(...args: any[]) => Promise<any>>(),
  getTopNotes: jest.fn<(...args: any[]) => Promise<any>>(),
  getScoringStatus: jest.fn<(...args: any[]) => Promise<any>>(),
};

const createMockContainer = () => {
  const containerJson = { type: 17, accent_color: 0x57f287, components: [] };
  return {
    toJSON: jest.fn().mockReturnValue(containerJson),
    addSeparatorComponents: jest.fn().mockReturnThis(),
    addTextDisplayComponents: jest.fn().mockReturnThis(),
  };
};

const createMockTextDisplay = () => ({
  data: { content: 'Test content' },
});

const createMockSeparator = () => ({
  toJSON: jest.fn().mockReturnValue({ type: 14 }),
});

const mockDiscordFormatter = {
  formatStatusSuccessV2: jest.fn().mockImplementation(() => {
    const container = createMockContainer();
    return {
      container,
      components: [container.toJSON()],
      flags: MessageFlags.IsComponentsV2 | MessageFlags.Ephemeral,
    };
  }),
  formatScoringStatusV2: jest.fn().mockImplementation(() => ({
    textDisplay: createMockTextDisplay(),
    separator: createMockSeparator(),
  })),
  formatError: jest.fn<(...args: any[]) => any>().mockReturnValue({ content: 'Error occurred' }),
  formatErrorV2: jest.fn().mockImplementation(() => {
    const container = createMockContainer();
    return {
      container,
      components: [container.toJSON()],
      flags: MessageFlags.IsComponentsV2 | MessageFlags.Ephemeral,
    };
  }),
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

const mockServiceProvider = {
  getStatusService: jest.fn(() => mockStatusService),
  getScoringService: jest.fn(() => mockScoringService),
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

const mockV2MessageFlags = (options?: { ephemeral?: boolean }): number => {
  let flags = MessageFlags.IsComponentsV2;
  if (options?.ephemeral) {
    flags = flags | MessageFlags.Ephemeral;
  }
  return flags;
};

jest.unstable_mockModule('../../src/utils/v2-components.js', () => ({
  v2MessageFlags: mockV2MessageFlags,
}));

const { execute } = await import('../../src/commands/status-bot.js');

describe('status-bot command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockServiceProvider.getStatusService.mockReturnValue(mockStatusService);
    mockServiceProvider.getScoringService.mockReturnValue(mockScoringService);
    mockDiscordFormatter.formatStatusSuccessV2.mockImplementation(() => {
      const container = createMockContainer();
      return {
        container,
        components: [container.toJSON()],
        flags: MessageFlags.IsComponentsV2 | MessageFlags.Ephemeral,
      };
    });
    mockDiscordFormatter.formatScoringStatusV2.mockImplementation(() => ({
      textDisplay: createMockTextDisplay(),
      separator: createMockSeparator(),
    }));
    mockDiscordFormatter.formatError.mockReturnValue({ content: 'Error occurred' });
    mockDiscordFormatter.formatErrorV2.mockImplementation(() => {
      const container = createMockContainer();
      return {
        container,
        components: [container.toJSON()],
        flags: MessageFlags.IsComponentsV2 | MessageFlags.Ephemeral,
      };
    });
  });

  describe('successful execution with v2 components', () => {
    it('should display bot and server status using v2 components', async () => {
      mockStatusService.execute.mockResolvedValue(
        createSuccessResult({
          bot: { uptime: 3600, cacheSize: 10, guilds: 5 },
          server: { status: 'healthy', version: '1.0.0', latency: 50 },
        })
      );

      mockScoringService.getScoringStatus.mockResolvedValue(
        createSuccessResult({
          status: 'healthy',
          totalNotes: 1000,
          avgScore: 0.75,
        })
      );

      const mockClient = {
        guilds: {
          cache: {
            size: 5,
          },
        },
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        client: mockClient,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockStatusService.execute).toHaveBeenCalledWith(5);
      expect(mockScoringService.getScoringStatus).toHaveBeenCalled();
      expect(mockDiscordFormatter.formatStatusSuccessV2).toHaveBeenCalled();
      expect(mockInteraction.deferReply).toHaveBeenCalledWith({
        flags: MessageFlags.IsComponentsV2 | MessageFlags.Ephemeral,
      });
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          components: expect.any(Array),
          flags: expect.any(Number),
        })
      );
    });

    it('should include IsComponentsV2 flag in response', async () => {
      mockStatusService.execute.mockResolvedValue(
        createSuccessResult({
          bot: { uptime: 3600, cacheSize: 10, guilds: 5 },
          server: { status: 'healthy', version: '1.0.0', latency: 50 },
        })
      );

      mockScoringService.getScoringStatus.mockResolvedValue(
        createSuccessResult({ status: 'healthy' })
      );

      const mockClient = {
        guilds: {
          cache: {
            size: 5,
          },
        },
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        client: mockClient,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      expect(editReplyCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should add scoring status when available', async () => {
      mockStatusService.execute.mockResolvedValue(
        createSuccessResult({
          bot: { uptime: 3600, cacheSize: 10, guilds: 5 },
          server: { status: 'healthy', version: '1.0.0', latency: 50 },
        })
      );

      mockScoringService.getScoringStatus.mockResolvedValue(
        createSuccessResult({
          status: 'healthy',
          totalNotes: 1000,
          avgScore: 0.75,
          active_tier: { level: 1, name: 'Bootstrap' },
          current_note_count: 100,
          data_confidence: 'standard',
        })
      );

      const mockClient = {
        guilds: {
          cache: {
            size: 5,
          },
        },
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        client: mockClient,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockDiscordFormatter.formatScoringStatusV2).toHaveBeenCalled();
    });

    it('should work without scoring status', async () => {
      mockStatusService.execute.mockResolvedValue(
        createSuccessResult({
          bot: { uptime: 3600, cacheSize: 10, guilds: 5 },
          server: { status: 'healthy', version: '1.0.0', latency: 50 },
        })
      );

      mockScoringService.getScoringStatus.mockResolvedValue(
        createErrorResult(ErrorCode.API_ERROR, 'Scoring unavailable')
      );

      const mockClient = {
        guilds: {
          cache: {
            size: 5,
          },
        },
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        client: mockClient,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockDiscordFormatter.formatScoringStatusV2).not.toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          components: expect.any(Array),
        })
      );
    });
  });

  describe('error handling', () => {
    it('should handle service errors with v2 components', async () => {
      mockStatusService.execute.mockResolvedValue(
        createErrorResult(ErrorCode.API_ERROR, 'Server unavailable')
      );

      const mockClient = {
        guilds: {
          cache: {
            size: 5,
          },
        },
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        client: mockClient,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockDiscordFormatter.formatErrorV2).toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          components: expect.any(Array),
          flags: expect.any(Number),
        })
      );
      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      expect(editReplyCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should handle unexpected errors', async () => {
      mockStatusService.execute.mockRejectedValue(new Error('Unexpected error'));

      const mockClient = {
        guilds: {
          cache: {
            size: 5,
          },
        },
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        client: mockClient,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Failed to retrieve bot status'),
        })
      );
    });
  });

  describe('ephemeral response with v2 flags', () => {
    it('should use v2 ephemeral flags for deferReply', async () => {
      mockStatusService.execute.mockResolvedValue(
        createSuccessResult({
          bot: { uptime: 3600, cacheSize: 10, guilds: 5 },
          server: { status: 'healthy', version: '1.0.0', latency: 50 },
        })
      );

      mockScoringService.getScoringStatus.mockResolvedValue(
        createSuccessResult({ status: 'healthy' })
      );

      const mockClient = {
        guilds: {
          cache: {
            size: 5,
          },
        },
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        client: mockClient,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const deferReplyCall = mockInteraction.deferReply.mock.calls[0][0];
      expect(deferReplyCall.flags & MessageFlags.Ephemeral).toBeTruthy();
      expect(deferReplyCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });
  });

  describe('logging', () => {
    it('should log command execution start', async () => {
      mockStatusService.execute.mockResolvedValue(
        createSuccessResult({
          bot: { uptime: 3600, cacheSize: 10, guilds: 5 },
          server: { status: 'healthy', version: '1.0.0', latency: 50 },
        })
      );

      mockScoringService.getScoringStatus.mockResolvedValue(
        createSuccessResult({ status: 'healthy' })
      );

      const mockClient = {
        guilds: {
          cache: {
            size: 5,
          },
        },
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        client: mockClient,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Executing status command',
        expect.objectContaining({
          command: 'status-bot',
          user_id: 'user123',
        })
      );
    });

    it('should log command completion', async () => {
      mockStatusService.execute.mockResolvedValue(
        createSuccessResult({
          bot: { uptime: 3600, cacheSize: 10, guilds: 5 },
          server: { status: 'healthy', version: '1.0.0', latency: 50 },
        })
      );

      mockScoringService.getScoringStatus.mockResolvedValue(
        createSuccessResult({ status: 'healthy' })
      );

      const mockClient = {
        guilds: {
          cache: {
            size: 5,
          },
        },
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        client: mockClient,
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Status command completed successfully',
        expect.objectContaining({
          command: 'status-bot',
          guild_count: 5,
        })
      );
    });
  });
});
