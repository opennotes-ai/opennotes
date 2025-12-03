import { jest } from '@jest/globals';
import { ChannelType, Collection } from 'discord.js';

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

  beforeEach(() => {
    service = new GuildSetupService();
    jest.clearAllMocks();

    mockGuild = {
      id: '123456789',
      name: 'Test Guild',
      channels: {
        fetch: jest.fn<(...args: any[]) => Promise<any>>(),
      },
    };
  });

  describe('autoRegisterChannels', () => {
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
        community_server_id: '123456789',
        channel_id: 'channel1',
        enabled: true,
        similarity_threshold: 0.6,
        dataset_tags: ['snopes'],
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
        community_server_id: '123456789',
        channel_id: 'channel1',
        enabled: true,
        similarity_threshold: 0.6,
        dataset_tags: ['snopes'],
        updated_by: null,
      });
    });
  });
});
