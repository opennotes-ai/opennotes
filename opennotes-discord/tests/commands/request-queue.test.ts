import { jest } from '@jest/globals';
import { MessageFlags, TextChannel } from 'discord.js';
import { createMockLogger, createSuccessResult, createErrorResult } from '../utils/service-mocks.js';
import { ErrorCode } from '../../src/services/types.js';

const mockLogger = createMockLogger();
const mockListRequestsService = {
  execute: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockDiscordFormatter = {
  formatListRequestsSuccess: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({ embeds: [] }),
  formatError: jest.fn<(...args: any[]) => any>().mockReturnValue({ content: 'Error occurred' }),
};

const mockApiClient = {
  healthCheck: jest.fn<() => Promise<any>>(),
  createNote: jest.fn<(...args: any[]) => Promise<any>>(),
  getNotes: jest.fn<(...args: any[]) => Promise<any>>(),
  rateNote: jest.fn<(...args: any[]) => Promise<any>>(),
  scoreNotes: jest.fn<(...args: any[]) => Promise<any>>(),
  createNoteRequest: jest.fn<(...args: any[]) => Promise<any>>(),
  getCommunityServerByPlatformId: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockCache = {
  get: jest.fn<(key: string) => unknown>(),
  set: jest.fn<(key: string, value: unknown, ttl?: number) => void>(),
  delete: jest.fn<(key: string) => void>(),
  start: jest.fn<() => void>(),
  stop: jest.fn<() => void>(),
  getMetrics: jest.fn(() => ({ size: 0 })),
};

const mockThread = {
  send: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({
    createMessageComponentCollector: jest.fn().mockReturnValue({
      on: jest.fn(),
    }),
  }),
  toString: () => '<#thread123>',
};

const mockQueueManager = {
  getOrCreateOpenNotesThread: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(mockThread),
};

const mockServiceProvider = {
  getListRequestsService: jest.fn(() => mockListRequestsService),
  getStatusService: jest.fn<() => any>(),
  getWriteNoteService: jest.fn<() => any>(),
  getViewNotesService: jest.fn<() => any>(),
  getRateNoteService: jest.fn<() => any>(),
  getRequestNoteService: jest.fn<() => any>(),
  getGuildConfigService: jest.fn<(...args: any[]) => any>(),
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

jest.unstable_mockModule('../../src/queue.js', () => ({
  getQueueManager: jest.fn(() => mockQueueManager),
  configCache: mockCache,
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

const { execute } = await import('../../src/commands/list.js');

describe('request-queue command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockServiceProvider.getListRequestsService.mockReturnValue(mockListRequestsService);
    mockDiscordFormatter.formatListRequestsSuccess.mockResolvedValue({ embeds: [], components: [] });
    mockDiscordFormatter.formatError.mockReturnValue({ content: 'Error occurred' });
    mockQueueManager.getOrCreateOpenNotesThread.mockResolvedValue(mockThread);
    mockThread.send.mockResolvedValue({
      createMessageComponentCollector: jest.fn().mockReturnValue({
        on: jest.fn(),
      }),
    });
    mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
      id: 'guild456',
      platform: 'discord',
      platform_id: 'guild456',
      name: 'Test Guild',
      is_active: true,
    });
  });

  describe('successful execution', () => {
    it('should list all requests with default parameters', async () => {
      mockListRequestsService.execute.mockResolvedValue(
        createSuccessResult({
          requests: [
            { id: 'req1', status: 'PENDING', messageId: 'msg1' },
            { id: 'req2', status: 'COMPLETED', messageId: 'msg2' },
          ],
          total: 2,
          page: 1,
          size: 10,
        })
      );

      const mockChannel = Object.create(TextChannel.prototype);
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(false),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockListRequestsService.execute).toHaveBeenCalledWith({
        userId: 'user123',
        page: 1,
        size: 5,
        status: undefined,
        myRequestsOnly: false,
        communityServerId: 'guild456',
      });
      expect(mockInteraction.deferReply).toHaveBeenCalledWith({ flags: MessageFlags.Ephemeral });
      expect(mockInteraction.editReply).toHaveBeenCalled();
    });

    it('should filter by status', async () => {
      mockListRequestsService.execute.mockResolvedValue(
        createSuccessResult({
          requests: [{ id: 'req1', status: 'PENDING', messageId: 'msg1' }],
          total: 1,
          page: 1,
          size: 10,
        })
      );

      const mockChannel = Object.create(TextChannel.prototype);
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
          getString: jest.fn<() => string>().mockReturnValue('PENDING'),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(false),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockListRequestsService.execute).toHaveBeenCalledWith({
        userId: 'user123',
        page: 1,
        size: 5,
        status: 'PENDING',
        myRequestsOnly: false,
        communityServerId: 'guild456',
      });
    });

    it('should filter by my-requests-only', async () => {
      mockListRequestsService.execute.mockResolvedValue(
        createSuccessResult({
          requests: [],
          total: 0,
          page: 1,
          size: 10,
        })
      );

      const mockChannel = Object.create(TextChannel.prototype);
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(true),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockListRequestsService.execute).toHaveBeenCalledWith({
        userId: 'user123',
        page: 1,
        size: 5,
        status: undefined,
        myRequestsOnly: true,
        communityServerId: 'guild456',
      });
    });

    it('should handle custom pagination', async () => {
      mockListRequestsService.execute.mockResolvedValue(
        createSuccessResult({
          requests: [],
          total: 0,
          page: 2,
          size: 25,
        })
      );

      const mockChannel = Object.create(TextChannel.prototype);
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(false),
          getInteger: jest.fn((name: string) => {
            if (name === 'page') return 2;
            if (name === 'page-size') return 25;
            return null;
          }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockListRequestsService.execute).toHaveBeenCalledWith({
        userId: 'user123',
        page: 2,
        size: 25,
        status: undefined,
        myRequestsOnly: false,
        communityServerId: 'guild456',
      });
    });

  });

  describe('error handling', () => {
    it('should handle service errors', async () => {
      mockListRequestsService.execute.mockResolvedValue(
        createErrorResult(ErrorCode.API_ERROR, 'Failed to fetch requests')
      );

      const mockChannel = Object.create(TextChannel.prototype);
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(false),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.any(String),
        })
      );
    });

    it('should handle missing data', async () => {
      mockListRequestsService.execute.mockResolvedValue(
        createSuccessResult(null as any)
      );

      const mockChannel = Object.create(TextChannel.prototype);
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(false),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: 'No data returned from the service.',
      });
    });

    it('should handle unexpected errors', async () => {
      mockListRequestsService.execute.mockRejectedValue(new Error('Unexpected error'));

      const mockChannel = Object.create(TextChannel.prototype);
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(false),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Failed to retrieve request list'),
        })
      );
    });
  });

  describe('logging', () => {
    it('should log command execution', async () => {
      mockListRequestsService.execute.mockResolvedValue(
        createSuccessResult({
          requests: [],
          total: 0,
          page: 1,
          size: 10,
        })
      );

      const mockChannel = Object.create(TextChannel.prototype);
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        channel: mockChannel,
        options: {
          getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
          getString: jest.fn<(name: string) => string | null>().mockReturnValue(null),
          getBoolean: jest.fn<() => boolean>().mockReturnValue(false),
          getInteger: jest.fn<() => number | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Executing list requests subcommand',
        expect.objectContaining({
          command: 'list requests',
          user_id: 'user123',
        })
      );
    });
  });
});
