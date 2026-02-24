import { jest } from '@jest/globals';
import { ChannelType, Collection } from 'discord.js';
import { ApiError } from '@opennotes/shared-types';

const mockCreateMonitoredChannel = jest.fn<(...args: any[]) => any>();

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
};

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: {
    createMonitoredChannel: mockCreateMonitoredChannel,
  },
}));

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const { GuildSetupService } = await import('../../src/services/GuildSetupService.js');

describe('GuildSetupService', () => {
  let service: InstanceType<typeof GuildSetupService>;
  let mockGuild: any;

  const TEST_GUILD_ID = '123456789';

  beforeEach(() => {
    service = new GuildSetupService();
    jest.clearAllMocks();

    mockGuild = {
      id: TEST_GUILD_ID,
      name: 'Test Guild',
      channels: {
        fetch: jest.fn<(...args: any[]) => Promise<any>>(),
      },
    };
  });

  describe('autoRegisterChannels', () => {
    it('should pass guild snowflake as community_server_id when registering channels', async () => {
      const mockChannels = new Collection();
      mockChannels.set('channel1', {
        id: 'channel1',
        name: 'general',
        type: ChannelType.GuildText,
      } as any);

      (mockGuild.channels.fetch as any).mockResolvedValue(mockChannels);
      mockCreateMonitoredChannel.mockResolvedValue({ id: 'response-id' });

      await service.autoRegisterChannels(mockGuild);

      expect(mockCreateMonitoredChannel).toHaveBeenCalledWith(
        expect.objectContaining({
          community_server_id: TEST_GUILD_ID,
        })
      );
    });

    it('should register all text channels successfully', async () => {
      const mockChannels = new Collection();
      mockChannels.set('channel1', {
        id: 'channel1',
        name: 'general',
        type: ChannelType.GuildText,
      } as any);
      mockChannels.set('channel2', {
        id: 'channel2',
        name: 'announcements',
        type: ChannelType.GuildText,
      } as any);

      (mockGuild.channels.fetch as any).mockResolvedValue(mockChannels);
      mockCreateMonitoredChannel.mockResolvedValue({
        id: 'response-id',
        channel_id: 'channel1',
      });

      await service.autoRegisterChannels(mockGuild);

      expect(mockCreateMonitoredChannel).toHaveBeenCalledTimes(2);
      expect(mockCreateMonitoredChannel).toHaveBeenCalledWith({
        community_server_id: TEST_GUILD_ID,
        channel_id: 'channel1',
        name: 'general',
        enabled: true,
        similarity_threshold: 0.6,
        dataset_tags: [],
        updated_by: null,
      });
    });

    it('should skip non-text channels', async () => {
      const mockChannels = new Collection();
      mockChannels.set('text-channel', {
        id: 'text-channel',
        name: 'general',
        type: ChannelType.GuildText,
      } as any);
      mockChannels.set('voice-channel', {
        id: 'voice-channel',
        name: 'voice',
        type: ChannelType.GuildVoice,
      } as any);
      mockChannels.set('category', {
        id: 'category',
        name: 'category',
        type: ChannelType.GuildCategory,
      } as any);

      (mockGuild.channels.fetch as any).mockResolvedValue(mockChannels);
      mockCreateMonitoredChannel.mockResolvedValue({
        id: 'response-id',
      });

      await service.autoRegisterChannels(mockGuild);

      expect(mockCreateMonitoredChannel).toHaveBeenCalledTimes(1);
      expect(mockCreateMonitoredChannel).toHaveBeenCalledWith(
        expect.objectContaining({
          channel_id: 'text-channel',
        })
      );
    });

    it('should handle already monitored channels gracefully', async () => {
      const mockChannels = new Collection();
      mockChannels.set('channel1', {
        id: 'channel1',
        name: 'general',
        type: ChannelType.GuildText,
      } as any);
      mockChannels.set('channel2', {
        id: 'channel2',
        name: 'announcements',
        type: ChannelType.GuildText,
      } as any);

      (mockGuild.channels.fetch as any).mockResolvedValue(mockChannels);
      mockCreateMonitoredChannel
        .mockResolvedValueOnce(null)
        .mockResolvedValueOnce({ id: 'response-id' });

      await service.autoRegisterChannels(mockGuild);

      expect(mockCreateMonitoredChannel).toHaveBeenCalledTimes(2);
    });

    it('should handle API errors gracefully', async () => {
      const mockChannels = new Collection();
      mockChannels.set('channel1', {
        id: 'channel1',
        name: 'general',
        type: ChannelType.GuildText,
      } as any);
      mockChannels.set('channel2', {
        id: 'channel2',
        name: 'announcements',
        type: ChannelType.GuildText,
      } as any);

      (mockGuild.channels.fetch as any).mockResolvedValue(mockChannels);
      mockCreateMonitoredChannel
        .mockRejectedValueOnce(new Error('API error'))
        .mockResolvedValueOnce({ id: 'response-id' });

      await service.autoRegisterChannels(mockGuild);

      expect(mockCreateMonitoredChannel).toHaveBeenCalledTimes(2);
    });

    it('should NOT include statusCode when a generic Error (not ApiError) is thrown', async () => {
      const mockChannels = new Collection();
      mockChannels.set('channel1', {
        id: 'channel1',
        name: 'general',
        type: ChannelType.GuildText,
      } as any);

      (mockGuild.channels.fetch as any).mockResolvedValue(mockChannels);
      mockCreateMonitoredChannel.mockRejectedValueOnce(new Error('Generic network error'));

      await service.autoRegisterChannels(mockGuild);

      expect(mockLogger.error).toHaveBeenCalledTimes(1);
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to register channel',
        expect.not.objectContaining({ statusCode: expect.anything() })
      );
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to register channel',
        expect.objectContaining({
          channelId: 'channel1',
          channelName: 'general',
          guildId: TEST_GUILD_ID,
          error: 'Generic network error',
        })
      );
    });

    it('should handle 400 Bad Request error and log HTTP status code', async () => {
      const mockChannels = new Collection();
      mockChannels.set('channel1', {
        id: 'channel1',
        name: 'general',
        type: ChannelType.GuildText,
      } as any);

      (mockGuild.channels.fetch as any).mockResolvedValue(mockChannels);

      const apiError = new ApiError(
        'Invalid community server ID',
        '/api/v2/monitored-channels',
        400,
        { detail: 'Community server not found' }
      );
      mockCreateMonitoredChannel.mockRejectedValueOnce(apiError);

      await service.autoRegisterChannels(mockGuild);

      expect(mockCreateMonitoredChannel).toHaveBeenCalledTimes(1);
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to register channel',
        expect.objectContaining({
          channelId: 'channel1',
          channelName: 'general',
          guildId: TEST_GUILD_ID,
          error: 'Invalid community server ID',
          statusCode: 400,
        })
      );
    });

    it('should handle 403 Forbidden error and log HTTP status code', async () => {
      const mockChannels = new Collection();
      mockChannels.set('channel1', {
        id: 'channel1',
        name: 'general',
        type: ChannelType.GuildText,
      } as any);

      (mockGuild.channels.fetch as any).mockResolvedValue(mockChannels);

      const apiError = new ApiError(
        'Access denied',
        '/api/v2/monitored-channels',
        403,
        { detail: 'Insufficient permissions' }
      );
      mockCreateMonitoredChannel.mockRejectedValueOnce(apiError);

      await service.autoRegisterChannels(mockGuild);

      expect(mockCreateMonitoredChannel).toHaveBeenCalledTimes(1);
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to register channel',
        expect.objectContaining({
          channelId: 'channel1',
          channelName: 'general',
          guildId: TEST_GUILD_ID,
          error: 'Access denied',
          statusCode: 403,
        })
      );
    });

    it('should handle 500 Internal Server Error and log HTTP status code', async () => {
      const mockChannels = new Collection();
      mockChannels.set('channel1', {
        id: 'channel1',
        name: 'general',
        type: ChannelType.GuildText,
      } as any);

      (mockGuild.channels.fetch as any).mockResolvedValue(mockChannels);

      const apiError = new ApiError(
        'Internal server error',
        '/api/v2/monitored-channels',
        500,
        { detail: 'Database connection failed' }
      );
      mockCreateMonitoredChannel.mockRejectedValueOnce(apiError);

      await service.autoRegisterChannels(mockGuild);

      expect(mockCreateMonitoredChannel).toHaveBeenCalledTimes(1);
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to register channel',
        expect.objectContaining({
          channelId: 'channel1',
          channelName: 'general',
          guildId: TEST_GUILD_ID,
          error: 'Internal server error',
          statusCode: 500,
        })
      );
    });

    it('should handle ApiError with partial failure on multiple channels and log statusCode', async () => {
      // Discord.js Collection (extends Map) iterates in insertion order.
      // The mock responses below are set up to match this order:
      // channel1 -> success, channel2 -> ApiError, channel3 -> success
      const mockChannels = new Collection();
      mockChannels.set('channel1', {
        id: 'channel1',
        name: 'general',
        type: ChannelType.GuildText,
      } as any);
      mockChannels.set('channel2', {
        id: 'channel2',
        name: 'announcements',
        type: ChannelType.GuildText,
      } as any);
      mockChannels.set('channel3', {
        id: 'channel3',
        name: 'random',
        type: ChannelType.GuildText,
      } as any);

      (mockGuild.channels.fetch as any).mockResolvedValue(mockChannels);

      const apiError = new ApiError(
        'Invalid request',
        '/api/v2/monitored-channels',
        400,
        { detail: 'Bad request data' }
      );
      // Mock responses in Collection insertion order (channel1, channel2, channel3)
      mockCreateMonitoredChannel
        .mockResolvedValueOnce({ id: 'response-1' })  // channel1: success
        .mockRejectedValueOnce(apiError)              // channel2: ApiError
        .mockResolvedValueOnce({ id: 'response-3' }); // channel3: success

      await service.autoRegisterChannels(mockGuild);

      expect(mockCreateMonitoredChannel).toHaveBeenCalledTimes(3);
      expect(mockLogger.error).toHaveBeenCalledTimes(1);
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to register channel',
        expect.objectContaining({
          channelId: 'channel2',
          channelName: 'announcements',
          guildId: TEST_GUILD_ID,
          error: 'Invalid request',
          statusCode: 400,
        })
      );
    });

    it('should handle empty channel list', async () => {
      const mockChannels = new Collection();

      (mockGuild.channels.fetch as any).mockResolvedValue(mockChannels);

      await service.autoRegisterChannels(mockGuild);

      expect(mockCreateMonitoredChannel).not.toHaveBeenCalled();
    });

    it('should handle channel fetch errors', async () => {
      (mockGuild.channels.fetch as any).mockRejectedValue(
        new Error('Failed to fetch channels')
      );

      await expect(
        service.autoRegisterChannels(mockGuild)
      ).rejects.toThrow('Failed to fetch channels');

      expect(mockCreateMonitoredChannel).not.toHaveBeenCalled();
    });

    it('should use correct default configuration values', async () => {
      const mockChannels = new Collection();
      mockChannels.set('channel1', {
        id: 'channel1',
        name: 'general',
        type: ChannelType.GuildText,
      } as any);

      (mockGuild.channels.fetch as any).mockResolvedValue(mockChannels);
      mockCreateMonitoredChannel.mockResolvedValue({
        id: 'response-id',
      });

      await service.autoRegisterChannels(mockGuild);

      expect(mockCreateMonitoredChannel).toHaveBeenCalledWith({
        community_server_id: TEST_GUILD_ID,
        channel_id: 'channel1',
        name: 'general',
        enabled: true,
        similarity_threshold: 0.6,
        dataset_tags: [],
        updated_by: null,
      });
    });
  });
});
