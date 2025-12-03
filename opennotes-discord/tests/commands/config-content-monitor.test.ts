import { jest } from '@jest/globals';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
};

const mockApiClient = {
  getMonitoredChannel: jest.fn<(...args: any[]) => Promise<any>>(),
  updateMonitoredChannel: jest.fn<(...args: any[]) => Promise<any>>(),
  createMonitoredChannel: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockGuildSetupService = {
  autoRegisterChannels: jest.fn<(...args: any[]) => Promise<void>>(),
};

const mockConfig = {
  similaritySearchDefaultThreshold: 0.8,
};

const mockApiError = class ApiError extends Error {
  statusCode: number;
  endpoint: string;
  responseBody?: any;
  requestBody?: any;
  metadata?: Record<string, any>;

  constructor(
    message: string,
    endpoint: string,
    statusCode: number,
    responseBody?: any,
    requestBody?: any,
    metadata?: Record<string, any>
  ) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
    this.endpoint = endpoint;
    this.responseBody = responseBody;
    this.requestBody = requestBody;
    this.metadata = metadata;
  }
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/services/GuildSetupService.js', () => ({
  GuildSetupService: jest.fn(() => mockGuildSetupService),
}));

jest.unstable_mockModule('../../src/config.js', () => ({
  config: mockConfig,
}));

const mockFormatErrorForUser = jest.fn<(errorId: string, msg: string) => string>();
mockFormatErrorForUser.mockImplementation((id, msg) => `Error: ${msg}`);

const mockExtractErrorDetails = jest.fn<(error: any) => any>();
mockExtractErrorDetails.mockImplementation((error: any) => {
  if (error instanceof mockApiError) {
    return {
      message: error.message || 'API error occurred',
      type: 'ApiError',
      stack: error.stack || '',
    };
  }
  if (error instanceof Error) {
    return {
      message: error.message || 'An error occurred',
      type: error.constructor.name,
      stack: error.stack || '',
    };
  }
  return {
    message: String(error) || 'Unknown error',
    type: 'Unknown',
    stack: '',
  };
});

jest.unstable_mockModule('../../src/lib/errors.js', () => ({
  generateErrorId: jest.fn<() => string>().mockReturnValue('test-error-id'),
  formatErrorForUser: mockFormatErrorForUser,
  extractErrorDetails: mockExtractErrorDetails,
  ApiError: mockApiError,
}));

const { execute } = await import('../../src/commands/config.js');

describe('config-content-monitor command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('enable subcommand', () => {
    it('should enable monitoring for existing channel', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('content-monitor'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable'),
          getChannel: jest.fn<(name: string, required: boolean) => any>().mockReturnValue({ id: 'channel789' }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      mockApiClient.getMonitoredChannel.mockResolvedValue({
        channel_id: 'channel789',
        enabled: false,
      });
      mockApiClient.updateMonitoredChannel.mockResolvedValue({
        channel_id: 'channel789',
        enabled: true,
      });

      await execute(mockInteraction as any);

      expect(mockApiClient.getMonitoredChannel).toHaveBeenCalledWith('channel789');
      expect(mockApiClient.updateMonitoredChannel).toHaveBeenCalledWith('channel789', {
        enabled: true,
        updated_by: 'user123',
      });
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Content monitoring enabled'),
        })
      );
    });

    it('should create new monitored channel if not found', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('content-monitor'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable'),
          getChannel: jest.fn<(name: string, required: boolean) => any>().mockReturnValue({ id: 'channel789' }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      mockApiClient.getMonitoredChannel.mockRejectedValue(
        new mockApiError('Not found', '/api/v1/monitored-channels/channel789', 404)
      );
      mockApiClient.createMonitoredChannel.mockResolvedValue({
        channel_id: 'channel789',
        enabled: true,
      });

      await execute(mockInteraction as any);

      expect(mockApiClient.getMonitoredChannel).toHaveBeenCalledWith('channel789');
      expect(mockApiClient.createMonitoredChannel).toHaveBeenCalledWith({
        community_server_id: 'guild456',
        channel_id: 'channel789',
        enabled: true,
        similarity_threshold: 0.8,
        dataset_tags: ['snopes'],
        updated_by: 'user123',
      });
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Content monitoring enabled'),
        })
      );
    });

    it('should handle already monitored channel (conflict)', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('content-monitor'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable'),
          getChannel: jest.fn<(name: string, required: boolean) => any>().mockReturnValue({ id: 'channel789' }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      mockApiClient.getMonitoredChannel.mockRejectedValue(
        new mockApiError('Not found', '/api/v1/monitored-channels/channel789', 404)
      );
      mockApiClient.createMonitoredChannel.mockResolvedValue(null);

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('already enabled'),
        })
      );
    });
  });

  describe('disable subcommand', () => {
    it('should disable monitoring for channel', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('content-monitor'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('disable'),
          getChannel: jest.fn<(name: string, required: boolean) => any>().mockReturnValue({ id: 'channel789' }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      mockApiClient.getMonitoredChannel.mockResolvedValue({
        channel_id: 'channel789',
        enabled: true,
      });
      mockApiClient.updateMonitoredChannel.mockResolvedValue({
        channel_id: 'channel789',
        enabled: false,
      });

      await execute(mockInteraction as any);

      expect(mockApiClient.getMonitoredChannel).toHaveBeenCalledWith('channel789');
      expect(mockApiClient.updateMonitoredChannel).toHaveBeenCalledWith('channel789', {
        enabled: false,
        updated_by: 'user123',
      });
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Content monitoring disabled'),
        })
      );
    });

    it('should handle channel not monitored error', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('content-monitor'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('disable'),
          getChannel: jest.fn<(name: string, required: boolean) => any>().mockReturnValue({ id: 'channel789' }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      mockApiClient.getMonitoredChannel.mockRejectedValue(
        new mockApiError('Not found', '/api/v1/monitored-channels/channel789', 404)
      );

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('not currently monitored'),
        })
      );
    });
  });

  describe('enable-all subcommand', () => {
    it('should enable monitoring for all channels', async () => {
      const mockGuild = {
        id: 'guild456',
        name: 'Test Guild',
      };

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        guild: mockGuild,
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('content-monitor'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable-all'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      mockGuildSetupService.autoRegisterChannels.mockResolvedValue(undefined);

      await execute(mockInteraction as any);

      expect(mockGuildSetupService.autoRegisterChannels).toHaveBeenCalledWith(mockGuild);
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          embeds: expect.arrayContaining([
            expect.objectContaining({
              data: expect.objectContaining({
                title: 'Content Monitoring Setup Complete',
              }),
            }),
          ]),
        })
      );
    });

    it('should handle missing guild', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        guild: null,
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('content-monitor'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable-all'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Unable to access guild information'),
        })
      );
      expect(mockGuildSetupService.autoRegisterChannels).not.toHaveBeenCalled();
    });
  });

  describe('error handling', () => {
    it('should handle errors gracefully', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('content-monitor'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable'),
          getChannel: jest.fn<(name: string, required: boolean) => any>().mockReturnValue({ id: 'channel789' }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
        deferred: true,
      };

      mockApiClient.getMonitoredChannel.mockRejectedValue(new Error('Network error'));

      await execute(mockInteraction as any);

      // Verify error was handled and editReply was called
      expect(mockInteraction.editReply).toHaveBeenCalled();
      expect(mockLogger.error).toHaveBeenCalled();
    });

    it('should handle missing guild ID', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: null,
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('content-monitor'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.deferReply).toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('can only be used in a server'),
        })
      );
    });
  });
});
