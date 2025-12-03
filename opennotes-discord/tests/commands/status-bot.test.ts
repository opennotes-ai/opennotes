import { jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';
import {
  createMockLogger,
  createMockStatusService,
  createSuccessResult,
  createErrorResult,
} from '../utils/service-mocks.js';
import { ErrorCode } from '../../src/services/types.js';

const mockLogger = createMockLogger();
const mockStatusService = createMockStatusService();
const mockScoringService = {
  getNoteScore: jest.fn<(...args: any[]) => Promise<any>>(),
  getTopNotes: jest.fn<(...args: any[]) => Promise<any>>(),
  getScoringStatus: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockDiscordFormatter = {
  formatStatusSuccess: jest.fn().mockReturnValue({
    embeds: [{
      addFields: jest.fn().mockReturnThis(),
      fields: []
    }]
  }),
  formatScoringStatus: jest.fn().mockReturnValue('Scoring status text'),
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

const { execute } = await import('../../src/commands/status-bot.js');

describe('status-bot command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockServiceProvider.getStatusService.mockReturnValue(mockStatusService);
    mockServiceProvider.getScoringService.mockReturnValue(mockScoringService);
    mockDiscordFormatter.formatStatusSuccess.mockReturnValue({
      embeds: [{
        addFields: jest.fn().mockReturnThis(),
        fields: []
      }]
    });
    mockDiscordFormatter.formatScoringStatus.mockReturnValue('Scoring status text');
    mockDiscordFormatter.formatError.mockReturnValue({ content: 'Error occurred' });
  });

  describe('successful execution', () => {
    it('should display bot and server status', async () => {
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
      expect(mockInteraction.deferReply).toHaveBeenCalledWith({ flags: MessageFlags.Ephemeral });
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          embeds: expect.arrayContaining([
            expect.objectContaining({
              fields: expect.any(Array),
            }),
          ]),
        })
      );
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

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          embeds: expect.any(Array),
        })
      );
    });
  });

  describe('error handling', () => {
    it('should handle service errors', async () => {
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

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.any(String),
        })
      );
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

  describe('ephemeral response', () => {
    it('should always use ephemeral flags', async () => {
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

      expect(mockInteraction.deferReply).toHaveBeenCalledWith({ flags: MessageFlags.Ephemeral });
    });
  });
});
